"""Hito 40-D: prueba de acceso del rol de escritura de la web cf_cashflow_web por el pooler de Supabase.

Uso (terminal de Pio; la contrasena SOLO en la variable de entorno CF_CASHFLOW_PASSWORD, nunca como argumento ni
impresa):
  python -B pruebas/auditoria_h7b/probar_acceso_cf_cashflow_web.py <host_pooler> <puerto_pooler> <categoria_PIO>

<categoria_PIO> es una categoria de la plantilla de la cuenta PIO en la importacion vigente (p. ej. «RE ...»); se
obtiene antes con una lectura READ_ONLY. Usuario fijo ``cf_cashflow_web.<project_ref>``. Patron de
pruebas/auditoria_h6/probar_acceso_cf_pagos_web.py. Comprueba:
- conecta (TLS) como cf_cashflow_web;
- lee sus cuatro tablas (conteos) y ejecuta cf_cashflow_ocurrencias;
- escribe en sus tablas: un INSERT de prueba en cf_cashflow_conceptos CON autor (nombre ZZPRUEBA...) en esa categoria y
  su anulacion funcionan y dejan dos filas de historial con ese autor; la transaccion se DESHACE siempre (rollback) y
  despues se comprueba que no queda ni la fila ni su historial;
- un concepto en una categoria inexistente falla (CATEGORIA_FUERA_DE_PLANTILLA: el trigger valida contra la
  importacion vigente sin que la web pueda leerla);
- el INSERT SIN autor falla (AUTOR_AUSENTE);
- DELETE en sus tablas y UPDATE del importe de una recurrente fallan (42501);
- leer las tablas importadas, facturas y vencimientos, escribir en ellas, escribir en el historial y ejecutar la RPC de
  importacion fallan (42501).
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
ROL = "cf_cashflow_web"
USUARIO = f"{ROL}.{PROJECT_REF}"
VARIABLE = "CF_CASHFLOW_PASSWORD"
APPLICATION_NAME = "cf_40d_prueba_acceso"
AUTOR = "prueba-acceso-40-D"

LECTURAS = ("cf_cashflow_conceptos", "cf_cashflow_recurrentes", "cf_cashflow_apuntes", "cf_cashflow_apuntes_historial")
DENEGADO = "42501"  # insufficient_privilege
NULO = "00000000-0000-4000-8000-000000000000"


def _nombre() -> str:
    return "ZZPRUEBA-" + uuid.uuid4().hex[:8].upper()


def _literal(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _insert_concepto(nombre: str, categoria: str) -> str:
    return ("insert into public.cf_cashflow_conceptos (cuenta, categoria, nombre) values "
            f"('PIO', {_literal(categoria)}, {_literal(nombre)}) returning id::text")


def _error(error: Exception) -> dict:
    texto = str(error).splitlines()[0] if str(error) else type(error).__name__
    return {"sqlstate": getattr(error, "pgcode", None), "mensaje": texto}


def _escritura_con_autor(conn, categoria: str) -> dict:
    nombre = _nombre()
    cur = conn.cursor()
    out = {"nombre_prueba": nombre}
    try:
        cur.execute("begin read write")
        cur.execute(f"set local cf.autor = '{AUTOR}'")
        cur.execute(_insert_concepto(nombre, categoria))
        registro = cur.fetchone()[0]
        cur.execute("update public.cf_cashflow_conceptos set anulado = true, motivo_anulacion = 'prueba de acceso' "
                    "where id = %s", (registro,))
        cur.execute("select operacion, autor from public.cf_cashflow_apuntes_historial "
                    "where tabla = 'cf_cashflow_conceptos' and registro_id = %s order by id", (registro,))
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
        cur.execute("select (select count(*) from public.cf_cashflow_conceptos where nombre = %s), "
                    "(select count(*) from public.cf_cashflow_apuntes_historial where despues ->> 'nombre' = %s)",
                    (nombre, nombre))
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


def probar(host: str, puerto: int, usuario: str, contrasena: str, categoria: str, dbname: str = "postgres",
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
        cur.execute("select count(*) from public.cf_cashflow_ocurrencias(current_date, current_date + 400)")
        ocurrencias = cur.fetchone()[0]
        conn.autocommit = False
        resultado = {
            "conecta_como_cf_cashflow_web": rol == ROL,
            "lee_sus_tablas": conteos,
            "ocurrencias_proximo_ano": ocurrencias,
            "escritura_con_autor": _escritura_con_autor(conn, categoria),
            "categoria_inexistente": _debe_fallar(conn, [autor, _insert_concepto(_nombre(), "RE ZZ-PRUEBA-INEXISTENTE")],
                                                  lambda i: "CATEGORIA_FUERA_DE_PLANTILLA" in i["mensaje"]),
            "insert_sin_autor": _debe_fallar(conn, [_insert_concepto(_nombre(), categoria)],
                                             lambda i: "AUTOR_AUSENTE" in i["mensaje"]),
            "delete_conceptos": _debe_fallar(conn, [f"delete from public.cf_cashflow_conceptos where id = '{NULO}'"],
                                             denegado),
            "delete_apuntes": _debe_fallar(conn, [f"delete from public.cf_cashflow_apuntes where id = '{NULO}'"],
                                           denegado),
            "cambiar_importe": _debe_fallar(conn, [autor, "update public.cf_cashflow_recurrentes set importe = 1 "
                                                          f"where id = '{NULO}'"], denegado),
            "leer_importes": _debe_fallar(conn, ["select count(*) from public.cf_cashflow_importes"], denegado),
            "leer_saldos": _debe_fallar(conn, ["select count(*) from public.cf_cashflow_saldos"], denegado),
            "leer_facturas": _debe_fallar(conn, ["select count(*) from public.facturas"], denegado),
            "leer_vencimientos": _debe_fallar(conn, ["select count(*) from public.facturas_vencimientos"], denegado),
            "escribir_importaciones": _debe_fallar(conn, [
                "update public.cf_cashflow_importaciones set vigente = vigente where false"], denegado),
            "escribir_historial": _debe_fallar(conn, [(
                "insert into public.cf_cashflow_apuntes_historial (tabla, registro_id, cuenta, farmacia, operacion, "
                f"despues, autor) values ('cf_cashflow_conceptos', '{NULO}', 'PIO', 'PIO', 'INSERT', '{{}}', "
                f"'{AUTOR}')")], denegado),
            "ejecutar_rpc_importacion": _debe_fallar(conn, [
                "select public.cf_cashflow_registrar_importacion('{}'::jsonb, '[]'::jsonb, '[]'::jsonb)"], denegado),
        }
    finally:
        conn.close()
    escritura = resultado["escritura_con_autor"]
    fallos_esperados = ("categoria_inexistente", "insert_sin_autor", "delete_conceptos", "delete_apuntes",
                        "cambiar_importe", "leer_importes", "leer_saldos", "leer_facturas", "leer_vencimientos",
                        "escribir_importaciones", "escribir_historial", "ejecutar_rpc_importacion")
    ok = (resultado["conecta_como_cf_cashflow_web"] and len(conteos) == len(LECTURAS)
          and escritura.get("inserta_y_anula") and escritura.get("historial_con_autor") and escritura.get("deshecho")
          and all(resultado[k]["falla"] for k in fallos_esperados))
    resultado["veredicto"] = "ACCESO_OK" if ok else "ACCESO_CON_FALLOS"
    return resultado


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit("uso: probar_acceso_cf_cashflow_web.py <host_pooler> <puerto_pooler> <categoria_PIO>")
    contrasena = os.environ.get(VARIABLE)
    if not contrasena:
        print(f"{VARIABLE} no definida: no se conecta")
        return 2
    try:
        resultado = probar(argv[0], int(argv[1]), USUARIO, contrasena, argv[2])
    except Exception as error:  # noqa: BLE001
        print(f"SIN_CONEXION: {type(error).__name__}: {str(error).splitlines()[0] if str(error) else ''}")
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=1, default=str))
    return 0 if resultado["veredicto"] == "ACCESO_OK" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
