"""Hito 2BP: serie supervisada de conciliacion (plan READ_ONLY y tandas de ``ejecutar_una_manual_conciliacion()``).

Uso (identidad Usuari; lecturas con CONTROLFARMACIAS_SUPABASE_DB_URL y la puerta READ_ONLY del 2AT; escrituras solo
con el cliente del .env y el worker manual del 2AT; sin Farmatic):
  python -B pruebas/auditoria_2bp/serie_conciliacion.py plan <plan.json>
  python -B pruebas/auditoria_2bp/serie_conciliacion.py tanda <n> <plan.json> <directorio_tanda>

Mismo esquema que la serie de normalizacion (2BJ, ``pruebas/auditoria_2bj/serie_normalizacion.py``); diseno en
``pruebas/auditoria_2bp/DISENO.md``.

``plan`` no escribe nada: lee las facturas elegibles en el orden del selector oficial (claim MANUAL_ONE_SHOT de la
migracion 18) y simula cada una con el camino real del worker (``auditoria_readonly._simular``) EN CADENA: los
albaranes que reservaria cada conciliacion prevista (R15) quedan ocupados para las siguientes. Registra el resultado
previsto (CONCILIADA / DIFERENCIA y cuanto, o FALLO), la clave idempotente prevista y la huella de cada fila.

``tanda`` (guard exclusivo por tanda, sin reintentos; como maximo 5 la primera y 20 las siguientes): preflight
READ_ONLY y snapshot por fila; puerta git (arbol limpio y HEAD = origin/main, o por delante solo con documentacion);
para cada ejecucion, puertas (operacion, configuracion, MIGRACION 30 DESPLEGADA, tareas a 60 min o mas, n.o 1 del
plan con la misma huella), nueva simulacion READ_ONLY del n.o 1 igual a la del plan y PARADA si no simula CONCILIADA
(salvo decision de Pio registrada en el plan para esa factura y esa diferencia), UNA llamada a
``ejecutar_una_manual_conciliacion()`` y comprobacion (estado y conciliacion previstos, filas cambiadas solo de la
factura). Cualquier desviacion -> PARADA. Al final, y tambien al parar, postcheck 2AX por fila de toda la tanda.
Salidas fuera del repositorio.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

import auditoria_readonly as ar  # noqa: E402
from auditoria_readonly import (  # noqa: E402
    COLUMNAS_HUELLA, MODO_CLAIM, PROJECT_REF, SQL_SELECTOR_OFICIAL, SQL_TODAS_CON_FILTROS, _cuerpo_local,
    _cuerpo_remoto, _ejecutar_lectura, _escribir, _operacion, _puertas_operacion, _salida_fuera_del_repo)


def _cargar(nombre: str, ruta: str):
    spec = importlib.util.spec_from_file_location(nombre, ROOT / ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


preflight_2bdd = _cargar("preflight_2bdd_2bp", "pruebas/auditoria_2bd_d/preflight_readonly.py")
_tareas = preflight_2bdd._tareas
_puertas_tareas = preflight_2bdd._puertas_tareas

WORKER_BASE = "cf-2bp-serie"
MAX_PRIMERA = 5
MAX_TANDA = 20
MIGRACION_30 = ROOT / "sql/migrations/30_cf_detalle_por_linea.sql"
PERSISTIR = "public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)"
POR_LINEA = "public.cf_detalles_por_linea(uuid,jsonb)"
PREVIO_30 = "public.conciliacion_detalles_previo_30"
DECISION_DIFERENCIA = "CONCILIAR_CON_DIFERENCIA"
# Lo que se compara entre la simulacion del plan y la de la tanda (la clave idempotente resume el resultado entero).
CAMPOS_PREVISION = ("camino", "resultado", "importe_factura", "importe_explicado", "diferencia", "tolerancia",
                    "idempotency_key_prevista")
# 2AX por fila: filas de la factura conciliada que pueden cambiar o desaparecer.
CAMBIABLES = frozenset({"facturas", "conciliaciones"})
BORRABLES = frozenset({"conciliacion_albaranes_reservados"})  # R15: las reservas pasan a la conciliacion nueva
HUELLA_FACTURA = ("select md5(to_jsonb(r)::text) from public.facturas t cross join lateral (select "
                  + ", ".join(f"t.{c}" for c in COLUMNAS_HUELLA["facturas"]) + ") r where t.id = %s")


def _ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --------------------------------------------------------------------------- simulacion

@contextmanager
def _reservas_previstas(reservas: dict[tuple[str, int], str]):
    """La simulacion ve como ocupados los albaranes de ``reservas`` (clave -> factura) de OTRAS facturas: las
    reservas reales mas las de las conciliaciones previstas antes en el plan (R15). Sin escrituras."""
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase as Repositorio

    original = Repositorio._contexto_exclusividad

    def con_previstas(self, factura, operational_rows):
        _, numeros = original(self, factura, operational_rows)
        return {k for k, f in reservas.items() if f != factura.factura_id}, numeros

    Repositorio._contexto_exclusividad = con_previstas
    try:
        yield
    finally:
        Repositorio._contexto_exclusividad = original


def prevision(simulacion: dict) -> dict:
    out = {k: simulacion.get(k) for k in CAMPOS_PREVISION}
    if simulacion.get("camino") == "FALLO":
        out["fallo"] = simulacion.get("fallo")
    else:
        out["resumen_detalles"] = simulacion.get("resumen_detalles")
        # Albaranes que reservaria la conciliacion (R15), para encadenar la simulacion de las siguientes.
        out["albaranes"] = sorted([d["albaran_operacional"]["farmacia"], int(d["albaran_operacional"]["id_contador"])]
                                  for d in simulacion.get("detalles", []) if d.get("albaran_operacional"))
    return out


def _simular_cadena(lector, ids: list[str]) -> list[dict]:
    reservas = {(r[0], int(r[1])): r[2] for r in lector.filas(
        "select albaran_farmacia, albaran_id_contador, factura_id::text from public.conciliacion_albaranes_reservados")}
    previstas = []
    for factura_id in ids:
        with _reservas_previstas(dict(reservas)):
            simulacion = ar._simular(lector, factura_id)
        p = prevision(simulacion)
        if p["camino"] == "PERSISTIR":  # cf_persistir_conciliacion sustituye las reservas de la factura (R15)
            reservas = {k: f for k, f in reservas.items() if f != factura_id}
            reservas.update({(a, int(c)): factura_id for a, c in p["albaranes"]})
        previstas.append(p)
    return previstas


# --------------------------------------------------------------------------- plan

def plan(salida: Path) -> int:
    def leer(lector) -> dict:
        ids = [r[0] for r in lector.filas(SQL_SELECTOR_OFICIAL, {"modo": MODO_CLAIM})]
        todas = {f["id"]: f for f in (json.loads(r[0]) for r in lector.filas(SQL_TODAS_CON_FILTROS))}
        previstas = _simular_cadena(lector, ids)
        facturas = []
        for posicion, (factura_id, p) in enumerate(zip(ids, previstas), start=1):
            f = todas[factura_id]
            facturas.append({"posicion": posicion, "id": factura_id, "numero_factura": f["numero_factura"],
                             "proveedor": f["proveedor_literal"] or f["proveedor_nombre"],
                             "fecha_factura": f["fecha_factura"], "importe_total": f["importe_total"],
                             "intentos_fallo": f["intentos_fallo"],
                             "huella_fila": lector.valor(HUELLA_FACTURA, (factura_id,)), "prevision": p})
        no_elegibles = [{k: f[k] for k in ("id", "numero_factura", "estado_conciliacion_cf", "elegibilidad", "razon")}
                        for f in todas.values() if f["id"] not in set(ids)
                        and f["estado_conciliacion_cf"] not in ("CONCILIADA",)]
        return {"facturas": facturas, "no_elegibles": no_elegibles,
                "migracion_30": _marcas_30(lector), "operacion": _operacion(lector)}

    _, datos = _ejecutar_lectura(leer)
    resumen: dict = {}
    for f in datos["facturas"]:
        clave = f["prevision"]["resultado"] or f["prevision"]["camino"]
        resumen[clave] = resumen.get(clave, 0) + 1
    primera = next((f["posicion"] for f in datos["facturas"] if f["prevision"]["resultado"] != "CONCILIADA"), None)
    datos.update({"hito": "2BP", "resumen": resumen, "primera_no_conciliada": primera, "decisiones_pio": {}})
    sha = _escribir(salida, datos)
    print(json.dumps({"resumen": resumen, "primera_no_conciliada": primera, "facturas": [
        (f["posicion"], f["numero_factura"], f["prevision"]["resultado"] or "FALLO", f["prevision"]["diferencia"])
        for f in datos["facturas"]], "migracion_30": datos["migracion_30"]}, ensure_ascii=False, indent=1))
    print("sha256", sha)
    return 0


# --------------------------------------------------------------------------- lecturas de la tanda

def _marcas_30(lector) -> dict:
    """La 30 desplegada: auxiliar y tabla de valores previos presentes y cuerpos iguales a los del repositorio."""
    por_linea = lector.valor(f"select to_regprocedure('{POR_LINEA}') is not null")
    return {
        "cf_detalles_por_linea": bool(por_linea) and _cuerpo_remoto(lector, POR_LINEA) == _cuerpo_local(
            MIGRACION_30, "cf_detalles_por_linea"),
        "valores_previos": lector.valor(f"select to_regclass('{PREVIO_30}') is not null"),
        "cf_persistir_conciliacion": _cuerpo_remoto(lector, PERSISTIR) == _cuerpo_local(
            MIGRACION_30, "cf_persistir_conciliacion"),
    }


def _tablas(lector) -> dict[str, dict]:
    """Tablas de public con su clave (id o fila) y la expresion que da su factura (si la hay)."""
    columnas: dict[str, set[str]] = {}
    for tabla, columna in lector.filas(
            "select table_name, column_name from information_schema.columns where table_schema = 'public' "
            "and table_name in (select table_name from information_schema.tables where table_schema = 'public' "
            "and table_type = 'BASE TABLE') order by 1, 2"):
        columnas.setdefault(tabla, set()).add(columna)
    tablas = {}
    for tabla, cols in sorted(columnas.items()):
        if tabla == "facturas":
            dueno = "t.id::text"
        elif tabla == "conciliacion_detalles":
            dueno = "(select c.factura_id::text from public.conciliaciones c where c.id = t.conciliacion_id)"
        elif tabla == "conciliacion_detalles_previo_30":
            dueno = ("(select c.factura_id::text from public.conciliacion_detalles d join public.conciliaciones c "
                     "on c.id = d.conciliacion_id where d.id = t.detalle_id)")
        elif "factura_id" in cols:
            dueno = "t.factura_id::text"
        else:
            dueno = "null"
        tablas[tabla] = {"clave": "t.id::text" if "id" in cols else "md5(to_jsonb(t)::text)", "dueno": dueno}
    return tablas


def _filas(lector) -> dict:
    out = {}
    for tabla, d in _tablas(lector).items():
        out[tabla] = {r[0]: [r[1], r[2]] for r in lector.filas(
            f"select {d['clave']}, md5(to_jsonb(t)::text), {d['dueno']} from public.{tabla} t")}
    return out


def _estado_operativo(lector) -> dict:
    out = {"operacion": _operacion(lector)}
    out["cf_configuracion"] = lector.json("select to_jsonb(c)::text from public.cf_configuracion c where id")
    out["migracion_30"] = _marcas_30(lector)
    out["cola"] = [r[0] for r in lector.filas(SQL_SELECTOR_OFICIAL, {"modo": MODO_CLAIM})]
    out["huella_numero_1"] = lector.valor(HUELLA_FACTURA, (out["cola"][0],)) if out["cola"] else None
    return out


def _leer_tanda(lector) -> dict:
    return {**_estado_operativo(lector), "filas": _filas(lector)}


def _resimular(factura_id: str) -> dict:
    def leer(lector) -> dict:
        simulacion = ar._simular(lector, factura_id)
        return {"prevision": prevision(simulacion),
                "estado_previsto": ar._estado_previsto(lector, factura_id, simulacion)}
    return _ejecutar_lectura(leer)[1]


def _factura(factura_id: str) -> dict:
    def leer(lector) -> dict:
        estado, intentos_fallo, bloqueado = lector.fila(
            "select estado_conciliacion_cf, conciliacion_intentos_fallo, conciliacion_bloqueado_por "
            "from public.facturas where id = %s", (factura_id,))
        vigente = lector.filas(
            "select resultado, diferencia::text, idempotency_key, disparador from public.conciliaciones "
            "where factura_id = %s and es_actual", (factura_id,))
        return {"estado_conciliacion_cf": estado, "conciliacion_intentos_fallo": intentos_fallo,
                "bloqueado_por": bloqueado, "vigente": [list(v) for v in vigente]}
    return _ejecutar_lectura(leer)[1]


# --------------------------------------------------------------------------- git

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def _estado_git() -> dict:
    try:
        return {"status": _git("status", "--porcelain"), "head": _git("rev-parse", "HEAD"),
                "origin": _git("rev-parse", "origin/main"),
                "origin_ancestro": subprocess.run(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
                                                  cwd=ROOT).returncode == 0,
                "cambios": _git("diff", "--name-only", "origin/main..HEAD").splitlines()}
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def puerta_git(g: dict) -> list[str]:
    """Arbol limpio y HEAD = origin/main; excepcion de Pio (2BN-D): por delante solo con documentacion."""
    if "error" in g:
        return [f"GIT_NO_DETERMINABLE:{g['error']}"]
    fallos = []
    if g["status"]:
        fallos.append("GIT_ARBOL_NO_LIMPIO")
    if g["head"] != g["origin"]:
        no_doc = [c for c in g["cambios"] if not (c.startswith("docs/") or c.endswith(".md"))]
        if not g["origin_ancestro"]:
            fallos.append("GIT_HEAD_NO_DESCIENDE_DE_ORIGIN")
        elif no_doc:
            fallos.append(f"GIT_COMMITS_NO_DOCUMENTALES:{','.join(no_doc[:10])}")
    return fallos


# --------------------------------------------------------------------------- comprobaciones (sin conexion)

def puertas(estado: dict, plan_facturas: dict, referencia: dict, tareas: dict, ahora: dt.datetime) -> list[str]:
    fallos = list(_puertas_operacion(estado["operacion"]))
    if estado["cf_configuracion"] != referencia["cf_configuracion"]:
        fallos.append("CONFIGURACION_DISTINTA_DEL_PREFLIGHT")
    # Decision de Pio (2BR): primero desplegar la 30, despues conciliar.
    fallos += [f"MIGRACION_30_AUSENTE:{k}" for k, v in estado["migracion_30"].items() if not v]
    fallos += _puertas_tareas(tareas, ahora)
    if not estado["cola"]:
        fallos.append("COLA_VACIA")
    else:
        factura_id = estado["cola"][0]
        previsto = plan_facturas.get(factura_id)
        if previsto is None:
            fallos.append(f"NUMERO_1_FUERA_DEL_PLAN:{factura_id}")
        elif previsto["huella_fila"] != estado["huella_numero_1"]:
            fallos.append(f"NUMERO_1_FILA_DISTINTA_DEL_PLAN:{factura_id}")
    return fallos


def comprobar_simulacion(plan_factura: dict, actual: dict, decisiones: dict) -> list[str]:
    """La simulacion inmediata debe ser la del plan, y CONCILIADA salvo decision de Pio para esa diferencia."""
    previsto = plan_factura["prevision"]
    motivos = [f"SIMULACION_DISTINTA_DEL_PLAN:{k}:{previsto.get(k)}!={actual.get(k)}"
               for k in CAMPOS_PREVISION if previsto.get(k) != actual.get(k)]
    if motivos:
        return motivos
    if actual["camino"] != "PERSISTIR":
        return [f"NUMERO_1_SIMULA_FALLO:{plan_factura['id']}:{(actual.get('fallo') or {}).get('codigo')}"]
    if actual["resultado"] != "CONCILIADA":
        decision = decisiones.get(plan_factura["id"]) or {}
        if decision.get("decision") != DECISION_DIFERENCIA or decision.get("diferencia") != actual["diferencia"]:
            return [f"NUMERO_1_SIMULA_DIFERENCIA:{plan_factura['id']}:{plan_factura['numero_factura']}:"
                    f"{actual['diferencia']}"]
    return []


def comprobar_resultado(previsto: dict, estado_previsto: dict, real: dict) -> list[str]:
    motivos = []
    if real["estado_conciliacion_cf"] != estado_previsto["estado_conciliacion_cf"]:
        motivos.append(f"ESTADO_INESPERADO:{estado_previsto['estado_conciliacion_cf']}!={real['estado_conciliacion_cf']}")
    if real["conciliacion_intentos_fallo"] != estado_previsto["conciliacion_intentos_fallo"]:
        motivos.append("INTENTOS_FALLO_INESPERADOS")
    if real["bloqueado_por"] is not None:
        motivos.append("CLAIM_NO_LIBERADO")
    esperada = [previsto["resultado"], previsto["diferencia"], previsto["idempotency_key_prevista"], MODO_CLAIM]
    if real["vigente"] != [esperada]:
        motivos.append(f"CONCILIACION_VIGENTE_INESPERADA:{real['vigente']}")
    return motivos


def diferencias_filas(antes: dict, despues: dict, facturas: set[str]) -> list[str]:
    """Criterio 2AX por fila: solo filas nuevas de ``facturas``, cambios en sus filas de ``CAMBIABLES`` y bajas de
    sus reservas (R15)."""
    problemas = []
    for tabla in sorted(set(antes) | set(despues)):
        a, b = antes.get(tabla, {}), despues.get(tabla, {})
        for clave in set(b) - set(a):
            if b[clave][1] not in facturas:
                problemas.append(f"FILA_NUEVA_AJENA:{tabla}:{clave}")
        for clave in set(a) - set(b):
            if not (tabla in BORRABLES and a[clave][1] in facturas):
                problemas.append(f"FILA_BORRADA:{tabla}:{clave}")
        for clave in set(a) & set(b):
            if a[clave][0] != b[clave][0] and not (tabla in CAMBIABLES and b[clave][1] in facturas):
                problemas.append(f"FILA_CAMBIADA_AJENA:{tabla}:{clave}")
    return sorted(problemas)[:50]


# --------------------------------------------------------------------------- escritura (cliente del .env)

def _rol_clave(clave: str) -> str | None:
    if clave.startswith("sb_secret_"):
        return "service" + "_role"
    if clave.startswith("sb_publishable_"):
        return "anon"
    try:
        cuerpo = clave.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4))).get("role")
    except Exception:
        return None


def _cliente():
    """Cliente del .env con project ref productivo y rol de servicio demostrados (patron 2AO rev3 / 2AT)."""
    from dotenv import dotenv_values
    from src.supabase_client.conexion_supabase import obtener_cliente_supabase

    env = dotenv_values(ROOT / ".env")
    ref = (urlparse(env.get("SUPABASE_URL", "")).hostname or "").split(".")[0]
    if ref != PROJECT_REF or _rol_clave(env.get("SUPABASE_KEY", "")) != "service" + "_role":
        raise SystemExit("CLIENTE_NO_DEMOSTRADO")
    return obtener_cliente_supabase()


def _ejecutar_una(cliente, directorio: Path):
    """UNA llamada a ``ejecutar_una_manual_conciliacion()`` (patron 2AT rev2)."""
    from src.facturas.runtime_supabase.compositor_manual import construir_worker_manual_productivo
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

    configuracion = RepositorioRuntimeSupabase(cliente).obtener_configuracion()
    worker_id = f"{WORKER_BASE}-{uuid.uuid4().hex[:8]}"
    return construir_worker_manual_productivo(cliente, configuracion, worker_id, directorio) \
        .ejecutar_una_manual_conciliacion()


# --------------------------------------------------------------------------- tanda

def _tandas_previas_ok(directorio: Path) -> int:
    ok = 0
    for registro in directorio.parent.glob("*/tanda.json"):
        try:
            ok += json.loads(registro.read_text(encoding="utf-8")).get("veredicto") == "TANDA_OK"
        except (OSError, ValueError):
            pass
    return ok


def tanda(n: int, plan_ruta: Path, directorio: Path) -> int:
    maximo = MAX_TANDA if _tandas_previas_ok(directorio) else MAX_PRIMERA
    if not 1 <= n <= maximo:
        raise SystemExit(f"TAMANO_DE_TANDA_NO_ADMITIDO:{n}>{maximo}")
    plan_datos = json.loads(plan_ruta.read_text(encoding="utf-8"))
    plan_facturas = {f["id"]: f for f in plan_datos["facturas"]}
    decisiones = plan_datos.get("decisiones_pio") or {}
    directorio.mkdir(parents=True, exist_ok=True)
    with open(directorio / "tanda.guard", "x", encoding="utf-8") as g:  # una sola ejecucion por directorio
        g.write(f"{_ahora()} n={n} plan={hashlib.sha256(plan_ruta.read_bytes()).hexdigest()}\n")
    registro: dict = {"hito": "2BP", "n": n, "maximo": maximo, "plan": str(plan_ruta),
                      "plan_sha256": hashlib.sha256(plan_ruta.read_bytes()).hexdigest(),
                      "inicio_utc": _ahora(), "ejecuciones": []}
    salida = directorio / "tanda.json"
    pre: dict = {}
    conciliadas: list[str] = []

    def postcheck() -> list[str]:
        """2AX por fila de toda la tanda frente al snapshot previo (tambien al parar)."""
        _, post = _ejecutar_lectura(_leer_tanda)
        _escribir(directorio / "snapshot_post.json", post)
        problemas = diferencias_filas(pre["filas"], post["filas"], set(conciliadas))
        if post["operacion"]["claims_conciliacion"]:
            problemas.append("CLAIMS_DE_CONCILIACION_TRAS_LA_TANDA")
        if post["cf_configuracion"] != pre["cf_configuracion"] or post["operacion"]["flags"] != pre["operacion"]["flags"]:
            problemas.append("CONFIGURACION_U_OPERACION_DISTINTA")
        registro["postcheck"] = {"veredicto": "POSTCHECK_OK" if not problemas else "POSTCHECK_REVISAR",
                                 "problemas": problemas, "facturas": list(conciliadas)}
        return problemas

    def cerrar(veredicto: str, motivos: list[str]) -> int:
        if veredicto == "PARADA" and pre and "postcheck" not in registro:
            try:
                postcheck()
            except Exception as exc:  # la parada se registra igual; el postcheck queda como no realizado
                registro["postcheck"] = {"veredicto": "POSTCHECK_NO_REALIZADO", "error": f"{type(exc).__name__}: {exc}"}
        registro.update({"veredicto": veredicto, "motivos": motivos, "fin_utc": _ahora()})
        _escribir(salida, registro)
        print(json.dumps({k: registro[k] for k in ("veredicto", "motivos")} | {
            "ejecuciones": [(e["factura_id"], e.get("numero_factura"), e.get("real", {}).get("estado_conciliacion_cf"))
                            for e in registro["ejecuciones"]]}, ensure_ascii=False, indent=1, default=str))
        return 0 if veredicto == "TANDA_OK" else 3

    pre.update(_ejecutar_lectura(_leer_tanda)[1])
    _escribir(directorio / "snapshot_pre.json", pre)
    registro["preflight"] = {k: pre.get(k) for k in ("project_ref", "capturado_utc", "transaction_read_only")}
    registro["git"] = _estado_git()
    fallos_git = puerta_git(registro["git"])
    if fallos_git:
        return cerrar("PARADA", fallos_git)
    try:
        cliente = _cliente()
    except SystemExit as exc:
        return cerrar("PARADA", [str(exc)])
    anterior = pre
    for i in range(n):
        fallos = puertas(anterior, plan_facturas, pre, _tareas(), dt.datetime.now(dt.timezone.utc))
        if fallos == ["COLA_VACIA"] and i > 0:
            break  # cola agotada a mitad de tanda: se cierra con el postcheck
        if fallos:
            return cerrar("PARADA", fallos)
        factura_id = anterior["cola"][0]
        plan_factura = plan_facturas[factura_id]
        ejecucion = {"factura_id": factura_id, "numero_factura": plan_factura["numero_factura"],
                     "posicion_plan": plan_factura["posicion"], "prevision": plan_factura["prevision"]}
        registro["ejecuciones"].append(ejecucion)
        inmediata = _resimular(factura_id)
        ejecucion["simulacion_inmediata"] = inmediata
        motivos = comprobar_simulacion(plan_factura, inmediata["prevision"], decisiones)
        if motivos:
            ejecucion["no_ejecutada"] = True
            return cerrar("PARADA", motivos)
        ejecucion["inicio_utc"] = _ahora()
        temporal = Path(tempfile.mkdtemp(prefix="cf2bp_"))
        try:
            retorno = _ejecutar_una(cliente, temporal)
            ejecucion["retorno"] = {"facturas_conciliacion_reclamadas": retorno.facturas_conciliacion_reclamadas,
                                    "documentos_reclamados": retorno.documentos_reclamados,
                                    "modo_ejecucion": retorno.modo_ejecucion}
        except BaseException as exc:  # sin reintento
            ejecucion["excepcion"] = f"{type(exc).__name__}: {exc}"
            ejecucion["traza"] = traceback.format_exc()[-3000:]
        finally:
            shutil.rmtree(temporal, ignore_errors=True)
            ejecucion["fin_utc"] = _ahora()
        conciliadas.append(factura_id)
        _, despues = _ejecutar_lectura(_leer_tanda)
        ejecucion["real"] = _factura(factura_id)
        motivos = []
        retorno_esperado = {"facturas_conciliacion_reclamadas": 1, "documentos_reclamados": 0,
                            "modo_ejecucion": MODO_CLAIM}
        if "excepcion" in ejecucion:
            motivos.append("EXCEPCION")
        elif ejecucion["retorno"] != retorno_esperado:
            motivos.append(f"RETORNO_INESPERADO:{ejecucion['retorno']}!={retorno_esperado}")
        motivos += comprobar_resultado(plan_factura["prevision"], inmediata["estado_previsto"], ejecucion["real"])
        motivos += diferencias_filas(anterior["filas"], despues["filas"], {factura_id})
        ejecucion["motivos"] = motivos
        _escribir(directorio / f"ejecucion_{i + 1:02d}.json", ejecucion)
        if motivos:
            return cerrar("PARADA", motivos)
        anterior = despues

    problemas = postcheck()
    return cerrar("TANDA_OK" if not problemas else "PARADA", problemas)


if __name__ == "__main__":
    modo, *args = sys.argv[1:]
    if modo == "plan":
        sys.exit(plan(_salida_fuera_del_repo(args[0])))
    elif modo == "tanda":
        sys.exit(tanda(int(args[0]), Path(args[1]), _salida_fuera_del_repo(args[2])))
    else:
        raise SystemExit("modo desconocido")
