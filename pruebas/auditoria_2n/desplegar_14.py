"""Despliegue unico 2N; solo migracion 14, con preflight read-only y sin claim."""
import sys, json, hashlib, re, os
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[2]
import audit_readonly as audit

def canonical(text): return re.sub(r'\s+',' ',text.strip()).lower()
def body(text): return text.split('declare',1)[1].split('$$',1)[0].split('$function$',1)[0].strip()

def main():
    path=ROOT/'sql/migrations/14_cf_claim_conciliacion_v2.sql'
    raw=path.read_bytes(); sql=raw.decode('utf-8')
    sha=hashlib.sha256(raw).hexdigest()
    assert sha=='7f13eeac1e395e30c7707df5f4b7708f8ebcaf d4763121a3dfd5adc429d2ab15'.replace(' ',''), 'MIGRACION_CAMBIADA'
    assert 'select f.*\n      into v_factura' in sql
    assert 'select n.resultado_json\n      into v_resultado' in sql
    assert 'for update of f skip locked' in sql and "e.estado = 'APTA'" in sql
    pre=json.loads((Path(__file__).parent/'snapshot_pre.json').read_text(encoding='utf-8'))
    now=audit.main(False)
    assert now==pre, 'PREFLIGHT_CAMBIADO_PARAR'
    assert pre['flags']==[[False,False,False,['PIO']]]
    assert pre['conteos']['facturas']==2 and pre['duplicadas']==[[0]] and pre['locks']==[[0,0]]
    assert len(pre['funciones'])==1 and pre['funciones'][0][0]=='cf_reclamar_factura_conciliacion'
    old=(ROOT/'sql/migrations/11_cf_conciliacion.sql').read_text(encoding='utf-8').split('create or replace function public.cf_reclamar_factura_conciliacion',1)[1]
    assert canonical(body(old))==canonical(body(pre['funciones'][0][4])), 'CLAIM_PREVIO_INESPERADO'
    assert all(row[1] for row in pre['rls'])
    expected={row[0] for row in pre['rls']} - {'albaranes'}
    assert {p[0] for p in pre['policies']}==expected and len(pre['policies'])==len(expected)
    assert all(p[1]==p[0]+'_authenticated_select' and p[2]==['authenticated'] and p[3]=='SELECT' and p[5] is None for p in pre['policies'])
    for table in expected:
        grants=[(g[1],g[2]) for g in pre['grants_tablas'] if g[0]==table]
        assert [p for role,p in grants if role=='authenticated']==['SELECT']
        assert not any(role=='anon' for role,p in grants)
        assert {'SELECT','INSERT','UPDATE','DELETE'}.issubset({p for role,p in grants if role=='service_role'})
    assert pre['funciones'][0][2:4]==['postgres','{postgres=X/postgres,service_role=X/postgres}']
    assert {f[0] for f in pre['facturas']}=={'0a9808ec-5c6a-4bde-bb0c-4513ca0961c9','14f7808e-cb2b-41fd-94fb-6eb82703de21'}
    assert all(f[4:6]==['NORMALIZADA','CONCILIADA'] and f[7]=='PIO' for f in pre['facturas'])
    print('PREFLIGHT=OK|DESTINO_PRODUCTIVO=SI|SHA256='+sha,flush=True)
    print('INICIO='+datetime.now(timezone.utc).isoformat(),flush=True)
    conn=audit.psycopg2.connect(os.environ['CONTROLFARMACIAS_SUPABASE_DB_URL'],sslmode='require',connect_timeout=10,application_name='cf_2n_migracion14')
    conn.autocommit=True
    try:
        with conn.cursor() as c:
            c.execute("set lock_timeout='5s'; set statement_timeout='60s';")
            c.execute(sql)
        print('MIGRACION_14_APLICADA=SI',flush=True)
    except audit.psycopg2.Error as e:
        print('ERROR_SQL='+str(e.pgcode)+':'+str(e.diag.message_primary),flush=True)
        with conn.cursor() as c: c.execute('ROLLBACK')
        raise
    finally: conn.close()
    print('FIN='+datetime.now(timezone.utc).isoformat(),flush=True)
    post=audit.main(False)
    for key in ['proyecto_sha256','conexion','flags','facturas','conteos','duplicadas','rls','policies','locks','huellas','grants_tablas']:
        assert post[key]==pre[key], 'POSTFLIGHT_DIFERENCIA_'+key
    assert len(post['funciones'])==2
    for f in post['funciones']:
        assert f[2:4]==['postgres','{postgres=X/postgres,service_role=X/postgres}']
        source=sql.split('create or replace function public.'+f[0],1)[1]
        assert canonical(body(source))==canonical(body(f[4])), 'FUNCION_DIFERENTE'
    c=audit.psycopg2.connect(os.environ['CONTROLFARMACIAS_SUPABASE_DB_URL'],sslmode='require',connect_timeout=10,application_name='cf_2n_evaluacion_readonly')
    c.set_session(readonly=True,autocommit=False)
    try:
        with c.cursor() as cur:
            cur.execute('select f.id,e.estado,e.razon from public.facturas f cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e order by f.id')
            post['evaluacion_readonly']=cur.fetchall()
    finally: c.rollback(); c.close()
    assert post['evaluacion_readonly']==[('0a9808ec-5c6a-4bde-bb0c-4513ca0961c9','APTA','APTA_GASTO_SERVICIO'),('14f7808e-cb2b-41fd-94fb-6eb82703de21','APTA','APTA_MERCANCIA')]
    assert audit.main(False)['huellas']==pre['huellas']
    print('POSTFLIGHT=OK|HUELLAS_IDENTICAS|EVALUACION_READONLY=OK',flush=True)
    print('POST_JSON='+json.dumps(post,ensure_ascii=True),flush=True)
if __name__=='__main__': main()
