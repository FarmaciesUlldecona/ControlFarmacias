"""Hito 2BA-D: preflight, backup, postcheck y prueba funcional ESTRICTAMENTE READ_ONLY de la migracion 21.

Uso:
  python -B pruebas/auditoria_2ba_d/preflight_readonly.py remoto <pre|post> <columnas_declaradas.json> <salida.json>
  python -B pruebas/auditoria_2ba_d/preflight_readonly.py local <variante 20|21> <salida.json>
  python -B pruebas/auditoria_2ba_d/preflight_readonly.py funcional <salida.json>
  python -B pruebas/auditoria_2ba_d/preflight_readonly.py comparar_pre <pre.json> <local_20.json> <postcheck_2azd.json> <salida.json>
  python -B pruebas/auditoria_2ba_d/preflight_readonly.py comparar <pre.json> <post.json> <local_21.json> <salida.json>

Patron del 2AZ-D (``pruebas/auditoria_2az_d/preflight_readonly.py``, del que reutiliza la huella de
esquema, las columnas y la referencia local) con la puerta certificada del 2AT: project ref
demostrado, sesion READ_ONLY REPEATABLE READ, solo SELECT/WITH, rollback. Salidas FUERA del
repositorio. Sin DML, sin RPC de escritura, sin Farmatic.

``remoto`` vuelca marcas 20/21, huella de esquema de ``public``, privilegios por defecto,
cf_configuracion completa, operacion, tareas, lineas vigentes con albaran (y duplicados: la
carga inicial de la 21 abortaria), reservas (si la tabla existe), elegibilidad de todas las
facturas (informativa: R16 la cambia) y huellas por fila de 9 tablas sobre columnas declaradas.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import (  # noqa: E402
    _Lector, _ejecutar_lectura, _escribir, _operacion, _puertas_operacion, _puertas_tareas, _salida_fuera_del_repo,
    _tareas)

_spec = importlib.util.spec_from_file_location("preflight_2azd", ROOT / "pruebas/auditoria_2az_d/preflight_readonly.py")
azd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(azd)

TABLAS_HUELLA = azd.TABLAS_HUELLA
SQL_ESQUEMA = azd.SQL_ESQUEMA
_md5 = azd._md5
RESERVAS = "conciliacion_albaranes_reservados"
ALCANCE = ("funcion:cf_persistir_conciliacion(uuid,text,text,text,jsonb)",
           "funcion:cf_evaluar_elegibilidad_conciliacion(uuid)",
           f"tabla:{RESERVAS}")

MARCAS = (
    "select jsonb_build_object("
    "'18_nucleo', to_regprocedure('public.cf_reclamar_factura_conciliacion_nucleo(text,integer,text)') is not null,"
    "'19_anon_sin_select_facturas', not has_table_privilege('anon','public.facturas','SELECT'),"
    "'19_service_role_sin_update_facturas', not has_table_privilege('service_role','public.facturas','UPDATE'),"
    "'20_columna_tope', exists(select 1 from information_schema.columns where table_schema='public' "
    "  and table_name='cf_configuracion' and column_name='conciliacion_tolerancia_tope'),"
    "'20_rpc_enriquecer', to_regprocedure('public.cf_enriquecer_factura(uuid,text,text,jsonb)') is not null,"
    f"'21_tabla_reservas', to_regclass('public.{RESERVAS}') is not null)::text"
)

SQL_VIGENTES = (
    "select coalesce(jsonb_agg(jsonb_build_object('albaran_farmacia', d.albaran_farmacia, "
    "'albaran_id_contador', d.albaran_id_contador, 'factura_id', c.factura_id::text, "
    "'conciliacion_id', c.id::text, 'orden', d.orden, 'numero_factura', f.numero_factura) "
    "order by d.albaran_farmacia, d.albaran_id_contador, c.id, d.orden), '[]'::jsonb)::text "
    "from public.conciliaciones c join public.conciliacion_detalles d on d.conciliacion_id = c.id "
    "join public.facturas f on f.id = c.factura_id "
    "where c.es_actual and d.albaran_id_contador is not null")

SQL_ELEGIBILIDAD = (
    "select coalesce(jsonb_object_agg(f.numero_factura || ':' || f.id::text, e.estado || ':' || e.razon), "
    "'{}'::jsonb)::text from public.facturas f "
    "cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e")


def _clave(r: dict) -> list:
    return [r["albaran_farmacia"], r["albaran_id_contador"], r["factura_id"], r["conciliacion_id"], r["orden"]]


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
        vigentes = lector.json(SQL_VIGENTES)
        out["lineas_vigentes_con_albaran"] = vigentes
        cuenta: dict = {}
        for r in vigentes:
            cuenta.setdefault(f"{r['albaran_farmacia']}:{r['albaran_id_contador']}", []).append(r)
        out["albaranes_duplicados_en_vigentes"] = {k: v for k, v in cuenta.items() if len(v) > 1}
        if out["marcas"]["21_tabla_reservas"]:
            out["reservas"] = lector.json(
                "select coalesce(jsonb_agg(jsonb_build_object('albaran_farmacia', r.albaran_farmacia, "
                "'albaran_id_contador', r.albaran_id_contador, 'factura_id', r.factura_id::text, "
                "'conciliacion_id', r.conciliacion_id::text, 'orden', r.orden) "
                "order by r.albaran_farmacia, r.albaran_id_contador), '[]'::jsonb)::text "
                f"from public.{RESERVAS} r")
        else:
            out["reservas"] = None
        out["elegibilidad"] = lector.json(SQL_ELEGIBILIDAD)
        reales = azd._columnas(lector)
        out["columnas_huella"] = {t: {"declaradas_ausentes": sorted(set(declaradas[t]) - set(reales[t])),
                                      "reales_no_declaradas": sorted(set(reales[t]) - set(declaradas[t]))}
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
    fallos = [f"MARCA_FALSA:{k}" for k, v in datos["marcas"].items() if k != "21_tabla_reservas" and v is not True]
    if fase == "pre":
        if datos["marcas"]["21_tabla_reservas"]:
            fallos.append("MIGRACION_21_YA_PRESENTE")
        if datos["albaranes_duplicados_en_vigentes"]:
            fallos.append(f"ALBARANES_DUPLICADOS_EN_VIGENTES:{sorted(datos['albaranes_duplicados_en_vigentes'])}")
        fallos += _puertas_tareas(tareas, ahora_tareas)
    elif not datos["marcas"]["21_tabla_reservas"]:
        fallos.append("MIGRACION_21_AUSENTE")
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
    resumen = {k: datos[k] for k in ("project_ref", "capturado_utc", "current_user", "marcas", "flags",
                                     "tolerancia_conciliacion", "locks_documentos", "locks_factura",
                                     "claims_conciliacion", "normalizando", "workers",
                                     "facturas_por_estado_conciliacion_cf", "conteos_extra",
                                     "albaranes_duplicados_en_vigentes", "tareas", "fallos", "veredicto")}
    resumen["lineas_vigentes_con_albaran"] = len(datos["lineas_vigentes_con_albaran"])
    resumen["reservas"] = None if datos["reservas"] is None else len(datos["reservas"])
    resumen["owner_distinto_de_postgres"] = datos["esquema"]["owner_distinto_de_postgres"]
    resumen["objetos_publicos"] = len(datos["esquema"]["objetos"])
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


# --------------------------------------------------------------------------- funcional (post)

def funcional(salida: Path) -> int:
    def leer(lector: _Lector) -> dict:
        cur = lector._cur
        out = {}
        cur.execute("savepoint sr; set local role service_role")
        cur.execute(f"select current_user, count(*) from public.{RESERVAS}")
        out["service_role_select_reservas"] = list(cur.fetchone())
        cur.execute("select count(*) from public.facturas f "
                    "cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e")
        out["service_role_ejecuta_elegibilidad_sobre_facturas"] = cur.fetchone()[0]
        cur.execute("rollback to savepoint sr")
        for rol in ("anon", "authenticated"):
            cur.execute(f"savepoint {rol}; set local role {rol}")
            try:
                cur.execute(f"select count(*) from public.{RESERVAS}")
                out[f"{rol}_select_reservas"] = "PERMITIDO"
            except Exception as exc:
                out[f"{rol}_select_reservas"] = f"DENEGADO: {str(exc).splitlines()[0]}"
            cur.execute(f"rollback to savepoint {rol}")
            cur.execute(f"savepoint {rol}e; set local role {rol}")
            try:
                cur.execute("select public.cf_evaluar_elegibilidad_conciliacion(gen_random_uuid())")
                out[f"{rol}_execute_elegibilidad"] = "PERMITIDO"
            except Exception as exc:
                out[f"{rol}_execute_elegibilidad"] = f"DENEGADO: {str(exc).splitlines()[0]}"
            cur.execute(f"rollback to savepoint {rol}e")
        out["privilegios_reservas"] = lector.json(
            "select jsonb_object_agg(r, jsonb_build_object("
            f"'select', has_table_privilege(r, 'public.{RESERVAS}', 'SELECT'), "
            f"'insert', has_table_privilege(r, 'public.{RESERVAS}', 'INSERT'), "
            f"'update', has_table_privilege(r, 'public.{RESERVAS}', 'UPDATE'), "
            f"'delete', has_table_privilege(r, 'public.{RESERVAS}', 'DELETE'), "
            f"'truncate', has_table_privilege(r, 'public.{RESERVAS}', 'TRUNCATE')))::text "
            "from unnest(array['service_role', 'anon', 'authenticated']) r")
        out["privilegios_funciones"] = lector.json(
            "select jsonb_object_agg(f, jsonb_build_object('anon', has_function_privilege('anon', f, 'EXECUTE'), "
            "'authenticated', has_function_privilege('authenticated', f, 'EXECUTE'), "
            "'service_role', has_function_privilege('service_role', f, 'EXECUTE'), "
            "'public', exists(select 1 from pg_proc p cross join lateral aclexplode(p.proacl) a "
            "                 where p.oid = f::regprocedure and a.grantee = 0), "
            "'definer', (select prosecdef from pg_proc where oid = f::regprocedure), "
            "'owner', (select pg_get_userbyid(proowner) from pg_proc where oid = f::regprocedure)))::text "
            "from unnest(array['public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)', "
            "'public.cf_evaluar_elegibilidad_conciliacion(uuid)']) f")
        out["tabla_reservas"] = lector.json(
            "select jsonb_build_object('owner', pg_get_userbyid(relowner), 'rls', relrowsecurity)::text "
            f"from pg_class where oid = 'public.{RESERVAS}'::regclass")
        return out

    _, datos = _ejecutar_lectura(leer)
    esperado_fun = {"anon": False, "authenticated": False, "service_role": True, "public": False,
                    "definer": True, "owner": "postgres"}
    ok = (datos["service_role_select_reservas"][0] == "service_role"
          and all(datos[f"{r}_select_reservas"].startswith("DENEGADO: permission denied") for r in ("anon", "authenticated"))
          and all(datos[f"{r}_execute_elegibilidad"].startswith("DENEGADO: permission denied")
                  for r in ("anon", "authenticated"))
          and datos["privilegios_reservas"]["service_role"] == {"select": True, "insert": False, "update": False,
                                                                "delete": False, "truncate": False}
          and all(not any(v.values()) for r, v in datos["privilegios_reservas"].items() if r != "service_role")
          and all(v == esperado_fun for v in datos["privilegios_funciones"].values())
          and datos["tabla_reservas"] == {"owner": "postgres", "rls": True})
    datos["veredicto"] = "FUNCIONAL_OK" if ok else "FUNCIONAL_CON_DIFERENCIAS"
    print(json.dumps(datos, ensure_ascii=False, indent=1, default=str))
    print("sha256", _escribir(salida, datos))
    return 0 if ok else 3


# --------------------------------------------------------------------------- comparaciones (sin conexion)

def comparar_pre(pre_ruta: Path, local20_ruta: Path, postcheck_2azd_ruta: Path, salida: Path) -> int:
    """El esquema productivo es el 20: alcance igual a la referencia local 20 y todo el esquema igual
    que tras el postcheck del 2AZ-D (fuera de lo que haya cambiado desde entonces, que se lista)."""
    pre = json.loads(pre_ruta.read_text(encoding="utf-8"))
    ref = json.loads(local20_ruta.read_text(encoding="utf-8"))["esquema"]
    azd_post = json.loads(postcheck_2azd_ruta.read_text(encoding="utf-8"))["esquema"]
    a, b = azd_post["objetos"], pre["esquema"]["objetos"]
    informe = {
        "alcance_igual_a_local_20": {k: _md5(b.get(k)) == _md5(ref["objetos"].get(k)) for k in ALCANCE},
        "objetos_distintos_desde_postcheck_2azd": sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k))),
        "default_acl_igual_que_2azd": azd_post["default_acl"] == pre["esquema"]["default_acl"],
    }
    ok = (all(informe["alcance_igual_a_local_20"].values()) and not informe["objetos_distintos_desde_postcheck_2azd"]
          and informe["default_acl_igual_que_2azd"])
    informe["veredicto"] = "ESQUEMA_20_CONFIRMADO" if ok else "ESQUEMA_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


def comparar(pre_ruta: Path, post_ruta: Path, local21_ruta: Path, salida: Path) -> int:
    pre, post = (json.loads(p.read_text(encoding="utf-8")) for p in (pre_ruta, post_ruta))
    ref = json.loads(local21_ruta.read_text(encoding="utf-8"))["esquema"]
    a, b = pre["esquema"]["objetos"], post["esquema"]["objetos"]
    cambiados = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    vigentes = sorted(_clave(r) for r in post["lineas_vigentes_con_albaran"])
    reservas = sorted(_clave(r) for r in (post["reservas"] or []))
    informe = {
        "c1_solo_cambia_el_alcance": set(cambiados) <= set(ALCANCE), "objetos_cambiados": cambiados,
        "c2_alcance_igual_a_local_21": {k: _md5(b.get(k)) == _md5(ref["objetos"].get(k)) for k in ALCANCE},
        "c3_fuera_de_alcance_identicos": all(_md5(a.get(k)) == _md5(b.get(k)) for k in set(a) | set(b) if k not in ALCANCE),
        "default_acl_identico": pre["esquema"]["default_acl"] == post["esquema"]["default_acl"],
        "cf_configuracion_identica": pre["cf_configuracion_completa"] == post["cf_configuracion_completa"],
        "huellas_identicas": {t: pre["huellas_por_fila"][t] == post["huellas_por_fila"][t] for t in TABLAS_HUELLA},
        "operacion_como_antes": {k: pre[k] == post[k] for k in ("flags", "locks_documentos", "claims_conciliacion",
                                                                 "normalizando", "workers", "locks_factura")},
        "vigentes_pre_igual_post": sorted(_clave(r) for r in pre["lineas_vigentes_con_albaran"]) == vigentes,
        "reservas_igual_a_vigentes_con_albaran": reservas == vigentes,
        "reservas": len(reservas), "lineas_vigentes_con_albaran": len(vigentes),
        # Informativo: R16 cambia la elegibilidad (no es condicion de parada).
        "elegibilidad_cambiada_r16": {k: [pre["elegibilidad"].get(k), v] for k, v in post["elegibilidad"].items()
                                      if pre["elegibilidad"].get(k) != v},
    }
    for t in TABLAS_HUELLA:
        if not informe["huellas_identicas"][t]:
            x, y = pre["huellas_por_fila"][t], post["huellas_por_fila"][t]
            informe.setdefault("diferencias_huella", {})[t] = {
                "nuevas": sorted(set(y) - set(x))[:50], "borradas": sorted(set(x) - set(y))[:50],
                "cambiadas": sorted(k for k in set(x) & set(y) if x[k] != y[k])[:50]}
    ok = (informe["c1_solo_cambia_el_alcance"] and all(informe["c2_alcance_igual_a_local_21"].values())
          and informe["c3_fuera_de_alcance_identicos"] and informe["default_acl_identico"]
          and informe["cf_configuracion_identica"] and all(informe["huellas_identicas"].values())
          and all(informe["operacion_como_antes"].values()) and informe["vigentes_pre_igual_post"]
          and informe["reservas_igual_a_vigentes_con_albaran"])
    informe["veredicto"] = "POSTCHECK_OK" if ok else "POSTCHECK_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=str))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


def precondiciones(salida: Path) -> int:
    """Norma 2AX: la consulta de precondiciones de ``desplegar_21.py`` (texto exacto, extraido por ast)
    se ejecuta antes en produccion en una transaccion READ_ONLY."""
    import ast
    script = ROOT / "pruebas/auditoria_2ba/desplegar_21.py"
    arbol = ast.parse(script.read_text(encoding="utf-8"))
    [consulta] = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"
                  and n.args and "has_table_privilege" in ast.unparse(n.args[0])]
    _spec21 = importlib.util.spec_from_file_location("desplegar_21_pre", script)
    modulo = importlib.util.module_from_spec(_spec21)
    _spec21.loader.exec_module(modulo)
    sql = eval(compile(ast.Expression(consulta.args[0]), str(script), "eval"), vars(modulo))

    _, datos = _ejecutar_lectura(lambda lector: {"precondiciones": list(lector.fila(sql))})
    datos["sql"] = sql
    datos["veredicto"] = "PRECONDICIONES_OK" if all(datos["precondiciones"]) else "PRECONDICIONES_NO_CUMPLIDAS"
    print(json.dumps({k: datos[k] for k in ("project_ref", "capturado_utc", "transaction_read_only",
                                            "precondiciones", "veredicto")}, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if all(datos["precondiciones"]) else 3


if __name__ == "__main__":
    modo = sys.argv[1]
    if modo == "precondiciones":
        sys.exit(precondiciones(_salida_fuera_del_repo(sys.argv[2])))
    elif modo == "remoto":
        sys.exit(remoto(sys.argv[2], Path(sys.argv[3]), _salida_fuera_del_repo(sys.argv[4])))
    elif modo == "local":
        azd.local(sys.argv[2], _salida_fuera_del_repo(sys.argv[3]))
    elif modo == "funcional":
        sys.exit(funcional(_salida_fuera_del_repo(sys.argv[2])))
    elif modo == "comparar_pre":
        sys.exit(comparar_pre(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]),
                              _salida_fuera_del_repo(sys.argv[5])))
    elif modo == "comparar":
        sys.exit(comparar(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), _salida_fuera_del_repo(sys.argv[5])))
    else:
        raise SystemExit("modo desconocido")
