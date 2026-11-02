"""Hito 2BK: medicion en PostgreSQL 17 local de la persistencia multifactura y de la conciliacion.

Solo local (contenedor desechable ``--network none``, tmpfs); sin produccion ni Farmatic. Volumen final
simulado: los 14 documentos Alliance (los 2 ya normalizados en produccion y los 12 del plan 2BJ) se
persisten con el worker manual real, en orden, y el de mas lineas (posicion 122 del plan, 274 lineas) el
ultimo. Para cada persistencia mide el tiempo de la RPC ``cf_persistir_documento_multifactura`` visto por el
cliente y, aparte, el de transferir y convertir a jsonb el mismo payload (lo que PostgREST tambien hace dentro
de la sentencia). Despues concilia la factura con mas albaranes extraidos (albaranes sinteticos con el
importe documental) y mide ``cf_persistir_conciliacion``. Con ``explain`` comprueba el plan de la busqueda de
identidad. Los PDF salen del mirror local por SHA; las salidas, fuera del repositorio.

Uso: python -B pruebas/auditoria_2bk/medir_persistencia.py <variante 25|26> <plan.json> <salida.json> [mirror]
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/facturas/runtime_supabase"))

import pg17_local as pgl  # noqa: E402
from pg17_local import _lit, _registrar  # noqa: E402
from test_ensayo_fase4_2at import _ClienteServiceRole  # noqa: E402
from src.facturas.runtime_supabase.compositor_manual import construir_worker_manual_productivo  # noqa: E402
from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime  # noqa: E402
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase  # noqa: E402
from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion  # noqa: E402

MIRROR = Path(r"C:\GoogleDrive\FACTURES PIO")
# Alliance ya normalizados en produccion (READ_ONLY 2026-11-02): 08007969-73 y 08009277-79.
YA_NORMALIZADOS = ("4faa899bda8fdb08f9f425b31074dbfb521a3c6051efacb2f3ee5e7259d9d9f1",
                   "7b806565a4f09e182c5ec9d75b40b959fd39c4af86da77b7a8cb745c6e1192b2")
OBJETIVO = "8595f722"  # posicion 122 del plan: 274 lineas de albaran
MULTIFACTURA = "cf_persistir_documento_multifactura"
CONCILIACION = "cf_persistir_conciliacion"
# Busqueda de identidad de la 26 (la misma consulta que la funcion, con un nucleo real).
EXPLAIN_IDENTIDAD = (
    "explain (analyze, costs off, timing off, summary off) "
    "select id, documento_id, datos_extraidos from public.facturas "
    "where (public.cf_componentes_identidad_factura(datos_extraidos))[1:4] = {partes}::text[] order by ctid")


def _salida_fuera(ruta: str) -> Path:
    salida = Path(ruta).resolve()
    if salida.is_relative_to(ROOT):
        raise SystemExit("SALIDA_DENTRO_DEL_REPOSITORIO")
    return salida


def _pdfs(plan: dict, mirror: Path) -> list[tuple[str, bytes]]:
    alliance = [d for d in plan["documentos"] if d["prediccion"]["clase"] == "ALLIANCE"]
    objetivo = [d for d in alliance if d["id"].startswith(OBJETIVO)]
    orden = [*YA_NORMALIZADOS, *(d["archivo_hash"] for d in alliance if d not in objetivo),
             objetivo[0]["archivo_hash"]]
    buscados, encontrados = set(orden), {}
    for ruta in sorted(mirror.rglob("*")):
        if ruta.is_file() and ruta.suffix.lower() == ".pdf":
            contenido = ruta.read_bytes()
            sha = hashlib.sha256(contenido).hexdigest()
            if sha in buscados:
                encontrados[sha] = contenido
    faltan = [h for h in orden if h not in encontrados]
    if faltan:
        raise SystemExit(f"PDF_AUSENTES_DEL_MIRROR:{faltan}")
    return [(h, encontrados[h]) for h in orden]


def _contenedor() -> str:
    nombre = "cf-pg17-2bk-" + uuid.uuid4().hex[:6]
    pgl._docker("run", "-d", "--rm", "--name", nombre, "--network", "none", "--tmpfs",
                "/var/lib/postgresql/data", "-e", "POSTGRES_PASSWORD=x", pgl.IMAGEN)
    for _ in range(240):
        if pgl._docker("exec", nombre, "pg_isready", "-U", "postgres", "-q", comprobar=False).returncode == 0:
            break
        time.sleep(0.5)
    time.sleep(2)
    return nombre


class _Cronometro:
    """Envuelve ``_rpc`` del cliente: tiempo de cada RPC medida y del transporte del mismo payload."""

    def __init__(self, cliente, pg) -> None:
        self.pg, self.medidas, self._rpc = pg, [], cliente._rpc
        cliente._rpc = self

    def __call__(self, nombre, payload):
        if nombre not in (MULTIFACTURA, CONCILIACION):
            return self._rpc(nombre, payload)
        texto = json.dumps(payload.get("p_resultado"), ensure_ascii=False, default=str)
        inicio = time.perf_counter()
        self.pg.sql(f"select length({_lit(texto)}::jsonb::text);")
        transporte = time.perf_counter() - inicio
        inicio = time.perf_counter()
        try:
            return self._rpc(nombre, payload)
        finally:
            total = time.perf_counter() - inicio
            self.medidas.append({"rpc": nombre, "payload_bytes": len(texto.encode("utf-8")),
                                 "total_s": round(total, 3), "transporte_s": round(transporte, 3),
                                 "neto_s": round(total - transporte, 3)})


def medir(variante: str, plan_ruta: Path, salida: Path, mirror: Path = MIRROR) -> dict:
    plan = json.loads(plan_ruta.read_text(encoding="utf-8"))
    pdfs = _pdfs(plan, mirror)
    nombre = _contenedor()
    resultado: dict = {"hito": "2BK", "variante": variante, "imagen": pgl.IMAGEN, "documentos": []}
    try:
        pg = pgl.base_desde(nombre, pgl.construir_plantilla(nombre, variante))
        pg.sql("update public.documentos_facturas set estado_lectura = 'NORMALIZADA' "
               "where estado_lectura in ('PENDIENTE', 'ERROR');")
        cliente = _ClienteServiceRole(pg)
        reloj = _Cronometro(cliente, pg)
        for orden, (sha, contenido) in enumerate(pdfs, start=1):
            _registrar(pg, cliente, contenido, orden)
        with tempfile.TemporaryDirectory(prefix="cf2bk_") as temporal:
            for i, (sha, _) in enumerate(pdfs, start=1):
                antes = int(pg.sql("select count(*) from public.facturas;"))
                retorno = construir_worker_manual_productivo(
                    cliente, ConfiguracionRuntime(), "medir-2bk", Path(temporal) / f"w{i}").ejecutar_una_manual()
                [medida] = [m for m in reloj.medidas[len(resultado["documentos"]):] if m["rpc"] == MULTIFACTURA]
                fila = pg.json(
                    "select count(distinct f.id) as facturas, count(a.id) as lineas from public.documentos_facturas d "
                    "join public.facturas f on f.documento_id = d.id "
                    "left join public.facturas_albaranes_extraidos a on a.factura_id = f.id "
                    f"where d.archivo_hash = {_lit(sha)}")[0]
                resultado["documentos"].append({"orden": i, "sha": sha[:12], "reclamados": retorno.documentos_reclamados,
                                                "facturas_en_tabla_antes": antes, **fila, **medida})
                print(json.dumps(resultado["documentos"][-1]), flush=True)
        pg.sql("analyze public.facturas;")
        partes = pg.sql(
            "select (public.cf_componentes_identidad_factura(datos_extraidos))[1:4]::text from public.facturas "
            "where public.cf_componentes_identidad_factura(datos_extraidos) is not null limit 1;")
        resultado["explain_identidad"] = pg.sql(EXPLAIN_IDENTIDAD.format(partes=_lit(partes))).splitlines()
        resultado["conciliacion"] = _conciliar(pg, cliente, reloj)
        resultado["facturas_total"] = int(pg.sql("select count(*) from public.facturas;"))
    finally:
        pgl.cerrar_sesiones(nombre)
        pgl._docker("rm", "-f", nombre, comprobar=False)
    salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    return resultado


def _conciliar(pg, cliente, reloj) -> dict:
    """La factura Alliance con mas albaranes extraidos, n.o 1 del selector, con albaranes que la casan."""
    objetivo = pg.json(
        "select f.id, f.numero_factura, count(a.id) as lineas from public.facturas f "
        "join public.facturas_albaranes_extraidos a on a.factura_id = f.id "
        "group by f.id, f.numero_factura order by count(a.id) desc limit 1")[0]
    pg.sql(
        "insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
        "importe_pvp,importe_puc,descuento,estado) "
        "select 'PIO', 990000 + row_number() over (order by a.orden), '2', '1.- SAFA', a.numero_albaran, "
        "a.fecha_albaran, round(abs(a.importe_total) * 1.6, 2), abs(a.importe_total), 0, 'PENDIENTE' "
        f"from public.facturas_albaranes_extraidos a where a.factura_id = {_lit(objetivo['id'])};")
    pg.sql("update public.facturas set fecha_factura = date '2099-12-31' "
           f"where id <> {_lit(objetivo['id'])} and fecha_factura is not null;")
    previas = len(reloj.medidas)
    concilio = construir_worker_conciliacion(RepositorioRuntimeSupabase(cliente), "medir-2bk-conc").ejecutar_una_manual()
    vigente = pg.json(
        "select c.resultado, c.diferencia::text as diferencia, (select count(*) from public.conciliacion_detalles d "
        "where d.conciliacion_id = c.id) as detalles from public.conciliaciones c "
        f"where c.factura_id = {_lit(objetivo['id'])} and c.es_actual")
    medidas = [m for m in reloj.medidas[previas:] if m["rpc"] == CONCILIACION]
    return {"factura": objetivo["numero_factura"], "lineas": objetivo["lineas"], "concilio": concilio,
            "vigente": vigente, "medidas": medidas}


if __name__ == "__main__":
    datos = medir(sys.argv[1], Path(sys.argv[2]), _salida_fuera(sys.argv[3]),
                  Path(sys.argv[4]) if len(sys.argv) > 4 else MIRROR)
    peor = max(d["neto_s"] for d in datos["documentos"])
    print(json.dumps({"variante": datos["variante"], "peor_neto_s": peor,
                      "conciliacion": datos["conciliacion"], "explain": datos["explain_identidad"]},
                     ensure_ascii=False, indent=1))
