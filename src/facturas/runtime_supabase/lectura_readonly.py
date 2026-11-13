"""Lectura ESTRICTAMENTE READ_ONLY de Supabase para el orquestador nocturno (Hito AUTO-A).

Copia en ``src/`` del patron certificado de ``pruebas/auditoria_2at/auditoria_readonly.py`` (lector con sesion
READ_ONLY REPEATABLE READ y solo SELECT/WITH; cliente sustituto sin escrituras; simulacion del camino real de
``WorkerConciliacion._procesar`` sin claim). Las series de ``pruebas/`` no cambian. Aqui la simulacion usa el
disparador ``AUTOMATICO`` (R8), que es el de la ruta automatica.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

# Ordering oficial del nucleo de la migracion 16 (cola de normalizacion); con el modo AUTOMATICO exige el flag.
SQL_COLA_NORMALIZACION = (
    "select d.id::text, d.estado_lectura, d.fecha_importacion::text, d.intentos_fallo_normalizacion "
    "from public.documentos_facturas d cross join public.cf_configuracion c "
    "where c.id = true and d.farmacia = any(c.farmacias_habilitadas) "
    "and (%(modo)s = 'MANUAL_ONE_SHOT' or c.normalizacion_automatica or d.reprocesar_solicitado_at is not null) "
    "and d.estado_lectura in ('PENDIENTE','ERROR') "
    "and coalesce(d.proximo_reintento_at,'-infinity'::timestamptz) <= now() "
    "and coalesce(d.bloqueado_hasta,'-infinity'::timestamptz) <= now() "
    "order by (d.reprocesar_solicitado_at is not null) desc, d.fecha_importacion, d.id")

# Selector oficial de conciliacion (migraciones 14 y 18).
SQL_SELECTOR_CONCILIACION = """
select f.id::text
  from public.facturas f
  cross join public.cf_configuracion c
  cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e
 where c.id = true
   and f.farmacia = any(c.farmacias_habilitadas)
   and (
       %(modo)s = 'MANUAL_ONE_SHOT'
       or c.conciliacion_automatica
       or f.conciliacion_reintento_solicitado_at is not null
   )
   and f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'
   and e.estado = 'APTA'
   and coalesce(f.conciliacion_proximo_at, '-infinity'::timestamptz) <= now()
   and coalesce(f.conciliacion_bloqueado_hasta, '-infinity'::timestamptz) <= now()
 order by
   (f.conciliacion_reintento_solicitado_at is not null) desc,
   f.fecha_factura nulls last,
   f.id
"""

_SOLO_LECTURA = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


class LectorReadOnly:
    """Unica puerta a la base: solo SELECT/WITH dentro de una transaccion READ_ONLY REPEATABLE READ."""

    def __init__(self, cur) -> None:
        self._cur = cur
        cur.execute("set local statement_timeout = '120s'")
        ro, iso = self.fila("select current_setting('transaction_read_only'), "
                            "current_setting('transaction_isolation')")
        if ro != "on" or iso != "repeatable read":
            raise PermissionError(f"SESION_NO_READ_ONLY: read_only={ro} isolation={iso}")

    def filas(self, sql: str, params=None) -> list[tuple]:
        if not _SOLO_LECTURA.match(sql):
            raise PermissionError("SENTENCIA_NO_SELECT")
        self._cur.execute(sql, params)
        return self._cur.fetchall()

    def fila(self, sql: str, params=None) -> tuple:
        resultado = self.filas(sql, params)
        if len(resultado) != 1:
            raise RuntimeError(f"SE_ESPERABA_UNA_FILA: {len(resultado)}")
        return resultado[0]

    def valor(self, sql: str, params=None):
        return self.fila(sql, params)[0]

    def json(self, sql: str, params=None):
        return json.loads(self.valor(sql, params))


class sesion_lectura:  # noqa: N801 - gestor de contexto
    """Abre una transaccion READ_ONLY REPEATABLE READ sobre una conexion psycopg2 y la deshace siempre."""

    def __init__(self, conexion) -> None:
        self._conexion = conexion

    def __enter__(self) -> LectorReadOnly:
        self._conexion.rollback()
        self._conexion.set_session(isolation_level="REPEATABLE READ", readonly=True, autocommit=False)
        self._cur = self._conexion.cursor()
        return LectorReadOnly(self._cur)

    def __exit__(self, *_exc) -> None:
        try:
            self._cur.close()
        finally:
            self._conexion.rollback()


class _Respuesta:
    def __init__(self, data) -> None:
        self.data = data


class _ConsultaLectura:
    """Subconjunto de solo lectura del query builder de supabase-py (copia del 2AT)."""

    TABLAS = frozenset({"facturas", "proveedores", "facturas_movimientos", "facturas_albaranes_extraidos",
                        "albaranes", "normalizacion_ejecuciones", "conciliacion_albaranes_reservados",
                        "albaranes_cambios"})

    def __init__(self, lector: LectorReadOnly, tabla: str) -> None:
        if tabla not in self.TABLAS:
            raise PermissionError(f"TABLA_NO_AUTORIZADA_EN_SIMULACION: {tabla}")
        self._lector, self._tabla = lector, tabla
        self._columnas: list[str] = []
        self._filtros: list[str] = []
        self._params: list = []
        self._orden: str | None = None
        self._single = False
        self._rango: tuple[int, int] | None = None

    @staticmethod
    def _ident(nombre: str) -> str:
        if not _IDENT.match(nombre):
            raise PermissionError(f"IDENTIFICADOR_NO_VALIDO: {nombre!r}")
        return nombre

    def select(self, columnas: str):
        self._columnas = [self._ident(c.strip()) for c in columnas.split(",")]
        return self

    def _filtro(self, columna: str, operador: str, valor):
        self._filtros.append(f"t.{self._ident(columna)} {operador} %s")
        self._params.append(valor)
        return self

    def eq(self, columna, valor):
        return self._filtro(columna, "=", valor)

    def gte(self, columna, valor):
        return self._filtro(columna, ">=", valor)

    def lte(self, columna, valor):
        return self._filtro(columna, "<=", valor)

    def order(self, columna: str):
        self._orden = self._ident(columna)
        return self

    def single(self):
        self._single = True
        return self

    def range(self, inicio: int, fin: int):
        if type(inicio) is not int or type(fin) is not int or inicio < 0 or fin < inicio:
            raise PermissionError(f"RANGO_NO_VALIDO: {inicio!r}..{fin!r}")
        self._rango = (inicio, fin)
        return self

    def execute(self) -> _Respuesta:
        lista = ", ".join(f"t.{c}" for c in self._columnas)
        where = " and ".join(self._filtros) or "true"
        orden = f" order by t.{self._orden}" if self._orden else ""
        params = list(self._params)
        pagina = ""
        if self._rango is not None:
            if self._orden is None or self._single:
                raise PermissionError(f"RANGO_SIN_ORDEN_O_CON_SINGLE: {self._tabla}")
            pagina = " limit %s offset %s"
            params += [self._rango[1] - self._rango[0] + 1, self._rango[0]]
        sql = (f"select to_jsonb(r)::text from public.{self._tabla} t "
               f"cross join lateral (select {lista}) r where {where}{orden}{pagina}")
        filas = [json.loads(f[0]) for f in self._lector.filas(sql, tuple(params))]
        if self._single:
            if len(filas) != 1:
                raise RuntimeError(f"SINGLE_SIN_FILA_UNICA: {self._tabla} {len(filas)}")
            return _Respuesta(filas[0])
        return _Respuesta(filas)


class ClienteLectura:
    """Cliente sustituto SOLO lectura: sin rpc, insert, update, delete ni storage."""

    def __init__(self, lector: LectorReadOnly) -> None:
        self._lector = lector

    def table(self, nombre: str) -> _ConsultaLectura:
        return _ConsultaLectura(self._lector, nombre)


def simular_conciliacion(lector: LectorReadOnly, factura_id: str, disparador: str = "AUTOMATICO") -> dict[str, Any]:
    """Camino de ``WorkerConciliacion._procesar`` sin claim ni escrituras (copia del 2AT con ``disparador``)."""
    from src.facturas.completitud_documental import validar_documento_antes_de_persistir

    from .conciliacion import ReglaTolerancia, conciliar_importes
    from .modelos import FacturaTrabajo
    from .multifactura import reconstruir_resultado_json, tiene_referencias
    from .repositorios import RepositorioRuntimeSupabase, clave_idempotente_conciliacion, payload_conciliacion

    cliente = ClienteLectura(lector)
    repositorio = RepositorioRuntimeSupabase(cliente)
    fila = json.loads(lector.valor("select to_jsonb(f)::text from public.facturas f where f.id = %s",
                                   (factura_id,)))
    factura = FacturaTrabajo(
        factura_id=str(fila["id"]),
        documento_id=str(fila["documento_id"]),
        farmacia=str(fila["farmacia"]),
        importe_total=(Decimal(str(fila["importe_total"])) if fila.get("importe_total") is not None else None),
        proveedor_id=(str(fila["proveedor_id"]) if fila.get("proveedor_id") else None),
    )
    out: dict[str, Any] = {"factura_id": factura.factura_id, "numero_factura": fila.get("numero_factura"),
                           "proveedor_nombre": fila.get("proveedor_nombre"),
                           "proveedor_literal": fila.get("proveedor_literal")}
    if factura.importe_total is None:
        out.update({"camino": "FALLO", "fallo": "IMPORTE_FACTURA_AUSENTE"})
        return out
    cfg = lector.json("select to_jsonb(c)::text from public.cf_configuracion c where id")
    regla = ReglaTolerancia(
        suelo=Decimal(str(cfg["conciliacion_tolerancia_suelo"])),
        por_albaran=Decimal(str(cfg["conciliacion_tolerancia_por_albaran"])),
        tope=Decimal(str(cfg["conciliacion_tolerancia_tope"])))
    try:
        detalles = repositorio.construir_detalles(factura)
        resultado = conciliar_importes(factura.importe_total, detalles, regla=regla)
        rev = cliente.table("facturas").select("normalizacion_ejecucion_id,farmacia") \
            .eq("id", factura.factura_id).single().execute().data
        if rev.get("farmacia") != factura.farmacia:
            raise ValueError("FARMACIA_DOCUMENTO_CONTRADICTORIA")
        ejecucion = cliente.table("normalizacion_ejecuciones").select("resultado_json,documento_id") \
            .eq("id", rev.get("normalizacion_ejecucion_id")).single().execute().data
        resultado_json = ejecucion.get("resultado_json")
        if tiene_referencias(resultado_json):
            filas = cliente.table("facturas").select("proyeccion_clave,datos_extraidos") \
                .eq("documento_id", ejecucion.get("documento_id")).execute().data or []
            resultado_json = reconstruir_resultado_json(
                resultado_json, {f["proyeccion_clave"]: f["datos_extraidos"] for f in filas})
        validar_documento_antes_de_persistir(factura.farmacia, resultado_json)
        payload = payload_conciliacion(resultado)
    except Exception as exc:  # mismo criterio que WorkerConciliacion._procesar
        out.update({"camino": "FALLO", "fallo": f"{type(exc).__name__}: {exc}"})
        return out
    out.update({
        "camino": "PERSISTIR",
        "resultado": resultado.resultado,
        "importe_factura": str(resultado.importe_factura),
        "importe_explicado": str(resultado.importe_explicado),
        "diferencia": str(resultado.diferencia),
        "idempotency_key_prevista": clave_idempotente_conciliacion(factura.factura_id, disparador, payload),
        "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                                    separators=(",", ":")).encode()).hexdigest(),
    })
    return out
