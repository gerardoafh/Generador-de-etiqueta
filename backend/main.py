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
from telegram_bot import start_bot

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

# --- Configuración CORS ---
# Permite que React (que corre en un puerto distinto) haga peticiones a esta API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción deberías poner la URL de tu frontend, ej: ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = 'data.json'
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logo.png")
DRYING_FILE = 'drying_state.json'
PRINT_QUEUE_FILE = 'print_queue.json'

# --- Modelo de Datos ---
# FastAPI valida automáticamente que la información enviada desde React tenga este formato
class PartData(BaseModel):
    descripcion: str
    linea: str
    id: str
    qtu: str           # Se guarda como string para mantener compatibilidad con el JSON existente
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

# --- ENDPOINTS COLA DE TELEGRAM ---
TELEGRAM_QUEUE_FILE = 'telegram_queue.json'

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
    # Escribir la nueva lista (usualmente vacía o con los que fallaron)
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
    Utiliza el diseño de 6x5 pulgadas y genera un PDF con 4 etiquetas por hoja horizontal.
    """
    def _draw_single_label(self, c, part_info, part_number, cantidad_por_etiqueta, turno, label_type="standard", cart_number=None):
        """Dibuja una sola etiqueta con el diseño original de 6x5 pulgadas."""
        # --- Constantes de Fuentes ---
        default_font = "Helvetica"
        bold_font = "Helvetica-Bold"
        
        # --- Dibujar cuadros base ---
        c.rect(0.25 * reportlab_inch, 0.25 * reportlab_inch, 5.5 * reportlab_inch, 4.5 * reportlab_inch)
        c.rect(0.5 * reportlab_inch, 3.72 * reportlab_inch, 1.5 * reportlab_inch, 0.8 * reportlab_inch)

        # --- Logo ---
        if os.path.exists(LOGO_PATH):
            try:
                c.drawImage(LOGO_PATH, 0.6 * reportlab_inch, 3.745 * reportlab_inch, width=1.3 * reportlab_inch, height=0.75 * reportlab_inch, mask='auto')
            except Exception as e:
                c.setFont(default_font, 8)
                c.drawCentredString(1.25 * reportlab_inch, 4.12 * reportlab_inch, "Error Logo")
                print(f"Error al dibujar imagen: {e}")
        else:
            c.setFont(default_font, 10)
            c.drawCentredString(1.25 * reportlab_inch, 4.12 * reportlab_inch, "Logo no encontrado")

        # --- Cuadro superior derecho (Cliente) ---
        box_top_right_x = 4 * reportlab_inch
        box_top_right_y = 3.72 * reportlab_inch
        box_top_right_width = 1.5 * reportlab_inch
        box_top_right_height = 0.8 * reportlab_inch
        c.rect(box_top_right_x, box_top_right_y, box_top_right_width, box_top_right_height)

        display_text_top_right = part_info.get('linea_lg', '').upper()
        font_size_top_right = 40
        c.setFont(bold_font, font_size_top_right)
        
        text_width_top_right = c.stringWidth(display_text_top_right, bold_font, font_size_top_right)
        while text_width_top_right > (box_top_right_width - 0.1 * reportlab_inch) and font_size_top_right > 5:
            font_size_top_right -= 1
            c.setFont(bold_font, font_size_top_right)
            text_width_top_right = c.stringWidth(display_text_top_right, bold_font, font_size_top_right)

        text_x_top_right = box_top_right_x + (box_top_right_width - text_width_top_right) / 2
        text_y_top_right = box_top_right_y + (box_top_right_height - font_size_top_right * 0.8) / 2
        c.drawString(text_x_top_right, text_y_top_right, display_text_top_right)

        # --- Fecha y Turno ---
        c.setFont(default_font, 12)
        c.drawString(2.33 * reportlab_inch, 4.1 * reportlab_inch, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
        
        # --- Dibujar el Turno en la etiqueta ---
        c.setFont(default_font, 12)
        c.drawString(2.33 * reportlab_inch, 3.8 * reportlab_inch, f"Turno: {turno}")


        # --- Información de la Parte ---
        info_y_start = 3.2 * reportlab_inch
        box_label_x = 0.5 * reportlab_inch
        box_value_x = 1.5 * reportlab_inch
        box_value_width = 2.4 * reportlab_inch
        box_height_abs = 0.3 * reportlab_inch
        box_height_vector = -box_height_abs

        labels_and_values = {
            "Part Number:": part_number,
            "Description:": part_info.get('descripcion', ''),
            "Qty:": str(cantidad_por_etiqueta)
        }

        y_pos = info_y_start
        for label, value in labels_and_values.items():
            c.setFont(default_font, 12)
            c.drawString(box_label_x, y_pos, label)
            
            value_box_y = y_pos + 0.2 * reportlab_inch
            c.rect(box_value_x, value_box_y, box_value_width, box_height_vector)

            if label == "Description:":
                font_size_desc = 14
                while font_size_desc > 5:
                    style = ParagraphStyle(name='DescStyle', fontName=bold_font, fontSize=font_size_desc, leading=font_size_desc + 1, alignment=1, textColor=black)
                    p = Paragraph(value, style)
                    w, h = p.wrapOn(c, box_value_width - 0.1 * reportlab_inch, box_height_abs)
                    if h <= box_height_abs: break
                    font_size_desc -= 1
                p.drawOn(c, box_value_x + 0.05 * reportlab_inch, (value_box_y + box_height_vector) + (box_height_abs - h) / 2)
            else:
                c.setFont(bold_font, 14)
                text_width = c.stringWidth(value, bold_font, 14)
                c.drawString(box_value_x + (box_value_width - text_width) / 2, y_pos, value)
            
            y_pos -= 0.4 * reportlab_inch

        # --- Texto dinámico (según Línea o Carrito) ---
        if label_type == "eps" and cart_number is not None:
            dynamic_text_bottom_content = f"Cartón: {cart_number}"
        else:
            linea = part_info.get('linea', 'SIN LINEA').strip().upper()
            dynamic_text_bottom_content = linea

        c.setFont(bold_font, 12)
        dynamic_text_width = c.stringWidth(dynamic_text_bottom_content, bold_font, 12)
        c.drawString(4 * reportlab_inch + (1.75 * reportlab_inch - dynamic_text_width) / 2, y_pos + 0.4 * reportlab_inch, dynamic_text_bottom_content)

        # --- Líneas Divisorias y Códigos QR ---
        line_y_separator = y_pos + 0.15 * reportlab_inch
        c.line(0.25 * reportlab_inch, line_y_separator, 5.75 * reportlab_inch, line_y_separator)
        
        qr_size = 0.75 * reportlab_inch
        qr_x_pos = 4 * reportlab_inch + (1.75 * reportlab_inch - qr_size) / 2

        y_qr1 = line_y_separator - 0.05 * reportlab_inch - qr_size
        self._generar_qr_code(c, part_number, qr_x_pos, y_qr1, qr_size)
        
        y_qr2 = y_qr1 - 0.05 * reportlab_inch - qr_size
        
        qr_data_info = f"Fecha: {datetime.now().strftime('%d/%m/%Y')}\nPart Number: {part_number}\nDescription: {part_info.get('descripcion', '')}\nQty: {cantidad_por_etiqueta}\nID: {part_info.get('id', '')}\nLínea: {part_info.get('linea', '')}"
        
        self._generar_qr_code(c, qr_data_info, qr_x_pos, y_qr2, qr_size)

        # --- Líneas adicionales y textos inferiores ---
        c.line(0.25 * reportlab_inch, 3.5 * reportlab_inch, 5.75 * reportlab_inch, 3.5 * reportlab_inch)
        c.line(4 * reportlab_inch, 3.5 * reportlab_inch, 4 * reportlab_inch, 0.25 * reportlab_inch)
        c.line(1.4 * reportlab_inch, line_y_separator, 1.4 * reportlab_inch, 0.25 * reportlab_inch)
        c.line(2.75 * reportlab_inch, line_y_separator, 2.75 * reportlab_inch, 0.25 * reportlab_inch)

        c.setFont(default_font, 10)
        bottom_text_y = y_qr2 - 0.25 * reportlab_inch
        
        cliente = part_info.get('linea_lg', '').strip()
        texto_iqc = f"{cliente.upper()} IQC" if cliente else "IQC"

        c.drawString(0.6 * reportlab_inch, bottom_text_y, "LQC")
        c.drawString(1.9 * reportlab_inch, bottom_text_y, "OQC")
        c.drawString(3.12 * reportlab_inch, bottom_text_y, texto_iqc)

    def _generar_qr_code(self, canvas, data, x, y, size):
        # Crear el widget del código QR nativo de ReportLab
        qr_widget = qr.QrCodeWidget(data)
        
        # Obtener las dimensiones del código QR para escalar correctamente
        bounds = qr_widget.getBounds()
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Calcular la escala basándose en el tamaño (size) deseado
        scale_x = size / width
        scale_y = size / height
        
        # Crear un "Drawing" escalado y añadir el QR
        drawing = Drawing(size, size, transform=[scale_x, 0, 0, scale_y, 0, 0])
        drawing.add(qr_widget)
        
        # Pintar directamente sobre el PDF en memoria sin usar disco duro
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

# --- Endpoints (Rutas de la API) ---

@app.get("/parts")
def get_parts():
    """Devuelve todos los números de parte registrados."""
    return load_data()

@app.post("/parts/import")
async def import_parts(file: UploadFile = File(...)):
    """Recibe un archivo Excel/CSV e importa los números de parte a data.json."""
    # --- Validar tamaño máximo del archivo (5 MB) ---
    MAX_FILE_SIZE = 5 * 1024 * 1024
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo el archivo: {str(e)}")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="El archivo excede el límite de 5 MB.")

    try:
        # Detectar si es CSV o Excel
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents), dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(contents), dtype=str)

        
        df.fillna('', inplace=True)
        
        # Mapear las columnas en español a las llaves que usa tu JSON
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
        
        # Iterar sobre las filas del Excel y guardar en el JSON
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
    
    # Si el usuario cambió el número de parte en el formulario
    target_part_number = old_part_upper
    if new_part_number:
        new_part_upper = new_part_number.strip().upper()
        if new_part_upper != old_part_upper and new_part_upper in data:
            raise HTTPException(status_code=400, detail="El nuevo número de parte ya está en uso.")
        target_part_number = new_part_upper
        # Eliminar el registro viejo si cambió de nombre
        if new_part_upper != old_part_upper:
            del data[old_part_upper]

    # Guardar los nuevos datos
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

        for item in queue:
            part_number = item.part
            num_labels_for_part = item.qty
            turno = item.turno
            part_info = part_data.get(part_number)
            if not part_info: continue
            
            qty_on_label = part_info.get('qtu', '0')

            for _ in range(num_labels_for_part):
                if label_count_on_page >= 4:
                    c.showPage()
                    label_count_on_page = 0
                
                x_offset, y_offset = positions[label_count_on_page]
                
                c.saveState()
                c.translate(x_offset, y_offset)
                c.scale(scale_x, scale_y)
                generador._draw_single_label(c, part_info, part_number, qty_on_label, turno)
                c.restoreState()
                
                label_count_on_page += 1

        c.save()
        buffer.seek(0)
        
        return Response(content=buffer.getvalue(), media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/drying-room/state")
def get_drying_state():
    """Devuelve el estado actual de los carritos y acumulados."""
    return load_drying_state()

@app.post("/drying-room/state")
def update_drying_state(state: DryingState):
    """Actualiza el estado global del cuarto de secado.
    Limita los registros históricos a los últimos 30 días para evitar crecimiento indefinido.
    """
    # Fecha límite: hace 30 días
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()

    # Filtrar solo records con horaEntrada dentro del rango o sin fecha (los activos)
    filtered_records = [
        r for r in state.records
        if not r.get('horaEntrada') or r.get('horaEntrada', '') >= cutoff or r.get('estado') == 'EN SECADO'
    ]
    state.records = filtered_records

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