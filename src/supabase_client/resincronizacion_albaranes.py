"""Hito 2BD: resincronización de albaranes modificados en Farmatic (migración 22).

La fuente de verdad es la cabecera actual de ``dbo.Albaran`` (leída solo con la identidad
de lectura certificada). Se comparan valores con ``Supabase.albaranes`` en una ventana:
- nuevos (en Farmatic y no en Supabase) -> ``insert`` (como la sincronización de nuevos);
- distintos -> RPC ``cf_resincronizar_albaran``, que decide en la base de datos (reserva
  R15 releída en la transacción): actualizar + historial o solo revisión;
- ausentes (en Supabase, dentro de la ventana, y no en Farmatic) -> RPC
  ``cf_registrar_albaran_ausente``: nunca se borran; quedan fuera del casado.

Este módulo no importa ``runtime_supabase`` (las tareas nocturnas no lo cargan, 2BA-D) ni
conecta a nada por sí mismo: recibe el cliente Supabase y los albaranes ya leídos.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable, Iterable

from postgrest.exceptions import APIError

from src.models.albaran import Albaran, conservar_id_proveedor

VENTANA_DIAS = 180
MARGEN_FACTURAS_DIAS = 15
PAGINA = 1000
ESTADOS_FACTURA_ABIERTOS = ("PENDIENTE_CONCILIAR", "REVISION_CONCILIACION")
ORIGEN_VENTANA = "RESYNC_VENTANA"
ORIGEN_CARGA = "CARGA_HISTORICA"
VARIABLE_ACTIVACION = "CONTROLFARMACIAS_ALBARANES_V2"
COLUMNAS_SUPABASE = ("id_contador", "farmacia", "id_proveedor", "proveedor", "numero_albaran", "fecha",
                     "importe_pvp", "importe_puc", "descuento")
CAMPOS_IDENTIDAD = ("numero_albaran", "id_proveedor")
CAMPOS_VALOR = ("fecha", "importe_puc", "importe_pvp", "descuento", "proveedor")
_CENTIMOS = Decimal("0.01")


def activada() -> bool:
    """La v2 (recepción + modificados) solo se activa tras desplegar la migración 22."""
    return os.environ.get(VARIABLE_ACTIVACION) == "1"


def id_proveedor_comparable(valor: str | None) -> str | None:
    """R9: misma regla que ``conciliacion._id_proveedor_comparable`` ('2' == '0002' == '0002 ')."""
    if valor is None:
        return None
    texto = valor.strip()
    if texto.isdigit():
        return texto.lstrip("0") or "0"
    return texto or None


def _dinero(valor: Any) -> Decimal | None:
    if valor is None or valor == "":
        return None
    return Decimal(str(valor)).quantize(_CENTIMOS, rounding=ROUND_HALF_UP)


def _fecha(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)[:10]


def payload_albaran(albaran: Albaran, farmacia: str, *, con_recepcion: bool) -> dict[str, Any]:
    """Fila de ``Supabase.albaranes`` (mismo formato que la sincronización de nuevos)."""
    fila = {
        "farmacia": farmacia,
        "id_contador": int(albaran.id_contador),
        "id_proveedor": conservar_id_proveedor(albaran.id_proveedor),
        "proveedor": albaran.proveedor.strip(),
        "numero_albaran": albaran.id_albaran.strip(),
        "fecha": albaran.fecha.date().isoformat() if isinstance(albaran.fecha, datetime) else _fecha(albaran.fecha),
        "importe_pvp": float(albaran.importe_pvp),
        "importe_puc": float(albaran.importe_puc),
        "descuento": float(albaran.dto),
        "estado": "PENDIENTE",
        "observaciones": None,
    }
    if con_recepcion:
        fila["id_recepcion"] = albaran.id_recepcion
    return fila


def valores_rpc(fila: dict[str, Any]) -> dict[str, Any]:
    """``p_valores`` de ``cf_resincronizar_albaran`` (importes en texto con 2 decimales)."""
    valores = {
        "id_proveedor": fila["id_proveedor"],
        "proveedor": fila["proveedor"],
        "numero_albaran": fila["numero_albaran"],
        "fecha": _fecha(fila["fecha"]),
        "importe_pvp": str(_dinero(fila["importe_pvp"])),
        "importe_puc": str(_dinero(fila["importe_puc"])),
        "descuento": str(_dinero(fila["descuento"])),
    }
    if "id_recepcion" in fila:
        valores["id_recepcion"] = fila["id_recepcion"]
    return valores


def diferencias(farmatic: dict[str, Any], supabase: dict[str, Any]) -> dict[str, list[str]]:
    """Campos distintos, por clase. ``id_recepcion`` solo si Supabase ya tiene la columna."""
    out: dict[str, list[str]] = {"identidad": [], "valores": [], "metadatos": []}
    if (farmatic["numero_albaran"] or "").strip() != (supabase.get("numero_albaran") or "").strip():
        out["identidad"].append("numero_albaran")
    if id_proveedor_comparable(farmatic["id_proveedor"]) != id_proveedor_comparable(supabase.get("id_proveedor")):
        out["identidad"].append("id_proveedor")
    if _fecha(farmatic["fecha"]) != _fecha(supabase.get("fecha")):
        out["valores"].append("fecha")
    for campo in ("importe_puc", "importe_pvp", "descuento"):
        if _dinero(farmatic[campo]) != _dinero(supabase.get(campo)):
            out["valores"].append(campo)
    if (farmatic["proveedor"] or "").strip() != (supabase.get("proveedor") or "").strip():
        out["valores"].append("proveedor")
    if "id_recepcion" in supabase and "id_recepcion" in farmatic:
        anterior = supabase.get("id_recepcion")
        if (None if anterior is None else int(anterior)) != farmatic["id_recepcion"]:
            out["metadatos"].append("id_recepcion")
    return out


@dataclass
class Plan:
    nuevos: list[dict[str, Any]] = field(default_factory=list)
    cambios: list[dict[str, Any]] = field(default_factory=list)
    reaparecidos: list[dict[str, Any]] = field(default_factory=list)
    ausentes: list[int] = field(default_factory=list)
    iguales: int = 0

    def resumen(self) -> dict[str, int]:
        return {"nuevos": len(self.nuevos), "cambios": len(self.cambios), "reaparecidos": len(self.reaparecidos),
                "ausentes": len(self.ausentes), "iguales": self.iguales}


def planificar(farmatic: Iterable[dict[str, Any]], supabase: Iterable[dict[str, Any]],
               ausentes_abiertos: set[int]) -> Plan:
    """Compara por ``id_contador`` (único en Farmatic y en Supabase por farmacia)."""
    f = {int(x["id_contador"]): x for x in farmatic}
    s = {int(x["id_contador"]): x for x in supabase}
    plan = Plan()
    for contador in sorted(f):
        fila = f[contador]
        if contador not in s:
            plan.nuevos.append(fila)
            continue
        dif = diferencias(fila, s[contador])
        if any(dif.values()):
            plan.cambios.append({"fila": fila, "supabase": s[contador], "diferencias": dif})
        elif contador in ausentes_abiertos:
            plan.reaparecidos.append({"fila": fila, "supabase": s[contador], "diferencias": dif})
        else:
            plan.iguales += 1
    plan.ausentes = sorted(c for c in s if c not in f and c not in ausentes_abiertos)
    return plan


def confirmar_ausentes(plan: Plan, encontrados: Iterable[dict[str, Any]],
                       supabase: Iterable[dict[str, Any]]) -> Plan:
    """Los 'ausentes' que Farmatic sí devuelve por IdContador (p. ej. fecha corregida fuera de
    la ventana) no están ausentes: pasan a cambios y la RPC decide."""
    s = {int(x["id_contador"]): x for x in supabase}
    vistos = {int(x["id_contador"]): x for x in encontrados}
    siguen = []
    for contador in plan.ausentes:
        if contador in vistos:
            fila = vistos[contador]
            plan.cambios.append({"fila": fila, "supabase": s[contador], "diferencias": diferencias(fila, s[contador])})
        else:
            siguen.append(contador)
    plan.ausentes = siguen
    return plan


# --------------------------------------------------------------------------- lecturas Supabase

def _paginado(consulta: Callable[[], Any]) -> list[dict[str, Any]]:
    """Todas las filas de una consulta ordenada (PostgREST corta cada respuesta)."""
    filas: list[dict[str, Any]] = []
    desde = 0
    while True:
        lote = consulta().range(desde, desde + PAGINA - 1).execute().data or []
        if not lote:
            return filas
        filas.extend(lote)
        desde += len(lote)


def leer_supabase(cliente, farmacia: str, desde: date, hasta: date | None, *, con_recepcion: bool) -> list[dict]:
    columnas = ",".join(COLUMNAS_SUPABASE + (("id_recepcion",) if con_recepcion else ()))

    def consulta():
        q = cliente.table("albaranes").select(columnas).eq("farmacia", farmacia).gte("fecha", desde.isoformat())
        if hasta is not None:
            q = q.lte("fecha", (hasta - timedelta(days=1)).isoformat())
        return q.order("id_contador")

    return _paginado(consulta)


def leer_ausentes_abiertos(cliente, farmacia: str) -> set[int]:
    """Albaranes cuyo último evento de presencia es AUSENTE (misma regla que la migración 22)."""
    filas = _paginado(lambda: cliente.table("albaranes_cambios").select("id,id_contador,valor_nuevo")
                      .eq("farmacia", farmacia).eq("campo", "presencia").order("id"))
    ultimo: dict[int, str] = {}
    for fila in filas:
        ultimo[int(fila["id_contador"])] = fila["valor_nuevo"]
    return {c for c, v in ultimo.items() if v == "AUSENTE"}


def leer_reservas(cliente, farmacia: str) -> dict[int, str]:
    """IdContador -> factura_id que lo reserva (solo para el informe; la RPC decide)."""
    filas = _paginado(lambda: cliente.table("conciliacion_albaranes_reservados")
                      .select("albaran_farmacia,albaran_id_contador,factura_id")
                      .eq("albaran_farmacia", farmacia).order("albaran_id_contador"))
    return {int(r["albaran_id_contador"]): str(r["factura_id"]) for r in filas}


def fecha_inicio_ventana(cliente, farmacia: str, hoy: date) -> date:
    """``hoy − 180`` días, ampliada a ±15 días de los albaranes de facturas no conciliadas."""
    inicio = hoy - timedelta(days=VENTANA_DIAS)
    facturas = _paginado(lambda: cliente.table("facturas").select("id,farmacia,estado_conciliacion_cf")
                         .eq("farmacia", farmacia).order("id"))
    abiertas = {str(f["id"]) for f in facturas if f.get("estado_conciliacion_cf") in ESTADOS_FACTURA_ABIERTOS}
    if not abiertas:
        return inicio
    extraidos = _paginado(lambda: cliente.table("facturas_albaranes_extraidos")
                          .select("id,factura_id,fecha_albaran").order("id"))
    fechas = [date.fromisoformat(str(e["fecha_albaran"])[:10]) for e in extraidos
              if str(e["factura_id"]) in abiertas and e.get("fecha_albaran")]
    if fechas:
        inicio = min(inicio, min(fechas) - timedelta(days=MARGEN_FACTURAS_DIAS))
    return inicio


# --------------------------------------------------------------------------- escritura

def _insertar(cliente, fila: dict[str, Any]) -> bool:
    try:
        return bool(cliente.table("albaranes").insert(fila).execute().data)
    except APIError as error:
        if error.code == "23505":
            return False
        raise


def ejecutar_plan(cliente, plan: Plan, farmacia: str, *, origen: str, ejecucion_id: str,
                  registrar: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """Aplica el plan. Un error en un albarán se registra y no detiene los demás."""
    resumen: dict[str, Any] = {"insertados": 0, "ya_existentes": 0, "actualizados": 0, "revisiones": 0,
                               "sin_cambios": 0, "ausentes_registrados": 0, "ausentes_ya_registrados": 0,
                               "errores": []}
    for fila in plan.nuevos:
        try:
            if _insertar(cliente, fila):
                resumen["insertados"] += 1
            else:
                resumen["ya_existentes"] += 1
        except Exception as exc:  # noqa: BLE001 - se informa y se sigue
            resumen["errores"].append({"id_contador": fila["id_contador"], "paso": "insert", "error": str(exc)})
    for item in plan.cambios + plan.reaparecidos:
        fila = item["fila"]
        try:
            respuesta = cliente.rpc("cf_resincronizar_albaran", {
                "p_farmacia": farmacia, "p_id_contador": int(fila["id_contador"]), "p_valores": valores_rpc(fila),
                "p_origen": origen, "p_ejecucion_id": ejecucion_id}).execute().data or {}
            accion = respuesta.get("accion")
            clave = {"ACTUALIZADO": "actualizados", "REVISION": "revisiones"}.get(accion, "sin_cambios")
            resumen[clave] += 1
            if accion == "REVISION":
                registrar(f"Albarán en revisión | IdContador: {fila['id_contador']} | "
                          f"Motivo: {respuesta.get('motivo')}")
        except Exception as exc:  # noqa: BLE001
            resumen["errores"].append({"id_contador": fila["id_contador"], "paso": "resincronizar", "error": str(exc)})
    for contador in plan.ausentes:
        try:
            respuesta = cliente.rpc("cf_registrar_albaran_ausente", {
                "p_farmacia": farmacia, "p_id_contador": int(contador), "p_origen": origen,
                "p_ejecucion_id": ejecucion_id}).execute().data or {}
            if respuesta.get("accion") == "REVISION":
                resumen["ausentes_registrados"] += 1
                registrar(f"Albarán ausente en Farmatic | IdContador: {contador} | "
                          f"Reservado por: {respuesta.get('reservado_por')}")
            else:
                resumen["ausentes_ya_registrados"] += 1
        except Exception as exc:  # noqa: BLE001
            resumen["errores"].append({"id_contador": contador, "paso": "ausente", "error": str(exc)})
    return resumen


def nueva_ejecucion_id(prefijo: str) -> str:
    return f"{prefijo}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}:{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------- informe

def informe(plan: Plan, reservas: dict[int, str], *, desde: date, hasta: date | None,
            esquema_22: bool) -> dict[str, Any]:
    """Lo que haría la escritura, sin escribir nada. La decisión final es de la RPC."""
    def prevision(item):
        dif = item["diferencias"]
        if dif["identidad"]:
            return "REVISION:CAMBIO_IDENTIDAD"
        if dif["valores"] and int(item["fila"]["id_contador"]) in reservas:
            return "REVISION:RESERVADO"
        return "ACTUALIZAR" if (dif["valores"] or dif["metadatos"]) else "CERRAR_REVISION"

    def detalle(item):
        fila, sup = item["fila"], item["supabase"]
        campos = item["diferencias"]["identidad"] + item["diferencias"]["valores"] + item["diferencias"]["metadatos"]
        return {"id_contador": fila["id_contador"], "numero_albaran": fila["numero_albaran"],
                "prevision": prevision(item),
                "reservado_por_factura": reservas.get(int(fila["id_contador"])),
                "campos": {c: [sup.get(c), fila.get(c)] for c in campos}}

    detalles = [detalle(i) for i in plan.cambios + plan.reaparecidos]
    previsiones: dict[str, int] = {}
    for d in detalles:
        previsiones[d["prevision"]] = previsiones.get(d["prevision"], 0) + 1
    return {
        "ventana": {"desde": desde.isoformat(), "hasta": hasta.isoformat() if hasta else None},
        "esquema_22": esquema_22,
        "resumen": plan.resumen(),
        "previsiones": previsiones,
        "cambios": detalles,
        "nuevos": [{"id_contador": f["id_contador"], "numero_albaran": f["numero_albaran"], "fecha": f["fecha"]}
                   for f in plan.nuevos],
        "ausentes": [{"id_contador": c, "reservado_por_factura": reservas.get(c)} for c in plan.ausentes],
    }


def ruta_fuera_del_repositorio(ruta: str, raiz: Path) -> Path:
    destino = Path(ruta).resolve()
    if destino == raiz or raiz in destino.parents:
        raise SystemExit(f"SALIDA_DENTRO_DEL_REPOSITORIO: {destino}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    return destino
