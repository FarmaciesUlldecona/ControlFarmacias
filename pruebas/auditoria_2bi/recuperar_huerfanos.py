"""Hito 2BI: informe y recuperacion de UN claim huerfano de normalizacion (migracion 25).

Uso (identidad Usuari; Supabase con la clave del .env; sin Farmatic):
  python -B pruebas/auditoria_2bi/recuperar_huerfanos.py informe <salida.json>
  python -B pruebas/auditoria_2bi/recuperar_huerfanos.py recuperar <documento_id> <salida.json>

``informe`` no escribe: llama a ``cf_huerfanos_normalizacion`` (funcion STABLE, solo lectura) y lista los
documentos en NORMALIZANDO con su prevision (``LOCK_VIGENTE``, ``RECUPERABLE`` o ``REVISION``) y sus senales.
``recuperar`` requiere la migracion 25, confirmacion expresa de Pio en chat, configuracion f|f|f|{PIO}, que el
documento figure en el informe como ``RECUPERABLE`` o ``REVISION`` y que no exista su guard (se crea en
exclusiva antes de escribir y no se borra). Una sola llamada a ``cf_recuperar_claim_huerfano_normalizacion``,
que decide en una transaccion; sin reintentos. Gracia aprobada por Pio: 30 minutos. Salidas fuera del
repositorio.
"""
from __future__ import annotations

import getpass
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.supabase_client import resincronizacion_albaranes as resync  # noqa: E402
from src.supabase_client.conexion_supabase import obtener_cliente_supabase  # noqa: E402

GRACIA = "30 minutes"
PREVISIONES_EJECUTABLES = ("RECUPERABLE", "REVISION")  # de cf_huerfanos_normalizacion
RESULTADOS_OK = ("RECUPERADO", "REVISION")  # de cf_recuperar_claim_huerfano_normalizacion


def _configuracion_segura(cliente) -> bool:
    filas = (cliente.table("cf_configuracion")
             .select("normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas")
             .execute().data or [])
    if len(filas) != 1:  # cf_configuracion es de fila unica
        return False
    fila = filas[0]
    return (fila["normalizacion_automatica"] is False and fila["conciliacion_automatica"] is False
            and fila["luna_habilitada"] is False and list(fila["farmacias_habilitadas"]) == ["PIO"])


def informe(cliente) -> list[dict]:
    return cliente.rpc("cf_huerfanos_normalizacion", {"p_gracia": GRACIA}).execute().data or []


def main(modo: str, argumentos: list[str], salida: Path) -> int:
    cliente = obtener_cliente_supabase()
    registro: dict = {"hito": "2BI", "modo": modo, "argumentos": argumentos, "gracia": GRACIA,
                      "inicio_utc": datetime.now(timezone.utc).isoformat()}

    def guardar() -> None:
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    if modo == "informe":
        registro["huerfanos"] = informe(cliente)
        registro["resultado"] = "INFORME_SIN_ESCRITURA"
        guardar()
        print(json.dumps({k: registro[k] for k in ("resultado", "huerfanos")}, ensure_ascii=False, indent=1,
                         default=str))
        return 0

    if modo != "recuperar":
        raise SystemExit("modo desconocido")
    documento_id = argumentos[0]
    if not _configuracion_segura(cliente):
        registro["resultado"] = "NO_EJECUTADO_CONFIGURACION_INESPERADA"
        guardar()
        raise SystemExit("CONFIGURACION_INESPERADA")
    guard = salida.parent / f"recuperar_huerfano_{documento_id}.guard"
    if guard.exists():
        registro["resultado"] = "NO_EJECUTADO_GUARD_EXISTENTE"
        guardar()
        raise SystemExit(f"GUARD_EXISTENTE: {guard}")
    candidatos = [h for h in informe(cliente) if h["documento_id"] == documento_id]  # sin la 25 falla aqui
    registro["prevision"] = candidatos
    if len(candidatos) != 1 or candidatos[0]["prevision"] not in PREVISIONES_EJECUTABLES:
        registro["resultado"] = "NO_EJECUTADO_NO_ES_CANDIDATO"
        guardar()
        raise SystemExit("NO_ES_CANDIDATO")
    with open(guard, "x", encoding="utf-8") as g:  # exclusivo: una sola ejecucion por documento
        g.write(f"{datetime.now(timezone.utc).isoformat()} documento {documento_id}\n")
    try:
        registro["respuesta"] = cliente.rpc("cf_recuperar_claim_huerfano_normalizacion", {
            "p_documento_id": documento_id, "p_actor": getpass.getuser(), "p_gracia": GRACIA}).execute().data
        registro["resultado"] = registro["respuesta"]["resultado"]
    except BaseException as exc:  # sin reintento
        registro["resultado"] = "EXCEPCION"
        registro["excepcion"] = f"{type(exc).__name__}: {exc}"
    finally:
        registro["fin_utc"] = datetime.now(timezone.utc).isoformat()
        guardar()
    print(json.dumps({k: registro.get(k) for k in ("resultado", "respuesta", "excepcion")}, ensure_ascii=False,
                     indent=1, default=str))
    return 0 if registro["resultado"] in RESULTADOS_OK else 3


if __name__ == "__main__":
    modo, *resto = sys.argv[1:]
    sys.exit(main(modo, resto[:-1], resync.ruta_fuera_del_repositorio(resto[-1], ROOT)))
