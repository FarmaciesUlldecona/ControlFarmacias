"""Hito 2BB: preflight, previsualizacion y postcheck ESTRICTAMENTE READ_ONLY del enriquecimiento (R12).

Uso:
  python -B pruebas/auditoria_2bb/enriquecimiento_readonly.py preflight <numero_factura> <dir_pdf_espejo> <salida.json>
  python -B pruebas/auditoria_2bb/enriquecimiento_readonly.py comparar <snapshot_pre.json> <snapshot_post.json> <numero_factura> <salida.json>

``preflight`` lee con la puerta READ_ONLY del 2AT exactamente lo que lee
``RepositorioRuntimeSupabase.datos_para_enriquecer`` (mas estado, claim, vencimientos, historial,
operacion y tareas), localiza el PDF en el espejo local por su SHA-256 registrado, ejecuta el
extractor autorizado del compositor manual EN LOCAL y construye con ``construir_enriquecimiento``
(funcion pura) el payload que enviaria ``enriquecer_una_vez.py``. Para cada albaran nuevo busca
su albaran operacional en ``Supabase.albaranes`` y si esta reservado por otra factura (R15). No
llama a ninguna RPC ni descarga del storage.

``comparar`` no se conecta a nada: compara dos snapshots de
``pruebas/auditoria_2ba_d/preflight_readonly.py remoto post`` y exige que solo cambien filas de
la factura indicada (albaranes extraidos nuevos, vencimientos e historial).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import (  # noqa: E402
    _Lector, _ejecutar_lectura, _escribir, _operacion, _puertas_operacion, _puertas_tareas, _salida_fuera_del_repo,
    _tareas)


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _pdf_por_sha(directorio: Path, nombre: str, sha: str) -> dict:
    """Primero los archivos con el mismo nombre; si ninguno coincide, todos los PDF del espejo."""
    mismos = [p for p in directorio.rglob("*") if p.is_file() and p.name == nombre]
    for p in mismos:
        if _sha256(p) == sha:
            return {"ruta": str(p), "por": "nombre+sha"}
    for p in directorio.rglob("*.pdf"):
        if _sha256(p) == sha:
            return {"ruta": str(p), "por": "sha"}
    return {"ruta": None, "candidatos_por_nombre": [str(p) for p in mismos]}


def preflight(numero: str, espejo: Path, salida: Path) -> int:
    tareas = _tareas()
    ahora_tareas = datetime.now(timezone.utc)

    def leer(lector: _Lector) -> dict:
        out = _operacion(lector)
        [factura_id] = [r[0] for r in lector.filas(
            "select id::text from public.facturas where numero_factura = %s and farmacia = 'PIO'", (numero,))]
        out["factura"] = lector.json(
            "select to_jsonb(r)::text from public.facturas t cross join lateral (select t.id, t.documento_id, "
            "t.farmacia, t.numero_factura, t.fecha_factura, t.importe_total, t.proveedor_cif, t.estado_conciliacion_cf, "
            "t.conciliacion_bloqueado_por, t.conciliacion_bloqueado_hasta, t.datos_extraidos) r where t.id = %s::uuid",
            (factura_id,))
        out["documento"] = lector.json(
            "select to_jsonb(r)::text from public.documentos_facturas t cross join lateral (select t.id, t.farmacia, "
            "t.archivo_ruta, t.archivo_nombre, t.archivo_hash) r where t.id = %s::uuid",
            (out["factura"]["documento_id"],))
        out["albaranes"] = lector.json(
            "select coalesce(jsonb_agg(jsonb_build_object('numero_albaran', numero_albaran) order by orden), "
            "'[]'::jsonb)::text from public.facturas_albaranes_extraidos where factura_id = %s::uuid", (factura_id,))
        out["movimientos"] = lector.json(
            "select coalesce(jsonb_agg(jsonb_build_object('descripcion_literal', descripcion_literal, 'sentido', sentido, "
            "'importe', importe) order by orden), '[]'::jsonb)::text from public.facturas_movimientos "
            "where factura_id = %s::uuid", (factura_id,))
        out["vencimientos"] = lector.json(
            "select coalesce(jsonb_agg(to_jsonb(v) order by v.id), '[]'::jsonb)::text "
            "from public.facturas_vencimientos v where v.factura_id = %s::uuid", (factura_id,))
        out["enriquecimientos_previos"] = lector.valor(
            "select count(*) from public.historial_facturas where factura_id = %s::uuid "
            "and evento = 'FACTURA_ENRIQUECIDA'", (factura_id,))
        out["conciliaciones_de_la_factura"] = lector.valor(
            "select count(*) from public.conciliaciones where factura_id = %s::uuid", (factura_id,))
        out["rpc_cf_enriquecer_factura"] = lector.valor(
            "select to_regprocedure('public.cf_enriquecer_factura(uuid,text,text,jsonb)') is not null")
        out["elegibilidad"] = list(lector.fila(
            "select e.estado, e.razon from public.cf_evaluar_elegibilidad_conciliacion(%s::uuid) e", (factura_id,)))
        return out

    _, datos = _ejecutar_lectura(leer)
    datos["tareas"] = tareas
    fallos = _puertas_operacion(datos) + _puertas_tareas(tareas, ahora_tareas)
    f, doc = datos["factura"], datos["documento"]
    if f["estado_conciliacion_cf"] != "PENDIENTE_CONCILIAR":
        fallos.append(f"FACTURA_NO_PENDIENTE_CONCILIAR:{f['estado_conciliacion_cf']}")
    if f["conciliacion_bloqueado_por"] is not None:
        fallos.append("FACTURA_CON_CLAIM")
    if not datos["rpc_cf_enriquecer_factura"]:
        fallos.append("RPC_CF_ENRIQUECER_FACTURA_AUSENTE")
    if datos["enriquecimientos_previos"]:
        fallos.append(f"ENRIQUECIMIENTOS_PREVIOS:{datos['enriquecimientos_previos']}")

    # Previsualizacion local: mismo extractor y misma funcion pura que el worker.
    pdf = _pdf_por_sha(espejo, doc["archivo_nombre"], doc["archivo_hash"])
    datos["pdf_local"] = pdf
    if pdf["ruta"] is None:
        fallos.append("PDF_LOCAL_CON_SHA_REGISTRADO_NO_ENCONTRADO")
    else:
        from src.facturas.completitud_documental import validar_documento_antes_de_persistir
        from src.facturas.runtime_supabase.compositor_manual import (
            CAMPO_DOCUMENTO, CAMPOS_REQUERIDOS_MANUAL, ExtractorDocumentalAutorizado)
        from src.facturas.runtime_supabase.enriquecimiento import (
            clave_idempotente_enriquecimiento, construir_enriquecimiento)
        etapa = ExtractorDocumentalAutorizado().extraer(Path(pdf["ruta"]), CAMPOS_REQUERIDOS_MANUAL)
        datos["extraccion_motivo"] = etapa.provenance.get("motivo")
        if datos["extraccion_motivo"] != "AUTORIZADO":
            fallos.append(f"EXTRACCION_NO_AUTORIZADA:{datos['extraccion_motivo']}")
        else:
            normalizado = etapa.valores[CAMPO_DOCUMENTO]
            validar_documento_antes_de_persistir(doc["farmacia"], normalizado)
            entrada = {k: datos[k] for k in ("factura", "documento", "albaranes", "movimientos")}
            entrada["factura"] = {**f, "id": str(f["id"]), "documento_id": str(f["documento_id"])}
            payload = construir_enriquecimiento(entrada, normalizado)
            datos["payload_previsto"] = payload
            datos["idempotency_key_prevista"] = clave_idempotente_enriquecimiento(str(f["id"]), payload)
            datos["efecto_previsto"] = {
                "albaranes_nuevos": [{"numero": (a.get("numero") or {}).get("valor"),
                                      "fecha": ((a.get("fecha") or {}).get("valor") or {}).get("iso")
                                      if isinstance((a.get("fecha") or {}).get("valor"), dict)
                                      else (a.get("fecha") or {}).get("valor"),
                                      "base": (a.get("base") or {}).get("valor"),
                                      "total": (a.get("total") or {}).get("valor"),
                                      "tipo": a.get("tipo_pedido") or a.get("descripcion")} for a in payload["albaranes"]],
                "movimientos_nuevos": len(payload["movimientos"]),
                "vencimientos": payload["vencimientos"],
                "identidad": payload["identidad"],
            }

            # R15: albaranes operacionales de los nuevos y si otra factura los tiene reservados.
            def operacionales(lector: _Lector) -> dict:
                res = {}
                for a in datos["efecto_previsto"]["albaranes_nuevos"]:
                    res[a["numero"]] = [json.loads(r[0]) for r in lector.filas(
                        "select jsonb_build_object('id_contador', a.id_contador, 'numero_albaran', a.numero_albaran, "
                        "'fecha', a.fecha::text, 'importe_puc', a.importe_puc::text, 'importe_pvp', a.importe_pvp::text, "
                        "'proveedor', a.proveedor, 'reservado_por', (select f.numero_factura "
                        "  from public.conciliacion_albaranes_reservados r join public.facturas f on f.id = r.factura_id "
                        "  where r.albaran_farmacia = a.farmacia and r.albaran_id_contador = a.id_contador))::text "
                        "from public.albaranes a where a.farmacia = 'PIO' and (upper(a.numero_albaran) = upper(%s) "
                        "  or (abs(a.importe_puc) = abs(%s::numeric) and a.fecha between %s::date - 3 and %s::date + 3)) "
                        "order by a.id_contador", (a["numero"], a["total"], a["fecha"], a["fecha"]))]
                return {"operacionales": res}
            datos["albaranes_operacionales"] = _ejecutar_lectura(operacionales)[1]["operacionales"]
            reservados = {n: [c for c in cs if c["reservado_por"] not in (None, numero)]
                          for n, cs in datos["albaranes_operacionales"].items()}
            if any(reservados.values()):
                fallos.append(f"ALBARAN_RESERVADO_POR_OTRA_FACTURA:{reservados}")
    datos["fallos"] = fallos
    datos["veredicto"] = "PREFLIGHT_OK" if not fallos else "PARADO_EN_PREFLIGHT"
    sha = _escribir(salida, datos)
    resumen = {k: datos.get(k) for k in ("capturado_utc", "flags", "locks_documentos", "claims_conciliacion",
                                         "normalizando", "workers", "rpc_cf_enriquecer_factura",
                                         "enriquecimientos_previos", "conciliaciones_de_la_factura", "elegibilidad",
                                         "vencimientos", "pdf_local", "extraccion_motivo", "efecto_previsto",
                                         "idempotency_key_prevista", "albaranes_operacionales", "fallos", "veredicto")}
    resumen["factura"] = {k: f[k] for k in ("id", "numero_factura", "fecha_factura", "importe_total", "proveedor_cif",
                                            "estado_conciliacion_cf", "conciliacion_bloqueado_por")}
    resumen["documento"] = doc
    resumen["albaranes_actuales"] = len(datos["albaranes"])
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


def comparar(pre_ruta: Path, post_ruta: Path, numero: str, salida: Path) -> int:
    pre, post = (json.loads(p.read_text(encoding="utf-8")) for p in (pre_ruta, post_ruta))
    [factura_id] = [k for k, v in pre["volcado"]["facturas"].items() if json.loads(v).get("numero_factura") == numero]
    informe: dict = {"factura_id": factura_id, "esquema_identico": pre["esquema"] == post["esquema"],
                     "cf_configuracion_identica": pre["cf_configuracion_completa"] == post["cf_configuracion_completa"],
                     "operacion_como_antes": {k: pre[k] == post[k] for k in ("flags", "locks_documentos",
                                              "claims_conciliacion", "normalizando", "workers", "locks_factura")},
                     "reservas_identicas": pre["reservas"] == post["reservas"], "tablas": {}}
    ajenas = []
    for tabla, x in pre["huellas_por_fila"].items():
        y = post["huellas_por_fila"][tabla]
        nuevas, borradas = sorted(set(y) - set(x)), sorted(set(x) - set(y))
        cambiadas = sorted(k for k in set(x) & set(y) if x[k] != y[k])

        def duena(fila_id: str, volcado: dict) -> str | None:
            fila = json.loads(volcado[tabla][fila_id])
            return str(fila.get("factura_id") or (fila_id if tabla == "facturas" else "")) or None

        detalle = {"nuevas": [[i, duena(i, post["volcado"])] for i in nuevas],
                   "borradas": [[i, duena(i, pre["volcado"])] for i in borradas],
                   "cambiadas": [[i, duena(i, post["volcado"])] for i in cambiadas]}
        if nuevas or borradas or cambiadas:
            informe["tablas"][tabla] = detalle
        ajenas += [(tabla, k, i) for k in ("nuevas", "borradas", "cambiadas") for i, d in detalle[k] if d != factura_id]
        if tabla == "facturas_albaranes_extraidos":
            informe["albaranes_nuevos"] = [json.loads(post["volcado"][tabla][i]) for i in nuevas]
        if tabla == "facturas_vencimientos":
            informe["vencimientos_cambiados"] = [[json.loads(pre["volcado"][tabla][i]), json.loads(post["volcado"][tabla][i])]
                                                 for i in cambiadas]
        if tabla == "historial_facturas":
            informe["historial_nuevo"] = [json.loads(post["volcado"][tabla][i]) for i in nuevas]
    informe["filas_ajenas_a_la_factura"] = ajenas
    esperado = {"facturas_albaranes_extraidos": "nuevas", "facturas_vencimientos": "cambiadas", "historial_facturas": "nuevas"}
    informe["solo_tablas_esperadas"] = all(
        t in esperado and not any(v for k, v in d.items() if k != esperado[t]) for t, d in informe["tablas"].items())
    ok = (informe["esquema_identico"] and informe["cf_configuracion_identica"]
          and all(informe["operacion_como_antes"].values()) and informe["reservas_identicas"]
          and not ajenas and informe["solo_tablas_esperadas"])
    informe["veredicto"] = "POSTCHECK_OK" if ok else "POSTCHECK_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=str))
    print("sha256", _escribir(salida, informe))
    return 0 if ok else 3


if __name__ == "__main__":
    modo = sys.argv[1]
    if modo == "preflight":
        sys.exit(preflight(sys.argv[2], Path(sys.argv[3]), _salida_fuera_del_repo(sys.argv[4])))
    elif modo == "comparar":
        sys.exit(comparar(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], _salida_fuera_del_repo(sys.argv[5])))
    else:
        raise SystemExit("modo desconocido")
