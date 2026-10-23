"""Hito 2BD-D: preflight, backup, postcheck y prueba funcional ESTRICTAMENTE READ_ONLY de la migracion 22.

Uso:
  python -B pruebas/auditoria_2bd_d/preflight_readonly.py precondiciones <salida.json>
  python -B pruebas/auditoria_2bd_d/preflight_readonly.py local <variante 21|22> <salida.json>
  python -B pruebas/auditoria_2bd_d/preflight_readonly.py alcance <local_21.json> <local_22.json> <salida.json>
  python -B pruebas/auditoria_2bd_d/preflight_readonly.py remoto <pre|post> <columnas_declaradas.json> <salida.json>
  python -B pruebas/auditoria_2bd_d/preflight_readonly.py comparar_pre <pre.json> <local_21.json> <alcance.json> <postcheck_2bad.json> <salida.json>
  python -B pruebas/auditoria_2bd_d/preflight_readonly.py comparar <pre.json> <post.json> <local_22.json> <alcance.json> <salida.json>
  python -B pruebas/auditoria_2bd_d/preflight_readonly.py funcional <salida.json>

Patron del 2BA-D (``pruebas/auditoria_2ba_d/preflight_readonly.py``) con la puerta certificada del 2AT:
project ref demostrado, sesion READ_ONLY REPEATABLE READ, solo SELECT/WITH, rollback. Salidas FUERA del
repositorio. Sin DML, sin RPC de escritura, sin Farmatic.

El alcance de la 22 no se escribe a mano: es el conjunto de objetos cuya huella difiere entre las
referencias locales 21 y 22 (``alcance``). Tareas programadas: solo ``Get-ScheduledTaskInfo``.
"""
from __future__ import annotations

import ast
import base64
import datetime as _dt
import importlib.util
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import (  # noqa: E402
    MARGEN_TAREAS, TAREAS_ESPERADAS, _Lector, _ejecutar_lectura, _escribir, _operacion, _puertas_operacion,
    _salida_fuera_del_repo)

_spec = importlib.util.spec_from_file_location("preflight_2azd", ROOT / "pruebas/auditoria_2az_d/preflight_readonly.py")
azd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(azd)

TABLAS_HUELLA = azd.TABLAS_HUELLA
SQL_ESQUEMA = azd.SQL_ESQUEMA
_md5 = azd._md5
RESERVAS = "conciliacion_albaranes_reservados"
CAMBIOS = "albaranes_cambios"
COLUMNA_NUEVA = "id_recepcion"
SCRIPT_DESPLIEGUE = ROOT / "pruebas/auditoria_2bd/desplegar_22.py"
# 267009 = SCHED_S_TASK_RUNNING
RESULTADO_EN_EJECUCION = 267009

MARCAS = (
    "select jsonb_build_object("
    "'19_anon_sin_select_facturas', not has_table_privilege('anon','public.facturas','SELECT'),"
    "'19_service_role_sin_update_albaranes', not has_table_privilege('service_role','public.albaranes','UPDATE'),"
    "'20_rpc_enriquecer', to_regprocedure('public.cf_enriquecer_factura(uuid,text,text,jsonb)') is not null,"
    f"'21_tabla_reservas', to_regclass('public.{RESERVAS}') is not null,"
    f"'22_tabla_cambios', to_regclass('public.{CAMBIOS}') is not null,"
    "'22_columna_recepcion', exists(select 1 from information_schema.columns where table_schema='public' "
    f"  and table_name='albaranes' and column_name='{COLUMNA_NUEVA}'),"
    "'22_rpc_resincronizar', to_regprocedure('public.cf_resincronizar_albaran(text,bigint,jsonb,text,text)') is not null,"
    "'22_rpc_ausente', to_regprocedure('public.cf_registrar_albaran_ausente(text,bigint,text,text)') is not null)::text"
)
MARCAS_22 = ("22_tabla_cambios", "22_columna_recepcion", "22_rpc_resincronizar", "22_rpc_ausente")

SQL_RESERVAS = (
    "select coalesce(jsonb_agg(jsonb_build_object('albaran_farmacia', r.albaran_farmacia, "
    "'albaran_id_contador', r.albaran_id_contador, 'factura_id', r.factura_id::text, "
    "'conciliacion_id', r.conciliacion_id::text, 'orden', r.orden) "
    "order by r.albaran_farmacia, r.albaran_id_contador), '[]'::jsonb)::text "
    f"from public.{RESERVAS} r")

SQL_VIGENTES = (
    "select coalesce(jsonb_agg(jsonb_build_object('albaran_farmacia', d.albaran_farmacia, "
    "'albaran_id_contador', d.albaran_id_contador, 'factura_id', c.factura_id::text, "
    "'conciliacion_id', c.id::text, 'orden', d.orden) "
    "order by d.albaran_farmacia, d.albaran_id_contador, c.id, d.orden), '[]'::jsonb)::text "
    "from public.conciliaciones c join public.conciliacion_detalles d on d.conciliacion_id = c.id "
    "where c.es_actual and d.albaran_id_contador is not null")


def _clave(r: dict) -> list:
    return [r["albaran_farmacia"], r["albaran_id_contador"], r["factura_id"], r["conciliacion_id"], r["orden"]]


# --------------------------------------------------------------------------- tareas (solo Get-ScheduledTaskInfo)

def _tareas() -> dict:
    nombres = ",".join("'" + n.replace("'", "''") + "'" for n in TAREAS_ESPERADAS)
    ps = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        f"$t = @(foreach ($n in @({nombres})) {{ $i = Get-ScheduledTaskInfo -TaskName $n -ErrorAction Stop;"
        " [pscustomobject]@{ nombre = $n;"
        "  proxima = $(if ($i.NextRunTime) { $i.NextRunTime.ToUniversalTime().ToString('o') } else { $null });"
        "  ultima = $(if ($i.LastRunTime) { $i.LastRunTime.ToUniversalTime().ToString('o') } else { $null });"
        "  resultado = $i.LastTaskResult } });"
        "ConvertTo-Json -InputObject $t -Depth 3"
    )
    codificado = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
                       capture_output=True, timeout=60)
    if r.returncode:
        return {"error": r.stderr.decode("utf-8", "replace").strip()[:500], "tareas": []}
    tareas = json.loads(r.stdout.decode("utf-8-sig") or "[]")
    return {"tareas": tareas if isinstance(tareas, list) else [tareas]}


def _puertas_tareas(info: dict, ahora: _dt.datetime) -> list[str]:
    if "error" in info:
        return [f"TAREAS_NO_DETERMINABLES: {info['error']}"]
    fallos = []
    nombres = {unicodedata.normalize("NFC", t["nombre"]) for t in info["tareas"]}
    for esperada in TAREAS_ESPERADAS:
        if unicodedata.normalize("NFC", esperada) not in nombres:
            fallos.append(f"TAREA_NO_ENCONTRADA: {esperada}")
    for t in info["tareas"]:
        if t.get("resultado") == RESULTADO_EN_EJECUCION:
            fallos.append(f"TAREA_EN_EJECUCION: {t['nombre']}")
        if t.get("proxima"):
            proxima = _dt.datetime.fromisoformat(t["proxima"].replace("Z", "+00:00"))
            if proxima - ahora < MARGEN_TAREAS:
                fallos.append(f"TAREA_A_MENOS_DE_60_MIN: {t['nombre']} {t['proxima']}")
    return fallos


# --------------------------------------------------------------------------- precondiciones (norma 2AX)

def precondiciones(salida: Path) -> int:
    """La consulta de precondiciones de ``desplegar_22.py`` (texto exacto, extraido por ast) en READ_ONLY."""
    arbol = ast.parse(SCRIPT_DESPLIEGUE.read_text(encoding="utf-8"))
    [consulta] = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"
                  and n.args and "has_table_privilege" in ast.unparse(n.args[0])]
    sql = eval(compile(ast.Expression(consulta.args[0]), str(SCRIPT_DESPLIEGUE), "eval"), {})
    _, datos = _ejecutar_lectura(lambda lector: {"precondiciones": list(lector.fila(sql))})
    datos["sql"] = sql
    datos["veredicto"] = "PRECONDICIONES_OK" if all(datos["precondiciones"]) else "PRECONDICIONES_NO_CUMPLIDAS"
    print(json.dumps({k: datos[k] for k in ("project_ref", "capturado_utc", "transaction_read_only",
                                            "precondiciones", "veredicto")}, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if all(datos["precondiciones"]) else 3


# --------------------------------------------------------------------------- alcance (sin conexion)

def alcance(local21_ruta: Path, local22_ruta: Path, salida: Path) -> int:
    a = json.loads(local21_ruta.read_text(encoding="utf-8"))["esquema"]["objetos"]
    b = json.loads(local22_ruta.read_text(encoding="utf-8"))["esquema"]["objetos"]
    claves = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    datos = {"alcance_22": claves, "nuevos": sorted(set(b) - set(a)), "eliminados": sorted(set(a) - set(b))}
    print(json.dumps(datos, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if claves and not datos["eliminados"] else 3


# --------------------------------------------------------------------------- remoto

def remoto(fase: str, declaradas_ruta: Path, salida: Path) -> int:
    assert fase in ("pre", "post")
    declaradas = json.loads(declaradas_ruta.read_text(encoding="utf-8"))
    tareas = _tareas()
    ahora_tareas = _dt.datetime.now(_dt.timezone.utc)

    def leer(lector: _Lector) -> dict:
        out = {"marcas": lector.json(MARCAS), "esquema": lector.json(SQL_ESQUEMA)}
        out.update(_operacion(lector))
        out["cf_configuracion_completa"] = lector.json("select to_jsonb(c)::text from public.cf_configuracion c where id")
        out["conteos_extra"] = {t: lector.valor(f"select count(*) from public.{t}") for t in TABLAS_HUELLA}
        out["locks_factura"] = lector.valor(
            "select count(*) from public.facturas where conciliacion_bloqueado_hasta > now()")
        out["lineas_vigentes_con_albaran"] = lector.json(SQL_VIGENTES)
        out["reservas"] = lector.json(SQL_RESERVAS)
        out["duplicados_farmacia_id_contador"] = lector.valor(
            "select count(*) from (select farmacia, id_contador from public.albaranes group by 1, 2 "
            "having count(*) > 1) x")
        if out["marcas"]["22_tabla_cambios"]:
            out["albaranes_cambios"] = lector.valor(f"select count(*) from public.{CAMBIOS}")
        if out["marcas"]["22_columna_recepcion"]:
            out["albaranes_con_recepcion"] = lector.valor(
                f"select count(*) from public.albaranes where {COLUMNA_NUEVA} is not null")
        reales = azd._columnas(lector)
        esperadas_nuevas = {"albaranes": [COLUMNA_NUEVA]} if fase == "post" else {}
        out["columnas_huella"] = {
            t: {"declaradas_ausentes": sorted(set(declaradas[t]) - set(reales[t])),
                "reales_no_declaradas": sorted(set(reales[t]) - set(declaradas[t]) - set(esperadas_nuevas.get(t, [])))}
            for t in TABLAS_HUELLA}
        huellas, volcado = {}, {}
        for tabla in TABLAS_HUELLA:
            lista = ", ".join(f"t.{c}" for c in declaradas[tabla] if c in reales[tabla])
            filas = lector.filas(f"select t.id::text, md5(to_jsonb(r)::text), to_jsonb(r)::text from public.{tabla} t "
                                 f"cross join lateral (select {lista}) r order by t.id")
            huellas[tabla] = {f[0]: f[1] for f in filas}
            volcado[tabla] = {f[0]: f[2] for f in filas}
        out["huellas_por_fila"] = huellas
        out["volcado"] = volcado
        return out

    _, datos = _ejecutar_lectura(leer)
    datos["fase"] = fase
    datos["columnas_declaradas"] = declaradas
    datos["tareas"] = tareas
    datos["tareas_consultadas_utc"] = ahora_tareas.isoformat()
    marcas = datos["marcas"]
    fallos = [f"MARCA_FALSA:{k}" for k, v in marcas.items() if k not in MARCAS_22 and v is not True]
    if fase == "pre":
        fallos += [f"MIGRACION_22_YA_PRESENTE:{k}" for k in MARCAS_22 if marcas[k]]
        fallos += _puertas_tareas(tareas, ahora_tareas)
    else:
        fallos += [f"MIGRACION_22_AUSENTE:{k}" for k in MARCAS_22 if not marcas[k]]
        if datos.get("albaranes_cambios") != 0:
            fallos.append(f"HISTORIAL_NO_VACIO:{datos.get('albaranes_cambios')}")
        if datos.get("albaranes_con_recepcion") != 0:
            fallos.append(f"RECEPCIONES_CARGADAS:{datos.get('albaranes_con_recepcion')}")
    if datos["duplicados_farmacia_id_contador"]:
        fallos.append(f"DUPLICADOS_FARMACIA_ID_CONTADOR:{datos['duplicados_farmacia_id_contador']}")
    if sorted(_clave(r) for r in datos["reservas"]) != sorted(_clave(r) for r in datos["lineas_vigentes_con_albaran"]):
        fallos.append("RESERVAS_DISTINTAS_DE_VIGENTES_CON_ALBARAN")
    if datos["esquema"]["owner_distinto_de_postgres"]:
        fallos.append(f"OWNER_DISTINTO_DE_POSTGRES:{datos['esquema']['owner_distinto_de_postgres']}")
    fallos += _puertas_operacion(datos)
    if datos["locks_factura"]:
        fallos.append(f"LOCKS_FACTURA:{datos['locks_factura']}")
    for t, dif in datos["columnas_huella"].items():
        if dif["declaradas_ausentes"] or dif["reales_no_declaradas"]:
            fallos.append(f"COLUMNAS_HUELLA_NO_COINCIDEN:{t}:{dif}")
    datos["fallos"] = fallos
    datos["veredicto"] = ("PREFLIGHT_OK" if fase == "pre" else "LECTURA_POST_OK") if not fallos else "PARADO"
    sha = _escribir(salida, datos)
    resumen = {k: datos.get(k) for k in ("project_ref", "capturado_utc", "current_user", "marcas", "flags",
                                         "tolerancia_conciliacion", "locks_documentos", "locks_factura",
                                         "claims_conciliacion", "normalizando", "workers",
                                         "facturas_por_estado_conciliacion_cf", "conteos_extra",
                                         "duplicados_farmacia_id_contador", "albaranes_cambios",
                                         "albaranes_con_recepcion", "tareas", "fallos", "veredicto")}
    resumen["lineas_vigentes_con_albaran"] = len(datos["lineas_vigentes_con_albaran"])
    resumen["reservas"] = len(datos["reservas"])
    resumen["objetos_publicos"] = len(datos["esquema"]["objetos"])
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


# --------------------------------------------------------------------------- comparaciones (sin conexion)

def comparar_pre(pre_ruta: Path, local21_ruta: Path, alcance_ruta: Path, postcheck_2bad_ruta: Path,
                 salida: Path) -> int:
    """Produccion esta en el esquema 21: el alcance de la 22 coincide con la referencia local 21 y todo el
    esquema es igual que tras el postcheck del 2BA-D."""
    pre = json.loads(pre_ruta.read_text(encoding="utf-8"))
    ref = json.loads(local21_ruta.read_text(encoding="utf-8"))["esquema"]["objetos"]
    claves = json.loads(alcance_ruta.read_text(encoding="utf-8"))["alcance_22"]
    bad = json.loads(postcheck_2bad_ruta.read_text(encoding="utf-8"))["esquema"]
    a, b = bad["objetos"], pre["esquema"]["objetos"]
    informe = {
        "alcance_22_igual_a_local_21": {k: _md5(b.get(k)) == _md5(ref.get(k)) for k in claves},
        "objetos_distintos_desde_postcheck_2bad": sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k))),
        "default_acl_igual_que_2bad": bad["default_acl"] == pre["esquema"]["default_acl"],
    }
    ok = (all(informe["alcance_22_igual_a_local_21"].values())
          and not informe["objetos_distintos_desde_postcheck_2bad"] and informe["default_acl_igual_que_2bad"])
    informe["veredicto"] = "ESQUEMA_21_CONFIRMADO" if ok else "ESQUEMA_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


TABLA_ALBARANES = "tabla:albaranes"
# Excepcion aprobada por Pio (2BD-D, 2026-10-23): indices productivos preexistentes (al menos desde 2P)
# que la referencia local no crea. Deben quedar identicos pre/post.
INDICES_PREEXISTENTES_ALBARANES = ("albaranes_fecha_idx", "albaranes_proveedor_idx")


def _albaranes_con_excepcion(pre_obj: dict, post_obj: dict, ref_obj: dict) -> dict:
    """Unico cambio pre->post = columnas (igual a la referencia 22); los dos indices, identicos pre/post;
    el resto del objeto, igual a la referencia 22 sin esos dos indices."""
    def sin_indices(obj: dict) -> dict:
        copia = json.loads(json.dumps(obj))
        for indice in INDICES_PREEXISTENTES_ALBARANES:
            copia["indices"].pop(indice, None)
        return copia

    claves_cambiadas = sorted(k for k in set(pre_obj) | set(post_obj) if pre_obj.get(k) != post_obj.get(k))
    return {
        "unico_cambio_pre_post_es_columnas": claves_cambiadas == ["columnas"],
        "columnas_igual_a_local_22": post_obj.get("columnas") == ref_obj.get("columnas"),
        "indices_preexistentes_identicos_pre_post": all(
            indice in pre_obj["indices"] and pre_obj["indices"][indice] == post_obj["indices"].get(indice)
            for indice in INDICES_PREEXISTENTES_ALBARANES),
        "resto_igual_a_local_22": _md5(sin_indices(post_obj)) == _md5(ref_obj),
    }


def comparar(pre_ruta: Path, post_ruta: Path, local22_ruta: Path, alcance_ruta: Path, salida: Path) -> int:
    """Criterio de postcheck de REGLAS_CRITICAS (2AX) mas datos intactos, con la unica excepcion aprobada
    para los indices preexistentes de albaranes."""
    pre, post = (json.loads(p.read_text(encoding="utf-8")) for p in (pre_ruta, post_ruta))
    ref = json.loads(local22_ruta.read_text(encoding="utf-8"))["esquema"]["objetos"]
    claves = json.loads(alcance_ruta.read_text(encoding="utf-8"))["alcance_22"]
    a, b = pre["esquema"]["objetos"], post["esquema"]["objetos"]
    cambiados = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    excepcion = _albaranes_con_excepcion(a[TABLA_ALBARANES], b[TABLA_ALBARANES], ref[TABLA_ALBARANES])
    c2 = {k: _md5(b.get(k)) == _md5(ref.get(k)) for k in claves if k != TABLA_ALBARANES}
    c2[TABLA_ALBARANES] = all(excepcion.values())
    informe = {
        "c1_solo_cambia_el_alcance": set(cambiados) <= set(claves), "objetos_cambiados": cambiados,
        "c2_alcance_igual_a_local_22": c2,
        "excepcion_albaranes": excepcion,
        "c3_fuera_de_alcance_identicos": all(_md5(a.get(k)) == _md5(b.get(k)) for k in set(a) | set(b)
                                             if k not in claves),
        "default_acl_identico": pre["esquema"]["default_acl"] == post["esquema"]["default_acl"],
        "cf_configuracion_identica": pre["cf_configuracion_completa"] == post["cf_configuracion_completa"],
        "huellas_identicas": {t: pre["huellas_por_fila"][t] == post["huellas_por_fila"][t] for t in TABLAS_HUELLA},
        "operacion_como_antes": {k: pre[k] == post[k] for k in ("flags", "locks_documentos", "claims_conciliacion",
                                                                 "normalizando", "workers", "locks_factura")},
        "reservas_pre_igual_post": sorted(_clave(r) for r in pre["reservas"]) == sorted(_clave(r) for r in post["reservas"]),
        "reservas": len(post["reservas"]),
        "historial_vacio": post.get("albaranes_cambios") == 0,
        "recepciones_sin_cargar": post.get("albaranes_con_recepcion") == 0,
    }
    for t in TABLAS_HUELLA:
        if not informe["huellas_identicas"][t]:
            x, y = pre["huellas_por_fila"][t], post["huellas_por_fila"][t]
            informe.setdefault("diferencias_huella", {})[t] = {
                "nuevas": sorted(set(y) - set(x))[:50], "borradas": sorted(set(x) - set(y))[:50],
                "cambiadas": sorted(k for k in set(x) & set(y) if x[k] != y[k])[:50]}
    ok = (informe["c1_solo_cambia_el_alcance"] and all(informe["c2_alcance_igual_a_local_22"].values())
          and informe["c3_fuera_de_alcance_identicos"] and informe["default_acl_identico"]
          and informe["cf_configuracion_identica"] and all(informe["huellas_identicas"].values())
          and all(informe["operacion_como_antes"].values()) and informe["reservas_pre_igual_post"]
          and informe["historial_vacio"] and informe["recepciones_sin_cargar"])
    informe["veredicto"] = "POSTCHECK_OK" if ok else "POSTCHECK_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=str))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


# --------------------------------------------------------------------------- funcional (post)

FUNCIONES_SERVICE_ROLE = ("public.cf_resincronizar_albaran(text,bigint,jsonb,text,text)",
                          "public.cf_registrar_albaran_ausente(text,bigint,text,text)",
                          "public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)")


def funcional(salida: Path) -> int:
    def leer(lector: _Lector) -> dict:
        cur = lector._cur
        out = {}
        cur.execute("savepoint sr; set local role service_role")
        cur.execute(f"select current_user, count(*) from public.{CAMBIOS}")
        out["service_role_select_cambios"] = list(cur.fetchone())
        cur.execute("rollback to savepoint sr")
        for rol in ("anon", "authenticated"):
            cur.execute(f"savepoint {rol}; set local role {rol}")
            try:
                cur.execute(f"select count(*) from public.{CAMBIOS}")
                out[f"{rol}_select_cambios"] = "PERMITIDO"
            except Exception as exc:
                out[f"{rol}_select_cambios"] = f"DENEGADO: {str(exc).splitlines()[0]}"
            cur.execute(f"rollback to savepoint {rol}")
        out["privilegios_cambios"] = lector.json(
            "select jsonb_object_agg(r, jsonb_build_object("
            + ", ".join(f"'{p.lower()}', has_table_privilege(r, 'public.{CAMBIOS}', '{p}')"
                        for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"))
            + "))::text from unnest(array['service_role', 'anon', 'authenticated']) r")
        out["service_role_update_albaranes"] = lector.valor(
            "select has_table_privilege('service_role', 'public.albaranes', 'UPDATE')")
        firmas = ", ".join(f"'{f}'" for f in FUNCIONES_SERVICE_ROLE)
        out["privilegios_funciones"] = lector.json(
            "select jsonb_object_agg(f, jsonb_build_object('anon', has_function_privilege('anon', f, 'EXECUTE'), "
            "'authenticated', has_function_privilege('authenticated', f, 'EXECUTE'), "
            "'service_role', has_function_privilege('service_role', f, 'EXECUTE'), "
            "'public', exists(select 1 from pg_proc p cross join lateral aclexplode(p.proacl) a "
            "                 where p.oid = f::regprocedure and a.grantee = 0), "
            "'definer', (select prosecdef from pg_proc where oid = f::regprocedure), "
            "'owner', (select pg_get_userbyid(proowner) from pg_proc where oid = f::regprocedure)))::text "
            f"from unnest(array[{firmas}]) f")
        out["auxiliares_solo_propietario"] = lector.json(
            "select coalesce(jsonb_object_agg(p.oid::regprocedure::text, jsonb_build_object("
            "'service_role', has_function_privilege('service_role', p.oid, 'EXECUTE'), "
            "'anon', has_function_privilege('anon', p.oid, 'EXECUTE'), "
            "'owner', pg_get_userbyid(p.proowner))), '{}'::jsonb)::text from pg_proc p "
            "where p.pronamespace = 'public'::regnamespace "
            "and p.proname in ('cf_albaran_ausente_abierto', 'cf_id_proveedor_comparable')")
        out["tabla_cambios"] = lector.json(
            "select jsonb_build_object('owner', pg_get_userbyid(relowner), 'rls', relrowsecurity)::text "
            f"from pg_class where oid = 'public.{CAMBIOS}'::regclass")
        out["triggers_cambios"] = [r[0] for r in lector.filas(
            f"select tgname::text from pg_trigger where tgrelid = 'public.{CAMBIOS}'::regclass and not tgisinternal "
            "order by 1")]
        return out

    _, datos = _ejecutar_lectura(leer)
    esperado_fun = {"anon": False, "authenticated": False, "service_role": True, "public": False,
                    "definer": True, "owner": "postgres"}
    ok = (datos["service_role_select_cambios"][0] == "service_role"
          and all(datos[f"{r}_select_cambios"].startswith("DENEGADO: permission denied") for r in ("anon", "authenticated"))
          and datos["privilegios_cambios"]["service_role"] == {"select": True, "insert": False, "update": False,
                                                               "delete": False, "truncate": False}
          and all(not any(v.values()) for r, v in datos["privilegios_cambios"].items() if r != "service_role")
          and datos["service_role_update_albaranes"] is False
          and all(v == esperado_fun for v in datos["privilegios_funciones"].values())
          and len(datos["auxiliares_solo_propietario"]) == 2
          and all(v == {"service_role": False, "anon": False, "owner": "postgres"}
                  for v in datos["auxiliares_solo_propietario"].values())
          and datos["tabla_cambios"] == {"owner": "postgres", "rls": True}
          and datos["triggers_cambios"])
    datos["veredicto"] = "FUNCIONAL_OK" if ok else "FUNCIONAL_CON_DIFERENCIAS"
    print(json.dumps(datos, ensure_ascii=False, indent=1, default=str))
    print("sha256", _escribir(salida, datos))
    return 0 if ok else 3


if __name__ == "__main__":
    modo, args = sys.argv[1], sys.argv[2:]
    if modo == "precondiciones":
        sys.exit(precondiciones(_salida_fuera_del_repo(args[0])))
    elif modo == "local":
        azd.local(args[0], _salida_fuera_del_repo(args[1]))
    elif modo == "alcance":
        sys.exit(alcance(Path(args[0]), Path(args[1]), _salida_fuera_del_repo(args[2])))
    elif modo == "remoto":
        sys.exit(remoto(args[0], Path(args[1]), _salida_fuera_del_repo(args[2])))
    elif modo == "comparar_pre":
        sys.exit(comparar_pre(Path(args[0]), Path(args[1]), Path(args[2]), Path(args[3]), _salida_fuera_del_repo(args[4])))
    elif modo == "comparar":
        sys.exit(comparar(Path(args[0]), Path(args[1]), Path(args[2]), Path(args[3]), _salida_fuera_del_repo(args[4])))
    elif modo == "funcional":
        sys.exit(funcional(_salida_fuera_del_repo(args[0])))
    else:
        raise SystemExit("modo desconocido")
