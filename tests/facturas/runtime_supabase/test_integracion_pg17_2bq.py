"""Hito 2BQ: la base local de tests (pg17_local) alineada con Supabase en lo que produccion tiene y local no tenia.

- columna documentos_facturas.observaciones en su posicion productiva (tras requiere_revision);
- indices albaranes_fecha_idx y albaranes_proveedor_idx;
- rls_auto_enable() con la ACL productiva (creada con los privilegios por defecto de Supabase, sin GRANT explicito);
- USAGE explicito sobre el esquema public para anon, authenticated y postgres;
- la 29 aplicada con la imitacion del postgres de Supabase: el creador queda con ADMIN sobre cf_lectura (INHERIT y
  SET no), como postgres en produccion.
Sin produccion ni Farmatic.
"""
from __future__ import annotations

import pytest

import pg17_local as pgl

pytestmark = pytest.mark.pg17_local


@pytest.fixture
def pg29(pg17_nueva_base):
    return pg17_nueva_base("29")


def test_observaciones_en_su_posicion(pg29):
    columnas = pg29.sql("select string_agg(attname, ',' order by attnum) from pg_attribute "
                        "where attrelid = 'public.documentos_facturas'::regclass and attnum > 0 and not attisdropped")
    nombres = columnas.split(",")
    assert nombres[nombres.index("requiere_revision") + 1] == "observaciones"
    assert pg29.sql("select format_type(atttypid, atttypmod), attnotnull from pg_attribute where attrelid = "
                    "'public.documentos_facturas'::regclass and attname = 'observaciones'") == "text|f"


def test_indices_productivos_de_albaranes(pg29):
    assert pg29.sql("select string_agg(indexrelid::regclass::text || '=' || pg_get_indexdef(indexrelid), ';' "
                    "order by 1) from pg_index where indrelid = 'public.albaranes'::regclass and indexrelid::regclass"
                    "::text in ('albaranes_fecha_idx', 'albaranes_proveedor_idx')") == (
        "albaranes_fecha_idx=CREATE INDEX albaranes_fecha_idx ON public.albaranes USING btree (fecha);"
        "albaranes_proveedor_idx=CREATE INDEX albaranes_proveedor_idx ON public.albaranes USING btree (id_proveedor)")


def test_rls_auto_enable_con_la_acl_productiva(pg29):
    assert pg29.sql("select prosecdef, prorettype::regtype, pg_get_userbyid(proowner) from pg_proc "
                    "where oid = 'public.rls_auto_enable()'::regprocedure") == "t|event_trigger|postgres"
    acl = pg29.sql("select string_agg(coalesce(r.rolname, 'PUBLIC') || ':' || a.privilege_type, ',' order by 1) "
                   "from pg_proc p cross join lateral aclexplode(p.proacl) a left join pg_roles r on r.oid = a.grantee "
                   "where p.oid = 'public.rls_auto_enable()'::regprocedure").split(",")
    # Produccion: PUBLIC, anon, authenticated, postgres y el rol del sistema (5 concesiones de EXECUTE).
    assert len(acl) == 5 and {"PUBLIC:EXECUTE", "anon:EXECUTE", "authenticated:EXECUTE",
                              "postgres:EXECUTE"} <= set(acl)


def test_usage_del_esquema_public(pg29):
    usage = pg29.sql("select string_agg(coalesce(r.rolname, 'PUBLIC'), ',') from pg_namespace n "
                     "cross join lateral aclexplode(n.nspacl) a left join pg_roles r on r.oid = a.grantee "
                     "where n.nspname = 'public' and a.privilege_type = 'USAGE'").split(",")
    assert {"PUBLIC", "anon", "authenticated", "postgres"} <= set(usage)


def test_la_29_la_crea_la_imitacion_con_admin(pg29):
    assert pg29.sql("select admin_option, inherit_option, set_option from pg_auth_members "
                    f"where roleid = 'cf_lectura'::regrole and member = '{pgl.ROL_SUPABASE}'::regrole") == "t|f|f"
    assert pg29.sql("select count(*) from pg_auth_members where member = 'cf_lectura'::regrole") == "0"
