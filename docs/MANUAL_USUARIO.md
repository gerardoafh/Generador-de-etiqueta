# 📖 Manual de Operación para Planta

Guía de usuario para operadores, líderes de línea, inspectores de calidad y supervisores de producción.

---

## 📑 Contenido del Manual

1. [Acceso al Sistema](#1-acceso-al-sistema)
2. [Módulo 1: Catálogo de Números de Parte](#2-módulo-1-catálogo-de-números-de-parte)
3. [Módulo 2: Generación e Impresión de Etiquetas](#3-módulo-2-generación-e-impresión-de-etiquetas)
4. [Módulo 3: Operación en Cuarto de Secado](#4-módulo-3-operación-en-cuarto-de-secado)
   - [Escaneo con Pistola de Código de Barras](#escaneo-con-pistola-usbbluetooth)
   - [Escaneo con Cámara Web o Celular](#escaneo-con-cámara-web-o-dispositivo-móvil)
   - [Alertas y Semáforos](#interpretación-de-alertas-y-semáforos)
5. [Módulo 4: Reportes y Auditoría](#5-módulo-4-reportes-y-auditoría)
6. [Resolución de Problemas Frecuentes](#6-resolución-de-problemas-frecuentes)

---

## 1. Acceso al Sistema

1. Abre tu navegador web (Google Chrome o Microsoft Edge recomendados).
2. Ingresa a la dirección del sistema (por ejemplo `https://localhost:5173` o la IP de red local asignada a la estación).
3. En la esquina superior del panel principal podrás verificar el estado:
   - 🟢 **Sistema en línea:** Listo para operar.
   - 🔴 **Backend sin conexión:** Notifica al personal de sistemas para verificar el servicio.

---

## 2. Módulo 1: Catálogo de Números de Parte

Este módulo permite dar de alta nuevos productos o actualizar los existentes.

### Alta o Edición Manual
1. Haz clic en **⚙️ Gestor de Partes** desde el menú principal.
2. Para editar una pieza existente, búscala en la lista de la izquierda y haz clic sobre ella. Sus datos se cargarán en el formulario.
3. Para dar de alta una nueva, escribe el **Número de Parte** y completa los campos obligatorios:
   - **Descripción:** Nombre técnico de la pieza.
   - **Línea:** Máquina asignada (ej. `LINEA 1`, `MÁQ 9`).
   - **Cantidad por Etiqueta (QTU):** Número de piezas físicas contenidas en cada carrito o contenedor.
   - **Cliente:** Código de cliente (ej. `LG`).
4. Presiona **Guardar Parte**.

### Importación Masiva desde Excel
1. Prepara tu archivo `.xlsx` o `.csv` asegurándote de que la primera fila contenga exactamente la columna `Número de Parte`.
2. Presiona el botón verde **📥 Importar Excel / CSV**.
3. Selecciona tu archivo. El sistema validará los datos y confirmará la cantidad de registros importados exitosamente.

---

## 3. Módulo 2: Generación e Impresión de Etiquetas

1. Ingresa a **🖨️ Cola de Impresión**.
2. Selecciona el **Número de Parte** deseado en la lista desplegable.
3. Ingresa la **Cantidad de Etiquetas** a imprimir.
4. Selecciona el **Turno** correspondiente (**Día** o **Noche**).
5. Haz clic en **➕ Agregar a la Cola**.
6. Repite los pasos anteriores para agregar diferentes modelos a la misma tanda de impresión.
7. Una vez completada la lista, haz clic en **🖨️ Generar e Imprimir PDF**:
   - Se abrirá una nueva pestaña con el documento PDF listo para imprimir.
   - Cada página contiene 4 etiquetas de 6×5 pulgadas con dos códigos QR legibles.

---

## 4. Módulo 3: Operación en Cuarto de Secado

El cuarto de secado opera bajo la metodología **FIFO** (*First-In, First-Out*): el primer carrito en ingresar debe ser el primero en salir.

### Escaneo con Pistola USB/Bluetooth
1. Colócate en la pantalla de **♨️ Cuarto de Secado**.
2. Selecciona el modo de operación presionando el botón:
   - 🟢 **MODO: ENTRADA** (para ingresar carritos recién fabricados).
   - 🔴 **MODO: SALIDA** (para dar salida a carritos secos).
3. Apunta la pistola al código QR o de barras de la etiqueta y dispara:
   - El sistema detectará la lectura, validará que la etiqueta sea del día y emitirá un sonido/notificación confirmando el registro.

### Escaneo con Cámara Web o Dispositivo Móvil
1. Presiona el botón **📷 Escanear con Cámara**.
2. Si el navegador solicita permisos para usar la cámara, selecciona **Permitir**.
3. Apunta la cámara trasera hacia el código QR de la etiqueta:
   - Al detectar el código, la ventana se cerrará automáticamente y registrará la entrada o salida según el modo activo.

### Interpretación de Alertas y Semáforos
- 🔴 **Etiqueta VENCIDA:** El carrito ha permanecido más minutos de los configurados en el campo *Tiempo Máximo (min)*. El operador debe priorizar su retiro.
- 🟡 **Alerta de Salida Anticipada:** El sistema detectó que el carrito está saliendo al menos 10 minutos antes del promedio habitual de esa parte. Se mostrará una advertencia toast amarilla para que el inspector verifique que la pieza esté efectivamente seca.
- ⚠️ **REZAGO:** El carrito ingresó en un turno anterior y aún no ha sido retirado.

---

## 5. Módulo 4: Reportes y Auditoría

1. Ingresa a **📊 Reporte de Producción**.
2. Utiliza los filtros en la cabecera:
   - **Fecha:** Selecciona el día a consultar (por defecto muestra el día actual).
   - **Turno:** Filtra por **DÍA**, **NOCHE** o **TODOS**.
3. Observa las tarjetas KPI con el total de piezas y lotes completados.
4. Para respaldar la información o enviarla por correo, presiona **📥 Exportar a CSV**. Se descargará un archivo compatible con Microsoft Excel.

---

## 6. Resolución de Problemas Frecuentes

| Síntoma | Causa Probable | Solución |
|---|---|---|
| *Etiqueta rechazada por fecha* | Se intentó ingresar una etiqueta generada en días previos. | Verifique que la pieza corresponda a la producción de hoy o genere una etiqueta nueva. |
| *La cámara web no abre o muestra error* | El navegador bloqueó el permiso o la conexión no es HTTPS. | Asegúrese de acceder mediante `https://` y otorgar permiso de cámara en el candado de la barra de direcciones. |
| *La pistola escribe caracteres raros (ej. Ñ en vez de :)* | La pistola tiene mapeo de teclado en inglés y la PC en español. | El sistema corrige automáticamente este problema. Si persiste, verifique la configuración de idioma del lector. |
| *El bot de Telegram no responde* | Falta conexión a internet o el token en `.env` está inactivo. | Verifique que el servidor tenga acceso a internet y que el backend esté ejecutando el hilo del bot. |
