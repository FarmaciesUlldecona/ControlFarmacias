"""Hito 2BD: carga única de albaranes anteriores a 2026-06-01 (rango [2026-04-01, 2026-06-01)).

Uso (Farmatic SOLO con la identidad ControlFarmaciasRO; Supabase con service_role del .env):
  python -B pruebas/auditoria_2bd/carga_historica.py informe <salida.json>
  python -B pruebas/auditoria_2bd/carga_historica.py ejecutar <salida.json>

Mismas reglas que la resincronización nocturna (``src/supabase_client/resincronizacion_albaranes``):
- albarán del rango que no está en Supabase -> ``insert`` (con su recepción);
- ya presente y distinto -> RPC ``cf_resincronizar_albaran`` (origen CARGA_HISTORICA): actualizar o
  revisión (reserva R15 / cambio de identidad), decidido en la base de datos;
- presente en Supabase y ausente en Farmatic (confirmado por IdContador) -> revisión
  ``AUSENTE_EN_FARMATIC``; nunca se borra.
``informe`` no escribe en ninguna base de datos. ``ejecutar`` requiere la migración 22, confirmación
expresa de Pio en chat, configuración f|f|f|{PIO} y que no exista el guard de ejecución única (se
crea en exclusiva antes de escribir y no se borra). Sin reintentos. Salidas fuera del repositorio.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from config.config import NOMBRE_FARMACIA  # noqa: E402
from src.database.leer_albaranes import (  # noqa: E402
    obtener_albaranes_entre_fechas, obtener_albaranes_por_contadores)
from src.supabase_client import resincronizacion_albaranes as resync  # noqa: E402
from src.supabase_client.conexion_supabase import obtener_cliente_supabase  # noqa: E402

DESDE = date(2026, 4, 1)
HASTA = date(2026, 6, 1)
NOMBRE_GUARD = "carga_historica_2bd.guard"


def preparar(cliente, *, tolerar_sin_22: bool) -> dict:
    farmatic = [resync.payload_albaran(a, NOMBRE_FARMACIA, con_recepcion=True)
                for a in obtener_albaranes_entre_fechas(DESDE, HASTA)]
    esquema_22 = True
    try:
        supabase = resync.leer_supabase(cliente, NOMBRE_FARMACIA, DESDE, HASTA, con_recepcion=True)
        ausentes_abiertos = resync.leer_ausentes_abiertos(cliente, NOMBRE_FARMACIA)
    except Exception:
        if not tolerar_sin_22:
            raise
        esquema_22 = False
        supabase = resync.leer_supabase(cliente, NOMBRE_FARMACIA, DESDE, HASTA, con_recepcion=False)
        ausentes_abiertos = set()
        for fila in farmatic:
            fila.pop("id_recepcion", None)
    plan = resync.planificar(farmatic, supabase, ausentes_abiertos)
    if plan.ausentes:
        encontrados = [resync.payload_albaran(a, NOMBRE_FARMACIA, con_recepcion=esquema_22)
                       for a in obtener_albaranes_por_contadores(plan.ausentes)]
        plan = resync.confirmar_ausentes(plan, encontrados, supabase)
    return {"plan": plan, "esquema_22": esquema_22, "leidos_farmatic": len(farmatic),
            "en_supabase": len(supabase)}


def _configuracion_segura(cliente) -> bool:
    filas = (cliente.table("cf_configuracion")
             .select("normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas")
             .execute().data or [])
    if len(filas) != 1:  # cf_configuracion es de fila única
        return False
    fila = filas[0]
    return (fila["normalizacion_automatica"] is False and fila["conciliacion_automatica"] is False
            and fila["luna_habilitada"] is False and list(fila["farmacias_habilitadas"]) == ["PIO"])


def main(modo: str, salida: Path) -> int:
    cliente = obtener_cliente_supabase()
    registro: dict = {"hito": "2BD", "modo": modo, "farmacia": NOMBRE_FARMACIA,
                      "rango": [DESDE.isoformat(), HASTA.isoformat()],
                      "inicio_utc": datetime.now(timezone.utc).isoformat()}

    def guardar() -> None:
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    if modo == "informe":
        datos = preparar(cliente, tolerar_sin_22=True)
        try:
            reservas = resync.leer_reservas(cliente, NOMBRE_FARMACIA)
        except Exception:
            reservas = {}
        registro.update(resync.informe(datos["plan"], reservas, desde=DESDE, hasta=HASTA,
                                       esquema_22=datos["esquema_22"]))
        registro.update({k: datos[k] for k in ("leidos_farmatic", "en_supabase")})
        registro["resultado"] = "INFORME_SIN_ESCRITURA"
        guardar()
        print(json.dumps({k: registro[k] for k in ("resultado", "resumen", "previsiones", "leidos_farmatic",
                                                   "en_supabase", "esquema_22")}, ensure_ascii=False, indent=1))
        return 0

    if modo != "ejecutar":
        raise SystemExit("modo desconocido")
    guard = salida.parent / NOMBRE_GUARD
    if guard.exists():
        registro["resultado"] = "NO_EJECUTADO_GUARD_EXISTENTE"
        guardar()
        raise SystemExit(f"GUARD_EXISTENTE: {guard}")
    if not _configuracion_segura(cliente):
        registro["resultado"] = "NO_EJECUTADO_CONFIGURACION_INESPERADA"
        guardar()
        raise SystemExit("CONFIGURACION_INESPERADA")
    datos = preparar(cliente, tolerar_sin_22=False)  # sin la 22 falla aquí, sin escribir
    registro["plan"] = datos["plan"].resumen()
    registro.update({k: datos[k] for k in ("leidos_farmatic", "en_supabase")})
    with open(guard, "x", encoding="utf-8") as g:  # exclusivo: una sola ejecución
        g.write(f"{datetime.now(timezone.utc).isoformat()} {DESDE}..{HASTA}\n")
    try:
        registro["resumen"] = resync.ejecutar_plan(
            cliente, datos["plan"], NOMBRE_FARMACIA, origen=resync.ORIGEN_CARGA,
            ejecucion_id=resync.nueva_ejecucion_id("carga-2bd"))
        registro["resultado"] = "CON_ERRORES" if registro["resumen"]["errores"] else "COMPLETADA"
    except BaseException as exc:  # sin reintento
        registro["resultado"] = "EXCEPCION"
        registro["excepcion"] = f"{type(exc).__name__}: {exc}"
    finally:
        registro["fin_utc"] = datetime.now(timezone.utc).isoformat()
        guardar()
    print(json.dumps({k: registro.get(k) for k in ("resultado", "plan", "resumen")}, ensure_ascii=False,
                     indent=1, default=str))
    return 0 if registro["resultado"] == "COMPLETADA" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], resync.ruta_fuera_del_repositorio(sys.argv[2], ROOT)))
