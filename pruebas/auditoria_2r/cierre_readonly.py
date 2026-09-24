"""Cierre 2R exclusivamente READ ONLY."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp_pg_probe_deps'))
import psycopg2
DOC='ffee3c1c-ebcc-4287-99b2-79ccbae45f22'
NUMS=('08009277','08009278','08009279')

def main():
 c=psycopg2.connect(os.environ['CONTROLFARMACIAS_SUPABASE_DB_URL'],sslmode='require',connect_timeout=10,application_name='cf_2r_cierre_readonly');c.set_session(readonly=True)
 try:
  with c.cursor() as q:
   def rows(sql,args=()):q.execute(sql,args);return q.fetchall()
   flags=rows('select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion where id')
   base=rows("select numero_factura,importe_total,estado_normalizacion,estado_conciliacion_cf,estado_revision from public.facturas where documento_id<>%s order by numero_factura",(DOC,))
   alliance=rows("select f.id::text,f.numero_factura,f.pagina_inicio,f.pagina_fin,f.importe_total,f.estado_normalizacion,f.estado_conciliacion_cf,f.estado_revision,(select count(*) from public.facturas_albaranes_extraidos a where a.factura_id=f.id),(select count(*) from public.facturas_movimientos m where m.factura_id=f.id),(select count(*) from public.facturas_incidencias i where i.factura_id=f.id and i.bloqueante) from public.facturas f where f.documento_id=%s order by f.numero_factura",(DOC,))
   eligibility=rows("select f.numero_factura,e.estado,e.razon from public.facturas f cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id)e where f.documento_id=%s order by f.numero_factura",(DOC,))
   reconciliations=rows("select f.numero_factura,c.resultado,c.importe_factura,c.importe_explicado,c.diferencia,count(cd.id),count(cd.albaran_id_contador),count(*) filter(where cd.tipo_relacion='SIN_COINCIDENCIA') from public.facturas f join public.conciliaciones c on c.factura_id=f.id and c.es_actual left join public.conciliacion_detalles cd on cd.conciliacion_id=c.id where f.documento_id=%s group by f.numero_factura,c.id order by f.numero_factura",(DOC,))
   incidents=rows("select f.numero_factura,array_agg(distinct i.codigo order by i.codigo) from public.facturas f left join public.facturas_incidencias i on i.factura_id=f.id where f.documento_id=%s group by f.numero_factura order by f.numero_factura",(DOC,))
   doc=rows("select estado_lectura,estado_persistencia,cantidad_documentos_detectados,jsonb_array_length(inventario_facturas),array(select x->>'estado' from jsonb_array_elements(inventario_facturas)x) from public.documentos_facturas where id=%s",(DOC,))
   counts={t:rows(f'select count(*) from public.{t}')[0][0] for t in ('facturas','normalizacion_ejecuciones','conciliaciones','conciliacion_detalles','facturas_albaranes_extraidos','facturas_movimientos')}
   isolation=rows("select (select count(*) from public.facturas where proveedor_literal ilike '%%HEFAME%%'),(select count(*) from public.facturas where farmacia='RITA'),(select count(*) from public.documentos_facturas where bloqueado_hasta>now()),(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now()),(select count(*) from public.normalizacion_ejecuciones where documento_id=%s)",(DOC,))[0]
  assert flags==[(False,False,False,['PIO'])]
  assert len(base)==2 and {(x[1],x[2],x[3]) for x in base}=={(Decimal('448.0000'),'NORMALIZADA','CONCILIADA'),(Decimal('177.7400'),'NORMALIZADA','CONCILIADA')}
  assert [x[1] for x in alliance]==list(NUMS) and all(x[5:8]==('NORMALIZADA','PENDIENTE_CONCILIAR','NO_REQUERIDA') for x in alliance)
  assert eligibility==[('08009277','APTA','APTA_MIXTA'),('08009278','APTA','APTA_MERCANCIA'),('08009279','APTA','APTA_MERCANCIA')]
  assert doc==[('NORMALIZADA','COMPLETA',3,3,['PERSISTIDAS','PERSISTIDAS','PERSISTIDAS'])]
  assert counts['facturas']==5 and counts['normalizacion_ejecuciones']==4 and counts['conciliaciones']==6
  assert isolation==(0,0,0,0,1)
  print(json.dumps({'flags':flags,'facturas_previas':base,'alliance':alliance,'elegibilidad':eligibility,'conciliaciones':reconciliations,'incidencias':incidents,'documento':doc,'conteos':counts,'aislamiento':isolation},default=str,ensure_ascii=True))
 finally:c.rollback();c.close()

from decimal import Decimal
if __name__=='__main__':main()
