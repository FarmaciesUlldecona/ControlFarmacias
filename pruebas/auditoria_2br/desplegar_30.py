"""Hito 2BR: despliega EXCLUSIVAMENTE la migracion 30 (detalle por linea en la conciliacion), una vez, en una
transaccion.

NO se ejecuta en el hito 2BR (solo se ensaya en local con el rol que imita al postgres de Supabase). Requiere
confirmacion expresa de Pio en chat. No invoca RPC funcionales. Normaliza el SQL a LF y exige que coincida byte a
byte con la version del commit indicado (git show <commit>:...). Revalida precondiciones dentro de la misma
transaccion. Error -> rollback y parada; nunca reintenta. Patron de pruebas/auditoria_2bn/desplegar_29.py.

Postcondiciones: facturas, conciliaciones, reservas y el resto de cada detalle identicos (el resultado de la factura
no cambia); cada detalle con los valores por linea de ``cf_detalles_por_linea``; los valores previos guardados tal
cual; privilegios de las dos funciones y de la tabla de valores previos; objetos nuevos del rol que despliega
(``postgres`` en Supabase).

Uso: python pruebas/auditoria_2br/desplegar_30.py <commit> <sha256_lf_esperado> <salida.json>
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
RUTA = "sql/migrations/30_cf_detalle_por_linea.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
PERSISTIR = "public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)"
POR_LINEA = "public.cf_detalles_por_linea(uuid,jsonb)"
PREVIO = "public.conciliacion_detalles_previo_30"
ROLES_SIN_ACCESO = ("anon", "authenticated", "cf_lectura")
COLUMNAS_LINEA = ("importe_documental", "importe_farmatic", "diferencia", "estado")

PRECONDICIONES = (
    # 29 aplicada (rol de lectura y su politica sobre albaranes).
    "select exists (select 1 from pg_roles where rolname = 'cf_lectura') and exists (select 1 from pg_policy "
    "  where polrelid = 'public.albaranes'::regclass and polname = 'albaranes_lectura_select'),"
    # 30 no aplicada.
    f"to_regprocedure('{POR_LINEA}') is null and to_regclass('{PREVIO}') is null,"
    # Estado de partida que se rellena: importes por linea vacios (hallazgo de la web).
    "(select count(*) = 0 from public.conciliacion_detalles where importe_documental is not null "
    "  or importe_farmatic is not null or diferencia is not null),"
    # 19: privilegios minimos.
    "not has_table_privilege('anon', 'public.facturas', 'SELECT') "
    "  and not has_table_privilege('authenticated', 'public.albaranes', 'UPDATE'),"
    "(select normalizacion_automatica=false and conciliacion_automatica=false and luna_habilitada=false "
    "  and farmacias_habilitadas=array['PIO']::text[] from public.cf_configuracion where id),"
    "(select count(*)=0 from public.facturas where conciliacion_bloqueado_por is not null "
    "  or conciliacion_bloqueado_hasta>now()),"
    "(select count(*)=0 from public.documentos_facturas where bloqueado_por is not null "
    "  or bloqueado_hasta>now() or estado_lectura='NORMALIZANDO'),"
    # Reservas coherentes con las conciliaciones vigentes (R15).
    "(select count(*) from public.conciliacion_albaranes_reservados) = "
    "  (select count(*) from public.conciliacion_detalles d join public.conciliaciones c "
    "   on c.id=d.conciliacion_id where c.es_actual and d.albaran_id_contador is not null),"
    # 2AX: ningun objeto de public con propietario distinto de postgres.
    "(select count(*)=0 from pg_class c where c.relnamespace='public'::regnamespace "
    "  and c.relkind in ('r','p','v','m','S','f') and pg_get_userbyid(c.relowner)<>'postgres') and "
    "(select count(*)=0 from pg_proc p where p.pronamespace='public'::regnamespace "
    "  and pg_get_userbyid(p.proowner)<>'postgres' "
    "  and not exists(select 1 from pg_depend d where d.objid=p.oid and d.deptype='e'))")


def _md5(consulta: str) -> str:
    return f"(select md5(coalesce(string_agg(md5(t.v::text), '' order by t.k), '')) from ({consulta}) t)"


# Lo que la 30 no puede cambiar: conteos, facturas, conciliaciones, reservas e historial; de cada detalle, todo menos
# los cuatro valores por linea.
DATOS = (
    "select array[(select count(*) from public.documentos_facturas), "
    "(select count(*) from public.facturas), "
    "(select count(*) from public.normalizacion_ejecuciones), "
    "(select count(*) from public.historial_facturas), "
    "(select count(*) from public.conciliaciones), "
    "(select count(*) from public.conciliacion_detalles), "
    "(select count(*) from public.conciliacion_albaranes_reservados)], array["
    + _md5("select f.id::text as k, to_jsonb(f) as v from public.facturas f") + ", "
    + _md5("select c.id::text as k, to_jsonb(c) as v from public.conciliaciones c") + ", "
    + _md5("select r.albaran_farmacia || ':' || r.albaran_id_contador as k, to_jsonb(r) as v "
           "from public.conciliacion_albaranes_reservados r") + ", "
    + _md5("select d.id::text as k, to_jsonb(d) - " + " - ".join(f"'{c}'" for c in COLUMNAS_LINEA)
           + " as v from public.conciliacion_detalles d") + "]")

# Valores por linea antes del relleno (y, despues, los guardados en la tabla de valores previos).
LINEA_ANTES = _md5("select d.id::text as k, jsonb_build_array(" + ", ".join(f"d.{c}" for c in COLUMNAS_LINEA)
                   + ") as v from public.conciliacion_detalles d")
LINEA_PREVIA = _md5("select p.detalle_id::text as k, jsonb_build_array(" + ", ".join(f"p.{c}" for c in COLUMNAS_LINEA)
                    + f") as v from {PREVIO} p")

DETALLES_DE = ("(select coalesce(jsonb_agg(jsonb_build_object('orden', x.orden, 'tipo_relacion', x.tipo_relacion, "
               "'factura_albaran_extraido_id', x.factura_albaran_extraido_id, 'importe_aplicado', x.importe_aplicado)), "
               "'[]'::jsonb) from public.conciliacion_detalles x where x.conciliacion_id = c.id)")

POSTCONDICIONES = (
    f"{DATOS},"
    # Relleno: cada detalle con los valores de cf_detalles_por_linea; los previos guardados uno por detalle.
    "not exists (select 1 from public.conciliaciones c "
    f"  cross join lateral public.cf_detalles_por_linea(c.factura_id, {DETALLES_DE}) l "
    "  join public.conciliacion_detalles d on d.conciliacion_id = c.id and d.orden = l.orden "
    "  where (d.importe_documental, d.importe_farmatic, d.diferencia, d.estado) is distinct from "
    "        (l.importe_documental, l.importe_farmatic, l.diferencia, l.estado)) "
    f"  and (select count(*) from {PREVIO}) = (select count(*) from public.conciliacion_detalles),"
    f"{LINEA_PREVIA},"
    # Privilegios: la RPC solo para service_role; la auxiliar y la tabla de valores previos, solo el propietario.
    f"(select prosecdef from pg_proc where oid = '{PERSISTIR}'::regprocedure) "
    f"  and has_function_privilege('service_role', '{PERSISTIR}', 'EXECUTE')"
    + "".join(f" and not has_function_privilege('{r}', '{PERSISTIR}', 'EXECUTE')" for r in ROLES_SIN_ACCESO)
    + "".join(f" and not has_function_privilege('{r}', '{POR_LINEA}', 'EXECUTE')"
              for r in ("service_role",) + ROLES_SIN_ACCESO)
    + "".join(f" and not has_table_privilege('{r}', '{PREVIO}', 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,"
              f"TRIGGER')" for r in ("service_role",) + ROLES_SIN_ACCESO)
    + f" and (select relrowsecurity from pg_class where oid = '{PREVIO}'::regclass),"
    # Objetos nuevos del rol que despliega (postgres en Supabase); la RPC sigue siendo de postgres.
    f"(select pg_get_userbyid(proowner) = current_user from pg_proc where oid = '{POR_LINEA}'::regprocedure) "
    f"  and (select pg_get_userbyid(relowner) = current_user from pg_class where oid = '{PREVIO}'::regclass) "
    f"  and (select pg_get_userbyid(proowner) = 'postgres' from pg_proc where oid = '{PERSISTIR}'::regprocedure)")

RESUMEN = ("select coalesce(json_agg(t order by t.tipo_relacion, t.estado), '[]'::json)::text from ("
           "select tipo_relacion, estado, count(*) as detalles from public.conciliacion_detalles "
           "group by 1, 2) t")


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_30_NO_COINCIDE_CON_COMMIT")
    return local


def cuerpo_transaccional(sql: str) -> str:
    """Quita el begin/commit exterior: la transaccion la gestiona el script."""
    lineas = sql.split("\n")
    inicio = lineas.index("begin;")
    fin = len(lineas) - 1 - lineas[::-1].index("commit;")
    assert all(l.startswith("--") or not l.strip() for l in lineas[:inicio])
    assert all(not l.strip() for l in lineas[fin + 1:])
    return "\n".join(lineas[inicio + 1:fin])


def main(commit: str, esperado: str, salida: Path) -> None:
    sql = sql_lf(commit)
    sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    if sha != esperado:
        raise SystemExit(f"SHA256_MIGRACION_30_INESPERADO:{sha}")
    cuerpo = cuerpo_transaccional(sql)

    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    from dotenv import dotenv_values
    import psycopg2

    dsn = os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"]
    app = urlparse(dotenv_values(ROOT / ".env").get("SUPABASE_URL", ""))
    db = urlparse(dsn)
    ref = (app.hostname or "").split(".")[0]
    assert ref == PROJECT_REF and (
        db.hostname == f"db.{ref}.supabase.co"
        or ((db.hostname or "").endswith(".pooler.supabase.com")
            and unquote(db.username or "").endswith("." + ref))
    ), "DESTINO_PRODUCTIVO_NO_DEMOSTRADO"

    registro = {"project_ref": ref, "migracion": RUTA, "commit": commit, "sha256_lf": sha,
                "inicio_utc": datetime.now(timezone.utc).isoformat()}
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2br_deploy_30")
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("set local lock_timeout='5s'; set local statement_timeout='120s'")
            cur.execute(PRECONDICIONES)
            pre = cur.fetchone()
            registro["precondiciones"] = list(pre)
            if not all(pre):
                raise RuntimeError(f"PRECONDICIONES_NO_CUMPLIDAS:{list(pre)}")
            cur.execute(DATOS)
            datos_antes = [list(v) for v in cur.fetchone()]
            cur.execute(f"select {LINEA_ANTES}")
            linea_antes = cur.fetchone()[0]
            cur.execute(cuerpo)
            cur.execute(POSTCONDICIONES)
            conteos, huellas, relleno, linea_previa, privilegios, propietarios = cur.fetchone()
            registro["postcondiciones"] = {"datos_sin_cambios": [list(conteos), list(huellas)] == datos_antes,
                                           "relleno": relleno, "valores_previos": linea_previa == linea_antes,
                                           "privilegios": privilegios, "propietarios": propietarios}
            cur.execute(RESUMEN)
            registro["resumen_detalles"] = json.loads(cur.fetchone()[0])
            if set(registro["postcondiciones"].values()) != {True}:
                raise RuntimeError(f"POSTCONDICIONES_NO_CUMPLIDAS:{registro['postcondiciones']}")
        conn.commit()
        registro["resultado"] = "APLICADA"
    except Exception as exc:
        conn.rollback()
        registro["resultado"] = "REVERTIDA"
        registro["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        conn.close()
        registro["fin_utc"] = datetime.now(timezone.utc).isoformat()
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: registro.get(k) for k in ("resultado", "sha256_lf", "precondiciones", "postcondiciones")},
                     ensure_ascii=False))
    if registro["resultado"] != "APLICADA":
        raise SystemExit(registro.get("error"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
