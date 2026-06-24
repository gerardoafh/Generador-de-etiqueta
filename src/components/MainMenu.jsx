import React, { useState, useEffect } from 'react';
import { apiFetch } from '../api';

// ─── Gráfica Lineal Múltiple SVG Premium ─────────────────────────
function LineChart({ data }) {
  const { chartData, topParts } = data;
  if (!chartData || chartData.length === 0 || topParts.length === 0) return null;

  // Encontrar el valor máximo global
  let maxVal = 1;
  chartData.forEach(d => {
    topParts.forEach(pn => {
      if (d[pn] > maxVal) maxVal = d[pn];
    });
  });

  const POINT_GAP = 120;
  const H = 400; // Altura grande para el Modal
  const svgW = Math.max(chartData.length * POINT_GAP, 800);
  const svgH = H + 80; 
  const offsetX = 60;

  const gridLines = 5;
  const gridYs = Array.from({ length: gridLines + 1 }, (_, i) => H - (H / gridLines) * i);

  const colors = ['#3b82f6', '#ef4444', '#10b981', '#f97316', '#8b5cf6'];

  return (
    <div className="relative w-full h-full flex flex-col bg-slate-900 rounded-3xl p-4 sm:p-8 shadow-2xl border border-slate-700">
      <div className="flex flex-wrap gap-3 sm:gap-6 mb-6 justify-center">
        {topParts.map((pn, i) => (
           <div key={pn} className="flex items-center gap-2 text-slate-200 text-sm sm:text-base font-bold bg-slate-800/80 px-4 py-2 rounded-full border border-slate-700">
             <span className="w-4 h-4 rounded-full shadow-inner" style={{ backgroundColor: colors[i] }}></span>
             {pn}
           </div>
        ))}
      </div>
      <div className="flex-1 overflow-x-auto overflow-y-hidden pb-4 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-800/50">
        <svg width="100%" height="100%" viewBox={`0 0 ${svgW} ${svgH}`} className="overflow-visible font-sans" style={{ minWidth: `${svgW}px`, minHeight: '300px' }}>
          <style>{`
            .data-point { cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
            .data-point:hover circle { r: 10; stroke-width: 4; filter: brightness(1.2); }
            .tooltip-group { opacity: 0; transition: opacity 0.2s; pointer-events: none; }
            .data-point:hover .tooltip-group { opacity: 1; transform: translateY(-4px); }
          `}</style>

          {/* Cuadrícula */}
          {gridYs.map((gy, idx) => (
            <g key={`grid-${idx}`}>
              <line x1={0} y1={gy} x2={svgW} y2={gy} stroke="#334155" strokeWidth={1.5} strokeDasharray="4 6" />
              <text x={45} y={gy + 5} textAnchor="end" fontSize={14} fill="#64748b" fontWeight="700">
                {Math.round((maxVal / gridLines) * idx)}
              </text>
            </g>
          ))}

          {/* Líneas por cada número de parte */}
          {topParts.map((pn, i) => {
            const color = colors[i];
            const points = chartData.map((d, j) => {
              const x = offsetX + j * POINT_GAP;
              const y = H - Math.max((d[pn] / maxVal) * H, 4);
              return { x, y, val: d[pn] };
            });
            const linePath = points.map((p, j) => (j === 0 ? `M ${p.x},${p.y}` : `L ${p.x},${p.y}`)).join(' ');

            return (
              <g key={pn}>
                <path d={linePath} fill="none" stroke={color} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
                {points.map((p, j) => (
                  <g key={`${pn}-${j}`} className="data-point">
                    <circle cx={p.x} cy={p.y} r={6} fill="#0f172a" stroke={color} strokeWidth={3} />
                    <g className="tooltip-group">
                       <rect x={p.x - 35} y={p.y - 50} width={70} height={32} rx={8} fill="#ffffff" filter="drop-shadow(0 10px 8px rgb(0 0 0 / 0.5))" />
                       <polygon points={`${p.x - 8},${p.y - 18} ${p.x + 8},${p.y - 18} ${p.x},${p.y - 8}`} fill="#ffffff" />
                       <text x={p.x} y={p.y - 28} textAnchor="middle" fontSize={16} fontWeight="900" fill={color}>{p.val}</text>
                    </g>
                  </g>
                ))}
              </g>
            );
          })}

          {/* Eje X (Fechas) */}
          {chartData.map((d, j) => {
            const x = offsetX + j * POINT_GAP;
            return (
              <g key={`x-${j}`}>
                <text x={x} y={H + 30} textAnchor="middle" fontSize={14} fontWeight="800" fill="#94a3b8" className="capitalize">
                  {d.dateLabel}
                </text>
              </g>
            );
          })}
          <line x1={55} y1={H} x2={svgW} y2={H} stroke="#475569" strokeWidth={3} strokeLinecap="round" />
        </svg>
      </div>
    </div>
  );
}


// ─── Componente principal ─────────────────────────────────────────────────────
export default function MainMenu({ setView }) {
  // ── Estado del backend ────────────────────────────────────────────────────
  const [backendStatus, setBackendStatus] = useState('checking');

  const checkBackend = async () => {
    try {
      const res = await apiFetch('/parts');
      setBackendStatus(res.ok ? 'online' : 'offline');
    } catch {
      setBackendStatus('offline');
    }
  };

  useEffect(() => {
    checkBackend();
    const interval = setInterval(checkBackend, 30_000);
    return () => clearInterval(interval);
  }, []);

  const statusConfig = {
    checking: { dot: 'bg-yellow-400 animate-pulse', label: 'Verificando...' },
    online:   { dot: 'bg-green-400 animate-pulse',  label: 'Sistema en línea' },
    offline:  { dot: 'bg-red-500',                  label: 'Backend sin conexión' },
  };
  const st = statusConfig[backendStatus];

  // ── Datos del cuarto de secado para tendencia ─────────────────────────────
  const [dryingRecords, setDryingRecords] = useState([]);
  const [trendDays, setTrendDays]         = useState(1);   // 1 | 7 | 30
  const [trendTurno, setTrendTurno]       = useState('TODOS');
  const [trendLoading, setTrendLoading]   = useState(true);
  const [chartModalOpen, setChartModalOpen] = useState(false); // <--- NUEVO ESTADO PARA EL MODAL

  useEffect(() => {
    const fetchDrying = async () => {
      try {
        const res = await apiFetch('/drying-room/state');
        if (res.ok) {
          const data = await res.json();
          setDryingRecords(data.records || []);
        }
      } catch { /* sin conexión, se muestra vacío */ }
      finally { setTrendLoading(false); }
    };
    fetchDrying();
  }, []);

  // ── Calcular datos del gráfico ────────────────────────────────────────────
  const trendData = (() => {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - trendDays + 1);
    cutoff.setHours(0, 0, 0, 0);

    const totals = {};   // { partNumber: totalQty }
    const lotes  = {};   // { partNumber: numLotes }
    const dailyData = {}; 

    for (const r of dryingRecords) {
      if (!r.horaEntrada || !r.numeroParte) continue;
      const d = new Date(r.horaEntrada);
      if (isNaN(d.getTime()) || d < cutoff) continue;
      if (trendTurno !== 'TODOS' && r.turno !== trendTurno) continue;

      const pn = r.numeroParte;
      totals[pn] = (totals[pn] || 0) + (Number(r.qty) || 0);
      lotes[pn]  = (lotes[pn]  || 0) + 1;

      // Agrupamos por fecha "YYYY-MM-DD" local
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const dateKey = `${yyyy}-${mm}-${dd}`;

      if (!dailyData[dateKey]) dailyData[dateKey] = {};
      dailyData[dateKey][pn] = (dailyData[dateKey][pn] || 0) + (Number(r.qty) || 0);
    }

    const ranking = Object.entries(totals)
      .map(([label, value]) => ({ label, value, lotes: lotes[label] }))
      .sort((a, b) => b.value - a.value);

    // Seleccionar los 5 modelos principales para la gráfica
    const topParts = ranking.slice(0, 5).map(r => r.label);

    // Generar dataset para cada día del rango
    const chartData = [];
    for (let i = trendDays - 1; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        const dateKey = `${yyyy}-${mm}-${dd}`;
        
        const dateLabel = d.toLocaleDateString('es-ES', { weekday: 'short', day: '2-digit' }).replace('.', '');
        
        const dayRecord = { dateLabel };
        for (const pn of topParts) {
            dayRecord[pn] = (dailyData[dateKey] && dailyData[dateKey][pn]) || 0;
        }
        chartData.push(dayRecord);
    }

    return { ranking, chartData, topParts };
  })();

  const totalPiezasTrend = trendData.ranking.reduce((s, d) => s + d.value, 0);
  const totalLotesTrend  = trendData.ranking.reduce((s, d) => s + d.lotes, 0);

  const dayLabel = trendDays === 1 ? 'Hoy' : `Últimos ${trendDays} días`;

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50 relative overflow-hidden">
      {/* Círculos decorativos de fondo */}
      <div className="absolute top-[-10%] left-[-10%] w-96 h-96 bg-blue-100 rounded-full mix-blend-multiply filter blur-3xl opacity-70" />
      <div className="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-orange-100 rounded-full mix-blend-multiply filter blur-3xl opacity-70" />

      {/* Contenedor Principal */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-12 relative z-10">

        {/* Banner de Bienvenida */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-10 bg-white/60 backdrop-blur-md p-6 md:p-8 rounded-3xl shadow-sm border border-white">
          <div className="flex items-center gap-6">
            <div className="w-20 h-20 bg-white border-2 border-slate-100 rounded-2xl flex items-center justify-center shadow-md transform -rotate-3 shrink-0">
              <span className="text-3xl font-extrabold"><span className="text-blue-600">C</span><span className="text-red-600">w</span></span>
            </div>
            <div>
              <h1 className="text-2xl md:text-4xl font-extrabold text-slate-800 tracking-tight mb-2">
                Sistema de Gestión
              </h1>
              <p className="text-slate-500 md:text-lg">Bienvenido al panel principal de control</p>
            </div>
          </div>
          <div className="hidden lg:block text-right mt-4 md:mt-0">
            <p className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Fecha Actual</p>
            <p className="text-xl font-bold text-slate-700 capitalize">
              {new Date().toLocaleDateString('es-ES', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            </p>
          </div>
        </div>

        {/* Cuadrícula de Módulos */}
        <div className="mb-10">
          <h2 className="text-xl font-bold text-slate-800 mb-6 flex items-center gap-2">
            <span className="text-blue-500">⚡</span> Módulos del Sistema
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">

            <div onClick={() => setView('parts')} className="bg-white rounded-3xl p-6 shadow-sm hover:shadow-xl border border-slate-100 hover:border-blue-300 transition-all duration-300 cursor-pointer group flex flex-col h-full">
              <div className="w-14 h-14 bg-blue-50 text-blue-600 rounded-2xl flex items-center justify-center text-2xl mb-6 group-hover:scale-110 group-hover:bg-blue-600 group-hover:text-white transition-all">⚙️</div>
              <h3 className="text-lg font-bold text-slate-800 mb-2">Gestor de Partes</h3>
              <p className="text-slate-500 text-sm flex-grow mb-6">Administra, edita e importa los números de parte desde Excel.</p>
              <div className="text-blue-600 font-semibold text-sm flex items-center gap-2 group-hover:translate-x-2 transition-transform">Acceder al módulo <span>→</span></div>
            </div>

            <div onClick={() => setView('queue')} className="bg-white rounded-3xl p-6 shadow-sm hover:shadow-xl border border-slate-100 hover:border-green-300 transition-all duration-300 cursor-pointer group flex flex-col h-full">
              <div className="w-14 h-14 bg-green-50 text-green-600 rounded-2xl flex items-center justify-center text-2xl mb-6 group-hover:scale-110 group-hover:bg-green-600 group-hover:text-white transition-all">🖨️</div>
              <h3 className="text-lg font-bold text-slate-800 mb-2">Cola de Impresión</h3>
              <p className="text-slate-500 text-sm flex-grow mb-6">Genera lotes de etiquetas en PDF listas para enviar a producción.</p>
              <div className="text-green-600 font-semibold text-sm flex items-center gap-2 group-hover:translate-x-2 transition-transform">Acceder al módulo <span>→</span></div>
            </div>

            <div onClick={() => setView('drying')} className="bg-white rounded-3xl p-6 shadow-sm hover:shadow-xl border border-slate-100 hover:border-orange-300 transition-all duration-300 cursor-pointer group flex flex-col h-full">
              <div className="w-14 h-14 bg-orange-50 text-orange-600 rounded-2xl flex items-center justify-center text-2xl mb-6 group-hover:scale-110 group-hover:bg-orange-500 group-hover:text-white transition-all">♨️</div>
              <h3 className="text-lg font-bold text-slate-800 mb-2">Cuarto de Secado</h3>
              <p className="text-slate-500 text-sm flex-grow mb-6">Control de entradas y salidas FIFO mediante escáner.</p>
              <div className="text-orange-600 font-semibold text-sm flex items-center gap-2 group-hover:translate-x-2 transition-transform">Acceder al módulo <span>→</span></div>
            </div>

            <div onClick={() => setView('report')} className="bg-white rounded-3xl p-6 shadow-sm hover:shadow-xl border border-slate-100 hover:border-purple-300 transition-all duration-300 cursor-pointer group flex flex-col h-full">
              <div className="w-14 h-14 bg-purple-50 text-purple-600 rounded-2xl flex items-center justify-center text-2xl mb-6 group-hover:scale-110 group-hover:bg-purple-600 group-hover:text-white transition-all">📊</div>
              <h3 className="text-lg font-bold text-slate-800 mb-2">Reporte de Prod.</h3>
              <p className="text-slate-500 text-sm flex-grow mb-6">Analiza y exporta la cantidad de piezas procesadas por turno.</p>
              <div className="text-purple-600 font-semibold text-sm flex items-center gap-2 group-hover:translate-x-2 transition-transform">Acceder al módulo <span>→</span></div>
            </div>

          </div>
        </div>

        {/* ── SECCIÓN TENDENCIA CUARTO DE SECADO ── */}
        <div className="mb-12 relative">
          <h2 className="text-2xl font-extrabold text-slate-800 mb-6 flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-orange-400 to-red-500 rounded-xl flex items-center justify-center text-white shadow-lg shadow-orange-500/30">📈</div>
            Tendencia por Número de Parte <span className="text-slate-400 font-medium text-lg hidden sm:inline">| Cuarto de Secado</span>
          </h2>

          <div className="bg-white/80 backdrop-blur-xl rounded-3xl shadow-xl border border-white overflow-hidden ring-1 ring-slate-100">

            {/* Barra de controles premium */}
            <div className="p-6 md:p-8 bg-gradient-to-b from-slate-50 to-white flex flex-col xl:flex-row xl:items-center justify-between gap-6 border-b border-slate-100">
              
              {/* KPIs Glassmorphism */}
              <div className="flex gap-4 flex-wrap">
                <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 flex-1 min-w-[140px] flex items-center gap-4 hover:shadow-md transition-shadow">
                  <div className="w-12 h-12 bg-blue-50 text-blue-500 rounded-xl flex items-center justify-center text-xl">🧩</div>
                  <div>
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Total Piezas</p>
                    <p className="text-3xl font-black text-slate-800 tracking-tight">{totalPiezasTrend.toLocaleString()}</p>
                  </div>
                </div>
                <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 flex-1 min-w-[140px] flex items-center gap-4 hover:shadow-md transition-shadow">
                  <div className="w-12 h-12 bg-purple-50 text-purple-500 rounded-xl flex items-center justify-center text-xl">📦</div>
                  <div>
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Lotes</p>
                    <p className="text-3xl font-black text-slate-800 tracking-tight">{totalLotesTrend}</p>
                  </div>
                </div>
                <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 flex-1 min-w-[140px] flex items-center gap-4 hover:shadow-md transition-shadow">
                  <div className="w-12 h-12 bg-orange-50 text-orange-500 rounded-xl flex items-center justify-center text-xl">✨</div>
                  <div>
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Modelos</p>
                    <p className="text-3xl font-black text-slate-800 tracking-tight">{trendData.ranking.length}</p>
                  </div>
                </div>
              </div>

              {/* Filtros Modernos */}
              <div className="flex items-center gap-3 flex-wrap bg-slate-100 p-2 rounded-2xl shadow-inner">
                {/* Rango de días estilo Toggle */}
                <div className="flex bg-white rounded-xl shadow-sm p-1">
                  {[{ v: 1, l: 'Hoy' }, { v: 7, l: '7 días' }, { v: 30, l: '30 días' }].map(opt => (
                    <button
                      key={opt.v}
                      onClick={() => setTrendDays(opt.v)}
                      className={`px-4 py-2 rounded-lg text-sm font-bold transition-all duration-300 ${
                        trendDays === opt.v
                          ? 'bg-blue-500 text-white shadow-md transform scale-105'
                          : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'
                      }`}
                    >
                      {opt.l}
                    </button>
                  ))}
                </div>

                <div className="w-px h-8 bg-slate-200 hidden sm:block" />

                {/* Filtro turno */}
                <div className="relative">
                  <select
                    value={trendTurno}
                    onChange={e => setTrendTurno(e.target.value)}
                    className="appearance-none bg-white border-none shadow-sm rounded-xl pl-4 pr-10 py-2.5 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-400 cursor-pointer"
                  >
                    <option value="TODOS">🌍 Ambos turnos</option>
                    <option value="DÍA">☀️ Turno Día</option>
                    <option value="NOCHE">🌙 Turno Noche</option>
                  </select>
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                    ▼
                  </div>
                </div>
              </div>
            </div>

            {/* Área del Botón Maximizar */}
            <div className="p-8 bg-white relative text-center border-b border-slate-100">
              <div className="absolute top-0 right-0 w-64 h-64 bg-blue-50 rounded-full filter blur-3xl opacity-50 -translate-y-1/2 translate-x-1/2 pointer-events-none"></div>
              
              {trendLoading ? (
                <div className="flex flex-col items-center justify-center py-10 gap-4 text-slate-400">
                  <div className="w-10 h-10 border-4 border-slate-100 border-t-blue-500 rounded-full animate-spin shadow-lg" />
                  <p className="font-bold tracking-widest uppercase text-sm animate-pulse">Analizando datos...</p>
                </div>
              ) : trendData.ranking.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 gap-4 text-slate-400">
                  <div className="w-20 h-20 bg-slate-50 rounded-full flex items-center justify-center text-4xl shadow-inner">📭</div>
                  <p className="font-bold text-lg text-slate-500">Sin actividad registrada en <span className="text-blue-500">{dayLabel}</span></p>
                  <p className="text-sm">Las tendencias aparecerán aquí conforme fluya la producción.</p>
                </div>
              ) : (
                <div className="py-6 flex flex-col items-center justify-center relative z-10">
                  <button
                    onClick={() => setChartModalOpen(true)}
                    className="inline-flex items-center gap-4 px-10 py-5 bg-gradient-to-r from-blue-600 to-cyan-500 text-white font-black text-xl rounded-2xl shadow-xl hover:shadow-cyan-500/30 hover:scale-105 transition-all active:scale-95 group"
                  >
                    <span className="text-3xl group-hover:animate-bounce">📊</span> 
                    <span>Maximizar Gráfica de Tendencias</span>
                  </button>
                  <p className="mt-6 text-slate-500 font-medium text-sm flex items-center gap-2">
                    <span className="text-blue-500">ℹ️</span> Visualiza las curvas de producción diaria de los modelos principales.
                  </p>
                </div>
              )}
            </div>

            {/* Tabla de ranking mejorada */}
            {trendData.ranking.length > 0 && (
              <div className="bg-slate-50/50">
                <div className="p-6 border-y border-slate-100 flex items-center gap-3">
                  <span className="flex h-3 w-3 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                  </span>
                  <p className="text-sm font-bold text-slate-700 tracking-wide">
                    Ranking de Producción <span className="text-slate-400 font-normal">| {dayLabel} | {trendTurno === 'TODOS' ? 'Ambos turnos' : `Turno ${trendTurno}`}</span>
                  </p>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-100/50 text-xs text-slate-500 uppercase tracking-widest text-left">
                        <th className="px-6 py-4 font-bold w-16">Rank</th>
                        <th className="px-6 py-4 font-bold">Número de Parte</th>
                        <th className="px-6 py-4 font-bold text-center">Cant. Lotes</th>
                        <th className="px-6 py-4 font-bold text-right">Volumen (Pzs)</th>
                        <th className="px-6 py-4 font-bold w-1/4">Distribución</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                      {trendData.ranking.map((item, i) => {
                        const pct = totalPiezasTrend > 0 ? ((item.value / totalPiezasTrend) * 100).toFixed(1) : 0;
                        // Paleta de gradientes para las barras de progreso
                        const gradients = [
                          'from-blue-500 to-cyan-400',
                          'from-orange-500 to-amber-400',
                          'from-purple-500 to-pink-400',
                          'from-emerald-500 to-teal-400',
                          'from-red-500 to-rose-400',
                        ];
                        const grad = gradients[i % gradients.length];
                        const isTop3 = i < 3;
                        
                        return (
                          <tr key={item.label} className="hover:bg-blue-50/30 transition-colors group">
                            <td className="px-6 py-4">
                              <div className={`w-8 h-8 rounded-xl flex items-center justify-center font-black shadow-sm transition-transform group-hover:scale-110 ${isTop3 ? `bg-gradient-to-br ${grad} text-white` : 'bg-slate-100 text-slate-500'}`}>
                                {i + 1}
                              </div>
                            </td>
                            <td className="px-6 py-4 font-mono font-bold text-slate-700 text-base">{item.label}</td>
                            <td className="px-6 py-4 text-center">
                              <span className="bg-slate-100 text-slate-600 px-3 py-1 rounded-lg font-bold text-xs">{item.lotes}</span>
                            </td>
                            <td className="px-6 py-4 text-right font-black text-slate-800 text-lg">{item.value.toLocaleString()}</td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-3">
                                <div className="flex-1 bg-slate-100 rounded-full h-2.5 overflow-hidden shadow-inner">
                                  <div className={`h-full rounded-full bg-gradient-to-r ${grad} transition-all duration-1000 ease-out`} style={{ width: `${pct}%` }} />
                                </div>
                                <span className="text-xs font-bold text-slate-600 w-12 text-right bg-white px-2 py-1 rounded shadow-sm border border-slate-100">{pct}%</span>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

          </div>
        </div>

        {/* Footer / Estado del Sistema */}
        <div className="bg-slate-900 text-white rounded-3xl p-6 md:p-8 shadow-lg flex flex-col sm:flex-row justify-between items-center gap-4">
          <p className="text-slate-300 text-sm text-center sm:text-left">
            {backendStatus === 'offline'
              ? 'Backend no disponible. Verifica que el servidor esté corriendo en el puerto 8000.'
              : 'Asegúrate de mantener tu servidor Backend corriendo en el puerto 8000.'}
          </p>
          <button
            onClick={checkBackend}
            title="Verificar conexión ahora"
            className={`px-4 py-2 rounded-full text-sm font-semibold flex items-center gap-2 shrink-0 border transition-colors ${
              backendStatus === 'offline'
                ? 'bg-red-900/50 border-red-700 text-red-300 hover:bg-red-800/60'
                : 'bg-slate-800 border-slate-700 hover:bg-slate-700'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${st.dot}`} />
            {st.label}
          </button>
        </div>

      </div>

      {/* ── MODAL DE LA GRÁFICA ── */}
      {chartModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-900/90 backdrop-blur-md animate-in fade-in duration-300">
          <div className="w-full max-w-7xl h-[85vh] flex flex-col relative animate-in zoom-in-95 duration-300 drop-shadow-2xl">
            <button 
              onClick={() => setChartModalOpen(false)}
              className="absolute -top-4 -right-4 sm:-top-6 sm:-right-6 w-14 h-14 bg-red-500 text-white rounded-full flex items-center justify-center shadow-2xl font-black text-2xl hover:bg-red-600 hover:scale-110 hover:rotate-90 transition-all z-10"
              title="Cerrar Gráfica"
            >
              ✕
            </button>
            <div className="flex-1 rounded-3xl overflow-hidden border border-slate-700">
               <LineChart data={trendData} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}