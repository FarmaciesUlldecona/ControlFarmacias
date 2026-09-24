import sys, os, json, hashlib
from pathlib import Path
from urllib.parse import urlparse, unquote
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp_pg_probe_deps'))
from dotenv import dotenv_values
import psycopg2

def main(emit=True):
    dsn=os.environ['CONTROLFARMACIAS_SUPABASE_DB_URL']
    app=urlparse(dotenv_values(ROOT/'.env').get('SUPABASE_URL',''))
    db=urlparse(dsn); ref=(app.hostname or '').split('.')[0]
    assert ref and ((db.hostname==f'db.{ref}.supabase.co') or ((db.hostname or '').endswith('.pooler.supabase.com') and unquote(db.username or '').endswith('.'+ref))), 'DESTINO_NO_DEMOSTRADO'
    conn=psycopg2.connect(dsn,sslmode='require',connect_timeout=10,application_name='cf_2n_readonly')
    conn.set_session(readonly=True,autocommit=False)
    out={'proyecto_sha256':hashlib.sha256(ref.encode()).hexdigest(),'destino':'SUPABASE_PRODUCTIVO_CONTROLFARMACIAS_PIO'}
    try:
        with conn.cursor() as c:
            def rows(sql):
                c.execute(sql); return c.fetchall()
            out['conexion']=rows('select current_database(),current_user,current_schema(),current_setting(\'transaction_read_only\')')
            out['flags']=rows('select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion')
            out['facturas']=rows("select f.id,f.proveedor_literal,f.proveedor_nombre,f.importe_total,f.estado_normalizacion,f.estado_conciliacion_cf,f.datos_extraidos->>'naturaleza_principal',f.farmacia,c.id,c.diferencia,(select count(*) from public.facturas_albaranes_extraidos a where a.factura_id=f.id) from public.facturas f left join public.conciliaciones c on c.factura_id=f.id and c.es_actual order by f.id")
            out['conteos']={t:rows(f'select count(*) from public.{t}')[0][0] for t in ['facturas','normalizacion_ejecuciones','conciliaciones','conciliacion_detalles','facturas_movimientos','facturas_impuestos','facturas_vencimientos','facturas_incidencias','historial_facturas']}
            out['duplicadas']=rows('select count(*) from (select factura_id from public.conciliaciones where es_actual group by factura_id having count(*)>1) x')
            out['funciones']=rows("select p.proname,pg_get_function_identity_arguments(p.oid),pg_get_userbyid(p.proowner),p.proacl::text,pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in ('cf_reclamar_factura_conciliacion','cf_evaluar_elegibilidad_conciliacion') order by p.proname")
            out['restriccion']=rows("select conname,pg_get_constraintdef(oid) from pg_constraint where conrelid='public.conciliacion_detalles'::regclass and conname='conciliacion_detalles_origen_check'")
            out['rls']=rows("select relname,relrowsecurity from pg_class where relnamespace='public'::regnamespace and relkind='r' order by relname")
            out['policies']=rows("select tablename,policyname,roles,cmd,qual,with_check from pg_policies where schemaname='public' order by tablename,policyname")
            out['locks']=rows("select (select count(*) from public.facturas where conciliacion_bloqueado_hasta>now()),(select count(*) from public.documentos_facturas where bloqueado_hasta>now())")
            out['huellas']={t:rows(f"select count(*),md5(coalesce(string_agg(to_jsonb(t)::text,E'\\n' order by id),'')) from public.{t} t") for t in list(out['conteos'])+['documentos_facturas','facturas_albaranes_extraidos','facturas_ajustes','cf_configuracion']}
            out['grants_tablas']=rows("select table_name,grantee,privilege_type from information_schema.role_table_grants where table_schema='public' and grantee in ('anon','authenticated','service_role') order by table_name,grantee,privilege_type")
        if emit: print(json.dumps(out,default=str,ensure_ascii=True))
        return json.loads(json.dumps(out,default=str))
    finally:
        conn.rollback(); conn.close()
if __name__=='__main__': main()
