"""Hito TRAB-D: prueba de acceso del rol de escritura de la web cf_trabajadores_web por el pooler de Supabase.

Uso (terminal de Pio; la contrasena SOLO en la variable de entorno CF_TRAB_PASSWORD, nunca como argumento ni
impresa):
  python -B pruebas/auditoria_trab/probar_acceso_cf_trabajadores_web.py <host_pooler> <puerto_pooler>

Usuario fijo ``cf_trabajadores_web.<project_ref>``. Patron de pruebas/auditoria_2bn_d/probar_acceso_cf_lectura.py.
Comprueba:
- conecta (TLS) como cf_trabajadores_web;
- lee las tablas, la vista y los permisos del modulo de Trabajadores (conteos);
- un INSERT de prueba en trabajadoras CON autor funciona y escribe su fila de historial con ese autor; la transaccion
  se DESHACE siempre (rollback) y despues se comprueba que no queda ni la trabajadora ni su historial;
- el mismo INSERT SIN autor falla (AUTOR_AUSENTE);
- un DELETE en trabajadoras falla (42501);
- leer facturas falla (42501).
Cada intento va en su propia transaccion READ WRITE que se deshace SIEMPRE. Efecto residual conocido: el INSERT con
autor consume un valor de la secuencia del historial (las secuencias no se deshacen); no deja filas. Sin salidas en
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
ROL = "cf_trabajadores_web"
USUARIO = f"{ROL}.{PROJECT_REF}"
VARIABLE = "CF_TRAB_PASSWORD"
APPLICATION_NAME = "cf_trabd_prueba_acceso"
AUTOR = "prueba-acceso-TRAB-D"

LECTURAS = ("trabajadoras", "convenio_anual", "eventos_calendario", "guardias_farmacia", "festivos",
            "trabajadores_historial", "cf_modulos_farmacias", "v_eventos_calendario_horas")
DENEGADO = "42501"  # insufficient_privilege


def _insert(nombre: str) -> str:
    return ("insert into public.trabajadoras (farmacia, nombre, categoria, tipo_jornada, horas_diarias, fecha_alta) "
            f"values ('PIO', '{nombre}', 'OTRA', 'COMPLETA', 8, '2099-01-01') returning id::text")


def _error(error: Exception) -> dict:
    texto = str(error).splitlines()[0] if str(error) else type(error).__name__
    return {"sqlstate": getattr(error, "pgcode", None), "mensaje": texto}


def _insert_con_autor(conn) -> dict:
    nombre = "PRUEBA_ACCESO_" + uuid.uuid4().hex[:8]
    cur = conn.cursor()
    out = {"nombre_prueba": nombre}
    try:
        cur.execute("begin read write")
        cur.execute(f"set local cf.autor = '{AUTOR}'")
        cur.execute(_insert(nombre))
        registro = cur.fetchone()[0]
        cur.execute("select autor from public.trabajadores_historial where tabla = 'trabajadoras' "
                    "and registro_id = %s and operacion = 'INSERT'", (registro,))
        autores = [r[0] for r in cur.fetchall()]
        out.update({"inserta": True, "historial_con_autor": autores == [AUTOR]})
    except Exception as error:  # noqa: BLE001 - se informa el SQLSTATE, nunca datos de conexion
        out.update({"inserta": False, "historial_con_autor": False, **_error(error)})
    finally:
        conn.rollback()
    # Tras el rollback: ni la trabajadora ni su historial.
    try:
        cur.execute("begin read only")
        cur.execute("select (select count(*) from public.trabajadoras where nombre = %s), "
                    "(select count(*) from public.trabajadores_historial where despues ->> 'nombre' = %s)",
                    (nombre, nombre))
        quedan = cur.fetchone()
        out["deshecho"] = list(quedan) == [0, 0]
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
        con_autor = _insert_con_autor(conn)
        sin_autor = _debe_fallar(conn, [_insert("PRUEBA_SIN_AUTOR_" + uuid.uuid4().hex[:8])],
                                 lambda i: "AUTOR_AUSENTE" in i["mensaje"])
        borrar = _debe_fallar(conn, ["delete from public.trabajadoras where id = "
                                     "'00000000-0000-4000-8000-000000000000'::uuid"],
                              lambda i: i["sqlstate"] == DENEGADO)
        facturas = _debe_fallar(conn, ["select count(*) from public.facturas"],
                                lambda i: i["sqlstate"] == DENEGADO)
    finally:
        conn.close()
    resultado = {
        "conecta_como_cf_trabajadores_web": rol == ROL,
        "lee_trabajadores": conteos,
        "insert_con_autor": con_autor,
        "insert_sin_autor": sin_autor,
        "delete": borrar,
        "leer_facturas": facturas,
    }
    ok = (resultado["conecta_como_cf_trabajadores_web"] and len(conteos) == len(LECTURAS)
          and con_autor.get("inserta") and con_autor.get("historial_con_autor") and con_autor.get("deshecho")
          and sin_autor["falla"] and borrar["falla"] and facturas["falla"])
    resultado["veredicto"] = "ACCESO_OK" if ok else "ACCESO_CON_FALLOS"
    return resultado


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("uso: probar_acceso_cf_trabajadores_web.py <host_pooler> <puerto_pooler>")
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
