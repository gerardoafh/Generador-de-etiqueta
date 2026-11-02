import { useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '../api';
import { useToast } from '../hooks/useToast.jsx';

const CAMPOS = [
  { k: 'parte', l: 'No. Parte', mono: true }, { k: 'descripcion', l: 'Descripción' }, { k: 'cliente', l: 'Cliente' },
  { k: 'linea', l: 'Línea' }, { k: 'modelo', l: 'Modelo' }, { k: 'id1', l: 'ID1' }, { k: 'id2', l: 'ID2 (Assy/Packing/Cutting)' },
  { k: 'resina', l: 'Resina' }, { k: 'tipo', l: 'Type (máquina)' }, { k: 'molde', l: 'Mold' },
  { k: 'cav', l: 'Cavidades', num: true }, { k: 'ciclo', l: 'Ciclo (seg)', num: true },
  { k: 'peso', l: 'Peso (kg)', num: true }, { k: 'densidad', l: 'Densidad', num: true },
];
const VACIO = Object.fromEntries(CAMPOS.map(c => [c.k, '']));

const faltantes = (v) => v.corte ? (v.peso ? [] : ['peso'])
  : [['cavidades', v.cav], ['ciclo', v.ciclo], ['peso', v.peso]].filter(([, x]) => !x).map(([n]) => n);

export default function BomManager({ confirmar }) {
  const { showToast } = useToast();
  const [bom, setBom] = useState({});
  const [buscar, setBuscar] = useState('');
  const [soloIncompletas, setSoloIncompletas] = useState(false);
  const [edit, setEdit] = useState(null);      // { original, datos }
  const [cargando, setCargando] = useState(true);
  const fileRef = useRef(null);

  const cargar = async () => {
    setCargando(true);
    try {
      const r = await apiFetch('/bom');
      if (r.ok) setBom((await r.json()).partes || {});
    } catch { showToast('No se pudo cargar el BOM.', 'error'); }
    finally { setCargando(false); }
  };
  useEffect(() => { cargar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const filas = useMemo(() => {
    const q = buscar.trim().toUpperCase();
    return Object.entries(bom)
      .filter(([k, v]) => !q || k.includes(q) || String(v.descripcion || '').toUpperCase().includes(q) || String(v.cliente || '').toUpperCase().includes(q) || String(v.modelo || '').toUpperCase().includes(q))
      .filter(([, v]) => !soloIncompletas || faltantes(v).length > 0)
      .sort(([a], [b]) => a.localeCompare(b));
  }, [bom, buscar, soloIncompletas]);

  const incompletas = useMemo(() => Object.values(bom).filter(v => faltantes(v).length > 0).length, [bom]);

  const abrir = (k, v) => setEdit({ original: k, datos: { ...VACIO, ...Object.fromEntries(CAMPOS.map(c => [c.k, v?.[c.k] ?? ''])), parte: k || '' } });

  const guardar = async () => {
    const d = edit.datos;
    if (!String(d.parte).trim()) { showToast('El número de parte es obligatorio.', 'warning'); return; }
    const body = Object.fromEntries(CAMPOS.map(c => [c.k, c.num ? (d[c.k] === '' || d[c.k] === null ? null : Number(d[c.k])) : String(d[c.k] ?? '')]));
    const original = edit.original || d.parte;
    try {
      const r = await apiFetch(`/bom/${encodeURIComponent(original)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.statusText);
      showToast(j.message, 'success');
      setEdit(null);
      cargar();
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
  };

  const borrar = async (k) => {
    const ok = await confirmar({ title: 'Eliminar del BOM', message: `¿Eliminar ${k} del BOM? El reporte ya no tendrá su peso, ciclo ni cavidades.`, confirmText: 'Eliminar', danger: true });
    if (!ok) return;
    const r = await apiFetch(`/bom/${encodeURIComponent(k)}`, { method: 'DELETE' });
    if (r.ok) { showToast(`${k} eliminada del BOM.`, 'info'); setEdit(null); cargar(); }
    else showToast('No se pudo eliminar.', 'error');
  };

  const importar = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    showToast('Importando BOM…', 'info');
    try {
      const r = await apiFetch('/bom/import', { method: 'POST', body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.statusText);
      showToast(j.message, 'success', 6000);
      cargar();
    } catch (err) { showToast('Error al importar: ' + err.message, 'error', 8000); }
    finally { e.target.value = ''; }
  };

  const exportar = () => {
    const cols = CAMPOS.map(c => c.k);
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const lineas = Object.entries(bom).map(([k, v]) => cols.map(c => esc(c === 'parte' ? k : v[c])).join(','));
    const blob = new Blob(['﻿' + CAMPOS.map(c => esc(c.l)).join(',') + '\n' + lineas.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `BOM_${new Date().toLocaleDateString('sv-SE')}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };

  return (
    <div className="flex flex-col gap-4 flex-grow">
      <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-200 flex flex-wrap items-center gap-3">
        <input value={buscar} onChange={(e) => setBuscar(e.target.value)} placeholder="Buscar parte, descripción, cliente o modelo…" className="flex-1 min-w-[220px] p-2.5 border border-slate-200 rounded-xl bg-slate-50 outline-none focus:ring-2 focus:ring-blue-400" />
        <label className="flex items-center gap-2 text-sm text-slate-600 font-medium cursor-pointer select-none">
          <input type="checkbox" checked={soloIncompletas} onChange={(e) => setSoloIncompletas(e.target.checked)} />
          Solo incompletas {incompletas > 0 && <span className="bg-amber-100 text-amber-700 text-xs font-bold px-2 py-0.5 rounded-full">{incompletas}</span>}
        </label>
        <span className="text-sm text-slate-500">{filas.length} de {Object.keys(bom).length}</span>
        <button onClick={() => abrir('', null)} className="bg-blue-600 text-white px-4 py-2 rounded-xl font-semibold hover:bg-blue-700 text-sm">+ Nueva parte</button>
        <button onClick={() => fileRef.current?.click()} className="bg-white border border-slate-300 text-slate-700 px-4 py-2 rounded-xl font-semibold hover:bg-slate-50 text-sm">📥 Importar Excel</button>
        <button onClick={exportar} className="bg-white border border-slate-300 text-slate-700 px-4 py-2 rounded-xl font-semibold hover:bg-slate-50 text-sm">📤 Exportar CSV</button>
        <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.json" className="hidden" onChange={importar} />
      </div>

      {edit && (
        <div className="bg-blue-50 border border-blue-200 p-5 rounded-2xl">
          <h3 className="font-bold text-slate-800 mb-4">{edit.original ? `Editar ${edit.original}` : 'Nueva parte en el BOM'}</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            {CAMPOS.map(c => (
              <label key={c.k} className="flex flex-col text-xs text-slate-500 font-medium">{c.l}
                <input type={c.num ? 'number' : 'text'} step="any" min="0" value={edit.datos[c.k] ?? ''}
                  onChange={(e) => setEdit({ ...edit, datos: { ...edit.datos, [c.k]: e.target.value } })}
                  className={`mt-1 p-2 border rounded-lg text-sm bg-white text-slate-800 outline-none focus:ring-2 focus:ring-blue-400 ${c.num && !edit.datos[c.k] ? 'border-amber-300' : 'border-slate-200'} ${c.mono ? 'font-mono uppercase' : ''}`} />
              </label>
            ))}
          </div>
          <p className="text-xs text-slate-500 mt-3">Meta del reporte = 3600 ÷ ciclo × cavidades × horas. Con ID2 = "Cutting" la parte se trata como corte (sin meta). Lo que guardes aquí se conserva aunque vuelvas a importar un Excel que traiga el dato vacío.</p>
          <div className="flex gap-3 mt-4">
            <button onClick={guardar} className="bg-green-600 text-white px-5 py-2 rounded-lg font-bold hover:bg-green-700">💾 Guardar</button>
            <button onClick={() => setEdit(null)} className="bg-white border border-slate-300 px-5 py-2 rounded-lg font-semibold">Cancelar</button>
            {edit.original && <button onClick={() => borrar(edit.original)} className="ml-auto text-red-600 border border-red-200 bg-white px-4 py-2 rounded-lg font-semibold hover:bg-red-50">Eliminar</button>}
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden flex-grow">
        <div className="overflow-auto max-h-[65vh]">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 uppercase text-xs sticky top-0">
              <tr>{['No. Parte', 'Descripción', 'Cliente', 'Modelo', 'ID2', 'Type', 'Mold', 'Cav.', 'Ciclo', 'Peso kg', 'Estado'].map(h => <th key={h} className="p-3 text-left font-semibold">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cargando && <tr><td colSpan="11" className="p-8 text-center text-slate-400">Cargando…</td></tr>}
              {!cargando && filas.length === 0 && <tr><td colSpan="11" className="p-8 text-center text-slate-400">{Object.keys(bom).length ? 'Sin resultados.' : 'BOM vacío: usa “Importar Excel”.'}</td></tr>}
              {filas.map(([k, v]) => {
                const f = faltantes(v);
                return (
                  <tr key={k} onClick={() => abrir(k, v)} className={`cursor-pointer hover:bg-blue-50 ${edit?.original === k ? 'bg-blue-50' : ''}`}>
                    <td className="p-3 font-mono font-semibold">{k}</td>
                    <td className="p-3 text-slate-600">{v.descripcion}</td>
                    <td className="p-3">{v.cliente}</td>
                    <td className="p-3 text-slate-500">{v.modelo}</td>
                    <td className="p-3">{v.id2}</td>
                    <td className="p-3">{v.tipo}</td>
                    <td className="p-3">{v.molde}</td>
                    <td className={`p-3 ${!v.cav && !v.corte ? 'text-amber-600 font-bold' : ''}`}>{v.cav ?? '—'}</td>
                    <td className={`p-3 ${!v.ciclo && !v.corte ? 'text-amber-600 font-bold' : ''}`}>{v.ciclo ?? '—'}{v.ciclo_fuente && v.ciclo_fuente !== 'R' && <span className="text-xs text-slate-400" title={v.ciclo_fuente === 'manual' ? 'Capturado a mano' : `Tomado de la columna ${v.ciclo_fuente}`}> ({v.ciclo_fuente})</span>}</td>
                    <td className={`p-3 ${!v.peso ? 'text-amber-600 font-bold' : ''}`}>{v.peso ?? '—'}</td>
                    <td className="p-3">
                      {v.corte && <span className="text-xs bg-slate-200 text-slate-600 px-2 py-0.5 rounded-full mr-1">corte</span>}
                      {f.length > 0 ? <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-semibold">falta {f.join(', ')}</span>
                        : <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">completa</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
