"""Hito 2BM: despliega EXCLUSIVAMENTE la migracion 28 (persistencia multifactura ligera), una vez, en una
transaccion.

NO se ejecuta en el hito 2BM (solo se ensaya en local). Requiere confirmacion expresa de Pio en chat. No
invoca RPC funcionales. Normaliza el SQL a LF y exige que coincida byte a byte con la version del commit
indicado (git show <commit>:...). Revalida precondiciones dentro de la misma transaccion. Error -> rollback y
parada; nunca reintenta. Patron de pruebas/auditoria_2bl/desplegar_27.py.

Uso: python pruebas/auditoria_2bm/desplegar_28.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/28_cf_persistencia_multifactura_ligera.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
NORMALIZACION = "'public.cf_persistir_normalizacion(uuid,text,text,text,text,jsonb)'::regprocedure"
MULTI_6 = "'public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[])'::regprocedure"
MULTI_7 = "'public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)'::regprocedure"
NUCLEO_NORMALIZACION = "public.cf_persistir_normalizacion_nucleo(uuid,text,text,text,text,jsonb,jsonb)"
NUCLEO_NORMALIZACION_9 = "public.cf_persistir_normalizacion_nucleo(uuid,text,text,text,text,jsonb,jsonb,jsonb,jsonb)"
NUCLEO_MULTI = "public.cf_persistir_documento_multifactura_nucleo(uuid,text,text,text,jsonb,text[],text)"
PERSISTIDA = "public.cf_ejecucion_persistida(uuid,text)"
REFERENCIA = "public.cf_referencia_factura(jsonb,text)"
DESDE_REFERENCIA = "public.cf_factura_desde_referencia(jsonb,jsonb)"
MATERIALIZAR = "public.cf_materializar_referencia()"
INTERNAS = (NUCLEO_NORMALIZACION, NUCLEO_NORMALIZACION_9, NUCLEO_MULTI, PERSISTIDA, REFERENCIA, DESDE_REFERENCIA,
            MATERIALIZAR)
COLUMNAS_LZ4 = (("normalizacion_ejecuciones", "resultado_json"), ("facturas", "datos_extraidos"),
                ("facturas_albaranes_extraidos", "provenance"), ("facturas_vencimientos", "provenance"),
                ("facturas_impuestos", "provenance"), ("facturas_movimientos", "provenance"),
                ("facturas_incidencias", "provenance"), ("facturas_incidencias", "detalle_tecnico"))
FIRMA_27 = "jsonb_build_object('documento',p_resultado,'seleccion',to_jsonb(p_segmentos_autorizados))::text"
ACUMULADO_27 = "nuevas:=nuevas || jsonb_build_array("
DOCUMENTO_27 = "coalesce(p_resultado->'resultado_json', p_resultado);"
# Textos de la 27 dentro de un literal SQL: comillas simples duplicadas.
FIRMA_27, ACUMULADO_27, DOCUMENTO_27 = (s.replace("'", "''") for s in (FIRMA_27, ACUMULADO_27, DOCUMENTO_27))
COMPRESION = " or ".join(f"(attrelid = 'public.{t}'::regclass and attname = '{c}')" for t, c in COLUMNAS_LZ4)

PRECONDICIONES = (
    # 28 no aplicada aun.
    f"select to_regprocedure('{MATERIALIZAR}') is null and to_regprocedure('{NUCLEO_NORMALIZACION_9}') is null,"
    # 27 aplicada.
    f"to_regprocedure('{PERSISTIDA}') is not null,"
    # Las funciones que se redefinen son las de la 27 (firma con objeto intermedio, acumulado jsonb, documento
    # dentro de p_resultado) y las columnas siguen con la compresion por defecto.
    f"position('{FIRMA_27}' in (select prosrc from pg_proc where oid = '{NUCLEO_MULTI}'::regprocedure)) > 0 "
    f"  and position('{ACUMULADO_27}' in (select prosrc from pg_proc where oid = '{NUCLEO_MULTI}'::regprocedure)) > 0 "
    f"  and position('{DOCUMENTO_27}' in (select prosrc from pg_proc "
    f"  where oid = '{NUCLEO_NORMALIZACION}'::regprocedure)) > 0 "
    f"  and (select count(*) = {len(COLUMNAS_LZ4)} and bool_and(attcompression = '') from pg_attribute "
    f"  where {COMPRESION}),"
    # 19: privilegios minimos.
    "not has_table_privilege('anon', 'public.facturas', 'SELECT') "
    "  and not has_table_privilege('service_role', 'public.albaranes', 'UPDATE'),"
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

DATOS = ("select array[(select count(*) from public.documentos_facturas), "
         "(select count(*) from public.facturas), "
         "(select count(*) from public.normalizacion_ejecuciones), "
         "(select count(*) from public.historial_facturas), "
         "(select count(*) from public.conciliaciones), "
         "(select count(*) from public.conciliacion_albaranes_reservados)], "
         "(select md5(coalesce(string_agg(md5(to_jsonb(e)::text), '' order by e.id), '')) "
         "   from public.normalizacion_ejecuciones e), "
         "(select md5(coalesce(string_agg(md5(to_jsonb(f)::text), '' order by f.id), '')) from public.facturas f)")

POSTCONDICIONES = (
    f"{DATOS},"
    # Objetos de la 28: funciones internas SECURITY DEFINER, nucleos que las usan y columnas en lz4.
    + " and ".join(f"(select prosecdef from pg_proc where oid = '{f}'::regprocedure)"
                   for f in (NUCLEO_NORMALIZACION_9, REFERENCIA, DESDE_REFERENCIA, MATERIALIZAR))
    + f"  and position('cf_referencia_factura' in (select prosrc from pg_proc where oid = '{NUCLEO_MULTI}'::regprocedure)) > 0 "
    f"  and position('{FIRMA_27}' in (select prosrc from pg_proc where oid = '{NUCLEO_MULTI}'::regprocedure)) > 0 "
    "  and exists (select 1 from pg_trigger where tgrelid = 'public.facturas'::regclass "
    "  and tgname = 'facturas_materializar_referencia' and tgenabled = 'O') "
    f"  and (select count(*) = {len(COLUMNAS_LZ4)} and bool_and(attcompression = 'l') from pg_attribute "
    f"  where {COMPRESION}),"
    # Privilegios: las RPC solo para service_role; funciones internas y firma de 6 parametros, solo el propietario.
    f"has_function_privilege('service_role', {NORMALIZACION}, 'EXECUTE') "
    f"  and has_function_privilege('service_role', {MULTI_7}, 'EXECUTE') "
    f"  and not has_function_privilege('service_role', {MULTI_6}, 'EXECUTE') "
    + "".join(f"  and not has_function_privilege('service_role', '{f}', 'EXECUTE') " for f in INTERNAS)
    + "".join(f"  and not has_function_privilege('{rol}', {f}, 'EXECUTE') "
              for rol in ("anon", "authenticated")
              for f in (NORMALIZACION, MULTI_6, MULTI_7, *(f"'{i}'" for i in INTERNAS)))
    + "  and not has_table_privilege('service_role', 'public.albaranes', 'UPDATE')")


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_28_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_28_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2bm_deploy_28")
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
            # Comprobacion dentro de la misma transaccion: objetos creados, ninguna fila cambiada.
            cur.execute(POSTCONDICIONES)
            conteos, ejecuciones, facturas, objetos, privilegios = cur.fetchone()
            registro["postcondiciones"] = {"datos_sin_cambios": [list(conteos), ejecuciones, facturas] == datos_antes,
                                           "objetos_28": objetos, "privilegios": privilegios}
            if registro["postcondiciones"] != {"datos_sin_cambios": True, "objetos_28": True, "privilegios": True}:
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
