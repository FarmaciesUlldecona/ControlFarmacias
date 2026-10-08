"""Hito 2AZ-D: preflight, backup, auditoria y postcheck ESTRICTAMENTE READ_ONLY de la migracion 20.

Uso:
  python -B pruebas/auditoria_2az_d/preflight_readonly.py columnas <salida.json>
  python -B pruebas/auditoria_2az_d/preflight_readonly.py remoto <columnas_declaradas.json> <salida.json>
  python -B pruebas/auditoria_2az_d/preflight_readonly.py local <variante 19|20> <salida.json>
  python -B pruebas/auditoria_2az_d/preflight_readonly.py funcional <salida.json>
  python -B pruebas/auditoria_2az_d/preflight_readonly.py comparar <pre.json> <post.json> <local_20.json> <salida.json>

``remoto`` usa la puerta certificada del 2AT (project ref demostrado, sesion READ_ONLY
REPEATABLE READ, solo SELECT/WITH, rollback) y vuelca: marcas de migraciones,
huella de esquema por objeto de ``public``, objetos del alcance de la 20,
privilegios por defecto, cf_configuracion completa, operacion y conteos, tareas,
08B96275, auditoria de las conciliaciones y huellas por fila sobre columnas
declaradas antes de ejecutar (fichero ``columnas_declaradas.json``).
``local`` calcula el mismo bloque de esquema en PostgreSQL 17 local (contenedor
desechable sin red) para las variantes 19 y 20. ``funcional`` prueba privilegios
con SET LOCAL ROLE dentro de una transaccion READ_ONLY. ``comparar`` no se
conecta a nada. No hay DML ni RPC de escritura. Sin Farmatic.
"""
from __future__ import annotations

import json
import sys
import uuid
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import (  # noqa: E402
    _Lector, _ejecutar_lectura, _escribir, _operacion, _puertas_operacion, _puertas_tareas, _salida_fuera_del_repo,
    _simular, _tareas)

TABLAS_HUELLA = ("facturas", "conciliaciones", "conciliacion_detalles", "facturas_vencimientos",
                 "facturas_albaranes_extraidos", "facturas_movimientos", "historial_facturas",
                 "documentos_facturas", "albaranes")
ALCANCE = ("funcion:cf_persistir_conciliacion(uuid,text,text,text,jsonb)",
           "funcion:cf_enriquecer_factura(uuid,text,text,jsonb)", "tabla:cf_configuracion")

MARCAS = (
    "select jsonb_build_object("
    "'15_multifactura_7', to_regprocedure('public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)') is not null,"
    "'16_manual', to_regprocedure('public.cf_reclamar_documento_normalizacion_manual_one_shot(text,integer)') is not null,"
    "'17_replay', to_regprocedure('public.cf_cerrar_replay_normalizacion(uuid,text,uuid,text)') is not null,"
    "'18_nucleo', to_regprocedure('public.cf_reclamar_factura_conciliacion_nucleo(text,integer,text)') is not null,"
    "'18_idempotency', exists(select 1 from information_schema.columns where table_schema='public' "
    "  and table_name='conciliaciones' and column_name='idempotency_key'),"
    "'19_anon_sin_select_facturas', not has_table_privilege('anon','public.facturas','SELECT'),"
    "'19_service_role_sin_update_facturas', not has_table_privilege('service_role','public.facturas','UPDATE'),"
    "'20_ausente_columna', not exists(select 1 from information_schema.columns where table_schema='public' "
    "  and table_name='cf_configuracion' and column_name='conciliacion_tolerancia_suelo'),"
    "'20_ausente_rpc', to_regprocedure('public.cf_enriquecer_factura(uuid,text,text,jsonb)') is null)::text"
)

# Huella de esquema por objeto de public: definicion, propietario, ACL efectiva normalizada, RLS.
SQL_ESQUEMA = r"""
with acl as (
  select o.oid, o.tipo, coalesce(jsonb_agg(jsonb_build_array(coalesce(r.rolname, 'PUBLIC'), a.privilege_type)
           order by coalesce(r.rolname, 'PUBLIC'), a.privilege_type), '[]'::jsonb) as acl
    from (select c.oid, 'rel' as tipo, coalesce(c.relacl, acldefault(case when c.relkind = 'S' then 's'::"char"
                 else 'r'::"char" end, c.relowner)) as a from pg_class c
           where c.relnamespace = 'public'::regnamespace and c.relkind in ('r','p','v','m','S','f')
          union all
          select p.oid, 'fun', coalesce(p.proacl, acldefault('f', p.proowner)) from pg_proc p
           where p.pronamespace = 'public'::regnamespace) o
    cross join lateral aclexplode(o.a) a
    left join pg_roles r on r.oid = a.grantee
   group by o.oid, o.tipo
), objetos as (
  select 'funcion:' || replace(p.oid::regprocedure::text, 'public.', '') as clave,
         jsonb_build_object('def', replace(pg_get_functiondef(p.oid), chr(13), ''),
                            'definer', p.prosecdef, 'owner', pg_get_userbyid(p.proowner),
                            'acl', (select acl from acl where acl.oid = p.oid and acl.tipo = 'fun')) as obj
    from pg_proc p where p.pronamespace = 'public'::regnamespace
     and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
  union all
  select case c.relkind when 'v' then 'vista:' when 'm' then 'vista_materializada:' when 'S' then 'secuencia:'
              else 'tabla:' end || c.relname,
         jsonb_build_object(
           'owner', pg_get_userbyid(c.relowner), 'rls', c.relrowsecurity,
           'acl', (select acl from acl where acl.oid = c.oid and acl.tipo = 'rel'),
           'columnas', (select coalesce(jsonb_agg(jsonb_build_array(a.attname, format_type(a.atttypid, a.atttypmod),
                          a.attnotnull, pg_get_expr(d.adbin, d.adrelid)) order by a.attnum), '[]'::jsonb)
                          from pg_attribute a left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
                         where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped),
           'constraints', (select coalesce(jsonb_object_agg(conname, pg_get_constraintdef(oid)), '{}'::jsonb)
                             from pg_constraint where conrelid = c.oid),
           'indices', (select coalesce(jsonb_object_agg(indexrelid::regclass::text, pg_get_indexdef(indexrelid)), '{}'::jsonb)
                         from pg_index where indrelid = c.oid),
           'vista', case when c.relkind in ('v','m') then md5(pg_get_viewdef(c.oid)) end,
           'politicas', (select coalesce(jsonb_object_agg(polname, jsonb_build_array(polcmd::text,
                           pg_get_expr(polqual, polrelid), pg_get_expr(polwithcheck, polrelid))), '{}'::jsonb)
                           from pg_policy where polrelid = c.oid))
    from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind in ('r','p','v','m','S','f')
)
select jsonb_build_object(
  'objetos', (select jsonb_object_agg(clave, obj) from objetos),
  'default_acl', (select coalesce(jsonb_agg(jsonb_build_array(pg_get_userbyid(defaclrole),
                    case when defaclnamespace = 0 then '*' else defaclnamespace::regnamespace::text end,
                    defaclobjtype::text, defaclacl::text) order by 1, 2, 3), '[]'::jsonb) from pg_default_acl
                    where defaclnamespace in (0, 'public'::regnamespace)),
  'owner_distinto_de_postgres', (select coalesce(jsonb_agg(clave), '[]'::jsonb) from objetos
                                   where obj->>'owner' <> 'postgres'))::text
"""


def _md5(obj) -> str:
    import hashlib
    return hashlib.md5(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _columnas(lector: _Lector) -> dict:
    return {t: [r[0] for r in lector.filas(
        "select column_name::text from information_schema.columns where table_schema = 'public' "
        "and table_name = %s order by ordinal_position", (t,))] for t in TABLAS_HUELLA}


# --------------------------------------------------------------------------- auditoria 1.6

def _auditoria(lector: _Lector) -> dict:
    detalles = [json.loads(r[0]) for r in lector.filas(
        "select jsonb_build_object('conciliacion_id', c.id::text, 'factura_id', c.factura_id::text, "
        "'numero_factura', f.numero_factura, 'es_actual', c.es_actual, 'disparador', c.disparador, "
        "'resultado', c.resultado, 'estado_factura', f.estado_conciliacion_cf, 'orden', d.orden, "
        "'tipo_relacion', d.tipo_relacion, 'importe_aplicado', d.importe_aplicado::text, "
        "'numero_documental', coalesce(e.numero_albaran, d.numero_albaran_documental, d.provenance->>'numero_documental'), "
        "'importe_documental', e.importe_total::text, 'albaran_farmacia', d.albaran_farmacia, "
        "'albaran_id_contador', d.albaran_id_contador, 'numero_farmatic', a.numero_albaran, "
        "'puc', a.importe_puc::text, 'pvp', a.importe_pvp::text, "
        "'coincidencia_registrada', d.provenance->>'coincidencia_numero', "
        "'movimiento', d.factura_movimiento_id is not null)::text "
        "from public.conciliaciones c join public.facturas f on f.id = c.factura_id "
        "join public.conciliacion_detalles d on d.conciliacion_id = c.id "
        "left join public.facturas_albaranes_extraidos e on e.id = d.factura_albaran_extraido_id "
        "left join public.albaranes a on a.farmacia = d.albaran_farmacia and a.id_contador = d.albaran_id_contador "
        "order by f.numero_factura, c.intento, d.orden")]
    from src.facturas.runtime_supabase.conciliacion import normalizar_numero_albaran

    usos = defaultdict(set)
    for d in detalles:
        if d["albaran_id_contador"] is not None:
            usos[(d["albaran_farmacia"], d["albaran_id_contador"])].add((d["conciliacion_id"], d["orden"]))
            d["usos_mismo_albaran"] = None
    for d in detalles:
        clave = (d["albaran_farmacia"], d["albaran_id_contador"])
        if d["movimiento"]:
            d["clase"] = "MOVIMIENTO"
        elif d["albaran_id_contador"] is None:
            d["clase"] = "SIN_COINCIDENCIA"
        else:
            exacto = (normalizar_numero_albaran(d["numero_documental"]) == normalizar_numero_albaran(d["numero_farmatic"])
                      and d["numero_documental"] is not None)
            aplicado = abs(Decimal(d["importe_aplicado"]))
            casa = lambda v: v is not None and abs(abs(Decimal(v)) - aplicado) == 0  # noqa: E731
            d["clase"] = ("NUMERO_EXACTO" if exacto else "PUC_NUMERO_DISTINTO" if casa(d["puc"])
                          else "PVP_NUMERO_DISTINTO" if casa(d["pvp"]) else "OTRA")
            d["usos_mismo_albaran"] = len(usos[clave])
    por_conciliacion: dict = {}
    for d in detalles:
        c = por_conciliacion.setdefault(d["conciliacion_id"], {
            "conciliacion_id": d["conciliacion_id"], "factura_id": d["factura_id"], "numero_factura": d["numero_factura"],
            "es_actual": d["es_actual"], "disparador": d["disparador"], "resultado": d["resultado"],
            "estado_factura": d["estado_factura"], "clases": defaultdict(int), "d12": [], "evidencias_d11": []})
        c["clases"][d["clase"]] += 1
        if (d.get("usos_mismo_albaran") or 0) > 1:
            c["d12"].append([d["numero_documental"], d["numero_farmatic"], d["albaran_id_contador"], d["usos_mismo_albaran"]])
        if d["clase"] in ("PVP_NUMERO_DISTINTO", "OTRA"):
            c["evidencias_d11"].append([d["numero_documental"], d["importe_documental"], d["numero_farmatic"],
                                        d["puc"], d["pvp"], d["importe_aplicado"], d["clase"]])
    # Albaranes usados en mas de una conciliacion VIGENTE (es_actual) o en mas de una linea de ella.
    vigentes = defaultdict(list)
    for d in detalles:
        if d["es_actual"] and d["albaran_id_contador"] is not None:
            vigentes[(d["albaran_farmacia"], d["albaran_id_contador"])].append([d["numero_factura"], d["orden"]])
    d12_vigentes = {f"{k[0]}:{k[1]}": v for k, v in vigentes.items() if len(v) > 1}
    simulaciones = {}
    for factura_id in sorted({c["factura_id"] for c in por_conciliacion.values() if c["es_actual"]}):
        try:
            s = _simular(lector, factura_id)
            simulaciones[factura_id] = {k: s.get(k) for k in ("camino", "resultado", "importe_explicado", "diferencia",
                                                             "tolerancia", "resumen_detalles", "fallo")}
        except Exception as exc:  # informativo
            simulaciones[factura_id] = {"error": f"{type(exc).__name__}: {exc}"}
    for c in por_conciliacion.values():
        c["clases"] = dict(c["clases"])
        s = simulaciones.get(c["factura_id"]) if c["es_actual"] else None
        c["simulacion_d11_r11"] = s
        d11 = bool(c["evidencias_d11"]) or (s is not None and s.get("resultado") not in (None, c["resultado"]))
        d12 = bool(c["d12"])
        c["clasificacion"] = ("AMBAS" if d11 and d12 else "AFECTADA_D11" if d11 else "AFECTADA_D12" if d12
                              else "CORRECTA")
    return {"conciliaciones": sorted(por_conciliacion.values(), key=lambda c: (c["numero_factura"], c["conciliacion_id"])),
            "d12_albaranes_en_varias_conciliaciones_vigentes": d12_vigentes, "detalles": detalles}


# --------------------------------------------------------------------------- modos remotos

def columnas(salida: Path) -> None:
    _, datos = _ejecutar_lectura(lambda l: {"columnas": _columnas(l)})
    print(json.dumps(datos["columnas"], ensure_ascii=False))
    print("sha256", _escribir(salida, datos))


def remoto(declaradas_ruta: Path, salida: Path) -> int:
    declaradas = json.loads(declaradas_ruta.read_text(encoding="utf-8"))
    tareas = _tareas()

    def leer(lector: _Lector) -> dict:
        out = {"marcas": lector.json(MARCAS), "esquema": lector.json(SQL_ESQUEMA)}
        out.update(_operacion(lector))
        out["cf_configuracion_completa"] = lector.json("select to_jsonb(c)::text from public.cf_configuracion c where id")
        out["conteos_extra"] = {t: lector.valor(f"select count(*) from public.{t}") for t in TABLAS_HUELLA}
        out["locks_factura"] = lector.valor(
            "select count(*) from public.facturas where conciliacion_bloqueado_hasta > now()")
        out["08B96275"] = [json.loads(r[0]) for r in lector.filas(
            "select to_jsonb(a)::text from public.albaranes a where upper(numero_albaran) like '%%96275%%' "
            "or (fecha between date '2026-06-01' and date '2026-06-30' and importe_puc = 6.51)")]
        reales = _columnas(lector)
        out["columnas_huella"] = {t: {"declaradas_ausentes": sorted(set(declaradas[t]) - set(reales[t])),
                                      "reales_no_declaradas": sorted(set(reales[t]) - set(declaradas[t]))}
                                  for t in TABLAS_HUELLA}
        huellas, volcado = {}, {}
        for tabla in TABLAS_HUELLA:
            lista = ", ".join(f"t.{c}" for c in declaradas[tabla] if c in reales[tabla])
            filas = lector.filas(f"select t.id::text, md5(to_jsonb(r)::text), to_jsonb(r)::text from public.{tabla} t "
                                 f"cross join lateral (select {lista}) r order by t.id")
            huellas[tabla] = {f[0]: f[1] for f in filas}
            volcado[tabla] = {f[0]: f[2] for f in filas}
        out["huellas_por_fila"] = huellas
        out["volcado"] = volcado
        out["auditoria_conciliaciones"] = _auditoria(lector)
        return out

    _, datos = _ejecutar_lectura(leer)
    datos["columnas_declaradas"] = declaradas
    datos["tareas"] = tareas
    import datetime as _dt
    fallos = [f"MARCA_FALSA:{k}" for k, v in datos["marcas"].items() if v is not True]
    if datos["esquema"]["owner_distinto_de_postgres"]:
        fallos.append(f"OWNER_DISTINTO_DE_POSTGRES:{datos['esquema']['owner_distinto_de_postgres']}")
    fallos += _puertas_operacion(datos)
    if datos["locks_factura"]:
        fallos.append(f"LOCKS_FACTURA:{datos['locks_factura']}")
    fallos += _puertas_tareas(tareas, _dt.datetime.now(_dt.timezone.utc))
    for t, dif in datos["columnas_huella"].items():
        if dif["declaradas_ausentes"] or dif["reales_no_declaradas"]:
            fallos.append(f"COLUMNAS_HUELLA_NO_COINCIDEN:{t}:{dif}")
    datos["fallos"] = fallos
    sha = _escribir(salida, datos)
    resumen = {k: datos[k] for k in ("project_ref", "capturado_utc", "marcas", "flags", "tolerancia_conciliacion",
                                     "locks_documentos", "locks_factura", "claims_conciliacion", "normalizando",
                                     "workers", "facturas_por_estado_conciliacion_cf", "conteos_extra", "08B96275",
                                     "tareas", "fallos")}
    resumen["owner_distinto_de_postgres"] = datos["esquema"]["owner_distinto_de_postgres"]
    resumen["objetos_publicos"] = len(datos["esquema"]["objetos"])
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


def funcional(salida: Path) -> int:
    def leer(lector: _Lector) -> dict:
        cur = lector._cur
        out = {}
        # service_role: la misma lectura que obtener_configuracion (columnas R11 incluidas).
        cur.execute("savepoint sr; set local role service_role")
        cur.execute("select current_user, normalizacion_automatica, conciliacion_automatica, luna_habilitada, "
                    "farmacias_habilitadas::text, tolerancia_conciliacion::text, conciliacion_tolerancia_suelo::text, "
                    "conciliacion_tolerancia_por_albaran::text, conciliacion_tolerancia_tope::text "
                    "from public.cf_configuracion where id")
        out["service_role_configuracion"] = list(cur.fetchone())
        cur.execute("rollback to savepoint sr")
        cur.execute("savepoint an; set local role anon")
        try:
            cur.execute("select public.cf_enriquecer_factura(gen_random_uuid(), 'x', 'enriquecimiento:x', '{}'::jsonb)")
            out["anon_execute_cf_enriquecer_factura"] = "PERMITIDO"
        except Exception as exc:
            out["anon_execute_cf_enriquecer_factura"] = f"DENEGADO: {str(exc).splitlines()[0]}"
        cur.execute("rollback to savepoint an")
        out["privilegios"] = lector.json(
            "select jsonb_object_agg(f, jsonb_build_object('anon', has_function_privilege('anon', f, 'EXECUTE'), "
            "'authenticated', has_function_privilege('authenticated', f, 'EXECUTE'), "
            "'service_role', has_function_privilege('service_role', f, 'EXECUTE'), "
            "'public', exists(select 1 from pg_proc p cross join lateral aclexplode(p.proacl) a "
            "                 where p.oid = f::regprocedure and a.grantee = 0)))::text "
            "from unnest(array['public.cf_enriquecer_factura(uuid,text,text,jsonb)', "
            "'public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)']) f")
        return out

    _, datos = _ejecutar_lectura(leer)
    print(json.dumps(datos, ensure_ascii=False, indent=1, default=str))
    print("sha256", _escribir(salida, datos))
    return 0


# --------------------------------------------------------------------------- referencia local

def local(variante: str, salida: Path) -> None:
    sys.path.insert(0, str(ROOT / "tests/facturas/runtime_supabase"))
    import pg17_local as pgl

    nombre = "cf-pg17-ref2azd-" + uuid.uuid4().hex[:8]
    pgl._docker("run", "-d", "--rm", "--name", nombre, "--label", "controlfarmacias.certificacion=pg17_local",
                "--network", "none", "--tmpfs", "/var/lib/postgresql/data",
                "-e", "POSTGRES_PASSWORD=local-only", pgl.IMAGEN)
    try:
        import time
        for _ in range(240):
            if pgl._docker("exec", nombre, "psql", "-U", "postgres", "-qAt", "-c", "select 1",
                           comprobar=False).returncode == 0:
                break
            time.sleep(0.5)
        time.sleep(2)
        db = pgl.construir_plantilla(nombre, variante)
        esquema = json.loads(pgl._Pg(nombre, db).sql(SQL_ESQUEMA + ";"))
    finally:
        pgl._docker("rm", "-f", nombre, comprobar=False)
    print("sha256", _escribir(salida, {"variante": variante, "esquema": esquema}))


# --------------------------------------------------------------------------- comparacion

def _alcance(esquema: dict) -> dict:
    return {k: esquema["objetos"].get(k) for k in ALCANCE}


def comparar(pre_ruta: Path, post_ruta: Path, local20_ruta: Path, salida: Path) -> int:
    pre, post = (json.loads(p.read_text(encoding="utf-8")) for p in (pre_ruta, post_ruta))
    ref = json.loads(local20_ruta.read_text(encoding="utf-8"))["esquema"]
    a, b = pre["esquema"]["objetos"], post["esquema"]["objetos"]
    cambiados = sorted(k for k in set(a) | set(b) if _md5(a.get(k)) != _md5(b.get(k)))
    informe = {
        "c1_solo_cambia_el_alcance": set(cambiados) <= set(ALCANCE), "objetos_cambiados": cambiados,
        "c2_alcance_igual_a_local_20": {k: _md5(b.get(k)) == _md5(ref["objetos"].get(k)) for k in ALCANCE},
        "c3_fuera_de_alcance_identicos": all(_md5(a.get(k)) == _md5(b.get(k)) for k in set(a) | set(b) if k not in ALCANCE),
        "default_acl_identico": pre["esquema"]["default_acl"] == post["esquema"]["default_acl"],
        "cf_configuracion_resto_identico": {k: v for k, v in post["cf_configuracion_completa"].items()
                                            if not k.startswith("conciliacion_tolerancia_")} == pre["cf_configuracion_completa"],
        "parametros_r11": {k: v for k, v in post["cf_configuracion_completa"].items()
                           if k.startswith("conciliacion_tolerancia_")},
        "huellas_identicas": {t: pre["huellas_por_fila"][t] == post["huellas_por_fila"][t] for t in TABLAS_HUELLA},
        "operacion_como_antes": {k: pre[k] == post[k] for k in ("flags", "locks_documentos", "claims_conciliacion",
                                                                 "normalizando", "workers", "locks_factura")},
    }
    for t in TABLAS_HUELLA:
        if not informe["huellas_identicas"][t]:
            x, y = pre["huellas_por_fila"][t], post["huellas_por_fila"][t]
            informe.setdefault("diferencias_huella", {})[t] = {
                "nuevas": sorted(set(y) - set(x))[:50], "borradas": sorted(set(x) - set(y))[:50],
                "cambiadas": sorted(k for k in set(x) & set(y) if x[k] != y[k])[:50]}
    ok = (informe["c1_solo_cambia_el_alcance"] and all(informe["c2_alcance_igual_a_local_20"].values())
          and informe["c3_fuera_de_alcance_identicos"] and informe["default_acl_identico"]
          and informe["cf_configuracion_resto_identico"] and all(informe["huellas_identicas"].values())
          and all(informe["operacion_como_antes"].values()))
    informe["veredicto"] = "POSTCHECK_OK" if ok else "POSTCHECK_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=str))
    _escribir(salida, informe)
    return 0 if ok else 3


if __name__ == "__main__":
    modo = sys.argv[1]
    if modo == "columnas":
        columnas(_salida_fuera_del_repo(sys.argv[2]))
    elif modo == "remoto":
        sys.exit(remoto(Path(sys.argv[2]), _salida_fuera_del_repo(sys.argv[3])))
    elif modo == "local":
        local(sys.argv[2], _salida_fuera_del_repo(sys.argv[3]))
    elif modo == "funcional":
        sys.exit(funcional(_salida_fuera_del_repo(sys.argv[2])))
    elif modo == "comparar":
        sys.exit(comparar(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), _salida_fuera_del_repo(sys.argv[5])))
    else:
        raise SystemExit("modo desconocido")
