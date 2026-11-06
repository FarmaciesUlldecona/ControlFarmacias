"""Hito 2BN-D: preflight, captura y postcheck ESTRICTAMENTE READ_ONLY de la migracion 29 (rol cf_lectura).

Uso (identidad Windows Usuari; conexion CONTROLFARMACIAS_SUPABASE_DB_URL; sin Farmatic):
  python -B pruebas/auditoria_2bn_d/preflight_readonly.py precondiciones <salida.json>
  python -B pruebas/auditoria_2bn_d/preflight_readonly.py local <28|29> <salida.json>
  python -B pruebas/auditoria_2bn_d/preflight_readonly.py alcance <local_28.json> <local_29.json> <salida.json>
  python -B pruebas/auditoria_2bn_d/preflight_readonly.py captura <pre|post> <salida.json>
  python -B pruebas/auditoria_2bn_d/preflight_readonly.py comparar_pre <pre.json> <local_28.json> <alcance.json> <salida.json>
  python -B pruebas/auditoria_2bn_d/preflight_readonly.py comparar_despliegue <pre.json> <post.json> <local_29.json> <alcance.json> <salida.json>

Patron de ``pruebas/auditoria_2bm_d/preflight_readonly.py`` (puerta del 2AT: project ref demostrado, sesion
READ_ONLY REPEATABLE READ, solo SELECT/WITH, rollback; salidas FUERA del repositorio; tareas solo con
``Get-ScheduledTaskInfo``). Cambia lo propio de la 29:
- precondiciones: la constante ``PRECONDICIONES`` de ``pruebas/auditoria_2bn/desplegar_29.py`` (mismo objeto);
- marcas 28 presentes y 29 ausentes (pre) o presentes (post);
- la huella de esquema del 2AZ recoge la ACL de las tablas y el texto de las politicas, pero no los roles de cada
  politica, la ACL de los esquemas ni el rol: ``extra`` los captura aparte (ademas de triggers y compresion de la
  2BM-D), tambien en las referencias locales, y entran en el alcance y en el postcheck;
- ``comparar_despliegue`` exige la huella por fila identica pre/post (criterio 2AX): la 29 no cambia filas.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import (  # noqa: E402
    _ejecutar_lectura, _escribir, _puertas_operacion, _salida_fuera_del_repo)


def _cargar(nombre: str, ruta: str):
    spec = importlib.util.spec_from_file_location(nombre, ROOT / ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


bmd = _cargar("preflight_2bmd", "pruebas/auditoria_2bm_d/preflight_readonly.py")
bid = bmd.bid
despliegue = _cargar("desplegar_29", "pruebas/auditoria_2bn/desplegar_29.py")
ROL = despliegue.ROL

TABLAS_HUELLA = bid.TABLAS_HUELLA
_md5, _clave, _leer_json = bid._md5, bid._clave, bid._leer_json

_POLITICA_NUEVA = despliegue.POLITICAS_NUEVAS[0]
MARCAS = (
    "select jsonb_build_object("
    "'28_materializar', to_regprocedure('public.cf_materializar_referencia()') is not null,"
    "'28_trigger', exists(select 1 from pg_trigger where tgrelid = 'public.facturas'::regclass "
    "  and tgname = 'facturas_materializar_referencia'),"
    f"'29_rol', exists(select 1 from pg_roles where rolname = '{ROL}'),"
    f"'29_lectura', case when exists(select 1 from pg_roles where rolname = '{ROL}') "
    f"  then has_table_privilege('{ROL}', 'public.facturas', 'SELECT') else false end,"
    f"'29_politicas_nuevas', exists(select 1 from pg_policy where polrelid = 'public.{_POLITICA_NUEVA[0]}'::regclass "
    f"  and polname = '{_POLITICA_NUEVA[1]}'))::text"
)
MARCAS_28 = ("28_materializar", "28_trigger")
# El rol es del cluster: su mera existencia no prueba la 29 en esta base (la marca 29_rol solo se informa).
MARCAS_29 = ("29_lectura", "29_politicas_nuevas")

ESQUEMAS = ("public",) + despliegue.ESQUEMAS_VEDADOS

# Lo que la huella de esquema del 2AZ no recoge y la 29 cambia (mas lo de la 2BM-D).
SQL_EXTRA = (
    "select jsonb_build_object("
    "'triggers', (select coalesce(jsonb_object_agg(c.relname || '.' || t.tgname, pg_get_triggerdef(t.oid)), "
    "  '{}'::jsonb) from pg_trigger t join pg_class c on c.oid = t.tgrelid "
    "  where c.relnamespace = 'public'::regnamespace and not t.tgisinternal),"
    "'compresion', (select jsonb_object_agg(attrelid::regclass::text || '.' || attname, attcompression::text) "
    f"  from pg_attribute where {bmd.despliegue.COMPRESION}),"
    "'politicas_roles', (select coalesce(jsonb_object_agg(c.relname || '.' || p.polname, "
    "  (select jsonb_agg(coalesce(r.rolname, 'public') order by coalesce(r.rolname, 'public')) "
    "   from unnest(p.polroles) o left join pg_roles r on r.oid = o)), '{}'::jsonb) "
    "  from pg_policy p join pg_class c on c.oid = p.polrelid where c.relnamespace = 'public'::regnamespace),"
    "'esquemas_acl', (select coalesce(jsonb_object_agg(n.nspname, (select coalesce(jsonb_agg(jsonb_build_array("
    "  coalesce(r.rolname, 'PUBLIC'), a.privilege_type) order by coalesce(r.rolname, 'PUBLIC'), a.privilege_type), "
    "  '[]'::jsonb) from aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a "
    "  left join pg_roles r on r.oid = a.grantee)), '{}'::jsonb) from pg_namespace n "
    f"  where n.nspname = any(array[{', '.join(repr(e) for e in ESQUEMAS)}])),"
    "'rol', (select to_jsonb(x) from (select rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, "
    "  rolcanlogin, rolreplication, rolbypassrls, rolconnlimit, rolvaliduntil, "
    "  (select array_agg(c order by c) from unnest(rolconfig) c) as rolconfig, "
    "  (select coalesce(array_agg(pg_get_userbyid(roleid) order by 1), '{}') from pg_auth_members "
    "   where member = r.oid) as miembro_de, "
    "  (select coalesce(array_agg(pg_get_userbyid(member) order by 1), '{}') from pg_auth_members "
    f"   where roleid = r.oid) as miembros from pg_roles r where rolname = '{ROL}') x))::text"
)

# bid._leer lee la global MARCAS de su modulo.
bid.MARCAS = MARCAS


def _leer(lector) -> dict:
    return {**bid._leer(lector), "extra": lector.json(SQL_EXTRA)}


def _objetos(captura: dict) -> dict:
    """Huella de esquema del 2AZ mas lo extra, en un mismo diccionario de objetos."""
    extra = captura["extra"]
    return {**captura["esquema"]["objetos"],
            **{f"trigger:{k}": v for k, v in extra["triggers"].items()},
            **{f"compresion:{k}": v for k, v in extra["compresion"].items()},
            **{f"politica_roles:{k}": v for k, v in extra["politicas_roles"].items()},
            **{f"esquema_acl:{k}": v for k, v in extra["esquemas_acl"].items()},
            **({f"rol:{ROL}": extra["rol"]} if extra["rol"] is not None else {})}


def precondiciones(salida: Path) -> int:
    sql = despliegue.PRECONDICIONES
    _, datos = _ejecutar_lectura(lambda lector: {"precondiciones": list(lector.fila(sql))})
    datos["sql"] = sql
    datos["veredicto"] = "PRECONDICIONES_OK" if all(datos["precondiciones"]) else "PRECONDICIONES_NO_CUMPLIDAS"
    print(json.dumps({k: datos[k] for k in ("project_ref", "capturado_utc", "transaction_read_only",
                                            "precondiciones", "veredicto")}, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if all(datos["precondiciones"]) else 3


def local(variante: str, salida: Path) -> None:
    """Referencia local (PG17 desechable): huella de esquema del 2AZ y lo extra."""
    sys.path.insert(0, str(ROOT / "tests/facturas/runtime_supabase"))
    import pg17_local as pgl

    nombre = "cf-pg17-ref2bnd-" + uuid.uuid4().hex[:8]
    pgl._docker("run", "-d", "--rm", "--name", nombre, "--label", "controlfarmacias.certificacion=pg17_local",
                "--network", "none", "--tmpfs", "/var/lib/postgresql/data",
                "-e", "POSTGRES_PASSWORD=local-only", pgl.IMAGEN)
    try:
        for _ in range(240):
            if pgl._docker("exec", nombre, "psql", "-U", "postgres", "-qAt", "-c", "select 1",
                           comprobar=False).returncode == 0:
                break
            time.sleep(0.5)
        time.sleep(2)
        pg = pgl._Pg(nombre, pgl.construir_plantilla(nombre, variante))
        datos = {"variante": variante, "esquema": json.loads(pg.sql(bid.SQL_ESQUEMA + ";")),
                 "extra": json.loads(pg.sql(SQL_EXTRA + ";"))}
        # 2BQ: la plantilla aplica la 29 con la imitacion del postgres de Supabase; su pertenencia ADMIN en el rol
        # nuevo es la que en produccion tiene postgres.
        if datos["extra"]["rol"]:
            datos["extra"]["rol"]["miembros"] = sorted(
                "postgres" if m == pgl.ROL_SUPABASE else m for m in datos["extra"]["rol"]["miembros"])
    finally:
        pgl.cerrar_sesiones(nombre)
        pgl._docker("rm", "-f", nombre, comprobar=False)
    print("sha256", _escribir(salida, datos))


def alcance(local28_ruta: Path, local29_ruta: Path, salida: Path) -> int:
    """Objetos cuya huella difiere entre las referencias locales 28 y 29 (no se escribe a mano)."""
    a, b = _objetos(_leer_json(local28_ruta)), _objetos(_leer_json(local29_ruta))
    claves = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    datos = {"alcance_29": claves, "nuevos": sorted(set(b) - set(a)), "eliminados": sorted(set(a) - set(b))}
    print(json.dumps(datos, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if claves and not datos["eliminados"] else 3


def captura(fase: str, salida: Path) -> int:
    if fase not in ("pre", "post"):
        raise SystemExit("fase debe ser pre o post")
    tareas = bid._tareas()
    ahora_tareas = _dt.datetime.now(_dt.timezone.utc)
    _, datos = _ejecutar_lectura(_leer)
    datos.update({"fase": fase, "tareas": tareas, "tareas_consultadas_utc": ahora_tareas.isoformat()})
    marcas = datos["marcas"]
    fallos = [f"MIGRACION_28_AUSENTE:{k}" for k in MARCAS_28 if not marcas[k]]
    if fase == "pre":
        fallos += [f"MIGRACION_29_YA_PRESENTE:{k}" for k in MARCAS_29 if marcas[k]]
        fallos += bid._puertas_tareas(tareas, ahora_tareas)
    else:
        fallos += [f"MIGRACION_29_AUSENTE:{k}" for k in MARCAS_29 if not marcas[k]]
    if datos["normalizando"]:
        fallos.append(f"DOCUMENTOS_EN_NORMALIZANDO:{len(datos['normalizando'])}")
    if sorted(_clave(r) for r in datos["reservas"]) != sorted(_clave(r) for r in datos["lineas_vigentes_con_albaran"]):
        fallos.append("RESERVAS_DISTINTAS_DE_VIGENTES_CON_ALBARAN")
    if datos["esquema"]["owner_distinto_de_postgres"]:
        fallos.append(f"OWNER_DISTINTO_DE_POSTGRES:{datos['esquema']['owner_distinto_de_postgres']}")
    fallos += _puertas_operacion(datos["operacion"])
    if datos["locks_factura"]:
        fallos.append(f"LOCKS_FACTURA:{datos['locks_factura']}")
    datos["fallos"] = fallos
    datos["veredicto"] = "CAPTURA_OK" if not fallos else "PARADO"
    sha = _escribir(salida, datos)
    resumen = {k: datos.get(k) for k in ("project_ref", "capturado_utc", "current_user", "fase", "marcas",
                                         "locks_factura", "normalizando", "fallos", "veredicto")}
    resumen.update({"flags": datos["operacion"]["flags"], "conteos": datos["operacion"]["conteos"],
                    "reservas": len(datos["reservas"]), "objetos_publicos": len(datos["esquema"]["objetos"]),
                    "triggers_publicos": len(datos["extra"]["triggers"]),
                    "politicas_publicas": len(datos["extra"]["politicas_roles"]),
                    "esquemas_acl": datos["extra"]["esquemas_acl"], "rol": datos["extra"]["rol"],
                    "filas_por_tabla": {t: len(v) for t, v in datos["huellas_por_fila"].items()},
                    "aprobaciones": len(datos["aprobaciones"]), "aplicadas": len(datos["aplicadas"]),
                    "tareas": tareas})
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


def comparar_pre(pre_ruta: Path, local28_ruta: Path, alcance_ruta: Path, salida: Path) -> int:
    """Produccion esta en el esquema 28 para todo el alcance de la 29 (incluidos roles de politicas y esquemas)."""
    pre = _leer_json(pre_ruta)
    ref = _objetos(_leer_json(local28_ruta))
    claves = _leer_json(alcance_ruta)["alcance_29"]
    b = _objetos(pre)
    informe = {"alcance_29_igual_a_local_28": {k: _md5(b.get(k)) == _md5(ref.get(k)) for k in claves},
               "captura_pre_ok": pre.get("veredicto") == "CAPTURA_OK"}
    ok = all(informe["alcance_29_igual_a_local_28"].values()) and informe["captura_pre_ok"]
    informe["veredicto"] = "ESQUEMA_28_CONFIRMADO" if ok else "ESQUEMA_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


# DECISION DE PIO (2BN-D, 2026-11-05): deuda de baseline conocida (2AS; excepcion del 2BC) en tres objetos del
# alcance. En las dos tablas, el campo con deriva queda identico pre/post y el resto igual a la referencia 29; en el
# esquema public solo se anade cf_lectura con USAGE y el resto de permisos queda identico.
EXCEPCION_TABLAS = {"tabla:albaranes": "indices", "tabla:documentos_facturas": "columnas"}
EXCEPCION_ESQUEMA = "esquema_acl:public"


def _igual_a_referencia(clave: str, pre: dict, post: dict, ref: dict) -> bool:
    if clave in EXCEPCION_TABLAS:
        deriva = EXCEPCION_TABLAS[clave]
        a, b, r = pre.get(clave), post.get(clave), ref.get(clave)
        if not (a and b and r) or set(b) != set(r) or _md5(a[deriva]) != _md5(b[deriva]):
            return False
        # Ademas de la ACL solo cambian las politicas, y solo por el alta de la politica nueva de la 29.
        nuevas = {p for t, p in despliegue.POLITICAS_NUEVAS if clave == f"tabla:{t}"}
        politicas_ok = set(b["politicas"]) - set(a["politicas"]) == nuevas and \
            all(_md5(a["politicas"][p]) == _md5(b["politicas"].get(p)) for p in a["politicas"])
        return politicas_ok and all(_md5(b[k]) == _md5(r[k]) for k in b if k != deriva) and \
            all(_md5(a[k]) == _md5(b[k]) for k in a if k not in (deriva, "acl", "politicas"))
    if clave == EXCEPCION_ESQUEMA:
        a, b = pre.get(clave) or [], post.get(clave) or []
        anadido = [ROL, "USAGE"]
        return anadido not in a and anadido in (ref.get(clave) or []) and \
            sorted(b) == sorted(a + [anadido]) and len(b) == len(a) + 1
    return _md5(post.get(clave)) == _md5(ref.get(clave))


def comparar_despliegue(pre_ruta: Path, post_ruta: Path, local29_ruta: Path, alcance_ruta: Path,
                        salida: Path) -> int:
    """Criterio de postcheck de REGLAS_CRITICAS (2AX) mas datos intactos, con la excepcion de Pio."""
    pre, post = _leer_json(pre_ruta), _leer_json(post_ruta)
    ref = _objetos(_leer_json(local29_ruta))
    claves = _leer_json(alcance_ruta)["alcance_29"]
    a, b = _objetos(pre), _objetos(post)
    cambiados = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    informe = {
        "c1_solo_cambia_el_alcance": set(cambiados) <= set(claves), "objetos_cambiados": cambiados,
        "c2_alcance_igual_a_local_29": {k: _igual_a_referencia(k, a, b, ref) for k in claves},
        "excepcion_pio": sorted(EXCEPCION_TABLAS) + [EXCEPCION_ESQUEMA],
        "excepcion_campos_cambiados": {k: sorted(c for c in a.get(k, {}) if _md5(a[k][c]) != _md5(b.get(k, {}).get(c)))
                                       for k in EXCEPCION_TABLAS},
        "c3_fuera_de_alcance_identicos": all(_md5(a.get(k)) == _md5(b.get(k)) for k in set(a) | set(b)
                                             if k not in claves),
        "default_acl_identico": pre["esquema"]["default_acl"] == post["esquema"]["default_acl"],
        "cf_configuracion_identica": pre["cf_configuracion_completa"] == post["cf_configuracion_completa"],
        "huellas_identicas": {t: pre["huellas_por_fila"][t] == post["huellas_por_fila"][t] for t in TABLAS_HUELLA},
        "operacion_identica": pre["operacion"] == post["operacion"] and pre["locks_factura"] == post["locks_factura"],
        "reservas_pre_igual_post": pre["reservas"] == post["reservas"],
        "normalizando_identico": pre["normalizando"] == post["normalizando"],
        "aprobaciones_identicas": pre["aprobaciones"] == post["aprobaciones"] and pre["aplicadas"] == post["aplicadas"],
        "captura_post_ok": post.get("veredicto") == "CAPTURA_OK",
    }
    for t in TABLAS_HUELLA:
        if not informe["huellas_identicas"][t]:
            informe.setdefault("diferencias_huella", {})[t] = bid._diferencias_huella(
                pre["huellas_por_fila"][t], post["huellas_por_fila"][t])
    ok = all(v if isinstance(v, bool) else all(v.values()) for k, v in informe.items()
             if k not in ("objetos_cambiados", "diferencias_huella", "excepcion_pio", "excepcion_campos_cambiados"))
    informe["veredicto"] = "POSTCHECK_OK" if ok else "POSTCHECK_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=str))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


if __name__ == "__main__":
    modo, args = sys.argv[1], sys.argv[2:]
    if modo == "precondiciones":
        sys.exit(precondiciones(_salida_fuera_del_repo(args[0])))
    elif modo == "local":
        local(args[0], _salida_fuera_del_repo(args[1]))
    elif modo == "alcance":
        sys.exit(alcance(Path(args[0]), Path(args[1]), _salida_fuera_del_repo(args[2])))
    elif modo == "captura":
        sys.exit(captura(args[0], _salida_fuera_del_repo(args[1])))
    elif modo == "comparar_pre":
        sys.exit(comparar_pre(Path(args[0]), Path(args[1]), Path(args[2]), _salida_fuera_del_repo(args[3])))
    elif modo == "comparar_despliegue":
        sys.exit(comparar_despliegue(Path(args[0]), Path(args[1]), Path(args[2]), Path(args[3]),
                                     _salida_fuera_del_repo(args[4])))
    else:
        raise SystemExit("modo desconocido")
