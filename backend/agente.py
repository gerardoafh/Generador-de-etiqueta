"""
Agente analista para el bot de Telegram.

Responde preguntas en lenguaje natural usando herramientas de SOLO LECTURA sobre
producción (reporte), capturas de turno, cuarto de secado y BOM.

Proveedor de IA configurable en backend/.env:
  AI_PROVIDER=anthropic | gemini | openai      (por defecto: el que tenga clave)
  ANTHROPIC_API_KEY=...  /  GEMINI_API_KEY=...  /  OPENAI_API_KEY=...
  AI_MODEL=...                                  (opcional)
Sin clave, el agente queda desactivado y el bot funciona como antes.

Límites (opcionales, en .env):
  AI_MAX_POR_HORA=30     consultas por chat por hora
  AI_MAX_POR_DIA=400     consultas totales por día (tope de costo)
Cada consulta queda registrada en backend/agente_log.jsonl (pregunta, herramientas, tiempo, tokens).
"""
import json
import os
import re
import time
from datetime import date, datetime, timedelta

import requests
from dotenv import load_dotenv

import reporte as R

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

MODELOS = {"anthropic": "claude-sonnet-5-5", "gemini": "gemini-2.5-flash", "openai": "gpt-4.1-mini"}
URLS = {"gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions"}
MAX_PASOS = 6
HIST_TURNOS = 8
HIST_TTL = 45 * 60

_historial = {}   # chat_id -> {"t": epoch, "msgs": [{"role","content"}]}
_uso_chat = {}    # chat_id -> [epochs de la última hora]
_uso_dia = {"fecha": None, "n": 0}
LOG_AGENTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agente_log.jsonl")


class LimiteExcedido(Exception):
    pass


def _limite(nombre, default):
    try:
        return int(os.getenv(nombre) or default)
    except ValueError:
        return default


def verificar_limites(chat_id):
    """Lanza LimiteExcedido si el chat o el día ya alcanzaron su tope."""
    ahora = time.time()
    hoy = date.today().isoformat()
    if _uso_dia["fecha"] != hoy:
        _uso_dia.update(fecha=hoy, n=0)
    if _uso_dia["n"] >= _limite("AI_MAX_POR_DIA", 400):
        raise LimiteExcedido("Se alcanzó el límite diario de consultas del asistente. Se reinicia mañana.")
    recientes = [t for t in _uso_chat.get(chat_id, []) if ahora - t < 3600]
    if len(recientes) >= _limite("AI_MAX_POR_HORA", 30):
        espera = int((3600 - (ahora - recientes[0])) / 60) + 1
        raise LimiteExcedido(f"Llegaste al límite de consultas por hora. Intenta en {espera} min.")
    recientes.append(ahora)
    _uso_chat[chat_id] = recientes
    _uso_dia["n"] += 1


def _registrar(evento):
    try:
        with open(LOG_AGENTE, "a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"[agente] No se pudo escribir el log: {e}")


def error_amigable(e):
    """Traduce errores del proveedor de IA a un mensaje útil para el usuario (y deja el detalle en consola)."""
    t = str(e)
    if " 401" in t or " 403" in t or "invalid x-api-key" in t.lower() or "api key not valid" in t.lower():
        return "⚠️ La clave del asistente de IA no es válida. Avisa al administrador del sistema."
    if " 429" in t or "rate" in t.lower() and "limit" in t.lower():
        return "⏳ El servicio de IA está saturado. Intenta en un minuto."
    if "credit" in t.lower() or "billing" in t.lower() or "quota" in t.lower() or " 402" in t:
        return "⚠️ Se agotó el saldo del servicio de IA. Avisa al administrador del sistema."
    if "timed out" in t.lower() or "timeout" in t.lower():
        return "⏳ La consulta tardó demasiado. Intenta con una pregunta más específica."
    return "⚠️ No pude completar la consulta en este momento. Intenta de nuevo en un minuto."


def proveedor():
    p = (os.getenv("AI_PROVIDER") or "").strip().lower()
    if p in MODELOS and _clave(p):
        return p
    for p in ("anthropic", "gemini", "openai"):
        if _clave(p):
            return p
    return None


def _clave(p):
    return (os.getenv({"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}[p]) or "").strip()


def activo():
    return proveedor() is not None


def olvidar(chat_id):
    _historial.pop(chat_id, None)


# ─────────────────────────────── Herramientas ────────────────────────────────
def _r(v, d=1):
    return round(v, d) if isinstance(v, float) else v


def _pct(v):
    return None if v is None else f"{v * 100:.1f}%"


def _fila_corta(x):
    return {
        "fecha": x["fecha"], "turno": x["turno"], "maquina": x["maquina"], "parte": x["parte"],
        "descripcion": x["descripcion"], "cliente": x["cliente"], "meta": round(x["meta"]),
        "produccion_ttl": x["prod_ttl"], "buena": x["prod_buena"], "cumplimiento": _pct(x["cumplimiento"]),
        "kg": _r(x["prod_kg"]), "scrap": x["scrap_ttl"],
        "scrap_detalle": {k: v for k, v in x["scrap"].items() if v},
        "paro_hrs": _r(x["paro_ttl"], 2), "paros_detalle": {k: _r(v, 2) for k, v in x["paros"].items() if v},
        "ciclo_bom": x["ciclo_bom"], "ciclo_real": x["ciclo_real"], "cav_real": x["cav_real"], "horas": x["horas"],
        "carritos": x["carritos"], "en_secado": x["en_secado"], "capturado": x["capturado"],
        "corte": x["corte"], "faltan_datos_bom": x["faltan"], "comentario": x["comentario"],
    }


def _tot_corto(t):
    return {
        "meta": round(t["meta"]), "resultado": t["resultado"], "cumplimiento": _pct(t["cumplimiento"]),
        "kg": _r(t["kg"]), "produccion_ttl": t["prod_ttl"], "scrap": t["scrap"], "scrap_pct": _pct(t["scrap_pct"]),
        "paro_hrs": _r(t["paro_hrs"], 2), "paro_pct": _pct(t["paro_pct"]), "cambios_molde": t["cambios_molde"],
        "carritos": t["carritos"], "en_secado": t["en_secado"], "filas_sin_captura": t["sin_captura"],
        "filas_sin_meta": t.get("sin_meta"), "ciclo_meta_prom": _r(t["ciclo_meta"]), "ciclo_real_prom": _r(t["ciclo_real"]),
        "scrap_por_defecto": {k: v for k, v in t["scrap_detalle"].items() if v},
        "paro_por_causa_hrs": {k: _r(v, 2) for k, v in t["paros_detalle"].items() if v},
    }


def _rango(desde, hasta):
    d = date.fromisoformat(desde) if desde else R.turno_actual()[0]
    h = date.fromisoformat(hasta) if hasta else d
    if h < d:
        d, h = h, d
    if (h - d).days > 62:
        raise ValueError("El rango máximo es de 62 días.")
    return d, h


def t_turno_actual():
    f, t = R.turno_actual()
    return {"fecha_turno": f.isoformat(), "turno": t, "ahora": datetime.now(R.TZ).strftime("%Y-%m-%d %H:%M"),
            "nota": "Turno DIA 07:30-19:30; NOCHE 19:30-07:30 (la noche pertenece a la fecha en que empezó)."}


def t_resumen_produccion(desde=None, hasta=None, turno=None):
    d, h = _rango(desde, hasta)
    filas = R.construir_filas(d, h, turno)
    res = R._resumen(filas)
    por_maq = {}
    for x in filas:
        m = por_maq.setdefault(x["maquina"], {"maquina": x["maquina"], "meta": 0, "buena": 0, "paro_hrs": 0, "scrap": 0})
        m["meta"] += x["meta"]; m["buena"] += x["prod_buena"]; m["paro_hrs"] += x["paro_ttl"]; m["scrap"] += x["scrap_ttl"]
    maqs = list(por_maq.values())
    for m in maqs:
        m["cumplimiento"] = _pct(m["buena"] / m["meta"]) if m["meta"] else None
        m["meta"] = round(m["meta"]); m["paro_hrs"] = _r(m["paro_hrs"], 2)
    return {
        "desde": d.isoformat(), "hasta": h.isoformat(), "turno": turno or "AMBOS",
        "total": _tot_corto(res["total"]),
        "por_turno": [{"fecha": x["fecha"], "turno": x["turno"], **{k: v for k, v in _tot_corto(x).items()
                       if k in ("meta", "resultado", "cumplimiento", "kg", "scrap", "paro_hrs", "carritos", "filas_sin_captura")}}
                      for x in res["por_turno"]][:62],
        "top_maquinas_por_paro": sorted(maqs, key=lambda m: -m["paro_hrs"])[:5],
        "top_maquinas_por_scrap": sorted(maqs, key=lambda m: -m["scrap"])[:5],
        "maquinas_menor_cumplimiento": sorted([m for m in maqs if m["meta"]], key=lambda m: m["buena"] / max(m["meta"], 1))[:5],
        "maquinas_con_produccion": len(maqs),
    }


def t_detalle_turno(fecha=None, turno=None, maquina=None):
    f, t = R.turno_actual()
    d = date.fromisoformat(fecha) if fecha else f
    filas = R.construir_filas(d, d, turno or t)
    if maquina is not None:
        filas = [x for x in filas if int(x["maquina"] or 0) == int(maquina)]
    return {"fecha": d.isoformat(), "turno": R.norm_turno(turno or t), "filas": [_fila_corta(x) for x in filas[:60]],
            "total_filas": len(filas)}


def t_produccion_parte(parte, desde=None, hasta=None):
    d, h = _rango(desde, hasta)
    q = parte.strip().upper()
    filas = [x for x in R.construir_filas(d, h) if q in x["parte"].upper()]
    tot = {"produccion_ttl": sum(x["prod_ttl"] for x in filas), "buena": sum(x["prod_buena"] for x in filas),
           "scrap": sum(x["scrap_ttl"] for x in filas), "kg": _r(sum(x["prod_kg"] or 0 for x in filas)),
           "carritos": sum(x["carritos"] for x in filas), "meta": round(sum(x["meta"] for x in filas))}
    return {"busqueda": q, "desde": d.isoformat(), "hasta": h.isoformat(), "total": tot,
            "detalle": [{k: v for k, v in _fila_corta(x).items() if k in ("fecha", "turno", "maquina", "parte", "produccion_ttl",
                         "buena", "meta", "cumplimiento", "scrap", "carritos")} for x in filas[:80]]}


def t_estado_secado(minutos_max=60):
    st = R._load(R.DRYING_FILE, {})
    ahora = datetime.now(R.TZ)
    activos = []
    for r in st.get("records", []):
        if r.get("estado") != "EN SECADO":
            continue
        dt = R.parse_dt(r.get("horaEntrada"))
        mins = round((ahora - dt).total_seconds() / 60) if dt else None
        activos.append({"id": r.get("idCarrito"), "parte": r.get("numeroParte"), "maquina": r.get("maquina"),
                        "qty": r.get("qty"), "entrada": dt.strftime("%Y-%m-%d %H:%M") if dt else None, "minutos": mins})
    activos.sort(key=lambda a: -(a["minutos"] or 0))
    f, t = R.turno_actual()
    log = R._load(R.LOG_FILE, {})
    ent = sal = 0
    for r in log.values():
        dt = R.parse_dt(r.get("horaEntrada"))
        if dt and R.turno_de(dt) == (f, t):
            ent += 1
        ds = R.parse_dt(r.get("horaSalida"))
        if ds and R.turno_de(ds) == (f, t):
            sal += 1
    return {"carritos_en_secado": len(activos), "piezas_en_secado": sum(a["qty"] or 0 for a in activos),
            "vencidos": [a for a in activos if (a["minutos"] or 0) >= minutos_max][:20], "minutos_max": minutos_max,
            "mas_antiguos": activos[:15], "turno_actual": {"fecha": f.isoformat(), "turno": t, "entradas": ent, "salidas": sal}}


def t_capturas_pendientes(fecha=None, turno=None):
    f, t = R.turno_actual()
    d = date.fromisoformat(fecha) if fecha else f
    filas = R.construir_filas(d, d, turno or t)
    pend = [{"maquina": x["maquina"], "parte": x["parte"], "carritos": x["carritos"], "produccion_ttl": x["prod_ttl"]}
            for x in filas if not x["capturado"]]
    return {"fecha": d.isoformat(), "turno": R.norm_turno(turno or t), "total_filas": len(filas),
            "pendientes": pend, "capturadas": len(filas) - len(pend),
            "nota": "Sin captura se asumen 12 h y 0 scrap/paro; se captura en la pantalla 'Captura de Turno'."}


def t_buscar_parte(texto):
    q = texto.strip().upper()
    bom = R._bom()
    cat = R._load(R.PARTS_FILE, {})
    out = []
    for k in sorted(set(bom) | set(cat)):
        b, c = bom.get(k, {}), cat.get(k, {})
        if q in k or q in str(b.get("descripcion", "")).upper() or q in str(b.get("modelo", "")).upper():
            out.append({"parte": k, "descripcion": b.get("descripcion") or c.get("descripcion"), "cliente": b.get("cliente"),
                        "modelo": b.get("modelo"), "tipo_pieza": b.get("id2"), "cav": b.get("cav"), "ciclo": b.get("ciclo"),
                        "peso_kg": b.get("peso"), "qty_por_etiqueta": c.get("qtu") or None, "corte": b.get("corte")})
        if len(out) >= 15:
            break
    return {"busqueda": q, "resultados": out}


HERRAMIENTAS = [
    ("turno_actual", "Fecha del turno, turno (DIA/NOCHE) y hora actuales. Úsala para resolver 'hoy', 'ayer', 'este turno'.",
     {}, [], t_turno_actual),
    ("resumen_produccion", "Resumen de producción en un rango: meta, resultado, % cumplimiento, kg, scrap por defecto, paros por causa, "
     "por turno y top máquinas por paro/scrap/menor cumplimiento.",
     {"desde": {"type": "string", "description": "YYYY-MM-DD (fecha del turno)"},
      "hasta": {"type": "string", "description": "YYYY-MM-DD, opcional"},
      "turno": {"type": "string", "enum": ["DIA", "NOCHE"], "description": "Opcional"}}, [], t_resumen_produccion),
    ("detalle_turno", "Detalle por máquina y parte de un turno: meta, producción, scrap y paros con su detalle, ciclo real, comentarios.",
     {"fecha": {"type": "string", "description": "YYYY-MM-DD"}, "turno": {"type": "string", "enum": ["DIA", "NOCHE"]},
      "maquina": {"type": "integer", "description": "Opcional, número de máquina"}}, [], t_detalle_turno),
    ("produccion_parte", "Producción de un número de parte (búsqueda parcial) en un rango, por fecha/turno/máquina.",
     {"parte": {"type": "string"}, "desde": {"type": "string"}, "hasta": {"type": "string"}}, ["parte"], t_produccion_parte),
    ("estado_secado", "Estado actual del cuarto de secado: carritos y piezas dentro, los más antiguos, vencidos y entradas/salidas del turno.",
     {"minutos_max": {"type": "integer", "description": "Minutos a partir de los cuales un carrito se considera vencido (default 60)"}},
     [], t_estado_secado),
    ("capturas_pendientes", "Máquinas/partes de un turno que todavía no tienen su captura (horas, paros, scrap, ciclo real).",
     {"fecha": {"type": "string", "description": "YYYY-MM-DD"}, "turno": {"type": "string", "enum": ["DIA", "NOCHE"]}},
     [], t_capturas_pendientes),
    ("buscar_parte", "Busca en el BOM y catálogo por número de parte, descripción o modelo: cliente, ciclo, cavidades, peso, qty por etiqueta.",
     {"texto": {"type": "string"}}, ["texto"], t_buscar_parte),
    ("enviar_excel_reporte", "Adjunta al chat el Excel del reporte de producción (formato de la hoja mensual) para el rango indicado. "
     "Úsala solo si el usuario pide el archivo/Excel.",
     {"desde": {"type": "string"}, "hasta": {"type": "string"}, "turno": {"type": "string", "enum": ["DIA", "NOCHE"]}}, [], None),
]


def _ejecutar(nombre, args, adjuntos):
    for n, _, _, _, fn in HERRAMIENTAS:
        if n != nombre:
            continue
        try:
            if n == "enviar_excel_reporte":
                d, h = _rango(args.get("desde"), args.get("hasta"))
                adjuntos.append({"desde": d.isoformat(), "hasta": h.isoformat(), "turno": args.get("turno")})
                return {"ok": True, "mensaje": f"Se adjuntará el Excel del {d} al {h}."}
            return fn(**{k: v for k, v in (args or {}).items() if v not in (None, "")})
        except Exception as e:
            return {"error": str(e)}
    return {"error": f"Herramienta desconocida: {nombre}"}


def _sistema():
    f, t = R.turno_actual()
    return (
        "Eres el asistente de producción de la planta de moldeo EPS (Cheong Woon México / EPS, Monterrey). "
        "Contestas por Telegram a supervisores y gerencia, en español, breve y directo.\n"
        f"Ahora: {datetime.now(R.TZ).strftime('%A %Y-%m-%d %H:%M')} (America/Mexico_City). Turno actual: {t} del {f.isoformat()}.\n"
        "Definiciones del sistema:\n"
        "- Producción = carritos que ENTRAN al cuarto de secado (cada carrito = una etiqueta con su Qty), por máquina y turno.\n"
        "- Turno DIA 07:30-19:30, NOCHE 19:30-07:30; la noche se cuenta en la fecha en que empezó.\n"
        "- Meta = 3600 / ciclo BOM × cavidades reales × horas trabajadas. Cumplimiento = producción buena / meta.\n"
        "- Buena = producción TTL − scrap. Scrap, paros, ciclo real y horas vienen de la 'Captura de turno'; "
        "si una fila no está capturada se asumen 12 h y 0 scrap/paro: adviértelo cuando importe.\n"
        "- Las piezas de corte (Cutting) no tienen meta.\n"
        "Reglas: usa SIEMPRE las herramientas para cualquier número; nunca inventes ni estimes cifras. "
        "Si no hay datos, dilo. Resuelve fechas relativas (hoy/ayer/semana) con la fecha actual. "
        "Formato Telegram: texto corto, viñetas con '•', negritas con *texto* (sin ** ni encabezados #), números con separador de miles. "
        "Máximo ~15 líneas salvo que pidan detalle. Eres de solo consulta: no puedes registrar entradas/salidas ni cambiar datos; "
        "para registrar, indica usar foto de la etiqueta o 'entrada <parte>' / 'salida <parte>'."
    )


# ─────────────────────────────── Proveedores ─────────────────────────────────
def _llamar_anthropic(sistema, mensajes, modelo):
    tools = [{"name": n, "description": d, "input_schema": {"type": "object", "properties": p, "required": req}}
             for n, d, p, req, _ in HERRAMIENTAS]
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=90, headers={
        "x-api-key": _clave("anthropic"), "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": modelo, "max_tokens": 1500, "system": sistema, "tools": tools, "messages": mensajes})
    if r.status_code != 200:
        raise RuntimeError(f"Anthropic {r.status_code}: {r.text[:300]}")
    return r.json()


def _llamar_openai(prov, sistema, mensajes, modelo):
    tools = [{"type": "function", "function": {"name": n, "description": d,
              "parameters": {"type": "object", "properties": p, "required": req}}} for n, d, p, req, _ in HERRAMIENTAS]
    r = requests.post(URLS[prov], timeout=90, headers={"Authorization": f"Bearer {_clave(prov)}", "Content-Type": "application/json"},
                      json={"model": modelo, "messages": [{"role": "system", "content": sistema}] + mensajes, "tools": tools})
    if r.status_code != 200:
        raise RuntimeError(f"{prov} {r.status_code}: {r.text[:300]}")
    return r.json()


def responder(chat_id, texto, llamar=None):
    """Devuelve (respuesta_texto, adjuntos). `llamar` permite inyectar un proveedor simulado en pruebas."""
    prov = proveedor() if llamar is None else "anthropic"
    if not prov:
        return None, []
    modelo = (os.getenv("AI_MODEL") or "").strip() or MODELOS[prov]
    h = _historial.get(chat_id)
    if not h or time.time() - h["t"] > HIST_TTL:
        h = {"t": time.time(), "msgs": []}
    previos = h["msgs"][-2 * HIST_TURNOS:]
    sistema = _sistema()
    adjuntos = []
    final = ""
    t0 = time.time()
    usadas = []
    tokens = {"entrada": 0, "salida": 0}

    if prov == "anthropic":
        msgs = previos + [{"role": "user", "content": texto}]
        for _ in range(MAX_PASOS):
            resp = (llamar or _llamar_anthropic)(sistema, msgs, modelo)
            u = resp.get("usage") or {}
            tokens["entrada"] += u.get("input_tokens", 0); tokens["salida"] += u.get("output_tokens", 0)
            bloques = resp.get("content", [])
            usos = [b for b in bloques if b.get("type") == "tool_use"]
            usadas += [b.get("name") for b in usos]
            texto_resp = "".join(b.get("text", "") for b in bloques if b.get("type") == "text").strip()
            if not usos:
                final = texto_resp
                break
            msgs.append({"role": "assistant", "content": bloques})
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": u["id"],
                 "content": json.dumps(_ejecutar(u["name"], u.get("input") or {}, adjuntos), ensure_ascii=False, default=str)[:15000]}
                for u in usos]})
        else:
            final = final or "No alcancé a terminar la consulta; intenta con una pregunta más específica."
    else:
        msgs = previos + [{"role": "user", "content": texto}]
        for _ in range(MAX_PASOS):
            resp = _llamar_openai(prov, sistema, msgs, modelo)
            u = resp.get("usage") or {}
            tokens["entrada"] += u.get("prompt_tokens", 0); tokens["salida"] += u.get("completion_tokens", 0)
            m = resp["choices"][0]["message"]
            calls = m.get("tool_calls") or []
            usadas += [c["function"]["name"] for c in calls]
            if not calls:
                final = (m.get("content") or "").strip()
                break
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
            for c in calls:
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                msgs.append({"role": "tool", "tool_call_id": c["id"],
                             "content": json.dumps(_ejecutar(c["function"]["name"], args, adjuntos), ensure_ascii=False, default=str)[:15000]})
        else:
            final = final or "No alcancé a terminar la consulta; intenta con una pregunta más específica."

    final = final or "No tengo una respuesta para eso."
    h["msgs"] = previos + [{"role": "user", "content": texto}, {"role": "assistant", "content": final}]
    h["t"] = time.time()
    _historial[chat_id] = h
    _registrar({"ts": datetime.now(R.TZ).isoformat(timespec="seconds"), "chat": chat_id, "proveedor": prov, "modelo": modelo,
                "pregunta": texto[:500], "herramientas": usadas, "segundos": round(time.time() - t0, 1),
                "tokens": tokens, "respuesta": final[:500]})
    return final, adjuntos


def a_markdown_telegram(t):
    """Convierte **negritas** y encabezados # al Markdown simple de Telegram."""
    t = re.sub(r"\*\*(.+?)\*\*", r"*\1*", t)
    t = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", t, flags=re.M)
    return t
