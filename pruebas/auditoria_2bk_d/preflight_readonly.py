"""Hito 2BK-D: preflight, captura y postcheck ESTRICTAMENTE READ_ONLY de la migracion 26.

Uso (identidad Windows Usuari; conexion CONTROLFARMACIAS_SUPABASE_DB_URL; sin Farmatic):
  python -B pruebas/auditoria_2bk_d/preflight_readonly.py precondiciones <salida.json>
  python -B pruebas/auditoria_2bk_d/preflight_readonly.py local <25|26> <salida.json>
  python -B pruebas/auditoria_2bk_d/preflight_readonly.py alcance <local_25.json> <local_26.json> <salida.json>
  python -B pruebas/auditoria_2bk_d/preflight_readonly.py captura <pre|post> <salida.json>
  python -B pruebas/auditoria_2bk_d/preflight_readonly.py comparar_pre <pre.json> <local_25.json> <alcance.json> <salida.json>
  python -B pruebas/auditoria_2bk_d/preflight_readonly.py comparar_despliegue <pre.json> <post.json> <local_26.json> <alcance.json> <salida.json>

Patron de ``pruebas/auditoria_2bi_d/preflight_readonly.py`` (puerta del 2AT: project ref demostrado, sesion
READ_ONLY REPEATABLE READ, solo SELECT/WITH, rollback; salidas FUERA del repositorio; tareas solo con
``Get-ScheduledTaskInfo``). Cambia lo propio de la 26:
- precondiciones: la constante ``PRECONDICIONES`` de ``pruebas/auditoria_2bk/desplegar_26.py`` (mismo objeto);
- marcas 25 presentes y 26 ausentes (pre) o presentes (post);
- el alcance incluye ``tabla:facturas`` (indice nuevo) y ``cf_componentes_identidad_factura`` (``COST``); las
  filas no cambian: ``comparar_despliegue`` exige la huella por fila identica pre/post (criterio 2AX).
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import (  # noqa: E402
    _ejecutar_lectura, _escribir, _puertas_operacion, _salida_fuera_del_repo)


def _cargar(nombre: str, ruta: str):
    spec = importlib.util.spec_from_file_location(nombre, ROOT / ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


bid = _cargar("preflight_2bid", "pruebas/auditoria_2bi_d/preflight_readonly.py")
despliegue = _cargar("desplegar_26", "pruebas/auditoria_2bk/desplegar_26.py")

TABLAS_HUELLA = bid.TABLAS_HUELLA
_md5, _clave, _leer_json = bid._md5, bid._clave, bid._leer_json

MARCAS = (
    "select jsonb_build_object("
    "'25_recuperar', to_regprocedure('public.cf_recuperar_claim_huerfano_normalizacion(uuid,text,interval)')"
    "  is not null,"
    "'25_huerfanos', to_regprocedure('public.cf_huerfanos_normalizacion(interval)') is not null,"
    "'25_senales', to_regprocedure('public.cf_senales_claim_huerfano(uuid)') is not null,"
    "'26_indice', to_regclass('public.facturas_identidad_nucleo_idx') is not null,"
    f"'26_nucleo_normalizacion', to_regprocedure('{despliegue.NUCLEO_NORMALIZACION}') is not null,"
    f"'26_nucleo_multifactura', to_regprocedure('{despliegue.NUCLEO_MULTI}') is not null,"
    f"'26_coste_identidad', (select procost = 10000 from pg_proc where oid = {despliegue.IDENTIDAD}))::text"
)
MARCAS_25 = ("25_recuperar", "25_huerfanos", "25_senales")
MARCAS_26 = ("26_indice", "26_nucleo_normalizacion", "26_nucleo_multifactura", "26_coste_identidad")

# bid._leer lee la global MARCAS de su modulo.
bid.MARCAS = MARCAS


def precondiciones(salida: Path) -> int:
    sql = despliegue.PRECONDICIONES
    _, datos = _ejecutar_lectura(lambda lector: {"precondiciones": list(lector.fila(sql))})
    datos["sql"] = sql
    datos["veredicto"] = "PRECONDICIONES_OK" if all(datos["precondiciones"]) else "PRECONDICIONES_NO_CUMPLIDAS"
    print(json.dumps({k: datos[k] for k in ("project_ref", "capturado_utc", "transaction_read_only",
                                            "precondiciones", "veredicto")}, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if all(datos["precondiciones"]) else 3


def alcance(local25_ruta: Path, local26_ruta: Path, salida: Path) -> int:
    """Objetos cuya huella difiere entre las referencias locales 25 y 26 (no se escribe a mano)."""
    a = _leer_json(local25_ruta)["esquema"]["objetos"]
    b = _leer_json(local26_ruta)["esquema"]["objetos"]
    claves = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    datos = {"alcance_26": claves, "nuevos": sorted(set(b) - set(a)), "eliminados": sorted(set(a) - set(b))}
    print(json.dumps(datos, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if claves and not datos["eliminados"] else 3


def captura(fase: str, salida: Path) -> int:
    if fase not in ("pre", "post"):
        raise SystemExit("fase debe ser pre o post")
    tareas = bid._tareas()
    ahora_tareas = _dt.datetime.now(_dt.timezone.utc)
    _, datos = _ejecutar_lectura(bid._leer)
    datos.update({"fase": fase, "tareas": tareas, "tareas_consultadas_utc": ahora_tareas.isoformat()})
    marcas = datos["marcas"]
    fallos = [f"MIGRACION_25_AUSENTE:{k}" for k in MARCAS_25 if not marcas[k]]
    if fase == "pre":
        fallos += [f"MIGRACION_26_YA_PRESENTE:{k}" for k in MARCAS_26 if marcas[k]]
        fallos += bid._puertas_tareas(tareas, ahora_tareas)
    else:
        fallos += [f"MIGRACION_26_AUSENTE:{k}" for k in MARCAS_26 if not marcas[k]]
    if datos["normalizando"]:
        fallos.append(f"DOCUMENTOS_EN_NORMALIZANDO:{len(datos['normalizando'])}")
    if sorted(_clave(r) for r in datos["reservas"]) != sorted(_clave(r) for r in datos["lineas_vigentes_con_albaran"]):
        fallos.append("RESERVAS_DISTINTAS_DE_VIGENTES_CON_ALBARAN")
    if datos["esquema"]["owner_distinto_de_postgres"]:
        fallos.append(f"OWNER_DISTINTO_DE_POSTGRES:{datos['esquema']['owner_distinto_de_postgres']}")
    fallos += _puertas_operacion(datos["operacion"])
    if datos["locks_factura"]:
        fallos.append(f"LOCKS_FACTURA:{datos['locks_factura']}")
    datos["fallos"] = fallos
    datos["veredicto"] = "CAPTURA_OK" if not fallos else "PARADO"
    sha = _escribir(salida, datos)
    resumen = {k: datos.get(k) for k in ("project_ref", "capturado_utc", "current_user", "fase", "marcas",
                                         "locks_factura", "normalizando", "fallos", "veredicto")}
    resumen.update({"flags": datos["operacion"]["flags"], "conteos": datos["operacion"]["conteos"],
                    "reservas": len(datos["reservas"]), "objetos_publicos": len(datos["esquema"]["objetos"]),
                    "filas_por_tabla": {t: len(v) for t, v in datos["huellas_por_fila"].items()},
                    "aprobaciones": len(datos["aprobaciones"]), "aplicadas": len(datos["aplicadas"]),
                    "tareas": tareas})
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


def comparar_pre(pre_ruta: Path, local25_ruta: Path, alcance_ruta: Path, salida: Path) -> int:
    """Produccion esta en el esquema 25 para todo el alcance de la 26."""
    pre = _leer_json(pre_ruta)
    ref = _leer_json(local25_ruta)["esquema"]["objetos"]
    claves = _leer_json(alcance_ruta)["alcance_26"]
    b = pre["esquema"]["objetos"]
    informe = {"alcance_26_igual_a_local_25": {k: _md5(b.get(k)) == _md5(ref.get(k)) for k in claves},
               "captura_pre_ok": pre.get("veredicto") == "CAPTURA_OK"}
    ok = all(informe["alcance_26_igual_a_local_25"].values()) and informe["captura_pre_ok"]
    informe["veredicto"] = "ESQUEMA_25_CONFIRMADO" if ok else "ESQUEMA_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


def comparar_despliegue(pre_ruta: Path, post_ruta: Path, local26_ruta: Path, alcance_ruta: Path,
                        salida: Path) -> int:
    """Criterio de postcheck de REGLAS_CRITICAS (2AX) mas datos intactos."""
    pre, post = _leer_json(pre_ruta), _leer_json(post_ruta)
    ref = _leer_json(local26_ruta)["esquema"]["objetos"]
    claves = _leer_json(alcance_ruta)["alcance_26"]
    a, b = pre["esquema"]["objetos"], post["esquema"]["objetos"]
    cambiados = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    informe = {
        "c1_solo_cambia_el_alcance": set(cambiados) <= set(claves), "objetos_cambiados": cambiados,
        "c2_alcance_igual_a_local_26": {k: _md5(b.get(k)) == _md5(ref.get(k)) for k in claves},
        "c3_fuera_de_alcance_identicos": all(_md5(a.get(k)) == _md5(b.get(k)) for k in set(a) | set(b)
                                             if k not in claves),
        "default_acl_identico": pre["esquema"]["default_acl"] == post["esquema"]["default_acl"],
        "cf_configuracion_identica": pre["cf_configuracion_completa"] == post["cf_configuracion_completa"],
        "huellas_identicas": {t: pre["huellas_por_fila"][t] == post["huellas_por_fila"][t] for t in TABLAS_HUELLA},
        "operacion_identica": pre["operacion"] == post["operacion"] and pre["locks_factura"] == post["locks_factura"],
        "reservas_pre_igual_post": pre["reservas"] == post["reservas"],
        "normalizando_identico": pre["normalizando"] == post["normalizando"],
        "aprobaciones_identicas": pre["aprobaciones"] == post["aprobaciones"] and pre["aplicadas"] == post["aplicadas"],
        "captura_post_ok": post.get("veredicto") == "CAPTURA_OK",
    }
    for t in TABLAS_HUELLA:
        if not informe["huellas_identicas"][t]:
            informe.setdefault("diferencias_huella", {})[t] = bid._diferencias_huella(
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
        bid.bed.bfd.bdd.azd.local(args[0], _salida_fuera_del_repo(args[1]))
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
