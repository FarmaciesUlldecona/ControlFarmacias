from types import SimpleNamespace
from pathlib import Path
import pytest
from src.facturas.barrera_farmacia import (
    AUTORIDADES_DOCUMENTALES_FARMACIA,
    ErrorFarmaciaDocumental,
    farmacia_destinatario,
    resolver_farmacia_documental,
    validar_farmacia_antes_de_persistir,
)
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase


def _documentado(valor):
    return None if valor is None else {
        "valor": valor,
        "evidencia": [{"pagina": 1, "literal": valor, "ubicacion": {"tabla": "cabecera"}}],
    }


def documento(*, nombre=None, nif=None, archivo=None):
    doc = {"documento_completo_demostrado": True, "facturas": [{"destinatario": {
        "nombre": _documentado(nombre), "nif": _documentado(nif),
    }}]}
    if archivo is not None:
        doc["archivo_origen"] = archivo
    return doc


def documento_pio(**kwargs):
    return documento(nif="40901058C", **kwargs)


def test_contenido_nif_maestro_resuelve_pio():
    doc = documento_pio()
    assert farmacia_destinatario(doc["facturas"][0]) == "PIO"
    resolucion = resolver_farmacia_documental(doc["facturas"][0])
    assert resolucion.campo_documental == "destinatario.nif"
    assert resolucion.valor_observado == "40901058C"
    assert resolucion.provenance["pagina"] == 1


def test_destinatario_y_nif_correctos_resuelven_pio_por_nif():
    doc = documento_pio(nombre="PUIG SALOMÓN, PÍO")
    resolucion = resolver_farmacia_documental(doc["facturas"][0])
    assert resolucion.farmacia_documental == "PIO"
    assert resolucion.campo_documental == "destinatario.nif"


def test_filename_pio_sin_evidencia_documental_no_demuestra():
    assert farmacia_destinatario(documento(archivo="PIO.pdf")["facturas"][0]) == "NO_DEMOSTRABLE"


def test_filename_rita_con_nif_pio_resuelve_pio_y_contrasta_contradictoria():
    doc = documento_pio(archivo="RITA.pdf")
    assert farmacia_destinatario(doc["facturas"][0]) == "PIO"
    with pytest.raises(ErrorFarmaciaDocumental, match="CONTRADICTORIA"):
        validar_farmacia_antes_de_persistir("RITA", doc)


def test_filename_pio_con_nif_diferente_no_identifica_pio():
    doc = documento(nif="B12345678", archivo="PIO.pdf")
    assert farmacia_destinatario(doc["facturas"][0]) == "NO_DEMOSTRABLE"


@pytest.mark.parametrize("nombre", [
    "PUIG SALOMÓN, PÍO", "puig salomon, pio", "  Puig   Salomón Pío  ",
])
def test_nombre_autorizado_normaliza_mayusculas_acentos(nombre):
    assert farmacia_destinatario(documento(nombre=nombre)["facturas"][0]) == "PIO"


def test_nif_pio_prevalece_con_nombre_ligeramente_distinto():
    doc = documento_pio(nombre="FARMACIA PIO PUIG SALOMON")
    resolucion = resolver_farmacia_documental(doc["facturas"][0])
    assert resolucion.farmacia_documental == "PIO"
    assert resolucion.campo_documental == "destinatario.nif"


def test_nif_desconocido_no_demuestra():
    assert farmacia_destinatario(documento(nif="A00000000")["facturas"][0]) == "NO_DEMOSTRABLE"


def test_nombre_pio_con_nif_distinto_es_contradictorio():
    doc = documento(nombre="PUIG SALOMÓN, PÍO", nif="B12345678")
    assert farmacia_destinatario(doc["facturas"][0]) == "CONTRADICTORIA"
    with pytest.raises(ErrorFarmaciaDocumental, match="CONTRADICTORIA"):
        validar_farmacia_antes_de_persistir("PIO", doc)


def test_no_existe_autoridad_documental_rita():
    assert set(AUTORIDADES_DOCUMENTALES_FARMACIA) == {"PIO"}


@pytest.mark.parametrize("operativa,contenido,codigo", [
    ("RITA","PIO","CONTRADICTORIA"),
    ("PIO","CLIENTE","NO_DEMOSTRABLE"), ("RITA","CLIENTE","NO_DEMOSTRABLE")])
def test_repositorio_bloquea_antes_de_cualquier_rpc(operativa, contenido, codigo):
    class ClienteProhibido:
        def __getattr__(self, name):
            pytest.fail("Se intento acceso remoto antes de barrera: " + name)
    repo = RepositorioRuntimeSupabase(ClienteProhibido())
    doc = documento_pio() if contenido == "PIO" else documento(nombre=contenido)
    with pytest.raises(ErrorFarmaciaDocumental, match=codigo):
        repo.persistir_normalizacion(SimpleNamespace(farmacia=operativa),
            SimpleNamespace(documento_normalizado=doc), "hash", "w", "MANUAL", "key")


def test_multifactura_valida_todas_antes_de_persistir():
    doc = documento_pio()
    doc["facturas"] += documento(nombre="CLIENTE SIN AUTORIDAD")["facturas"]
    with pytest.raises(ErrorFarmaciaDocumental, match="NO_DEMOSTRABLE"):
        validar_farmacia_antes_de_persistir("PIO", doc)


@pytest.mark.parametrize("nombre", ["PIO.pdf", "RITA.pdf", "HEFAME_1234.pdf"])
def test_filename_no_cambia_farmacia_documental(nombre):
    doc = documento_pio(archivo=nombre)
    assert validar_farmacia_antes_de_persistir("PIO", doc) == "CONSISTENTE"


def test_valor_sin_literal_de_respaldo_no_demuestra():
    doc = documento_pio()
    doc["facturas"][0]["destinatario"]["nif"]["evidencia"][0]["literal"] = "CLIENTE"
    with pytest.raises(ErrorFarmaciaDocumental, match="NO_DEMOSTRABLE"):
        validar_farmacia_antes_de_persistir("PIO", doc)


def test_conciliacion_revalida_antes_de_escrituras():
    class Lectura:
        def table(self, name):
            self.name = name
            return self
        def select(self, *args): return self
        def eq(self, *args): return self
        def single(self): return self
        def execute(self):
            data = ({"farmacia": "PIO", "normalizacion_ejecucion_id": "n"}
                    if self.name == "facturas" else {"resultado_json": documento(nombre="CLIENTE")})
            return SimpleNamespace(data=data)
        def update(self, *args): pytest.fail("Escritura antes de validar")
        def insert(self, *args): pytest.fail("Escritura antes de validar")
    with pytest.raises(ErrorFarmaciaDocumental, match="NO_DEMOSTRABLE"):
        RepositorioRuntimeSupabase(Lectura()).guardar_conciliacion(
            SimpleNamespace(farmacia="PIO", factura_id="f"), "w", None)


def test_entrypoints_productivos_sin_barrera_farmacia_es_cero():
    raiz = Path(__file__).resolve().parents[2]
    comprobaciones = (
        (
            raiz / "src/facturas/runtime_supabase/repositorios.py",
            "def persistir_normalizacion(\n        self,",
            "def fallar_ejecucion(",
            'self._cliente.rpc("cf_persistir_normalizacion"',
        ),
        (
            raiz / "src/facturas/runtime_supabase/repositorios.py",
            "def guardar_conciliacion(\n        self,",
            "def fallar_conciliacion(",
            '.update({"es_actual": False})',
        ),
        (
            raiz / "pruebas/piloto_productivo_2i.py",
            "def persist(document:",
            "def validate_persistence(",
            "select public.cf_persistir_normalizacion",
        ),
        (
            raiz / "pruebas/renormalizacion_controlada_logista_2k.py",
            "def main():",
            'if __name__ == "__main__":',
            "insert into public.normalizacion_ejecuciones",
        ),
    )
    sin_barrera = []
    for ruta, inicio, fin, escritura in comprobaciones:
        texto = ruta.read_text(encoding="utf-8")
        posicion_inicio = texto.rindex(inicio)
        cuerpo = texto[posicion_inicio:texto.index(fin, posicion_inicio)]
        if (
            "validar_documento_antes_de_persistir" not in cuerpo
            or cuerpo.index("validar_documento_antes_de_persistir") > cuerpo.index(escritura)
        ):
            sin_barrera.append(str(ruta.relative_to(raiz)))
    assert sin_barrera == [], f"ENTRYPOINTS_PERSISTENCIA_SIN_BARRERA_FARMACIA={len(sin_barrera)}: {sin_barrera}"
