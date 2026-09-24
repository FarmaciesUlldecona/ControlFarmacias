"""Verificacion final 2P, sin ninguna operacion de escritura productiva."""
import json, os
from pathlib import Path
import auditar
from desplegar import check_post, SHA
import hashlib

def main():
    here=Path(__file__).resolve().parent
    pre=json.loads((here/'snapshot_pre.json').read_text(encoding='utf-8'))
    post=json.loads((here/'snapshot_post.json').read_text(encoding='utf-8'))
    final=auditar.snapshot()
    assert final==post,'CAMBIO_POSTERIOR_AL_POSTFLIGHT_PARAR'
    raw=(auditar.ROOT/'sql/migrations/15_cf_multifactura.sql').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SHA
    check_post(pre,final,raw.decode('utf-8'))
    conn=auditar.audit.psycopg2.connect(os.environ['CONTROLFARMACIAS_SUPABASE_DB_URL'],sslmode='require',connect_timeout=10,application_name='cf_2p_cierre_readonly')
    conn.set_session(readonly=True,autocommit=False)
    try:
        with conn.cursor() as c:
            c.execute("select n.resultado_json#>>'{metadata_tecnica,clasificacion_documental,tipo}' from public.facturas f join public.normalizacion_ejecuciones n on n.id=f.normalizacion_ejecucion_id where f.id='0a9808ec-5c6a-4bde-bb0c-4513ca0961c9'")
            clasificacion=c.fetchone()[0]
            assert clasificacion=='FACTURA_GASTO_SERVICIO','CLASIFICACION_COFARES_INESPERADA'
        print(json.dumps({'cierre':'READ_ONLY_OK','cofares_clasificacion':clasificacion,'facturas':final['conteos']['facturas'],'flags':final['flags'],'huellas_economicas_intactas':True,'claim_v2_intacto':True,'rollback_ejecutado':False}))
    finally:conn.rollback();conn.close()

if __name__=='__main__':main()
