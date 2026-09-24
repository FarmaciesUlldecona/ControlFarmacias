from copy import deepcopy
from pathlib import Path

from src.facturas.motor_local.adaptadores.alliance import promover_albaran_alliance
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional


ROOT=Path(__file__).resolve().parents[3]
PDF=ROOT/'pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf'


def campo(value,page=2):
    return {'valor':value,'evidencias':[{'pagina':page,'literal':str(value)}]}


def candidato(page=2,numero='08C00001',fecha='2026-07-20',total=10.0):
    return {'orden':1,'numero_referencia':campo(numero,page),
      'fecha':campo(fecha,page) if fecha is not None else None,
      'tipo_pedido':campo('NORMAL',page),'base':campo(9.0,page),
      'total':campo(total,page) if total is not None else None,
      'sentido':campo('CARGO',page),'rol_fila':'INDETERMINADO',
      'rol_documentacion':{'valor':'ALBARAN','literal':'NUMERO ALBARAN',
        'regla':'COLUMNAS_NUMERO_ALBARAN_EXPLICITAS','evidencias':[{'pagina':page,'literal':'NUMERO ALBARAN'}]},
      'clasificacion_economica':{'concepto':'ALBARAN_MERCANCIA','regla':'TEST_MERCANCIA'},
      'provenance':{'pagina':page,'lado_tabla':'IZQUIERDA','fila_literal':'fila'}}


def promover(c,**kw):
    return promover_albaran_alliance(c,factura_documental=kw.get('factura','F1'),
      paginas_factura=kw.get('paginas',[1,2,3]),segmentacion_inequivoca=kw.get('inequivoca',True))


def test_albaran_claro_promovido():
    assert promover(candidato())['rol_fila']=='ALBARAN_DEMOSTRADO'


def test_candidato_ambiguo_no_promovido():
    c=candidato();c['rol_documentacion']['regla']='PATRON_REFERENCIA'
    assert promover(c) is None


def test_pagina_siguiente_misma_factura_promovida_por_provenance():
    assert promover(candidato(page=3),paginas=[1,2,3])['provenance']['factura_documental']=='F1'


def test_cambio_factura_no_arrastra_albaran():
    assert promover(candidato(page=4),paginas=[1,2,3]) is None


def test_mismo_numero_en_dos_bloques_conserva_provenance_separada():
    a=promover(candidato(page=2),factura='F1',paginas=[1,2])
    b=promover(candidato(page=4),factura='F2',paginas=[3,4])
    assert a['numero_albaran']['valor']==b['numero_albaran']['valor']
    assert a['provenance']['factura_documental']!=b['provenance']['factura_documental']


def test_importe_ausente_no_se_inventa():
    assert promover(candidato(total=None))['total'] is None


def test_fecha_ausente_no_se_inventa():
    assert promover(candidato(fecha=None))['fecha'] is None


def test_texto_no_concluyente_permanece_candidato():
    c=candidato();c['rol_documentacion']['valor']='OPERACION'
    assert promover(c) is None and c['rol_fila']=='INDETERMINADO'


def test_segmentacion_ambigua_no_promueve():
    assert promover(candidato(),inequivoca=False) is None


def test_pdf_real_tres_facturas_sin_mezcla():
    r=MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
    assert [(f['segmento']['identidad'],len(f['albaranes'])) for f in r.facturas]==[
      ('08009278',109),('08009277',160),('08009279',5)]
    vistos=[]
    for f in r.facturas:
        inicio,fin=f['segmento']['paginas']
        assert all(a['provenance']['factura_documental']==f['segmento']['identidad'] for a in f['albaranes'])
        assert all(inicio<=a['provenance']['pagina']<=fin for a in f['albaranes'])
        vistos.extend((a['provenance']['factura_documental'],a['orden']) for a in f['albaranes'])
    assert len(vistos)==len(set(vistos))==274


def test_reprocesado_determinista():
    motor=MotorDocumentoLocal(BackendPdfium())
    assert hash_funcional(motor.extraer(PDF))==hash_funcional(motor.extraer(PDF))


def test_filename_y_supabase_no_intervienen_en_promocion():
    c=candidato();c['filename']='engañoso.pdf';c['supabase_numero']='OTRO'
    promoted=promover(c)
    assert promoted['numero_albaran']['valor']=='08C00001'
    assert 'filename' not in promoted and 'supabase_numero' not in promoted


def test_campo_existente_sin_evidencia_falla_cerrado():
    c=candidato();c['total']['evidencias']=[]
    assert promover(c) is None
