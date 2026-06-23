import React, { useState, useEffect } from 'react';
import { apiFetch } from '../api';

export default function ProductionReport({ goBack }) {
  const [records, setRecords] = useState([]);
  
  // Por defecto, muestra el reporte del día actual
  const [filtroFecha, setFiltroFecha] = useState(new Date().toISOString().split('T')[0]);
  const [filtroTurno, setFiltroTurno] = useState('TODOS');

  useEffect(() => {
    const fetchDryingState = async () => {
      try {
        const res = await apiFetch("/drying-room/state");
        if (res.ok) {
          const data = await res.json();
          // Obtenemos todos los registros históricos del cuarto de secado
          setRecords(data.records || []);
        }
      } catch (err) {
        console.error("Error al cargar estado del backend:", err);
      }
    };
    fetchDryingState();
  }, []);

  // 1. Filtrar registros según fecha y turno
  const filteredRecords = records.filter(r => {
    if (!r.horaEntrada) return false;
    const d = new Date(r.horaEntrada);
    if (isNaN(d.getTime())) return false;
    
    if (filtroFecha) {
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      if (`${yyyy}-${mm}-${dd}` !== filtroFecha) return false;
    }

    if (filtroTurno !== 'TODOS' && r.turno !== filtroTurno) return false;
    return true;
  });

  // 2. Agrupar y sumar la producción (entradas al cuarto de secado)
  const productionData = filteredRecords.reduce((acc, r) => {
    const d = r.horaEntrada ? new Date(r.horaEntrada) : null;
    const fechaStr = d && !isNaN(d.getTime()) ? d.toLocaleDateString() : '-';
    const turnoStr = r.turno || '-';
    
    const key = `${r.numeroParte}_${fechaStr}_${turnoStr}`;

    if (!acc[key]) {
      acc[key] = {
        fecha: fechaStr,
        turno: turnoStr,
        part: r.numeroParte,
        desc: r.descripcion,
        maquina: r.maquina,
        lotes: 0,
        totalQty: 0
      };
    }
    acc[key].lotes += 1;
    acc[key].totalQty += Number(r.qty) || 0;
    return acc;
  }, {});

  // 3. Convertir el objeto a un arreglo y calcular totales generales
  const reportArray = Object.values(productionData);
  const totalPiezas = reportArray.reduce((sum, item) => sum + item.totalQty, 0);
  const totalLotes = reportArray.reduce((sum, item) => sum + item.lotes, 0);

  const exportarCSV = () => {
    if (reportArray.length === 0) return alert('No hay datos para exportar.');
    const cabeceras = ['Fecha', 'Turno', 'N°_Parte', 'Descripción', 'Máquina', 'Lotes_Ingresados', 'Total_Piezas_Producidas'];
    const lineas = reportArray.map(r => 
      `${r.fecha},${r.turno},${r.part},"${r.desc}",${r.maquina},${r.lotes},${r.totalQty}`
    );
    const blob = new Blob([cabeceras.join(',') + '\n' + lineas.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Reporte_Produccion_${filtroFecha || 'General'}.csv`;
    link.click();
  };

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      {/* Header */}
      <div className="max-w-[1400px] mx-auto flex flex-wrap justify-between items-center gap-4 mb-6 bg-white p-5 rounded-2xl shadow-sm border border-slate-200">
        <div className="flex items-center gap-4">
          <span className="text-3xl">📊</span>
          <h2 className="text-xl md:text-2xl font-bold text-slate-800">Reporte de Producción</h2>
        </div>
        <button type="button" onClick={goBack} className="hidden md:block bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800 px-5 py-2 rounded-lg font-semibold transition-colors">
          Volver al Menú
        </button>
      </div>

      {/* KPI Cards */}
      <div className="max-w-[1400px] mx-auto grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 flex items-center justify-between border-l-4 border-l-purple-500">
          <div>
            <p className="text-slate-500 text-sm font-semibold uppercase tracking-wider mb-1">Total Piezas Producidas</p>
            <p className="text-4xl font-extrabold text-slate-800">{totalPiezas}</p>
          </div>
          <span className="text-4xl">📦</span>
        </div>
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 flex items-center justify-between border-l-4 border-l-blue-500">
          <div>
            <p className="text-slate-500 text-sm font-semibold uppercase tracking-wider mb-1">Total Lotes (Carritos)</p>
            <p className="text-4xl font-extrabold text-slate-800">{totalLotes}</p>
          </div>
          <span className="text-4xl">🧱</span>
        </div>
      </div>

      {/* Tabla de Reporte */}
      <div className="max-w-[1400px] mx-auto bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
        <div className="p-5 bg-slate-50 border-b border-slate-200 flex flex-wrap gap-4 items-center justify-between">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-slate-500">Fecha de Producción:</label>
              <input type="date" value={filtroFecha} onChange={(e) => setFiltroFecha(e.target.value)} className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-purple-500 outline-none"/>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-slate-500">Turno:</label>
              <select value={filtroTurno} onChange={(e) => setFiltroTurno(e.target.value)} className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-purple-500 outline-none">
                <option value="TODOS">Ambos Turnos</option><option value="DÍA">Día</option><option value="NOCHE">Noche</option>
              </select>
            </div>
            {(filtroFecha || filtroTurno !== 'TODOS') && (<button type="button" onClick={() => { setFiltroFecha(''); setFiltroTurno('TODOS'); }} className="text-sm text-purple-600 hover:underline">Limpiar Filtros</button>)}
          </div>
          <button type="button" onClick={exportarCSV} className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg font-medium text-sm transition-colors flex gap-2 items-center">📥 Exportar Reporte</button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse whitespace-nowrap">
            <thead><tr className="bg-white text-slate-500 text-xs uppercase tracking-wider border-b border-slate-200"><th className="p-4 font-medium text-center">Fecha</th><th className="p-4 font-medium text-center">Turno</th><th className="p-4 font-medium text-center">N° Parte</th><th className="p-4 font-medium text-left">Descripción</th><th className="p-4 font-medium text-center">Máquina (Línea)</th><th className="p-4 font-medium text-center">Lotes Ingresados</th><th className="p-4 font-medium text-center text-purple-600">Total Producido</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {reportArray.map((row, idx) => (<tr key={idx} className="hover:bg-slate-50 transition-colors"><td className="p-4 text-center text-slate-500 text-sm">{row.fecha}</td><td className="p-4 text-center font-semibold text-slate-500 text-xs">{row.turno}</td><td className="p-4 text-center font-bold text-slate-900">{row.part}</td><td className="p-4 text-left text-slate-600 text-sm truncate max-w-[200px]" title={row.desc}>{row.desc}</td><td className="p-4 text-center text-slate-600 text-sm">{row.maquina}</td><td className="p-4 text-center font-medium text-blue-600">{row.lotes}</td><td className="p-4 text-center font-extrabold text-purple-600 text-lg">{row.totalQty}</td></tr>))}
              {reportArray.length === 0 && (<tr><td colSpan="7" className="p-12 text-center text-slate-400">No hay producción registrada en esta fecha.</td></tr>)}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}