"""Auditoria 2P estrictamente READ ONLY. No muestra credenciales."""
import sys, json, os, importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('audit_2n',ROOT/'pruebas/auditoria_2n/audit_readonly.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

def snapshot():
    out=audit.main(False)
    conn=audit.psycopg2.connect(os.environ['CONTROLFARMACIAS_SUPABASE_DB_URL'],sslmode='require',connect_timeout=10,application_name='cf_2p_readonly')
    conn.set_session(readonly=True,autocommit=False)
    try:
        with conn.cursor() as c:
            c.execute("set local statement_timeout='30s'")
            def rows(sql):
                c.execute(sql);return c.fetchall()
            out['columnas']=rows("select column_name,data_type,is_nullable,column_default from information_schema.columns where table_schema='public' and table_name='documentos_facturas' order by ordinal_position")
            out['constraints']=rows("select conrelid::regclass::text,conname,pg_get_constraintdef(oid) from pg_constraint where connamespace='public'::regnamespace order by 1,2")
            out['indices']=rows("select tablename,indexname,indexdef from pg_indexes where schemaname='public' order by 1,2")
            out['funciones_publicas']=rows("select p.proname,pg_get_function_identity_arguments(p.oid),pg_get_userbyid(p.proowner),p.proacl::text,pg_get_functiondef(p.oid) from pg_proc p where p.pronamespace='public'::regnamespace and p.proname like 'cf_%' order by 1,2")
            out['permisos_multifactura']=rows("select p.proname,pg_get_function_identity_arguments(p.oid),pg_get_function_result(p.oid),p.prosecdef,p.provolatile,p.proconfig,has_function_privilege('anon',p.oid,'EXECUTE'),has_function_privilege('authenticated',p.oid,'EXECUTE'),has_function_privilege('service_role',p.oid,'EXECUTE') from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in ('cf_componentes_identidad_factura','cf_clave_economica_factura','cf_persistir_documento_multifactura') order by 1,2")
            out['huella_documentos_legacy']=rows("select count(*),md5(coalesce(string_agg((to_jsonb(t)-'inventario_facturas'-'estado_persistencia')::text,E'\\n' order by id),'')) from public.documentos_facturas t")
            out['sesiones_workers']=rows("select application_name,state,count(*) from pg_stat_activity where pid<>pg_backend_pid() and (application_name ilike '%worker%' or application_name ilike '%runtime%') group by 1,2 order by 1,2")
            if any(x[0]=='inventario_facturas' for x in out['columnas']):
                out['inventario_defaults']=rows("select count(*) filter(where inventario_facturas<>'[]'::jsonb),count(*) filter(where estado_persistencia<>'PENDIENTE') from public.documentos_facturas")
        return json.loads(json.dumps(out,default=str))
    finally:conn.rollback();conn.close()

if __name__=='__main__':
    print(json.dumps(snapshot(),ensure_ascii=True))
