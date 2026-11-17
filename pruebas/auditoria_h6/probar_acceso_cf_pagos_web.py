"""Hito H6-D: prueba de acceso del rol de escritura de la web cf_pagos_web por el pooler de Supabase.

Uso (terminal de Pio; la contrasena SOLO en la variable de entorno CF_PAGOS_PASSWORD, nunca como argumento ni
impresa):
  python -B pruebas/auditoria_h6/probar_acceso_cf_pagos_web.py <host_pooler> <puerto_pooler>

Usuario fijo ``cf_pagos_web.<project_ref>``. Patron de pruebas/auditoria_trab/probar_acceso_cf_trabajadores_web.py.
Comprueba:
- conecta (TLS) como cf_pagos_web;
- lee sus tres tablas (conteos);
- escribe en sus tablas: un INSERT de prueba en proveedores_forma_pago CON autor (CIF ficticio ZZPRUEBA...) y su
  anulacion funcionan y dejan dos filas de historial con ese autor; la transaccion se DESHACE siempre (rollback) y
  despues se comprueba que no queda ni la fila ni su historial;
- una marca sobre una factura inexistente falla (FACTURA_NO_ENCONTRADA: el trigger valida contra facturas sin que la
  web pueda leerlas);
- el INSERT SIN autor falla (AUTOR_AUSENTE);
- un DELETE en sus tablas falla (42501);
- leer facturas y facturas_vencimientos, escribir en ellas y escribir en pagos_historial fallan (42501).
Cada intento va en su propia transaccion READ WRITE que se deshace SIEMPRE. Efecto residual conocido: el INSERT con
autor consume valores de la secuencia del historial (las secuencias no se deshacen); no deja filas. Sin salidas en
disco. Codigo 0 = todo OK; 3 = alguna comprobacion fallida; 2 = sin contrasena o sin conexion.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT_REF = "vklaiuytvegkelgyspxc"
ROL = "cf_pagos_web"
USUARIO = f"{ROL}.{PROJECT_REF}"
VARIABLE = "CF_PAGOS_PASSWORD"
APPLICATION_NAME = "cf_h6d_prueba_acceso"
AUTOR = "prueba-acceso-H6-D"

LECTURAS = ("vencimientos_marcas_pago", "proveedores_forma_pago", "pagos_historial")
DENEGADO = "42501"  # insufficient_privilege
FACTURA_FICTICIA = "00000000-0000-4000-8000-000000000006"


def _cif() -> str:
    return "ZZPRUEBA" + uuid.uuid4().hex[:8].upper()


def _insert_forma(cif: str) -> str:
    return (f"insert into public.proveedores_forma_pago (farmacia, cif, forma) values ('PIO', '{cif}', 'EFECTIVO') "
            "returning id::text")


def _error(error: Exception) -> dict:
    texto = str(error).splitlines()[0] if str(error) else type(error).__name__
    return {"sqlstate": getattr(error, "pgcode", None), "mensaje": texto}


def _escritura_con_autor(conn) -> dict:
    cif = _cif()
    cur = conn.cursor()
    out = {"cif_prueba": cif}
    try:
        cur.execute("begin read write")
        cur.execute(f"set local cf.autor = '{AUTOR}'")
        cur.execute(_insert_forma(cif))
        registro = cur.fetchone()[0]
        cur.execute("update public.proveedores_forma_pago set anulada = true where id = %s", (registro,))
        cur.execute("select operacion, autor from public.pagos_historial where tabla = 'proveedores_forma_pago' "
                    "and registro_id = %s order by id", (registro,))
        historial = [list(r) for r in cur.fetchall()]
        out.update({"inserta_y_anula": True,
                    "historial_con_autor": historial == [["INSERT", AUTOR], ["UPDATE", AUTOR]]})
    except Exception as error:  # noqa: BLE001 - se informa el SQLSTATE, nunca datos de conexion
        out.update({"inserta_y_anula": False, "historial_con_autor": False, **_error(error)})
    finally:
        conn.rollback()
    # Tras el rollback: ni la fila ni su historial.
    try:
        cur.execute("begin read only")
        cur.execute("select (select count(*) from public.proveedores_forma_pago where cif = %s), "
                    "(select count(*) from public.pagos_historial where despues ->> 'cif' = %s)", (cif, cif))
        out["deshecho"] = list(cur.fetchone()) == [0, 0]
    except Exception as error:  # noqa: BLE001
        out.update({"deshecho": False, "error_comprobacion": _error(error)})
    finally:
        conn.rollback()
    return out


def _debe_fallar(conn, sentencias: list[str], esperado) -> dict:
    cur = conn.cursor()
    try:
        cur.execute("begin read write")
        for s in sentencias:
            cur.execute(s)
    except Exception as error:  # noqa: BLE001
        info = _error(error)
        return {"falla": esperado(info), **info}
    finally:
        conn.rollback()
    return {"falla": False, "sqlstate": None, "mensaje": "NO_FALLO (deshecho)"}


def probar(host: str, puerto: int, usuario: str, contrasena: str, dbname: str = "postgres",
           sslmode: str = "require") -> dict:
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import psycopg2

    conn = psycopg2.connect(host=host, port=puerto, dbname=dbname, user=usuario, password=contrasena,
                            sslmode=sslmode, connect_timeout=10, application_name=APPLICATION_NAME)
    denegado = lambda i: i["sqlstate"] == DENEGADO  # noqa: E731
    autor = f"set local cf.autor = '{AUTOR}'"
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("select current_user")
        rol = cur.fetchone()[0]
        conteos = {}
        for objeto in LECTURAS:
            cur.execute(f"select count(*) from public.{objeto}")
            conteos[objeto] = cur.fetchone()[0]
        conn.autocommit = False
        resultado = {
            "conecta_como_cf_pagos_web": rol == ROL,
            "lee_sus_tablas": conteos,
            "escritura_con_autor": _escritura_con_autor(conn),
            "marca_factura_inexistente": _debe_fallar(conn, [autor, (
                "insert into public.vencimientos_marcas_pago (farmacia, factura_id, vencimiento_orden, fecha_pago, "
                f"forma) values ('PIO', '{FACTURA_FICTICIA}', 1, '2026-01-01', 'EFECTIVO')")],
                lambda i: "FACTURA_NO_ENCONTRADA" in i["mensaje"]),
            "insert_sin_autor": _debe_fallar(conn, [_insert_forma(_cif())],
                                             lambda i: "AUTOR_AUSENTE" in i["mensaje"]),
            "delete_marcas": _debe_fallar(conn, ["delete from public.vencimientos_marcas_pago where id = "
                                                 "'00000000-0000-4000-8000-000000000000'::uuid"], denegado),
            "delete_formas": _debe_fallar(conn, ["delete from public.proveedores_forma_pago where id = "
                                                 "'00000000-0000-4000-8000-000000000000'::uuid"], denegado),
            "leer_facturas": _debe_fallar(conn, ["select count(*) from public.facturas"], denegado),
            "leer_vencimientos": _debe_fallar(conn, ["select count(*) from public.facturas_vencimientos"], denegado),
            "escribir_facturas": _debe_fallar(conn, [autor, "update public.facturas set observaciones = observaciones "
                                                            "where false"], denegado),
            "escribir_vencimientos": _debe_fallar(conn, [autor, (
                "insert into public.facturas_vencimientos (factura_id, fecha_vencimiento, importe, orden) values "
                f"('{FACTURA_FICTICIA}', '2026-01-01', 1, 99)")], denegado),
            "escribir_historial": _debe_fallar(conn, [(
                "insert into public.pagos_historial (tabla, registro_id, operacion, despues, autor) values "
                f"('proveedores_forma_pago', 'x', 'INSERT', '{{}}', '{AUTOR}')")], denegado),
        }
    finally:
        conn.close()
    escritura = resultado["escritura_con_autor"]
    fallos_esperados = ("marca_factura_inexistente", "insert_sin_autor", "delete_marcas", "delete_formas",
                        "leer_facturas", "leer_vencimientos", "escribir_facturas", "escribir_vencimientos",
                        "escribir_historial")
    ok = (resultado["conecta_como_cf_pagos_web"] and len(conteos) == len(LECTURAS)
          and escritura.get("inserta_y_anula") and escritura.get("historial_con_autor") and escritura.get("deshecho")
          and all(resultado[k]["falla"] for k in fallos_esperados))
    resultado["veredicto"] = "ACCESO_OK" if ok else "ACCESO_CON_FALLOS"
    return resultado


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("uso: probar_acceso_cf_pagos_web.py <host_pooler> <puerto_pooler>")
    contrasena = os.environ.get(VARIABLE)
    if not contrasena:
        print(f"{VARIABLE} no definida: no se conecta")
        return 2
    try:
        resultado = probar(argv[0], int(argv[1]), USUARIO, contrasena)
    except Exception as error:  # noqa: BLE001
        print(f"SIN_CONEXION: {type(error).__name__}: {str(error).splitlines()[0] if str(error) else ''}")
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=1, default=str))
    return 0 if resultado["veredicto"] == "ACCESO_OK" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
