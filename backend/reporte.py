"""
Reporte de Producción (formato hoja OCTUBRE del Excel de producción).

Fuentes:
  - ENTRADAS al cuarto de secado  -> Producción TTL por fecha/turno/máquina/parte
  - Captura de turno (web)        -> horas, cav/ciclo real, paros, scrap, MTTO, comentario
  - BOM (importado del Excel)     -> descripción, cliente, ID, peso, cavidades, ciclo, tipo

Los registros de producción se guardan en produccion_log.json (no se borran con el
"Resetear" del cuarto de secado ni con la depuración de 30 días).
"""
import io
import json
import os
import re
import threading
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "produccion_log.json")
CAPT_FILE = os.path.join(BASE_DIR, "capturas_turno.json")
BOM_FILE = os.path.join(BASE_DIR, "bom.json")
PARTS_FILE = os.path.join(BASE_DIR, "data.json")
LABELS_FILE = os.path.join(BASE_DIR, "generated_labels.json")
DRYING_FILE = os.path.join(BASE_DIR, "drying_state.json")
TZ = ZoneInfo("America/Mexico_City")

_lock = threading.RLock()
router = APIRouter()

# ── Columnas de captura (mismo orden que el Excel) ─────────────────────────────
PAROS = [("cambio_molde", "Cambio de molde"), ("ajustes", "Ajustes"), ("arranque", "Arranque"),
         ("mtto", "MTTO"), ("molde_danado", "Molde dañado"), ("falta_personal", "Falta de personal"),
         ("falta_material", "Falta de material")]
SCRAP = [("falta_llenado", "Falta de llenado"), ("crudas", "Crudas"), ("quebradas", "Quebradas"),
         ("hinchadas", "Hinchadas"), ("arranque", "Arranque"), ("fuera_dimension", "Fuera de dimensión"),
         ("pandeada", "Pandeada"), ("aplastada", "Aplastada por molde")]
MTTO = [("soldar_puerta", "Soldar puerta ejector"), ("estopero", "Estopero"), ("bomba_hid", "Bomba hidráulica"),
        ("motor_hid", "Motor hidráulico"), ("manguera_hid", "Manguera hidráulica"), ("valvula_hid", "Válvula hidráulica"),
        ("reloj", "Reloj"), ("caldera", "Caldera"), ("sensor", "Sensor seguridad"), ("falta_aire", "Falta de aire"),
        ("fuga_aceite", "Fuga de aceite"), ("electrica", "Eléctrica"), ("tolva", "Tolva tapada"), ("extra", "Extra")]


# ── Utilidades de archivo (escritura atómica) ──────────────────────────────────
def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ── Turnos ─────────────────────────────────────────────────────────────────────
def parse_dt(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ)


def turno_de(dt_local: datetime):
    """(fecha_del_turno, 'DIA'|'NOCHE'). La noche que pasa de medianoche pertenece al día anterior."""
    h = dt_local.hour + dt_local.minute / 60
    if 7.5 <= h < 19.5:
        return dt_local.date(), "DIA"
    if h >= 19.5:
        return dt_local.date(), "NOCHE"
    return dt_local.date() - timedelta(days=1), "NOCHE"


def turno_actual():
    return turno_de(datetime.now(TZ))


def weeknum(d: date) -> int:
    """Igual que WEEKNUM() de Excel (semana inicia domingo, 1-ene = semana 1)."""
    jan1 = date(d.year, 1, 1)
    return (d.timetuple().tm_yday + (jan1.isoweekday() % 7) - 1) // 7 + 1


def norm_turno(t: str) -> str:
    t = (t or "").strip().upper()
    return "NOCHE" if t.startswith("N") else "DIA"


def maq_num(v) -> Optional[int]:
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else None


# ── Log de producción ──────────────────────────────────────────────────────────
def registrar_en_log(records: List[Dict[str, Any]]):
    """Upsert de registros del cuarto de secado (entrada y, si existe, salida) en el log permanente."""
    if not records:
        return
    with _lock:
        log = _load(LOG_FILE, {})
        labels = _load(LABELS_FILE, {})
        changed = False
        for r in records:
            cid = r.get("idCarrito")
            if not cid or not r.get("horaEntrada"):
                continue
            prev = log.get(cid, {})
            maq = prev.get("maquina")
            if maq is None:
                lbl = labels.get(cid) or {}
                maq = lbl.get("maquina") or maq_num(r.get("maquina")) or maq_num(lbl.get("linea"))
            hora = r.get("horaEntrada")
            if isinstance(hora, datetime):
                hora = hora.isoformat()
            new = {
                "idCarrito": cid,
                "parte": str(r.get("numeroParte") or "").strip().upper(),
                "qty": int(float(r.get("qty") or 0)),
                "maquina": maq,
                "horaEntrada": hora,
                "horaSalida": r.get("horaSalida") or prev.get("horaSalida"),
                "tiempoMinutos": r.get("tiempoMinutos") if r.get("tiempoMinutos") is not None else prev.get("tiempoMinutos"),
                "estado": r.get("estado") or prev.get("estado"),
            }
            if prev != new:
                log[cid] = new
                changed = True
        if changed:
            _save(LOG_FILE, log)


def _seed_desde_secado():
    st = _load(DRYING_FILE, {})
    registrar_en_log(st.get("records", []))


try:
    _seed_desde_secado()
except Exception as e:  # nunca impedir el arranque
    print(f"[reporte] No se pudo sembrar el log: {e}")


# ── BOM ────────────────────────────────────────────────────────────────────────
def _bom():
    return _load(BOM_FILE, {})


def bom_de(parte: str, bom=None) -> Dict[str, Any]:
    bom = bom if bom is not None else _bom()
    p = str(parte or "").strip().upper()
    if p in bom:
        return bom[p]
    base = re.sub(r"\s*#\s*\d+$", "", p)
    if base in bom:
        return bom[base]
    for k, v in bom.items():  # p.ej. etiqueta "MFZ67190201" vs BOM "MFZ67190201 #6"
        if re.sub(r"\s*#\s*\d+$", "", k) == p:
            return v
    return {}


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, (int, float, str)):
        return v
    return str(v)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@router.post("/bom/import")
async def importar_bom(file: UploadFile = File(...)):
    """Importa el BOM: hoja 'BOM' o la primera hoja con encabezado 'NO. PARTE' en la columna D."""
    import openpyxl
    data = await file.read()
    if file.filename and file.filename.lower().endswith(".json"):
        try:
            out = {str(k).strip().upper(): v for k, v in json.loads(data).items()}
        except Exception as e:
            raise HTTPException(400, f"JSON inválido: {e}")
        with _lock:
            _save(BOM_FILE, out)
        return {"message": f"BOM importado: {len(out)} números de parte.", "total": len(out)}
    # El servidor tiene poca RAM: un libro completo de producción (7+ MB, 100+ hojas) lo tumba.
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(400, "Archivo muy grande para el servidor. En Excel: clic derecho en la hoja BOM → "
                                 "Mover o copiar → (nuevo libro) → Crear una copia, guárdalo y sube ese archivo.")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as e:
        raise HTTPException(400, f"No se pudo leer el Excel: {e}")
    def _tiene_encabezado(hoja):
        for i, r in enumerate(hoja.iter_rows(max_row=30, max_col=6, values_only=True)):
            if len(r) > 3 and str(r[3] or "").strip().upper() in ("NO. PARTE", "품번"):
                return True
        return False
    hojas = (["BOM"] if "BOM" in wb.sheetnames else []) + [n for n in wb.sheetnames if n != "BOM"]
    ws = next((wb[n] for n in hojas if _tiene_encabezado(wb[n])), None)
    if ws is None:
        raise HTTPException(400, "No encontré una hoja con el encabezado 'NO. PARTE' en la columna D.")
    out = {}
    header_found = False
    for row in ws.iter_rows(values_only=True):
        row = list(row) + [None] * 20
        if not header_found:
            if str(row[3] or "").strip().upper() in ("NO. PARTE", "품번"):
                header_found = True
            continue
        parte = row[3]
        if parte in (None, "") or str(parte).strip().upper() in ("NO. PARTE", "품번"):
            continue
        key = str(parte).strip().upper()
        if key in ("AAA", "#N/A", "#VALUE!", "#REF!"):
            continue  # filas de prueba / basura
        # Ciclo: columna R (vigente); si viene en 0 usar las columnas históricas Y, W, V
        ciclo, fuente = None, None
        for idx, col in ((17, "R"), (24, "Y"), (22, "W"), (21, "V")):
            v = _num(row[idx])
            if v and v > 0:
                ciclo, fuente = v, col
                break
        corte = str(row[7] or "").strip().lower() == "cutting"
        out[key] = {
            "linea": _txt(row[1]), "modelo": _txt(row[2]), "descripcion": _txt(row[4]), "cliente": _txt(row[5]),
            "id1": _txt(row[6]), "id2": _txt(row[7]), "resina": _txt(row[8]), "densidad": _num(row[9]),
            "peso": _num(row[10]), "tipo": _txt(row[14]), "molde": _txt(row[15]), "cav": _num(row[16]) or None, "ciclo": ciclo,
            "ciclo_fuente": fuente, "corte": corte,
        }
    if not out:
        raise HTTPException(400, "No encontré filas de BOM (encabezado 'NO. PARTE' en la columna D).")
    conservados = 0
    with _lock:
        prev_bom = _bom()
        # Conservar lo capturado a mano en la pestaña BOM cuando el Excel lo trae vacío
        for k, prev in prev_bom.items():
            if not prev.get("editado"):
                continue
            if k not in out:
                out[k] = prev
                conservados += 1
                continue
            for campo in ("peso", "cav", "ciclo", "densidad"):
                if not out[k].get(campo) and prev.get(campo):
                    out[k][campo] = prev[campo]
                    if campo == "ciclo":
                        out[k]["ciclo_fuente"] = "manual"
                    conservados += 1
            out[k]["editado"] = prev["editado"]
        _save(BOM_FILE, out)
    extra = f" Se conservaron {conservados} dato(s) capturados a mano." if conservados else ""
    nuevas = sincronizar_catalogo()
    if nuevas:
        extra += f" {nuevas} parte(s) nuevas agregadas al Gestor de Partes."
    return {"message": f"BOM importado: {len(out)} números de parte.{extra}", "total": len(out)}


def sincronizar_catalogo() -> int:
    """Agrega al catálogo de etiquetas (data.json) toda parte del BOM que falte. No modifica las existentes."""
    with _lock:
        bom = _bom()
        partes = _load(PARTS_FILE, {})
        nuevas = 0
        for k, v in bom.items():
            if k in partes:
                continue
            partes[k] = {
                "descripcion": str(v.get("descripcion") or ""),
                "linea": "",                                  # la máquina se elige al imprimir
                "id": str(v.get("id2") or ""),
                "qtu": "",                                    # cantidad por etiqueta: capturar en Gestor de Partes
                "linea_lg": str(v.get("linea") or ""),
                "ayuda_visual": "",
            }
            nuevas += 1
        if nuevas:
            _save(PARTS_FILE, partes)
    return nuevas


try:
    sincronizar_catalogo()
except Exception as e:
    print(f"[reporte] No se pudo sincronizar el catálogo: {e}")


@router.post("/parts/sync-bom")
def sync_catalogo():
    n = sincronizar_catalogo()
    return {"message": f"{n} parte(s) del BOM agregadas al catálogo." if n else "El catálogo ya tiene todas las partes del BOM.", "nuevas": n}


@router.get("/bom")
def ver_bom():
    b = _bom()
    return {"total": len(b), "partes": b}


BOM_CAMPOS_TXT = ("linea", "modelo", "descripcion", "cliente", "id1", "id2", "resina", "tipo", "molde")
BOM_CAMPOS_NUM = ("densidad", "peso", "cav", "ciclo")


class BomItem(BaseModel):
    parte: str
    linea: Optional[str] = ""
    modelo: Optional[str] = ""
    descripcion: Optional[str] = ""
    cliente: Optional[str] = ""
    id1: Optional[str] = ""
    id2: Optional[str] = ""
    resina: Optional[str] = ""
    tipo: Optional[str] = ""
    molde: Optional[str] = ""
    densidad: Optional[float] = None
    peso: Optional[float] = None
    cav: Optional[float] = None
    ciclo: Optional[float] = None


@router.put("/bom/{parte}")
def guardar_bom(parte: str, item: BomItem):
    """Crea o edita una parte del BOM. Si item.parte difiere de {parte}, la renombra."""
    original = parte.strip().upper()
    nuevo = (item.parte or original).strip().upper()
    if not nuevo:
        raise HTTPException(400, "El número de parte es obligatorio.")
    with _lock:
        bom = _bom()
        if nuevo != original and nuevo in bom:
            raise HTTPException(400, f"La parte {nuevo} ya existe en el BOM.")
        prev = bom.pop(original, {}) if original in bom else {}
        datos = {**prev}
        for k in BOM_CAMPOS_TXT:
            datos[k] = (getattr(item, k) or "").strip()
        for k in BOM_CAMPOS_NUM:
            v = getattr(item, k)
            datos[k] = v if (v is not None and v > 0) else None
        datos["corte"] = datos.get("id2", "").lower() == "cutting"
        datos["ciclo_fuente"] = "manual" if datos.get("ciclo") != prev.get("ciclo") else prev.get("ciclo_fuente")
        datos["editado"] = datetime.now(TZ).isoformat(timespec="seconds")
        bom[nuevo] = datos
        _save(BOM_FILE, bom)
    sincronizar_catalogo()
    return {"message": f"Parte {nuevo} guardada en el BOM.", "parte": nuevo}


@router.delete("/bom/{parte}")
def borrar_bom(parte: str):
    key = parte.strip().upper()
    with _lock:
        bom = _bom()
        if key not in bom:
            raise HTTPException(404, "La parte no está en el BOM.")
        bom.pop(key)
        _save(BOM_FILE, bom)
    return {"message": f"Parte {key} eliminada del BOM."}


# ── Captura de turno ───────────────────────────────────────────────────────────
class Captura(BaseModel):
    fecha: str                      # YYYY-MM-DD (fecha del turno)
    turno: str                      # DIA | NOCHE
    maquina: int
    parte: str
    horas: Optional[float] = None
    cav_real: Optional[float] = None
    ciclo_real: Optional[float] = None
    prod_manual: Optional[float] = None   # solo si no se escanearon carritos
    cambios_molde: Optional[int] = None
    paros: Dict[str, float] = {}
    scrap: Dict[str, float] = {}
    mtto: Dict[str, float] = {}
    comentario: str = ""


def _ckey(fecha, turno, maq, parte):
    return f"{fecha}|{norm_turno(turno)}|{int(maq)}|{str(parte).strip().upper()}"


def _escaneos(desde: date, hasta: date):
    """Agrupa entradas del log por (fecha, turno, máquina, parte)."""
    log = _load(LOG_FILE, {})
    agg = {}
    for r in log.values():
        dt = parse_dt(r.get("horaEntrada"))
        if not dt:
            continue
        f, t = turno_de(dt)
        if not (desde <= f <= hasta):
            continue
        k = (f.isoformat(), t, r.get("maquina") or 0, r.get("parte"))
        a = agg.setdefault(k, {"qty": 0, "carritos": 0, "en_secado": 0, "tiempos": []})
        a["qty"] += r.get("qty") or 0
        a["carritos"] += 1
        if r.get("estado") == "EN SECADO":
            a["en_secado"] += 1
        if r.get("tiempoMinutos") is not None:
            a["tiempos"].append(float(r["tiempoMinutos"]))
    return agg


def _fila(fecha: str, turno: str, maq: int, parte: str, esc: dict, cap: dict, bom_all: dict) -> dict:
    b = bom_de(parte, bom_all)
    f = date.fromisoformat(fecha)
    peso, cav_bom, ciclo_bom = b.get("peso"), b.get("cav"), b.get("ciclo")
    cav = cap.get("cav_real") if cap.get("cav_real") is not None else cav_bom
    horas = cap.get("horas") if cap.get("horas") is not None else 12.0
    ttl_esc = esc.get("qty", 0)
    ttl = cap.get("prod_manual") if cap.get("prod_manual") is not None else ttl_esc
    scrap = {k: float(cap.get("scrap", {}).get(k) or 0) for k, _ in SCRAP}
    paros = {k: float(cap.get("paros", {}).get(k) or 0) for k, _ in PAROS}
    mtto = {k: float(cap.get("mtto", {}).get(k) or 0) for k, _ in MTTO}
    scrap_ttl = sum(scrap.values())
    buena = ttl - scrap_ttl
    corte = bool(b.get("corte"))
    meta = (3600 / ciclo_bom * cav * horas) if (ciclo_bom and cav and not corte) else 0
    faltan = [] if not b else [n for n, v in (("peso", peso), ("cavidades", cav_bom), ("ciclo", ciclo_bom))
                               if not v and not (corte and n != "peso")]
    tiempos = esc.get("tiempos") or []
    return {
        "fecha": fecha, "mes": f.month, "semana": weeknum(f), "turno": turno, "maquina": maq, "parte": parte,
        "descripcion": b.get("descripcion", ""), "cliente": b.get("cliente", ""), "id1": b.get("id1", ""),
        "id2": b.get("id2", ""), "peso": peso, "cav_bom": cav_bom, "ciclo_bom": ciclo_bom, "tipo": b.get("tipo"),
        "molde": b.get("molde"), "resina": b.get("resina"), "densidad": b.get("densidad"),
        "cav_real": cav, "ciclo_real": cap.get("ciclo_real"), "horas": horas,
        "paros": paros, "paro_ttl": sum(paros.values()), "scrap": scrap, "scrap_ttl": scrap_ttl,
        "mtto": mtto, "mtto_ttl": sum(mtto.values()), "cambios_molde": cap.get("cambios_molde") or 0,
        "prod_ttl": ttl, "prod_buena": buena, "prod_kg": buena * peso if peso else None,
        "scrap_kg": scrap_ttl * peso if peso else None, "meta": meta,
        "meta_kg": meta * peso if peso else None, "cumplimiento": (buena / meta) if meta else None,
        "scrap_pct": (scrap_ttl / buena) if buena else None, "shot": (ttl / cav) if cav else None,
        "carritos": esc.get("carritos", 0), "en_secado": esc.get("en_secado", 0),
        "secado_prom_min": round(sum(tiempos) / len(tiempos), 1) if tiempos else None,
        "prod_escaneada": ttl_esc, "capturado": bool(cap), "sin_bom": not b, "corte": corte, "faltan": faltan,
        "comentario": cap.get("comentario", ""),
    }


def construir_filas(desde: date, hasta: date, turno: Optional[str] = None) -> List[dict]:
    esc = _escaneos(desde, hasta)
    caps = _load(CAPT_FILE, {})
    bom_all = _bom()
    keys = set()
    for (f, t, m, p) in esc:
        keys.add((f, t, int(m or 0), p))
    for k, c in caps.items():
        f = date.fromisoformat(c["fecha"])
        if desde <= f <= hasta:
            keys.add((c["fecha"], norm_turno(c["turno"]), int(c["maquina"]), c["parte"]))
    filas = []
    for (f, t, m, p) in keys:
        if turno and norm_turno(turno) != t:
            continue
        e = esc.get((f, t, m, p)) or esc.get((f, t, m or None, p)) or {}
        c = caps.get(_ckey(f, t, m, p), {})
        filas.append(_fila(f, t, m, p, e, c, bom_all))
    filas.sort(key=lambda x: (x["fecha"], 0 if x["turno"] == "DIA" else 1, x["maquina"], x["parte"]))
    return filas


def _resumen(filas):
    def tot(fs):
        meta = sum(x["meta"] for x in fs)
        buena = sum(x["prod_buena"] for x in fs)
        buena_con_meta = sum(x["prod_buena"] for x in fs if x["meta"])
        horas = sum(x["horas"] for x in fs)
        paro = sum(x["paro_ttl"] for x in fs)
        scrap = sum(x["scrap_ttl"] for x in fs)
        cb = [x for x in fs if x["ciclo_bom"] and x["ciclo_real"]]
        return {
            "filas": len(fs), "meta": meta, "resultado": buena, "cumplimiento": buena_con_meta / meta if meta else None,
            "sin_meta": sum(1 for x in fs if not x["meta"]),
            "kg": sum(x["prod_kg"] or 0 for x in fs), "prod_ttl": sum(x["prod_ttl"] for x in fs),
            "scrap": scrap, "scrap_pct": scrap / buena if buena else None, "paro_hrs": paro,
            "paro_pct": paro / horas if horas else None, "cambios_molde": sum(x["cambios_molde"] for x in fs),
            "ciclo_meta": sum(x["ciclo_bom"] for x in cb) / len(cb) if cb else None,
            "ciclo_real": sum(x["ciclo_real"] for x in cb) / len(cb) if cb else None,
            "carritos": sum(x["carritos"] for x in fs), "en_secado": sum(x["en_secado"] for x in fs),
            "sin_captura": sum(1 for x in fs if not x["capturado"]),
            "scrap_detalle": {k: sum(x["scrap"][k] for x in fs) for k, _ in SCRAP},
            "paros_detalle": {k: sum(x["paros"][k] for x in fs) for k, _ in PAROS},
        }
    grupos = {}
    for x in filas:
        grupos.setdefault((x["fecha"], x["turno"]), []).append(x)
    return {
        "por_turno": [{"fecha": f, "turno": t, **tot(fs)} for (f, t), fs in sorted(grupos.items())],
        "total": tot(filas),
    }


def _rango(desde: Optional[str], hasta: Optional[str]):
    if desde:
        d = date.fromisoformat(desde)
    else:
        d = turno_actual()[0]
    h = date.fromisoformat(hasta) if hasta else d
    if h < d:
        d, h = h, d
    if (h - d).days > 62:
        raise HTTPException(400, "El rango máximo es de 62 días.")
    return d, h


@router.get("/captura/turno")
def captura_turno(fecha: Optional[str] = None, turno: Optional[str] = None):
    """Filas para la pantalla de captura: lo escaneado + lo ya capturado."""
    ft, tt = turno_actual()
    fecha = fecha or ft.isoformat()
    turno = norm_turno(turno or tt)
    d = date.fromisoformat(fecha)
    filas = construir_filas(d, d, turno)
    caps = _load(CAPT_FILE, {})
    for x in filas:
        x["captura"] = caps.get(_ckey(fecha, turno, x["maquina"], x["parte"]), {})
    return {"fecha": fecha, "turno": turno, "filas": filas, "catalogos": {
        "paros": PAROS, "scrap": SCRAP, "mtto": MTTO}, "resumen": _resumen(filas)["total"]}


@router.put("/captura/turno")
def guardar_captura(c: Captura):
    if c.maquina < 0 or not c.parte.strip():
        raise HTTPException(400, "Máquina y número de parte son obligatorios.")
    date.fromisoformat(c.fecha)
    data = c.model_dump()
    data["turno"] = norm_turno(c.turno)
    data["parte"] = c.parte.strip().upper()
    data["actualizado"] = datetime.now(TZ).isoformat(timespec="seconds")
    with _lock:
        caps = _load(CAPT_FILE, {})
        caps[_ckey(c.fecha, c.turno, c.maquina, c.parte)] = data
        _save(CAPT_FILE, caps)
    return {"message": "Captura guardada"}


@router.delete("/captura/turno")
def borrar_captura(fecha: str, turno: str, maquina: int, parte: str):
    with _lock:
        caps = _load(CAPT_FILE, {})
        caps.pop(_ckey(fecha, turno, maquina, parte), None)
        _save(CAPT_FILE, caps)
    return {"message": "Captura eliminada"}


@router.get("/reporte/produccion")
def reporte(desde: Optional[str] = None, hasta: Optional[str] = None, turno: Optional[str] = None):
    d, h = _rango(desde, hasta)
    filas = construir_filas(d, h, turno)
    return {"desde": d.isoformat(), "hasta": h.isoformat(), "filas": filas, **_resumen(filas)}


# ── Exportación a Excel con el layout de la hoja OCTUBRE ───────────────────────
# (columna, encabezado, función) — mismas columnas B..CH para poder pegar debajo de la fila 6
def _cols():
    c = [
        ("B", "Fecha", lambda x: date.fromisoformat(x["fecha"])), ("C", "Mes", lambda x: x["mes"]),
        ("D", "Semana", lambda x: x["semana"]), ("E", "Turno\n(D/N)", lambda x: x["turno"]),
        ("F", "No. Parte", lambda x: x["parte"]), ("G", "Descripcion", lambda x: x["descripcion"]),
        ("H", "CLIENTE", lambda x: x["cliente"]), ("I", "ID", lambda x: x["id1"]), ("J", "ID", lambda x: x["id2"]),
        ("K", "Peso", lambda x: x["peso"]), ("L", "Cav.\nBOM", lambda x: x["cav_bom"]),
        ("M", "Ciclo", lambda x: x["ciclo_bom"]), ("N", "Type", lambda x: x["tipo"]), ("O", "Maq.", lambda x: x["maquina"]),
        ("P", "Cav. Real", lambda x: x["cav_real"]), ("Q", "Ciclo\nReal", lambda x: x["ciclo_real"]),
        ("R", "Tiempo de Trabajo", lambda x: x["horas"]), ("S", "Tiempo de Paro", lambda x: x["paro_ttl"]),
        ("T", "Produccion\nBuena", lambda x: x["prod_buena"]), ("U", "Scrap", lambda x: x["scrap_ttl"]),
        ("V", "Produccion\nTTL", lambda x: x["prod_ttl"]), ("W", "Prod.\nKg", lambda x: x["prod_kg"]),
        ("X", "Scrap\nKg", lambda x: x["scrap_kg"]), ("Y", "Prod. Meta\nTTL", lambda x: x["meta"]),
        ("Z", "Prod. Meta\nKg", lambda x: x["meta_kg"]), ("AA", "PROD/%", lambda x: x["cumplimiento"]),
    ]
    for col, (k, lbl) in zip(["AC", "AD", "AE", "AF", "AG", "AH", "AI"], PAROS):
        c.append((col, lbl, lambda x, k=k: x["paros"][k] or None))
    c += [("AJ", "Tiempo de Paro", lambda x: x["paro_ttl"]), ("AL", "Mold", lambda x: x["molde"]),
          ("AM", "Tiempo de Trabajo", lambda x: x["horas"])]
    for col, (k, lbl) in zip(["AO", "AP", "AQ", "AR", "AS", "AT", "AU", "AV"], SCRAP):
        c.append((col, lbl.upper(), lambda x, k=k: x["scrap"][k] or None))
    c += [("AW", "Scrap\nTTL", lambda x: x["scrap_ttl"]), ("AX", "SCRAP \n%", lambda x: x["scrap_pct"])]
    for col, (k, lbl) in zip(["AY", "AZ", "BA", "BB", "BC", "BD", "BE", "BF"], SCRAP):
        c.append((col, lbl.upper(), lambda x, k=k: (x["scrap"][k] * x["peso"]) if (x["scrap"][k] and x["peso"]) else None))
    c += [("BG", "Scrap\nTTL", lambda x: x["scrap_kg"]), ("BI", "C/M", lambda x: x["cambios_molde"] or None),
          ("BJ", "C/M", lambda x: x["cumplimiento"])]
    for col, (k, lbl) in zip(["BL", "BM", "BN", "BO", "BP", "BQ", "BR", "BS", "BT", "BU", "BV", "BW", "BX", "BY"], MTTO):
        c.append((col, lbl, lambda x, k=k: x["mtto"][k] or None))
    c += [("BZ", "Total", lambda x: x["mtto_ttl"]), ("CE", "SHOT", lambda x: x["shot"]),
          ("CG", "RESIN Grade", lambda x: x["resina"]), ("CH", "Densidad", lambda x: x["densidad"]),
          ("CJ", "Carritos", lambda x: x["carritos"]), ("CK", "En secado", lambda x: x["en_secado"]),
          ("CL", "Secado prom. (min)", lambda x: x["secado_prom_min"]), ("CM", "Comentario", lambda x: x["comentario"])]
    return c


@router.get("/reporte/produccion.xlsx")
def reporte_excel(desde: Optional[str] = None, hasta: Optional[str] = None, turno: Optional[str] = None):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    d, h = _rango(desde, hasta)
    filas = construir_filas(d, h, turno)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PRODUCCION"
    ws["B2"] = f"Reporte de producción {d.isoformat()} a {h.isoformat()} — copiar desde la fila 7 a la hoja del mes"
    ws["B2"].font = Font(bold=True)
    head = PatternFill("solid", fgColor="DDEBF7")
    for col, lbl, _ in _cols():
        cell = ws[f"{col}6"]
        cell.value = lbl
        cell.font = Font(bold=True)
        cell.fill = head
        cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
    for i, x in enumerate(filas, start=7):
        for col, _, fn in _cols():
            v = fn(x)
            if isinstance(v, float):
                v = round(v, 4)
            ws[f"{col}{i}"] = v
        ws[f"B{i}"].number_format = "yyyy-mm-dd"
        for col in ("AA", "AX", "BJ"):
            ws[f"{col}{i}"].number_format = "0.0%"
    ws.freeze_panes = "G7"
    ws.row_dimensions[6].height = 42
    buf = io.BytesIO()
    wb.save(buf)
    nombre = f"Reporte_Produccion_{d.isoformat()}_{h.isoformat()}.xlsx"
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
