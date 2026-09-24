"""Certificacion LOCAL exclusivamente por docker exec, sin URLs ni workers.

Ejecutar con el Python del proyecto. Requiere contenedor cf-hito2f1-local
con label controlfarmacias.certificacion=2f1, network none y sin puertos.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = 'cf-hito2f1-local'
MIG = ROOT / 'sql/migrations'
PRE = ROOT / 'sql/preflight'
STG = ROOT / 'sql/staging'
LEGACY = ['PENDIENTE', 'PROCESANDO', 'EXTRAIDA', 'REVISION', 'ERROR']
FINAL = LEGACY + ['NORMALIZANDO', 'NORMALIZADA']


def docker(*args, input=None, check=True):
    r = subprocess.run(['docker', *args], input=input, text=True,
                       encoding='utf-8', capture_output=True, timeout=90)
    if check and r.returncode:
        raise RuntimeError(r.stderr)
    return r


def expand(path):
    lines = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('\\ir '):
            lines.append(expand((path.parent / line[4:].strip()).resolve()))
        else:
            lines.append(line)
    return '\n'.join(lines)


def sql(db, statement, fail=None):
    r = docker('exec', '-i', CONTAINER, 'psql', '-X', '-qAt',
               '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose',
               '-U', 'postgres', '-d', db, input=statement, check=fail is None)
    if fail:
        assert r.returncode != 0 and fail in r.stderr, (r.stdout, r.stderr)
    return r.stdout.strip()


def file(db, path):
    return sql(db, expand(path))


def fingerprint(db, table):
    rows = sql(db, f'SELECT row_to_json(t)::text FROM public.{table} t ORDER BY id;')
    return hashlib.sha256(rows.encode()).hexdigest()


def fresh(db):
    docker('exec', CONTAINER, 'createdb', '-U', 'postgres', db)
    file(db, STG / '00_baseline_controlfarmacias.sql')


def destroy(db):
    assert db.startswith('cf_2f1_')
    docker('exec', CONTAINER, 'dropdb', '-U', 'postgres', db)


def state_status(db, post=False):
    # The last SELECT is the same semantic classifier in both self-contained scripts.
    path = PRE / ('postflight_supabase_v1.sql' if post else 'preflight_supabase_controlfarmacias.sql')
    text = path.read_text(encoding='utf-8')
    return sql(db, text[text.index('-- Contrato semantico'):])


def cases():
    db = 'cf_2f1_cases'
    fresh(db)
    assert 'ESTADO_LECTURA_LEGACY_COMPATIBLE_PARA_MIGRAR' in state_status(db)
    for state in LEGACY:
        sql(db, "INSERT INTO public.documentos_facturas(archivo_nombre,archivo_ruta,estado_lectura) "
            f"VALUES ('SINTETICO_{state}','local/{state}','{state}');")
    before = fingerprint(db, 'documentos_facturas')
    # Names and list ordering must not determine recognition.
    sql(db, 'ALTER TABLE public.documentos_facturas RENAME CONSTRAINT '
        'facturas_estado_lectura_check TO nombre_legacy_alternativo;')
    file(db, MIG / '08b_cf_estado_lectura_compatibilidad.sql')
    assert before == fingerprint(db, 'documentos_facturas')
    print('CASOS_A_E_FILAS_COMPLETAS_PRESERVADAS=OK', flush=True)
    for state in FINAL:
        sql(db, f"UPDATE public.documentos_facturas SET estado_lectura='{state}';")
    sql(db, "UPDATE public.documentos_facturas SET estado_lectura='ESTADO_FALSO';", fail='23514')
    check_oid = sql(db, "SELECT oid FROM pg_constraint WHERE conrelid='public.documentos_facturas'::regclass "
                   "AND conname='cf_documentos_estado_lectura_check';")
    before = fingerprint(db, 'documentos_facturas')
    file(db, MIG / '08b_cf_estado_lectura_compatibilidad.sql')
    assert check_oid == sql(db, "SELECT oid FROM pg_constraint WHERE conrelid='public.documentos_facturas'::regclass "
                           "AND conname='cf_documentos_estado_lectura_check';")
    assert before == fingerprint(db, 'documentos_facturas')
    assert 'ESTADO_LECTURA_V1_COMPATIBLE' in state_status(db)
    print('CASOS_F_I_ESCRITURAS_RECHAZO_IDEMPOTENCIA=OK', flush=True)
    # Actual production UNIQUE name must remain the only equivalent guarantee.
    before = sql(db, "SELECT indexrelid FROM pg_index WHERE indrelid='public.albaranes'::regclass ORDER BY indexrelid;")
    file(db, MIG / '06b_cf_integridad_albaranes.sql')
    file(db, MIG / '06b_cf_integridad_albaranes.sql')
    assert before == sql(db, "SELECT indexrelid FROM pg_index WHERE indrelid='public.albaranes'::regclass ORDER BY indexrelid;")
    print('UNIQUE_ALBARANES_CONTADOR_UNICO_RECONOCIDA=OK', flush=True)
    destroy(db)
    for name, mutation in {
        'sin_check': 'ALTER TABLE public.documentos_facturas DROP CONSTRAINT facturas_estado_lectura_check;',
        'desconocido': "ALTER TABLE public.documentos_facturas DROP CONSTRAINT facturas_estado_lectura_check; "
            "ALTER TABLE public.documentos_facturas ADD CHECK (estado_lectura <> 'ESTADO_FALSO');",
        'multiples': "ALTER TABLE public.documentos_facturas ADD CHECK (length(estado_lectura)>0);",
        'valor_inesperado': "ALTER TABLE public.documentos_facturas DROP CONSTRAINT facturas_estado_lectura_check; "
            "INSERT INTO public.documentos_facturas(archivo_nombre,archivo_ruta,estado_lectura) "
            "VALUES ('SINTETICO','local','ESTADO_FALSO');",
    }.items():
        db = 'cf_2f1_' + name
        fresh(db)
        sql(db, mutation)
        before = fingerprint(db, 'documentos_facturas')
        assert 'BLOQUEADO_ESTADO_LECTURA_DESCONOCIDO' in state_status(db)
        sql(db, expand(MIG / '08b_cf_estado_lectura_compatibilidad.sql'), fail='MIGRACION_08B_BLOQUEADA')
        assert before == fingerprint(db, 'documentos_facturas')
        print('GUARD_' + name.upper() + '=OK', flush=True)
        destroy(db)


def pgcrypto_compatibilidad():
    db = 'cf_2f1_pgcrypto'
    fresh(db)
    assert sql(db, "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n "
               "ON n.oid=e.extnamespace WHERE e.extname='pgcrypto';") == 'extensions'
    sql(db, "SET search_path=public; SELECT digest('abc','sha256');", fail='42883')
    esperado = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    assert sql(db, "SET search_path=public; SELECT encode(extensions.digest('abc','sha256'),'hex');") == esperado
    file(db, MIG / '07_cf_proveedores_config.sql')
    assert sql(db, "SELECT to_regprocedure('public.cf_preflight_pio_valido()') IS NOT NULL;") == 't'
    print('PGCRYPTO_EXTENSIONS_FORMA_ANTIGUA_BLOQUEADA_Y_CUALIFICADA_OK', flush=True)
    destroy(db)


def concurrency(db, factura=False):
    if factura:
        sql(db, "UPDATE public.facturas SET conciliacion_reintento_solicitado_at=NULL; "
            "UPDATE public.facturas SET conciliacion_reintento_solicitado_at=now(), "
            "estado_normalizacion='NORMALIZADA',estado_conciliacion_cf='PENDIENTE_CONCILIAR' "
            "WHERE proyeccion_clave='STG-RPC-A';")
        rpc = 'cf_reclamar_factura_conciliacion'
    else:
        sql(db, "UPDATE public.documentos_facturas SET reprocesar_solicitado_at=NULL; "
            "UPDATE public.documentos_facturas SET estado_lectura='PENDIENTE',reprocesar_solicitado_at=now() "
            "WHERE archivo_nombre='SINTETICO_PIO_090.pdf';")
        rpc = 'cf_reclamar_documento_normalizacion'
    a = subprocess.Popen(['docker', 'exec', '-i', CONTAINER, 'psql', '-X', '-qAt',
        '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', db],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8')
    try:
        a.stdin.write(f"BEGIN; SELECT count(*) FROM public.{rpc}('local-a',300);\n")
        a.stdin.flush()
        # A reports its acquired claim before B starts. No race based on a sleep.
        assert a.stdout.readline().strip() == '1'
        b = sql(db, f"SET statement_timeout='2s'; SELECT count(*) FROM public.{rpc}('local-b',300);")
        assert b == '0', b
        a.stdin.write('ROLLBACK;\n\\q\n'); a.stdin.flush()
        assert a.wait(timeout=10) == 0
    finally:
        if a.poll() is None:
            a.kill(); a.wait()
    print('CONCURRENCIA_DOS_SESIONES_' + rpc + '=OK', flush=True)


def cycle(number):
    db = f'cf_2f1_cycle_{number}'
    fresh(db)
    pre = file(db, PRE / 'preflight_supabase_controlfarmacias.sql')
    assert 'ESTADO_LECTURA_LEGACY_COMPATIBLE_PARA_MIGRAR' in pre
    assert 'APTO_DESPLIEGUE_V1' in pre
    for path in sorted(MIG.glob('*_cf_*.sql')):
        if path.name.startswith('13_'):
            continue
        file(db, path)
    file(db, STG / '01_seed_controlfarmacias.sql')
    post = file(db, PRE / 'postflight_supabase_v1.sql')
    assert 'ESTADO_LECTURA_V1_COMPATIBLE' in post
    for name in ['02_validar_migraciones.sql', '03_test_rpc_normalizacion.sql',
                 '04_test_concurrencia_idempotencia.sql']:
        print(file(db, STG / name), flush=True)
    print(file(db, STG / '07_test_claim_conciliacion_v2.sql'), flush=True)
    concurrency(db)
    concurrency(db, factura=True)
    print(file(db, STG / '05_test_conciliacion.sql'), flush=True)
    before = fingerprint(db, 'documentos_facturas')
    rita = sql(db, "SELECT row_to_json(f)::text FROM public.facturas f WHERE farmacia='RITA' ORDER BY id;")
    print(file(db, STG / '06_test_backfill_pio.sql'), flush=True)
    assert before == fingerprint(db, 'documentos_facturas')
    assert rita == sql(db, "SELECT row_to_json(f)::text FROM public.facturas f WHERE farmacia='RITA' ORDER BY id;")
    assert 'ESTADO_LECTURA_V1_COMPATIBLE' in state_status(db, post=True)
    assert sql(db, "SELECT normalizacion_automatica,conciliacion_automatica,luna_habilitada,"
               "farmacias_habilitadas FROM public.cf_configuracion;") == 'f|f|f|{PIO}'
    assert sql(db, 'SELECT count(*) FROM public.normalizacion_ejecuciones WHERE uso_luna;') == '0'
    print(f'CICLO_{number}_COMPLETO_OK', flush=True)
    destroy(db)
    print(f'CICLO_{number}_BASE_DESTRUIDA', flush=True)


if __name__ == '__main__':
    info = json.loads(docker('inspect', CONTAINER).stdout)[0]
    assert info['Config']['Labels'].get('controlfarmacias.certificacion') == '2f1'
    assert info['HostConfig']['NetworkMode'] == 'none'
    assert not info['HostConfig']['PortBindings']
    print('DESTINO_CERTIFICACION=LOCAL', flush=True)
    pgcrypto_compatibilidad()
    cases()
    cycle(1)
    cycle(2)
    print('ESTADO_LECTURA_POSTGRESQL_CERTIFICADO', flush=True)
