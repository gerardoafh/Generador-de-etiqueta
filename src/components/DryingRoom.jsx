import React, { useState, useEffect, useRef } from 'react';
import WebQRScanner from './WebQRScanner';
import { apiFetch } from '../api';
import { useToast } from '../hooks/useToast.jsx';
import { useConfirm } from '../hooks/useConfirm.jsx';

// Función para obtener el turno actual (07:30 a 19:30 = DÍA)
const getTurnoActual = () => {
  const ahora = new Date();
  const horaDecimal = ahora.getHours() + (ahora.getMinutes() / 60);
  return (horaDecimal >= 7.5 && horaDecimal < 19.5) ? 'DÍA' : 'NOCHE';
};

// #2 — Genera un ID único para cada carrito, no se repite entre turnos
const generarIdCarrito = () => `C-${Date.now().toString(36).toUpperCase()}`;

// #8 — Timer en vivo: muestra los minutos transcurridos para carritos EN SECADO
// Se actualiza cada 30s de forma independiente para no causar re-renders globales.
function LiveTimer({ horaEntrada, maxMins }) {
  const [mins, setMins] = React.useState(() =>
    Math.floor((Date.now() - new Date(horaEntrada)) / 60000)
  );
  useEffect(() => {
    const id = setInterval(() => {
      setMins(Math.floor((Date.now() - new Date(horaEntrada)) / 60000));
    }, 30_000);
    return () => clearInterval(id);
  }, [horaEntrada]);
  const vencido = maxMins > 0 && mins >= maxMins;
  return (
    <span className={vencido ? 'text-red-600 font-bold animate-pulse' : 'text-orange-500 font-semibold'}>
      ⏱ {mins} min{vencido ? ' ⚠️' : ''}
    </span>
  );
}



export default function DryingRoom({ goBack }) {
  const { showToast } = useToast();
  const { confirmModal, requestConfirm } = useConfirm();

  const [partData, setPartData] = useState({}); // Para almacenar los datos de las partes del backend
  const [scanMode, setScanMode] = useState('ENTRADA');
  const [qrCode, setQrCode] = useState('');
  const [isScannerOpen, setIsScannerOpen] = useState(false);
  const [records, setRecords] = useState([]);

  // Variables de control y acumulados por turno
  const [acumuladoPorParte, setAcumuladoPorParte] = useState({});
  const [contadorCarritos, setContadorCarritos] = useState({});
  const [turnoActual, setTurnoActual] = useState(getTurnoActual());

  // Tiempo máximo de secado (configurable, en minutos). Se persiste en localStorage.
  const [maxDryingMins, setMaxDryingMins] = useState(() => {
    const saved = localStorage.getItem('maxDryingMins');
    return saved !== null ? Number(saved) : 60;
  });

  useEffect(() => {
    localStorage.setItem('maxDryingMins', String(maxDryingMins));
  }, [maxDryingMins]);

  // Panel de análisis de tiempos
  const [viendoAnalisis, setViendoAnalisis] = useState(false);

  // Filtros
  const [filtroParte, setFiltroParte] = useState('');
  const [filtroMaquina, setFiltroMaquina] = useState('TODAS');
  const [viendoHistorial, setViendoHistorial] = useState(false);
  const [filtroFecha, setFiltroFecha] = useState('');
  const inputRef = useRef(null); // Ref para mantener el enfoque en el campo de texto
  const [isStateLoaded, setIsStateLoaded] = useState(false); // Para saber si ya cargamos la red

  // Cargar datos de partes desde el backend al montar el componente
  useEffect(() => {
    const fetchPartData = async () => {
      try {
        const response = await apiFetch("/parts");
        if (response.ok) {
          const data = await response.json();
          setPartData(data || {});
        } else {
          console.error("Error fetching part data for DryingRoom:", response.statusText);
        }
      } catch (error) {
        console.error("Error de conexión al cargar datos de partes para DryingRoom:", error);
      }
    };
    fetchPartData();
  }, []);

  // Historial de turnos anteriores (snapshots)
  const [historialTurnos, setHistorialTurnos] = useState([]);

  // NUEVO: Cargar el historial y acumulados desde el backend para compartir en todas las máquinas
  useEffect(() => {
    const fetchDryingState = async () => {
      try {
        const res = await apiFetch("/drying-room/state");
        if (res.ok) {
          const data = await res.json();
          if (data.turnoActual) {
            // Convertir de vuelta las cadenas de texto a Objetos Date
            const parsedRecords = (data.records || []).map(r => ({
              ...r,
              horaEntrada: r.horaEntrada ? new Date(r.horaEntrada) : null,
              horaSalida: r.horaSalida ? new Date(r.horaSalida) : null,
            }));
            setRecords(parsedRecords);
            setAcumuladoPorParte(data.acumuladoPorParte || {});
            setContadorCarritos(data.contadorCarritos || {});
            setTurnoActual(data.turnoActual);
            setHistorialTurnos(data.historialTurnos || []);
          }
        }
      } catch (err) {
        console.error("Error al cargar estado del backend. Se requiere conexión local.", err);
      } finally {
        setIsStateLoaded(true);
      }
    };
    fetchDryingState();
  }, []);

  // Actualizar turno periódicamente — guarda snapshot antes de limpiar
  useEffect(() => {
    if (!isStateLoaded) return;
    const interval = setInterval(() => {
      const nuevoTurno = getTurnoActual();
      if (nuevoTurno !== turnoActual) {
        // Guardar snapshot del turno que termina
        const snapshot = {
          turno: turnoActual,
          fechaCierre: new Date().toISOString(),
          acumuladoPorParte,
          contadorCarritos,
          totalCarritos: Object.values(contadorCarritos).reduce((a, b) => a + b, 0),
        };
        setHistorialTurnos(prev => [snapshot, ...prev]);
        showToast(`⏰ Cambio de turno: iniciando turno ${nuevoTurno}. Acumuladores guardados y reiniciados.`, 'warning', 8000);
        setTurnoActual(nuevoTurno);
        setAcumuladoPorParte({});
        setContadorCarritos({});
      }
    }, 60000);
    return () => clearInterval(interval);
  }, [turnoActual, isStateLoaded, acumuladoPorParte, contadorCarritos]);

  // Sincronizar hacia el backend con debounce de 1s para no saturar en cada render
  useEffect(() => {
    if (!isStateLoaded) return; // Evita borrar el servidor si la app apenas está abriendo

    const timer = setTimeout(() => {
      apiFetch("/drying-room/state", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          records,
          acumuladoPorParte,
          contadorCarritos,
          turnoActual,
          historialTurnos,
        })
      }).catch(err => console.error("Error guardando el estado en el backend:", err));
    }, 1000); // debounce: espera 1s de inactividad antes de guardar

    return () => clearTimeout(timer);
  }, [records, acumuladoPorParte, contadorCarritos, turnoActual, historialTurnos, isStateLoaded]);

  // Referencia para acceder a la última versión de la función en el setTimeout
  const handleScanRef = useRef();

  const handleScan = (e, overrideCodigo = null, overrideMode = null) => {
    if (e) e.preventDefault();
    const codigo = (overrideCodigo || qrCode).trim().toUpperCase();
    if (!codigo) return;

    const partInfo = partData[codigo];
    if (!partInfo) {
      showToast(`Parte "${codigo}" no registrada en la base de datos.`, 'error');
      if (!overrideCodigo) setQrCode('');
      return;
    }

    const currentMode = overrideMode || scanMode;
    const qtyNum = Number(partInfo.qtu) || 0;
    const ahora = new Date();

    if (currentMode === 'ENTRADA') {
      // Lógica de ENTRADA
      // #2 — ID único basado en timestamp
      const nuevoId = generarIdCarrito();
      const currentCount = (contadorCarritos[codigo] || 0) + 1;
      const currentAcum = (acumuladoPorParte[codigo] || 0) + qtyNum;

      setContadorCarritos({ ...contadorCarritos, [codigo]: currentCount });
      setAcumuladoPorParte({ ...acumuladoPorParte, [codigo]: currentAcum });

      const newRecord = {
        idCarrito: nuevoId,
        numeroParte: codigo,
        descripcion: partInfo.descripcion,
        maquina: partInfo.linea,
        qty: qtyNum,
        acumulado: currentAcum,
        turno: turnoActual,
        estado: 'EN SECADO',
        horaEntrada: ahora,
        horaSalida: null,
        tiempoMinutos: null
      };
      setRecords([newRecord, ...records]);
      // #5 — Toast de confirmación de entrada
      showToast(`✅ ENTRADA: ${codigo} — ${qtyNum} piezas`, 'success', 2500);

    } else {
      // Lógica de SALIDA (FIFO)
      const index = [...records].reverse().findIndex(r => r.numeroParte === codigo && r.estado === 'EN SECADO');

      if (index === -1) {
        showToast(`No hay carritos de "${codigo}" en secado actualmente.`, 'error');
      } else {
        const realIndex = records.length - 1 - index;
        const tiempoMin = parseFloat(((ahora - new Date(records[realIndex].horaEntrada)) / 60000).toFixed(1));

        // ── Calcular promedio histórico de tiempoMinutos para este número de parte ──
        const historicos = records.filter(
          (r, i) => i !== realIndex && r.numeroParte === codigo && r.estado === 'FINALIZADO' && r.tiempoMinutos != null
        );
        const promedio = historicos.length > 0
          ? historicos.reduce((s, r) => s + parseFloat(r.tiempoMinutos), 0) / historicos.length
          : null;

        // ── Detectar salida anticipada (≥ 10 min antes del promedio) ──
        const earlyExit = promedio !== null && (promedio - tiempoMin) >= 10;
        if (earlyExit) {
          showToast(
            `⚠️ SALIDA ANTICIPADA: ${codigo}\nTiempo: ${tiempoMin} min — Promedio histórico: ${promedio.toFixed(1)} min\nSalida ${(promedio - tiempoMin).toFixed(1)} min antes de lo normal.`,
            'warning',
            8000
          );
        }

        // #1 — Actualización inmutable (sin mutar el objeto original)
        const updatedRecords = records.map((r, i) =>
          i === realIndex
            ? { ...r, estado: 'FINALIZADO', horaSalida: ahora, tiempoMinutos: tiempoMin, earlyExit }
            : r
        );
        setRecords(updatedRecords);
        // #5 — Toast de confirmación de salida
        if (!earlyExit) {
          showToast(`📤 SALIDA: ${codigo} — ${tiempoMin} min en secado`, 'info', 2500);
        }
      }
    }
    if (!overrideCodigo) setQrCode('');
  };

  // Actualizar referencia de handleScan en cada renderizado
  useEffect(() => {
    handleScanRef.current = handleScan;
  });

  // Handler para el éxito del escáner web
  const handleWebScanSuccess = (decodedText) => {
    setIsScannerOpen(false); // Cerrar el modal

    // Extraer número de parte usando lógica similar a la del bot
    let extractedPart = decodedText.trim().toUpperCase();
    const match = extractedPart.match(/(?:PART\s*)?NUMBER\s*[:\|]?\s*([A-Z0-9]{5,20})/i);
    if (match) {
      extractedPart = match[1];
    }

    if (handleScanRef.current) {
      handleScanRef.current(null, extractedPart);
    }
  };

  // NUEVO: Polling de la cola de acciones de Telegram (cada 3 segundos)
  useEffect(() => {
    if (!isStateLoaded) return;
    const interval = setInterval(async () => {
      try {
        const res = await apiFetch("/telegram-queue");
        if (res.ok) {
          const data = await res.json();
          if (data.actions && data.actions.length > 0) {
            const act = data.actions[0];
            // Remover la acción procesada
            await apiFetch("/telegram-queue/clear", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ actions: data.actions.slice(1) })
            });
            // Ejecutar la acción
            if (handleScanRef.current) {
              // Pequeño retardo visual para que parezca que "llegó"
              setTimeout(() => {
                showToast(`🤖 Comando de Telegram recibido: ${act.action} - ${act.codigo}`, 'info', 3000);
                handleScanRef.current(null, act.codigo, act.action);
              }, 500);
            }
          }
        }
      } catch (err) {
        // Ignorar errores de red temporales
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [isStateLoaded]);

  // Auto-submit (Enter automático) tras detectar que el escáner terminó de escribir
  useEffect(() => {
    if (qrCode.trim() !== '') {
      const timer = setTimeout(() => {
        if (handleScanRef.current) handleScanRef.current();
      }, 400); // 400ms de inactividad disparan el enter automático
      return () => clearTimeout(timer);
    }
  }, [qrCode]);

  // Funciones seguras para formatear fechas (evitan crasheos si el dato es un string o inválido)
  const formatDate = (dateVal) => {
    if (!dateVal) return '-';
    const d = new Date(dateVal);
    return isNaN(d.getTime()) ? '-' : d.toLocaleDateString();
  };

  const formatTime = (dateVal) => {
    if (!dateVal) return '-';
    const d = new Date(dateVal);
    return isNaN(d.getTime()) ? '-' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };


  const exportarCSV = () => {
    if (datosFiltrados.length === 0) { showToast('No hay datos para exportar.', 'warning'); return; }
    const cabeceras = ['ID_Carrito', 'N°_Parte', 'Descripción', 'Máquina', 'Cantidad', 'Acumulado', 'Turno', 'Estado', 'Hora_Entrada', 'Hora_Salida', 'Tiempo_Minutos'];
    const lineas = datosFiltrados.map(r => {
      // Para el CSV, calcular tiempo real si todavía está en secado
      const tMin = r.tiempoMinutos || (r.estado === 'EN SECADO' && r.horaEntrada
        ? ((Date.now() - new Date(r.horaEntrada)) / 60000).toFixed(1)
        : '');
      return `${r.idCarrito},${r.numeroParte},"${r.descripcion}",${r.maquina},${r.qty},${r.acumulado},${r.turno},${r.estado},${formatTime(r.horaEntrada)},${formatTime(r.horaSalida)},${tMin}`;
    });
    const blob = new Blob([cabeceras.join(',') + '\n' + lineas.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Reporte_Secado_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    showToast(`${datosFiltrados.length} registros exportados.`, 'success');
  };

  // #11 — Resetear estado del cuarto de secado manualmente
  const handleReset = async () => {
    const ok = await requestConfirm({
      title: '⚠️ Resetear cuarto de secado',
      message: 'Se borrarán TODOS los registros activos, el historial y los acumuladores del turno actual. Esta acción no se puede deshacer.',
      confirmText: 'Sí, resetear todo',
      danger: true,
    });
    if (!ok) return;
    // Segunda confirmación por seguridad
    const ok2 = await requestConfirm({
      title: 'Confirmar reset definitivo',
      message: '¿Estás completamente seguro? Los datos se perderán permanentemente.',
      confirmText: 'Confirmar reset',
      danger: true,
    });
    if (!ok2) return;

    setRecords([]);
    setAcumuladoPorParte({});
    setContadorCarritos({});
    setHistorialTurnos([]);
    // Sincronizar limpieza al backend
    apiFetch('/drying-room/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        records: [],
        acumuladoPorParte: {},
        contadorCarritos: {},
        turnoActual,
        historialTurnos: [],
      })
    }).catch(err => console.error('Error al resetear estado en backend:', err));
    showToast('Estado del cuarto de secado reseteado correctamente.', 'success');
  };

  // Preparación de datos para la vista
  const recordsActivos = records.filter(r => r.estado === 'EN SECADO');
  const recordsHistorial = records.filter(r => r.estado === 'FINALIZADO');
  const datosVista = viendoHistorial ? recordsHistorial : recordsActivos;

  // KPIs del turno actual únicamente
  const entradasTurnoActual = records.filter(r => r.turno === turnoActual);
  const salidasTurnoActual  = recordsHistorial.filter(r => r.turno === turnoActual);

  // Contar cuántos carritos se quedaron del turno anterior
  const carritosTurnoAnterior = recordsActivos.filter(r => r.turno !== turnoActual).length;

  // Contar carritos vencidos (EN SECADO y superaron el tiempo máximo)
  const now = Date.now();
  const carritosVencidos = maxDryingMins > 0
    ? recordsActivos.filter(r => r.horaEntrada && (now - new Date(r.horaEntrada)) / 60000 >= maxDryingMins).length
    : 0;

  const datosFiltrados = datosVista.filter(r => {
    if (filtroParte && (!r.numeroParte || !r.numeroParte.includes(filtroParte.toUpperCase()))) return false;
    if (filtroMaquina !== 'TODAS' && r.maquina !== filtroMaquina) return false;
    if (filtroFecha) {
      const d = r.horaEntrada ? new Date(r.horaEntrada) : null;
      if (!d || isNaN(d.getTime())) return false;
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      if (`${yyyy}-${mm}-${dd}` !== filtroFecha) return false;
    }
    return true;
  });

  const maquinasUnicas = ['TODAS', ...new Set(Object.values(partData || {}).map(p => p?.linea).filter(Boolean))];

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      {/* Modal de confirmación */}
      {confirmModal}

      {/* Header */}
      <div className="max-w-[1400px] mx-auto flex flex-wrap justify-between items-center gap-4 mb-6 bg-white p-5 rounded-2xl shadow-sm border border-slate-200">
        <div className="flex items-center gap-4">
          <span className="text-3xl">♨️</span>
          <div>
            <h2 className="text-xl md:text-2xl font-bold text-slate-800">Control Cuarto de Secado</h2>
            <p className="text-sm font-bold text-blue-600 tracking-wide uppercase mt-1">Turno: {turnoActual}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {/* Configuración de tiempo máximo en secado */}
          <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            <span className="text-amber-600 text-sm font-semibold whitespace-nowrap">⏰ Máx. secado:</span>
            <input
              type="number"
              min="0"
              value={maxDryingMins}
              onChange={(e) => setMaxDryingMins(Number(e.target.value))}
              title="Minutos máximos en secado. 0 = desactivado."
              className="w-16 text-center border border-amber-300 rounded-md p-1 text-sm font-bold text-amber-800 bg-white outline-none focus:ring-2 focus:ring-amber-400"
            />
            <span className="text-amber-600 text-sm font-semibold">min</span>
          </div>
          {/* #11 — Botón de reset */}
          <button
            type="button"
            onClick={handleReset}
            title="Resetear todo el estado del cuarto de secado"
            className="bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 px-4 py-2 rounded-lg font-semibold text-sm transition-colors flex items-center gap-2"
          >
            🗑️ Resetear
          </button>
          <button type="button" onClick={() => goBack()} className="hidden md:block bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800 px-5 py-2 rounded-lg font-semibold transition-colors">
            Volver al Menú
          </button>
        </div>
      </div>

      {/* Tarjetas de Estadísticas */}
      <div className="max-w-[1400px] mx-auto grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 flex items-center gap-5 hover:shadow-md transition-shadow">
          <div className="w-14 h-14 rounded-2xl bg-orange-100 flex items-center justify-center text-2xl shadow-inner">🧱</div>
          <div>
            <p className="text-slate-500 text-sm font-semibold uppercase tracking-wider mb-1">En Secado</p>
            <p className="text-3xl font-extrabold text-slate-800">{recordsActivos.length} <span className="text-sm font-normal text-slate-400">carritos</span></p>
            {carritosTurnoAnterior > 0 && (
              <p className="text-xs font-bold text-red-500 mt-1">⚠️ {carritosTurnoAnterior} rezago{carritosTurnoAnterior !== 1 ? 's' : ''}</p>
            )}
          </div>
        </div>

        {/* KPI: Vencidos */}
        <div className={`rounded-2xl p-6 shadow-sm border flex items-center gap-5 hover:shadow-md transition-shadow ${carritosVencidos > 0 ? 'bg-red-50 border-red-300 animate-pulse' : 'bg-white border-slate-200'
          }`}>
          <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-2xl shadow-inner ${carritosVencidos > 0 ? 'bg-red-200' : 'bg-slate-100'
            }`}>⏰</div>
          <div>
            <p className={`text-sm font-semibold uppercase tracking-wider mb-1 ${carritosVencidos > 0 ? 'text-red-600' : 'text-slate-500'
              }`}>Tiempo Vencido</p>
            <p className={`text-3xl font-extrabold ${carritosVencidos > 0 ? 'text-red-700' : 'text-slate-400'
              }`}>{carritosVencidos} <span className="text-sm font-normal">carritos</span></p>
            {maxDryingMins === 0 && <p className="text-xs text-slate-400 mt-1">Alerta desactivada</p>}
          </div>
        </div>

        <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 flex items-center gap-5 hover:shadow-md transition-shadow">
          <div className="w-14 h-14 rounded-2xl bg-green-100 flex items-center justify-center text-2xl shadow-inner">📥</div>
          <div>
            <p className="text-slate-500 text-sm font-semibold uppercase tracking-wider mb-1">Entradas Totales</p>
            <p className="text-3xl font-extrabold text-slate-800">{entradasTurnoActual.length} <span className="text-sm font-normal text-slate-400">lotes</span></p>
            <p className="text-xs text-slate-400 mt-0.5">Turno {turnoActual}</p>
          </div>
        </div>
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 flex items-center gap-5 hover:shadow-md transition-shadow">
          <div className="w-14 h-14 rounded-2xl bg-blue-100 flex items-center justify-center text-2xl shadow-inner">📤</div>
          <div>
            <p className="text-slate-500 text-sm font-semibold uppercase tracking-wider mb-1">Salidas Completadas</p>
            <p className="text-3xl font-extrabold text-slate-800">{salidasTurnoActual.length} <span className="text-sm font-normal text-slate-400">lotes</span></p>
            <p className="text-xs text-slate-400 mt-0.5">Turno {turnoActual}</p>
          </div>
        </div>
      </div>

      {/* Controles de Escaneo */}
      <div className={`max-w-[1400px] mx-auto bg-white rounded-2xl shadow-sm border-2 p-8 mb-8 flex flex-col items-center relative overflow-hidden transition-colors duration-300 ${scanMode === 'ENTRADA' ? 'border-green-200' : 'border-red-200'}`}>
        {/* Background Highlight (Línea superior de color) */}
        <div className={`absolute top-0 left-0 w-full h-2 ${scanMode === 'ENTRADA' ? 'bg-green-500' : 'bg-red-500'}`}></div>

        <h3 className="font-bold text-slate-700 mb-6 tracking-wide uppercase text-sm flex items-center gap-2">
          <span className="text-xl">📻</span> Modo de Operación Activo
        </h3>

        {/* Segmented Control */}
        <div className="flex bg-slate-100 p-1 rounded-xl mb-8 w-full max-w-md">
          <button
            type="button"
            onClick={() => setScanMode('ENTRADA')}
            className={`flex-1 py-3 rounded-lg font-bold text-sm transition-all duration-200 flex justify-center items-center gap-2 ${scanMode === 'ENTRADA' ? 'bg-white shadow-md text-green-600 scale-[1.02]' : 'text-slate-500 hover:bg-slate-200'}`}
          >
            🟢 REGISTRAR ENTRADA
          </button>
          <button
            type="button"
            onClick={() => setScanMode('SALIDA')}
            className={`flex-1 py-3 rounded-lg font-bold text-sm transition-all duration-200 flex justify-center items-center gap-2 ${scanMode === 'SALIDA' ? 'bg-white shadow-md text-red-600 scale-[1.02]' : 'text-slate-500 hover:bg-slate-200'}`}
          >
            🔴 REGISTRAR SALIDA
          </button>
        </div>

        <form onSubmit={handleScan} className="w-full max-w-3xl flex flex-col items-center">
          <div className="flex flex-col md:flex-row w-full gap-4 relative">
            <div className="relative flex-1">
              <span className="absolute inset-y-0 left-6 flex items-center text-3xl text-slate-300 pointer-events-none">
                {scanMode === 'ENTRADA' ? '📥' : '📤'}
              </span>
              <input
                type="text"
                placeholder="ESCANEAR CÓDIGO (N° PARTE)"
                value={qrCode}
                onChange={(e) => setQrCode(e.target.value)}
                ref={inputRef}
                className={`w-full h-full text-center text-2xl md:text-3xl font-mono pl-16 p-6 bg-slate-50 border-2 border-slate-200 rounded-2xl focus:bg-white outline-none transition-all placeholder:text-slate-300 ${scanMode === 'ENTRADA' ? 'focus:border-green-500 focus:ring-4 focus:ring-green-500/20' : 'focus:border-red-500 focus:ring-4 focus:ring-red-500/20'}`}
              />
            </div>
            
            <button
              type="button"
              onClick={() => setIsScannerOpen(true)}
              className="px-8 py-5 bg-slate-800 text-white font-bold text-lg md:text-xl rounded-2xl hover:bg-slate-700 transition-transform active:scale-95 flex lg:hidden items-center justify-center gap-3 shadow-lg whitespace-nowrap"
            >
              <span className="text-2xl">📷</span> <span>Escanear QR</span>
            </button>
          </div>
          <p className="text-center text-slate-400 mt-4 text-sm font-medium">Usa la pistola física de código de barras<span className="lg:hidden"> o escanea con la cámara del dispositivo</span>.</p>
        </form>
      </div>

      {isScannerOpen && (
        <WebQRScanner 
          onScanSuccess={handleWebScanSuccess} 
          onClose={() => setIsScannerOpen(false)} 
        />
      )}

      {/* Sección Tabla con Filtros */}
      <div className="max-w-[1400px] mx-auto bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">

        {/* Barra de Filtros */}
        <div className="p-5 bg-slate-50 border-b border-slate-200 flex flex-wrap gap-4 items-center justify-between">
          <div className="flex flex-wrap items-center gap-4">
            <h3 className="font-bold text-slate-800 text-lg mr-4">
              {viendoHistorial ? '📜 Historial de Finalizados' : '🧱 Moldes Activos en Secado'}
            </h3>

            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-slate-500">Fecha:</label>
              <input
                type="date"
                value={filtroFecha}
                onChange={(e) => setFiltroFecha(e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>

            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-slate-500">N° Parte:</label>
              <input
                type="text"
                value={filtroParte}
                onChange={(e) => setFiltroParte(e.target.value)}
                placeholder="Buscar..."
                className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>

            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-slate-500">Máquina:</label>
              <select
                value={filtroMaquina}
                onChange={(e) => setFiltroMaquina(e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              >
                {maquinasUnicas.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>

            {(filtroParte || filtroMaquina !== 'TODAS' || filtroFecha) && (
              <button type="button" onClick={() => { setFiltroParte(''); setFiltroMaquina('TODAS'); setFiltroFecha(''); }} className="text-sm text-blue-600 hover:underline">Limpiar Filtros</button>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button type="button" onClick={exportarCSV} className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium text-sm transition-colors flex gap-2 items-center">
              📤 Exportar CSV
            </button>
            <button type="button" onClick={() => setViendoHistorial(!viendoHistorial)} className="bg-slate-800 hover:bg-slate-900 text-white px-4 py-2 rounded-lg font-medium text-sm transition-colors">
              {viendoHistorial ? 'Ver Activos' : 'Ver Historial'}
            </button>
          </div>
        </div>

        {/* Contenedor desplazable para la tabla */}
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse whitespace-nowrap">
            <thead>
              <tr className="bg-white text-slate-500 text-xs uppercase tracking-wider border-b border-slate-200">
                <th className="p-4 font-medium text-center">Fecha</th>
                <th className="p-4 font-medium text-center">Turno</th>
                <th className="p-4 font-medium text-center">N° Parte</th>
                <th className="p-4 font-medium text-left">Descripción</th>
                <th className="p-4 font-medium text-center">Máquina</th>
                <th className="p-4 font-medium text-center">Qty</th>
                <th className="p-4 font-medium text-center">Estado</th>
                <th className="p-4 font-medium text-center">Entrada</th>
                <th className="p-4 font-medium text-center">Salida</th>
                <th className="p-4 font-medium text-center">Tiempo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {datosFiltrados.map((row, idx) => {
                const minsEnSecado = row.horaEntrada && row.estado === 'EN SECADO'
                  ? (Date.now() - new Date(row.horaEntrada)) / 60000
                  : null;
                const esVencido = maxDryingMins > 0 && minsEnSecado !== null && minsEnSecado >= maxDryingMins;
                const esRezago = row.turno !== turnoActual && row.estado === 'EN SECADO';
                return (
                  <tr key={row.idCarrito || idx} className={`hover:bg-slate-50 transition-colors ${esVencido ? 'bg-red-100 border-l-4 border-l-red-500' : esRezago ? 'bg-red-50/50' : ''
                    }`}>
                    <td className="p-4 text-center text-slate-500 text-sm">{formatDate(row.horaEntrada)}</td>
                    <td className="p-4 text-center font-semibold text-slate-500 text-xs">
                      {row.turno}
                      {esVencido && (
                        <span className="block text-[10px] text-red-700 font-bold mt-1">🔴 VENCIDO</span>
                      )}
                      {!esVencido && esRezago && (
                        <span className="block text-[10px] text-red-600 font-bold mt-1">⚠️ REZAGO</span>
                      )}
                    </td>
                    <td className="p-4 text-center text-slate-700 font-mono text-sm">{row.numeroParte}</td>
                    <td className="p-4 text-left text-slate-600 text-sm truncate max-w-[150px]" title={row.descripcion}>{row.descripcion}</td>
                    <td className="p-4 text-center text-slate-600 text-sm">{row.maquina}</td>
                    <td className="p-4 text-center font-medium text-blue-600">{row.qty}</td>
                    <td className="p-4 flex justify-center">
                      <span className={`px-3 py-1 rounded-full text-xs font-bold flex items-center w-max gap-1.5 ${row.estado === 'EN SECADO' ? 'bg-orange-100 text-orange-700' : 'bg-green-100 text-green-700'}`}>
                        {row.estado === 'EN SECADO' && <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse"></span>}
                        {row.estado === 'FINALIZADO' && <span className="w-2 h-2 rounded-full bg-green-500"></span>}
                        {row.estado}
                      </span>
                    </td>
                    <td className="p-4 text-center text-slate-500 text-sm">{formatTime(row.horaEntrada)}</td>
                    <td className="p-4 text-center text-slate-500 text-sm">{formatTime(row.horaSalida)}</td>
                    {/* #8 — Tiempo en vivo para carritos EN SECADO */}
                    <td className="p-4 text-slate-500 text-center font-mono text-sm">
                      {row.tiempoMinutos
                        ? `${row.tiempoMinutos} min`
                        : row.estado === 'EN SECADO' && row.horaEntrada
                          ? <LiveTimer horaEntrada={row.horaEntrada} maxMins={maxDryingMins} />
                          : '-'}
                    </td>
                  </tr>
                );
              })}
              {datosFiltrados.length === 0 && (
                <tr>
                  <td colSpan="12" className="p-12 text-center text-slate-400">
                    {viendoHistorial ? 'No hay registros en el historial.' : 'No hay carritos en secado actualmente.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── PANEL DE ANÁLISIS DE TIEMPOS ── */}
      <div className="max-w-[1400px] mx-auto mt-8">
        <button
          type="button"
          onClick={() => setViendoAnalisis(v => !v)}
          className="w-full flex items-center justify-between bg-white border border-slate-200 rounded-2xl px-6 py-4 shadow-sm hover:shadow-md transition-shadow group"
        >
          <div className="flex items-center gap-3">
            <span className="text-2xl">🔬</span>
            <div className="text-left">
              <p className="font-bold text-slate-800 text-lg">Análisis de Tiempos por Parte</p>
              <p className="text-slate-400 text-sm">Promedio, mínimo, máximo y detección de salidas anticipadas</p>
            </div>
          </div>
          <span className={`text-slate-400 text-xl transition-transform duration-200 ${viendoAnalisis ? 'rotate-180' : ''}`}>▼</span>
        </button>

        {viendoAnalisis && <TimeAnalysisPanel records={records} />}
      </div>

    </div>
  );
}

// ─── Panel de análisis de tiempos de secado ─────────────────────────────────
function TimeAnalysisPanel({ records }) {
  // Solo registros FINALIZADOS con tiempoMinutos válido
  const finished = records.filter(
    r => r.estado === 'FINALIZADO' && r.tiempoMinutos != null && !isNaN(parseFloat(r.tiempoMinutos))
  );

  if (finished.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-b-2xl p-10 text-center text-slate-400 flex flex-col items-center gap-3">
        <span className="text-4xl">📊</span>
        <p className="font-semibold">Sin datos finalizados aún.</p>
        <p className="text-sm">El análisis aparece en cuanto haya carritos con salida registrada.</p>
      </div>
    );
  }

  // Agrupar por numeroParte
  const statsMap = {};
  for (const r of finished) {
    const t = parseFloat(r.tiempoMinutos);
    const pn = r.numeroParte;
    if (!statsMap[pn]) {
      statsMap[pn] = { part: pn, desc: r.descripcion, times: [], earlyCount: 0 };
    }
    statsMap[pn].times.push(t);
    if (r.earlyExit) statsMap[pn].earlyCount += 1;
  }

  const stats = Object.values(statsMap).map(s => {
    const sorted = [...s.times].sort((a, b) => a - b);
    const avg = s.times.reduce((a, b) => a + b, 0) / s.times.length;
    const min = sorted[0];
    const max = sorted[sorted.length - 1];
    const stdDev = Math.sqrt(s.times.reduce((acc, t) => acc + Math.pow(t - avg, 2), 0) / s.times.length);
    return { ...s, avg, min, max, stdDev, samples: s.times.length };
  }).sort((a, b) => b.samples - a.samples);

  // Semáforo: variabilidad baja (<10min stddev) = verde, media = amarillo, alta = rojo
  const getVariabilityColor = (stdDev) => {
    if (stdDev < 5) return { bg: 'bg-green-100', text: 'text-green-700', label: 'Estable' };
    if (stdDev < 15) return { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Variable' };
    return { bg: 'bg-red-100', text: 'text-red-700', label: 'Inestable' };
  };

  return (
    <div className="bg-white border border-t-0 border-slate-200 rounded-b-2xl overflow-hidden shadow-sm">
      {/* Resumen global */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-0 border-b border-slate-100">
        {[
          { label: 'Partes analizadas', value: stats.length, icon: '🔬' },
          { label: 'Total muestras', value: finished.length, icon: '📋' },
          { label: 'Promedio global', value: `${(finished.reduce((s, r) => s + parseFloat(r.tiempoMinutos), 0) / finished.length).toFixed(1)} min`, icon: '⏱' },
          { label: 'Salidas anticipadas', value: finished.filter(r => r.earlyExit).length, icon: '⚠️' },
        ].map((kpi, i) => (
          <div key={i} className="p-5 border-r border-slate-100 last:border-r-0">
            <p className="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">{kpi.icon} {kpi.label}</p>
            <p className="text-2xl font-extrabold text-slate-800">{kpi.value}</p>
          </div>
        ))}
      </div>

      {/* Tabla por parte */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm whitespace-nowrap">
          <thead>
            <tr className="bg-slate-50 text-slate-400 text-xs uppercase tracking-wider border-b border-slate-100">
              <th className="px-5 py-3 text-left font-medium">N° Parte</th>
              <th className="px-5 py-3 text-left font-medium">Descripción</th>
              <th className="px-5 py-3 text-center font-medium">Muestras</th>
              <th className="px-5 py-3 text-center font-medium">Mínimo</th>
              <th className="px-5 py-3 text-center font-medium">Promedio</th>
              <th className="px-5 py-3 text-center font-medium">Máximo</th>
              <th className="px-5 py-3 text-center font-medium">Desv. Est.</th>
              <th className="px-5 py-3 text-center font-medium">Estabilidad</th>
              <th className="px-5 py-3 text-center font-medium">⚠️ Anticipadas</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {stats.map(s => {
              const vc = getVariabilityColor(s.stdDev);
              return (
                <tr key={s.part} className="hover:bg-slate-50 transition-colors">
                  <td className="px-5 py-4 font-mono font-bold text-slate-800">{s.part}</td>
                  <td className="px-5 py-4 text-slate-500 text-sm max-w-[180px] truncate" title={s.desc}>{s.desc}</td>
                  <td className="px-5 py-4 text-center font-medium text-slate-600">{s.samples}</td>
                  <td className="px-5 py-4 text-center font-semibold text-green-600">{s.min.toFixed(1)} min</td>
                  <td className="px-5 py-4 text-center">
                    <span className="font-extrabold text-slate-900 text-base">{s.avg.toFixed(1)}</span>
                    <span className="text-slate-400 text-xs"> min</span>
                  </td>
                  <td className="px-5 py-4 text-center font-semibold text-orange-600">{s.max.toFixed(1)} min</td>
                  <td className="px-5 py-4 text-center font-medium text-slate-500">±{s.stdDev.toFixed(1)} min</td>
                  <td className="px-5 py-4 text-center">
                    <span className={`px-3 py-1 rounded-full text-xs font-bold ${vc.bg} ${vc.text}`}>{vc.label}</span>
                  </td>
                  <td className="px-5 py-4 text-center">
                    {s.earlyCount > 0
                      ? <span className="px-3 py-1 rounded-full text-xs font-bold bg-red-100 text-red-700">⚠️ {s.earlyCount}</span>
                      : <span className="text-slate-300 text-xs">—</span>
                    }
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Leyenda */}
      <div className="p-4 bg-slate-50 border-t border-slate-100 flex flex-wrap gap-4 text-xs text-slate-500">
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-green-400 inline-block"></span> Estable: desv. &lt; 5 min</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-yellow-400 inline-block"></span> Variable: desv. 5–15 min</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-red-400 inline-block"></span> Inestable: desv. &gt; 15 min</span>
        <span className="flex items-center gap-1.5">⚠️ Anticipada: salida ≥ 10 min antes del promedio histórico</span>
      </div>
    </div>
  );
}