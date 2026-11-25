"""R21: despliega EXCLUSIVAMENTE la migracion 39 (numero exacto + 1 a 3 complementarios), una vez, en una transaccion.

NO se ejecuta en el hito R21 (solo se ensaya en local, con el rol que imita al postgres de Supabase). Requiere
confirmacion expresa de Pio en chat (hito 39-D) y los flags apagados por Pio durante la ventana. No invoca RPC.
Normaliza el SQL a LF y exige que coincida byte a byte con la version del commit indicado (git show <commit>:...), y la
entrada de linea de ordenes exige ademas ese commit ya subido al main del remoto. Revalida precondiciones dentro de la
misma transaccion. Error -> rollback y parada; nunca reintenta. Patron de pruebas/auditoria_r20/desplegar_36.py. La 39
no nombra el rol del sistema. La marca conciliacion_r21 queda a false (R21-D5): la enciende Pio en el editor SQL tras
el postcheck.

Uso: python pruebas/auditoria_r21/desplegar_39.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/39_cf_r21_complementarios.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
AUXILIAR = "public.cf_linea_r17_valida(uuid,text,jsonb,jsonb)"
PERSISTIR = "public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)"
COLUMNA = "conciliacion_r21"
COLUMNA_R20 = "conciliacion_r20"

_COLUMNA_EXISTE = ("exists (select 1 from information_schema.columns where table_schema = 'public' "
                   f"and table_name = 'cf_configuracion' and column_name = '{COLUMNA}')")

PRECONDICIONES = (
    # 1. 39 no aplicada: sin la columna marca.
    f"select not {_COLUMNA_EXISTE},"
    # 2. 38 aplicada (cada migracion exige la anterior) y la 36 (marca de R20), con la auxiliar R17 y el detalle por
    #    linea (24 y 30).
    "to_regclass('public.cf_cashflow_saldos') is not null "
    "  and exists (select 1 from information_schema.columns where table_schema = 'public' "
    f"  and table_name = 'cf_configuracion' and column_name = '{COLUMNA_R20}') "
    f"  and to_regprocedure('{AUXILIAR}') is not null "
    "  and to_regprocedure('public.cf_detalles_por_linea(uuid,jsonb)') is not null,"
    # 3. Flags apagados y solo PIO.
    "(select normalizacion_automatica=false and conciliacion_automatica=false and luna_habilitada=false "
    "  and farmacias_habilitadas=array['PIO']::text[] from public.cf_configuracion where id),"
    # 4. Sin claims de conciliacion ni de normalizacion.
    "(select count(*)=0 from public.facturas where conciliacion_bloqueado_por is not null "
    "  or conciliacion_bloqueado_hasta>now()) and "
    "(select count(*)=0 from public.documentos_facturas where bloqueado_por is not null "
    "  or bloqueado_hasta>now() or estado_lectura='NORMALIZANDO'),"
    # 5. 2AX: ningun objeto de public con propietario distinto de postgres.
    "(select count(*)=0 from pg_class c where c.relnamespace='public'::regnamespace "
    "  and c.relkind in ('r','p','v','m','S','f') and pg_get_userbyid(c.relowner)<>'postgres') and "
    "(select count(*)=0 from pg_proc p where p.pronamespace='public'::regnamespace "
    "  and pg_get_userbyid(p.proowner)<>'postgres' "
    "  and not exists(select 1 from pg_depend d where d.objid=p.oid and d.deptype='e'))")

# Lo que la 39 no puede tocar: conteos y huellas de facturas, conciliacion, reservas y albaranes; la configuracion sin
# la columna nueva (incluida la marca de R20); la RPC de persistencia (texto y ACL) y la ACL de la auxiliar.
DATOS = ("select array[(select count(*) from public.documentos_facturas), "
         "(select count(*) from public.facturas), "
         "(select count(*) from public.conciliaciones), "
         "(select count(*) from public.conciliacion_detalles), "
         "(select count(*) from public.conciliacion_albaranes_reservados), "
         "(select count(*) from public.albaranes)], "
         "(select md5(coalesce(string_agg(md5(to_jsonb(f)::text), '' order by f.id), '')) from public.facturas f), "
         "(select md5(coalesce(string_agg(md5(to_jsonb(c)::text), '' order by c.id), '')) from public.conciliaciones c), "
         "(select md5(coalesce(string_agg(md5(to_jsonb(d)::text), '' order by d.id), '')) "
         " from public.conciliacion_detalles d), "
         f"(select md5((to_jsonb(c) - '{COLUMNA}')::text) from public.cf_configuracion c where c.id), "
         f"(select md5(prosrc || coalesce(proacl::text, '') || prosecdef::text) from pg_proc "
         f" where oid = '{PERSISTIR}'::regprocedure), "
         f"(select coalesce(proacl::text, '') || pg_get_userbyid(proowner) from pg_proc "
         f" where oid = '{AUXILIAR}'::regprocedure)")

POSTCONDICIONES = (
    f"{DATOS},"
    # Columna marca: boolean not null default false, y false en la fila de configuracion (R21-D5).
    f"{_COLUMNA_EXISTE} and (select data_type = 'boolean' and is_nullable = 'NO' and column_default = 'false' "
    "  from information_schema.columns where table_schema = 'public' and table_name = 'cf_configuracion' "
    f"  and column_name = '{COLUMNA}') and (select {COLUMNA} is false from public.cf_configuracion where id),"
    # Auxiliar redefinida (R17 + R20 + R21), propietario postgres y sin privilegios para nadie mas.
    f"(select prosrc like '%R21 (39)%' and prosrc like '%R20:%' and pg_get_userbyid(proowner) = 'postgres' "
    f"  from pg_proc where oid = '{AUXILIAR}'::regprocedure) "
    f"  and (select count(*) = 0 from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, "
    f"       acldefault('f', p.proowner))) a where p.oid = '{AUXILIAR}'::regprocedure and a.grantee <> p.proowner)")


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_39_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_39_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_r21_deploy_39")
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
            n = len(datos_antes)
            datos, (columna, auxiliar) = fila[:n], fila[n:]
            registro["postcondiciones"] = {
                "datos_sin_cambios": [list(datos[0]), *datos[1:]] == datos_antes,
                "columna_marca": columna, "auxiliar_r17_r20_r21": auxiliar}
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
    ls-remote; modulo comun ``puerta_git``, 2026-11-19). ``main`` sigue siendo ensayable sin remoto."""
    if len(argv) != 3:
        raise SystemExit(__doc__)
    sys.path.insert(0, str(ROOT))
    from src.facturas.runtime_supabase.puerta_git import exigir_commit_en_origen
    exigir_commit_en_origen(argv[0], ROOT)
    main(argv[0], argv[1], Path(argv[2]))


if __name__ == "__main__":
    cli(sys.argv[1:])
