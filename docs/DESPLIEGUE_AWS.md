# ☁️ Guía de Despliegue en Servidores AWS (Ubuntu EC2)

Esta guía documenta los pasos para desplegar en producción el **Sistema de Gestión de Etiquetas y Cuarto de Secado** en una instancia **EC2 de Amazon Web Services (AWS)** con sistema operativo **Ubuntu 22.04 LTS o 24.04 LTS**.

---

## 📑 Contenido de la Guía

1. [Requisitos de la Instancia EC2](#1-requisitos-de-la-instancia-ec2)
2. [Instalación de Dependencias del Sistema](#2-instalación-de-dependencias-del-sistema)
3. [Descarga y Configuración del Proyecto](#3-descarga-y-configuración-del-proyecto)
4. [Configuración de Variables de Entorno (.env)](#4-configuración-de-variables-de-entorno-env)
5. [Configuración de Servicio Systemd (Backend Autogestionado)](#5-configuración-de-servicio-systemd-backend)
6. [Compilación y Servicio del Frontend con Nginx](#6-compilación-y-servicio-del-frontend-con-nginx)
7. [Configuración de Certificado SSL (HTTPS con Certbot)](#7-configuración-de-certificado-ssl-https-con-certbot)
8. [Procedimiento para Desplegar Actualizaciones Futuras](#8-procedimiento-para-desplegar-actualizaciones-futuras)

---

## 1. Requisitos de la Instancia EC2

- **Tipo de Instancia sugerido:** `t3.small` o `t3.medium` (mínimo 2 GB RAM recomendado para procesamiento de imágenes con OpenCV/Tesseract).
- **Sistema Operativo:** Ubuntu Server 22.04 o 24.04 LTS (64-bit x86).
- **Puertos de Red (Security Groups en AWS):**
  - Puerto `22` (SSH) — Restringido a tu IP.
  - Puerto `80` (HTTP) — Abierto a `0.0.0.0/0`.
  - Puerto `443` (HTTPS) — Abierto a `0.0.0.0/0`.
  - Puerto `8000` *(Opcional si usas proxy Nginx)*.

---

## 2. Instalación de Dependencias del Sistema

Conéctate por SSH a tu instancia y ejecuta los siguientes comandos para preparar las librerías nativas requeridas por Python, OpenCV, ZBar, Tesseract y Node.js:

```bash
# 1. Actualizar repositorios
sudo apt update && sudo apt upgrade -y

# 2. Instalar paquetes de Python, herramientas de compilación y librerías de visión
sudo apt install -y python3 python3-pip python3-venv \
    libzbar0 libgl1 libglib2.0-0 tesseract-ocr nginx git curl

# 3. Instalar Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## 3. Descarga y Configuración del Proyecto

```bash
# Clonar el repositorio en el directorio home del usuario ubuntu
cd /home/ubuntu
git clone <URL_DE_TU_REPOSITORIO_GIT> CSECADO
cd CSECADO/mi-sistema-etiquetas

# Crear entorno virtual de Python
cd backend
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias de Python
pip install --upgrade pip
pip install -r requirements.txt
```

> [!NOTE]
> `opencv-python-headless` está configurado en `requirements.txt` para garantizar que no se soliciten librerías gráficas de X11 en servidores sin monitor.

---

## 4. Configuración de Variables de Entorno (.env)

Crea el archivo `.env` dentro de la carpeta `backend`:

```bash
nano /home/ubuntu/CSECADO/mi-sistema-etiquetas/backend/.env
```

Pega tus credenciales reales:
```env
TELEGRAM_BOT_TOKEN="tu_token_de_telegram"
TELEGRAM_CHAT_ID="7629357744, -1004412654974"

SMTP_SERVER="smtp.gmail.com"
SMTP_PORT=587
EMAIL_SENDER="tu_correo_de_envio@gmail.com"
EMAIL_PASSWORD="tu_password_de_aplicacion_google"
EMAIL_RECEIVERS="gerente@empresa.com, supervisor@empresa.com"
```
*(Guarda con `Ctrl + O` seguido de `Enter` y sal con `Ctrl + X`)*.

---

## 5. Configuración de Servicio Systemd (Backend)

Para que el backend de FastAPI y el hilo del Bot de Telegram arranquen automáticamente si el servidor se reinicia o sufre una caída:

Crea el archivo de servicio de systemd:
```bash
sudo nano /etc/systemd/system/etiquetas-backend.service
```

Agrega la siguiente configuración:
```ini
[Unit]
Description=Servicio Backend Sistema de Etiquetas FastAPI
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/CSECADO/mi-sistema-etiquetas/backend
Environment="PATH=/home/ubuntu/CSECADO/mi-sistema-etiquetas/backend/venv/bin"
ExecStart=/home/ubuntu/CSECADO/mi-sistema-etiquetas/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Habilita e inicia el servicio:
```bash
sudo systemctl daemon-reload
sudo systemctl enable etiquetas-backend
sudo systemctl start etiquetas-backend

# Verificar estado:
sudo systemctl status etiquetas-backend
```

---

## 6. Compilación y Servicio del Frontend con Nginx

### Compilar los activos de React con Vite:
```bash
cd /home/ubuntu/CSECADO/mi-sistema-etiquetas

# Instalar dependencias de npm
npm install

# Compilar para producción (genera la carpeta dist/)
npm run build
```

### Configurar Nginx:
Crea un archivo de configuración para el sitio:
```bash
sudo nano /etc/nginx/sites-available/etiquetas.conf
```

Pega la siguiente configuración (reemplaza `tu-dominio.com` por tu dominio o IP pública):
```nginx
server {
    listen 80;
    server_name tu-dominio.com;

    # Directorio de los archivos estáticos de React compilados
    root /home/ubuntu/CSECADO/mi-sistema-etiquetas/dist;
    index index.html;

    # Rutas SPA
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy inverso hacia el backend de FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Límite de carga para importación de hojas de cálculo
    client_max_body_size 10M;
}
```

Habilita la configuración y recarga Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/etiquetas.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

## 7. Configuración de Certificado SSL (HTTPS con Certbot)

El acceso a la cámara trasera para el escaneo web (`html5-qrcode`) **requiere obligatoriamente conexión HTTPS segura** por políticas de seguridad de los navegadores móviles.

Para activar un certificado SSL gratuito con Let's Encrypt:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tu-dominio.com
```
El asistente configurará la redirección automática de HTTP a HTTPS y renovará el certificado automáticamente.

---

## 8. Procedimiento para Desplegar Actualizaciones Futuras

Cuando realices mejoras en tu repositorio local y quieras desplegarlas en el servidor de producción:

```bash
# 1. En tu máquina de desarrollo local:
git add .
git commit -m "feat: mejoras del sistema"
git push origin main

# 2. En el servidor AWS (vía SSH):
cd /home/ubuntu/CSECADO/mi-sistema-etiquetas
git pull origin main

# Si hubo cambios en el backend:
cd backend
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart etiquetas-backend

# Si hubo cambios en el frontend:
cd ..
npm install
npm run build
sudo systemctl reload nginx
```

¡Listo! El sistema estará actualizado y corriendo con alta disponibilidad.
