import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
import json
import os
import pandas as pd
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape, inch
from reportlab.lib.units import inch as reportlab_inch, cm
import qrcode
from qrcode import constants

# --- Nuevas importaciones para el ajuste de texto en PDF ---
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import black
import tempfile # Para manejar archivos temporales de forma segura

# --- Constantes Globales ---
DATA_FILE = 'data.json'
# --- IMPORTANTE: La ruta del logo ahora es relativa para que funcione el instalador ---
# Asegúrate de que "logo.png" esté en la misma carpeta que el script.
LOGO_PATH = "logo.png"

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

    def generar_etiquetas_desde_cola(self, part_data, print_queue, ruta_archivo, status_callback):
        """Genera un PDF a partir de una cola, con 4 etiquetas por página, en formato horizontal."""
        try:
            c = canvas.Canvas(ruta_archivo, pagesize=landscape(letter))
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
            total_labels_generated = 0

            for item in print_queue:
                part_number = item['part_number']
                num_labels_for_part = item['quantity']
                turno = item['turno']
                part_info = part_data.get(part_number)
                if not part_info:
                    print(f"Omitiendo parte no encontrada en datos: {part_number}")
                    continue
                
                qty_on_label = part_info.get('qtu', '0')

                for _ in range(num_labels_for_part):
                    if label_count_on_page >= 4:
                        c.showPage()
                        label_count_on_page = 0
                    
                    x_offset, y_offset = positions[label_count_on_page]
                    
                    c.saveState()
                    c.translate(x_offset, y_offset)
                    c.scale(scale_x, scale_y)
                    self._draw_single_label(c, part_info, part_number, qty_on_label, turno)
                    c.restoreState()
                    
                    label_count_on_page += 1
                    total_labels_generated += 1

            if total_labels_generated > 0:
                c.save()
                messagebox.showinfo("Éxito", f"{total_labels_generated} etiqueta(s) generada(s) en '{ruta_archivo}'")
                status_callback(f"PDF generado con éxito en '{os.path.basename(ruta_archivo)}'")
            else:
                messagebox.showwarning("Advertencia", "No se generaron etiquetas. La cola podría estar vacía o las partes no fueron encontradas.")
                status_callback("No se generaron etiquetas.")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error al generar el PDF:\n{e}")
            status_callback(f"Error al generar PDF.")


    def _generar_qr_code(self, canvas, data, x, y, size):
        qr = qrcode.QRCode(version=1, error_correction=constants.ERROR_CORRECT_M, box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            img_path = temp_file.name
            img.save(img_path)
        
        try:
            canvas.drawImage(img_path, x, y, width=size, height=size, mask='auto')
        finally:
            os.remove(img_path)

class PartApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Gestión de Partes")
        
        try:
            self.logo_image = Image.open(LOGO_PATH)
            self.logo = ImageTk.PhotoImage(self.logo_image)
            self.root.iconphoto(True, self.logo)
        except Exception:
            self.logo = None

        self.part_data = self.load_data()
        self.generador_etiquetas = GeneradorEtiquetas()
        self.print_queue = []

        style = ttk.Style()
        style.configure("TButton", padding=6, relief="flat", font=("Arial", 10))
        style.configure("MainMenu.TButton", font=("Arial", 12, "bold"), padding=10)
        style.configure("TLabelFrame", padding=10)
        style.configure("TLabel", padding=5)

        main_frame = tk.Frame(root, padx=20, pady=20)
        main_frame.pack(expand=True, fill="both")

        ttk.Button(main_frame, text="⚙️ Gestionar Número de Parte", command=self.open_manage_parts_window, style="MainMenu.TButton").pack(pady=10, fill="x", ipady=5)
        ttk.Button(main_frame, text="🖨️ Cola de Impresión de Etiquetas", command=self.open_print_queue_window, style="MainMenu.TButton").pack(pady=10, fill="x", ipady=5)
        
        # --- NUEVO: Barra de estado principal ---
        self.status_bar = ttk.Label(root, text="Sistema listo.", relief=tk.SUNKEN, anchor=tk.W, padding=5)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.active_status_bar = self.status_bar

    def update_status(self, message):
        """Actualiza el texto de la barra de estado activa."""
        if self.active_status_bar and self.active_status_bar.winfo_exists():
            self.active_status_bar.config(text=message)
        else: # Si la ventana activa fue cerrada, usa la principal
            self.status_bar.config(text=message)


    def open_manage_parts_window(self):
        manage_window = tk.Toplevel(self.root)
        manage_window.title("Gestionar Números de Parte")
        if self.logo: manage_window.iconphoto(True, self.logo) 

        # --- NUEVO: Asignar barra de estado activa ---
        original_status_bar = self.active_status_bar
        manage_status_bar = ttk.Label(manage_window, text="Listo.", relief=tk.SUNKEN, anchor=tk.W, padding=5)
        self.active_status_bar = manage_status_bar
        manage_window.protocol("WM_DELETE_WINDOW", lambda: self._on_window_close(manage_window, original_status_bar))


        manage_frame = ttk.LabelFrame(manage_window, text="Datos del Número de Parte")
        manage_frame.pack(padx=10, pady=10, fill="x")

        labels_map = {"N° Parte:": "n_parte", "Descripción:": "descripcion", "Línea:": "linea", "ID:": "id", "Qty:": "qty", "Cliente (LG):": "linea_lg", "Ayuda Visual (link):": "ayuda_visual_link"}
        self.entries = {}
        for i, (label_text, key) in enumerate(labels_map.items()):
            ttk.Label(manage_frame, text=label_text).grid(row=i, column=0, padx=5, pady=5, sticky="w")
            entry = ttk.Entry(manage_frame, width=50)
            entry.grid(row=i, column=1, padx=5, pady=5, sticky="ew")
            self.entries[key] = entry
        
        button_frame = ttk.Frame(manage_frame)
        button_frame.grid(row=len(labels_map), column=0, columnspan=2, pady=10)
        
        # --- MODIFICADO: Guardar referencia a los botones para poder activarlos/desactivarlos ---
        self.add_button = ttk.Button(button_frame, text="➕ Agregar", command=self.add_part)
        self.add_button.pack(side=tk.LEFT, padx=5)
        self.edit_button = ttk.Button(button_frame, text="✏️ Editar", command=self.edit_part, state=tk.DISABLED)
        self.edit_button.pack(side=tk.LEFT, padx=5)
        self.delete_button = ttk.Button(button_frame, text="🗑️ Borrar", command=self.delete_part, state=tk.DISABLED)
        self.delete_button.pack(side=tk.LEFT, padx=5)
        self.add_to_queue_button = ttk.Button(button_frame, text="➡️ Añadir a la Cola", command=self.add_to_print_queue_from_manager, state=tk.DISABLED)
        self.add_to_queue_button.pack(side=tk.LEFT, padx=10)

        list_frame = ttk.LabelFrame(manage_window, text="Listado de Partes")
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)
        search_frame = ttk.Frame(list_frame)
        search_frame.pack(pady=5, fill="x")
        ttk.Label(search_frame, text="Buscar:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side=tk.LEFT, fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self.search_parts)
        listbox_frame = ttk.Frame(list_frame)
        listbox_frame.pack(pady=5, fill="both", expand=True)
        self.part_listbox = tk.Listbox(listbox_frame, width=60, height=10)
        scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=self.part_listbox.yview)
        self.part_listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.part_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        self.part_listbox.bind('<<ListboxSelect>>', self.on_part_select)
        # --- NUEVO: Atajo de doble clic ---
        self.part_listbox.bind('<Double-1>', self.add_to_queue_on_double_click)


        import_export_frame = ttk.Frame(manage_window)
        import_export_frame.pack(pady=10)
        ttk.Button(import_export_frame, text="📥 Importar desde Excel", command=self.import_parts_from_excel).pack(side=tk.LEFT, padx=5)
        ttk.Button(import_export_frame, text="📤 Exportar a Excel", command=self.export_to_excel).pack(side=tk.LEFT, padx=5)
        
        # --- NUEVO: Empaquetar barra de estado al final ---
        manage_status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.update_part_listbox()
        self.update_status(f"{len(self.part_data)} partes cargadas.")

    def _on_window_close(self, window, previous_status_bar):
        """Restaura la barra de estado anterior cuando una ventana se cierra."""
        self.active_status_bar = previous_status_bar
        self.update_status("Sistema listo.")
        window.destroy()

    def open_print_queue_window(self):
        self.queue_window = tk.Toplevel(self.root)
        self.queue_window.title("Cola de Impresión")
        if self.logo: self.queue_window.iconphoto(True, self.logo)

        # --- NUEVO: Asignar barra de estado activa ---
        original_status_bar = self.active_status_bar
        queue_status_bar = ttk.Label(self.queue_window, text="Listo.", relief=tk.SUNKEN, anchor=tk.W, padding=5)
        self.active_status_bar = queue_status_bar
        self.queue_window.protocol("WM_DELETE_WINDOW", lambda: self._on_window_close(self.queue_window, original_status_bar))

        add_frame = ttk.LabelFrame(self.queue_window, text="Añadir Parte a la Cola")
        add_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(add_frame, text="Buscar Parte:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.queue_search_var = tk.StringVar()
        self.queue_search_entry = ttk.Entry(add_frame, textvariable=self.queue_search_var, width=20)
        self.queue_search_entry.grid(row=0, column=1, padx=5, pady=5)
        self.queue_search_var.trace_add("write", self.filter_parts_for_queue_combobox)

        ttk.Label(add_frame, text="Seleccionar N° Parte:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.queue_part_combobox = ttk.Combobox(add_frame, state="readonly", width=35)
        self.queue_part_combobox.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        self.filter_parts_for_queue_combobox()

        ttk.Label(add_frame, text="Cantidad de Etiquetas:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.queue_qty_var = tk.StringVar(value="1")
        self.queue_qty_entry = ttk.Entry(add_frame, textvariable=self.queue_qty_var, width=10)
        self.queue_qty_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(add_frame, text="Turno:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.queue_turno_var = tk.StringVar()
        self.queue_turno_combobox = ttk.Combobox(add_frame, textvariable=self.queue_turno_var, values=["Día", "Noche"], state="readonly", width=8)
        self.queue_turno_combobox.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        self.queue_turno_combobox.set("Día")

        ttk.Button(add_frame, text="➡️ Añadir a la Cola", command=self.add_to_print_queue_from_queue_window).grid(row=4, column=0, columnspan=2, pady=10)

        queue_list_frame = ttk.LabelFrame(self.queue_window, text="Etiquetas en Cola")
        queue_list_frame.pack(padx=10, pady=10, fill="both", expand=True)

        cols = ("part_number", "quantity", "turno")
        self.queue_tree = ttk.Treeview(queue_list_frame, columns=cols, show="headings")
        self.queue_tree.heading("part_number", text="Número de Parte")
        self.queue_tree.heading("quantity", text="Cantidad de Etiquetas")
        self.queue_tree.heading("turno", text="Turno")
        self.queue_tree.pack(fill="both", expand=True)
        self.update_queue_treeview()

        action_button_frame = ttk.Frame(self.queue_window)
        action_button_frame.pack(pady=10)
        ttk.Button(action_button_frame, text="📄 Generar PDF", command=self.generate_pdf_from_queue).pack(side=tk.LEFT, padx=10)
        ttk.Button(action_button_frame, text="🧹 Limpiar Cola", command=self.clear_print_queue).pack(side=tk.LEFT, padx=10)

        queue_status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.update_status(f"{len(self.print_queue)} item(s) en la cola.")

    def filter_parts_for_queue_combobox(self, *args):
        search_term = self.queue_search_var.get().upper()
        if not search_term:
            filtered_parts = sorted(self.part_data.keys())
        else:
            filtered_parts = sorted([p for p in self.part_data if search_term in p])
        self.queue_part_combobox['values'] = filtered_parts
        if filtered_parts:
            self.queue_part_combobox.set(filtered_parts[0])
        else:
            self.queue_part_combobox.set('')

    def update_queue_treeview(self):
        if hasattr(self, 'queue_tree') and self.queue_tree.winfo_exists():
            for i in self.queue_tree.get_children():
                self.queue_tree.delete(i)
            for item in self.print_queue:
                self.queue_tree.insert("", "end", values=(item['part_number'], item['quantity'], item['turno']))
            self.update_status(f"{len(self.print_queue)} item(s) en la cola.")

    
    def clear_print_queue(self):
        if messagebox.askyesno("Confirmar", "¿Está seguro de que desea limpiar toda la cola de impresión?"):
            self.print_queue.clear()
            self.update_queue_treeview()
            messagebox.showinfo("Cola Limpia", "La cola de impresión ha sido vaciada.")
            self.update_status("Cola de impresión vaciada.")

    def _ask_turno_dialog(self, parent):
        dialog = tk.Toplevel(parent)
        dialog.title("Seleccionar Turno")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.resizable(False, False)

        result = tk.StringVar()

        ttk.Label(dialog, text="Por favor, selecciona el turno:").pack(padx=20, pady=10)
        
        combo = ttk.Combobox(dialog, values=["Día", "Noche"], state="readonly")
        combo.pack(padx=20, pady=5)
        combo.set("Día")

        def on_ok():
            result.set(combo.get())
            dialog.destroy()

        def on_cancel():
            result.set("")
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(padx=20, pady=(10, 15))
        ttk.Button(button_frame, text="Aceptar", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancelar", command=on_cancel).pack(side=tk.LEFT, padx=5)
        
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_reqwidth()) / 2
        y = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_reqheight()) / 2
        dialog.geometry(f"+{int(x)}+{int(y)}")

        dialog.wait_window(dialog)
        return result.get()

    def add_to_queue_on_double_click(self, event):
        """Manejador para el evento de doble clic en la lista de partes."""
        self.add_to_print_queue_from_manager()

    def add_to_print_queue_from_manager(self):
        selected_indices = self.part_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Advertencia", "Selecciona un número de parte de la lista para añadir a la cola.", parent=self.root)
            return
        part_number = self.part_listbox.get(selected_indices)
        
        quantity = simpledialog.askinteger("Cantidad de Etiquetas", f"¿Cuántas etiquetas para '{part_number}' deseas añadir a la cola?", parent=self.root, minvalue=1, initialvalue=1)
        if quantity:
            turno = self._ask_turno_dialog(self.root)
            if turno:
                self._add_item_to_queue(part_number, quantity, turno)

    def add_to_print_queue_from_queue_window(self):
        part_number = self.queue_part_combobox.get()
        if not part_number:
            messagebox.showwarning("Selección Requerida", "Por favor, selecciona un número de parte.", parent=self.queue_window)
            return
        
        turno = self.queue_turno_var.get()
        if not turno:
            messagebox.showwarning("Campo Requerido", "Por favor, selecciona un turno.", parent=self.queue_window)
            return
            
        try:
            quantity = int(self.queue_qty_var.get())
            if quantity < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Entrada Inválida", "La cantidad debe ser un número entero positivo.", parent=self.queue_window)
            return
        self._add_item_to_queue(part_number, quantity, turno)
        
        # --- NUEVO: Limpieza automática de campos ---
        self.queue_qty_var.set("1")
        self.queue_turno_combobox.set("Día")
        self.queue_search_entry.focus_set()


    def _add_item_to_queue(self, part_number, quantity, turno):
        self.print_queue.append({'part_number': part_number, 'quantity': quantity, 'turno': turno})
        messagebox.showinfo("Éxito", f"Se añadieron {quantity} etiquetas de '{part_number}' (Turno: {turno}) a la cola.", parent=self.root)
        if hasattr(self, 'queue_window') and self.queue_window.winfo_exists():
            self.update_queue_treeview()

    def add_part(self):
        part_number = self.entries['n_parte'].get().strip().upper()
        if not part_number:
            messagebox.showwarning("Advertencia", "El campo 'N° Parte' es obligatorio.", parent=self.root)
            return
        if part_number in self.part_data:
            messagebox.showerror("Error", f"El N° de Parte '{part_number}' ya existe.", parent=self.root)
            return
        self._update_part_data(part_number)
        messagebox.showinfo("Éxito", f"N° Parte '{part_number}' agregado.", parent=self.root)
        self.clear_part_fields()
        self.update_status(f"Parte '{part_number}' agregada.")


    def edit_part(self):
        selected_indices = self.part_listbox.curselection()
        if not selected_indices:
            return
        original_part_number = self.part_listbox.get(selected_indices)
        new_part_number = self.entries['n_parte'].get().strip().upper()
        if original_part_number != new_part_number:
            if new_part_number in self.part_data:
                messagebox.showerror("Error", f"El nuevo N° de Parte '{new_part_number}' ya existe.", parent=self.root)
                return
            del self.part_data[original_part_number]
        self._update_part_data(new_part_number)
        messagebox.showinfo("Éxito", f"N° Parte '{new_part_number}' actualizado.", parent=self.root)
        self.clear_part_fields()
        self.update_status(f"Parte '{new_part_number}' actualizada.")


    def _update_part_data(self, part_number):
        self.part_data[part_number] = {
            'descripcion': self.entries['descripcion'].get().strip(),
            'linea': self.entries['linea'].get().strip(),
            'id': self.entries['id'].get().strip(),
            'qtu': self.entries['qty'].get().strip(),
            'linea_lg': self.entries['linea_lg'].get().strip(),
            'ayuda_visual': self.entries['ayuda_visual_link'].get().strip()
        }
        self.save_data()
        self.update_part_listbox()

    def delete_part(self):
        selected_indices = self.part_listbox.curselection()
        if not selected_indices:
            return
        part_number = self.part_listbox.get(selected_indices)
        if messagebox.askyesno("Confirmar", f"¿Estás seguro de que deseas borrar el N° Parte '{part_number}'?", parent=self.root):
            del self.part_data[part_number]
            self.save_data()
            self.update_part_listbox()
            messagebox.showinfo("Éxito", f"N° Parte '{part_number}' borrado.", parent=self.root)
            self.clear_part_fields()
            self.update_status(f"Parte '{part_number}' borrada.")


    def search_parts(self, event=None):
        search_term = self.search_entry.get().strip().upper()
        self.part_listbox.delete(0, tk.END)
        count = 0
        for part_number in sorted(self.part_data.keys()):
            if search_term in part_number or search_term in self.part_data[part_number].get('descripcion', '').upper():
                self.part_listbox.insert(tk.END, part_number)
                count += 1
        self.update_status(f"{count} parte(s) encontrada(s).")


    def on_part_select(self, event=None):
        """Activa los botones y carga los datos de la parte seleccionada."""
        if not self.part_listbox.curselection():
            self._set_manage_buttons_state(tk.DISABLED)
            return
        
        self._set_manage_buttons_state(tk.NORMAL)
        self.load_selected_part_data()

    def load_selected_part_data(self):
        """Carga los datos del item seleccionado en los campos de entrada."""
        selected_indices = self.part_listbox.curselection()
        if not selected_indices: return

        part_number = self.part_listbox.get(selected_indices)
        part_info = self.part_data.get(part_number, {})
        
        entry_map = {
            'n_parte': part_number, 
            'descripcion': part_info.get('descripcion', ''), 
            'linea': part_info.get('linea', ''), 
            'id': part_info.get('id', ''), 
            'qty': part_info.get('qtu', ''), 
            'linea_lg': part_info.get('linea_lg', ''), 
            'ayuda_visual_link': part_info.get('ayuda_visual', '')
        }
        for key, value in entry_map.items():
            self.entries[key].delete(0, tk.END)
            self.entries[key].insert(0, value)
        self.update_status(f"Mostrando datos para: {part_number}")

    def _set_manage_buttons_state(self, state):
        """Establece el estado de los botones de gestión."""
        if hasattr(self, 'edit_button'):
            self.edit_button.config(state=state)
            self.delete_button.config(state=state)
            self.add_to_queue_button.config(state=state)

    def update_part_listbox(self):
        if hasattr(self, 'part_listbox') and self.part_listbox.winfo_exists():
            current_selection_indices = self.part_listbox.curselection()
            self.search_parts()
            if current_selection_indices:
                try: self.part_listbox.selection_set(current_selection_indices)
                except tk.TclError: pass

    def clear_part_fields(self):
        for entry in self.entries.values(): entry.delete(0, tk.END)
        if hasattr(self, 'part_listbox'): self.part_listbox.selection_clear(0, tk.END)
        self._set_manage_buttons_state(tk.DISABLED)
        self.update_status("Listo.")


    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as file: return json.load(file)
            except (json.JSONDecodeError, FileNotFoundError):
                messagebox.showerror("Error de Datos", f"No se pudo leer o decodificar el archivo {DATA_FILE}. Se creará uno nuevo.")
                return {} 
        return {}

    def save_data(self):
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as file: json.dump(self.part_data, file, indent=4, ensure_ascii=False)
            self.update_status("Datos guardados correctamente.")
        except IOError as e: 
            messagebox.showerror("Error al Guardar", f"No se pudo guardar el archivo de datos:\n{e}")
            self.update_status("Error al guardar datos.")

    def export_to_excel(self):
        if not self.part_data:
            messagebox.showinfo("Sin datos", "No hay datos para exportar.", parent=self.root)
            return
        df = pd.DataFrame.from_dict(self.part_data, orient='index')
        df.reset_index(inplace=True)
        df.rename(columns={'index': 'Número de Parte', 'descripcion': 'Descripción', 'linea': 'Línea', 'id': 'ID', 'qtu': 'Cantidad', 'linea_lg': 'Cliente (LG)', 'ayuda_visual': 'Ayuda Visual'}, inplace=True)
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if not file_path: return
        try:
            df.to_excel(file_path, index=False)
            messagebox.showinfo("Éxito", f"Datos exportados a '{file_path}' exitosamente.", parent=self.root)
            self.update_status(f"Datos exportados a '{os.path.basename(file_path)}'")
        except Exception as e: 
            messagebox.showerror("Error", f"No se pudo exportar los datos a Excel:\n{e}", parent=self.root)
            self.update_status("Error al exportar a Excel.")

    def generate_pdf_from_queue(self):
        if not self.print_queue:
            messagebox.showwarning("Cola Vacía", "No hay etiquetas en la cola de impresión.", parent=self.queue_window)
            return
        
        ruta_archivo = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"lote_etiquetas.pdf", filetypes=[("PDF Files", "*.pdf")])
        if not ruta_archivo: return
        
        self.update_status("Generando PDF... por favor espere.")
        # Usamos lambda para poder pasar el argumento a la función de callback
        self.generador_etiquetas.generar_etiquetas_desde_cola(self.part_data, self.print_queue, ruta_archivo, lambda msg: self.update_status(msg))


    def import_parts_from_excel(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx; *.xls")])
        if not file_path: return
        try:
            df = pd.read_excel(file_path, dtype=str)
            df.fillna('', inplace=True)
            column_map = {'Número de Parte': 'part_number', 'Descripción': 'descripcion', 'Línea': 'linea', 'ID': 'id', 'Cantidad': 'qtu', 'Cliente (LG)': 'linea_lg', 'Ayuda Visual': 'ayuda_visual'}
            df.rename(columns={k: v for k, v in column_map.items() if k in df.columns}, inplace=True)
            if 'part_number' not in df.columns:
                messagebox.showerror("Error de Formato", "El archivo de Excel debe contener una columna llamada 'Número de Parte'.", parent=self.root)
                return
            imported_count = 0
            for index, row in df.iterrows():
                part_number = str(row.get('part_number', '')).strip().upper()
                if not part_number: continue
                self.part_data[part_number] = {
                    'descripcion': str(row.get('descripcion', '')).strip(), 
                    'linea': str(row.get('linea', '')).strip(), 
                    'id': str(row.get('id', '')).strip(), 
                    'qtu': str(row.get('qtu', '')).strip(), 
                    'linea_lg': str(row.get('linea_lg', '')).strip(), 
                    'ayuda_visual': str(row.get('ayuda_visual', '')).strip()
                }
                imported_count += 1
            self.save_data()
            self.update_part_listbox()
            messagebox.showinfo("Éxito", f"{imported_count} números de parte importados/actualizados exitosamente.", parent=self.root)
            self.update_status(f"{imported_count} partes importadas desde '{os.path.basename(file_path)}'")
        except Exception as e: 
            messagebox.showerror("Error", f"No se pudo importar los datos: {e}", parent=self.root)
            self.update_status("Error al importar desde Excel.")

if __name__ == "__main__":
    root = tk.Tk()
    app = PartApp(root)
    root.mainloop()
