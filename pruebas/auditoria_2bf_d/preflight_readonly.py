"""Hito 2BF-D: preflight, captura y postchecks ESTRICTAMENTE READ_ONLY de la migracion 23 y de la
aplicacion de la aprobacion de 279410.

Uso (identidad Windows Usuari; conexion CONTROLFARMACIAS_SUPABASE_DB_URL; sin Farmatic):
  python -B pruebas/auditoria_2bf_d/preflight_readonly.py precondiciones <salida.json>
  python -B pruebas/auditoria_2bf_d/preflight_readonly.py local <22|23> <salida.json>
  python -B pruebas/auditoria_2bf_d/preflight_readonly.py alcance <local_22.json> <local_23.json> <salida.json>
  python -B pruebas/auditoria_2bf_d/preflight_readonly.py captura <pre|post|post_aplicar> <salida.json>
  python -B pruebas/auditoria_2bf_d/preflight_readonly.py comparar_pre <pre.json> <local_22.json> <alcance.json> <salida.json>
  python -B pruebas/auditoria_2bf_d/preflight_readonly.py comparar_despliegue <pre.json> <post.json> <local_23.json> <alcance.json> <salida.json>
  python -B pruebas/auditoria_2bf_d/preflight_readonly.py comparar_aplicacion <post.json> <post_aplicar.json> <salida.json>

Puerta certificada del 2AT (``pruebas/auditoria_2at/auditoria_readonly.py``): project ref demostrado, sesion
READ_ONLY REPEATABLE READ, solo SELECT/WITH, rollback. Salidas FUERA del repositorio. Sin DML, sin RPC, sin
Farmatic. Tareas programadas: solo ``Get-ScheduledTaskInfo``. Patron de ``pruebas/auditoria_2bd_d`` (esquema,
alcance local, criterio 2AX) y de ``pruebas/auditoria_2bd_ro`` (historial y albaranes por fila).

- El alcance de la 23 no se escribe a mano: objetos cuya huella difiere entre las referencias locales 22 y 23.
- ``comparar_despliegue`` (criterio 2AX): solo cambia el alcance; el alcance queda igual a la referencia 23;
  fuera de alcance identico; datos (huella por fila de todas las tablas, historial y reservas), operacion y
  configuracion identicos; aprobaciones y aplicaciones vacias.
- ``comparar_aplicacion``: entre la captura posterior al despliegue y la posterior a ``aplicar`` solo puede
  cambiar la fila de 279410 (``numero_albaran``, ``id_proveedor``, ``fecha_actualizacion``) con los valores
  aprobados, y aparecer exactamente una aprobacion (la de ``aprobacion_279410.json``) y su aplicacion, que
  resuelve las revisiones ``CAMBIO_IDENTIDAD`` pendientes de 279410. Todo lo demas, identico.
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
from src.supabase_client.resincronizacion_albaranes import id_proveedor_comparable  # noqa: E402

_spec = importlib.util.spec_from_file_location("preflight_2bdd", ROOT / "pruebas/auditoria_2bd_d/preflight_readonly.py")
bdd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bdd)

SQL_ESQUEMA = bdd.SQL_ESQUEMA
SQL_RESERVAS = bdd.SQL_RESERVAS
SQL_VIGENTES = bdd.SQL_VIGENTES
_md5 = bdd._md5
_clave = bdd._clave
_tareas = bdd._tareas
_puertas_tareas = bdd._puertas_tareas

SCRIPT_DESPLIEGUE = ROOT / "pruebas/auditoria_2bf/desplegar_23.py"
APROBACION = json.loads((ROOT / "pruebas/auditoria_2bf/aprobacion_279410.json").read_text(encoding="utf-8"))
FARMACIA = APROBACION["farmacia"]
ALBARAN = int(APROBACION["id_contador"])
CAMPOS_APLICACION = {"numero_albaran", "id_proveedor", "fecha_actualizacion"}
# Tablas con huella por fila (clave = id): las del 2AZ-D (incluye albaranes) y el historial de la 22.
TABLAS_HUELLA = (*bdd.TABLAS_HUELLA, "albaranes_cambios")

MARCAS = (
    "select jsonb_build_object("
    "'22_tabla_cambios', to_regclass('public.albaranes_cambios') is not null,"
    "'22_rpc_resincronizar', to_regprocedure('public.cf_resincronizar_albaran(text,bigint,jsonb,text,text)') is not null,"
    "'23_tabla_aprobaciones', to_regclass('public.albaranes_aprobaciones') is not null,"
    "'23_tabla_aplicadas', to_regclass('public.albaranes_aprobaciones_aplicadas') is not null,"
    "'23_rpc_registrar', to_regprocedure("
    "  'public.cf_registrar_aprobacion_albaran(text,bigint,jsonb,text,timestamptz,text,text)') is not null,"
    "'23_rpc_aplicar', to_regprocedure('public.cf_aplicar_aprobacion_albaran(bigint,jsonb,text)') is not null,"
    "'23_resync_solo_pendientes', position('cf_revision_albaran_pendiente' in pg_get_functiondef("
    "  'public.cf_resincronizar_albaran(text,bigint,jsonb,text,text)'::regprocedure)) > 0)::text"
)
MARCAS_22 = ("22_tabla_cambios", "22_rpc_resincronizar")
MARCAS_23 = ("23_tabla_aprobaciones", "23_tabla_aplicadas", "23_rpc_registrar", "23_rpc_aplicar",
             "23_resync_solo_pendientes")


def cambio_aprobado() -> list[dict]:
    """El cambio tal como lo guarda ``cf_registrar_aprobacion_albaran`` (ordenado por campo, btrim)."""
    return sorted(({"campo": c["campo"], "anterior": c["anterior"].strip(), "nuevo": c["nuevo"].strip()}
                   for c in APROBACION["cambio"]), key=lambda c: c["campo"])


def _comparable(campo: str, valor):
    return id_proveedor_comparable(valor) if campo == "id_proveedor" else (valor or "").strip()


# --------------------------------------------------------------------------- precondiciones (norma 2AX)

def sql_precondiciones() -> str:
    """La consulta de precondiciones de ``desplegar_23.py`` (texto exacto, extraido por ast)."""
    arbol = ast.parse(SCRIPT_DESPLIEGUE.read_text(encoding="utf-8"))
    [consulta] = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"
                  and n.args and "has_table_privilege" in ast.unparse(n.args[0])
                  and "to_regclass('public.albaranes_aprobaciones') is null" in ast.unparse(n.args[0])]
    return eval(compile(ast.Expression(consulta.args[0]), str(SCRIPT_DESPLIEGUE), "eval"), {})


def precondiciones(salida: Path) -> int:
    sql = sql_precondiciones()
    _, datos = _ejecutar_lectura(lambda lector: {"precondiciones": list(lector.fila(sql))})
    datos["sql"] = sql
    datos["veredicto"] = "PRECONDICIONES_OK" if all(datos["precondiciones"]) else "PRECONDICIONES_NO_CUMPLIDAS"
    print(json.dumps({k: datos[k] for k in ("project_ref", "capturado_utc", "transaction_read_only",
                                            "precondiciones", "veredicto")}, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if all(datos["precondiciones"]) else 3


# --------------------------------------------------------------------------- referencia local y alcance

def alcance(local22_ruta: Path, local23_ruta: Path, salida: Path) -> int:
    a = json.loads(local22_ruta.read_text(encoding="utf-8"))["esquema"]["objetos"]
    b = json.loads(local23_ruta.read_text(encoding="utf-8"))["esquema"]["objetos"]
    claves = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    datos = {"alcance_23": claves, "nuevos": sorted(set(b) - set(a)), "eliminados": sorted(set(a) - set(b))}
    print(json.dumps(datos, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, datos))
    return 0 if claves and not datos["eliminados"] else 3


# --------------------------------------------------------------------------- captura

def _filas_json(lector: _Lector, sql: str) -> list[dict]:
    return [json.loads(r[0]) for r in lector.filas(sql)]


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
    out["albaran_objetivo"] = _filas_json(
        lector, f"select to_jsonb(a)::text from public.albaranes a where farmacia = '{FARMACIA}' "
                f"and id_contador = {ALBARAN}")
    out["cambios_objetivo"] = _filas_json(
        lector, f"select to_jsonb(c)::text from public.albaranes_cambios c where farmacia = '{FARMACIA}' "
                f"and id_contador = {ALBARAN} order by id")
    if out["marcas"]["23_tabla_aprobaciones"]:
        out["aprobaciones"] = _filas_json(
            lector, "select to_jsonb(a)::text from public.albaranes_aprobaciones a order by id")
    if out["marcas"]["23_tabla_aplicadas"]:
        out["aplicadas"] = _filas_json(
            lector, "select to_jsonb(p)::text from public.albaranes_aprobaciones_aplicadas p order by aprobacion_id")
    return out


def captura(fase: str, salida: Path) -> int:
    if fase not in ("pre", "post", "post_aplicar"):
        raise SystemExit("fase debe ser pre, post o post_aplicar")
    tareas = _tareas()
    import datetime as _dt
    ahora_tareas = _dt.datetime.now(_dt.timezone.utc)
    _, datos = _ejecutar_lectura(_leer)
    datos.update({"fase": fase, "tareas": tareas, "tareas_consultadas_utc": ahora_tareas.isoformat()})
    marcas = datos["marcas"]
    fallos = [f"MIGRACION_22_AUSENTE:{k}" for k in MARCAS_22 if not marcas[k]]
    if fase == "pre":
        fallos += [f"MIGRACION_23_YA_PRESENTE:{k}" for k in MARCAS_23 if marcas[k]]
        fallos += _puertas_tareas(tareas, ahora_tareas)
    else:
        fallos += [f"MIGRACION_23_AUSENTE:{k}" for k in MARCAS_23 if not marcas[k]]
    if fase == "post" and (datos.get("aprobaciones") or datos.get("aplicadas")):
        fallos.append(f"APROBACIONES_NO_VACIAS:{len(datos.get('aprobaciones', []))}/{len(datos.get('aplicadas', []))}")
    if sorted(_clave(r) for r in datos["reservas"]) != sorted(_clave(r) for r in datos["lineas_vigentes_con_albaran"]):
        fallos.append("RESERVAS_DISTINTAS_DE_VIGENTES_CON_ALBARAN")
    if datos["esquema"]["owner_distinto_de_postgres"]:
        fallos.append(f"OWNER_DISTINTO_DE_POSTGRES:{datos['esquema']['owner_distinto_de_postgres']}")
    fallos += _puertas_operacion(datos["operacion"])
    if datos["locks_factura"]:
        fallos.append(f"LOCKS_FACTURA:{datos['locks_factura']}")
    if len(datos["albaran_objetivo"]) != 1:
        fallos.append(f"ALBARAN_{ALBARAN}_NO_UNICO:{len(datos['albaran_objetivo'])}")
    datos["fallos"] = fallos
    datos["veredicto"] = "CAPTURA_OK" if not fallos else "PARADO"
    sha = _escribir(salida, datos)
    resumen = {k: datos.get(k) for k in ("project_ref", "capturado_utc", "current_user", "fase", "marcas",
                                         "locks_factura", "albaran_objetivo", "fallos", "veredicto")}
    resumen.update({"flags": datos["operacion"]["flags"], "conteos": datos["operacion"]["conteos"],
                    "reservas": len(datos["reservas"]), "objetos_publicos": len(datos["esquema"]["objetos"]),
                    "filas_por_tabla": {t: len(v) for t, v in datos["huellas_por_fila"].items()},
                    "revisiones_objetivo": [(c["campo"], c["valor_anterior"], c["valor_nuevo"], c["accion"])
                                            for c in datos["cambios_objetivo"]],
                    "aprobaciones": len(datos.get("aprobaciones", [])), "aplicadas": len(datos.get("aplicadas", [])),
                    "tareas": tareas})
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


# --------------------------------------------------------------------------- comparaciones (sin conexion)

def _leer_json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _diferencias_huella(x: dict, y: dict) -> dict:
    return {"nuevas": sorted(set(y) - set(x))[:50], "borradas": sorted(set(x) - set(y))[:50],
            "cambiadas": sorted(k for k in set(x) & set(y) if x[k] != y[k])[:50]}


def comparar_pre(pre_ruta: Path, local22_ruta: Path, alcance_ruta: Path, salida: Path) -> int:
    """Produccion esta en el esquema 22 para todo el alcance de la 23."""
    pre = _leer_json(pre_ruta)
    ref = _leer_json(local22_ruta)["esquema"]["objetos"]
    claves = _leer_json(alcance_ruta)["alcance_23"]
    b = pre["esquema"]["objetos"]
    informe = {"alcance_23_igual_a_local_22": {k: _md5(b.get(k)) == _md5(ref.get(k)) for k in claves},
               "captura_pre_ok": pre.get("veredicto") == "CAPTURA_OK"}
    ok = all(informe["alcance_23_igual_a_local_22"].values()) and informe["captura_pre_ok"]
    informe["veredicto"] = "ESQUEMA_22_CONFIRMADO" if ok else "ESQUEMA_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


def comparar_despliegue(pre_ruta: Path, post_ruta: Path, local23_ruta: Path, alcance_ruta: Path,
                        salida: Path) -> int:
    """Criterio de postcheck de REGLAS_CRITICAS (2AX) mas datos intactos."""
    pre, post = _leer_json(pre_ruta), _leer_json(post_ruta)
    ref = _leer_json(local23_ruta)["esquema"]["objetos"]
    claves = _leer_json(alcance_ruta)["alcance_23"]
    a, b = pre["esquema"]["objetos"], post["esquema"]["objetos"]
    cambiados = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    informe = {
        "c1_solo_cambia_el_alcance": set(cambiados) <= set(claves), "objetos_cambiados": cambiados,
        "c2_alcance_igual_a_local_23": {k: _md5(b.get(k)) == _md5(ref.get(k)) for k in claves},
        "c3_fuera_de_alcance_identicos": all(_md5(a.get(k)) == _md5(b.get(k)) for k in set(a) | set(b)
                                             if k not in claves),
        "default_acl_identico": pre["esquema"]["default_acl"] == post["esquema"]["default_acl"],
        "cf_configuracion_identica": pre["cf_configuracion_completa"] == post["cf_configuracion_completa"],
        "huellas_identicas": {t: pre["huellas_por_fila"][t] == post["huellas_por_fila"][t] for t in TABLAS_HUELLA},
        "operacion_identica": pre["operacion"] == post["operacion"] and pre["locks_factura"] == post["locks_factura"],
        "reservas_pre_igual_post": pre["reservas"] == post["reservas"],
        "albaran_objetivo_identico": pre["albaran_objetivo"] == post["albaran_objetivo"],
        "aprobaciones_vacias": post.get("aprobaciones") == [] and post.get("aplicadas") == [],
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


def comparar_aplicacion(pre_ruta: Path, post_ruta: Path, salida: Path) -> int:
    """Desde la captura posterior al despliegue: solo la aprobacion de 279410 y su aplicacion."""
    pre, post = _leer_json(pre_ruta), _leer_json(post_ruta)
    problemas: list[str] = []
    [antes] = pre["albaran_objetivo"] or [None]
    [despues] = post["albaran_objetivo"] or [None]
    if antes is None or despues is None:
        problemas.append("ALBARAN_OBJETIVO_AUSENTE")
        antes, despues = antes or {}, despues or {}
    campos = sorted(k for k in set(antes) | set(despues) if antes.get(k) != despues.get(k))
    if not set(campos) <= CAMPOS_APLICACION or not {"numero_albaran", "id_proveedor"} <= set(campos):
        problemas.append(f"CAMPOS_CAMBIADOS_INESPERADOS:{campos}")
    for c in cambio_aprobado():
        if (_comparable(c["campo"], antes.get(c["campo"])) != _comparable(c["campo"], c["anterior"])
                or _comparable(c["campo"], despues.get(c["campo"])) != _comparable(c["campo"], c["nuevo"])):
            problemas.append(f"VALOR_NO_APROBADO:{c['campo']}:{antes.get(c['campo'])}->{despues.get(c['campo'])}")

    if pre["esquema"] != post["esquema"]:
        problemas.append("ESQUEMA_DISTINTO")
    if pre["cf_configuracion_completa"] != post["cf_configuracion_completa"] or pre["operacion"] != post["operacion"] \
            or pre["locks_factura"] != post["locks_factura"]:
        problemas.append("OPERACION_O_CONFIGURACION_DISTINTA")
    if pre["reservas"] != post["reservas"]:
        problemas.append("RESERVAS_DISTINTAS")
    diferencias = {}
    for t in TABLAS_HUELLA:
        x, y = pre["huellas_por_fila"][t], post["huellas_por_fila"][t]
        permitidas = {str(antes.get("id"))} if t == "albaranes" else set()
        dif = _diferencias_huella(x, y)
        if dif["nuevas"] or dif["borradas"] or set(dif["cambiadas"]) - permitidas:
            diferencias[t] = dif
    if diferencias:
        problemas.append(f"HUELLAS_DISTINTAS:{sorted(diferencias)}")

    ids_pre = {a["id"] for a in pre.get("aprobaciones", [])}
    nuevas = [a for a in post.get("aprobaciones", []) if a["id"] not in ids_pre]
    previas_alteradas = [a for a in pre.get("aprobaciones", []) if a not in post.get("aprobaciones", [])]
    aprobacion = nuevas[0] if len(nuevas) == 1 else None
    if aprobacion is None or previas_alteradas:
        problemas.append(f"APROBACIONES_INESPERADAS:{len(nuevas)} nuevas, {len(previas_alteradas)} alteradas")
    elif ((aprobacion["farmacia"], int(aprobacion["id_contador"]), aprobacion["motivo"], aprobacion["aprobado_por"])
          != (FARMACIA, ALBARAN, "CAMBIO_IDENTIDAD", APROBACION["aprobado_por"])
          or aprobacion["cambio"] != cambio_aprobado()):
        problemas.append("APROBACION_DISTINTA_DE_LA_APROBADA")

    ids_aplicadas_pre = {p["aprobacion_id"] for p in pre.get("aplicadas", [])}
    aplicadas = [p for p in post.get("aplicadas", []) if p["aprobacion_id"] not in ids_aplicadas_pre]
    pendientes = sorted(c["id"] for c in pre["cambios_objetivo"]
                        if c["accion"] == "REVISION" and c["motivo"] == "CAMBIO_IDENTIDAD")
    if len(aplicadas) != 1 or [p for p in pre.get("aplicadas", []) if p not in post.get("aplicadas", [])]:
        problemas.append(f"APLICACIONES_INESPERADAS:{len(aplicadas)}")
    else:
        aplicada = aplicadas[0]
        if aprobacion is not None and aplicada["aprobacion_id"] != aprobacion["id"]:
            problemas.append("APLICACION_DE_OTRA_APROBACION")
        if sorted(aplicada["revisiones_resueltas"]) != pendientes or not pendientes:
            problemas.append(f"REVISIONES_RESUELTAS_INESPERADAS:{aplicada['revisiones_resueltas']}!={pendientes}")
        if aplicada["valores_nuevos"] != {"numero_albaran": despues.get("numero_albaran"),
                                          "id_proveedor": despues.get("id_proveedor")}:
            problemas.append("VALORES_NUEVOS_NO_COINCIDEN_CON_EL_ALBARAN")

    informe = {
        "veredicto": "APLICACION_OK" if not problemas else "APLICACION_REVISAR",
        "problemas": problemas,
        "albaran": {"antes": {c: antes.get(c) for c in sorted(CAMPOS_APLICACION | {"proveedor"})},
                    "despues": {c: despues.get(c) for c in sorted(CAMPOS_APLICACION | {"proveedor"})},
                    "campos_cambiados": campos},
        "aprobacion": aprobacion, "aplicaciones": aplicadas, "revisiones_pendientes_pre": pendientes,
        "diferencias_huella": diferencias,
        "pre": {"capturado_utc": pre.get("capturado_utc"), "fase": pre.get("fase")},
        "post": {"capturado_utc": post.get("capturado_utc"), "fase": post.get("fase")},
    }
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=str))
    print("sha256", _escribir(salida, informe))
    return 0 if not problemas else 3


if __name__ == "__main__":
    modo, args = sys.argv[1], sys.argv[2:]
    if modo == "precondiciones":
        sys.exit(precondiciones(_salida_fuera_del_repo(args[0])))
    elif modo == "local":
        bdd.azd.local(args[0], _salida_fuera_del_repo(args[1]))
    elif modo == "alcance":
        sys.exit(alcance(Path(args[0]), Path(args[1]), _salida_fuera_del_repo(args[2])))
    elif modo == "captura":
        sys.exit(captura(args[0], _salida_fuera_del_repo(args[1])))
    elif modo == "comparar_pre":
        sys.exit(comparar_pre(Path(args[0]), Path(args[1]), Path(args[2]), _salida_fuera_del_repo(args[3])))
    elif modo == "comparar_despliegue":
        sys.exit(comparar_despliegue(Path(args[0]), Path(args[1]), Path(args[2]), Path(args[3]),
                                     _salida_fuera_del_repo(args[4])))
    elif modo == "comparar_aplicacion":
        sys.exit(comparar_aplicacion(Path(args[0]), Path(args[1]), _salida_fuera_del_repo(args[2])))
    else:
        raise SystemExit("modo desconocido")
