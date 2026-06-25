import os
import json
import smtplib
from email.message import EmailMessage
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

DRYING_FILE = 'drying_state.json'

def get_current_shift_info():
    """Determina el turno actual y su hora de inicio basándose en la hora actual."""
    now = datetime.now()
    
    # Horarios de corte
    shift_day_start = now.replace(hour=7, minute=30, second=0, microsecond=0)
    shift_night_start = now.replace(hour=19, minute=30, second=0, microsecond=0)
    
    if shift_day_start <= now < shift_night_start:
        return "DÍA", shift_day_start
    elif now >= shift_night_start:
        return "NOCHE", shift_night_start
    else:
        # Entre medianoche y las 07:30 am, pertenece al turno NOCHE del día anterior
        return "NOCHE", shift_night_start - timedelta(days=1)

def get_production_data(shift_name, shift_start):
    """Filtra y consolida los datos de producción del turno especificado."""
    if not os.path.exists(DRYING_FILE):
        return []
        
    try:
        with open(DRYING_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
    except json.JSONDecodeError:
        return []

    records = state.get('records', [])
    
    # Agrupar datos
    production = {}
    for r in records:
        hora_entrada_str = r.get('horaEntrada')
        if not hora_entrada_str:
            continue
            
        try:
            hora_entrada = datetime.fromisoformat(hora_entrada_str.replace('Z', '+00:00'))
            # Convertir UTC a local si es necesario, asumiendo que horaEntrada se guardó en local o UTC.
            # En Javascript (new Date().toISOString()) guarda en UTC. 
            # Como la app React usa ISO, en Python debemos ser cuidadosos con la zona horaria.
            # Simplificación: comparar strings si están en la misma zona, o parsear bien.
            # Mejor usar un filtro por el campo 'turno' que ya guarda la app.
        except:
            pass

        # Filtrar por turno y asegurarnos de que es del turno actual
        # Para evitar mezclar turnos de días anteriores, verificamos la hora
        try:
            dt = datetime.fromisoformat(hora_entrada_str.replace('Z', '+00:00'))
            # Convertir a timezone naive local para comparar con shift_start
            # Esto es un workaround simple asumiendo que el servidor y el cliente están en la misma zona horaria
            # Si el cliente mandó 'Z' (UTC), calculamos el offset
            if hora_entrada_str.endswith('Z'):
                # Ajuste rudimentario (CST = UTC-6, ajusta si es necesario)
                dt = dt - timedelta(hours=6) 
                dt = dt.replace(tzinfo=None)
            
            if dt < shift_start:
                continue
        except:
            pass

        # Validamos explícitamente el turno
        if r.get('turno', '').upper() != shift_name.upper():
            continue

        part = r.get('numeroParte', 'DESC')
        if part not in production:
            production[part] = {
                'part': part,
                'maquina': r.get('maquina', ''),
                'desc': r.get('descripcion', ''),
                'cliente': r.get('cliente', ''),
                'lotes': 0,
                'qty': 0
            }
        
        production[part]['lotes'] += 1
        production[part]['qty'] += int(r.get('qty', 0))

    return list(production.values())

def format_telegram_message(data, shift_name):
    """Genera el texto para Telegram."""
    total_lotes = sum(item['lotes'] for item in data)
    total_piezas = sum(item['qty'] for item in data)
    
    msg = f"📊 *Reporte de Producción (Acumulado)*\n"
    msg += f"🗓 Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    msg += f"🏭 Turno: *{shift_name}*\n\n"
    msg += f"📦 *Total Lotes:* {total_lotes}\n"
    msg += f"🧩 *Total Piezas:* {total_piezas}\n\n"
    
    if not data:
        msg += "⚠️ No hay producción registrada en este turno aún."
        return msg
        
    msg += "📋 *Detalle por Parte:*\n"
    for item in data:
        cliente_str = f" - {item['cliente']}" if item['cliente'] else ""
        msg += f"• `{item['part']}`{cliente_str}: {item['qty']} pzas ({item['lotes']} lotes)\n"
        
    return msg

def format_email_html(data, shift_name):
    """Genera el HTML para el correo."""
    total_lotes = sum(item['lotes'] for item in data)
    total_piezas = sum(item['qty'] for item in data)
    
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #4F46E5;">Reporte de Producción - Fin de Turno</h2>
        <p><strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        <p><strong>Turno:</strong> {shift_name}</p>
        <hr>
        <h3>Resumen General</h3>
        <ul>
            <li><strong>Total Lotes (Carritos):</strong> {total_lotes}</li>
            <li><strong>Total Piezas Producidas:</strong> {total_piezas}</li>
        </ul>
        <h3>Detalle de Producción</h3>
    """
    
    if not data:
        html += "<p>No hay producción registrada en este turno.</p></body></html>"
        return html
        
    html += """
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 800px;">
            <tr style="background-color: #f3f4f6;">
                <th>N° Parte</th>
                <th>Máquina</th>
                <th>Descripción</th>
                <th>Cliente</th>
                <th>Lotes</th>
                <th>Total Piezas</th>
            </tr>
    """
    for item in data:
        html += f"""
            <tr>
                <td><strong>{item['part']}</strong></td>
                <td>{item['maquina']}</td>
                <td>{item['desc']}</td>
                <td>{item['cliente']}</td>
                <td style="text-align: center;">{item['lotes']}</td>
                <td style="text-align: right; color: #7C3AED; font-weight: bold;">{item['qty']}</td>
            </tr>
        """
    html += "</table><br><p><em>Sistema de Gestión de Secado y Etiquetas</em></p></body></html>"
    return html

def generate_excel_bytes(data, shift_name):
    """Genera el reporte en Excel y devuelve los bytes."""
    import pandas as pd
    import io
    
    if not data:
        return None
        
    df = pd.DataFrame(data)
    # Renombrar columnas para que se vean bien
    df.rename(columns={
        'part': 'N° Parte',
        'maquina': 'Máquina',
        'desc': 'Descripción',
        'cliente': 'Cliente',
        'lotes': 'Lotes',
        'qty': 'Total Piezas'
    }, inplace=True)
    
    # Ordenar columnas
    df = df[['N° Parte', 'Máquina', 'Descripción', 'Cliente', 'Lotes', 'Total Piezas']]
    
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f'Reporte {shift_name}')
    
    excel_buffer.seek(0)
    return excel_buffer.read()

def send_telegram_report():
    """Ejecutado cada hora."""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_ids_env = os.getenv('TELEGRAM_CHAT_ID')
    
    if not token or not chat_ids_env or chat_ids_env == 'tu_chat_id_aqui':
        print("Telegram no configurado.")
        return
        
    chat_ids = [cid.strip() for cid in chat_ids_env.split(',') if cid.strip()]
    
    shift_name, shift_start = get_current_shift_info()
    data = get_production_data(shift_name, shift_start)
    text = format_telegram_message(data, shift_name)
    
    # Send document if data exists
    excel_bytes = generate_excel_bytes(data, shift_name)
    
    for chat_id in chat_ids:
        # Send text
        url_text = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        
        try:
            response = requests.post(url_text, json=payload)
            response.raise_for_status()
            print(f"[{datetime.now()}] Reporte Telegram enviado con éxito a {chat_id}.")
            
            if excel_bytes:
                url_doc = f"https://api.telegram.org/bot{token}/sendDocument"
                filename = f"Reporte_Produccion_{shift_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
                files = {'document': (filename, excel_bytes, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                data_doc = {'chat_id': chat_id}
                doc_response = requests.post(url_doc, data=data_doc, files=files)
                doc_response.raise_for_status()
                print(f"[{datetime.now()}] Excel enviado a Telegram con éxito a {chat_id}.")
        except Exception as e:
            print(f"Error enviando Telegram a {chat_id}: {e}")

def send_email_report():
    """Ejecutado al final del turno."""
    sender = os.getenv('EMAIL_SENDER')
    password_raw = os.getenv('EMAIL_PASSWORD')
    password = password_raw.replace(' ', '') if password_raw else ''
    receivers_str = os.getenv('EMAIL_RECEIVERS')
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = os.getenv('SMTP_PORT')
    
    if not sender or not password or password == 'tu_password_de_aplicacion':
        print("Correo no configurado.")
        return
        
    receivers = [r.strip() for r in receivers_str.split(',') if r.strip()]
    if not receivers:
        return
        
    now = datetime.now() - timedelta(minutes=5)
    shift_day_start = now.replace(hour=7, minute=30, second=0, microsecond=0)
    shift_night_start = now.replace(hour=19, minute=30, second=0, microsecond=0)
    
    if shift_day_start <= now < shift_night_start:
        shift_name, shift_start = "DÍA", shift_day_start
    elif now >= shift_night_start:
        shift_name, shift_start = "NOCHE", shift_night_start
    else:
        shift_name, shift_start = "NOCHE", shift_night_start - timedelta(days=1)

    data = get_production_data(shift_name, shift_start)
    html_content = format_email_html(data, shift_name)
    
    msg = EmailMessage()
    msg['Subject'] = f"Reporte de Producción - Fin de Turno {shift_name} - {datetime.now().strftime('%d/%m/%Y')}"
    msg['From'] = sender
    msg['To'] = ", ".join(receivers)
    msg.set_content("Por favor habilita HTML para ver este correo.")
    msg.add_alternative(html_content, subtype='html')
    
    # Adjuntar reporte en Excel
    excel_bytes = generate_excel_bytes(data, shift_name)
    if excel_bytes:
        filename = f"Reporte_Produccion_{shift_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        msg.add_attachment(
            excel_bytes,
            maintype='application',
            subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=filename
        )

    try:
        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        print(f"[{datetime.now()}] Reporte Correo enviado con éxito a {msg['To']}.")
        
        # Opcional: También enviar el resumen final a Telegram
        send_telegram_report()
    except Exception as e:
        print(f"Error enviando Correo: {e}")
