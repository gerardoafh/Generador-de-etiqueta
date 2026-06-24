import os
import re
import io
import json
import random
import string
import difflib
from datetime import datetime

import telebot
import cv2
import numpy as np
from PIL import Image
from pyzbar.pyzbar import decode as qr_decode
from dotenv import load_dotenv

from reporter import get_current_shift_info, get_production_data, format_telegram_message, generate_excel_bytes

load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN')

DRYING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'drying_state.json')
DATA_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')

# Estado temporal por chat: guarda la parte detectada antes de que el
# usuario diga "entrada" o "salida" en un mensaje separado.
_pending_part: dict[int, dict] = {}  # chat_id → {part_number, part_info, qty}


# ─────────────────────────────────────────────
#  Helpers de archivo
# ─────────────────────────────────────────────
def _load_json(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}


def _save_json(path: str, data: dict):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _gen_id() -> str:
    return "C-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ─────────────────────────────────────────────
#  Leer QR desde bytes de imagen
# ─────────────────────────────────────────────
def _read_qr_from_bytes(image_bytes: bytes) -> str | None:
    """Intenta leer el QR con pyzbar y OpenCV. Devuelve el texto o None."""
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img_cv = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    # 1. pyzbar sobre imagen original
    pil_img = Image.open(io.BytesIO(image_bytes))
    decoded = qr_decode(pil_img)
    if decoded:
        return decoded[0].data.decode('utf-8', errors='ignore')

    # 2. pyzbar sobre escala de grises ecualizada
    if img_cv is not None:
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        decoded2 = qr_decode(Image.fromarray(gray))
        if decoded2:
            return decoded2[0].data.decode('utf-8', errors='ignore')

        # 3. Detector nativo de OpenCV
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img_cv)
        if data:
            return data

    return None


# ─────────────────────────────────────────────
#  Corrección de errores comunes de OCR
# ─────────────────────────────────────────────
# Tesseract confunde frecuentemente estos caracteres en texto de etiquetas
_OCR_CHAR_FIXES = [
    (r'2(?=[A-Z])',        'Z'),  # 2Z → Z  (MC2Z → MCZ)
    (r'(?<=[A-Z])2',       'Z'),  # Z2 → Z
    (r'\bO(?=\d)',         '0'),  # O seguido de número → 0
    (r'(?<=\d)O\b',        '0'),  # número seguido de O → 0
    (r'(?<=[A-Z])l',       '1'),  # l minúscula en texto → 1
    (r'(?<=[A-Z])I(?=\d)', '1'),  # I mayúscula antes de número → 1
    (r'(?<=\d)S(?=\d)',    '5'),  # S entre números → 5
    (r'(?<=\d)B(?=\d)',    '8'),  # B entre números → 8
]


def _fix_ocr_part_number(raw: str) -> str:
    """Aplica correcciones de caracteres comunes de OCR al número de parte."""
    result = raw.upper().strip()
    for pattern, replacement in _OCR_CHAR_FIXES:
        result = re.sub(pattern, replacement, result)
    return result


def _fuzzy_match_part(ocr_raw: str, parts_db: dict, cutoff: float = 0.82) -> str | None:
    """
    Busca el número de parte más parecido al texto OCR en la base de datos.
    Primero aplica correcciones de caracteres; si no coincide exactamente,
    usa búsqueda difusa (difflib). Devuelve el mejor match o None.
    """
    known_parts = list(parts_db.keys())
    if not known_parts:
        return None

    # 1. Corrección de caracteres → match exacto
    fixed = _fix_ocr_part_number(ocr_raw)
    if fixed in parts_db:
        return fixed

    # 2. Búsqueda difusa sobre el texto corregido
    matches = difflib.get_close_matches(fixed, known_parts, n=1, cutoff=cutoff)
    if matches:
        return matches[0]

    # 3. Búsqueda difusa sobre el texto original (por si la corrección empeoró algo)
    matches = difflib.get_close_matches(ocr_raw.upper(), known_parts, n=1, cutoff=cutoff)
    if matches:
        return matches[0]

    return None


# ─────────────────────────────────────────────
#  OCR de fallback cuando el QR no se lee
# ─────────────────────────────────────────────
def _ocr_extract_part_info(image_bytes: bytes) -> dict | None:
    """
    Usa Tesseract OCR para extraer Part Number y Qty del texto impreso.
    Devuelve {'part_number': str, 'qty': int|None, 'ocr_raw': str} o None.
    """
    try:
        import pytesseract

        # Ruta de Tesseract en Windows (en Linux se detecta automáticamente)
        for p in [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]:
            if os.path.exists(p):
                pytesseract.pytesseract.tesseract_cmd = p
                break

        # Preprocesar imagen
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img_cv = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        gray   = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        gray   = cv2.GaussianBlur(gray, (3, 3), 0)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 10
        )
        enlarged = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

        ocr_text = pytesseract.image_to_string(Image.fromarray(enlarged), config='--psm 6')
        print(f"[OCR] Texto extraído:\n{ocr_text}")

        # El (?i) es manejado por re.IGNORECASE. Hacemos que "Part" y la "N" sean opcionales
        # por si la foto está cortada (ej. "art Number" o "umber")
        part_match = re.search(r'(?:P?art\s*)?N?umber\s*[:\|]?\s*([A-Z0-9]{5,20})', ocr_text, re.IGNORECASE)
        qty_match  = re.search(r'Qty\s*[:\|]?\s*(\d+)', ocr_text, re.IGNORECASE)

        ocr_raw = part_match.group(1).strip().upper() if part_match else None
        qty     = int(qty_match.group(1)) if qty_match else None

        if ocr_raw:
            return {'part_number': ocr_raw, 'qty': qty, 'ocr_raw': ocr_raw}

    except ImportError:
        print("[OCR] pytesseract no instalado.")
    except Exception as e:
        print(f"[OCR] Error: {e}")

    return None


# ─────────────────────────────────────────────
#  Extraer número de parte del payload del QR
# ─────────────────────────────────────────────
def _parse_part_number_from_qr(qr_text: str) -> str | None:
    """
    El QR contiene líneas como:
        Part Number: MAL62524101
        Description: BARRIER INS C
        ...
    Extrae el valor de 'Part Number'.
    """
    match = re.search(r'Part\s+Number[:\s]+([A-Z0-9_\-]+)', qr_text, re.IGNORECASE)
    if match:
        return match.group(1).strip().upper()
    # QR simple que solo contiene el número de parte
    candidate = qr_text.strip().upper()
    if re.match(r'^[A-Z0-9_\-]{5,}$', candidate):
        return candidate
    return None


# ─────────────────────────────────────────────
#  Operaciones en el cuarto de secado
# ─────────────────────────────────────────────
def _registrar_entrada(part_number: str, part_info: dict, qty: int) -> dict:
    """Agrega un carrito al cuarto de secado con estado 'EN SECADO'."""
    state               = _load_json(DRYING_FILE)
    records             = state.get('records', [])
    acumulado_por_parte = state.get('acumuladoPorParte', {})
    contador_carritos   = state.get('contadorCarritos', {})

    shift_name, _ = get_current_shift_info()
    prev_acumulado = acumulado_por_parte.get(part_number, 0) + qty

    new_record = {
        "idCarrito":    _gen_id(),
        "numeroParte":  part_number,
        "descripcion":  part_info.get('descripcion', ''),
        "maquina":      part_info.get('linea', ''),
        "qty":          qty,
        "acumulado":    prev_acumulado,
        "turno":        shift_name,
        "estado":       "EN SECADO",
        "horaEntrada":  datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        "horaSalida":   None,
        "tiempoMinutos": None,
        "earlyExit":    False,
    }

    records.append(new_record)
    acumulado_por_parte[part_number] = prev_acumulado
    contador_carritos[part_number]   = contador_carritos.get(part_number, 0) + 1

    state['records']           = records
    state['acumuladoPorParte'] = acumulado_por_parte
    state['contadorCarritos']  = contador_carritos
    state['turnoActual']       = shift_name

    _save_json(DRYING_FILE, state)
    return new_record


def _registrar_salida(part_number: str) -> dict | None:
    """Marca el carrito EN SECADO más reciente de esa parte como FINALIZADO."""
    state   = _load_json(DRYING_FILE)
    records = state.get('records', [])

    target = None
    for r in reversed(records):
        if r.get('numeroParte') == part_number and r.get('estado') == 'EN SECADO':
            target = r
            break

    if target is None:
        return None

    hora_entrada = datetime.fromisoformat(target['horaEntrada'].replace('Z', '+00:00'))
    hora_salida  = datetime.utcnow()
    minutos      = round((hora_salida - hora_entrada.replace(tzinfo=None)).total_seconds() / 60, 1)

    target['estado']        = 'FINALIZADO'
    target['horaSalida']    = hora_salida.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    target['tiempoMinutos'] = minutos

    _save_json(DRYING_FILE, state)
    return target


# ─────────────────────────────────────────────
#  Procesador central de foto + acción
# ─────────────────────────────────────────────
def _procesar_foto_con_accion(bot: telebot.TeleBot, chat_id: int,
                               image_bytes: bytes, accion: str | None):
    """
    Intenta leer el QR; si falla, usa OCR con corrección de errores y
    búsqueda difusa contra los números de parte registrados.
    Luego ejecuta la acción (entrada/salida) o espera confirmación.
    """
    parts_db = _load_json(DATA_FILE)

    # ── 1. Intentar QR ───────────────────────────────────────────────────────
    qr_text = _read_qr_from_bytes(image_bytes)

    if qr_text:
        part_number = _parse_part_number_from_qr(qr_text)
        if not part_number:
            bot.send_message(chat_id,
                f"⚠️ Leí el QR pero no encontré el número de parte.\n"
                f"Contenido QR:\n`{qr_text[:200]}`", parse_mode="Markdown")
            return
        ocr_qty    = None
        via_ocr    = False
        ocr_raw    = None
    else:
        # ── 2. Fallback OCR ──────────────────────────────────────────────────
        bot.send_message(chat_id, "🔍 QR no detectado, leyendo texto de la etiqueta...")
        ocr_result = _ocr_extract_part_info(image_bytes)

        if not ocr_result:
            bot.send_message(chat_id,
                "⚠️ No pude leer ni el QR ni el texto de la etiqueta.\n"
                "Envía la foto con mejor iluminación o usa el comando:\n"
                "`entrada MCZ60014601`",
                parse_mode="Markdown")
            return

        ocr_raw  = ocr_result['ocr_raw']
        ocr_qty  = ocr_result.get('qty')
        via_ocr  = True

        # 2a. Corrección + búsqueda difusa
        matched = _fuzzy_match_part(ocr_raw, parts_db)
        if matched:
            part_number = matched
            if matched != ocr_raw:
                bot.send_message(chat_id,
                    f"📝 OCR leyó `{ocr_raw}` → corregido a `{matched}`",
                    parse_mode="Markdown")
            else:
                bot.send_message(chat_id,
                    f"📝 Texto leído por OCR: `{part_number}`",
                    parse_mode="Markdown")
        else:
            bot.send_message(chat_id,
                f"⚠️ OCR leyó `{ocr_raw}` pero no encontré una parte similar en el sistema.\n"
                f"Usa el comando manual: `entrada {ocr_raw}`",
                parse_mode="Markdown")
            return

    # ── 3. Buscar datos en la base ───────────────────────────────────────────
    part_info = parts_db.get(part_number)
    if not part_info:
        bot.send_message(chat_id,
            f"⚠️ La parte `{part_number}` no está registrada en el sistema.",
            parse_mode="Markdown")
        return

    qty = ocr_qty if ocr_qty else int(part_info.get('qtu', 0))

    # ── 4. Ejecutar acción ───────────────────────────────────────────────────
    if accion == 'entrada':
        record = _registrar_entrada(part_number, part_info, qty)
        bot.send_message(chat_id,
            f"✅ *Entrada registrada*\n"
            f"🏷 Parte: `{part_number}`\n"
            f"📋 Descripción: {part_info.get('descripcion', '')}\n"
            f"📦 Qty: {qty} pzas\n"
            f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="Markdown")
        _pending_part.pop(chat_id, None)

    elif accion == 'salida':
        record = _registrar_salida(part_number)
        if record is None:
            bot.send_message(chat_id,
                f"⚠️ No encontré un carrito *EN SECADO* activo para `{part_number}`.\n"
                f"Verifica en el sistema si ya fue registrado.",
                parse_mode="Markdown")
        else:
            bot.send_message(chat_id,
                f"✅ *Salida registrada*\n"
                f"🏷 Parte: `{part_number}`\n"
                f"📋 Descripción: {record['descripcion']}\n"
                f"⏱ Tiempo en secado: {record['tiempoMinutos']} min\n"
                f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}",
                parse_mode="Markdown")
        _pending_part.pop(chat_id, None)

    else:
        # Sin acción: guardar pendiente y pedir confirmación
        _pending_part[chat_id] = {
            'part_number': part_number,
            'part_info':   part_info,
            'qty':         qty,
        }
        bot.send_message(chat_id,
            f"📷 Etiqueta leída correctamente:\n"
            f"🏷 Parte: `{part_number}`\n"
            f"📋 Descripción: {part_info.get('descripcion', '')}\n"
            f"📦 Qty: {qty} pzas\n\n"
            f"¿Qué deseas hacer?\n"
            f"👉 Escribe *entrada* o *salida*",
            parse_mode="Markdown")


# ─────────────────────────────────────────────
#  Configuración del bot
# ─────────────────────────────────────────────
bot = None
if token:
    bot = telebot.TeleBot(token)

    # ── Handler de FOTOS ─────────────────────────────────────────────────────
    @bot.message_handler(content_types=['photo'])
    def handle_photo(message):
        caption = (message.caption or "").strip().lower()
        accion  = 'entrada' if 'entrada' in caption else ('salida' if 'salida' in caption else None)

        file_info  = bot.get_file(message.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)

        _procesar_foto_con_accion(bot, message.chat.id, downloaded, accion)

    # ── Handler de TEXTO ─────────────────────────────────────────────────────
    @bot.message_handler(content_types=['text'])
    def handle_all_messages(message):
        text    = (message.text or "").strip().lower()
        chat_id = message.chat.id

        # ── Comando manual: "entrada MCZ60014601" / "salida MCZ60014601" ─────
        match_cmd = re.match(r'^(entrada|salida)\s+([A-Za-z0-9_\-]{4,})$', text.strip())
        if match_cmd:
            accion_manual = match_cmd.group(1)
            part_number   = match_cmd.group(2).upper()
            parts_db      = _load_json(DATA_FILE)
            part_info     = parts_db.get(part_number)
            if not part_info:
                # Intentar fuzzy match también para el comando manual
                matched = _fuzzy_match_part(part_number, parts_db)
                if matched:
                    part_info   = parts_db[matched]
                    bot.send_message(chat_id,
                        f"📝 `{part_number}` → corregido a `{matched}`",
                        parse_mode="Markdown")
                    part_number = matched
                else:
                    bot.send_message(chat_id,
                        f"⚠️ La parte `{part_number}` no está registrada en el sistema.",
                        parse_mode="Markdown")
                    return
            qty = int(part_info.get('qtu', 0))
            if accion_manual == 'entrada':
                _registrar_entrada(part_number, part_info, qty)
                bot.send_message(chat_id,
                    f"✅ *Entrada manual registrada*\n"
                    f"🏷 Parte: `{part_number}`\n"
                    f"📋 Descripción: {part_info.get('descripcion', '')}\n"
                    f"📦 Qty: {qty} pzas\n"
                    f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}",
                    parse_mode="Markdown")
            else:
                record = _registrar_salida(part_number)
                if record is None:
                    bot.send_message(chat_id,
                        f"⚠️ No encontré un carrito *EN SECADO* activo para `{part_number}`.",
                        parse_mode="Markdown")
                else:
                    bot.send_message(chat_id,
                        f"✅ *Salida manual registrada*\n"
                        f"🏷 Parte: `{part_number}`\n"
                        f"⏱ Tiempo en secado: {record['tiempoMinutos']} min\n"
                        f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}",
                        parse_mode="Markdown")
            return

        # ── Acción diferida (foto enviada antes sin caption) ─────────────────
        if text in ('entrada', 'salida') and chat_id in _pending_part:
            pending     = _pending_part[chat_id]
            part_number = pending['part_number']
            part_info   = pending['part_info']
            qty         = pending['qty']

            if text == 'entrada':
                _registrar_entrada(part_number, part_info, qty)
                bot.send_message(chat_id,
                    f"✅ *Entrada registrada*\n"
                    f"🏷 Parte: `{part_number}`\n"
                    f"📋 Descripción: {part_info.get('descripcion', '')}\n"
                    f"📦 Qty: {qty} pzas\n"
                    f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}",
                    parse_mode="Markdown")
            else:
                record = _registrar_salida(part_number)
                if record is None:
                    bot.send_message(chat_id,
                        f"⚠️ No encontré un carrito *EN SECADO* activo para `{part_number}`.",
                        parse_mode="Markdown")
                else:
                    bot.send_message(chat_id,
                        f"✅ *Salida registrada*\n"
                        f"🏷 Parte: `{part_number}`\n"
                        f"⏱ Tiempo en secado: {record['tiempoMinutos']} min\n"
                        f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}",
                        parse_mode="Markdown")

            _pending_part.pop(chat_id, None)
            return

        # ── Búsqueda de pieza específica ──────────────────────────────────────
        match_part = re.search(r'pieza(?:s)?\s+(?:de\s+)?([a-zA-Z0-9_-]+)', text)
        if match_part:
            part_num = match_part.group(1).upper()
            try:
                shift_name, shift_start = get_current_shift_info()
                data      = get_production_data(shift_name, shift_start)
                part_data = next((item for item in data if item['part'].upper() == part_num), None)
                if part_data:
                    bot.send_message(chat_id,
                        f"🏭 *Turno {shift_name}*\n"
                        f"N° Parte: `{part_num}`\n"
                        f"Descripción: {part_data['desc']}\n"
                        f"📦 Lotes: {part_data['lotes']}\n"
                        f"🧩 *Total Piezas: {part_data['qty']}*",
                        parse_mode="Markdown")
                else:
                    bot.send_message(chat_id,
                        f"⚠️ No se han ingresado lotes del número de parte `{part_num}` "
                        f"en el turno actual ({shift_name}).", parse_mode="Markdown")
            except Exception as e:
                print(f"Error buscando parte específica: {e}")
                bot.reply_to(message, "Ocurrió un error al buscar el número de parte.")
            return

        # ── Reporte de producción general ─────────────────────────────────────
        if "reporte" in text and ("producción" in text or "produccion" in text
                                   or "actual" in text or "hoy" in text):
            bot.reply_to(message, "Generando el reporte de producción actual... ⏳")
            try:
                shift_name, shift_start = get_current_shift_info()
                data        = get_production_data(shift_name, shift_start)
                msg_text    = format_telegram_message(data, shift_name)
                excel_bytes = generate_excel_bytes(data, shift_name)
                if excel_bytes:
                    filename = (f"Reporte_Produccion_{shift_name}_"
                                f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
                    bot.send_document(chat_id, (filename, excel_bytes),
                                      caption=msg_text, parse_mode="Markdown")
                else:
                    bot.send_message(chat_id, msg_text, parse_mode="Markdown")
            except Exception as e:
                print(f"Error generando reporte: {e}")
                bot.reply_to(message, "Ocurrió un error al generar el reporte.")
            return

        # ── Estado del cuarto de secado ───────────────────────────────────────
        if "secado" in text or "cuarto" in text or "carritos" in text:
            try:
                state   = _load_json(DRYING_FILE)
                records = state.get('records', [])
                activos = [r for r in records if r.get('estado') == 'EN SECADO']
                if not activos:
                    bot.send_message(chat_id,
                        "🟢 El cuarto de secado está *vacío* en este momento.",
                        parse_mode="Markdown")
                else:
                    lines = [f"🏭 *Cuarto de Secado — {len(activos)} carrito(s) activo(s)*\n"]
                    for r in activos:
                        hora = r.get('horaEntrada', '')[:16].replace('T', ' ')
                        lines.append(f"• `{r['numeroParte']}` — {r['descripcion']} "
                                     f"({r['qty']} pzas) — desde {hora}")
                    bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
            except Exception as e:
                print(f"Error consultando cuarto de secado: {e}")
                bot.reply_to(message, "Error consultando el cuarto de secado.")
            return

        # ── Ayuda ─────────────────────────────────────────────────────────────
        bot.send_message(chat_id,
            "🤖 *Comandos disponibles:*\n\n"
            "📷 *Foto de etiqueta* + caption `entrada` → Registrar entrada\n"
            "📷 *Foto de etiqueta* + caption `salida`  → Registrar salida\n"
            "📷 *Solo foto* → El bot lee el QR (o el texto si el QR está borroso)\n\n"
            "✏️ *Registro manual (si la foto no funciona):*\n"
            "• `entrada MCZ60014601` → Entrada manual por número de parte\n"
            "• `salida MCZ60014601`  → Salida manual por número de parte\n\n"
            "💬 *Consultas:*\n"
            "• `reporte de producción` → Reporte del turno actual\n"
            "• `piezas de [NUM_PARTE]` → Consulta específica de una parte\n"
            "• `cuarto de secado` → Ver carritos activos en este momento",
            parse_mode="Markdown")


def start_bot():
    """Inicia el bot en modo polling infinito."""
    if bot:
        print("Iniciando escucha activa de Telegram (con soporte de fotos QR + OCR)...")
        bot.infinity_polling()
    else:
        print("No se pudo iniciar Telegram: Falta TELEGRAM_BOT_TOKEN en .env")
