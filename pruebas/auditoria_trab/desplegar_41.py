"""Hito TA4-2: despliega EXCLUSIVAMENTE la migracion 41 (guardias por asignar en PIO y RITA y estado PLANIFICADO o
CONFIRMADO en guardias_semana y guardias_festivo), una vez, en una transaccion.

NO se ejecuta en el hito TA4-2 (solo se ensaya en local, con el rol que imita al postgres de Supabase). Requiere
confirmacion expresa de Pio en chat (hito 41-D) y los flags apagados por Pio durante la ventana. No invoca RPC.
Normaliza el SQL a LF y exige que coincida byte a byte con la version del commit indicado (git show <commit>:...), y la
entrada de linea de ordenes exige ademas ese commit ya subido al main del remoto. Revalida precondiciones dentro de la
misma transaccion. Error -> rollback y parada; nunca reintenta. Patron de pruebas/auditoria_trab/desplegar_34.py y
pruebas/auditoria_h7b/desplegar_40.py.

La migracion no crea tablas ni funciones ni cambia privilegios: las postcondiciones exigen que las filas de las guardias
(sin la columna nueva), su ACL, el historial, facturas y configuracion no cambien, que todas las filas queden CONFIRMADO
y que la web escriba y cf_lectura lea la columna nueva.

Uso: python pruebas/auditoria_trab/desplegar_41.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/41_cf_trabajadores_guardias_estado.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
ROL = "cf_trabajadores_web"
LECTURA_GENERAL = "cf_lectura"
TABLAS = ("guardias_semana", "guardias_festivo")
COLUMNA = "estado"
ESTADOS = ("PLANIFICADO", "CONFIRMADO")
# Checks de persona obligatoria en PIO y RITA que retira la 41; los de OTRA sin persona se mantienen.
CHECKS_RETIRADOS = ("guardias_semana_guardia_obligatoria", "guardias_festivo_persona_obligatoria")
CHECKS_OTRA = ("guardias_semana_otra_sin_personas", "guardias_festivo_otra_sin_persona")
CHECKS_ESTADO = ("guardias_semana_estado", "guardias_festivo_estado")
# Escritura y lectura de la web tras la 34 (no cambian en la 41).
ESCRITURA = ("trabajadoras", "convenio_anual", "eventos_calendario", "festivos", "trabajadoras_ajustes_anuales",
             *TABLAS)
SOLO_LECTURA = ("trabajadores_historial", "cf_modulos_farmacias", "v_eventos_calendario_horas")
OBJETOS = ESCRITURA + SOLO_LECTURA
ESQUEMAS_VEDADOS = ("auth", "storage", "vault", "pgsodium", "pgsodium_masks", "supabase_functions", "net", "cron",
                    "realtime", "graphql")
TRIGGERS_POR_TABLA = 4
POLITICAS_POR_TABLA = 3


def _lista(nombres) -> str:
    return "array[" + ", ".join(f"'{n}'" for n in nombres) + "]"


def _columna_estado(tabla: str) -> str:
    return ("exists (select 1 from information_schema.columns where table_schema = 'public' "
            f"and table_name = '{tabla}' and column_name = '{COLUMNA}')")


def _huella_sin_estado(tabla: str) -> str:
    """Huella por fila sin la columna nueva: vale igual antes y despues de la 41."""
    return (f"(select md5(coalesce(string_agg(md5((to_jsonb(t) - '{COLUMNA}')::text), '' "
            f"order by (to_jsonb(t) - '{COLUMNA}')::text), '')) from public.{tabla} t)")


def _huella(tabla: str) -> str:
    return (f"(select md5(coalesce(string_agg(md5(to_jsonb(t)::text), '' order by to_jsonb(t)::text), '')) "
            f" from public.{tabla} t)")


PRECONDICIONES = (
    # 1. 41 no aplicada: sin la columna estado y con los dos checks de persona obligatoria.
    "select " + " and ".join(f"not {_columna_estado(t)}" for t in TABLAS)
    + f" and (select count(*) from pg_constraint where conname = any({_lista(CHECKS_RETIRADOS)})) = 2,"
    # 2. 40 aplicada (con la 34): prevision de Cashflow y guardias presentes; TRABAJADORES = {PIO, RITA}.
    "to_regclass('public.cf_cashflow_apuntes') is not null "
    + "".join(f" and to_regclass('public.{t}') is not null" for t in TABLAS)
    + " and (select farmacias = array['PIO', 'RITA']::text[] from public.cf_modulos_farmacias "
    "       where modulo = 'TRABAJADORES'),"
    # 3. Roles presentes: la web (31) y cf_lectura (29).
    f"exists (select 1 from pg_roles where rolname = '{ROL}') "
    f"  and exists (select 1 from pg_roles where rolname = '{LECTURA_GENERAL}'),"
    # 4. 19: privilegios minimos.
    "not has_table_privilege('anon', 'public.facturas', 'SELECT') "
    "  and not has_table_privilege('authenticated', 'public.albaranes', 'UPDATE'),"
    # 5. Flags apagados y solo PIO.
    "(select normalizacion_automatica=false and conciliacion_automatica=false and luna_habilitada=false "
    "  and farmacias_habilitadas=array['PIO']::text[] from public.cf_configuracion where id),"
    # 6. Sin claims de conciliacion ni de normalizacion.
    "(select count(*)=0 from public.facturas where conciliacion_bloqueado_por is not null "
    "  or conciliacion_bloqueado_hasta>now()) and "
    "(select count(*)=0 from public.documentos_facturas where bloqueado_por is not null "
    "  or bloqueado_hasta>now() or estado_lectura='NORMALIZANDO'),"
    # 7. 2AX: ningun objeto de public con propietario distinto de postgres.
    "(select count(*)=0 from pg_class c where c.relnamespace='public'::regnamespace "
    "  and c.relkind in ('r','p','v','m','S','f') and pg_get_userbyid(c.relowner)<>'postgres') and "
    "(select count(*)=0 from pg_proc p where p.pronamespace='public'::regnamespace "
    "  and pg_get_userbyid(p.proowner)<>'postgres' "
    "  and not exists(select 1 from pg_depend d where d.objid=p.oid and d.deptype='e'))")

# Lo que la 41 no puede tocar: conteos, facturas, configuracion, permisos por modulo, el historial de Trabajadores, las
# filas de las guardias sin la columna nueva y la ACL de las dos tablas.
DATOS = ("select array[(select count(*) from public.documentos_facturas), "
         "(select count(*) from public.facturas), "
         "(select count(*) from public.conciliaciones), "
         "(select count(*) from public.albaranes), "
         "(select count(*) from public.trabajadoras), "
         "(select count(*) from public.eventos_calendario), "
         "(select count(*) from public.festivos), "
         "(select count(*) from public.trabajadores_historial), "
         "(select count(*) from public.guardias_semana), "
         "(select count(*) from public.guardias_festivo)], "
         + _huella("facturas") + ", "
         "(select md5(to_jsonb(c)::text) from public.cf_configuracion c where c.id), "
         + _huella("cf_modulos_farmacias") + ", "
         + _huella("trabajadores_historial") + ", "
         + ", ".join(_huella_sin_estado(t) for t in TABLAS) + ", "
         "(select string_agg(relname || ':' || coalesce(relacl::text, ''), ',' order by relname) from pg_class "
         f" where relnamespace = 'public'::regnamespace and relname = any({_lista(TABLAS)}))")
# Conteos, facturas, configuracion, modulos, historial, una huella por tabla de guardias y la ACL.
N_DATOS = 6 + len(TABLAS)

PRIVILEGIOS_WEB = (
    " and ".join(f"has_table_privilege('{ROL}', 'public.{t}', 'SELECT,INSERT,UPDATE')" for t in ESCRITURA)
    + " and " + " and ".join(f"has_table_privilege('{ROL}', 'public.{t}', 'SELECT')" for t in SOLO_LECTURA)
    # La columna nueva: la web la lee, la escribe al dar de alta y la cambia (cada privilegio por separado).
    + " and " + " and ".join(f"has_column_privilege('{ROL}', 'public.{t}', '{COLUMNA}', '{p}')"
                             for t in TABLAS for p in ("SELECT", "INSERT", "UPDATE"))
    # Nada mas: ni DELETE/TRUNCATE en el modulo, ni escritura en historial o permisos, ni lectura fuera del modulo.
    + f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and c.relkind in ('r','p','v','m','f') and (has_table_privilege('{ROL}', c.oid, "
    f"  'DELETE,TRUNCATE,REFERENCES,TRIGGER') "
    f"  or (has_table_privilege('{ROL}', c.oid, 'INSERT,UPDATE') and c.relname <> all({_lista(ESCRITURA)})) "
    f"  or (has_table_privilege('{ROL}', c.oid, 'SELECT') and c.relname <> all({_lista(OBJETOS)}))))"
    f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind = 'S' "
    f"  and case when c.relkind = 'S' then has_sequence_privilege('{ROL}', c.oid, 'USAGE,SELECT,UPDATE') end)"
    f" and not exists (select 1 from pg_proc p where p.pronamespace = 'public'::regnamespace "
    f"  and has_function_privilege('{ROL}', p.oid, 'EXECUTE') and p.prorettype <> 'event_trigger'::regtype "
    f"  and (p.prosecdef or (p.provolatile = 'v' and p.prorettype <> 'trigger'::regtype)))"
    + "".join(f" and not coalesce(has_schema_privilege('{ROL}', to_regnamespace('{e}'), 'USAGE'), false)"
              for e in ESQUEMAS_VEDADOS))

# cf_lectura lee la columna nueva y sigue sin escribir; ningun privilegio de columna sobre ella (todo es de tabla).
LECTURA = (
    " and ".join(f"has_column_privilege('{LECTURA_GENERAL}', 'public.{t}', '{COLUMNA}', 'SELECT') "
                 f"and not has_table_privilege('{LECTURA_GENERAL}', 'public.{t}', 'INSERT,UPDATE,DELETE,TRUNCATE')"
                 for t in TABLAS)
    + " and not exists (select 1 from pg_attribute a "
    f"  where a.attrelid = any(array[{', '.join(f'{chr(39)}public.{t}{chr(39)}::regclass' for t in TABLAS)}]) "
    f"  and a.attname = '{COLUMNA}' and a.attacl is not null)")

ESTRUCTURA = (
    # Columna estado: text not null, default CONFIRMADO, con su check; todas las filas CONFIRMADO.
    " and ".join(
        f"(select data_type = 'text' and is_nullable = 'NO' and column_default like '''CONFIRMADO''%' "
        f"  from information_schema.columns where table_schema = 'public' and table_name = '{t}' "
        f"  and column_name = '{COLUMNA}') "
        f"and (select count(*) from public.{t} where (to_jsonb({t}) ->> '{COLUMNA}') is distinct from 'CONFIRMADO') = 0 "
        f"and (select count(*) from pg_policy where polrelid = 'public.{t}'::regclass) = {POLITICAS_POR_TABLA} "
        f"and (select relrowsecurity from pg_class where oid = 'public.{t}'::regclass) "
        f"and (select count(*) from pg_trigger where tgrelid = 'public.{t}'::regclass and not tgisinternal) "
        f"    = {TRIGGERS_POR_TABLA}"
        for t in TABLAS)
    + "".join(f" and (select pg_get_constraintdef(oid) like '%PLANIFICADO%CONFIRMADO%' from pg_constraint "
              f"      where conname = '{c}')" for c in CHECKS_ESTADO)
    + f" and not exists (select 1 from pg_constraint where conname = any({_lista(CHECKS_RETIRADOS)}))"
    + f" and (select count(*) from pg_constraint where conname = any({_lista(CHECKS_OTRA)})) = {len(CHECKS_OTRA)}"
    + " and (select farmacias = array['PIO', 'RITA']::text[] from public.cf_modulos_farmacias "
    "       where modulo = 'TRABAJADORES') "
    "  and (select farmacias_habilitadas = array['PIO']::text[] from public.cf_configuracion where id)")

POSTCONDICIONES = (
    f"{DATOS},"
    f"{PRIVILEGIOS_WEB},"
    f"{LECTURA},"
    f"{ESTRUCTURA},"
    # Propietario de las guardias: postgres (2AX), sin cambios.
    "(select bool_and(pg_get_userbyid(relowner) = 'postgres') from pg_class "
    f" where relnamespace = 'public'::regnamespace and relname = any({_lista(TABLAS)}))")


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_41_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_41_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_trab_deploy_41")
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
            datos_antes = list(cur.fetchone())
            cur.execute(cuerpo)
            cur.execute(POSTCONDICIONES)
            fila = cur.fetchone()
            datos, (privilegios, lectura, estructura, propietario) = fila[:N_DATOS], fila[N_DATOS:]
            registro["postcondiciones"] = {
                "datos_sin_cambios": [list(datos[0]), *datos[1:]] == [list(datos_antes[0]), *datos_antes[1:]],
                "privilegios_web": privilegios, "lectura": lectura, "estructura": estructura,
                "propietario": propietario}
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


def cli(argv: list[str]) -> None:
    """Entrada de linea de ordenes: antes de nada, el commit indicado debe estar ya en el main del remoto (leido con
    ls-remote; modulo comun ``puerta_git``). ``main`` sigue siendo ensayable sin remoto."""
    if len(argv) != 3:
        raise SystemExit(__doc__)
    sys.path.insert(0, str(ROOT))
    from src.facturas.runtime_supabase.puerta_git import exigir_commit_en_origen
    exigir_commit_en_origen(argv[0], ROOT)
    main(argv[0], argv[1], Path(argv[2]))


if __name__ == "__main__":
    cli(sys.argv[1:])
