"""Hito 2BE-D: preflight, captura y postcheck ESTRICTAMENTE READ_ONLY de la migracion 24 (R17).

Uso (identidad Windows Usuari; conexion CONTROLFARMACIAS_SUPABASE_DB_URL; sin Farmatic):
  python -B pruebas/auditoria_2be_d/preflight_readonly.py precondiciones <salida.json>
  python -B pruebas/auditoria_2be_d/preflight_readonly.py local <23|24> <salida.json>
  python -B pruebas/auditoria_2be_d/preflight_readonly.py alcance <local_23.json> <local_24.json> <salida.json>
  python -B pruebas/auditoria_2be_d/preflight_readonly.py captura <pre|post> <salida.json>
  python -B pruebas/auditoria_2be_d/preflight_readonly.py comparar_pre <pre.json> <local_23.json> <alcance.json> <salida.json>
  python -B pruebas/auditoria_2be_d/preflight_readonly.py comparar_despliegue <pre.json> <post.json> <local_24.json> <alcance.json> <salida.json>

Patron de ``pruebas/auditoria_2bf_d/preflight_readonly.py`` (puerta del 2AT: project ref demostrado, sesion
READ_ONLY REPEATABLE READ, solo SELECT/WITH, rollback; salidas FUERA del repositorio; tareas solo con
``Get-ScheduledTaskInfo``). Cambia lo propio de la 24:

- las precondiciones son las de ``desplegar_24.py`` (texto exacto, extraido por ast);
- marcas 23 presentes y 24 ausentes (pre) o presentes (post);
- objetivo: la factura 08007969 (PENDIENTE_CONCILIAR) y los albaranes de su linea R17, 280005 (08C20268) y
  280004 (Q039921/2026), de la recepcion 50898 y sin reserva;
- ``comparar_despliegue`` (criterio 2AX): solo cambia el alcance 23 <-> 24, igual a la referencia 24; fuera de
  alcance identico; datos (huella por fila de todas las tablas, historial, reservas, aprobaciones y
  aplicaciones), operacion y configuracion identicos.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import (  # noqa: E402
    _Lector, _ejecutar_lectura, _escribir, _operacion, _puertas_operacion, _salida_fuera_del_repo)

_spec = importlib.util.spec_from_file_location("preflight_2bfd", ROOT / "pruebas/auditoria_2bf_d/preflight_readonly.py")
bfd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bfd)

SQL_ESQUEMA = bfd.SQL_ESQUEMA
SQL_RESERVAS = bfd.SQL_RESERVAS
SQL_VIGENTES = bfd.SQL_VIGENTES
TABLAS_HUELLA = bfd.TABLAS_HUELLA
_md5 = bfd._md5
_clave = bfd._clave
_tareas = bfd._tareas
_puertas_tareas = bfd._puertas_tareas
_filas_json = bfd._filas_json
_leer_json = bfd._leer_json
_diferencias_huella = bfd._diferencias_huella

SCRIPT_DESPLIEGUE = ROOT / "pruebas/auditoria_2be/desplegar_24.py"
FARMACIA = "PIO"
FACTURA = "08007969"
# Linea R17 de 08007969 (medicion READ_ONLY del 2BE, 2026-10-29): IdContador -> (numero, PUC).
ALBARANES_R17 = {280005: ("08C20268", "500.86"), 280004: ("Q039921/2026", "3.16")}
RECEPCION = 50898
PERSISTIR = "'public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)'::regprocedure"

MARCAS = (
    "select jsonb_build_object("
    "'23_tabla_aprobaciones', to_regclass('public.albaranes_aprobaciones') is not null,"
    "'23_tabla_aplicadas', to_regclass('public.albaranes_aprobaciones_aplicadas') is not null,"
    "'23_rpc_aplicar', to_regprocedure('public.cf_aplicar_aprobacion_albaran(bigint,jsonb,text)') is not null,"
    "'24_auxiliar_r17', to_regprocedure('public.cf_linea_r17_valida(uuid,text,jsonb,jsonb)') is not null,"
    f"'24_persistir_r17', position('cf_linea_r17_valida' in pg_get_functiondef({PERSISTIR})) > 0)::text"
)
MARCAS_23 = ("23_tabla_aprobaciones", "23_tabla_aplicadas", "23_rpc_aplicar")
MARCAS_24 = ("24_auxiliar_r17", "24_persistir_r17")


# --------------------------------------------------------------------------- precondiciones (norma 2AX)

def sql_precondiciones() -> str:
    """La consulta ``PRECONDICIONES`` de ``desplegar_24.py`` (texto exacto, extraido por ast)."""
    arbol = ast.parse(SCRIPT_DESPLIEGUE.read_text(encoding="utf-8"))
    [nodo] = [n for n in arbol.body if isinstance(n, ast.Assign)
              and [getattr(t, "id", None) for t in n.targets] == ["PRECONDICIONES"]]
    entorno = {"PERSISTIR": next(eval(compile(ast.Expression(n.value), str(SCRIPT_DESPLIEGUE), "eval"), {})
                                 for n in arbol.body if isinstance(n, ast.Assign)
                                 and [getattr(t, "id", None) for t in n.targets] == ["PERSISTIR"])}
    return eval(compile(ast.Expression(nodo.value), str(SCRIPT_DESPLIEGUE), "eval"), entorno)


def precondiciones(salida: Path) -> int:
    sql = sql_precondiciones()
    _, datos = _ejecutar_lectura(lambda lector: {"precondiciones": list(lector.fila(sql))})
    datos["sql"] = sql
    datos["veredicto"] = "PRECONDICIONES_OK" if all(datos["precondiciones"]) else "PRECONDICIONES_NO_CUMPLIDAS"
    print(json.dumps({k: datos[k] for k in ("project_ref", "capturado_utc", "transaction_read_only",
                                            "precondiciones", "veredicto")}, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if all(datos["precondiciones"]) else 3


# --------------------------------------------------------------------------- alcance (sin conexion)

def alcance(local23_ruta: Path, local24_ruta: Path, salida: Path) -> int:
    """Objetos cuya huella difiere entre las referencias locales 23 y 24 (no se escribe a mano)."""
    a = _leer_json(local23_ruta)["esquema"]["objetos"]
    b = _leer_json(local24_ruta)["esquema"]["objetos"]
    claves = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    datos = {"alcance_24": claves, "nuevos": sorted(set(b) - set(a)), "eliminados": sorted(set(a) - set(b))}
    print(json.dumps(datos, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if claves and not datos["eliminados"] else 3


# --------------------------------------------------------------------------- captura

def _leer(lector: _Lector) -> dict:
    out = {"marcas": lector.json(MARCAS), "esquema": lector.json(SQL_ESQUEMA + "")}
    out["operacion"] = _operacion(lector)
    out["cf_configuracion_completa"] = lector.json("select to_jsonb(c)::text from public.cf_configuracion c where id")
    out["locks_factura"] = lector.valor(
        "select count(*) from public.facturas where conciliacion_bloqueado_hasta > now()")
    out["lineas_vigentes_con_albaran"] = lector.json(SQL_VIGENTES)
    out["reservas"] = lector.json(SQL_RESERVAS)
    out["huellas_por_fila"] = {t: {r[0]: r[1] for r in lector.filas(
        f"select t.id::text, md5(to_jsonb(t)::text) from public.{t} t order by t.id")} for t in TABLAS_HUELLA}
    out["factura_objetivo"] = _filas_json(
        lector, f"select to_jsonb(f)::text from public.facturas f where numero_factura = '{FACTURA}'")
    contadores = ",".join(str(c) for c in ALBARANES_R17)
    out["albaranes_r17"] = _filas_json(
        lector, f"select to_jsonb(a)::text from public.albaranes a where farmacia = '{FARMACIA}' "
                f"and id_contador in ({contadores}) order by id_contador")
    out["reservas_r17"] = _filas_json(
        lector, "select to_jsonb(r)::text from public.conciliacion_albaranes_reservados r "
                f"where albaran_farmacia = '{FARMACIA}' and albaran_id_contador in ({contadores})")
    out["recepcion_albaranes"] = lector.valor(
        f"select count(*) from public.albaranes where farmacia = '{FARMACIA}' and id_recepcion = {RECEPCION}")
    if out["marcas"]["23_tabla_aprobaciones"]:
        out["aprobaciones"] = _filas_json(
            lector, "select to_jsonb(a)::text from public.albaranes_aprobaciones a order by id")
    if out["marcas"]["23_tabla_aplicadas"]:
        out["aplicadas"] = _filas_json(
            lector, "select to_jsonb(p)::text from public.albaranes_aprobaciones_aplicadas p order by aprobacion_id")
    return out


def _fallos_objetivo(datos: dict) -> list[str]:
    fallos = []
    facturas = datos["factura_objetivo"]
    if len(facturas) != 1:
        fallos.append(f"FACTURA_{FACTURA}_NO_UNICA:{len(facturas)}")
    elif facturas[0].get("estado_conciliacion_cf") != "PENDIENTE_CONCILIAR":
        fallos.append(f"FACTURA_{FACTURA}_NO_PENDIENTE:{facturas[0].get('estado_conciliacion_cf')}")
    vistos = {int(a["id_contador"]): a for a in datos["albaranes_r17"]}
    for contador, (numero, puc) in ALBARANES_R17.items():
        a = vistos.get(contador)
        if a is None:
            fallos.append(f"ALBARAN_R17_AUSENTE:{contador}")
        elif (a.get("numero_albaran"), f"{float(a.get('importe_puc')):.2f}", a.get("id_recepcion")) != \
                (numero, puc, RECEPCION):
            fallos.append(f"ALBARAN_R17_DISTINTO:{contador}:{a.get('numero_albaran')}:{a.get('importe_puc')}:"
                          f"{a.get('id_recepcion')}")
    if datos["reservas_r17"]:
        fallos.append(f"ALBARAN_R17_RESERVADO:{[r['albaran_id_contador'] for r in datos['reservas_r17']]}")
    if datos["recepcion_albaranes"] != len(ALBARANES_R17):
        fallos.append(f"RECEPCION_{RECEPCION}_CON_{datos['recepcion_albaranes']}_ALBARANES")
    return fallos


def captura(fase: str, salida: Path) -> int:
    if fase not in ("pre", "post"):
        raise SystemExit("fase debe ser pre o post")
    tareas = _tareas()
    import datetime as _dt
    ahora_tareas = _dt.datetime.now(_dt.timezone.utc)
    _, datos = _ejecutar_lectura(_leer)
    datos.update({"fase": fase, "tareas": tareas, "tareas_consultadas_utc": ahora_tareas.isoformat()})
    marcas = datos["marcas"]
    fallos = [f"MIGRACION_23_AUSENTE:{k}" for k in MARCAS_23 if not marcas[k]]
    if fase == "pre":
        fallos += [f"MIGRACION_24_YA_PRESENTE:{k}" for k in MARCAS_24 if marcas[k]]
        fallos += _puertas_tareas(tareas, ahora_tareas)
    else:
        fallos += [f"MIGRACION_24_AUSENTE:{k}" for k in MARCAS_24 if not marcas[k]]
    if sorted(_clave(r) for r in datos["reservas"]) != sorted(_clave(r) for r in datos["lineas_vigentes_con_albaran"]):
        fallos.append("RESERVAS_DISTINTAS_DE_VIGENTES_CON_ALBARAN")
    if datos["esquema"]["owner_distinto_de_postgres"]:
        fallos.append(f"OWNER_DISTINTO_DE_POSTGRES:{datos['esquema']['owner_distinto_de_postgres']}")
    fallos += _puertas_operacion(datos["operacion"])
    if datos["locks_factura"]:
        fallos.append(f"LOCKS_FACTURA:{datos['locks_factura']}")
    fallos += _fallos_objetivo(datos)
    datos["fallos"] = fallos
    datos["veredicto"] = "CAPTURA_OK" if not fallos else "PARADO"
    sha = _escribir(salida, datos)
    [factura] = datos["factura_objetivo"] or [{}]
    resumen = {k: datos.get(k) for k in ("project_ref", "capturado_utc", "current_user", "fase", "marcas",
                                         "locks_factura", "fallos", "veredicto")}
    resumen.update({"flags": datos["operacion"]["flags"], "conteos": datos["operacion"]["conteos"],
                    "reservas": len(datos["reservas"]), "objetos_publicos": len(datos["esquema"]["objetos"]),
                    "filas_por_tabla": {t: len(v) for t, v in datos["huellas_por_fila"].items()},
                    "factura_objetivo": {k: factura.get(k) for k in ("id", "numero_factura", "estado_conciliacion_cf",
                                                                     "importe_total", "intentos_conciliacion")},
                    "albaranes_r17": [(a["id_contador"], a["numero_albaran"], a["importe_puc"], a["id_recepcion"])
                                      for a in datos["albaranes_r17"]],
                    "reservas_r17": len(datos["reservas_r17"]), "recepcion_albaranes": datos["recepcion_albaranes"],
                    "aprobaciones": len(datos.get("aprobaciones", [])), "aplicadas": len(datos.get("aplicadas", [])),
                    "tareas": tareas})
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


# --------------------------------------------------------------------------- comparaciones (sin conexion)

def comparar_pre(pre_ruta: Path, local23_ruta: Path, alcance_ruta: Path, salida: Path) -> int:
    """Produccion esta en el esquema 23 para todo el alcance de la 24."""
    pre = _leer_json(pre_ruta)
    ref = _leer_json(local23_ruta)["esquema"]["objetos"]
    claves = _leer_json(alcance_ruta)["alcance_24"]
    b = pre["esquema"]["objetos"]
    informe = {"alcance_24_igual_a_local_23": {k: _md5(b.get(k)) == _md5(ref.get(k)) for k in claves},
               "captura_pre_ok": pre.get("veredicto") == "CAPTURA_OK"}
    ok = all(informe["alcance_24_igual_a_local_23"].values()) and informe["captura_pre_ok"]
    informe["veredicto"] = "ESQUEMA_23_CONFIRMADO" if ok else "ESQUEMA_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


def comparar_despliegue(pre_ruta: Path, post_ruta: Path, local24_ruta: Path, alcance_ruta: Path,
                        salida: Path) -> int:
    """Criterio de postcheck de REGLAS_CRITICAS (2AX) mas datos intactos."""
    pre, post = _leer_json(pre_ruta), _leer_json(post_ruta)
    ref = _leer_json(local24_ruta)["esquema"]["objetos"]
    claves = _leer_json(alcance_ruta)["alcance_24"]
    a, b = pre["esquema"]["objetos"], post["esquema"]["objetos"]
    cambiados = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    informe = {
        "c1_solo_cambia_el_alcance": set(cambiados) <= set(claves), "objetos_cambiados": cambiados,
        "c2_alcance_igual_a_local_24": {k: _md5(b.get(k)) == _md5(ref.get(k)) for k in claves},
        "c3_fuera_de_alcance_identicos": all(_md5(a.get(k)) == _md5(b.get(k)) for k in set(a) | set(b)
                                             if k not in claves),
        "default_acl_identico": pre["esquema"]["default_acl"] == post["esquema"]["default_acl"],
        "cf_configuracion_identica": pre["cf_configuracion_completa"] == post["cf_configuracion_completa"],
        "huellas_identicas": {t: pre["huellas_por_fila"][t] == post["huellas_por_fila"][t] for t in TABLAS_HUELLA},
        "operacion_identica": pre["operacion"] == post["operacion"] and pre["locks_factura"] == post["locks_factura"],
        "reservas_pre_igual_post": pre["reservas"] == post["reservas"],
        "objetivo_identico": all(pre[k] == post[k] for k in ("factura_objetivo", "albaranes_r17", "reservas_r17",
                                                             "recepcion_albaranes")),
        "aprobaciones_identicas": pre.get("aprobaciones") == post.get("aprobaciones")
                                  and pre.get("aplicadas") == post.get("aplicadas"),
        "captura_post_ok": post.get("veredicto") == "CAPTURA_OK",
    }
    for t in TABLAS_HUELLA:
        if not informe["huellas_identicas"][t]:
            informe.setdefault("diferencias_huella", {})[t] = _diferencias_huella(
                pre["huellas_por_fila"][t], post["huellas_por_fila"][t])
    ok = all(v if isinstance(v, bool) else all(v.values()) for k, v in informe.items()
             if k not in ("objetos_cambiados", "diferencias_huella"))
    informe["veredicto"] = "POSTCHECK_OK" if ok else "POSTCHECK_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=str))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


if __name__ == "__main__":
    modo, args = sys.argv[1], sys.argv[2:]
    if modo == "precondiciones":
        sys.exit(precondiciones(_salida_fuera_del_repo(args[0])))
    elif modo == "local":
        bfd.bdd.azd.local(args[0], _salida_fuera_del_repo(args[1]))
    elif modo == "alcance":
        sys.exit(alcance(Path(args[0]), Path(args[1]), _salida_fuera_del_repo(args[2])))
    elif modo == "captura":
        sys.exit(captura(args[0], _salida_fuera_del_repo(args[1])))
    elif modo == "comparar_pre":
        sys.exit(comparar_pre(Path(args[0]), Path(args[1]), Path(args[2]), _salida_fuera_del_repo(args[3])))
    elif modo == "comparar_despliegue":
        sys.exit(comparar_despliegue(Path(args[0]), Path(args[1]), Path(args[2]), Path(args[3]),
                                     _salida_fuera_del_repo(args[4])))
    else:
        raise SystemExit("modo desconocido")
