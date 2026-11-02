from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import json
import os
import pandas as pd
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch as reportlab_inch, cm
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import black
from datetime import datetime, timedelta
from typing import List, Dict, Any
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from reporter import send_telegram_report, send_email_report
import threading
import random
import string
import re
from telegram_bot import start_bot
from qr_parse import parse_qr_texts, fill_from_labels_db, find_cart_for_exit
from reporte import router as reporte_router, registrar_en_log
from typing import Optional

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Iniciar bot de Telegram interactivo en segundo plano
    threading.Thread(target=start_bot, daemon=True).start()
    
    # Programar reporte por hora en Telegram
    scheduler.add_job(send_telegram_report, 'interval', hours=1, id='telegram_job')
    # Programar reporte de fin de turno (7:30 AM y 7:30 PM) por Email
    scheduler.add_job(send_email_report, 'cron', hour=7, minute=30, id='email_job_morning')
    scheduler.add_job(send_email_report, 'cron', hour=19, minute=30, id='email_job_evening')
    
    scheduler.start()
    print("APScheduler iniciado con tareas programadas.")
    yield
    scheduler.shutdown()

app = FastAPI(title="API Sistema de Etiquetas", lifespan=lifespan)
app.include_router(reporte_router)

# --- Configuración CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'data.json')
LOGO_PATH = os.path.join(BASE_DIR, 'Logo.png')
DRYING_FILE = os.path.join(BASE_DIR, 'drying_state.json')
PRINT_QUEUE_FILE = os.path.join(BASE_DIR, 'print_queue.json')
LABELS_FILE = os.path.join(BASE_DIR, 'generated_labels.json')

# --- Modelo de Datos ---
class PartData(BaseModel):
    descripcion: str
    linea: str
    id: str
    qtu: str
    linea_lg: str
    ayuda_visual: str

    @field_validator('qtu', mode='before')
    @classmethod
    def coerce_qtu(cls, v):
        """Acepta int o str. Convierte int → str para almacenamiento uniforme."""
        if isinstance(v, int):
            return str(v)
        return str(v).strip() if v is not None else '0'

# --- Modelo para la Cola de Impresión ---
class PrintQueueItem(BaseModel):
    part: str
    desc: str
    qty: int
    turno: str
    maquina: Optional[str] = None   # máquina elegida al imprimir (ej. "10")

# --- ENDPOINTS COLA DE TELEGRAM ---
TELEGRAM_QUEUE_FILE = os.path.join(BASE_DIR, 'telegram_queue.json')

@app.get("/telegram-queue")
def get_telegram_queue():
    if not os.path.exists(TELEGRAM_QUEUE_FILE):
        return {"actions": []}
    try:
        with open(TELEGRAM_QUEUE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"actions": []}

class TelegramActions(BaseModel):
    actions: List[Dict[str, Any]]

@app.post("/telegram-queue/clear")
def clear_telegram_queue(data: TelegramActions):
    with open(TELEGRAM_QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump({"actions": data.actions}, f, indent=4)
    return {"message": "Queue updated"}

# --- ENDPOINTS ESTADO DEL CUARTO DE SECADO ---
class DryingState(BaseModel):
    records: List[Dict[str, Any]] = []
    acumuladoPorParte: Dict[str, int] = {}
    contadorCarritos: Dict[str, int] = {}
    turnoActual: str = ""
    historialTurnos: List[Dict[str, Any]] = []

class PrintQueueState(BaseModel):
    queue: List[Dict[str, Any]] = []


class GeneradorEtiquetas:
    """
    Clase para generar etiquetas en PDF.
    Diseño de 6x5 pulgadas, 4 etiquetas por hoja horizontal.
    """

    def _draw_single_label(self, c, part_info, part_number, cantidad_por_etiqueta, turno, label_type="standard", cart_number=None, label_id=None):
        """Dibuja una sola etiqueta con el diseño de 6x5 pulgadas y su ID único.

        Layout:
          ┌──────────┬──────────────────┬────────┐
          │  Logo    │  Fecha / Turno   │  EPP   │  ← Header  (~0.9")
          ├──────────┴──────────────────┼────────┤
          │ Part Number: [  valor  ]    │        │
          │ Description: [  valor  ]    │ MÁQ 9  │  ← Filas  (~1.2")
          │ Qty:         [  valor  ]    │        │
          ├─────────────────────────────┼────────┤
          │                             │ [QR 1] │  ← QR     (~1.8")
          │                             │ [QR 2] │
          ├─────────────────────────────┴────────┤
          │  EPP Lider        Iqc                │  ← Footer (~0.6")
          └──────────────────────────────────────┘
        """
        if not label_id:
            label_id = f"ETQ-{datetime.now().strftime('%y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"
        default_font = "Helvetica"
        bold_font    = "Helvetica-Bold"

        # ── Dimensiones base ────────────────────────────────────────────────
        M  = 0.25 * reportlab_inch
        ux, uy = M, M
        uw = 5.5 * reportlab_inch    # ancho útil
        uh = 4.5 * reportlab_inch    # alto útil

        HDR_H = 0.9  * reportlab_inch   # header
        FTR_H = 0.0                     # no separate footer
        CTN_H = uh - HDR_H - FTR_H      # contenido ocupa todo el resto

        ftr_y = uy
        ctn_y = ftr_y + FTR_H
        hdr_y = ctn_y + CTN_H

        # ── Anchos de columnas ──────────────────────────────────────────────
        LBL_W = 1.15 * reportlab_inch   # labels
        VAL_W = 2.35 * reportlab_inch   # valores
        QR_W  = uw - LBL_W - VAL_W     # máquina + QR (≈ 2.0")

        lbl_x = ux
        val_x = lbl_x + LBL_W
        qr_x  = val_x + VAL_W

        # ── Zonas verticales del contenido ──────────────────────────────────
        ROW_H  = 0.35 * reportlab_inch   # altura de cada fila (compacta)
        ROWS_N = 3
        ROWS_H = ROW_H * ROWS_N          # zona filas = 1.2"
        QR_ZH  = CTN_H - ROWS_H         # zona QR   = 1.8"

        # rows_bot_y = y donde terminan las filas (= inicio zona QR desde abajo)
        rows_bot_y = hdr_y - ROWS_H

        # ── Borde exterior ──────────────────────────────────────────────────
        c.setLineWidth(0.8)
        c.rect(ux, uy, uw, uh)

        # ════════════════════════════════════════════════════════════════════
        #  HEADER
        # ════════════════════════════════════════════════════════════════════
        c.line(ux, hdr_y, ux + uw, hdr_y)

        # Logo
        LOGO_BOX_W = 1.75 * reportlab_inch
        pad = 0.1 * reportlab_inch
        
        # Caja interior para el logo
        inner_logo_w = LOGO_BOX_W - 2 * pad
        inner_logo_h = HDR_H - 2 * pad
        c.rect(ux + pad, hdr_y + pad, inner_logo_w, inner_logo_h)
        
        if os.path.exists(LOGO_PATH):
            try:
                # preserveAspectRatio=True para que quede "cuadrado" y no se estire
                c.drawImage(LOGO_PATH,
                            ux + pad, hdr_y + pad,
                            width=inner_logo_w,
                            height=inner_logo_h,
                            mask='auto', preserveAspectRatio=True, anchor='c')
            except Exception as e:
                print(f"Error al dibujar logo: {e}")

        # Cliente / EPP
        EPP_W = 1.5 * reportlab_inch
        epp_x = ux + uw - EPP_W
        
        # Caja interior para EPP
        inner_epp_w = EPP_W - 2 * pad
        inner_epp_h = HDR_H - 2 * pad
        c.rect(epp_x + pad, hdr_y + pad, inner_epp_w, inner_epp_h)

        cliente_text = part_info.get('linea_lg', '').strip().upper()
        fs_epp = 40
        c.setFont(bold_font, fs_epp)
        tw = c.stringWidth(cliente_text, bold_font, fs_epp)
        while tw > (inner_epp_w - 0.1 * reportlab_inch) and fs_epp > 6:
            fs_epp -= 1
            c.setFont(bold_font, fs_epp)
            tw = c.stringWidth(cliente_text, bold_font, fs_epp)
        c.drawString(epp_x + pad + (inner_epp_w - tw) / 2,
                     hdr_y + pad + (inner_epp_h - fs_epp * 0.72) / 2,
                     cliente_text)

        # Fecha, turno y ID único de etiqueta
        center_x = (ux + LOGO_BOX_W + epp_x) / 2
        c.setFont(default_font, 10)
        c.drawCentredString(center_x, hdr_y + HDR_H * 0.68,
                            f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
        c.drawCentredString(center_x, hdr_y + HDR_H * 0.40,
                            f"Turno: {turno}")
        c.setFont(bold_font, 10)
        c.drawCentredString(center_x, hdr_y + HDR_H * 0.12,
                            f"ID: {label_id}")

        # ════════════════════════════════════════════════════════════════════
        #  LÍNEAS ESTRUCTURALES DEL CONTENIDO
        # ════════════════════════════════════════════════════════════════════
        # Divisor vertical QR — recorre todo el contenido (filas + zona QR)
        c.line(qr_x, ctn_y, qr_x, hdr_y)
        # Separador horizontal entre zona filas y zona QR
        c.line(ux, rows_bot_y, ux + uw, rows_bot_y)
        # Divisor vertical inferior — divide EPS Lider e Iqc por la mitad (de ctn_y a rows_bot_y)
        mid_bot_x = ux + (LBL_W + VAL_W) / 2
        c.line(mid_bot_x, ctn_y, mid_bot_x, rows_bot_y)

        # ════════════════════════════════════════════════════════════════════
        #  ZONA SUPERIOR: filas de información (compactas)
        # ════════════════════════════════════════════════════════════════════
        info_rows = [
            ("Part Number:", part_number),
            ("Description:", part_info.get('descripcion', '')),
            ("Qty:",         str(cantidad_por_etiqueta)),
        ]
        BOX_H  = ROW_H - 0.08 * reportlab_inch
        FS_LBL = 9

        row_top = hdr_y
        for i, (lbl_txt, val_txt) in enumerate(info_rows):
            row_bot = row_top - ROW_H

            # Label centrado verticalmente en la fila
            lbl_y = row_bot + (ROW_H - FS_LBL * reportlab_inch / 72) / 2
            c.setFont(default_font, FS_LBL)
            c.drawString(lbl_x + 0.07 * reportlab_inch, lbl_y, lbl_txt)

            # Caja del valor centrada verticalmente
            bm_x = 0.06 * reportlab_inch
            bx   = val_x + bm_x
            bw   = VAL_W - 2 * bm_x
            bh   = BOX_H
            by   = row_bot + (ROW_H - BOX_H) / 2
            c.rect(bx, by, bw, bh)

            # Texto dentro de la caja
            if lbl_txt == "Description:":
                fs_d = 10
                while fs_d > 5:
                    style = ParagraphStyle(
                        name='DS', fontName=bold_font, fontSize=fs_d,
                        leading=fs_d + 1, alignment=1, textColor=black
                    )
                    p = Paragraph(val_txt, style)
                    pw, ph = p.wrapOn(c, bw - 0.08 * reportlab_inch, bh)
                    if ph <= bh:
                        break
                    fs_d -= 1
                p.drawOn(c, bx + 0.04 * reportlab_inch, by + (bh - ph) / 2)
            else:
                fs_v = 10
                c.setFont(bold_font, fs_v)
                vw = c.stringWidth(val_txt, bold_font, fs_v)
                while vw > (bw - 0.08 * reportlab_inch) and fs_v > 5:
                    fs_v -= 1
                    c.setFont(bold_font, fs_v)
                    vw = c.stringWidth(val_txt, bold_font, fs_v)
                c.drawString(bx + (bw - vw) / 2,
                             by + (bh - fs_v * reportlab_inch / 72) / 2,
                             val_txt)

            row_top = row_bot

        # ════════════════════════════════════════════════════════════════════
        #  ZONA SUPERIOR DERECHA: nombre de máquina
        # ════════════════════════════════════════════════════════════════════
        if label_type == "eps" and cart_number is not None:
            machine_name = f"Cartón: {cart_number}"
        elif part_info.get('_maquina'):
            machine_name = f"MÁQUINA {part_info['_maquina']}"
        else:
            machine_name = part_info.get('linea', '').strip().upper()

        fs_m = 11
        c.setFont(bold_font, fs_m)
        mw = c.stringWidth(machine_name, bold_font, fs_m)
        while mw > (QR_W - 0.1 * reportlab_inch) and fs_m > 6:
            fs_m -= 1
            c.setFont(bold_font, fs_m)
            mw = c.stringWidth(machine_name, bold_font, fs_m)
        # Centrado verticalmente en la zona de filas (columna derecha)
        mach_y = rows_bot_y + ROWS_H / 2 - (fs_m * reportlab_inch / 72) / 2
        c.drawString(qr_x + (QR_W - mw) / 2, mach_y, machine_name)

        # ════════════════════════════════════════════════════════════════════
        #  ZONA INFERIOR DERECHA: QR codes
        # ════════════════════════════════════════════════════════════════════
        qr_size = min(QR_W - 0.22 * reportlab_inch,
                      QR_ZH / 2 - 0.16 * reportlab_inch)
        qr_cx = qr_x + (QR_W - qr_size) / 2

        # QR 1 — Número de parte + ID único en una sola línea (mitad superior).
        # Así cualquiera de los dos QR basta para identificar la parte.
        qr1_y = ctn_y + QR_ZH / 2 + 0.10 * reportlab_inch
        self._generar_qr_code(c, f"{part_number} {label_id}", qr_cx, qr1_y, qr_size)
        c.setFont(bold_font, 7)
        c.drawCentredString(qr_cx + qr_size / 2, qr1_y - 8, f"ID: {label_id}")

        # QR 2 — Información completa con ID único (mitad inferior de la zona QR)
        qr_full = (f"ID: {label_id}\n"
                   f"Fecha: {datetime.now().strftime('%d/%m/%Y')}\n"
                   f"Turno: {turno}\n"
                   f"Part Number: {part_number}\n"
                   f"Description: {part_info.get('descripcion', '')}\n"
                   f"Qty: {cantidad_por_etiqueta}\n"
                   f"ID Catálogo: {part_info.get('id', '')}\n"
                   f"Máquina: {part_info.get('_maquina') or part_info.get('linea', '')}")
        qr2_y = ctn_y + 0.08 * reportlab_inch
        self._generar_qr_code(c, qr_full, qr_cx, qr2_y, qr_size)

        # ════════════════════════════════════════════════════════════════════
        #  FOOTER TEXT (inside columns)
        # ════════════════════════════════════════════════════════════════════
        c.setFont(default_font, 10)
        lider_txt = f"{cliente_text} Lider" if cliente_text else "EPS Lider"
        mid_bot_x = ux + (LBL_W + VAL_W) / 2
        c.drawCentredString(ux + (LBL_W + VAL_W) / 4, uy + 0.1 * reportlab_inch, lider_txt)
        c.drawCentredString(mid_bot_x + (LBL_W + VAL_W) / 4, uy + 0.1 * reportlab_inch, "Iqc")

    def _generar_qr_code(self, canvas, data, x, y, size):
        """Renderiza un código QR directamente sobre el PDF en memoria."""
        qr_widget = qr.QrCodeWidget(data)
        bounds    = qr_widget.getBounds()
        width     = bounds[2] - bounds[0]
        height    = bounds[3] - bounds[1]
        scale_x   = size / width
        scale_y   = size / height
        drawing   = Drawing(size, size, transform=[scale_x, 0, 0, scale_y, 0, 0])
        drawing.add(qr_widget)
        renderPDF.draw(drawing, canvas, x, y)


# --- Funciones Auxiliares ---
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_drying_state():
    if os.path.exists(DRYING_FILE):
        try:
            with open(DRYING_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}

def load_generated_labels():
    if os.path.exists(LABELS_FILE):
        try:
            with open(LABELS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}

def save_generated_labels(labels):
    with open(LABELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(labels, f, indent=4, ensure_ascii=False)

# --- Endpoints (Rutas de la API) ---

@app.get("/parts")
def get_parts():
    """Devuelve todos los números de parte registrados."""
    return load_data()

@app.post("/parts/import")
async def import_parts(file: UploadFile = File(...)):
    """Recibe un archivo Excel/CSV e importa los números de parte a data.json."""
    MAX_FILE_SIZE = 5 * 1024 * 1024
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo el archivo: {str(e)}")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="El archivo excede el límite de 5 MB.")

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents), dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(contents), dtype=str)

        df.fillna('', inplace=True)

        column_map = {
            'Número de Parte': 'part_number',
            'Descripción': 'descripcion',
            'Línea': 'linea',
            'ID': 'id',
            'Cantidad': 'qtu',
            'Cliente (LG)': 'linea_lg',
            'Ayuda Visual': 'ayuda_visual'
        }
        df.rename(columns={k: v for k, v in column_map.items() if k in df.columns}, inplace=True)

        if 'part_number' not in df.columns:
            raise HTTPException(status_code=400, detail="El archivo debe contener una columna llamada 'Número de Parte'.")

        data = load_data()
        imported_count = 0

        for index, row in df.iterrows():
            part_number = str(row.get('part_number', '')).strip().upper()
            if not part_number: continue

            data[part_number] = {
                'descripcion': str(row.get('descripcion', '')).strip(),
                'linea': str(row.get('linea', '')).strip(),
                'id': str(row.get('id', '')).strip(),
                'qtu': str(row.get('qtu', '')).strip(),
                'linea_lg': str(row.get('linea_lg', '')).strip(),
                'ayuda_visual': str(row.get('ayuda_visual', '')).strip()
            }
            imported_count += 1

        save_data(data)
        return {"message": f"¡Éxito! {imported_count} partes importadas correctamente."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando el archivo: {str(e)}")

@app.post("/parts/{part_number}")
def add_part(part_number: str, part_data: PartData):
    """Agrega un nuevo número de parte."""
    data = load_data()
    part_number_upper = part_number.strip().upper()

    if part_number_upper in data:
        raise HTTPException(status_code=400, detail=f"El número de parte '{part_number_upper}' ya existe.")

    data[part_number_upper] = part_data.model_dump()
    save_data(data)
    return {"message": "Parte agregada exitosamente", "part": part_number_upper}

@app.put("/parts/{old_part_number}")
def edit_part(old_part_number: str, part_data: PartData, new_part_number: str = None):
    """Edita una parte existente. Permite cambiar el número de parte si se envía new_part_number."""
    data = load_data()
    old_part_upper = old_part_number.strip().upper()

    if old_part_upper not in data:
        raise HTTPException(status_code=404, detail="Número de parte original no encontrado.")

    target_part_number = old_part_upper
    if new_part_number:
        new_part_upper = new_part_number.strip().upper()
        if new_part_upper != old_part_upper and new_part_upper in data:
            raise HTTPException(status_code=400, detail="El nuevo número de parte ya está en uso.")
        target_part_number = new_part_upper
        if new_part_upper != old_part_upper:
            del data[old_part_upper]

    data[target_part_number] = part_data.model_dump()
    save_data(data)
    return {"message": "Parte actualizada exitosamente"}

@app.delete("/parts/{part_number}")
def delete_part(part_number: str):
    """Borra un número de parte."""
    data = load_data()
    part_number_upper = part_number.strip().upper()

    if part_number_upper not in data:
        raise HTTPException(status_code=404, detail="Número de parte no encontrado.")

    del data[part_number_upper]
    save_data(data)
    return {"message": "Parte eliminada exitosamente"}

@app.post("/print-queue/generate-pdf")
def generate_pdf(queue: list[PrintQueueItem]):
    """Genera un archivo PDF a partir de la cola de impresión usando ReportLab."""
    part_data = load_data()
    generador = GeneradorEtiquetas()

    try:
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=landscape(letter))
        page_w, page_h = landscape(letter)

        margin = 0.5 * cm

        usable_w = page_w - (2 * margin)
        usable_h = page_h - (2 * margin)

        target_label_w = usable_w / 2
        target_label_h = usable_h / 2

        original_label_w = 6 * reportlab_inch
        original_label_h = 5 * reportlab_inch

        scale_x = target_label_w / original_label_w
        scale_y = target_label_h / original_label_h

        positions = [
            (margin, page_h - margin - target_label_h),
            (margin + target_label_w, page_h - margin - target_label_h),
            (margin, margin),
            (margin + target_label_w, margin)
        ]

        label_count_on_page = 0
        labels_db = load_generated_labels()
        now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
        fecha_str = datetime.now().strftime('%d/%m/%Y')

        for item in queue:
            part_number = item.part
            num_labels_for_part = item.qty
            turno = item.turno
            part_info = part_data.get(part_number)
            if not part_info: continue

            qty_on_label = part_info.get('qtu', '0')
            maq = (item.maquina or '').strip()
            if maq:
                part_info = {**part_info, '_maquina': maq}

            for _ in range(num_labels_for_part):
                unique_label_id = f"ETQ-{datetime.now().strftime('%y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"
                labels_db[unique_label_id] = {
                    "id": unique_label_id,
                    "part_number": part_number,
                    "descripcion": part_info.get('descripcion', ''),
                    "qty": int(qty_on_label) if str(qty_on_label).isdigit() else 0,
                    "linea": part_info.get('linea', ''),
                    "maquina": int(maq) if maq.isdigit() else None,
                    "cliente": part_info.get('linea_lg', ''),
                    "turno": turno,
                    "fecha": fecha_str,
                    "created_at": now_iso
                }

                if label_count_on_page >= 4:
                    c.showPage()
                    label_count_on_page = 0

                x_offset, y_offset = positions[label_count_on_page]

                c.saveState()
                c.translate(x_offset, y_offset)
                c.scale(scale_x, scale_y)
                generador._draw_single_label(c, part_info, part_number, qty_on_label, turno, label_id=unique_label_id)
                c.restoreState()

                label_count_on_page += 1

        save_generated_labels(labels_db)

        c.save()
        buffer.seek(0)

        return Response(content=buffer.getvalue(), media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CameraScanPayload(BaseModel):
    qr_data: str
    action: str  # "entrada" o "salida"

@app.get("/labels/{label_id}")
def get_label_by_id(label_id: str):
    """Devuelve los datos de una etiqueta generada por su ID único."""
    labels_db = load_generated_labels()
    target_id = label_id.strip().upper()
    if target_id not in labels_db:
        raise HTTPException(status_code=404, detail=f"Etiqueta '{target_id}' no encontrada.")
    return labels_db[target_id]

@app.post("/drying-room/scan")
def register_camera_scan(payload: CameraScanPayload):
    """
    Recibe un escaneo de la cámara local y registra entrada o salida identificando la etiqueta única.
    """
    raw_data = payload.qr_data.strip()
    
    labels_db = load_generated_labels()
    parsed = fill_from_labels_db(parse_qr_texts([raw_data]), labels_db)
    label_id = parsed['label_id']
    part_number = parsed['part_number']
    lbl_info = labels_db.get(label_id) if label_id else None

    parts_db = load_data()
    part_info = parts_db.get(part_number) if part_number else None
    if not part_info and lbl_info:
        part_info = {
            'descripcion': lbl_info.get('descripcion', ''),
            'linea': lbl_info.get('linea', ''),
            'qtu': str(lbl_info.get('qty', 0)),
            'linea_lg': lbl_info.get('cliente', ''),
        }

    if not part_info and not part_number:
        raise HTTPException(status_code=404, detail="No se encontró la parte ni la etiqueta correspondiente.")

    qty = int(part_info.get('qtu', 0)) if part_info else (lbl_info.get('qty', 0) if lbl_info else 0)
    state = load_drying_state()
    records = state.get('records', [])
    acumulado_por_parte = state.get('acumuladoPorParte', {})
    contador_carritos = state.get('contadorCarritos', {})
    
    from reporter import get_current_shift_info
    shift_name, _ = get_current_shift_info()

    if payload.action == 'entrada':
        carrito_id = label_id or ("C-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8)))
        if label_id:
            for r in records:
                if r.get('idCarrito') == label_id and r.get('estado') == 'EN SECADO':
                    raise HTTPException(status_code=400, detail=f"La etiqueta '{label_id}' ya está EN SECADO.")

        prev_acumulado = acumulado_por_parte.get(part_number, 0) + qty
        new_record = {
            "idCarrito": carrito_id,
            "numeroParte": part_number,
            "descripcion": part_info.get('descripcion', '') if part_info else '',
            "maquina": (f"maquina {lbl_info['maquina']}" if lbl_info and lbl_info.get('maquina') else (part_info.get('linea', '') if part_info else '')),
            "qty": qty,
            "acumulado": prev_acumulado,
            "turno": shift_name,
            "estado": "EN SECADO",
            "horaEntrada": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            "horaSalida": None,
            "tiempoMinutos": None,
            "earlyExit": False,
        }
        records.append(new_record)
        acumulado_por_parte[part_number] = prev_acumulado
        contador_carritos[part_number] = contador_carritos.get(part_number, 0) + 1
        
        state['records'] = records
        state['acumuladoPorParte'] = acumulado_por_parte
        state['contadorCarritos'] = contador_carritos
        state['turnoActual'] = shift_name
        
        with open(DRYING_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
        registrar_en_log([new_record])
        return {"message": "Entrada registrada", "record": new_record}

    elif payload.action == 'salida':
        target, err = find_cart_for_exit(records, label_id, part_number)
        if not target:
            raise HTTPException(status_code=400, detail=err)

        hora_entrada = datetime.fromisoformat(target['horaEntrada'].replace('Z', '+00:00'))
        hora_salida = datetime.utcnow()
        minutos = round((hora_salida - hora_entrada.replace(tzinfo=None)).total_seconds() / 60, 1)
        
        target['estado'] = 'FINALIZADO'
        target['horaSalida'] = hora_salida.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        target['tiempoMinutos'] = minutos
        
        with open(DRYING_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
        registrar_en_log([target])
        return {"message": "Salida registrada", "record": target}

    raise HTTPException(status_code=400, detail="Acción inválida. Usa 'entrada' o 'salida'.")

@app.get("/drying-room/state")
def get_drying_state():
    """Devuelve el estado actual de los carritos y acumulados."""
    state = load_drying_state()
    try:
        state['lastUpdated'] = os.path.getmtime(DRYING_FILE)
    except:
        state['lastUpdated'] = 0
    return state

@app.post("/drying-room/state")
def update_drying_state(state: DryingState):
    """Actualiza el estado global del cuarto de secado.
    Limita los registros históricos a los últimos 30 días para evitar crecimiento indefinido.
    """
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()

    filtered_records = [
        r for r in state.records
        if not r.get('horaEntrada') or r.get('horaEntrada', '') >= cutoff or r.get('estado') == 'EN SECADO'
    ]
    state.records = filtered_records
    try:
        registrar_en_log(state.records)
    except Exception as e:
        print(f"[reporte] Error registrando en log: {e}")

    with open(DRYING_FILE, 'w', encoding='utf-8') as f:
        json.dump(state.model_dump(), f, indent=4, ensure_ascii=False)
    return {"message": f"Estado sincronizado. {len(filtered_records)} registros activos."}

@app.get("/print-queue/state")
def get_print_queue_state():
    """Devuelve la cola de impresión guardada en disco."""
    if os.path.exists(PRINT_QUEUE_FILE):
        try:
            with open(PRINT_QUEUE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"queue": []}

@app.post("/print-queue/state")
def save_print_queue_state(state: PrintQueueState):
    """Guarda el estado actual de la cola de impresión en disco."""
    with open(PRINT_QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state.model_dump(), f, indent=4, ensure_ascii=False)
    return {"message": "Cola de impresión guardada exitosamente."}