"""Hito 2R controlado. Fases explicitas; nunca importa Farmatic ni usa API."""
import os,sys,json,hashlib
from pathlib import Path
from decimal import Decimal
from datetime import date,datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tmp_pg_probe_deps')]
import psycopg2
from psycopg2.extras import Json
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.runtime_supabase.multifactura import adaptar_resultado_local,preparar_documento
from src.facturas.runtime_supabase.conciliacion import dinero

PDF=ROOT/'pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf'
PDF_SHA='7b806565a4f09e182c5ec9d75b40b959fd39c4af86da77b7a8cb745c6e1192b2'
DOCUMENTO='ffee3c1c-ebcc-4287-99b2-79ccbae45f22'
NUMEROS=('08009278','08009277','08009279')
WORKER_N='manual-hito-2r-normalizacion'
WORKER_C='manual-hito-2r-conciliacion'
TABLES=('facturas','normalizacion_ejecuciones','conciliaciones','conciliacion_detalles','facturas_movimientos','facturas_impuestos','facturas_vencimientos','facturas_incidencias','facturas_albaranes_extraidos','historial_facturas')

def connect(readonly=False):
 c=psycopg2.connect(os.environ['CONTROLFARMACIAS_SUPABASE_DB_URL'],sslmode='require',connect_timeout=10,application_name='cf_2r_'+('readonly' if readonly else 'controlado'))
 c.set_session(readonly=readonly,autocommit=False);return c

def extract():
 assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA
 local=MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
 doc=adaptar_resultado_local(local)
 assert doc['documento_completo_demostrado'] is True
 assert [f['numero_factura']['valor'] for f in doc['facturas']]==list(NUMEROS)
 assert [len(f['albaranes']) for f in doc['facturas']]==[109,165,5]
 assert all(f['factura_completa_demostrada'] and f['identidad_economica_clave'] for f in doc['facturas'])
 assert [len(f['movimientos_comerciales']) for f in doc['facturas']]==[0,2,0]
 return local,doc

def snapshot():
 c=connect(True)
 try:
  with c.cursor() as q:
   def one(sql,args=()):q.execute(sql,args);return q.fetchone()
   flags=one('select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion where id')
   counts={t:one(f'select count(*) from public.{t}')[0] for t in TABLES}
   facturas=one("select jsonb_agg(jsonb_build_array(id,numero_factura,importe_total,estado_normalizacion,estado_conciliacion_cf,estado_revision) order by numero_factura) from public.facturas") [0]
   doc=one("select id,archivo_hash,estado_lectura,estado_persistencia,inventario_facturas,cantidad_documentos_detectados from public.documentos_facturas where id=%s",(DOCUMENTO,))
   functions=one("select count(*) from pg_proc where pronamespace='public'::regnamespace and proname in ('cf_evaluar_elegibilidad_conciliacion','cf_reclamar_factura_conciliacion','cf_persistir_documento_multifactura')")[0]
   locks=one("select (select count(*) from public.documentos_facturas where bloqueado_hasta>now()),(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now())")
   requested=one("select count(*) from public.documentos_facturas where reprocesar_solicitado_at is not null") [0]
   return {'at':datetime.now(timezone.utc).isoformat(),'flags':list(flags),'counts':counts,'facturas':facturas,'documento':list(doc) if doc else None,'funciones_14_15':functions,'locks':list(locks),'reprocesos_solicitados':requested}
 finally:c.rollback();c.close()

def preflight():
 s=snapshot()
 assert s['flags']==[False,False,False,['PIO']]
 assert s['counts']['facturas']==2 and s['counts']['normalizacion_ejecuciones']==3 and s['counts']['conciliaciones']==3
 assert s['funciones_14_15']==3 and s['locks']==[0,0] and s['reprocesos_solicitados']==0
 assert s['documento'][1]==PDF_SHA and s['documento'][2]=='PENDIENTE'
 assert s['documento'][3]=='PENDIENTE' and s['documento'][4]==[]
 assert {(f[1],float(f[2]),f[3],f[4]) for f in s['facturas']}=={
  ('5011640669',448.0,'NORMALIZADA','CONCILIADA'),('5460017198',177.74,'NORMALIZADA','CONCILIADA')}
 print(json.dumps(s,default=str,ensure_ascii=True));return s

def persistir():
 _,doc=extract();payload=preparar_documento(doc,['paginas-1-4','paginas-5-9','paginas-10-11'])
 encoded=json.dumps(payload['resultado_json'],sort_keys=True,separators=(',',':'),ensure_ascii=False)
 idem='hito-2r-'+PDF_SHA[:32];result_hash=hashlib.sha256(encoded.encode()).hexdigest()
 c=connect()
 try:
  with c.cursor() as q:
   q.execute("select (public.cf_solicitar_reprocesado(%s,%s)).id::text",(DOCUMENTO,'PIO-HITO-2R'));assert q.fetchone()[0]==DOCUMENTO
   q.execute("select id::text from public.cf_reclamar_documento_normalizacion(%s,%s)",(WORKER_N,300));assert q.fetchone()[0]==DOCUMENTO
   q.execute("select public.cf_persistir_documento_multifactura(%s,%s,%s,%s,%s,%s)::text",(DOCUMENTO,WORKER_N,idem,result_hash,Json(payload['resultado_json']),payload['segmentos_autorizados']))
   execution=q.fetchone()[0]
   q.execute("select count(*),array_agg(numero_factura order by numero_factura) from public.facturas where documento_id=%s",(DOCUMENTO,));assert q.fetchone()==(3,['08009277','08009278','08009279'])
   q.execute("select estado_lectura,estado_persistencia,cantidad_documentos_detectados from public.documentos_facturas where id=%s",(DOCUMENTO,));assert q.fetchone()==('NORMALIZADA','COMPLETA',3)
  c.commit();print(json.dumps({'persistencia':'OK','ejecucion_id':execution,'idempotency_key':idem}))
 except Exception:c.rollback();raise
 finally:c.close()

def elegibilidad():
 c=connect(True)
 try:
  with c.cursor() as q:
   q.execute("select f.id::text,f.numero_factura,e.estado,e.razon,(select count(*) from public.facturas_albaranes_extraidos a where a.factura_id=f.id),(select count(*) from public.facturas_movimientos m where m.factura_id=f.id) from public.facturas f cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e where f.documento_id=%s order by f.numero_factura",(DOCUMENTO,))
   rows=q.fetchall();assert len(rows)==3 and all(x[2]=='APTA' for x in rows)
   print(json.dumps(rows,default=str));return rows
 finally:c.rollback();c.close()

def conciliar():
 eligible=elegibilidad();ids={r[1]:r[0] for r in eligible}
 c=connect()
 try:
  with c.cursor() as q:
   for number in NUMEROS:
    q.execute("select (public.cf_solicitar_reintento_conciliacion(%s,%s)).id::text",(ids[number],'PIO-HITO-2R'));assert q.fetchone()[0]==ids[number]
   claimed=[]
   for _ in NUMEROS:
    q.execute("select id::text,numero_factura from public.cf_reclamar_factura_conciliacion(%s,%s)",(WORKER_C,300));row=q.fetchone();assert row and row[1] in NUMEROS;claimed.append(row)
   assert {x[0] for x in claimed}==set(ids.values())
  c.commit()
 finally:c.close()
 results=[]
 for invoice_id,number in claimed:
  c=connect()
  try:
   with c.cursor() as q:
    q.execute("select importe_total from public.facturas where id=%s and conciliacion_bloqueado_por=%s for update",(invoice_id,WORKER_C));total=dinero(q.fetchone()[0])
    q.execute("select id::text,numero_albaran,fecha_albaran,importe_total,tipo_movimiento from public.facturas_albaranes_extraidos where factura_id=%s order by orden",(invoice_id,));albs=q.fetchall()
    q.execute("select id::text,descripcion_literal,importe,sentido from public.facturas_movimientos where factura_id=%s order by orden",(invoice_id,));movs=q.fetchall()
    explained=sum((abs(dinero(x[2])) if x[3]=='CARGO' else -abs(dinero(x[2])) for x in movs),Decimal('0.0000'))
    diff=dinero(total-explained);result='CONCILIADA' if abs(diff)<=Decimal('.0500') else 'DIFERENCIA'
    assert result=='DIFERENCIA'
    q.execute("insert into public.conciliaciones(factura_id,intento,disparador,estado,es_actual,tolerancia,importe_factura,importe_explicado,diferencia,resultado,estrategia,provenance,worker_id,finalizado_at) values (%s,1,'MANUAL','COMPLETADA',true,.05,%s,%s,%s,%s,'MATCHING_CERTIFICADO_V2',%s,%s,now()) returning id::text",(invoice_id,total,explained,diff,result,Json({'fuente':'SUPABASE_ALBARANES','proveedor_documental':'ALLIANCE HEALTHCARE ESPAÑA, S.A.','equivalencias_inventadas':False,'resultado_matching':'NO_LOCALIZADO'}),WORKER_C));rec=q.fetchone()[0]
    order=0
    for aid,num,fecha,amount,sentido in albs:
     order+=1;q.execute("insert into public.conciliacion_detalles(conciliacion_id,orden,factura_albaran_extraido_id,numero_albaran_documental,coincidencia_numero_literal,tipo_relacion,importe_documental,importe_aplicado,diferencia,estado,provenance) values (%s,%s,%s,%s,false,'SIN_COINCIDENCIA',%s,0,%s,'DIFERENCIA',%s)",(rec,order,aid,num,amount,amount,Json({'estado_matching':'NO_LOCALIZADO','fecha_documental':fecha.isoformat() if fecha else None,'farmatic_consultado':False})))
    for mid,desc,amount,sentido in movs:
     applied=abs(dinero(amount)) if sentido=='CARGO' else -abs(dinero(amount));order+=1
     q.execute("insert into public.conciliacion_detalles(conciliacion_id,orden,factura_movimiento_id,coincidencia_numero_literal,tipo_relacion,importe_documental,importe_aplicado,diferencia,estado,provenance) values (%s,%s,%s,false,'MOVIMIENTO_NO_FARMATIC',%s,%s,0,'DIFERENCIA',%s)",(rec,order,mid,amount,applied,Json({'fuente':'MOVIMIENTO_DOCUMENTAL','concepto_literal':desc,'sentido':sentido,'farmatic_consultado':False})))
    q.execute("update public.facturas set estado_conciliacion_cf='PENDIENTE_CONCILIAR',diferencia_albaranes=%s,conciliacion_intentos=1,conciliacion_bloqueado_hasta=null,conciliacion_bloqueado_por=null,conciliacion_reintento_solicitado_at=null,updated_at=now() where id=%s",(diff,invoice_id))
   c.commit();results.append({'numero':number,'factura_id':invoice_id,'conciliacion_id':rec,'albaranes_documentales':len(albs),'albaranes_operacionales':0,'movimientos_independientes':len(movs),'importe_factura':str(total),'importe_explicado':str(explained),'diferencia':str(diff),'resultado':result})
  except Exception:c.rollback();raise
  finally:c.close()
 print(json.dumps({'claimed':claimed,'resultados':sorted(results,key=lambda x:x['numero'])},ensure_ascii=True))

if __name__=='__main__':
 if len(sys.argv)!=2 or sys.argv[1] not in {'preflight','persistir','elegibilidad','conciliar','snapshot'}:raise SystemExit('fase requerida')
 result=globals()[sys.argv[1]]()
 if sys.argv[1]=='snapshot':print(json.dumps(result,default=str,ensure_ascii=True))
