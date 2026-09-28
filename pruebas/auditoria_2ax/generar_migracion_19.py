"""Hito 2AX: genera la migracion 19 y su rollback desde el inventario productivo READ_ONLY.

Uso: python pruebas/auditoria_2ax/generar_migracion_19.py <inventario_pre_2ax.json>

La 19 aplica P1 (tablas, vistas y secuencias de public sin privilegios para
PUBLIC, anon y authenticated; service_role solo con lo que usa el codigo),
P2 (cf_validar_factura y cf_desvalidar_factura sin EXECUTE salvo el propietario)
y P3 (privilegios por defecto de postgres cerrados). El rollback restaura
EXACTAMENTE la matriz y los privilegios por defecto inventariados.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
ROLES = ("PUBLIC", "anon", "authenticated", "service_role")
FUNCIONES_P2 = ("cf_validar_factura(uuid,text)", "cf_desvalidar_factura(uuid,text)")

# Uso real por el codigo Python con la clave service_role (via PostgREST). Todas
# las escrituras de negocio pasan por RPC SECURITY DEFINER.
USO_SERVICE_ROLE = {
    "documentos_facturas": ("SELECT", "INSERT"),  # importar_facturas_drive.py:519,833; compositor_manual.py:89
    "albaranes": ("SELECT", "INSERT"),            # guardar_albaranes.py:18,51; repositorios.py:391
    "facturas": ("SELECT",),                      # repositorios.py (construir_detalles, guardar_conciliacion)
    "cf_configuracion": ("SELECT",),              # repositorios.py:108 (obtener_configuracion)
    "proveedores": ("SELECT",),                   # repositorios.py (construir_detalles)
    "facturas_movimientos": ("SELECT",),          # repositorios.py (construir_detalles)
    "facturas_albaranes_extraidos": ("SELECT",),  # repositorios.py (construir_detalles)
    "normalizacion_ejecuciones": ("SELECT",),     # repositorios.py (guardar_conciliacion, revalidacion)
}


def _firma_sql(firma: str) -> str:
    nombre, args = firma.split("(", 1)
    return f"public.{nombre}({args.rstrip(')').replace(',', ', ')})"


def _destinatario(rol: str) -> str:
    return "public" if rol == "PUBLIC" else rol


def generar(inventario: dict) -> tuple[str, str]:
    matriz = inventario["matriz"]
    relaciones = sorted(k for k in matriz if k.split(":", 1)[0] in ("tabla", "vista", "secuencia", "vista_materializada"))
    faltan = set(USO_SERVICE_ROLE) - {k.split(":", 1)[1] for k in relaciones if k.startswith("tabla:")}
    assert not faltan, faltan

    m = [
        "-- Migracion 19 (Hito 2AX): privilegios minimos. Generada por",
        "-- pruebas/auditoria_2ax/generar_migracion_19.py desde el inventario productivo READ_ONLY.",
        "-- P1: tablas, vistas y secuencias de public sin privilegios para PUBLIC, anon y",
        "--     authenticated; service_role solo con lo que usa el codigo. RLS no cambia.",
        "-- P2: cf_validar_factura y cf_desvalidar_factura solo para el propietario.",
        "-- P3: privilegios por defecto de postgres cerrados para PUBLIC, anon y authenticated.",
        "-- No toca funciones de trigger, cf_resultado_conciliacion, rls_auto_enable,",
        "-- politicas ni otros esquemas. Idempotente. Sin DML.",
        "begin;",
        "",
        "-- P1",
    ]
    for clave in relaciones:
        tipo, nombre = clave.split(":", 1)
        objeto = "sequence" if tipo == "secuencia" else "table"
        m.append(f"revoke all on {objeto} public.{nombre} from public, anon, authenticated, service_role;")
    m.append("")
    for tabla, privilegios in USO_SERVICE_ROLE.items():
        m.append(f"grant {', '.join(p.lower() for p in privilegios)} on table public.{tabla} to service_role;")
    m += ["", "-- P2"]
    for firma in FUNCIONES_P2:
        m.append(f"revoke all on function {_firma_sql(firma)} from public, anon, authenticated, service_role;")
    m += [
        "",
        "-- P3: por esquema (anon y authenticated) y global para PUBLIC en funciones:",
        "-- un REVOKE por esquema no puede quitar el EXECUTE a PUBLIC incorporado por defecto.",
        "alter default privileges for role postgres in schema public",
        "    revoke all on tables from public, anon, authenticated;",
        "alter default privileges for role postgres in schema public",
        "    revoke all on sequences from public, anon, authenticated;",
        "alter default privileges for role postgres in schema public",
        "    revoke all on functions from public, anon, authenticated;",
        "alter default privileges for role postgres",
        "    revoke execute on functions from public;",
        "",
        "commit;",
        "",
    ]

    r = [
        "-- Rollback de la migracion 19 (Hito 2AX). Restaura EXACTAMENTE la matriz de",
        "-- privilegios y los privilegios por defecto de postgres inventariados en",
        f"-- produccion ({inventario.get('capturado_utc', 'n/d')}). Generado por",
        "-- pruebas/auditoria_2ax/generar_migracion_19.py. Sin DML.",
        "begin;",
        "",
    ]
    for clave in relaciones + [f"funcion:{f}" for f in FUNCIONES_P2]:
        tipo, nombre = clave.split(":", 1)
        objeto = {"secuencia": "sequence", "funcion": "function"}.get(tipo, "table")
        ref = _firma_sql(nombre) if tipo == "funcion" else f"public.{nombre}"
        r.append(f"revoke all on {objeto} {ref} from public, anon, authenticated, service_role;")
        for rol in ROLES:
            privilegios = matriz[clave]["privilegios"][rol]
            if privilegios:
                r.append(f"grant {', '.join(p.lower() for p in privilegios)} on {objeto} {ref} to {_destinatario(rol)};")
    postgres = [d for d in inventario["default_acl"] if d["rol"] == "postgres" and d["esquema"] == "public"]
    tipos = {"r": ("tables", "select, insert, update, delete, truncate, references, trigger, maintain"),
             "S": ("sequences", "select, update, usage"),
             "f": ("functions", "execute")}
    r += ["", "-- Privilegios por defecto de postgres en public (inventario 1.2)."]
    for d in sorted(postgres, key=lambda x: x["tipo"]):
        clase, todos = tipos[d["tipo"]]
        grantees = [e.split("=")[0] for e in d["acl"].strip("{}").split(",")]
        for g in grantees:
            r.append(f"alter default privileges for role postgres in schema public grant {todos} on {clase} to {g};")
    globales = [d for d in inventario["default_acl"] if d["rol"] == "postgres" and d["esquema"] == "*"]
    assert not globales, "privilegios por defecto globales de postgres no previstos"
    r += [
        "-- Sin privilegios por defecto globales de postgres en el inventario: se restaura el",
        "-- EXECUTE a PUBLIC incorporado por defecto (elimina la entrada global de la 19).",
        "alter default privileges for role postgres grant execute on functions to public;",
        "",
        "commit;",
        "",
    ]
    return "\n".join(m), "\n".join(r)


if __name__ == "__main__":
    inventario = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    migracion, rollback = generar(inventario)
    (MIG / "19_cf_privilegios_minimos.sql").write_bytes(migracion.encode("utf-8"))
    (MIG / "19_cf_privilegios_minimos.rollback.sql").write_bytes(rollback.encode("utf-8"))
    print("generadas", len(migracion), len(rollback))
