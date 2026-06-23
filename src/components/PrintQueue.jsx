import React, { useState, useEffect } from 'react';
import { apiFetch } from '../api';
import { useToast } from '../hooks/useToast.jsx';
import { useConfirm } from '../hooks/useConfirm.jsx';

export default function PrintQueue({ goBack }) {
  const { showToast } = useToast();
  const { confirmModal, requestConfirm } = useConfirm();

  const [queue, setQueue] = useState([]);
  const [isLoaded, setIsLoaded] = useState(false);

  // Estado para almacenar las partes disponibles desde el backend
  const [availableParts, setAvailableParts] = useState({});
  
  // Estados para el formulario de añadir
  const [selectedPart, setSelectedPart] = useState('');
  const [addQty, setAddQty] = useState(1);
  const [addTurno, setAddTurno] = useState('Día');

  // #7 — Estado de carga para generación de PDF
  const [isGenerating, setIsGenerating] = useState(false);

  // Cargar partes disponibles desde el backend al montar el componente
  useEffect(() => {
    const fetchAvailableParts = async () => {
      try {
        const response = await apiFetch("/parts");
        if (response.ok) {
          const data = await response.json();
          setAvailableParts(data);
          if (Object.keys(data).length > 0) {
            setSelectedPart(Object.keys(data)[0]);
          }
        }
      } catch (error) {
        console.error("Error de conexión al cargar partes disponibles:", error);
      }
    };
    fetchAvailableParts();
  }, []);

  // Cargar cola desde el backend al montar (reemplaza localStorage)
  useEffect(() => {
    const fetchQueue = async () => {
      try {
        const res = await apiFetch('/print-queue/state');
        if (res.ok) {
          const data = await res.json();
          setQueue(data.queue || []);
        }
      } catch (err) {
        console.error('Error al cargar cola desde el backend:', err);
      } finally {
        setIsLoaded(true);
      }
    };
    fetchQueue();
  }, []);

  // Guardar cola en el backend cada vez que cambie (con debounce de 800ms)
  useEffect(() => {
    if (!isLoaded) return; // No guardar hasta haber cargado
    const timer = setTimeout(() => {
      apiFetch('/print-queue/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ queue }),
      }).catch(err => console.error('Error al guardar cola en el backend:', err));
    }, 800);
    return () => clearTimeout(timer);
  }, [queue, isLoaded]);

  // #9 — Validación de cantidad mínima
  const handleAddQueue = () => {
    if (!selectedPart) {
      showToast('Por favor selecciona un número de parte.', 'warning');
      return;
    }
    const qty = Number(addQty);
    if (!qty || qty < 1) {
      showToast('La cantidad debe ser mayor o igual a 1.', 'error');
      return;
    }
    const newQueue = [...queue, {
      part: selectedPart,
      desc: availableParts[selectedPart]?.descripcion || '',
      qty,
      turno: addTurno
    }];
    setQueue(newQueue);
    setAddQty(1); // Resetear cantidad
    showToast(`Añadido: ${qty}× ${selectedPart} (${addTurno})`, 'success');
  };

  // #8 — Eliminar ítem individual
  const handleRemoveItem = async (idx) => {
    const item = queue[idx];
    const ok = await requestConfirm({
      title: 'Quitar de la cola',
      message: `¿Eliminar "${item.part}" (${item.qty} etiqueta${item.qty !== 1 ? 's' : ''}) de la cola?`,
      confirmText: 'Quitar',
      danger: true,
    });
    if (!ok) return;
    setQueue(prev => prev.filter((_, i) => i !== idx));
    showToast('Ítem eliminado de la cola.', 'info');
  };

  const handleClearQueue = async () => {
    if (queue.length === 0) return;
    const ok = await requestConfirm({
      title: 'Limpiar toda la cola',
      message: `¿Estás seguro? Se eliminarán los ${queue.length} ítem${queue.length !== 1 ? 's' : ''} de la cola.`,
      confirmText: 'Limpiar cola',
      danger: true,
    });
    if (!ok) return;
    setQueue([]);
    showToast('Cola de impresión limpiada.', 'info');
  };

  // #7 — Estado de carga en generación de PDF
  const handleGeneratePDF = async () => {
    if (queue.length === 0) {
      showToast('La cola está vacía. Añade partes primero.', 'warning');
      return;
    }
    setIsGenerating(true);
    try {
      const response = await apiFetch("/print-queue/generate-pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(queue)
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        window.open(url, '_blank');
        setTimeout(() => window.URL.revokeObjectURL(url), 1000);
        setQueue([]);
        showToast('¡PDF generado y abierto en nueva pestaña!', 'success');
      } else {
        const res = await response.json();
        showToast('Error al generar PDF: ' + res.detail, 'error');
      }
    } catch (error) {
      console.error("Error:", error);
      showToast('Error al conectar con el servidor para generar el PDF.', 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  const totalEtiquetas = queue.reduce((sum, item) => sum + item.qty, 0);

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto min-h-screen flex flex-col bg-slate-50">
      {/* Modal de confirmación */}
      {confirmModal}

      {/* Header */}
      <div className="flex justify-between items-center mb-8 bg-white p-5 rounded-2xl shadow-sm border border-slate-200">
        <div className="flex items-center gap-3">
          <span className="text-3xl">🖨️</span>
          <h2 className="text-xl md:text-2xl font-bold text-slate-800">Cola de Impresión</h2>
          {queue.length > 0 && (
            <span className="bg-blue-100 text-blue-700 text-xs font-bold px-2.5 py-1 rounded-full">
              {queue.length} ítem{queue.length !== 1 ? 's' : ''} · {totalEtiquetas} etiqueta{totalEtiquetas !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <button onClick={goBack} className="bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800 px-5 py-2 rounded-lg font-semibold transition-colors">Volver al Menú</button>
      </div>

      {/* Formulario Añadir a Cola */}
      <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 mb-8 flex flex-col md:flex-row gap-4 items-end">
        <div className="flex-1 min-w-[200px]">
          <label className="block font-medium text-slate-600 text-sm mb-2">Seleccionar N° Parte:</label>
          <select value={selectedPart} onChange={(e) => setSelectedPart(e.target.value)} className="w-full bg-slate-50 border border-slate-200 text-slate-900 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 p-3 outline-none transition-all">            
            {Object.entries(availableParts).map(([partNum, partDetails]) => (
              <option key={partNum} value={partNum}>
                {partNum} - {partDetails.descripcion}
              </option>
            ))}
          </select>
        </div>
        
        {/* #9 — Input con min=1 y borde rojo si inválido */}
        <div className="w-full md:w-32">
          <label className="block font-medium text-slate-600 text-sm mb-2">Cantidad:</label>
          <input
            type="number"
            value={addQty}
            onChange={(e) => setAddQty(e.target.value)}
            min="1"
            className={`w-full bg-slate-50 border text-slate-900 rounded-xl focus:ring-2 focus:ring-blue-500 p-3 outline-none transition-all ${
              Number(addQty) < 1 ? 'border-red-400 focus:border-red-400 focus:ring-red-400/30' : 'border-slate-200 focus:border-blue-500'
            }`}
          />
          {Number(addQty) < 1 && (
            <p className="text-red-500 text-xs mt-1 font-medium">Mínimo 1</p>
          )}
        </div>

        <div className="w-full md:w-40">
          <label className="block font-medium text-slate-600 text-sm mb-2">Turno:</label>
          <select value={addTurno} onChange={(e) => setAddTurno(e.target.value)} className="w-full bg-slate-50 border border-slate-200 text-slate-900 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 p-3 outline-none transition-all">
            <option>Día</option>
            <option>Noche</option>
          </select>
        </div>

        <button
          onClick={handleAddQueue}
          disabled={Number(addQty) < 1}
          className="w-full md:w-auto bg-green-600 text-white px-8 py-3 rounded-xl hover:bg-green-700 font-bold transition-colors shadow-sm disabled:opacity-40 disabled:cursor-not-allowed"
        >
          + Añadir
        </button>
      </div>

      {/* Tabla de Cola */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 flex-grow overflow-hidden flex flex-col">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 text-slate-500 uppercase text-xs tracking-wider border-b border-slate-200">
                <th className="p-5 font-medium">Número de Parte</th>
                <th className="p-5 font-medium text-left">Descripción</th>
                <th className="p-5 font-medium text-center">Cantidad</th>
                <th className="p-5 font-medium">Turno</th>
                {/* #8 — Columna de eliminar */}
                <th className="p-5 font-medium text-center">Quitar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {queue.map((item, idx) => (
                <tr key={idx} className="hover:bg-slate-50 transition-colors group">
                  <td className="p-5 font-semibold text-slate-800 font-mono">{item.part}</td>
                  <td className="p-5 text-slate-600 text-sm">{item.desc}</td>
                  <td className="p-5 text-center font-bold text-blue-600">{item.qty}</td>
                  <td className="p-5">
                    <span className={`px-3 py-1 rounded-full text-xs font-bold ${item.turno === 'Día' ? 'bg-blue-100 text-blue-700' : 'bg-indigo-100 text-indigo-700'}`}>
                      {item.turno}
                    </span>
                  </td>
                  {/* #8 — Botón ✕ por fila */}
                  <td className="p-5 text-center">
                    <button
                      onClick={() => handleRemoveItem(idx)}
                      title="Quitar de la cola"
                      className="w-7 h-7 rounded-full bg-slate-100 text-slate-400 hover:bg-red-100 hover:text-red-600 transition-colors font-bold text-sm flex items-center justify-center mx-auto"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
              {queue.length === 0 && (
                <tr>
                  <td colSpan="5" className="p-12 text-center text-slate-400">La cola está vacía. Añade partes arriba.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        
        {/* Acciones Finales */}
        <div className="p-5 bg-slate-50 border-t border-slate-200 flex flex-col md:flex-row gap-3 justify-end items-center">
          <button
            onClick={handleClearQueue}
            disabled={queue.length === 0}
            className="bg-white text-red-600 border border-red-200 px-6 py-2.5 rounded-xl hover:bg-red-50 font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Limpiar Cola
          </button>
          {/* #7 — Spinner y deshabilitar mientras genera */}
          <button
            onClick={handleGeneratePDF}
            disabled={isGenerating || queue.length === 0}
            className="bg-blue-600 text-white px-8 py-2.5 rounded-xl hover:bg-blue-700 font-bold shadow-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed min-w-[160px]"
          >
            {isGenerating ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Generando...
              </>
            ) : (
              '📄 Generar PDF'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}