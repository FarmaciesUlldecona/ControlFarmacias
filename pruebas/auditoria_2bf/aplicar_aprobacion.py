"""Hito 2BF: registrar y aplicar UNA aprobación de Pio de un cambio de identidad de albarán.

Uso (Supabase con service_role del .env). ``informe`` y ``aplicar`` leen Farmatic: SOLO con la identidad
ControlFarmaciasRO. ``registrar`` no lee ni importa Farmatic: se ejecuta con Usuari, para que
``registrado_por`` sea quien registra.
  python -B pruebas/auditoria_2bf/aplicar_aprobacion.py informe <id_contador> <salida.json>
  python -B pruebas/auditoria_2bf/aplicar_aprobacion.py registrar <aprobacion.json> <salida.json>
  python -B pruebas/auditoria_2bf/aplicar_aprobacion.py aplicar <aprobacion_id> <salida.json>

``informe`` no escribe en ninguna base de datos (su previsión es orientativa; decide la RPC).
``registrar`` solo escribe la aprobación (RPC ``cf_registrar_aprobacion_albaran``). ``aplicar``
relee la cabecera actual de Farmatic por IdContador y llama una vez a
``cf_aplicar_aprobacion_albaran``, que aplica solo si el cambio detectado coincide exactamente con
lo aprobado y el albarán no está reservado. ``registrar`` y ``aplicar`` requieren la migración 23,
confirmación expresa de Pio en chat y configuración f|f|f|{PIO}; ``aplicar`` además que no exista
el guard de esa aprobación (se crea en exclusiva antes de escribir y no se borra). Sin reintentos.
Salidas fuera del repositorio.
"""
from __future__ import annotations

import getpass
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from config.config import NOMBRE_FARMACIA  # noqa: E402
from src.supabase_client import resincronizacion_albaranes as resync  # noqa: E402
from src.supabase_client.conexion_supabase import obtener_cliente_supabase  # noqa: E402

CLAVES_APROBACION = {"farmacia", "id_contador", "cambio", "aprobado_por", "aprobado_at", "referencia"}


def obtener_albaranes_por_contadores(contadores: list[int]):
    """Lectura de Farmatic (solo ControlFarmaciasRO). Import diferido: ``registrar`` no carga Farmatic."""
    from src.database.leer_albaranes import obtener_albaranes_por_contadores as leer
    return leer(contadores)


def _configuracion_segura(cliente) -> bool:
    filas = (cliente.table("cf_configuracion")
             .select("normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas")
             .execute().data or [])
    if len(filas) != 1:  # cf_configuracion es de fila única
        return False
    fila = filas[0]
    return (fila["normalizacion_automatica"] is False and fila["conciliacion_automatica"] is False
            and fila["luna_habilitada"] is False and list(fila["farmacias_habilitadas"]) == ["PIO"])


def _farmatic(id_contador: int) -> dict | None:
    """Cabecera actual de Farmatic (solo lectura), en el formato de la resincronización."""
    leidos = [resync.payload_albaran(a, NOMBRE_FARMACIA, con_recepcion=True)
              for a in obtener_albaranes_por_contadores([id_contador])]
    return leidos[0] if len(leidos) == 1 else None


def _comparable(campo: str, valor: str | None) -> str | None:
    if campo == "id_proveedor":
        return resync.id_proveedor_comparable(valor)
    return None if valor is None else valor.strip()


def _conjunto(cambio: list[dict]) -> list[tuple]:
    return sorted((c["campo"], _comparable(c["campo"], c["anterior"]), _comparable(c["campo"], c["nuevo"]))
                  for c in cambio)


def _pendientes(cambios: list[dict], aplicadas: list[dict]) -> list[dict]:
    """Revisiones CAMBIO_IDENTIDAD pendientes (misma regla que cf_revision_albaran_pendiente)."""
    resueltas = {int(i) for a in aplicadas for i in (a.get("revisiones_resueltas") or [])}
    out = []
    for c in cambios:
        if c["accion"] != "REVISION" or c["motivo"] != "CAMBIO_IDENTIDAD" or int(c["id"]) in resueltas:
            continue
        if any(u["campo"] == c["campo"] and u["accion"] == "ACTUALIZADO" and int(u["id"]) > int(c["id"])
               for u in cambios):
            continue
        out.append(c)
    return out


def informe(cliente, id_contador: int) -> dict:
    def filas(tabla, columnas):
        return (cliente.table(tabla).select(columnas).eq("farmacia", NOMBRE_FARMACIA)
                .eq("id_contador", str(id_contador)).order("id" if tabla != "albaranes" else "id_contador")
                .execute().data or [])

    supabase = filas("albaranes", ",".join(resync.COLUMNAS_SUPABASE + ("id_recepcion",)))
    cambios = filas("albaranes_cambios", "id,campo,valor_anterior,valor_nuevo,accion,motivo,origen,detectado_at")
    aprobaciones = filas("albaranes_aprobaciones", "id,cambio,aprobado_por,aprobado_at,referencia,registrado_at")
    aplicadas = (cliente.table("albaranes_aprobaciones_aplicadas").select("aprobacion_id,revisiones_resueltas")
                 .eq("farmacia", NOMBRE_FARMACIA).eq("id_contador", str(id_contador)).order("aprobacion_id")
                 .execute().data or [])
    reserva = resync.leer_reservas(cliente, NOMBRE_FARMACIA).get(id_contador)
    farmatic = _farmatic(id_contador)
    pendientes = [{"campo": c["campo"], "anterior": c["valor_anterior"], "nuevo": c["valor_nuevo"]}
                  for c in _pendientes(cambios, aplicadas)]
    detectado = []
    if supabase and farmatic:
        dif = resync.diferencias(farmatic, supabase[0])
        detectado = [{"campo": c, "anterior": supabase[0].get(c), "nuevo": farmatic[c]} for c in dif["identidad"]]
    aplicadas_ids = {int(a["aprobacion_id"]) for a in aplicadas}

    def prevision(aprobacion) -> str:
        if int(aprobacion["id"]) in aplicadas_ids:
            return "YA_APLICADA"
        if not supabase or farmatic is None:
            return "ALBARAN_NO_ENCONTRADO"
        if reserva is not None:
            return "NO_APLICADA:RESERVADO"
        if (not detectado or _conjunto(aprobacion["cambio"]) != _conjunto(detectado)
                or not set(_conjunto(detectado)) <= set(_conjunto(pendientes))):
            return "NO_APLICADA:CAMBIO_NO_COINCIDE"
        return "APLICABLE"

    return {"id_contador": id_contador, "supabase": supabase[0] if supabase else None, "farmatic": farmatic,
            "reservado_por_factura": reserva, "revisiones": cambios, "pendientes": pendientes,
            "detectado_ahora": detectado,
            "aprobaciones": [{**a, "prevision": prevision(a)} for a in aprobaciones]}


def _leer_aprobacion(ruta: Path) -> dict:
    aprobacion = json.loads(ruta.read_text(encoding="utf-8"))
    if set(aprobacion) != CLAVES_APROBACION or aprobacion["farmacia"] != NOMBRE_FARMACIA:
        raise SystemExit("APROBACION_JSON_INVALIDA")
    return aprobacion


def main(modo: str, argumento: str, salida: Path) -> int:
    cliente = obtener_cliente_supabase()
    registro: dict = {"hito": "2BF", "modo": modo, "farmacia": NOMBRE_FARMACIA, "argumento": argumento,
                      "inicio_utc": datetime.now(timezone.utc).isoformat()}

    def guardar() -> None:
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    if modo == "informe":
        registro.update(informe(cliente, int(argumento)))
        registro["resultado"] = "INFORME_SIN_ESCRITURA"
        guardar()
        print(json.dumps({k: registro[k] for k in ("resultado", "pendientes", "detectado_ahora",
                                                   "reservado_por_factura")}, ensure_ascii=False, indent=1))
        print(json.dumps([{k: a[k] for k in ("id", "prevision")} for a in registro["aprobaciones"]], indent=1))
        return 0

    if modo not in ("registrar", "aplicar"):
        raise SystemExit("modo desconocido")
    if not _configuracion_segura(cliente):
        registro["resultado"] = "NO_EJECUTADO_CONFIGURACION_INESPERADA"
        guardar()
        raise SystemExit("CONFIGURACION_INESPERADA")

    if modo == "registrar":
        aprobacion = _leer_aprobacion(Path(argumento))
        registro["aprobacion"] = aprobacion
        registro["respuesta"] = cliente.rpc("cf_registrar_aprobacion_albaran", {
            "p_farmacia": aprobacion["farmacia"], "p_id_contador": int(aprobacion["id_contador"]),
            "p_cambio": aprobacion["cambio"], "p_aprobado_por": aprobacion["aprobado_por"],
            "p_aprobado_at": aprobacion["aprobado_at"], "p_referencia": aprobacion["referencia"],
            "p_registrado_por": getpass.getuser()}).execute().data
        registro["resultado"] = registro["respuesta"]["accion"]
        guardar()
        print(json.dumps(registro["respuesta"], ensure_ascii=False, indent=1))
        return 0

    aprobacion_id = int(argumento)
    guard = salida.parent / f"aplicar_aprobacion_{aprobacion_id}.guard"
    if guard.exists():
        registro["resultado"] = "NO_EJECUTADO_GUARD_EXISTENTE"
        guardar()
        raise SystemExit(f"GUARD_EXISTENTE: {guard}")
    [aprobacion] = (cliente.table("albaranes_aprobaciones").select("id,farmacia,id_contador,cambio")
                    .eq("id", str(aprobacion_id)).execute().data or [None])  # sin la 23 falla aquí, sin escribir
    if aprobacion is None or aprobacion["farmacia"] != NOMBRE_FARMACIA:
        registro["resultado"] = "NO_EJECUTADO_APROBACION_NO_ENCONTRADA"
        guardar()
        raise SystemExit("APROBACION_NO_ENCONTRADA")
    farmatic = _farmatic(int(aprobacion["id_contador"]))
    if farmatic is None:
        registro["resultado"] = "NO_EJECUTADO_ALBARAN_NO_ENCONTRADO_EN_FARMATIC"
        guardar()
        raise SystemExit("ALBARAN_NO_ENCONTRADO_EN_FARMATIC")
    registro.update({"aprobacion": aprobacion, "farmatic": farmatic})
    with open(guard, "x", encoding="utf-8") as g:  # exclusivo: una sola ejecución por aprobación
        g.write(f"{datetime.now(timezone.utc).isoformat()} aprobacion {aprobacion_id}\n")
    try:
        registro["respuesta"] = cliente.rpc("cf_aplicar_aprobacion_albaran", {
            "p_aprobacion_id": aprobacion_id, "p_valores": resync.valores_rpc(farmatic),
            "p_ejecucion_id": resync.nueva_ejecucion_id("aprobacion-2bf")}).execute().data
        registro["resultado"] = registro["respuesta"]["accion"]
    except BaseException as exc:  # sin reintento
        registro["resultado"] = "EXCEPCION"
        registro["excepcion"] = f"{type(exc).__name__}: {exc}"
    finally:
        registro["fin_utc"] = datetime.now(timezone.utc).isoformat()
        guardar()
    print(json.dumps({k: registro.get(k) for k in ("resultado", "respuesta", "excepcion")}, ensure_ascii=False,
                     indent=1, default=str))
    return 0 if registro["resultado"] == "APLICADA" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], resync.ruta_fuera_del_repositorio(sys.argv[3], ROOT)))
