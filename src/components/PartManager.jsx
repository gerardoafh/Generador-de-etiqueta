import React, { useState, useEffect, useRef } from 'react';
import { apiFetch } from '../api';
import { useToast } from '../hooks/useToast.jsx';
import { useConfirm } from '../hooks/useConfirm.jsx';

export default function PartManager({ goBack }) {
  const { showToast } = useToast();
  const { confirmModal, requestConfirm } = useConfirm();

  // `parts` ahora almacenará el objeto completo de partes del backend
  const [parts, setParts] = useState({});
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(true);    // cargando partes por primera vez
  const [isImporting, setIsImporting] = useState(false); // subiendo archivo
  
  // Estado para los inputs del formulario (componentes controlados)
  const [formData, setFormData] = useState({
    'n_parte': '',
    'descripcion': '',
    'linea': '',
    'id': '',
    'qtu': '',
    'linea_lg': '',
    'ayuda_visual_link': ''
  });
  const [selectedPartNumber, setSelectedPartNumber] = useState(null); // Para saber qué parte está seleccionada en la lista


  // Función para cargar las partes desde el backend
  const fetchParts = async () => {
    try {
      const response = await apiFetch("/parts");
      if (response.ok) {
        const data = await response.json();
        setParts(data);
      } else {
        console.error("Error fetching parts:", response.statusText);
        showToast('Error al cargar las partes del servidor.', 'error');
      }
    } catch (error) {
      console.error("Error de conexión al cargar partes:", error);
      showToast('Sin conexión con el servidor. Verifica que el backend esté corriendo.', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  // Cargar partes al montar el componente
  useEffect(() => {
    fetchParts();
  }, []);

  // Manejar cambios en los inputs del formulario
  const handleInputChange = (e, key) => {
    setFormData({ ...formData, [key]: e.target.value });
  };
  
  // Referencia oculta para el input de tipo archivo
  const fileInputRef = useRef(null);

  // Función para abrir la ventana de selección de archivos
  const handleImportClick = () => {
    fileInputRef.current.click();
  };

  // Función que se ejecuta cuando el usuario selecciona el archivo
  const handleFileChange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setIsImporting(true); // Mostrar banner de carga
    const formDataObj = new FormData();
    formDataObj.append("file", file);

    try {
      const response = await apiFetch("/parts/import", {
        method: "POST",
        body: formDataObj,
      });
      const result = await response.json();
      if (response.ok) {
        showToast(result.message, 'success');
        await fetchParts(); // Recargar lista
      } else {
        showToast('Error: ' + result.detail, 'error');
      }
    } catch (error) {
      console.error("Error al importar:", error);
      showToast('Error de conexión con el servidor.', 'error');
    } finally {
      setIsImporting(false); // Ocultar banner
      event.target.value = null;
    }
  };

  // Manejar la selección de una parte de la lista
  const handlePartSelect = (partNum) => {
    setSelectedPartNumber(partNum);
    const partDetails = parts[partNum];
    if (partDetails) {
      setFormData({
        'n_parte': partNum,
        'descripcion': partDetails.descripcion,
        'linea': partDetails.linea,
        'id': partDetails.id,
        'qtu': partDetails.qtu,
        'linea_lg': partDetails.linea_lg,
        'ayuda_visual_link': partDetails.ayuda_visual
      });
    }
  };
  const clearForm = () => {
    setFormData({ 'n_parte': '', 'descripcion': '', 'linea': '', 'id': '', 'qtu': '', 'linea_lg': '', 'ayuda_visual_link': '' });
    setSelectedPartNumber(null);
  };

  // Agregar nueva parte
  const handleAdd = async () => {
    const partNumber = formData.n_parte.trim().toUpperCase();
    if (!partNumber) { showToast('El número de parte es obligatorio.', 'warning'); return; }
    try {
      const response = await apiFetch(`/parts/${encodeURIComponent(partNumber)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          descripcion: formData.descripcion,
          linea: formData.linea,
          id: formData.id,
          qtu: formData.qtu,
          linea_lg: formData.linea_lg,
          ayuda_visual: formData.ayuda_visual_link
        })
      });
      const result = await response.json();
      if (response.ok) {
        showToast(result.message, 'success');
        clearForm();
        fetchParts();
      } else {
        showToast('Error: ' + result.detail, 'error');
      }
    } catch (error) {
      showToast('Error de conexión con el servidor.', 'error');
    }
  };

  // Editar parte existente
  const handleEdit = async () => {
    if (!selectedPartNumber) { showToast('Selecciona una parte de la lista primero.', 'warning'); return; }
    const newPartNumber = formData.n_parte.trim().toUpperCase();
    if (!newPartNumber) { showToast('El número de parte es obligatorio.', 'warning'); return; }
    try {
      const url = new URL(`/parts/${encodeURIComponent(selectedPartNumber)}`, import.meta.env.VITE_API_URL ?? 'http://localhost:8000');
      if (newPartNumber !== selectedPartNumber) {
        url.searchParams.set('new_part_number', newPartNumber);
      }
      const response = await apiFetch(url.pathname + url.search, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          descripcion: formData.descripcion,
          linea: formData.linea,
          id: formData.id,
          qtu: formData.qtu,
          linea_lg: formData.linea_lg,
          ayuda_visual: formData.ayuda_visual_link
        })
      });
      const result = await response.json();
      if (response.ok) {
        showToast(result.message, 'success');
        clearForm();
        fetchParts();
      } else {
        showToast('Error: ' + result.detail, 'error');
      }
    } catch (error) {
      showToast('Error de conexión con el servidor.', 'error');
    }
  };

  // Borrar parte
  const handleDelete = async () => {
    if (!selectedPartNumber) { showToast('Selecciona una parte de la lista primero.', 'warning'); return; }
    const ok = await requestConfirm({
      title: 'Borrar número de parte',
      message: `¿Estás seguro de que deseas borrar permanentemente la parte "${selectedPartNumber}"? Esta acción no se puede deshacer.`,
      confirmText: 'Sí, borrar',
      danger: true,
    });
    if (!ok) return;
    try {
      const response = await apiFetch(`/parts/${encodeURIComponent(selectedPartNumber)}`, {
        method: 'DELETE'
      });
      const result = await response.json();
      if (response.ok) {
        showToast(result.message, 'success');
        clearForm();
        fetchParts();
      } else {
        showToast('Error: ' + result.detail, 'error');
      }
    } catch (error) {
      showToast('Error de conexión con el servidor.', 'error');
    }
  };

  const handleAddToQueue = () => {
    // Redirige al usuario a la sección de Cola de Impresión.
    // El flujo principal de añadir a la cola está en PrintQueue.jsx.
    showToast(`Selecciona "Cola de Impresión" en el menú para añadir ${selectedPartNumber} a la cola.`, 'info');
  };

  // Exportar todas las partes actuales como CSV
  const handleExport = () => {
    const entries = Object.entries(parts);
    if (entries.length === 0) { showToast('No hay partes para exportar.', 'warning'); return; }
    const headers = ['Número de Parte', 'Descripción', 'Línea', 'ID', 'Cantidad', 'Cliente (LG)', 'Ayuda Visual'];
    const rows = entries.map(([partNum, d]) =>
      [
        partNum,
        `"${(d.descripcion || '').replace(/"/g, '""')}"`,
        d.linea || '',
        d.id || '',
        d.qtu || '',
        d.linea_lg || '',
        d.ayuda_visual || '',
      ].join(',')
    );
    const csv = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Partes_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    showToast(`${entries.length} parte${entries.length !== 1 ? 's' : ''} exportadas como CSV.`, 'success');
  };
  
  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto min-h-screen flex flex-col bg-slate-50 relative">

      {/* Modal de confirmación */}
      {confirmModal}

      {/* Banner de importación */}
      {isImporting && (
        <div className="fixed inset-0 z-40 bg-black/30 flex items-center justify-center">
          <div className="bg-white rounded-2xl shadow-2xl p-8 flex flex-col items-center gap-4 min-w-[280px]">
            <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
            <p className="font-bold text-slate-800 text-lg">Subiendo archivo...</p>
            <p className="text-slate-400 text-sm text-center">Procesando el Excel, por favor espera.</p>
          </div>
        </div>
      )}
      {/* Header */}
      <div className="flex justify-between items-center mb-8 bg-white p-5 rounded-2xl shadow-sm border border-slate-200">
        <div className="flex items-center gap-3">
          <span className="text-3xl">⚙️</span>
          <h2 className="text-xl md:text-2xl font-bold text-slate-800">Gestionar Números de Parte</h2>
        </div>
        <button onClick={goBack} className="bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800 px-5 py-2 rounded-lg font-semibold transition-colors">Volver al Menú</button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-grow">
        {/* Formulario */}
        <div className="bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200">
          <h3 className="font-bold text-lg text-slate-800 mb-6">Datos del Número de Parte</h3>
          <form className="flex flex-col gap-5">
            {[
              { label: 'N° Parte', key: 'n_parte' }, { label: 'Descripción', key: 'descripcion' }, { label: 'Línea', key: 'linea' },
              { label: 'ID', key: 'id' }, { label: 'Qty', key: 'qtu' }, { label: 'Cliente (LG)', key: 'linea_lg' },
              { label: 'Ayuda Visual (Link)', key: 'ayuda_visual_link' }
            ].map((field, idx) => (
              <div key={idx} className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                <label className="sm:w-1/3 font-medium text-slate-600 text-sm">{field.label}</label>
                <input
                  type="text"
                  value={formData[field.key]}
                  onChange={(e) => handleInputChange(e, field.key)}
                  className="sm:w-2/3 bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 block p-2.5 outline-none transition-all"
                  placeholder={`Ingrese ${field.label.toLowerCase()}`}
                />
              </div>
            ))}
            
            {/* Botones de Acción */}
            <div className="grid grid-cols-3 gap-3 mt-4 pt-6 border-t border-slate-100">
              <button type="button" onClick={handleAdd} className="bg-blue-600 text-white px-4 py-2.5 rounded-xl hover:bg-blue-700 font-medium transition-colors">Agregar</button>
              <button type="button" onClick={handleEdit} className="bg-amber-500 text-white px-4 py-2.5 rounded-xl hover:bg-amber-600 font-medium transition-colors" disabled={!selectedPartNumber}>Editar</button>
              <button type="button" onClick={handleDelete} className="bg-red-500 text-white px-4 py-2.5 rounded-xl hover:bg-red-600 font-medium transition-colors" disabled={!selectedPartNumber}>Borrar</button>
              <button type="button" onClick={clearForm} className="col-span-3 bg-slate-200 text-slate-700 px-4 py-3 rounded-xl hover:bg-slate-300 font-bold transition-colors mt-2 flex justify-center items-center gap-2">Limpiar Formulario</button>
              <button type="button" onClick={handleAddToQueue} className="col-span-3 bg-slate-800 text-white px-4 py-3 rounded-xl hover:bg-slate-900 font-bold transition-colors mt-2 flex justify-center items-center gap-2" disabled={!selectedPartNumber}>
                ➡️ Enviar a Cola de Impresión
              </button>
            </div>
          </form>
        </div>

        {/* Buscador y Lista */}
        <div className="bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200 flex flex-col">
          <h3 className="font-bold text-lg text-slate-800 mb-6">Listado de Partes</h3>
          <div className="mb-6 relative">
            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">🔍</span>
            <input 
              type="text" 
              placeholder="Buscar número de parte..." 
              className="w-full bg-slate-50 border border-slate-200 text-slate-900 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 block pl-10 p-3 outline-none transition-all"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          
          <div className="flex-grow border border-slate-200 rounded-xl overflow-y-auto max-h-[400px] relative">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center h-40 gap-3 text-slate-400">
                <div className="w-8 h-8 border-4 border-slate-200 border-t-blue-500 rounded-full animate-spin" />
                <p className="text-sm font-medium">Cargando partes...</p>
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {Object.entries(parts)
                  .filter(([partNum, partDetails]) =>
                    partNum.toUpperCase().includes(searchTerm.toUpperCase()) ||
                    (partDetails.descripcion || '').toUpperCase().includes(searchTerm.toUpperCase())
                  ).map(([partNum, partDetails]) => (
                  <li key={partNum} className={`p-4 hover:bg-blue-50 cursor-pointer transition-colors flex items-center justify-between group ${selectedPartNumber === partNum ? 'bg-blue-100' : ''}`} onClick={() => handlePartSelect(partNum)}>
                    <span className="font-medium text-slate-700">
                      {partNum} <span className="text-slate-400 font-normal ml-2">- {partDetails.descripcion}</span>
                    </span>
                    <span className="text-slate-300 group-hover:text-blue-500">•••</span>
                  </li>
                ))}
                {Object.keys(parts).length === 0 && (
                  <li className="p-8 text-center text-slate-400 text-sm">
                    No hay partes registradas. Importa un archivo para comenzar.
                  </li>
                )}
              </ul>
            )}
          </div>

          <div className="flex gap-3 mt-6">
            {/* Input oculto */}
            <input 
              type="file" 
              ref={fileInputRef} 
              onChange={handleFileChange} 
              accept=".xlsx, .xls, .csv" 
              className="hidden" 
            />
            {/* Botón que dispara el input oculto */}
            <button
              onClick={handleImportClick}
              disabled={isImporting}
              className="flex-1 bg-white border border-slate-300 text-slate-700 px-4 py-2.5 rounded-xl hover:bg-slate-50 font-medium transition-colors text-sm text-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isImporting ? '⏳ Importando...' : '📥 Importar'}
            </button>
            <button onClick={handleExport} className="flex-1 bg-white border border-slate-300 text-slate-700 px-4 py-2.5 rounded-xl hover:bg-slate-50 font-medium transition-colors text-sm text-center">📤 Exportar</button>
          </div>
        </div>
      </div>
    </div>
  );
}