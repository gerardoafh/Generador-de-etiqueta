"""
Lectura unificada de QRs de etiqueta (usada por la API y el bot de Telegram).

Formatos soportados:
  QR chico  (nuevo):  "MFZ62834301 ETQ-261102-AB12C"      -> parte + ID único
  QR grande (nuevo):  "ID: ETQ-261102-AB12C\nFecha: ...\nPart Number: MFZ62834301\n..."
  QR chico  (viejo):  "MFZ62834301"                        -> solo parte

Reglas:
  - El número de parte se busca en CUALQUIER QR legible; con eso se da la entrada.
  - Solo se acepta como ID único algo con formato ETQ-AAMMDD-XXXXX
    (antes "ID: Packing" del catálogo se confundía con un ID de etiqueta).
  - Tolera pistolas con teclado en español (Ñ en lugar de ':' y ' o - en el ID)
    y texto "pegado" sin saltos de línea.
"""
import re
from datetime import datetime

LABEL_ID_RE = re.compile(r"ETQ['\-]?(\d{6})['\-]([A-Z0-9]{5})", re.IGNORECASE)
PART_RE = re.compile(r"PART\s*NUMBER\s*[:Ñ|]?\s*([A-Z0-9\-]{4,}?)(?=DESCRIPTION|QTY|\s|$)", re.IGNORECASE)
FIRST_TOKEN_RE = re.compile(r"^\s*([A-Z0-9\-]{5,})\s+ETQ", re.IGNORECASE)
PLAIN_RE = re.compile(r"^[A-Z0-9_\-]{5,}$", re.IGNORECASE)
DATE_RE = re.compile(r"FECHA\s*[:Ñ]?\s*(\d{2})[/\-](\d{2})[/\-](\d{4})", re.IGNORECASE)
QTY_RE = re.compile(r"QTY\s*[:Ñ]?\s*(\d+)", re.IGNORECASE)
TURNO_RE = re.compile(r"TURNO\s*[:Ñ]?\s*([A-ZÁÉÍÓÚ]+)", re.IGNORECASE)


def parse_qr_texts(texts):
    """Combina la información de todos los QRs leídos de una etiqueta."""
    info = {"label_id": None, "part_number": None, "fecha_qr": None, "qty": None, "turno": None}
    for raw in texts or []:
        t = (raw or "").strip()
        if not t:
            continue
        up = t.upper()

        m = LABEL_ID_RE.search(up)
        if m and not info["label_id"]:
            info["label_id"] = f"ETQ-{m.group(1)}-{m.group(2).upper()}"

        if not info["part_number"]:
            m = PART_RE.search(up) or FIRST_TOKEN_RE.search(up)
            if m:
                info["part_number"] = m.group(1).upper()
            elif PLAIN_RE.match(up) and not up.startswith("ETQ"):
                info["part_number"] = up

        m = DATE_RE.search(up)
        if m and not info["fecha_qr"]:
            info["fecha_qr"] = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"

        m = QTY_RE.search(up)
        if m and info["qty"] is None:
            info["qty"] = int(m.group(1))

        m = TURNO_RE.search(up)
        if m and not info["turno"]:
            info["turno"] = m.group(1)
    return info


def fill_from_labels_db(info, labels_db):
    """Completa parte/qty/fecha con el registro de la etiqueta impresa (si existe)."""
    lbl = labels_db.get(info.get("label_id")) if info.get("label_id") else None
    if lbl:
        info["part_number"] = info.get("part_number") or lbl.get("part_number")
        if info.get("qty") is None:
            info["qty"] = lbl.get("qty")
        info["fecha_qr"] = info.get("fecha_qr") or lbl.get("fecha")
    return info


def _hora(r):
    try:
        return datetime.fromisoformat(str(r.get("horaEntrada", "")).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.max


def find_cart_for_exit(records, label_id=None, part_number=None):
    """
    Devuelve (registro, error). Primero busca el carrito exacto por ID único;
    si no existe (p. ej. entró por número de parte), toma el carrito EN SECADO
    más antiguo de esa parte (FIFO real por hora de entrada).
    """
    if label_id:
        same = [r for r in records if r.get("idCarrito") == label_id]
        activo = next((r for r in same if r.get("estado") == "EN SECADO"), None)
        if activo:
            return activo, None
        if same:
            return None, f"La etiqueta {label_id} ya finalizó su secado anteriormente."
    if part_number:
        activos = [r for r in records if r.get("numeroParte") == part_number and r.get("estado") == "EN SECADO"]
        if activos:
            return min(activos, key=_hora), None
    return None, f"No hay carritos EN SECADO de {part_number or label_id}."
