"""Matching Alliance 2R exclusivamente READ ONLY, sin Farmatic."""
import os,sys,json
from pathlib import Path
from datetime import date
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tmp_pg_probe_deps')]
import psycopg2
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.runtime_supabase.conciliacion import (
 AlbaranDocumentalTrabajo,CandidatoAlbaranSupabase,buscar_candidato_albaran)

PDF=ROOT/'pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf'

def main():
 r=MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
 conn=psycopg2.connect(os.environ['CONTROLFARMACIAS_SUPABASE_DB_URL'],sslmode='require',connect_timeout=10,application_name='cf_2r_matching_readonly')
 conn.set_session(readonly=True,autocommit=False)
 try:
  with conn.cursor() as c:
   c.execute("select proveedor,id_proveedor,count(*) from public.albaranes where farmacia='PIO' and fecha between %s and %s and (proveedor ilike '%%alliance%%' or proveedor ilike '%%cencora%%') group by proveedor,id_proveedor order by 1,2",(date(2026,7,5),date(2026,8,15)))
   proveedores=c.fetchall()
   c.execute("select proveedor,id_proveedor,count(*) from public.albaranes where farmacia='PIO' and fecha between %s and %s group by proveedor,id_proveedor order by count(*) desc limit 20",(date(2026,7,5),date(2026,8,15)))
   principales=c.fetchall()
   c.execute("select p.codigo,p.nombre,p.farmatic_id_proveedor,p.nivel_confianza,a.alias from public.proveedores p left join public.proveedores_alias a on a.proveedor_id=p.id where p.codigo ilike '%%alliance%%' or p.nombre ilike '%%alliance%%' or p.nombre ilike '%%cencora%%' or a.alias ilike '%%alliance%%' or a.alias ilike '%%cencora%%' order by p.codigo,a.alias")
   autoridad_proveedor=c.fetchall()
   c.execute("select id_contador,farmacia,id_proveedor,proveedor,numero_albaran,fecha,importe_puc,importe_pvp,estado from public.albaranes where farmacia='PIO' and fecha between %s and %s",(date(2026,7,5),date(2026,8,15)))
   rows=[CandidatoAlbaranSupabase(*x) for x in c.fetchall()]
  out={}
  for f in r.facturas:
   matches=[]
   for a in f['albaranes']:
    d=AlbaranDocumentalTrabajo(str(a['orden']),a['numero_albaran']['valor'],date.fromisoformat(a['fecha']['valor']),Decimal(str(a['total']['valor'])),a['sentido']['valor'])
    m=buscar_candidato_albaran(d,rows,proveedor_literal='ALLIANCE HEALTHCARE ESPAÑA, S.A.')
    estado=('EXACTO' if m.estado=='MATCH_UNICO' and m.coincidencia_numero=='EXACTA' else
      'ECONOMICO_UNICO' if m.estado=='MATCH_UNICO' else 'AMBIGUO' if m.estado=='AMBIGUO' else 'NO_LOCALIZADO')
    matches.append({'orden':a['orden'],'numero':d.numero,'fecha':d.fecha.isoformat(),'importe':str(d.importe),'sentido':d.sentido,'estado':estado,'id_contador':m.candidato.id_contador if m.candidato else None,'importe_compatible':str(m.importe_compatible) if m.importe_compatible is not None else None,'candidatos_finales':m.candidatos_finales})
   out[f['segmento']['identidad']]={'paginas':f['segmento']['paginas'],'total':str(f['cabecera']['importe_total']['valor']),'albaranes':len(f['albaranes']),'resumen':{s:sum(x['estado']==s for x in matches) for s in ('EXACTO','ECONOMICO_UNICO','AMBIGUO','NO_LOCALIZADO')},'matches':matches}
  result={'destino':'SUPABASE_PRODUCTIVO_READ_ONLY','filas_operacionales_ventana':len(rows),'proveedores_alliance':proveedores,'proveedores_principales':principales,'autoridad_proveedor':autoridad_proveedor,'facturas':out}
  if os.environ.get('CF_2R_RESUMEN')=='1':
   result['facturas']={k:{x:v[x] for x in ('paginas','total','albaranes','resumen')} for k,v in out.items()}
  print(json.dumps(result,ensure_ascii=True))
 finally:conn.rollback();conn.close()
if __name__=='__main__':main()
