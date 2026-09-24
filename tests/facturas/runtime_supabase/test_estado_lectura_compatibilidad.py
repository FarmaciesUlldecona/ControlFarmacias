from __future__ import annotations

import ast
import re
from pathlib import Path

from src.facturas.runtime_supabase.modelos import EstadoLecturaDocumento

ROOT = Path(__file__).resolve().parents[3]
LEGACY = {'PENDIENTE', 'PROCESANDO', 'EXTRAIDA', 'REVISION', 'ERROR'}
V1 = {'PENDIENTE', 'NORMALIZANDO', 'NORMALIZADA', 'ERROR'}
FINAL = LEGACY | V1


def test_check_final_exactamente_union_de_contratos():
    sql = (ROOT / 'sql/migrations/08b_cf_estado_lectura_compatibilidad.sql').read_text()
    check = re.search(r'check \(estado_lectura in \((.*?)\)\)', sql, re.S).group(1)
    assert set(re.findall(r"'([A-Z_]+)'", check)) == FINAL
    assert {state.value for state in EstadoLecturaDocumento} == V1


def test_baseline_reproduce_el_check_productivo_y_unique_real():
    sql = (ROOT / 'sql/staging/00_baseline_controlfarmacias.sql').read_text()
    check = re.search(r'check \(estado_lectura in \((.*?)\)\)', sql, re.S).group(1)
    assert set(re.findall(r"'([A-Z_]+)'", check)) == LEGACY
    assert 'constraint albaranes_contador_unico unique (farmacia, id_contador)' in sql
    assert 'unique (farmacia, archivo_hash)' in sql


def test_todos_los_writers_sql_documentales_cubiertos_por_check():
    encontrados = set()
    for path in (ROOT / 'sql/migrations').glob('*.sql'):
        sql = re.sub(r'--[^\n]*', '', path.read_text(encoding='utf-8'))
        for update in re.findall(r'update\s+public\.documentos_facturas\s+.*?;', sql, re.I | re.S):
            states = re.findall(r"estado_lectura\s*=\s*'([A-Z_]+)'", update)
            assert set(states) <= FINAL, path.name
            encontrados.update(states)
    assert encontrados == V1


def test_writers_python_documentales_no_introducen_estados_ajenos():
    encontrados = set()
    for path in (ROOT / 'src').rglob('*.py'):
        text = path.read_text(encoding='utf-8-sig')
        if 'estado_lectura' not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == 'estado_lectura':
                        assert isinstance(value, ast.Constant), f'Writer dinamico requiere auditoria: {path}'
                        assert value.value in FINAL
                        encontrados.add(value.value)
    assert encontrados == {'PENDIENTE'}


def test_worker_delega_las_transiciones_al_repositorio_rpc():
    worker = (ROOT / 'src/facturas/runtime_supabase/worker_normalizacion.py').read_text()
    repo = (ROOT / 'src/facturas/runtime_supabase/repositorios.py').read_text()
    assert 'estado_lectura' not in worker
    assert 'estado_lectura' not in repo
    for method in ('reclamar_documento', 'persistir_normalizacion', 'fallar_ejecucion'):
        assert 'self.repositorio.' + method in worker
    for rpc in ('cf_reclamar_documento_normalizacion', 'cf_persistir_normalizacion',
                'cf_registrar_fallo_normalizacion'):
        assert '"' + rpc + '"' in repo


def test_migracion_08b_no_cambia_filas_defaults_ni_otros_checks():
    sql = (ROOT / 'sql/migrations/08b_cf_estado_lectura_compatibilidad.sql').read_text()
    assert not re.search(r'\b(insert|update|delete|truncate)\b', sql, re.I)
    assert 'alter column' not in sql.lower()
    assert 'v.checks_en_columna <> 1' in sql
    assert 'v.forma_reconocida is not true' in sql
    assert 'drop constraint %I' in sql
    assert 'v.constraint_name' in sql
    assert 'lock table public.documentos_facturas in access exclusive mode' in sql


def test_pre_post_no_ejecutan_writers_y_comparten_detector():
    paths = [ROOT / 'sql/preflight' / name for name in (
        'preflight_supabase_controlfarmacias.sql', 'postflight_supabase_v1.sql')]
    blocks = []
    for path in paths:
        text = path.read_text()
        blocks.append(text[text.index('-- Contrato semantico'):])
    assert blocks[0] == blocks[1]
    assert 'BLOQUEADO_ESTADO_LECTURA_DESCONOCIDO' in blocks[0]
    assert 'estado_lectura_v1_ok' in blocks[0]
