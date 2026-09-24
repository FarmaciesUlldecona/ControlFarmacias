"""Solo migracion 15 certificada, sin llamadas a claim/normalizacion/persistencia."""
import json, hashlib, re, os
from pathlib import Path
from datetime import datetime, timezone
import auditar
ROOT=auditar.ROOT
HERE=Path(__file__).resolve().parent
SHA='aa28b84225f62f0337e71b3b869b6c1e6030f4a1d8a56f9a5eb787d2de60f8a3'
NAMES={'cf_componentes_identidad_factura','cf_clave_economica_factura','cf_persistir_documento_multifactura'}

def check_post(pre,post,sql):
    for key in ['proyecto_sha256','conexion','flags','facturas','conteos','duplicadas','funciones','restriccion','rls','policies','locks','grants_tablas','indices','huella_documentos_legacy','sesiones_workers']:
        assert post[key]==pre[key], 'POSTFLIGHT_DIFERENCIA_'+key
    assert {k:v for k,v in post['huellas'].items() if k!='documentos_facturas'}=={k:v for k,v in pre['huellas'].items() if k!='documentos_facturas'},'DATOS_ECONOMICOS_CAMBIADOS'
    assert [f for f in post['funciones_publicas'] if f[0] not in NAMES]==pre['funciones_publicas'],'FUNCIONES_ANTERIORES_CAMBIADAS'
    assert post['columnas'][:-2]==pre['columnas']
    assert post['columnas'][-2:]==[['inventario_facturas','jsonb','NO',"'[]'::jsonb"],['estado_persistencia','text','NO',"'PENDIENTE'::text"]]
    added=[c for c in post['constraints'] if c not in pre['constraints']]
    assert all(c in post['constraints'] for c in pre['constraints']) and len(added)==1
    assert added[0][0:2]==['documentos_facturas','documentos_facturas_estado_persistencia_check']
    assert set(re.findall(r"'([A-Z_]+)'",added[0][2]))=={'PENDIENTE','PARCIAL','COMPLETA','REQUIERE_REVISION'}
    assert post['inventario_defaults']==[[0,0]]
    signatures={'cf_componentes_identidad_factura':('p jsonb','text[]',False,'i'),
      'cf_clave_economica_factura':('p jsonb','text',False,'i'),
      'cf_persistir_documento_multifactura':('p_documento_id uuid, p_worker_id text, p_idempotency_key text, p_resultado_hash text, p_resultado jsonb, p_segmentos_autorizados text[]','uuid',True,'v')}
    assert len(post['permisos_multifactura'])==3
    for row in post['permisos_multifactura']:
        assert tuple(row[1:5])==signatures[row[0]] and row[5:]==[['search_path=public'],False,False,True]
    for f in post['funciones_publicas']:
        if f[0] not in NAMES:continue
        assert f[2:4]==['postgres','{postgres=X/postgres,service_role=X/postgres}']
        local=re.search(r'create or replace function public\.'+f[0]+r'\(.*?as \$\$(.*?)\$\$;',sql,re.S).group(1).strip()
        remote=f[4].split('$function$')[1].strip()
        assert local==remote,'CUERPO_RPC_DISTINTO_'+f[0]

def main():
    raw=(ROOT/'sql/migrations/15_cf_multifactura.sql').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SHA,'MIGRACION_CAMBIADA_PARAR'
    sql=raw.decode('utf-8')
    assert (HERE/'rollback_15.sql').is_file(),'FALTA_ROLLBACK'
    pre=json.loads((HERE/'snapshot_pre.json').read_text(encoding='utf-8'))
    current=auditar.snapshot()
    assert current==pre,'PREFLIGHT_CAMBIADO_PARAR'
    assert not pre['permisos_multifactura'],'YA_EXISTE_15_NO_REAPLICAR'
    assert not any(c[0] in {'inventario_facturas','estado_persistencia'} for c in pre['columnas'])
    assert pre['flags']==[[False,False,False,['PIO']]] and pre['conteos']['facturas']==2
    assert pre['locks']==[[0,0]] and pre['sesiones_workers']==[]
    old=json.loads((ROOT/'pruebas/auditoria_2n/snapshot_post.json').read_text(encoding='utf-8'))
    for k in ['proyecto_sha256','flags','facturas','conteos','funciones','restriccion','rls','policies','huellas','grants_tablas']:
        assert pre[k]==old[k],'DIFERENCIA_ESTADO_CERTIFICADO_'+k
    print('PREFLIGHT=OK|SHA256='+SHA,flush=True)
    print('INICIO='+datetime.now(timezone.utc).isoformat(),flush=True)
    conn=auditar.audit.psycopg2.connect(os.environ['CONTROLFARMACIAS_SUPABASE_DB_URL'],sslmode='require',connect_timeout=10,application_name='cf_2p_migracion15')
    conn.autocommit=True
    try:
        with conn.cursor() as c:
            c.execute("set lock_timeout='5s'; set statement_timeout='60s';")
            c.execute(sql)
        print('MIGRACION_15_APLICADA=SI',flush=True)
    except auditar.audit.psycopg2.Error as e:
        print('ERROR_SQL='+str(e.pgcode),flush=True)
        raise
    finally:conn.close()
    print('FIN='+datetime.now(timezone.utc).isoformat(),flush=True)
    post=auditar.snapshot()
    print('POST_JSON='+json.dumps(post,ensure_ascii=True),flush=True)
    check_post(pre,post,sql)
    print('POSTFLIGHT=OK|SIN_EFECTOS_ECONOMICOS|ROLLBACK_NO_EJECUTADO',flush=True)

if __name__=='__main__':main()
