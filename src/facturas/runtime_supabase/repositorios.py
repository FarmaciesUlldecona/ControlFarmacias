from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol
from src.facturas.completitud_documental import validar_documento_antes_de_persistir

from .clasificacion_fallos import clasificar_fallo, clasificar_fallo_conciliacion
from .modelos import (
    DetalleConciliacion,
    conservar_id_proveedor,
    ConfiguracionRuntime,
    DocumentoTrabajo,
    FacturaTrabajo,
    IncidenciaRuntime,
    ResultadoConciliacion,
    ResultadoExtraccionProductiva,
)
from .conciliacion import (
    AjusteDocumentalTrabajo,
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    MovimientoDocumentalTrabajo,
    VENTANA_FECHA_DIAS,
    buscar_candidato_albaran,
    construir_detalles_movimientos_documentales,
    detalle_desde_busqueda,
)


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RepositorioNormalizacion(Protocol):
    def reclamar_documento(self, worker_id: str) -> DocumentoTrabajo | None: ...

    def reclamar_documento_manual_one_shot(
        self,
        worker_id: str,
    ) -> DocumentoTrabajo | None: ...

    def persistir_normalizacion(
        self,
        documento: DocumentoTrabajo,
        resultado: ResultadoExtraccionProductiva,
        resultado_hash: str,
        worker_id: str,
        disparador: str,
        idempotency_key: str,
    ) -> None: ...

    def fallar_ejecucion(
        self,
        documento: DocumentoTrabajo,
        codigo: str,
        detalle: str,
        worker_id: str,
        disparador: str,
        idempotency_key: str,
    ) -> None: ...


class RepositorioConciliacion(Protocol):
    def reclamar_factura(self, worker_id: str) -> FacturaTrabajo | None: ...

    def reclamar_factura_manual_one_shot(self, worker_id: str) -> FacturaTrabajo | None: ...

    def construir_detalles(
        self,
        factura: FacturaTrabajo,
    ) -> tuple[DetalleConciliacion, ...]: ...

    def guardar_conciliacion(
        self,
        factura: FacturaTrabajo,
        worker_id: str,
        resultado: ResultadoConciliacion,
        *,
        disparador: str = "AUTOMATICO",
    ) -> str: ...

    def fallar_conciliacion(
        self,
        factura: FacturaTrabajo,
        codigo: str,
        detalle: str,
        worker_id: str,
        disparador: str = "AUTOMATICO",
    ) -> None: ...


class RepositorioRuntimeSupabase:
    """Adaptador PostgREST para uso exclusivo desde backend/service role.

    Construir el repositorio no realiza red. Cada metodo explicita las tablas o
    RPC utilizadas y no se importa desde los procesos diarios existentes.
    """

    def __init__(self, cliente: Any) -> None:
        self._cliente = cliente

    def obtener_configuracion(self) -> ConfiguracionRuntime:
        respuesta = (
            self._cliente.table("cf_configuracion")
            .select(
                "normalizacion_automatica,conciliacion_automatica,"
                "luna_habilitada,farmacias_habilitadas,tolerancia_conciliacion"
            )
            .eq("id", True)
            .single()
            .execute()
        )
        fila = respuesta.data
        return ConfiguracionRuntime(
            normalizacion_automatica=bool(fila["normalizacion_automatica"]),
            conciliacion_automatica=bool(fila["conciliacion_automatica"]),
            luna_habilitada=bool(fila["luna_habilitada"]),
            farmacias_habilitadas=tuple(fila["farmacias_habilitadas"]),
            tolerancia_conciliacion=Decimal(str(fila["tolerancia_conciliacion"])),
        )

    def crear_signed_url_pdf(
        self,
        archivo_ruta: str,
        *,
        segundos: int = 300,
    ) -> str:
        """Genera una URL temporal desde backend; el bucket permanece privado."""
        if segundos <= 0 or segundos > 3600:
            raise ValueError("La caducidad debe estar entre 1 y 3600 segundos")
        respuesta = (
            self._cliente.storage.from_("facturas-pdf")
            .create_signed_url(archivo_ruta, segundos)
        )
        url = respuesta.get("signedURL") or respuesta.get("signedUrl")
        if not url:
            raise RuntimeError("Supabase no devolvio una signed URL")
        return str(url)

    @staticmethod
    def _documento_desde_filas(filas: list[dict[str, Any]]) -> DocumentoTrabajo | None:
        if not filas:
            return None
        fila = filas[0]
        return DocumentoTrabajo(
            documento_id=str(fila["id"]),
            archivo_ruta=str(fila["archivo_ruta"]),
            archivo_nombre=str(fila["archivo_nombre"]),
            farmacia=str(fila["farmacia"]),
            reprocesado_manual=fila.get("reprocesar_solicitado_at") is not None,
        )

    def reclamar_documento(self, worker_id: str) -> DocumentoTrabajo | None:
        respuesta = self._cliente.rpc(
            "cf_reclamar_documento_normalizacion",
            {"p_worker_id": worker_id, "p_bloqueo_segundos": 300},
        ).execute()
        return self._documento_desde_filas(respuesta.data or [])

    def reclamar_documento_manual_one_shot(
        self,
        worker_id: str,
    ) -> DocumentoTrabajo | None:
        respuesta = self._cliente.rpc(
            "cf_reclamar_documento_normalizacion_manual_one_shot",
            {"p_worker_id": worker_id, "p_bloqueo_segundos": 300},
        ).execute()
        return self._documento_desde_filas(respuesta.data or [])

    def persistir_normalizacion(
        self,
        documento: DocumentoTrabajo,
        resultado: ResultadoExtraccionProductiva,
        resultado_hash: str,
        worker_id: str,
        disparador: str,
        idempotency_key: str,
    ) -> None:
        validar_documento_antes_de_persistir(documento.farmacia, resultado.documento_normalizado)
        luna = resultado.uso_luna
        payload = {
            "estado": "COMPLETADA" if resultado.completo else "INCOMPLETA",
            "resultado_hash": resultado_hash,
            "uso_ocr": any(paso.uso_ocr for paso in resultado.pasos),
            "uso_luna": luna is not None,
            "luna_modelo": luna.modelo if luna else None,
            "luna_campos": list(luna.campos) if luna else [],
            "tokens_entrada": luna.tokens_entrada if luna else None,
            "tokens_salida": luna.tokens_salida if luna else None,
            "tokens_total": luna.tokens_total if luna else None,
            "coste_luna": str(luna.coste) if luna else None,
            "pasos": [asdict(paso) for paso in resultado.pasos],
            "resultado_json": (
                dict(resultado.documento_normalizado)
                if resultado.documento_normalizado is not None
                else {
                    "valores": dict(resultado.valores),
                    "campos_pendientes": list(resultado.campos_pendientes),
                }
            ),
            "finalizado_at": _ahora_iso(),
        }
        payload["incidencias_runtime"] = [asdict(item) for item in resultado.incidencias]
        self._cliente.rpc("cf_persistir_normalizacion", {
            "p_documento_id": documento.documento_id,
            "p_worker_id": worker_id,
            "p_disparador": disparador,
            "p_idempotency_key": idempotency_key,
            "p_resultado_hash": resultado_hash,
            "p_resultado": payload,
        }).execute()

    def persistir_documento_automatico(
        self,
        documento: DocumentoTrabajo,
        resultado: ResultadoExtraccionProductiva,
        resultado_hash: str,
        worker_id: str,
        disparador: str,
        idempotency_key: str,
    ) -> None:
        """Persistencia oficial protegida por identidad económica y multifactura.

        Conserva el inventario completo y autoriza únicamente segmentos completos,
        fiscalmente identificados, normalizados y pertenecientes a PIO. La RPC
        decide atómicamente duplicados y versiones económicas incompatibles.
        """
        from .multifactura import preparar_documento
        from src.facturas.barrera_farmacia import resolver_farmacia_documental

        normalizado = resultado.documento_normalizado
        validar_documento_antes_de_persistir(documento.farmacia, normalizado)
        preparado = preparar_documento(normalizado, [])
        inventario = preparado["resultado_json"]
        segmentos = []
        for factura in inventario["facturas"]:
            farmacia = resolver_farmacia_documental(factura)
            if (
                factura.get("factura_completa_demostrada") is True
                and factura.get("estado_validacion") in {"VALIDADA", "VALIDADA_CON_INCIDENCIAS"}
                and factura.get("identidad_economica_clave")
                and farmacia.estado == "RESUELTA"
                and farmacia.farmacia_documental == documento.farmacia
            ):
                segmentos.append(factura["provenance"]["segment_id"])
        if not segmentos:
            raise ValueError("NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE")
        self._cliente.rpc("cf_persistir_documento_multifactura", {
            "p_documento_id": documento.documento_id,
            "p_worker_id": worker_id,
            "p_idempotency_key": idempotency_key,
            "p_resultado_hash": resultado_hash,
            "p_resultado": inventario,
            "p_segmentos_autorizados": segmentos,
            "p_disparador": disparador,
        }).execute()

    def fallar_ejecucion(
        self,
        documento: DocumentoTrabajo,
        codigo: str,
        detalle: str,
        worker_id: str,
        disparador: str,
        idempotency_key: str,
    ) -> None:
        self._cliente.rpc("cf_registrar_fallo_normalizacion", {
            "p_documento_id": documento.documento_id,
            "p_worker_id": worker_id,
            "p_disparador": disparador,
            "p_idempotency_key": idempotency_key,
            "p_error_codigo": codigo,
            "p_error_detalle": detalle,
            "p_clase_fallo": clasificar_fallo(codigo, detalle),
        }).execute()

    def reclamar_factura(self, worker_id: str) -> FacturaTrabajo | None:
        return self._reclamar_factura("cf_reclamar_factura_conciliacion", worker_id)

    def reclamar_factura_manual_one_shot(self, worker_id: str) -> FacturaTrabajo | None:
        """Claim MANUAL_ONE_SHOT (R5, migracion 18): selector oficial, sin preseleccion."""
        return self._reclamar_factura("cf_reclamar_factura_conciliacion_manual_one_shot", worker_id)

    def _reclamar_factura(self, rpc: str, worker_id: str) -> FacturaTrabajo | None:
        respuesta = self._cliente.rpc(
            rpc,
            {"p_worker_id": worker_id, "p_bloqueo_segundos": 300},
        ).execute()
        filas = respuesta.data or []
        if not filas:
            return None
        fila = filas[0]
        return FacturaTrabajo(
            factura_id=str(fila["id"]),
            documento_id=str(fila["documento_id"]),
            farmacia=str(fila["farmacia"]),
            importe_total=(
                Decimal(str(fila["importe_total"]))
                if fila.get("importe_total") is not None
                else None
            ),
            proveedor_id=(str(fila["proveedor_id"]) if fila.get("proveedor_id") else None),
        )

    def construir_detalles(
        self,
        factura: FacturaTrabajo,
    ) -> tuple[DetalleConciliacion, ...]:
        """Construye matches solo desde Supabase; nunca consulta Farmatic."""
        invoice_response = (
            self._cliente.table("facturas")
            .select("proveedor_literal,proveedor_nombre,proveedor_id,categoria,iva_total,recargo_equivalencia_total,datos_extraidos")
            .eq("id", factura.factura_id)
            .single()
            .execute()
        )
        invoice_row = invoice_response.data
        provider_literal = invoice_row.get("proveedor_literal") or invoice_row.get("proveedor_nombre")
        farmatic_provider_id = None
        provider_id = invoice_row.get("proveedor_id")
        if provider_id:
            provider_response = (
                self._cliente.table("proveedores")
                .select("farmatic_id_proveedor")
                .eq("id", provider_id)
                .single()
                .execute()
            )
            farmatic_provider_id = provider_response.data.get("farmatic_id_proveedor")

        naturaleza = str((invoice_row.get("datos_extraidos") or {}).get("naturaleza_principal") or "")
        usa_mercancia = invoice_row.get("categoria") == "MERCANCIA" or naturaleza == "MIXTA"
        usa_servicios = invoice_row.get("categoria") == "CUOTA_SERVICIO" or naturaleza == "MIXTA"
        if not usa_mercancia and not usa_servicios:
            raise ValueError("TIPO_DOCUMENTAL_NO_DEMOSTRADO")

        details = []
        if usa_servicios:
            movement_response = (
                self._cliente.table("facturas_movimientos")
                .select("id,categoria,descripcion_literal,sentido,importe,base,provenance")
                .eq("factura_id", factura.factura_id)
                .order("orden")
                .execute()
            )
            movements = tuple(
                MovimientoDocumentalTrabajo(
                    id=str(row["id"]), concepto_literal=str(row["descripcion_literal"]),
                    tipo=str(row["categoria"]), sentido=str(row["sentido"]) if row.get("sentido") else None,
                    importe=Decimal(str(row["importe"])) if row.get("importe") is not None else None,
                    base=Decimal(str(row["base"])) if row.get("base") is not None else None,
                    provenance=row.get("provenance") or {},
                )
                for row in (movement_response.data or [])
            )
            ajustes = ()
            if naturaleza != "MIXTA" and movements and all(m.importe is None for m in movements):
                ajustes = tuple(
                    AjusteDocumentalTrabajo(nombre, Decimal(str(valor)), {"factura_id": factura.factura_id})
                    for nombre, valor in (
                        ("IVA_TOTAL", invoice_row.get("iva_total")),
                        ("RECARGO_EQUIVALENCIA_TOTAL", invoice_row.get("recargo_equivalencia_total")),
                    )
                    if valor is not None and Decimal(str(valor)) != 0
                )
            movement_details = construir_detalles_movimientos_documentales(movements, ajustes=ajustes)
            if movement_details is None:
                raise ValueError("TRAZABILIDAD_SERVICIO_INSUFICIENTE")
            details.extend(movement_details)

        extracted_rows = []
        if usa_mercancia:
            extracted_response = (
                self._cliente.table("facturas_albaranes_extraidos")
                .select("id,numero_albaran,fecha_albaran,importe_total,tipo_movimiento")
                .eq("factura_id", factura.factura_id)
                .order("orden")
                .execute()
            )
            extracted_rows = extracted_response.data or []
        dates = [date.fromisoformat(row["fecha_albaran"]) for row in extracted_rows if row.get("fecha_albaran")]
        operational_rows = []
        if dates:
            start = min(dates) - timedelta(days=VENTANA_FECHA_DIAS)
            end = max(dates) + timedelta(days=VENTANA_FECHA_DIAS)
            response = (
                self._cliente.table("albaranes")
                .select("id_contador,farmacia,id_proveedor,proveedor,numero_albaran,fecha,importe_puc,importe_pvp,estado")
                .eq("farmacia", factura.farmacia)
                .gte("fecha", start.isoformat())
                .lte("fecha", end.isoformat())
                .execute()
            )
            operational_rows = response.data or []
        candidates = tuple(
            CandidatoAlbaranSupabase(
                id_contador=int(row["id_contador"]),
                farmacia=str(row["farmacia"]),
                id_proveedor=conservar_id_proveedor(row["id_proveedor"]),
                proveedor=str(row["proveedor"]),
                numero_albaran=str(row["numero_albaran"]),
                fecha=date.fromisoformat(row["fecha"]),
                importe_puc=Decimal(str(row["importe_puc"])) if row.get("importe_puc") is not None else None,
                importe_pvp=Decimal(str(row["importe_pvp"])) if row.get("importe_pvp") is not None else None,
                estado=str(row["estado"]) if row.get("estado") is not None else None,
            )
            for row in operational_rows
        )
        for row in extracted_rows:
            documentary = AlbaranDocumentalTrabajo(
                id=str(row["id"]),
                numero=str(row["numero_albaran"]) if row.get("numero_albaran") else None,
                fecha=date.fromisoformat(row["fecha_albaran"]) if row.get("fecha_albaran") else None,
                importe=Decimal(str(row["importe_total"])) if row.get("importe_total") is not None else None,
                sentido=str(row["tipo_movimiento"]) if row.get("tipo_movimiento") else None,
            )
            match = buscar_candidato_albaran(
                documentary,
                candidates,
                proveedor_literal=provider_literal,
                farmatic_id_proveedor=farmatic_provider_id,
            )
            details.append(detalle_desde_busqueda(documentary, match))
        return tuple(details)

    def guardar_conciliacion(
        self,
        factura: FacturaTrabajo,
        worker_id: str,
        resultado: ResultadoConciliacion,
        *,
        disparador: str = "AUTOMATICO",
    ) -> str:
        """Cierre atomico (R6, migracion 18) con clave idempotente y replay seguro.

        Revalida la evidencia persistida antes de la unica escritura, que es la RPC
        transaccional ``cf_persistir_conciliacion``.
        """
        if disparador not in DISPARADORES_CONCILIACION:
            raise ValueError("disparador de conciliacion no admitido")
        # Revalidar evidencia persistida antes de la primera escritura.
        fila = (self._cliente.table("facturas")
                .select("normalizacion_ejecucion_id,farmacia")
                .eq("id", factura.factura_id).single().execute()).data
        if fila.get("farmacia") != factura.farmacia:
            raise ValueError("FARMACIA_DOCUMENTO_CONTRADICTORIA")
        ejecucion = (self._cliente.table("normalizacion_ejecuciones")
                     .select("resultado_json")
                     .eq("id", fila.get("normalizacion_ejecucion_id"))
                     .single().execute()).data
        validar_documento_antes_de_persistir(factura.farmacia, ejecucion.get("resultado_json"))
        payload = payload_conciliacion(resultado)
        respuesta = self._cliente.rpc("cf_persistir_conciliacion", {
            "p_factura_id": factura.factura_id,
            "p_worker_id": worker_id,
            "p_disparador": disparador,
            "p_idempotency_key": clave_idempotente_conciliacion(
                factura.factura_id, disparador, payload),
            "p_resultado": payload,
        }).execute()
        return str(respuesta.data)

    def fallar_conciliacion(
        self,
        factura: FacturaTrabajo,
        codigo: str,
        detalle: str,
        worker_id: str,
        disparador: str = "AUTOMATICO",
    ) -> None:
        """Fallo con backoff (R7, migracion 18); sin claim del worker no cambia nada."""
        self._cliente.rpc("cf_registrar_fallo_conciliacion", {
            "p_factura_id": factura.factura_id,
            "p_worker_id": worker_id,
            "p_disparador": disparador,
            "p_error_codigo": codigo,
            "p_error_detalle": detalle,
            "p_clase_fallo": clasificar_fallo_conciliacion(codigo, detalle),
        }).execute()


DISPARADORES_CONCILIACION = frozenset({"AUTOMATICO", "MANUAL_ONE_SHOT"})


def payload_conciliacion(resultado: ResultadoConciliacion) -> dict[str, Any]:
    """Resultado serializable para ``cf_persistir_conciliacion`` (importes como texto)."""
    estado_detalle = "COINCIDE" if resultado.resultado == "CONCILIADA" else "DIFERENCIA"
    payload = {
        "importe_factura": str(resultado.importe_factura),
        "importe_explicado": str(resultado.importe_explicado),
        "diferencia": str(resultado.diferencia),
        "tolerancia": str(resultado.tolerancia),
        "resultado": resultado.resultado,
        "detalles": [
            {
                "orden": orden,
                "factura_albaran_extraido_id": detalle.factura_albaran_extraido_id,
                "factura_movimiento_id": detalle.factura_movimiento_id,
                "albaran_farmacia": detalle.albaran_farmacia,
                "albaran_id_contador": detalle.albaran_id_contador,
                "coincidencia_numero_literal": detalle.coincidencia_numero_literal,
                "tipo_relacion": detalle.tipo_relacion.value,
                "importe_aplicado": str(detalle.importe_aplicado),
                "estado": estado_detalle,
                "provenance": dict(detalle.provenance),
            }
            for orden, detalle in enumerate(resultado.detalles, start=1)
        ],
    }
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def clave_idempotente_conciliacion(factura_id: str, disparador: str, payload: dict[str, Any]) -> str:
    """Misma evidencia -> misma clave (replay); evidencia distinta -> intento nuevo."""
    canonico = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"conciliacion:{factura_id}:{disparador}:{hashlib.sha256(canonico.encode()).hexdigest()}"
