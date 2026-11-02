# 🔌 Especificación de la API REST

Documentación completa de los endpoints del backend implementado con **FastAPI**.

- **URL Base Local:** `http://localhost:8000`
- **Prefijo en Desarrollo con Vite:** `/api` (redireccionado por proxy a `http://127.0.0.1:8000`)
- **Documentación Interactiva Swagger:** `http://localhost:8000/docs`
- **Documentación ReDoc:** `http://localhost:8000/redoc`

---

## 📑 Índice de Endpoints

1. [Módulo de Partes](#1-módulo-de-partes)
   - `GET /parts`
   - `POST /parts/{part_number}`
   - `PUT /parts/{old_part_number}`
   - `DELETE /parts/{part_number}`
   - `POST /parts/import`
2. [Módulo de Cola de Impresión](#2-módulo-de-cola-de-impresión)
   - `GET /print-queue/state`
   - `POST /print-queue/state`
   - `POST /print-queue/generate-pdf`
3. [Módulo de Cuarto de Secado](#3-módulo-de-cuarto-de-secado)
   - `GET /drying-room/state`
   - `POST /drying-room/state`
   - `POST /drying-room/scan`
4. [Módulo de Telegram Queue](#4-módulo-de-cola-de-telegram)
   - `GET /telegram-queue`
   - `POST /telegram-queue/clear`

---

## 1. Módulo de Partes

### `GET /parts`
Devuelve el diccionario completo de partes registradas.

- **Respuesta Exitosa (200 OK):**
```json
{
  "MCZ60014601": {
    "descripcion": "COVER ASSEMBLY FRONT",
    "linea": "LINEA 1",
    "id": "104",
    "qtu": "120",
    "linea_lg": "LG-WASH",
    "ayuda_visual": "https://servidor/ayudas/MCZ60014601.jpg"
  }
}
```

---

### `POST /parts/{part_number}`
Crea un nuevo número de parte.

- **Parámetros de Ruta:** `part_number` (string)
- **Cuerpo de la Petición (JSON):**
```json
{
  "descripcion": "BARRIER INSULATOR C",
  "linea": "LINEA 2",
  "id": "205",
  "qtu": "80",
  "linea_lg": "LG-REF",
  "ayuda_visual": ""
}
```
- **Respuestas:**
  - `200 OK`: `{"message": "Parte agregada exitosamente", "part": "MAL62524101"}`
  - `400 Bad Request`: `{"detail": "El número de parte 'MAL62524101' ya existe."}`

---

### `PUT /parts/{old_part_number}`
Actualiza una parte existente. Permite renombrar la clave del número de parte mediante el query param `new_part_number`.

- **Parámetros:**
  - `old_part_number` (Ruta, string): Número actual.
  - `new_part_number` (Query, opcional, string): Nuevo número de parte si se renombra.
- **Cuerpo de la Petición (JSON):** Modelo `PartData` con valores actualizados.
- **Respuestas:**
  - `200 OK`: `{"message": "Parte actualizada exitosamente"}`
  - `404 Not Found`: `{"detail": "Número de parte original no encontrado."}`
  - `400 Bad Request`: `{"detail": "El nuevo número de parte ya está en uso."}`

---

### `DELETE /parts/{part_number}`
Elimina una parte del catálogo.

- **Parámetros de Ruta:** `part_number` (string)
- **Respuestas:**
  - `200 OK`: `{"message": "Parte eliminada exitosamente"}`
  - `404 Not Found`: `{"detail": "Número de parte no encontrado."}`

---

### `POST /parts/import`
Importación masiva desde un archivo Excel (`.xlsx`) o CSV (`.csv`).

- **Encabezado:** `Content-Type: multipart/form-data`
- **Cuerpo:** `file` (archivo binario, límite de 5 MB).
- **Columnas Requeridas en la Hoja:**
  - `Número de Parte` *(Obligatoria)*
  - `Descripción`
  - `Línea`
  - `ID`
  - `Cantidad`
  - `Cliente (LG)`
  - `Ayuda Visual`
- **Respuestas:**
  - `200 OK`: `{"message": "¡Éxito! 45 partes importadas correctamente."}`
  - `400 Bad Request`: Archivo supera 5 MB o carece de la columna 'Número de Parte'.

---

## 2. Módulo de Cola de Impresión

### `GET /print-queue/state`
Obtiene la cola de impresión guardada en disco.

- **Respuesta (200 OK):**
```json
{
  "queue": [
    {
      "part": "MCZ60014601",
      "desc": "COVER ASSEMBLY FRONT",
      "qty": 4,
      "turno": "Día"
    }
  ]
}
```

---

### `POST /print-queue/state`
Persiste los cambios de la cola de impresión.

- **Cuerpo de la Petición (JSON):**
```json
{
  "queue": [
    {
      "part": "MCZ60014601",
      "desc": "COVER ASSEMBLY FRONT",
      "qty": 2,
      "turno": "Noche"
    }
  ]
}
```

---

### `POST /print-queue/generate-pdf`
Genera y transmite directamente el archivo binario PDF con las etiquetas renderizadas.

- **Cuerpo de la Petición (JSON):**
```json
[
  {
    "part": "MCZ60014601",
    "desc": "COVER ASSEMBLY FRONT",
    "qty": 8,
    "turno": "Día"
  }
]
```
- **Respuesta Exitosa:**
  - `Status`: `200 OK`
  - `Content-Type`: `application/pdf`
  - Stream binario del PDF generado con ReportLab.

---

## 3. Módulo de Cuarto de Secado

### `GET /drying-room/state`
Retorna el estado general, acumuladores del turno y registros.

- **Respuesta (200 OK):**
```json
{
  "records": [
    {
      "idCarrito": "C-ABC12345",
      "numeroParte": "MCZ60014601",
      "descripcion": "COVER ASSEMBLY FRONT",
      "maquina": "LINEA 1",
      "qty": 120,
      "acumulado": 120,
      "turno": "DÍA",
      "estado": "EN SECADO",
      "horaEntrada": "2026-10-13T10:15:00.000Z",
      "horaSalida": null,
      "tiempoMinutos": null,
      "earlyExit": false
    }
  ],
  "acumuladoPorParte": {
    "MCZ60014601": 120
  },
  "contadorCarritos": {
    "MCZ60014601": 1
  },
  "turnoActual": "DÍA",
  "historialTurnos": [],
  "lastUpdated": 1791928372.45
}
```

---

### `POST /drying-room/state`
Sincroniza y almacena el estado completo desde el frontend. Purga automáticamente registros finalizados con más de 30 días de antigüedad.

- **Cuerpo de la Petición:** Objeto `DryingState`.
- **Respuesta:**
```json
{
  "message": "Estado sincronizado. 32 registros activos."
}
```

---

### `POST /drying-room/scan`
Permite a terminales con cámara o integraciones registrar entradas o salidas inmediatas identificando la etiqueta única o número de parte.

- **Cuerpo de la Petición (JSON):**
```json
{
  "qr_data": "ETQ-261013-A1B2C",
  "action": "entrada"
}
```
*(Soporta `qr_data` con ID único `ETQ-...`, texto multilínea completo o número de parte. Valores para `action`: `"entrada"` o `"salida"`)*

- **Respuesta (200 OK):**
```json
{
  "message": "Entrada registrada",
  "record": {
    "idCarrito": "ETQ-261013-A1B2C",
    "numeroParte": "MCZ60014601",
    "estado": "EN SECADO",
    "qty": 120
  }
}
```

---

### `GET /labels/{label_id}`
Consulta los metadatos de una etiqueta generada por su ID único.

- **Parámetros de Ruta:** `label_id` (string, ej. `ETQ-261013-A1B2C`)
- **Respuesta (200 OK):**
```json
{
  "id": "ETQ-261013-A1B2C",
  "part_number": "MCZ60014601",
  "descripcion": "COVER ASSEMBLY FRONT",
  "qty": 120,
  "linea": "LINEA 1",
  "cliente": "LG",
  "turno": "Día",
  "fecha": "13/10/2026",
  "created_at": "2026-10-13T12:00:00.000Z"
}
```

---

## 4. Módulo de Cola de Telegram

### `GET /telegram-queue`
Permite a las terminales web consultar qué eventos han sido disparados remotamente por operadores desde Telegram.

- **Respuesta (200 OK):**
```json
{
  "actions": [
    {
      "codigo": "MCZ60014601",
      "action": "ENTRADA",
      "timestamp": "2026-10-13T12:00:00.000000"
    }
  ]
}
```

---

### `POST /telegram-queue/clear`
Limpia o actualiza los eventos procesados por el frontend.

- **Cuerpo (JSON):**
```json
{
  "actions": []
}
```
