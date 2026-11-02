import { useEffect, useState, useCallback } from 'react';
import { apiFetch } from '../api';
import { useToast } from '../hooks/useToast.jsx';

const fmt = (n, d = 0) => (n === null || n === undefined || n === '' || isNaN(n)) ? '-' : Number(n).toLocaleString('es-MX', { maximumFractionDigits: d, minimumFractionDigits: d });
const pct = (n) => (n === null || n === undefined) ? '-' : `${(n * 100).toFixed(1)}%`;
const MAQUINAS = Array.from({ length: 40 }, (_, i) => i + 1);

const vacia = (f) => ({
  horas: f.captura?.horas ?? 12,
  cav_real: f.captura?.cav_real ?? f.cav_bom ?? '',
  ciclo_real: f.captura?.ciclo_real ?? '',
  cambios_molde: f.captura?.cambios_molde ?? 0,
  prod_manual: f.captura?.prod_manual ?? '',
  paros: { ...(f.captura?.paros || {}) },
  scrap: { ...(f.captura?.scrap || {}) },
  mtto: { ...(f.captura?.mtto || {}) },
  comentario: f.captura?.comentario ?? '',
});

const num = (v) => (v === '' || v === null || v === undefined) ? null : Number(v);

function Campo({ label, value, onChange, step = 'any', w = 'w-24' }) {
  return (
    <label className="flex flex-col text-xs text-slate-500 font-medium">
      {label}
      <input type="number" step={step} min="0" value={value ?? ''} onChange={(e) => onChange(e.target.value)}
        className={`${w} mt-1 p-2 border border-slate-200 rounded-lg text-sm text-slate-800 bg-white focus:ring-2 focus:ring-blue-400 outline-none`} />
    </label>
  );
}

export default function CapturaTurno({ goBack }) {
  const { showToast } = useToast();
  const [fecha, setFecha] = useState('');
  const [turno, setTurno] = useState('');
  const [data, setData] = useState(null);
  const [abierta, setAbierta] = useState(null);   // key de la fila en edición
  const [form, setForm] = useState(null);
  const [verMtto, setVerMtto] = useState(false);
  const [nueva, setNueva] = useState({ maquina: 1, parte: '' });
  const [guardando, setGuardando] = useState(false);

  const cargar = useCallback(async (f = fecha, t = turno) => {
    const qs = new URLSearchParams();
    if (f) qs.set('fecha', f);
    if (t) qs.set('turno', t);
    try {
      const r = await apiFetch(`/captura/turno?${qs}`);
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();
      setData(d); setFecha(d.fecha); setTurno(d.turno);
    } catch (e) { showToast('No se pudo cargar el turno: ' + e.message, 'error'); }
  }, [fecha, turno, showToast]);

  useEffect(() => { cargar('', ''); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const keyDe = (f) => `${f.maquina}|${f.parte}`;
  const abrir = (f) => { setAbierta(keyDe(f)); setForm(vacia(f)); setVerMtto(false); };

  const guardar = async (f) => {
    setGuardando(true);
    const limpio = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== null && !isNaN(v)).map(([k, v]) => [k, Number(v)]));
    const body = {
      fecha, turno, maquina: f.maquina, parte: f.parte,
      horas: num(form.horas), cav_real: num(form.cav_real), ciclo_real: num(form.ciclo_real),
      cambios_molde: num(form.cambios_molde), prod_manual: num(form.prod_manual),
      paros: limpio(form.paros), scrap: limpio(form.scrap), mtto: limpio(form.mtto), comentario: form.comentario || '',
    };
    try {
      const r = await apiFetch('/captura/turno', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      showToast(`✅ Máquina ${f.maquina} · ${f.parte} guardada`, 'success');
      setAbierta(null); setForm(null);
      cargar();
    } catch (e) { showToast('Error al guardar: ' + e.message, 'error'); }
    finally { setGuardando(false); }
  };

  const agregarFila = () => {
    const parte = nueva.parte.trim().toUpperCase();
    if (!parte) { showToast('Escribe el número de parte.', 'warning'); return; }
    const f = { maquina: Number(nueva.maquina), parte, captura: {}, cav_bom: null, descripcion: '', prod_escaneada: 0, carritos: 0 };
    setData(d => ({ ...d, filas: [...d.filas, f] }));
    abrir(f);
    setNueva({ maquina: nueva.maquina, parte: '' });
  };

  const cat = data?.catalogos;
  const res = data?.resumen;

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      <div className="max-w-[1400px] mx-auto">
        <div className="flex flex-wrap justify-between items-center gap-4 mb-6 bg-white p-5 rounded-2xl shadow-sm border border-slate-200">
          <div className="flex items-center gap-3">
            <span className="text-3xl">📝</span>
            <div>
              <h2 className="text-xl md:text-2xl font-bold text-slate-800">Captura de Turno</h2>
              <p className="text-sm text-slate-500">La producción viene de las entradas al cuarto de secado. Aquí se captura horas, paros, scrap y ciclo real por máquina.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-slate-500 font-medium flex flex-col">Fecha del turno
              <input type="date" value={fecha} onChange={(e) => { setFecha(e.target.value); cargar(e.target.value, turno); }} className="mt-1 p-2 border border-slate-200 rounded-lg" />
            </label>
            <label className="text-xs text-slate-500 font-medium flex flex-col">Turno
              <select value={turno} onChange={(e) => { setTurno(e.target.value); cargar(fecha, e.target.value); }} className="mt-1 p-2 border border-slate-200 rounded-lg">
                <option value="DIA">Día (7:30–19:30)</option>
                <option value="NOCHE">Noche (19:30–7:30)</option>
              </select>
            </label>
            <button onClick={() => goBack()} className="bg-slate-100 text-slate-600 hover:bg-slate-200 px-5 py-2 rounded-lg font-semibold">Volver</button>
          </div>
        </div>

        {res && (
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
            {[['Meta', fmt(res.meta)], ['Resultado', fmt(res.resultado)], ['Cumplimiento', pct(res.cumplimiento)],
              ['Scrap', `${fmt(res.scrap)} (${pct(res.scrap_pct)})`], ['Paro', `${fmt(res.paro_hrs, 1)} h`], ['Sin capturar', res.sin_captura]].map(([k, v]) => (
              <div key={k} className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="text-xs text-slate-500 font-semibold uppercase">{k}</div>
                <div className={`text-xl font-bold ${k === 'Sin capturar' && v > 0 ? 'text-amber-600' : 'text-slate-800'}`}>{v}</div>
              </div>
            ))}
          </div>
        )}

        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 uppercase text-xs">
                <tr>
                  {['Máq.', 'No. Parte', 'Descripción', 'Carritos', 'Prod. TTL', 'Meta', '%', 'Scrap', 'Paro h', 'Estado', ''].map(h => <th key={h} className="p-3 text-left font-semibold">{h}</th>)}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.filas?.length === 0 && (
                  <tr><td colSpan="11" className="p-10 text-center text-slate-400">No hay entradas registradas en este turno. Puedes agregar una máquina abajo (p. ej. si estuvo en paro).</td></tr>
                )}
                {data?.filas?.map((f) => {
                  const k = keyDe(f);
                  const abiertaEsta = abierta === k;
                  return (
                    <FragmentFila key={k}>
                      <tr className={`${abiertaEsta ? 'bg-blue-50' : 'hover:bg-slate-50'}`}>
                        <td className="p-3 font-bold">{f.maquina || '¿?'}</td>
                        <td className="p-3 font-mono">{f.parte}{f.sin_bom && <span title="No está en el BOM: sin peso/ciclo/cavidades" className="ml-1 text-amber-600">⚠</span>}</td>
                        <td className="p-3 text-slate-600">{f.descripcion}</td>
                        <td className="p-3">{f.carritos ?? 0}{f.en_secado > 0 && <span className="text-orange-500 text-xs"> ({f.en_secado} en secado)</span>}</td>
                        <td className="p-3 font-semibold">{fmt(f.prod_ttl)}</td>
                        <td className="p-3">{fmt(f.meta)}</td>
                        <td className={`p-3 font-bold ${f.cumplimiento >= 0.95 ? 'text-green-600' : f.cumplimiento >= 0.85 ? 'text-amber-600' : 'text-red-600'}`}>{pct(f.cumplimiento)}</td>
                        <td className="p-3">{fmt(f.scrap_ttl)}</td>
                        <td className="p-3">{fmt(f.paro_ttl, 1)}</td>
                        <td className="p-3">{f.capturado ? <span className="text-green-700 bg-green-100 px-2 py-0.5 rounded-full text-xs font-bold">Capturado</span> : <span className="text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full text-xs font-bold">Pendiente</span>}</td>
                        <td className="p-3 text-right">
                          <button onClick={() => abiertaEsta ? setAbierta(null) : abrir(f)} className="bg-blue-600 text-white px-3 py-1.5 rounded-lg text-xs font-bold hover:bg-blue-700">{abiertaEsta ? 'Cerrar' : 'Capturar'}</button>
                        </td>
                      </tr>
                      {abiertaEsta && form && cat && (
                        <tr className="bg-blue-50/60">
                          <td colSpan="11" className="p-4">
                            <div className="flex flex-wrap gap-4 mb-4">
                              <Campo label="Horas trabajadas" value={form.horas} onChange={(v) => setForm({ ...form, horas: v })} />
                              <Campo label={`Cav. real (BOM ${f.cav_bom ?? '-'})`} value={form.cav_real} onChange={(v) => setForm({ ...form, cav_real: v })} />
                              <Campo label={`Ciclo real seg (BOM ${f.ciclo_bom ?? '-'})`} value={form.ciclo_real} onChange={(v) => setForm({ ...form, ciclo_real: v })} />
                              <Campo label="Cambios de molde" step="1" value={form.cambios_molde} onChange={(v) => setForm({ ...form, cambios_molde: v })} />
                              <Campo label="Prod. manual (si no se escaneó)" w="w-40" value={form.prod_manual} onChange={(v) => setForm({ ...form, prod_manual: v })} />
                            </div>
                            <div className="mb-3 text-xs font-bold text-slate-600 uppercase">Paros (horas)</div>
                            <div className="flex flex-wrap gap-3 mb-4">
                              {cat.paros.map(([k, l]) => <Campo key={k} label={l} value={form.paros[k]} onChange={(v) => setForm({ ...form, paros: { ...form.paros, [k]: v } })} />)}
                            </div>
                            <div className="mb-3 text-xs font-bold text-slate-600 uppercase">Scrap (piezas)</div>
                            <div className="flex flex-wrap gap-3 mb-4">
                              {cat.scrap.map(([k, l]) => <Campo key={k} label={l} step="1" value={form.scrap[k]} onChange={(v) => setForm({ ...form, scrap: { ...form.scrap, [k]: v } })} />)}
                            </div>
                            <button type="button" onClick={() => setVerMtto(!verMtto)} className="text-xs font-bold text-blue-700 mb-3">{verMtto ? '▾' : '▸'} Detalle de paro por MTTO (horas)</button>
                            {verMtto && (
                              <div className="flex flex-wrap gap-3 mb-4">
                                {cat.mtto.map(([k, l]) => <Campo key={k} label={l} value={form.mtto[k]} onChange={(v) => setForm({ ...form, mtto: { ...form.mtto, [k]: v } })} />)}
                              </div>
                            )}
                            <label className="flex flex-col text-xs text-slate-500 font-medium mb-4">Comentario
                              <input value={form.comentario} onChange={(e) => setForm({ ...form, comentario: e.target.value })} className="mt-1 p-2 border border-slate-200 rounded-lg text-sm bg-white" placeholder="Ej. PARO POR CAMBIO DE MOLDE" />
                            </label>
                            <button disabled={guardando} onClick={() => guardar(f)} className="bg-green-600 text-white px-6 py-2 rounded-lg font-bold hover:bg-green-700 disabled:opacity-50">{guardando ? 'Guardando…' : '💾 Guardar captura'}</button>
                          </td>
                        </tr>
                      )}
                    </FragmentFila>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-wrap items-end gap-3">
            <span className="text-sm font-semibold text-slate-600">Agregar máquina sin escaneos:</span>
            <select value={nueva.maquina} onChange={(e) => setNueva({ ...nueva, maquina: e.target.value })} className="p-2 border border-slate-200 rounded-lg">
              {MAQUINAS.map(m => <option key={m} value={m}>Máquina {m}</option>)}
            </select>
            <input value={nueva.parte} onChange={(e) => setNueva({ ...nueva, parte: e.target.value })} placeholder="No. de parte" className="p-2 border border-slate-200 rounded-lg font-mono" />
            <button onClick={agregarFila} className="bg-slate-800 text-white px-4 py-2 rounded-lg font-semibold">+ Agregar</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function FragmentFila({ children }) { return <>{children}</>; }
