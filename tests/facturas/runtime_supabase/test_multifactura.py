from copy import deepcopy
import pytest
from src.facturas.runtime_supabase.multifactura import (
    clave_economica, clasificar_identidad, preparar_documento, persistir_multifactura,
)


def campo(value, page=1):
    return {'valor':value,'literal':str(value),'evidencia':[{'pagina':page,'literal':str(value)}]}


def documento(n=3, prefix='TEST'):
    fs=[]
    for i in range(n):
        p=i+1
        fs.append({'tipo_documento':campo('FACTURA',p),'numero_factura':campo(f'{prefix}-{p}',p),
          'fecha_factura':campo({'iso':'2026-07-31'},p),
          'proveedor':{'nif':campo('A50004324',p),'nombre':campo('ALLIANCE HEALTHCARE',p)},
          'destinatario':{'nif':campo('40901058C',p)},
          'totales':{'total':campo('121.0000',p),'base_imponible':campo('100',p),'iva':campo('21',p)},
          'naturaleza_principal':'MERCANCIA','estado_validacion':'VALIDADA',
          'requiere_conciliacion_albaranes':True,'factura_completa_demostrada':True,
          'pagina_inicio':p,'pagina_fin':p,'provenance':{'segment_id':f's{p}','paginas':[p]},
          'albaranes':[{'orden':1,'numero':campo(f'ALB-{p}',p),'sentido':'CARGO','importe_total':campo('121',p)}],
          'impuestos':[],'vencimientos':[],'movimientos_comerciales':[],'incidencias':[]})
    return {'documento_completo_demostrado':True,'numero_paginas':n,'facturas':fs}


@pytest.mark.parametrize('n',[1,3,5])
def test_n_facturas_y_seleccion_sin_recortar(n):
    d=documento(n); p=preparar_documento(d,['s1'])
    assert len(p['resultado_json']['facturas'])==n
    assert len({f['factura_id'] for f in p['resultado_json']['facturas']})==n
    assert 'factura_id' not in d['facturas'][0]


def test_identidad_no_depende_filename_sha_paginas():
    a=documento(1)['facturas'][0]; b=deepcopy(a)
    b.update(filename='otra.pdf',sha='distinto',pagina_inicio=10,pagina_fin=11)
    b['provenance']={'segment_id':'otro','paginas':[10,11]}
    assert clave_economica(a)==clave_economica(b)


def test_identidad_mismo_numero_version_incompatible():
    a=documento(1)['facturas'][0]; b=deepcopy(a)
    b['totales']['total']=campo('122')
    assert clasificar_identidad(b,[a])=='IDENTIDAD_NO_DEMOSTRADA'
    assert clave_economica(b)!=clave_economica(a)


def test_duplicada_y_dos_nuevas():
    fs=documento(3)['facturas']
    assert [clasificar_identidad(f,[fs[0]]) for f in fs]==['DUPLICADA','NUEVA','NUEVA']


def test_falta_evidencia():
    f=documento(1)['facturas'][0]; f['proveedor']['nif']['evidencia']=[]
    assert clave_economica(f) is None
    assert clasificar_identidad(f,[])=='IDENTIDAD_NO_DEMOSTRADA'


def test_conflicto_prevalece_sobre_duplicado_sin_depender_del_orden():
    a=documento(1)['facturas'][0]; b=deepcopy(a)
    b['totales']['total']=campo('122')
    assert clasificar_identidad(a,[a,b])=='IDENTIDAD_NO_DEMOSTRADA'
    assert clasificar_identidad(a,[b,a])=='IDENTIDAD_NO_DEMOSTRADA'


def test_total_canonico_compatible_con_numeric_18_4():
    a=documento(1)['facturas'][0]; b=deepcopy(a)
    a['totales']['total']=campo('-0.0000'); b['totales']['total']=campo('0.0000')
    assert clave_economica(a)==clave_economica(b)
    a['totales']['total']=campo('100000000000000.0000')
    assert clave_economica(a) is None


def test_incompleta_no_oculta_hermanas():
    d=documento();d['facturas'][1]['factura_completa_demostrada']=False
    r=preparar_documento(d,['s1'])['resultado_json']
    assert not r['facturas'][1]['factura_completa_demostrada'] and len(r['facturas'])==3


@pytest.mark.parametrize('error',['documento','rango','provenance','solape','seleccion'])
def test_cobertura_fail_closed(error):
    d=documento(); selected=['s1']
    if error=='documento':d['documento_completo_demostrado']=False
    elif error=='rango':d['facturas'][0]['pagina_fin']=99
    elif error=='provenance':d['facturas'][0]['provenance']['paginas']=[]
    elif error=='solape':d['facturas'][1]['pagina_inicio']=1;d['facturas'][1]['provenance']['paginas']=[1,2]
    else:selected=['inexistente']
    with pytest.raises(ValueError):preparar_documento(d,selected)


def test_wrapper_usa_un_rpc_con_inventario_completo():
    class Client:
        def rpc(self,name,payload):self.name=name;self.payload=payload;return self
        def execute(self):return 'OK'
    c=Client()
    assert persistir_multifactura(c,'doc',documento(),['s2'],'local','idem','hash')=='OK'
    assert c.name=='cf_persistir_documento_multifactura'
    assert len(c.payload['p_resultado']['facturas'])==3
    assert c.payload['p_segmentos_autorizados']==['s2']


def test_evidencia_no_puede_provenir_de_otra_hermana():
    d=documento();d['facturas'][1]['totales']['total']=campo('121',1)
    with pytest.raises(ValueError,match='EVIDENCIA_FUERA_DE_FACTURA'):
        preparar_documento(d,['s2'])


def test_alliance_real_completo_solo_memoria_promocion_conservadora():
    from pathlib import Path
    from src.facturas.motor_local.backend.pdfium import BackendPdfium
    from src.facturas.motor_local.servicio import MotorDocumentoLocal
    from src.facturas.runtime_supabase.multifactura import adaptar_resultado_local
    path=Path(__file__).resolve().parents[3]/'pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf'
    local=MotorDocumentoLocal(BackendPdfium()).extraer(path)
    d=adaptar_resultado_local(local)
    assert d['numero_paginas']==11 and d['documento_completo_demostrado']
    assert [(f['pagina_inicio'],f['pagina_fin']) for f in d['facturas']]==[(1,4),(5,9),(10,11)]
    assert [f['numero_factura']['valor'] for f in d['facturas']]==['08009278','08009277','08009279']
    assert [f['totales']['total']['valor'] for f in d['facturas']]==['3824.59','10111.55','141.01']
    assert len({f['identidad_economica_clave'] for f in d['facturas']})==3
    for f,raw in zip(d['facturas'],local.facturas):
        assert f['factura_completa_demostrada']
        assert len(f['vencimientos'])==1
        assert len(f['vencimientos'][0]['fecha']['evidencia'])==f['pagina_fin']-f['pagina_inicio']+1
        assert len(f['albaranes'])==len(raw['albaranes'])
        assert all(a['numero']['evidencia'] for a in f['albaranes'])
        assert len(f['extraccion_local']['candidatos_fila'])==len(raw['candidatos_fila'])
        assert len(f['impuestos'])==len(raw['impuestos'])
    assert [len(f['albaranes']) for f in d['facturas']]==[109,160,5]
    assert [len(f['movimientos_comerciales']) for f in d['facturas']]==[0,7,0]
    assert {m['descripcion_literal']['valor'] for m in d['facturas'][1]['movimientos_comerciales']}=={
        'ABONOS AGRUPADOS','CARGO/ABONO DIRECT','CARGO VENTA DIRECT',
        'CONDIC. COMERCIAL','SERVICIO BASICO',
    }
    assert len(d['facturas'][1]['extraccion_local']['operaciones_economicas'])==5
    assert len(d['facturas'][1]['extraccion_local']['movimientos'])==5
    assert len(d['facturas'][1]['extraccion_local']['relaciones_documentales'])==3
