import { useEffect, useState, useRef } from 'react';
import { apiFetch } from '../api';
import { useToast } from '../hooks/useToast.jsx';

const fmt = (n, d = 0) => (n === null || n === undefined || isNaN(n)) ? '-' : Number(n).toLocaleString('es-MX', { maximumFractionDigits: d, minimumFractionDigits: d });
const pct = (n) => (n === null || n === undefined) ? '-' : `${(n * 100).toFixed(1)}%`;
const colorPct = (n) => n == null ? 'text-slate-400' : n >= 0.95 ? 'text-green-600' : n >= 0.85 ? 'text-amber-600' : 'text-red-600';

export default function ProductionReport({ goBack }) {
  const { showToast } = useToast();
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [turno, setTurno] = useState('');
  const [data, setData] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [bomTotal, setBomTotal] = useState(null);
  const fileRef = useRef(null);

  const params = (d = desde, h = hasta, t = turno) => {
    const qs = new URLSearchParams();
    if (d) qs.set('desde', d);
    if (h) qs.set('hasta', h);
    if (t) qs.set('turno', t);
    return qs.toString();
  };

  const cargar = async (d = desde, h = hasta, t = turno) => {
    setCargando(true);
    try {
      const r = await apiFetch(`/reporte/produccion?${params(d, h, t)}`);
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      const j = await r.json();
      setData(j); setDesde(j.desde); setHasta(j.hasta);
    } catch (e) { showToast('Error al cargar el reporte: ' + e.message, 'error'); }
    finally { setCargando(false); }
  };

  const cargarBom = async () => {
    try { const r = await apiFetch('/bom'); if (r.ok) setBomTotal((await r.json()).total); } catch { /* sin conexión */ }
  };

  useEffect(() => { cargar('', '', ''); cargarBom(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const descargarExcel = async () => {
    try {
      const r = await apiFetch(`/reporte/produccion.xlsx?${params()}`);
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `Reporte_Produccion_${desde}_${hasta}.xlsx`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) { showToast('No se pudo descargar: ' + e.message, 'error'); }
  };

  const importarBom = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    showToast('Importando BOM…', 'info');
    try {
      const r = await apiFetch('/bom/import', { method: 'POST', body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.statusText);
      showToast(j.message, 'success');
      setBomTotal(j.total);
      cargar();
    } catch (err) { showToast('Error al importar BOM: ' + err.message, 'error'); }
    finally { e.target.value = ''; }
  };

  const t = data?.total;
  const kpis = t ? [
    ['Meta', fmt(t.meta), ''], ['Resultado', fmt(t.resultado), ''], ['Cumplimiento', pct(t.cumplimiento), colorPct(t.cumplimiento)],
    ['Producción Kg', fmt(t.kg, 1), ''], ['Scrap', `${fmt(t.scrap)} · ${pct(t.scrap_pct)}`, ''],
    ['Paro', `${fmt(t.paro_hrs, 1)} h · ${pct(t.paro_pct)}`, ''], ['Cambios de molde', fmt(t.cambios_molde), ''],
    ['Carritos', `${fmt(t.carritos)}${t.en_secado ? ` (${t.en_secado} en secado)` : ''}`, ''],
  ] : [];

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      <div className="max-w-[1500px] mx-auto">
        <div className="flex flex-wrap justify-between items-center gap-4 mb-6 bg-white p-5 rounded-2xl shadow-sm border border-slate-200">
          <div className="flex items-center gap-3">
            <span className="text-3xl">📊</span>
            <div>
              <h2 className="text-xl md:text-2xl font-bold text-slate-800">Reporte de Producción Completo</h2>
              <p className="text-sm text-slate-500">Producción = entradas al cuarto de secado · Meta = 3600 / ciclo BOM × cav. real × horas{bomTotal != null && <> · BOM: <b>{bomTotal}</b> partes</>}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-slate-500 font-medium flex flex-col">Desde
              <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="mt-1 p-2 border border-slate-200 rounded-lg" />
            </label>
            <label className="text-xs text-slate-500 font-medium flex flex-col">Hasta
              <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} className="mt-1 p-2 border border-slate-200 rounded-lg" />
            </label>
            <label className="text-xs text-slate-500 font-medium flex flex-col">Turno
              <select value={turno} onChange={(e) => setTurno(e.target.value)} className="mt-1 p-2 border border-slate-200 rounded-lg">
                <option value="">Ambos</option><option value="DIA">Día</option><option value="NOCHE">Noche</option>
              </select>
            </label>
            <button onClick={() => cargar()} className="bg-purple-600 text-white px-4 py-2 rounded-lg font-semibold hover:bg-purple-700">{cargando ? '…' : 'Consultar'}</button>
            <button onClick={descargarExcel} className="bg-green-600 text-white px-4 py-2 rounded-lg font-semibold hover:bg-green-700">⬇ Excel (formato mensual)</button>
            <button onClick={() => fileRef.current?.click()} className="bg-white border border-slate-300 text-slate-700 px-4 py-2 rounded-lg font-semibold hover:bg-slate-50">Importar BOM</button>
            <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.json" className="hidden" onChange={importarBom} />
            <button onClick={() => goBack()} className="bg-slate-100 text-slate-600 hover:bg-slate-200 px-4 py-2 rounded-lg font-semibold">Volver</button>
          </div>
        </div>

        {bomTotal === 0 && (
          <div className="mb-6 p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
            Aún no hay BOM cargado: sin él no hay peso, ciclo ni cavidades y la meta sale en 0. Usa <b>Importar BOM</b> con un Excel que tenga solo la hoja "BOM" (clic derecho en la hoja → Mover o copiar → nuevo libro).
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 mb-6">
          {kpis.map(([k, v, c]) => (
            <div key={k} className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
              <div className="text-xs text-slate-500 font-semibold uppercase">{k}</div>
              <div className={`text-lg font-bold ${c || 'text-slate-800'}`}>{v}</div>
            </div>
          ))}
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 mb-6 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 uppercase text-xs">
              <tr>{['Fecha', 'Turno', 'Meta', 'Resultado', '%', 'Kg', 'Ciclo meta', 'Ciclo real', 'Scrap', 'Paro h', 'C/M', 'Sin capturar'].map(h => <th key={h} className="p-3 text-left">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data?.por_turno?.map(r => (
                <tr key={r.fecha + r.turno}>
                  <td className="p-3 font-semibold">{r.fecha}</td><td className="p-3">{r.turno === 'DIA' ? 'Día' : 'Noche'}</td>
                  <td className="p-3">{fmt(r.meta)}</td><td className="p-3 font-semibold">{fmt(r.resultado)}</td>
                  <td className={`p-3 font-bold ${colorPct(r.cumplimiento)}`}>{pct(r.cumplimiento)}</td>
                  <td className="p-3">{fmt(r.kg, 1)}</td><td className="p-3">{fmt(r.ciclo_meta, 1)}</td><td className="p-3">{fmt(r.ciclo_real, 1)}</td>
                  <td className="p-3">{fmt(r.scrap)}</td><td className="p-3">{fmt(r.paro_hrs, 1)}</td><td className="p-3">{fmt(r.cambios_molde)}</td>
                  <td className={`p-3 ${r.sin_captura ? 'text-amber-600 font-bold' : 'text-slate-400'}`}>{r.sin_captura}</td>
                </tr>
              ))}
              {data && data.por_turno?.length === 0 && <tr><td colSpan="12" className="p-8 text-center text-slate-400">Sin producción registrada en el rango.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-x-auto">
          <table className="w-full text-xs md:text-sm">
            <thead className="bg-slate-50 text-slate-500 uppercase text-xs">
              <tr>{['Fecha', 'T', 'Máq.', 'No. Parte', 'Descripción', 'Cliente', 'Hrs', 'Cav', 'Ciclo', 'Meta', 'TTL', 'Buena', '%', 'Kg', 'Scrap', 'Paro h', 'Carritos', 'Comentario'].map(h => <th key={h} className="p-2 text-left">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data?.filas?.map(f => (
                <tr key={`${f.fecha}${f.turno}${f.maquina}${f.parte}`} className={!f.capturado ? 'bg-amber-50/40' : ''}>
                  <td className="p-2">{f.fecha.slice(5)}</td><td className="p-2">{f.turno === 'DIA' ? 'D' : 'N'}</td>
                  <td className="p-2 font-bold">{f.maquina || '¿?'}</td>
                  <td className="p-2 font-mono">{f.parte}{f.sin_bom ? <span title="No está en el BOM" className="text-amber-600"> ⚠</span> : f.faltan?.length > 0 && <span title={`Falta en BOM: ${f.faltan.join(", ")}`} className="text-amber-600"> ⚠</span>}{f.corte && <span title="Pieza de corte: sin meta por ciclo" className="ml-1 text-xs bg-slate-200 text-slate-600 px-1.5 rounded">corte</span>}</td>
                  <td className="p-2 text-slate-600">{f.descripcion}</td><td className="p-2">{f.cliente}</td>
                  <td className="p-2">{fmt(f.horas, 1)}</td><td className="p-2">{fmt(f.cav_real)}</td><td className="p-2">{fmt(f.ciclo_real)}</td>
                  <td className="p-2">{fmt(f.meta)}</td><td className="p-2">{fmt(f.prod_ttl)}</td><td className="p-2 font-semibold">{fmt(f.prod_buena)}</td>
                  <td className={`p-2 font-bold ${colorPct(f.cumplimiento)}`}>{pct(f.cumplimiento)}</td>
                  <td className="p-2">{fmt(f.prod_kg, 1)}</td><td className="p-2">{fmt(f.scrap_ttl)}</td><td className="p-2">{fmt(f.paro_ttl, 1)}</td>
                  <td className="p-2">{f.carritos}{f.en_secado > 0 && <span className="text-orange-500"> ({f.en_secado})</span>}</td>
                  <td className="p-2 text-slate-500">{f.comentario}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
