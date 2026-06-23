import React, { useState, useEffect } from 'react';
import { apiFetch } from '../api';

// ─── Gráfica de barras SVG (sin librerías externas) ─────────────────────────
function BarChart({ data, colorClass }) {
  if (!data || data.length === 0) return null;

  const maxVal = Math.max(...data.map(d => d.value), 1);
  const BAR_W = 48;
  const GAP   = 16;
  const H     = 160; // altura útil de las barras
  const svgW  = data.length * (BAR_W + GAP) + GAP;
  const svgH  = H + 56; // + espacio para etiquetas

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${svgW} ${svgH}`}
      className="overflow-visible"
      style={{ minWidth: `${Math.min(svgW, 320)}px` }}
    >
      {data.map((item, i) => {
        const barH = Math.max((item.value / maxVal) * H, 4);
        const x = GAP + i * (BAR_W + GAP);
        const y = H - barH;

        // Colores alternados por índice
        const fills = [
          '#3b82f6', '#f97316', '#8b5cf6',
          '#10b981', '#ef4444', '#eab308',
          '#06b6d4', '#ec4899',
        ];
        const fill = fills[i % fills.length];

        return (
          <g key={item.label}>
            {/* Barra */}
            <rect
              x={x}
              y={y}
              width={BAR_W}
              height={barH}
              rx={6}
              fill={fill}
              opacity={0.85}
            />
            {/* Valor encima */}
            <text
              x={x + BAR_W / 2}
              y={y - 6}
              textAnchor="middle"
              fontSize={11}
              fontWeight="700"
              fill="#1e293b"
            >
              {item.value}
            </text>
            {/* Etiqueta debajo (cortada si es larga) */}
            <text
              x={x + BAR_W / 2}
              y={H + 18}
              textAnchor="middle"
              fontSize={9}
              fontWeight="600"
              fill="#64748b"
            >
              {item.label.length > 10 ? item.label.slice(0, 9) + '…' : item.label}
            </text>
          </g>
        );
      })}
      {/* Línea base */}
      <line x1={0} y1={H} x2={svgW} y2={H} stroke="#e2e8f0" strokeWidth={1.5} />
    </svg>
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

    for (const r of dryingRecords) {
      if (!r.horaEntrada || !r.numeroParte) continue;
      const d = new Date(r.horaEntrada);
      if (isNaN(d.getTime()) || d < cutoff) continue;
      if (trendTurno !== 'TODOS' && r.turno !== trendTurno) continue;

      const pn = r.numeroParte;
      totals[pn] = (totals[pn] || 0) + (Number(r.qty) || 0);
      lotes[pn]  = (lotes[pn]  || 0) + 1;
    }

    return Object.entries(totals)
      .map(([label, value]) => ({ label, value, lotes: lotes[label] }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 12); // máx. 12 barras
  })();

  const totalPiezasTrend = trendData.reduce((s, d) => s + d.value, 0);
  const totalLotesTrend  = trendData.reduce((s, d) => s + d.lotes, 0);

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
        <div className="mb-10">
          <h2 className="text-xl font-bold text-slate-800 mb-6 flex items-center gap-2">
            <span className="text-orange-500">📈</span> Tendencia por Número de Parte — Cuarto de Secado
          </h2>

          <div className="bg-white rounded-3xl shadow-sm border border-slate-100 overflow-hidden">

            {/* Barra de controles */}
            <div className="flex flex-wrap items-center justify-between gap-4 p-5 border-b border-slate-100 bg-slate-50">
              {/* KPIs inline */}
              <div className="flex items-center gap-6">
                <div>
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total piezas</p>
                  <p className="text-2xl font-extrabold text-slate-800">{totalPiezasTrend.toLocaleString()}</p>
                </div>
                <div className="w-px h-10 bg-slate-200" />
                <div>
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Lotes</p>
                  <p className="text-2xl font-extrabold text-slate-800">{totalLotesTrend}</p>
                </div>
                <div className="w-px h-10 bg-slate-200" />
                <div>
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Partes distintas</p>
                  <p className="text-2xl font-extrabold text-slate-800">{trendData.length}</p>
                </div>
              </div>

              {/* Filtros */}
              <div className="flex items-center gap-3 flex-wrap">
                {/* Rango de días */}
                <div className="flex bg-slate-200 rounded-xl p-1 gap-1">
                  {[{ v: 1, l: 'Hoy' }, { v: 7, l: '7 días' }, { v: 30, l: '30 días' }].map(opt => (
                    <button
                      key={opt.v}
                      onClick={() => setTrendDays(opt.v)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        trendDays === opt.v
                          ? 'bg-white shadow text-orange-600'
                          : 'text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      {opt.l}
                    </button>
                  ))}
                </div>

                {/* Filtro turno */}
                <select
                  value={trendTurno}
                  onChange={e => setTrendTurno(e.target.value)}
                  className="border border-slate-200 rounded-xl px-3 py-2 text-sm font-medium text-slate-700 bg-white outline-none focus:ring-2 focus:ring-orange-400"
                >
                  <option value="TODOS">Ambos turnos</option>
                  <option value="DÍA">Turno Día</option>
                  <option value="NOCHE">Turno Noche</option>
                </select>
              </div>
            </div>

            {/* Área de la gráfica */}
            <div className="p-6">
              {trendLoading ? (
                <div className="flex items-center justify-center h-48 gap-3 text-slate-400">
                  <div className="w-8 h-8 border-4 border-slate-200 border-t-orange-500 rounded-full animate-spin" />
                  <p className="font-medium">Cargando datos...</p>
                </div>
              ) : trendData.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 gap-3 text-slate-400">
                  <span className="text-5xl">📭</span>
                  <p className="font-semibold">Sin registros para <span className="text-orange-500">{dayLabel}</span></p>
                  <p className="text-sm">Cuando haya entradas en el Cuarto de Secado, aparecerán aquí.</p>
                </div>
              ) : (
                <div className="overflow-x-auto pb-2">
                  <BarChart data={trendData} />
                </div>
              )}
            </div>

            {/* Tabla de ranking */}
            {trendData.length > 0 && (
              <div className="border-t border-slate-100">
                <div className="p-4 bg-slate-50 border-b border-slate-100">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Ranking de piezas producidas · {dayLabel} · {trendTurno === 'TODOS' ? 'Ambos turnos' : `Turno ${trendTurno}`}
                  </p>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-xs text-slate-400 uppercase tracking-wider">
                        <th className="px-5 py-3 text-left font-medium w-10">#</th>
                        <th className="px-5 py-3 text-left font-medium">N° Parte</th>
                        <th className="px-5 py-3 text-center font-medium">Lotes</th>
                        <th className="px-5 py-3 text-center font-medium">Total Piezas</th>
                        <th className="px-5 py-3 font-medium">Proporción</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {trendData.map((item, i) => {
                        const pct = totalPiezasTrend > 0 ? ((item.value / totalPiezasTrend) * 100).toFixed(1) : 0;
                        const colors = [
                          'bg-blue-500', 'bg-orange-500', 'bg-purple-500',
                          'bg-emerald-500', 'bg-red-500', 'bg-yellow-500',
                          'bg-cyan-500', 'bg-pink-500',
                        ];
                        const barColor = colors[i % colors.length];
                        return (
                          <tr key={item.label} className="hover:bg-slate-50 transition-colors">
                            <td className="px-5 py-3">
                              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${i < 3 ? barColor : 'bg-slate-300'}`}>
                                {i + 1}
                              </span>
                            </td>
                            <td className="px-5 py-3 font-mono font-bold text-slate-800">{item.label}</td>
                            <td className="px-5 py-3 text-center font-medium text-slate-600">{item.lotes}</td>
                            <td className="px-5 py-3 text-center font-extrabold text-slate-900">{item.value.toLocaleString()}</td>
                            <td className="px-5 py-3">
                              <div className="flex items-center gap-2">
                                <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
                                  <div className={`h-2 rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
                                </div>
                                <span className="text-xs font-semibold text-slate-500 w-10 text-right">{pct}%</span>
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
    </div>
  );
}