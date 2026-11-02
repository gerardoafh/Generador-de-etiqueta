# 🤖 Bot de Telegram y Visión Artificial

El bot de Telegram ([backend/telegram_bot.py](file:///d:/p/CSECADO/mi-sistema-etiquetas/backend/telegram_bot.py)) es un asistente inteligente diseñado para que los supervisores y operadores de piso registren entradas y salidas de carritos, consulten el estado del cuarto de secado y reciban reportes directamente en sus dispositivos móviles.

---

## ⚙️ Configuración y Puesta en Marcha

### 1. Variables de Entorno (`.env`)
En el archivo [backend/.env](file:///d:/p/CSECADO/mi-sistema-etiquetas/backend/.env):
```env
TELEGRAM_BOT_TOKEN="123456789:ABCDEF_tu_token_aqui"
TELEGRAM_CHAT_ID="7629357744, -1004412654974"
```
- `TELEGRAM_BOT_TOKEN`: Token obtenido de [@BotFather](https://t.me/BotFather).
- `TELEGRAM_CHAT_ID`: Lista de Chat IDs numéricos (de usuarios o grupos) separados por comas que recibirán los reportes automáticos.

### 2. Dependencias de Sistema para Visión
- **Linux / Ubuntu:**
  ```bash
  sudo apt install -y libzbar0 libgl1 tesseract-ocr
  ```
- **Windows:**
  - Instalar Tesseract en `C:\Program Files\Tesseract-OCR\tesseract.exe`.
  - El bot detecta automáticamente la ruta de Windows o Linux.

---

## 👁️ Pipeline de Visión Artificial para Lectura de Etiquetas

Cuando un operador envía una fotografía de una etiqueta al bot, se ejecuta un algoritmo de cascada en múltiples fases:

```
[ Fotografía Recibida ]
        │
        ▼
Fase 1: PyZbar sobre Imagen Original
        │── ¿Se leyó el QR? ──► SÍ ──► Extraer Número de Parte
        ▼ (NO)
Fase 2: Preprocesamiento OpenCV
        • Conversión a escala de grises
        • Ecualización de histograma (cv2.equalizeHist)
        • Reintento con PyZbar
        │── ¿Se leyó el QR? ──► SÍ ──► Extraer Número de Parte
        ▼ (NO)
Fase 3: Detector Nativo de OpenCV (cv2.QRCodeDetector)
        │── ¿Se leyó el QR? ──► SÍ ──► Extraer Número de Parte
        ▼ (NO)
Fase 4: OCR Tesseract + Normalización
        • Filtro Gaussiano de reducción de ruido
        • Umbralización adaptativa (adaptiveThreshold)
        • Escalamiento bicúbico (2x)
        • Extracción de texto con --psm 6
        • Extracción por Regex de "Part Number" y "Qty"
        ▼
Fase 5: Corrección de Caracteres y Búsqueda Difusa (Fuzzy Match)
        • Reglas regex de sustitución de confusiones OCR:
          - O ➔ 0 (cuando está junto a números)
          - l / I ➔ 1
          - S ➔ 5
          - B ➔ 8
          - 2Z / Z2 ➔ Z (corrección de prefijos comunes)
        • Comparación con difflib contra el catálogo data.json (umbral 82% similitud)
```

---

## 🆔 Trazabilidad por Identificación Única de Etiqueta (ETQ-XXXXX)

Cada etiqueta generada en el sistema cuenta con un identificador único (ej. `ETQ-261013-A1B2C`) impreso en texto legible y codificado en ambos códigos QR.

### Flujo de Escaneo en Telegram:
1. **ENTRADA de Carrito:**
   - Al escanear la foto de la etiqueta con caption `entrada`, el bot extrae el ID único (`ETQ-...`).
   - El sistema comprueba si esa etiqueta específica ya se encuentra `EN SECADO`.
     - Si ya está adentro: responde con advertencia preventiva (*"⚠️ La etiqueta ETQ-... ya está registrada EN SECADO desde las HH:MM"*).
     - Si no: guarda el carrito con `idCarrito = ETQ-...`.
2. **SALIDA de Carrito:**
   - Al escanear la etiqueta con caption `salida`, el bot busca **exactamente** el carrito con ese ID único.
   - Si se encuentra activo: finaliza su secado, registra la hora de salida y calcula sus minutos exactos.
   - Si ya había finalizado: avisa que esa etiqueta ya había salido previamente para evitar dobles salidas.
   - Si no se encuentra: notifica que no existe ningún carrito con ese ID en secado.

---

## 💬 Guía de Comandos del Bot

### A. Registro por Fotografía
1. **Foto con texto:**
   - Envía la foto de la etiqueta agregando como comentario (caption): `entrada` o `salida`.
   - El bot lee el QR (o aplica OCR), identifica el ID único de la etiqueta y el número de parte, ejecuta la acción e informa el ID confirmado.
2. **Foto sin texto:**
   - Si envías solo la imagen, el bot procesará la etiqueta y te preguntará:
     > *📷 Etiqueta leída correctamente:*  
     > *🆔 ID Etiqueta: `ETQ-261013-A1B2C`*  
     > *🏷 Parte: `MCZ60014601`*  
     > *¿Qué deseas hacer? 👉 Escribe entrada o salida*
   - Al responder con una de esas dos palabras, se completa la operación con ese ID.

### B. Registro Manual por Texto
- `entrada ETQ-261013-A1B2C` — Entrada manual mediante el ID único de la etiqueta.
- `salida ETQ-261013-A1B2C` — Salida manual del carrito exacto con ese ID.
- `entrada MCZ60014601` — Registro manual por número de parte (genera un ID aleatorio).
- `salida MCZ60014601` — Salida manual por número de parte (FIFO, cierra el más antiguo de esa parte).

### C. Consultas Rápidas en Tiempo Real
| Mensaje del Usuario | Respuesta del Bot |
|---|---|
| `cuarto de secado` | Lista todos los carritos que se encuentran actualmente en estado `EN SECADO`, indicando número de parte, ID único, descripción, cantidad y hora de ingreso. |
| `piezas de MCZ60014601` | Muestra el total de piezas y número de lotes registrados para esa parte durante el **turno actual**. |
| `reporte de producción` | Genera de forma inmediata el reporte del turno en curso y adjunta el archivo **Excel (.xlsx)** con la tabla detallada. |
| `ayuda` o cualquier otro texto | Despliega el menú de instrucciones y comandos disponibles. |

---

## 🔒 Validaciones y Reglas de Calidad

1. **Validación de Fecha en el QR:**
   - En peticiones de **ENTRADA**, el bot verifica que la fecha impresa en el código QR corresponda al día de **hoy** (o **ayer** si nos encontramos en el turno noche cruzando medianoche).
   - Etiquetas con fechas anteriores son rechazadas automáticamente.
2. **Cierre de Ciclo de Secado Exacto:**
   - Al escanear una etiqueta por salida, se cierra la instancia exacta de ese carrito mediante su `idCarrito`, eliminando discrepancias o errores donde carritos de la misma parte se cierren fuera de orden.
