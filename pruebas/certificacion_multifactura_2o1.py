"""Certificacion exclusivamente Docker local: no lee URLs ni conecta a Supabase."""
import sys, json, uuid, time, runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pruebas import certificacion_2f1 as pg
from src.facturas.runtime_supabase.multifactura import preparar_documento, clave_economica
fixture=runpy.run_path(str(ROOT/'tests/facturas/runtime_supabase/test_multifactura.py'))

def lit(value):return "'"+str(value).replace("'","''")+"'"
def js(value):return lit(json.dumps(value))+"::jsonb"
def q(s):return pg.sql('cert_2o1',s)
def new_doc():
    tag=uuid.uuid4().hex
    return q(f"insert into public.documentos_facturas(farmacia,archivo_nombre,archivo_ruta,archivo_hash) values ('PIO','SINTETICO','local/{tag}','{tag}') returning id;")
def claim_doc(d):
    q(f"select id from public.cf_solicitar_reprocesado('{d}','LOCAL');")
    assert q("select id from public.cf_reclamar_documento_normalizacion('local',300);")==d
def persist(d,doc,selected,key=None,claim=True,fail=None):
    payload=preparar_documento(doc,selected)['resultado_json']
    if claim:claim_doc(d)
    key=key or uuid.uuid4().hex
    sql=f"set role service_role; select public.cf_persistir_documento_multifactura('{d}','local','{key}','local-hash',{js(payload)},array[{','.join(lit(x) for x in selected)}]::text[]);"
    result=pg.sql('cert_2o1',sql,fail=fail)
    return result,key
def state(d):
    return json.loads(q(f"select jsonb_build_object('estado',estado_persistencia,'lectura',estado_lectura,'n',cantidad_documentos_detectados,'inventario',inventario_facturas) from public.documentos_facturas where id='{d}';"))
def fp():
    tables=['documentos_facturas','facturas','normalizacion_ejecuciones','facturas_impuestos','facturas_vencimientos','facturas_movimientos','facturas_albaranes_extraidos','conciliaciones','conciliacion_detalles','historial_facturas']
    return {t:q(f"select md5(coalesce(string_agg(to_jsonb(t)::text,'' order by id),'')) from public.{t} t") for t in tables}
def security():
    return q("select jsonb_build_object('policies',(select jsonb_agg(to_jsonb(p) order by tablename,policyname) from pg_policies p where schemaname='public'),'rls',(select jsonb_agg(jsonb_build_array(relname,relrowsecurity) order by relname) from pg_class where relnamespace='public'::regnamespace and relkind='r'),'grants',(select jsonb_agg(to_jsonb(g) order by table_name,grantee,privilege_type) from information_schema.role_table_grants g where table_schema='public'));")

def check_cycle(number):
    pg.docker('exec',pg.CONTAINER,'createdb','-U','postgres','cert_2o1')
    pg.file('cert_2o1',pg.STG/'00_baseline_controlfarmacias.sql')
    for name in ['06b_cf_integridad_albaranes.sql','07_cf_proveedores_config.sql','08_cf_core_facturas.sql','08b_cf_estado_lectura_compatibilidad.sql','09_cf_normalizacion_runtime.sql','10_cf_movimientos_incidencias_historial.sql','11_cf_conciliacion.sql','12_cf_views_rls_rpc.sql']:
        pg.file('cert_2o1',pg.MIG/name)
    pg.file('cert_2o1',pg.STG/'01_seed_controlfarmacias.sql');pg.file('cert_2o1',pg.STG/'06_test_backfill_pio.sql')
    pg.file('cert_2o1',pg.MIG/'14_cf_claim_conciliacion_v2.sql')
    security_before=security()
    pg.file('cert_2o1',pg.MIG/'15_cf_multifactura.sql')
    assert security()==security_before
    signature='public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[])'
    assert q(f"select has_function_privilege('anon','{signature}','EXECUTE'),has_function_privilege('authenticated','{signature}','EXECUTE'),has_function_privilege('service_role','{signature}','EXECUTE');")=='f|f|t'
    pg.sql('cert_2o1',f"set role anon; select {signature.split('(')[0]}(null,null,null,null,null,null);",fail='42501')
    assert q('show server_version;').startswith('17.')
    print(f'CICLO_{number}_MIGRACION_15_COMPILA_RLS_POLICIES_GRANTS_OK',flush=True)
    for n in [1,3,5]:
        d=new_doc();doc=fixture['documento'](n,f'full-{n}')
        persist(d,doc,[f's{i+1}' for i in range(n)])
        assert state(d)['estado']=='COMPLETA'
        assert q(f"select count(*) from public.facturas where documento_id='{d}';")==str(n)
        for f in doc['facturas']:
            assert q(f"select public.cf_clave_economica_factura({js(f)});")==clave_economica(f)
    print('N_1_3_5_Y_EQUIVALENCIA_IDENTIDAD_OK',flush=True)
    d=new_doc();doc=fixture['documento'](4,'partial')
    execution,key=persist(d,doc,['s2'])
    assert state(d)['estado']=='PARCIAL' and state(d)['lectura']=='REVISION' and state(d)['n']==4
    assert [f['estado'] for f in state(d)['inventario']]==['PENDIENTES','PERSISTIDAS','PENDIENTES','PENDIENTES']
    before=fp();assert persist(d,doc,['s2'],key=key,claim=False)[0]==execution;assert fp()==before
    persist(d,doc,['s3'])
    assert q(f"select count(*) from public.facturas where documento_id='{d}';")=='2'
    b_before=q(f"select to_jsonb(f) from public.facturas f where documento_id='{d}' and numero_factura='partial-2';")
    persist(d,doc,['s2','s3'])
    assert b_before==q(f"select to_jsonb(f) from public.facturas f where documento_id='{d}' and numero_factura='partial-2';")
    assert q(f"select count(*) from public.facturas where documento_id='{d}';")=='2'
    print('B_RELECTURA_C_SIN_DUPLICAR_NI_MODIFICAR_B_OK',flush=True)
    di=new_doc();inc=fixture['documento'](3,'incomplete');inc['facturas'][1]['factura_completa_demostrada']=False
    persist(di,inc,['s1','s2','s3'])
    assert [x['estado'] for x in state(di)['inventario']]==['PERSISTIDAS','REQUIERE_REVISION','PERSISTIDAS']
    assert q(f"select count(*) from public.facturas where documento_id='{di}';")=='2'
    dd=new_doc();dup=fixture['documento'](3,'dup')
    original=fixture['documento'](1,'full-1')['facturas'][0]
    dup['facturas'][0]=original
    persist(dd,dup,['s1','s2','s3'])
    assert [x['estado'] for x in state(dd)['inventario']]==['DUPLICADAS','PERSISTIDAS','PERSISTIDAS']
    dv=new_doc();version=fixture['documento'](1,'full-1');version['facturas'][0]['totales']['total']=fixture['campo']('122')
    persist(dv,version,['s1']);assert state(dv)['inventario'][0]['estado']=='REQUIERE_REVISION'
    ds=new_doc();sibling=fixture['documento'](2,'conflict');sibling['facturas'][1]['numero_factura']=fixture['campo']('conflict-1',2);sibling['facturas'][1]['totales']['total']=fixture['campo']('130',2)
    persist(ds,sibling,['s1','s2']);assert all(x['estado']=='REQUIERE_REVISION' for x in state(ds)['inventario'])
    print('INCOMPLETA_DUPLICADAS_VERSIONES_HERMANAS_OK',flush=True)
    # Una copia anterior NO seleccionada no impide persistir la segunda copia.
    copies=new_doc();copied=fixture['documento'](2,'copies')
    copied['facturas'][1]['numero_factura']=fixture['campo']('copies-1',2)
    persist(copies,copied,[])
    assert [x['estado'] for x in state(copies)['inventario']]==['PENDIENTES','PENDIENTES']
    persist(copies,copied,['s2'])
    assert q(f"select count(*) from public.facturas where documento_id='{copies}';")=='1'
    assert state(copies)['estado']=='COMPLETA'
    assert all(x['factura_id'] for x in state(copies)['inventario'])
    print('COPIAS_INTERNAS_SELECCION_SEGUNDA_SIN_PERDIDA_OK',flush=True)
    bad=new_doc();broken=fixture['documento'](3,'technical')
    broken['facturas'][1]['vencimientos']=[{'orden':None,'importe':fixture['campo']('121',2)}]
    claim_doc(bad);before=fp();persist(bad,broken,['s1','s2','s3'],claim=False,fail='23502');assert fp()==before
    print('ERROR_TECNICO_ROLLBACK_TOTAL_OK',flush=True)
    # Solo las hermanas pendientes aptas B/D se habilitan mediante solicitudes sinteticas.
    dc=new_doc();claims=fixture['documento'](4,'claims')
    claims['facturas'][2]['albaranes']=[]
    persist(dc,claims,['s1','s2','s3','s4'])
    ids=json.loads(q(f"select json_object_agg(numero_factura,id) from public.facturas where documento_id='{dc}';"))
    q(f"update public.facturas set estado_conciliacion_cf='CONCILIADA' where id='{ids['claims-1']}';")
    q(f"update public.facturas set conciliacion_reintento_solicitado_at=now() where documento_id='{dc}';")
    a=q("select id from public.cf_reclamar_factura_conciliacion('local-claim',300);")
    b=q("select id from public.cf_reclamar_factura_conciliacion('local-claim2',300);")
    assert {a,b}=={ids['claims-2'],ids['claims-4']}
    assert q("select count(*) from public.cf_reclamar_factura_conciliacion('local-empty',300);")=='0'
    from src.facturas.runtime_supabase.conciliacion import conciliar_importes
    assert conciliar_importes('121',()).resultado!='CONCILIADA'
    for invoice in (a,b):
        q(f"insert into public.conciliaciones(factura_id,intento,disparador,estado,importe_factura,importe_explicado,diferencia,resultado) values ('{invoice}',1,'TEST','COMPLETADA',121,0,121,'SIN_CANDIDATOS');")
    assert q(f"select count(distinct factura_id) from public.conciliaciones where factura_id in ('{a}','{b}') and es_actual;")=='2'
    pg.sql('cert_2o1',f"insert into public.conciliaciones(factura_id,intento,disparador) values ('{a}',2,'TEST');",fail='23505')
    print('CLAIM_INDIVIDUAL_Y_CONCILIACIONES_INDEPENDIENTES_OK',flush=True)
    before=fp();pg.file('cert_2o1',pg.MIG/'15_cf_multifactura.sql');assert fp()==before;assert security()==security_before
    assert 'ESTADO_LECTURA_V1_COMPATIBLE' in pg.file('cert_2o1',pg.PRE/'postflight_supabase_v1.sql')
    assert q('select normalizacion_automatica,conciliacion_automatica,luna_habilitada from public.cf_configuracion;')=='f|f|f'
    print(f'CICLO_{number}_IDEMPOTENCIA_POSTFLIGHT_OK',flush=True)

def main():
    print('DESTINO_CERTIFICACION=LOCAL',flush=True)
    for number in (1,2):
        suffix=uuid.uuid4().hex[:12];name='cf-2o1-'+suffix;volume=name+'-data'
        pg.CONTAINER=name
        pg.docker('volume','create','--label','controlfarmacias.certificacion=2o1',volume)
        try:
            pg.docker('run','-d','--name',name,'--label','controlfarmacias.certificacion=2o1','--network','none','--mount',f'type=volume,source={volume},target=/var/lib/postgresql/data','-e','POSTGRES_PASSWORD=local-only','postgres:17-alpine')
            for attempt in range(30):
                if pg.docker('exec',name,'pg_isready','-U','postgres',check=False).returncode==0:break
                time.sleep(.5)
            info=json.loads(pg.docker('inspect',name).stdout)[0]
            assert info['HostConfig']['NetworkMode']=='none' and not info['HostConfig']['PortBindings']
            check_cycle(number)
        finally:
            info=pg.docker('inspect',name,check=False)
            if info.returncode==0:
                assert json.loads(info.stdout)[0]['Config']['Labels']['controlfarmacias.certificacion']=='2o1'
                pg.docker('rm','-f',name)
            vi=json.loads(pg.docker('volume','inspect',volume).stdout)[0]
            assert vi['Labels']['controlfarmacias.certificacion']=='2o1'
            pg.docker('volume','rm',volume)
            print(f'CICLO_{number}_CONTENEDOR_VOLUMEN_ELIMINADOS',flush=True)
if __name__=='__main__':main()
