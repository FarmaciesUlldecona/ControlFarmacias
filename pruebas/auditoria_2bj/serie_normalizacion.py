"""Hito 2BJ: serie supervisada de normalizacion (plan READ_ONLY y tandas de ``ejecutar_una_manual()``).

Uso (identidad Usuari; lecturas con CONTROLFARMACIAS_SUPABASE_DB_URL y la puerta READ_ONLY del 2AT; escrituras
solo con el cliente del .env y el compositor manual del 2AP; sin Farmatic):
  python -B pruebas/auditoria_2bj/serie_normalizacion.py plan <plan.json> [mirror]
  python -B pruebas/auditoria_2bj/serie_normalizacion.py tanda <n> <plan.json> <directorio_tanda>

Decisiones de Pio (2026-10-30, ``pruebas/auditoria_2bj/DISENO.md``): la primera tanda tiene como maximo 5
ejecuciones y las siguientes como maximo 20; cada tanda termina al persistir un documento Alliance; los defectos
de extraccion previstos por el plan consumen intentos (R3) y no son parada; ejecuta Claude con confirmacion
expresa de Pio por tanda.

``plan`` no escribe nada: lee la cola en el ordering oficial (el del nucleo de la migracion 16, modo
MANUAL_ONE_SHOT) y predice el resultado de cada documento con la cadena oficial en memoria sobre el PDF del
mirror con el mismo SHA (``pruebas/auditoria_2ay/banco_extraccion.py``): ``ALLIANCE`` (facturas, numeros y
totales), ``NO_SOPORTADO``, ``DEFECTO`` o ``SIN_PREDICCION`` (no esta en el mirror o no se reconoce el motivo).

``tanda`` (guard exclusivo por tanda, sin reintentos): preflight READ_ONLY y snapshot por fila; para cada
ejecucion, puertas (flags y configuracion, 25, 27 desde el 2BL, 0 NORMALIZANDO, 0 huerfanos, 0 locks/claims/workers, tareas a
60 min o mas, n.o 1 con prediccion y mismo SHA que en el plan), UNA llamada a ``ejecutar_una_manual()`` y
comprobacion (estado previsto, facturas del plan, filas cambiadas solo del documento). Cualquier desviacion
-> PARADA. Al final, y tambien al parar (2BK), postcheck 2AX por fila de toda la tanda. Salidas fuera del
repositorio.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import traceback
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import (  # noqa: E402
    PROJECT_REF, _ejecutar_lectura, _escribir, _operacion, _puertas_operacion, _salida_fuera_del_repo)
from src.facturas.runtime_supabase.clasificacion_fallos import (  # noqa: E402
    DEFECTO_DOCUMENTO, NO_SOPORTADO, clasificar_fallo)


def _cargar(nombre: str, ruta: str):
    spec = importlib.util.spec_from_file_location(nombre, ROOT / ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


preflight_2bdd = _cargar("preflight_2bdd_2bj", "pruebas/auditoria_2bd_d/preflight_readonly.py")
banco = _cargar("banco_2ay_2bj", "pruebas/auditoria_2ay/banco_extraccion.py")

_tareas = preflight_2bdd._tareas
_puertas_tareas = preflight_2bdd._puertas_tareas

WORKER_BASE = "cf-2bj-serie"  # 2BI: el worker añade un sufijo unico por ejecucion
MAX_PRIMERA = 5
MAX_TANDA = 20
GRACIA_HUERFANOS = "30 minutes"

# Ordering oficial del nucleo de la migracion 16 en modo MANUAL_ONE_SHOT (salta solo el interruptor global).
SQL_COLA = (
    "select d.id::text, d.archivo_hash, d.fecha_importacion::text, d.estado_lectura, "
    "d.intentos_fallo_normalizacion, md5(to_jsonb(d)::text) "
    "from public.documentos_facturas d cross join public.cf_configuracion c "
    "where c.id = true and d.farmacia = any(c.farmacias_habilitadas) "
    "and d.estado_lectura in ('PENDIENTE','ERROR') "
    "and coalesce(d.proximo_reintento_at,'-infinity'::timestamptz) <= now() "
    "and coalesce(d.bloqueado_hasta,'-infinity'::timestamptz) <= now() "
    "order by (d.reprocesar_solicitado_at is not null) desc, d.fecha_importacion, d.id")
SQL_COLA_TOTAL = (
    "select d.id::text, d.archivo_hash, d.fecha_importacion::text, d.estado_lectura, "
    "d.intentos_fallo_normalizacion from public.documentos_facturas d cross join public.cf_configuracion c "
    "where c.id = true and d.farmacia = any(c.farmacias_habilitadas) and d.estado_lectura in ('PENDIENTE','ERROR') "
    "order by (d.reprocesar_solicitado_at is not null) desc, d.fecha_importacion, d.id")


# Marcas de la 27 (2BL): la funcion de repeticion existe y la usan los dos nucleos y el envoltorio de 7 parametros.
# Por nombre (2BM): desde la 28 el nucleo de normalizacion que la usa es el de 9 parametros.
SQL_MARCAS_27 = (
    "select to_regprocedure('public.cf_ejecucion_persistida(uuid,text)') is not null and coalesce(("
    "select count(distinct p.proname) = 3 from pg_proc p "
    "where p.pronamespace = 'public'::regnamespace and p.proname in ("
    "'cf_persistir_normalizacion_nucleo', 'cf_persistir_documento_multifactura_nucleo', "
    "'cf_persistir_documento_multifactura') and position('cf_ejecucion_persistida' in p.prosrc) > 0), false)")


def _ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --------------------------------------------------------------------------- prediccion

def prediccion_desde_analisis(analisis: dict) -> dict:
    """Traduce el analisis en memoria de la cadena oficial al resultado que registrara el worker real."""
    etapa, motivo = analisis.get("etapa_detencion"), analisis.get("motivo")
    if etapa == "PREVIO_A_PERSISTIR_OK":
        facturas = [{"numero": f.get("numero"), "total": str(f.get("total")), "autorizable": f.get("autorizable")}
                    for f in analisis.get("facturas_normalizadas", [])]
        return {"clase": "ALLIANCE", "facturas": facturas,
                "completa": bool(facturas) and all(f["autorizable"] for f in facturas)}
    if etapa == "EXTRACCION_MOTOR":
        real = "EXTRACCION_LOCAL_ERROR"
    elif etapa == "RECONOCIMIENTO":
        real = "REQUIERE_OCR_O_LUNA_NO_AUTORIZADO" if motivo == "PENDIENTE_OCR" else "PROVEEDOR_NO_RECONOCIDO"
    elif etapa in ("AUTORIDAD", "COMPLETITUD", "SEGMENTACION_MULTIFACTURA", "EXTRACCION"):
        real = motivo
    else:
        return {"clase": "SIN_PREDICCION", "motivo": motivo, "etapa": etapa}
    clase = clasificar_fallo(None, real)
    if clase == NO_SOPORTADO:
        return {"clase": "NO_SOPORTADO", "motivo": real}
    if clase == DEFECTO_DOCUMENTO:
        return {"clase": "DEFECTO", "motivo": real}
    return {"clase": "SIN_PREDICCION", "motivo": real, "etapa": etapa}


def _indice_mirror(mirror: Path) -> dict[str, Path]:
    indice: dict[str, Path] = {}
    for p in sorted(mirror.rglob("*")):
        if p.is_file() and p.suffix.lower() == ".pdf":
            indice.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), p)
    return indice


def plan(salida: Path, mirror: Path = banco.DRIVE) -> int:
    _, cola = _ejecutar_lectura(lambda lector: {"cola": [list(r) for r in lector.filas(SQL_COLA_TOTAL)]})
    indice = _indice_mirror(mirror)
    documentos = []
    for documento_id, sha, fecha, estado, intentos in cola["cola"]:
        ruta = indice.get(sha)
        if ruta is None:
            prediccion = {"clase": "SIN_PREDICCION", "motivo": "AUSENTE_DEL_MIRROR"}
        else:
            try:
                prediccion = prediccion_desde_analisis(banco._analizar(str(ruta)))
            except Exception as exc:
                prediccion = {"clase": "SIN_PREDICCION", "motivo": f"ANALISIS:{type(exc).__name__}"}
        documentos.append({"id": documento_id, "archivo_hash": sha, "fecha_importacion": fecha,
                           "estado_lectura": estado, "intentos": intentos, "ruta_mirror": str(ruta) if ruta else None,
                           "prediccion": prediccion})
    resumen: dict = {}
    for d in documentos:
        resumen[d["prediccion"]["clase"]] = resumen.get(d["prediccion"]["clase"], 0) + 1
    datos = {"hito": "2BJ", "capturado_utc": cola.get("capturado_utc"), "project_ref": cola.get("project_ref"),
             "transaction_read_only": cola.get("transaction_read_only"), "mirror": str(mirror),
             "resumen": resumen, "documentos": documentos}
    sha = _escribir(salida, datos)
    print(json.dumps({"resumen": resumen, "documentos": len(documentos),
                      "alliance": [(d["id"], [f["numero"] for f in d["prediccion"]["facturas"]])
                                   for d in documentos if d["prediccion"]["clase"] == "ALLIANCE"]},
                     ensure_ascii=False, indent=1))
    print("sha256", sha)
    return 0


# --------------------------------------------------------------------------- lecturas de la tanda

def _tablas(lector) -> dict[str, dict]:
    """Tablas de public con su clave (id o fila) y la expresion que da su documento (si la hay)."""
    columnas: dict[str, set[str]] = {}
    for tabla, columna in lector.filas(
            "select table_name, column_name from information_schema.columns where table_schema = 'public' "
            "and table_name in (select table_name from information_schema.tables where table_schema = 'public' "
            "and table_type = 'BASE TABLE') order by 1, 2"):
        columnas.setdefault(tabla, set()).add(columna)
    tablas = {}
    for tabla, cols in sorted(columnas.items()):
        if tabla == "documentos_facturas":
            dueno = "t.id::text"
        elif "documento_id" in cols and "factura_id" in cols:
            dueno = ("coalesce(t.documento_id::text, (select f.documento_id::text from public.facturas f "
                     "where f.id = t.factura_id))")
        elif "documento_id" in cols:
            dueno = "t.documento_id::text"
        elif "factura_id" in cols and tabla not in ("conciliaciones", "conciliacion_albaranes_reservados"):
            dueno = "(select f.documento_id::text from public.facturas f where f.id = t.factura_id)"
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
    out["migracion_25"] = lector.valor(
        "select to_regprocedure('public.cf_huerfanos_normalizacion(interval)') is not null")
    # 2BL (decision de Pio): la serie exige la 27; un fallo de persistencia no debe bloquear el reintento.
    out["migracion_27"] = lector.valor(SQL_MARCAS_27)
    out["normalizando"] = lector.valor(
        "select count(*) from public.documentos_facturas where estado_lectura = 'NORMALIZANDO'")
    out["claims_normalizacion"] = lector.valor(
        "select count(*) from public.documentos_facturas where bloqueado_por is not null or bloqueado_hasta > now()")
    out["huerfanos"] = ([list(r) for r in lector.filas(
        f"select documento_id::text, prevision from public.cf_huerfanos_normalizacion('{GRACIA_HUERFANOS}')")]
        if out["migracion_25"] else None)
    out["max_intentos"] = lector.valor("select normalizacion_max_intentos from public.cf_configuracion where id")
    out["cola"] = [list(r) for r in lector.filas(SQL_COLA)]
    return out


def _leer_tanda(lector) -> dict:
    return {**_estado_operativo(lector), "filas": _filas(lector)}


def _documento(documento_id: str):
    def leer(lector):
        [fila] = lector.filas(
            "select estado_lectura, estado_persistencia, intentos_fallo_normalizacion, ultima_clase_fallo, "
            f"ultimo_error_codigo from public.documentos_facturas where id = '{documento_id}'")
        facturas = [[r[0], str(r[1])] for r in lector.filas(
            f"select numero_factura, importe_total from public.facturas where documento_id = '{documento_id}' "
            "order by numero_factura")]
        return {"estado_lectura": fila[0], "estado_persistencia": fila[1], "intentos": fila[2],
                "ultima_clase_fallo": fila[3], "ultimo_error_codigo": fila[4], "facturas": facturas}
    return _ejecutar_lectura(leer)[1]


# --------------------------------------------------------------------------- comprobaciones (sin conexion)

def puertas(estado: dict, plan_docs: dict, referencia: dict, tareas: dict, ahora: dt.datetime) -> list[str]:
    fallos = list(_puertas_operacion(estado["operacion"]))
    if estado["cf_configuracion"] != referencia["cf_configuracion"]:
        fallos.append("CONFIGURACION_DISTINTA_DEL_PREFLIGHT")
    if not estado["migracion_25"]:
        fallos.append("MIGRACION_25_AUSENTE")
    if not estado["migracion_27"]:
        fallos.append("MIGRACION_27_AUSENTE")
    if estado["normalizando"]:
        fallos.append(f"DOCUMENTOS_EN_NORMALIZANDO:{estado['normalizando']}")
    if estado["claims_normalizacion"]:
        fallos.append(f"CLAIMS_NORMALIZACION:{estado['claims_normalizacion']}")
    if estado["huerfanos"]:
        fallos.append(f"HUERFANOS:{len(estado['huerfanos'])}")
    fallos += _puertas_tareas(tareas, ahora)
    if not estado["cola"]:
        fallos.append("COLA_VACIA")
    else:
        documento_id, sha = estado["cola"][0][0], estado["cola"][0][1]
        previsto = plan_docs.get(documento_id)
        if previsto is None:
            fallos.append(f"NUMERO_1_FUERA_DEL_PLAN:{documento_id}")
        elif previsto["archivo_hash"] != sha:
            fallos.append(f"NUMERO_1_SHA_DISTINTO_DEL_PLAN:{documento_id}")
        elif previsto["prediccion"]["clase"] == "SIN_PREDICCION":
            fallos.append(f"NUMERO_1_SIN_PREDICCION:{documento_id}:{previsto['prediccion'].get('motivo')}")
    return fallos


def resultado_esperado(prediccion: dict, intentos_antes: int, max_intentos: int) -> dict:
    clase = prediccion["clase"]
    if clase == "ALLIANCE":
        return {"estado_lectura": "NORMALIZADA", "estado_persistencia": "COMPLETA",
                "facturas": sorted([f["numero"], str(Decimal(f["total"]).quantize(Decimal("0.01")))]
                                   for f in prediccion["facturas"] if f["autorizable"])}
    if clase == "NO_SOPORTADO":
        return {"estado_lectura": "PROVEEDOR_NO_SOPORTADO", "ultima_clase_fallo": NO_SOPORTADO,
                "intentos": intentos_antes, "facturas": []}
    return {"estado_lectura": "REVISION" if intentos_antes + 1 >= max_intentos else "ERROR",
            "ultima_clase_fallo": DEFECTO_DOCUMENTO, "intentos": intentos_antes + 1, "facturas": []}


def comprobar_resultado(esperado: dict, real: dict) -> list[str]:
    real = {**real, "facturas": sorted([n, str(Decimal(t).quantize(Decimal("0.01")))] for n, t in real["facturas"])}
    return [f"RESULTADO_INESPERADO:{k}:{esperado[k]}!={real.get(k)}" for k in esperado if real.get(k) != esperado[k]]


def diferencias_filas(antes: dict, despues: dict, documentos: set[str], cambiables: set[str]) -> list[str]:
    """Criterio 2AX por fila: solo filas nuevas de ``documentos`` y cambios en sus filas de ``cambiables``."""
    problemas = []
    for tabla in sorted(set(antes) | set(despues)):
        a, b = antes.get(tabla, {}), despues.get(tabla, {})
        for clave in set(b) - set(a):
            if b[clave][1] not in documentos:
                problemas.append(f"FILA_NUEVA_AJENA:{tabla}:{clave}")
        for clave in set(a) - set(b):
            problemas.append(f"FILA_BORRADA:{tabla}:{clave}")
        for clave in set(a) & set(b):
            if a[clave][0] != b[clave][0] and not (tabla in cambiables and b[clave][1] in documentos):
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
    """Cliente del .env con project ref productivo y rol de servicio demostrados (patron 2AO rev3)."""
    from dotenv import dotenv_values
    from src.supabase_client.conexion_supabase import obtener_cliente_supabase

    env = dotenv_values(ROOT / ".env")
    ref = (urlparse(env.get("SUPABASE_URL", "")).hostname or "").split(".")[0]
    if ref != PROJECT_REF or _rol_clave(env.get("SUPABASE_KEY", "")) != "service" + "_role":
        raise SystemExit("CLIENTE_NO_DEMOSTRADO")
    return obtener_cliente_supabase()


def _ejecutar_una(cliente, directorio: Path):
    """UNA llamada a ``ejecutar_una_manual()`` con el compositor manual del 2AP."""
    from src.facturas.runtime_supabase.compositor_manual import construir_worker_manual_productivo
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

    configuracion = RepositorioRuntimeSupabase(cliente).obtener_configuracion()
    return construir_worker_manual_productivo(cliente, configuracion, WORKER_BASE, directorio).ejecutar_una_manual()


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
    plan_docs = {d["id"]: d for d in plan_datos["documentos"]}
    directorio.mkdir(parents=True, exist_ok=True)
    guard = directorio / "tanda.guard"
    with open(guard, "x", encoding="utf-8") as g:  # exclusivo: una sola ejecucion por directorio de tanda
        g.write(f"{_ahora()} n={n} plan={hashlib.sha256(plan_ruta.read_bytes()).hexdigest()}\n")
    registro: dict = {"hito": "2BJ", "n": n, "maximo": maximo, "plan": str(plan_ruta),
                      "plan_sha256": hashlib.sha256(plan_ruta.read_bytes()).hexdigest(),
                      "inicio_utc": _ahora(), "ejecuciones": []}
    salida = directorio / "tanda.json"
    pre: dict = {}
    reclamados: list[str] = []
    alliance = False

    def postcheck() -> list[str]:
        """2AX por fila de toda la tanda frente al snapshot previo (tambien al parar, 2BK)."""
        _, post = _ejecutar_lectura(_leer_tanda)
        _escribir(directorio / "snapshot_post.json", post)
        problemas = diferencias_filas(pre["filas"], post["filas"], set(reclamados), {"documentos_facturas"})
        if post["normalizando"] or post["huerfanos"]:
            problemas.append("NORMALIZANDO_O_HUERFANOS_TRAS_LA_TANDA")
        if post["cf_configuracion"] != pre["cf_configuracion"] or post["operacion"]["flags"] != pre["operacion"]["flags"]:
            problemas.append("CONFIGURACION_U_OPERACION_DISTINTA")
        registro["postcheck"] = {"veredicto": "POSTCHECK_OK" if not problemas else "POSTCHECK_REVISAR",
                                 "problemas": problemas, "documentos": list(reclamados), "corte_alliance": alliance}
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
            "ejecuciones": [(e["documento_id"], e.get("clase"), e.get("real", {}).get("estado_lectura"))
                            for e in registro["ejecuciones"]]}, ensure_ascii=False, indent=1, default=str))
        return 0 if veredicto == "TANDA_OK" else 3

    pre.update(_ejecutar_lectura(_leer_tanda)[1])
    _escribir(directorio / "snapshot_pre.json", pre)
    registro["preflight"] = {k: pre.get(k) for k in ("project_ref", "capturado_utc", "transaction_read_only")}
    try:
        cliente = _cliente()
    except SystemExit as exc:
        return cerrar("PARADA", [str(exc)])
    anterior = pre
    for i in range(n):
        tareas = _tareas()
        fallos = puertas(anterior, plan_docs, pre, tareas, dt.datetime.now(dt.timezone.utc))
        if fallos == ["COLA_VACIA"] and i > 0:
            break  # cola agotada a mitad de tanda: se cierra con el postcheck
        if fallos:
            return cerrar("PARADA", fallos)
        documento_id = anterior["cola"][0][0]
        previsto = plan_docs[documento_id]["prediccion"]
        esperado = resultado_esperado(previsto, anterior["cola"][0][4], anterior["max_intentos"])
        ejecucion = {"documento_id": documento_id, "clase": previsto["clase"], "esperado": esperado,
                     "inicio_utc": _ahora()}
        registro["ejecuciones"].append(ejecucion)
        temporal = Path(tempfile.mkdtemp(prefix="cf2bj_"))
        try:
            retorno = _ejecutar_una(cliente, temporal)
            ejecucion["retorno"] = {"documentos_reclamados": retorno.documentos_reclamados,
                                    "modo_ejecucion": retorno.modo_ejecucion}
        except BaseException as exc:  # sin reintento
            ejecucion["excepcion"] = f"{type(exc).__name__}: {exc}"
            ejecucion["traza"] = traceback.format_exc()[-3000:]
        finally:
            shutil.rmtree(temporal, ignore_errors=True)
            ejecucion["fin_utc"] = _ahora()
        reclamados.append(documento_id)
        _, despues = _ejecutar_lectura(_leer_tanda)
        ejecucion["real"] = _documento(documento_id)
        motivos = []
        # ``documentos_reclamados`` cuenta las normalizaciones persistidas: 1 si el Alliance persiste, 0 si el
        # documento falla y se registra su fallo (R2/R3). El documento reclamado lo prueban su estado y las filas.
        retorno_esperado = {"documentos_reclamados": int(previsto["clase"] == "ALLIANCE"),
                            "modo_ejecucion": "MANUAL_ONE_SHOT"}
        if "excepcion" in ejecucion:
            motivos.append("EXCEPCION")
        elif ejecucion["retorno"] != retorno_esperado:
            motivos.append(f"RETORNO_INESPERADO:{ejecucion['retorno']}!={retorno_esperado}")
        if despues["normalizando"]:
            motivos.append(f"HUERFANO:{despues['normalizando']}")
        motivos += comprobar_resultado(esperado, ejecucion["real"])
        if previsto["clase"] == "ALLIANCE" and not previsto["completa"]:
            motivos.append("ALLIANCE_CON_FACTURAS_NO_AUTORIZABLES")
        if previsto["clase"] not in ("ALLIANCE", "NO_SOPORTADO", "DEFECTO"):
            motivos.append(f"CLASE_NO_EJECUTABLE:{previsto['clase']}")
        motivos += diferencias_filas(anterior["filas"], despues["filas"], {documento_id}, {"documentos_facturas"})
        ejecucion["motivos"] = motivos
        _escribir(directorio / f"ejecucion_{i + 1:02d}.json", {k: v for k, v in ejecucion.items()})
        if motivos:
            return cerrar("PARADA", motivos)
        anterior = despues
        if previsto["clase"] == "ALLIANCE":
            alliance = True
            break  # corte: postcheck propio de cada Alliance persistido

    problemas = postcheck()
    return cerrar("TANDA_OK" if not problemas else "PARADA", problemas)


if __name__ == "__main__":
    modo, *args = sys.argv[1:]
    if modo == "plan":
        sys.exit(plan(_salida_fuera_del_repo(args[0]), Path(args[1]) if len(args) > 1 else banco.DRIVE))
    elif modo == "tanda":
        sys.exit(tanda(int(args[0]), Path(args[1]), _salida_fuera_del_repo(args[2])))
    else:
        raise SystemExit("modo desconocido")
