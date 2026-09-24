from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.runtime_supabase.conciliacion import conciliar_importes
from src.facturas.runtime_supabase.extraccion_productiva import (
    ConfiguracionExtraccionProductiva,
    OrquestadorExtraccionProductiva,
)
from src.facturas.runtime_supabase.modelos import (
    ConfiguracionRuntime,
    DetalleConciliacion,
    DocumentoTrabajo,
    EstadoConciliacion,
    EstadoNormalizacion,
    EstadoRevision,
    FacturaTrabajo,
    ResultadoEtapa,
    TipoRelacionConciliacion,
    UsoLuna,
    conservar_id_proveedor,
)
from src.facturas.runtime_supabase.worker_conciliacion import WorkerConciliacion
from src.facturas.runtime_supabase.worker_normalizacion import WorkerNormalizacion


class Etapa:
    def __init__(self, codigo: str, valores: dict, *, uso_ocr: bool = False) -> None:
        self.codigo = codigo
        self.valores = valores
        self.uso_ocr = uso_ocr
        self.solicitudes: list[frozenset[str]] = []

    def extraer(self, ruta_pdf: Path, campos_pendientes: frozenset[str]) -> ResultadoEtapa:
        self.solicitudes.append(campos_pendientes)
        return ResultadoEtapa(
            valores={k: v for k, v in self.valores.items() if k in campos_pendientes},
            provenance={"fuente": self.codigo},
            uso_ocr=self.uso_ocr,
        )


class Luna:
    codigo = "LUNA_FIELD_ONLY"

    def __init__(self, valores: dict) -> None:
        self.valores = valores
        self.solicitudes: list[frozenset[str]] = []

    def extraer_campos(self, ruta_pdf: Path, campos_pendientes: frozenset[str]):
        self.solicitudes.append(campos_pendientes)
        return (
            ResultadoEtapa(
                valores={k: v for k, v in self.valores.items() if k in campos_pendientes},
                provenance={"fuente": "LUNA", "field_only": True},
            ),
            UsoLuna(
                modelo="gpt-5.6-luna",
                campos=tuple(sorted(campos_pendientes)),
                tokens_entrada=100,
                tokens_salida=20,
                coste=Decimal("0.001234"),
            ),
        )


def test_estados_publicos_exactos() -> None:
    assert {x.value for x in EstadoNormalizacion} == {
        "PENDIENTE", "NORMALIZANDO", "NORMALIZADA", "REQUIERE_REVISION"
    }
    assert {x.value for x in EstadoConciliacion} == {
        "PENDIENTE_CONCILIAR", "CONCILIADA"
    }
    assert {x.value for x in EstadoRevision} == {
        "NO_REQUERIDA", "PENDIENTE_REVISION_PIO", "VALIDADA_PIO"
    }


def test_configuracion_runtime_es_segura_por_defecto() -> None:
    config = ConfiguracionRuntime()
    assert config.normalizacion_automatica is False
    assert config.conciliacion_automatica is False
    assert config.luna_habilitada is False
    assert config.farmacias_habilitadas == ("PIO",)
    assert config.tolerancia_conciliacion == Decimal("0.0500")


def test_cascada_solo_pide_a_luna_campos_pendientes() -> None:
    especifico = Etapa("ESPECIFICO", {"numero": "F-1"})
    generico = Etapa("GENERICO_LOCAL", {"total": Decimal("10.00")})
    ocr = Etapa("OCR_LOCAL", {}, uso_ocr=True)
    luna = Luna({"fecha": "2026-09-03"})
    servicio = OrquestadorExtraccionProductiva(
        extractor_especifico=especifico,
        extractor_generico_local=generico,
        extractor_ocr_local=ocr,
        extractor_luna=luna,
        configuracion=ConfiguracionExtraccionProductiva(luna_habilitada=True),
    )

    resultado = servicio.extraer("factura.pdf", {"numero", "fecha", "total"})

    assert resultado.completo is True
    assert resultado.valores == {
        "numero": "F-1",
        "total": Decimal("10.00"),
        "fecha": "2026-09-03",
    }
    assert especifico.solicitudes == [frozenset({"numero", "fecha", "total"})]
    assert generico.solicitudes == [frozenset({"fecha", "total"})]
    assert ocr.solicitudes == [frozenset({"fecha"})]
    assert luna.solicitudes == [frozenset({"fecha"})]
    assert resultado.uso_luna is not None
    assert resultado.uso_luna.tokens_total == 120
    assert resultado.uso_luna.coste == Decimal("0.001234")


def test_luna_deshabilitada_deja_null_logico_e_incidencia() -> None:
    servicio = OrquestadorExtraccionProductiva(
        extractor_especifico=Etapa("ESPECIFICO", {}),
        extractor_generico_local=None,
        extractor_ocr_local=None,
        extractor_luna=Luna({"total": "10"}),
        configuracion=ConfiguracionExtraccionProductiva(luna_habilitada=False),
    )
    resultado = servicio.extraer("factura.pdf", {"total"})
    assert resultado.valores == {}
    assert resultado.campos_pendientes == ("total",)
    assert resultado.estado_normalizacion == EstadoNormalizacion.REQUIERE_REVISION
    assert resultado.estado_revision == EstadoRevision.PENDIENTE_REVISION_PIO
    assert resultado.incidencias[0].codigo == "CAMPOS_PENDIENTES_TRAS_EXTRACCION"


def test_una_etapa_no_puede_sobrescribir_campos_ya_resueltos() -> None:
    servicio = OrquestadorExtraccionProductiva(
        extractor_especifico=Etapa("A", {"numero": "1"}),
        extractor_generico_local=Etapa("B", {"numero": "2"}),
        extractor_ocr_local=None,
        extractor_luna=None,
    )
    resultado = servicio.extraer("factura.pdf", {"numero"})
    assert resultado.valores["numero"] == "1"


def _detalle(
    importe: str,
    tipo: TipoRelacionConciliacion = TipoRelacionConciliacion.UNO_A_UNO,
    contador: int = 1,
) -> DetalleConciliacion:
    return DetalleConciliacion(
        tipo_relacion=tipo,
        importe_aplicado=Decimal(importe),
        albaran_farmacia="PIO",
        albaran_id_contador=contador,
        factura_albaran_extraido_id=f"extraido-{contador}",
        provenance={"fuente": "ALBARANES_SUPABASE"},
    )


@pytest.mark.parametrize("diferencia", ["0.0500", "-0.0500", "0.0000"])
def test_tolerancia_cinco_centimos_es_inclusiva(diferencia: str) -> None:
    total = Decimal("100.0000")
    explicado = total - Decimal(diferencia)
    resultado = conciliar_importes(total, [_detalle(str(explicado))])
    assert resultado.diferencia == Decimal(diferencia)
    assert resultado.resultado == "CONCILIADA"


def test_superar_cinco_centimos_no_oculta_diferencia() -> None:
    resultado = conciliar_importes("100", [_detalle("99.9499")])
    assert resultado.resultado == "DIFERENCIA"
    assert resultado.diferencia == Decimal("0.0501")


def test_uno_a_varios() -> None:
    resultado = conciliar_importes(
        "100",
        [
            _detalle("40", TipoRelacionConciliacion.UNO_A_VARIOS, 1),
            _detalle("60", TipoRelacionConciliacion.UNO_A_VARIOS, 2),
        ],
    )
    assert resultado.resultado == "CONCILIADA"
    assert len(resultado.detalles) == 2


def test_varios_a_uno_no_impone_unicidad_global_del_albaran() -> None:
    a = _detalle("40", TipoRelacionConciliacion.VARIOS_A_UNO, 99)
    b = _detalle("60", TipoRelacionConciliacion.VARIOS_A_UNO, 99)
    assert conciliar_importes("40", [a]).resultado == "CONCILIADA"
    assert conciliar_importes("60", [b]).resultado == "CONCILIADA"


class RepoNormalizacion:
    def __init__(self, documento: DocumentoTrabajo | None) -> None:
        self.documento = documento
        self.completados = []
        self.fallos = []

    def reclamar_documento(self, worker_id):
        resultado, self.documento = self.documento, None
        return resultado

    def persistir_normalizacion(self, *args):
        self.completados.append(args)

    def fallar_ejecucion(self, *args):
        self.fallos.append(args)


def test_worker_normalizacion_no_hace_nada_sin_claim(tmp_path: Path) -> None:
    repo = RepoNormalizacion(None)
    servicio = OrquestadorExtraccionProductiva(
        extractor_especifico=Etapa("LOCAL", {"total": "1"}),
        extractor_generico_local=None,
        extractor_ocr_local=None,
        extractor_luna=None,
    )
    worker = WorkerNormalizacion(repo, lambda _: tmp_path / "x.pdf", servicio, frozenset({"total"}), "w")
    assert worker.ejecutar_una() is False
    assert repo.completados == []


def test_worker_normalizacion_registra_resultado_y_hash(tmp_path: Path) -> None:
    documento = DocumentoTrabajo("d1", "PIO/x.pdf", "x.pdf", "PIO")
    repo = RepoNormalizacion(documento)
    servicio = OrquestadorExtraccionProductiva(
        extractor_especifico=Etapa("LOCAL", {"total": "1.0000"}),
        extractor_generico_local=None,
        extractor_ocr_local=None,
        extractor_luna=None,
    )
    worker = WorkerNormalizacion(repo, lambda _: tmp_path / "x.pdf", servicio, frozenset({"total"}), "w")
    assert worker.ejecutar_una() is False
    assert repo.completados == []
    assert "EXTRACCION_INCOMPLETA_REQUIERE_REVISION" in str(repo.fallos)


def test_worker_puede_conservar_documento_normalizado_completo(tmp_path: Path) -> None:
    documento = DocumentoTrabajo("d1", "PIO/x.pdf", "x.pdf", "PIO")
    repo = RepoNormalizacion(documento)
    servicio = OrquestadorExtraccionProductiva(
        extractor_especifico=Etapa("LOCAL", {"facturas": [{"factura_id": "f1"}]}),
        extractor_generico_local=None,
        extractor_ocr_local=None,
        extractor_luna=None,
    )
    esperado = {
        "documento_completo_demostrado": True,
        "documento_id": "doc_1",
        "facturas": [{"factura_id": "f1", "destinatario": {"nombre": {
            "valor": "PUIG SALOMON, PIO", "evidencia": [
                {"pagina": 1, "literal": "PUIG SALOMON, PIO"}]}}}],
        "metadata_tecnica": {"normalizador_version": "v1"},
    }
    worker = WorkerNormalizacion(
        repo,
        lambda _: tmp_path / "x.pdf",
        servicio,
        frozenset({"facturas"}),
        "w",
        ensamblar_documento=lambda _documento, _resultado: esperado,
    )
    assert worker.ejecutar_una() is True
    resultado = repo.completados[0][1]
    assert resultado.documento_normalizado == esperado


@pytest.mark.parametrize("literal", ["123", "00123", "ABC123", None])
def test_id_proveedor_supabase_se_conserva_literal(literal: str | None) -> None:
    assert conservar_id_proveedor(literal) == literal


def test_id_proveedor_no_admite_coercion_numerica() -> None:
    with pytest.raises(TypeError):
        conservar_id_proveedor(123)  # type: ignore[arg-type]


class RepoConciliacion:
    def __init__(self, factura: FacturaTrabajo | None) -> None:
        self.factura = factura
        self.guardados = []
        self.fallos = []

    def reclamar_factura(self, worker_id):
        resultado, self.factura = self.factura, None
        return resultado

    def guardar_conciliacion(self, *args):
        self.guardados.append(args)
        return "c1"

    def fallar_conciliacion(self, *args):
        self.fallos.append(args)


def test_worker_conciliacion_registra_resultado() -> None:
    factura = FacturaTrabajo("f1", "d1", "PIO", Decimal("10.0000"))
    repo = RepoConciliacion(factura)
    worker = WorkerConciliacion(repo, lambda _: [_detalle("10")], "w")
    assert worker.ejecutar_una() is True
    assert repo.guardados[0][2].resultado == "CONCILIADA"


def test_worker_conciliacion_sin_total_crea_fallo() -> None:
    factura = FacturaTrabajo("f1", "d1", "PIO", None)
    repo = RepoConciliacion(factura)
    worker = WorkerConciliacion(repo, lambda _: [], "w")
    assert worker.ejecutar_una() is False
    assert repo.fallos[0][1] == "IMPORTE_FACTURA_AUSENTE"
