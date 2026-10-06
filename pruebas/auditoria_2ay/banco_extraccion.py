"""Hito 2AY: banco de pruebas de extraccion (fases 1.2, 1.3, 2 y simulacion 2AU de 3.5).

Uso:
  python -B pruebas/auditoria_2ay/banco_extraccion.py inventario <supabase.json> <inventario.json>
  python -B pruebas/auditoria_2ay/banco_extraccion.py motor <inventario.json> <motor.json> [timeout_s]

SOLO MEDICION. Lee el mirror ``C:\\GoogleDrive\\FACTURES PIO`` (nunca escribe en
el) y ejecuta en memoria la cadena oficial hasta el punto previo a persistir:
``MotorDocumentoLocal`` -> ``ExtractorDocumentalAutorizado`` (reconocimiento,
autoridad, completitud, puente multifactura e identidad economica) ->
``RepositorioRuntimeSupabase.persistir_documento_automatico`` con un cliente que
solo CAPTURA la RPC (no hay red: la autorizacion por segmento la decide el
codigo oficial). Cada documento corre en un proceso hijo con tiempo limite; un
fallo no detiene el lote. La simulacion 2AU parchea en memoria, solo dentro del
proceso hijo, la clasificacion de filas Alliance; no modifica ningun archivo.
Sin Supabase, Farmatic, Luna, OCR ni red. Las salidas contienen datos de
negocio: escribirlas fuera del repositorio.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import re
import sys
import time
import traceback
import unicodedata
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVE = Path(r"C:\GoogleDrive\FACTURES PIO")
TIMEOUT_POR_DEFECTO = 180
NIF_PIO = "40901058C"
CIF_RE = re.compile(r"\b(?:ES)?([ABCDEFGHJNPQRSUVW])[- .]?(\d{7})[- .]?([0-9A-J])\b")
TIPOS_2AU_MERCANCIA = frozenset({"DIRECTO", "ENCARGO VACUNAS", "MIS RESERVAS", "TELEVENTA 2"})
TIPO_2AU_SERVICIO = "COSTO TELEVENTA"
# "ABONO ECOCEUTICS" del 2AU: filas con tipo literal ECOCEUTICS dentro del bloque ABONOS.
TIPOS_2AU_ABONO = frozenset({"ECOCEUTICS", "ABONO ECOCEUTICS"})


def _salida_fuera_del_repo(ruta: str) -> Path:
    destino = Path(ruta).resolve()
    if destino == ROOT or ROOT in destino.parents:
        raise SystemExit(f"SALIDA_DENTRO_DEL_REPOSITORIO: {destino}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    return destino


def _escribir(destino: Path, datos) -> str:
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return hashlib.sha256(destino.read_bytes()).hexdigest()


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:  # solo lectura
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()


def cifs_en_texto(texto: str) -> list[str]:
    """CIF/NIF de persona juridica en orden de aparicion (sin duplicados)."""
    vistos: list[str] = []
    for m in CIF_RE.finditer(_normalizar(texto)):
        cif = "".join(m.groups())
        if cif not in vistos:
            vistos.append(cif)
    return vistos


def clasificar_capa_texto(caracteres_por_pagina: list[int]) -> str:
    if not caracteres_por_pagina:
        return "SIN_PAGINAS"
    con = sum(1 for c in caracteres_por_pagina if c > 0)
    return "TEXTO" if con == len(caracteres_por_pagina) else "SIN_TEXTO" if con == 0 else "MIXTO"


# --------------------------------------------------------------------------- fase 1.2 / 1.3

def _propiedades_pdf(path: Path) -> dict:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        caracteres, primera = [], ""
        textos = []
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            try:
                texto = tp.get_text_range()
            finally:
                tp.close()
                page.close()
            caracteres.append(len(texto.strip()))
            textos.append(texto)
            if i == 0:
                primera = texto
        try:
            meta = {k: v for k, v in pdf.get_metadata_dict().items() if v}
        except Exception:
            meta = {}
    finally:
        pdf.close()
    lineas = [l.strip() for l in _normalizar(primera).splitlines() if l.strip()]
    return {
        "paginas": len(caracteres), "caracteres_por_pagina": caracteres,
        "capa_texto": clasificar_capa_texto(caracteres), "tamano_bytes": path.stat().st_size,
        "metadatos_pdf": meta, "cifs": cifs_en_texto("\n".join(textos)),
        "cabecera_primera_pagina": lineas[:4],
    }


def inventario(supabase: Path, salida: Path) -> None:
    datos = json.loads(supabase.read_text(encoding="utf-8"))
    por_sha: dict[str, list[str]] = {}
    pdfs = sorted(p for p in DRIVE.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    for p in pdfs:
        por_sha.setdefault(_sha(p), []).append(str(p))
    filas, ausentes = [], []
    for d in datos["documentos"]:
        rutas = por_sha.get(d["archivo_hash"], [])
        fila = {**d, "rutas_mirror": rutas}
        if not rutas:
            ausentes.append(d["id"])
        else:
            try:
                fila.update(_propiedades_pdf(Path(rutas[0])))
            except Exception as exc:
                fila["error_propiedades"] = f"{type(exc).__name__}: {exc}"
        filas.append(fila)
    resumen = {
        "pdfs_en_mirror": len(pdfs), "shas_distintos_en_mirror": len(por_sha),
        "documentos_supabase": len(filas), "localizados": len(filas) - len(ausentes),
        "ausentes_del_mirror": ausentes,
        "capa_texto": Counter(f.get("capa_texto", "NO_LOCALIZADO") for f in filas),
        "paginas_total": sum(f.get("paginas", 0) for f in filas),
    }
    sha = _escribir(salida, {"resumen": resumen, "documentos": filas})
    print(json.dumps(resumen, ensure_ascii=False, default=str))
    print("sha256", sha)


# --------------------------------------------------------------------------- fase 2 (proceso hijo)

def _v(campo):
    return campo.get("valor") if isinstance(campo, dict) else None


def _dec(valor):
    if valor is None:
        return None
    if isinstance(valor, dict):
        valor = valor.get("valor")
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return None


def cuadre_fiscal(total, base, iva, recargo, otros) -> dict:
    """bases + cuotas (+ otros) frente a total. Diferencia en euros (total - suma)."""
    t, b = _dec(total), _dec(base)
    if t is None or b is None:
        return {"evaluable": False}
    suma = b + (_dec(iva) or 0) + (_dec(recargo) or 0) + (_dec(otros) or 0)
    diferencia = (t - suma).quantize(Decimal("0.01"))
    return {"evaluable": True, "suma": str(suma), "diferencia": str(diferencia),
            "cuadra_005": abs(diferencia) <= Decimal("0.05")}


def _resumen_traza(exc: BaseException) -> str:
    tb = traceback.extract_tb(exc.__traceback__)
    propias = [f for f in tb if "ControlFarmacias" in f.filename] or tb
    return " <- ".join(f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in reversed(propias[-4:]))


def _diagnostico_factura_local(raw: dict, cabecera_documento: dict) -> dict:
    cab = raw.get("cabecera") or cabecera_documento or {}
    candidatos = raw.get("candidatos_fila") or []
    albaranes = raw.get("albaranes") or []
    no_promovidas = []
    for c in candidatos:
        clasif = c.get("clasificacion_economica") or {}
        if clasif.get("concepto") == "NO_DEMOSTRABLE":
            no_promovidas.append({"referencia": _v(c.get("numero_referencia")), "tipo_pedido": _v(c.get("tipo_pedido")),
                                  "sentido": _v(c.get("sentido")), "total": _v(c.get("total")),
                                  "regla": clasif.get("regla")})
    operaciones = [{"tipo_pedido": _v(o.get("descripcion_literal")), "concepto": o.get("concepto"),
                    "categoria": o.get("categoria"), "sentido": o.get("sentido"), "importe": _v(o.get("importe"))}
                   for o in raw.get("operaciones_economicas") or []]
    return {
        "segmento": {k: (raw.get("segmento") or {}).get(k) for k in ("paginas", "estado", "regla", "identidad")},
        "numero": _v(cab.get("numero_factura")), "fecha": _v(cab.get("fecha_factura")),
        "tipo_documento": _v(cab.get("tipo_documento")),
        "base": _v(cab.get("base_imponible_total")), "iva": _v(cab.get("iva_total")),
        "recargo": _v(cab.get("recargo_equivalencia_total")), "otros": _v(cab.get("otros_total")),
        "total": _v(cab.get("importe_total")),
        "proveedor_nombre": _v((cab.get("proveedor") or {}).get("nombre")),
        "proveedor_nif": _v((cab.get("proveedor") or {}).get("nif")),
        "destinatario_nif": _v((cab.get("destinatario") or {}).get("nif")),
        "cuadre_fiscal": cuadre_fiscal(_v(cab.get("importe_total")), _v(cab.get("base_imponible_total")),
                                       _v(cab.get("iva_total")), _v(cab.get("recargo_equivalencia_total")),
                                       _v(cab.get("otros_total"))),
        "filas_albaran_leidas": len(candidatos) if candidatos else len(albaranes),
        "filas_albaran_promovidas": len(albaranes),
        "filas_no_promovidas": no_promovidas,
        "tipos_pedido": dict(Counter(str(_v(c.get("tipo_pedido"))) for c in candidatos)),
        "operaciones_economicas": operaciones,
        "movimientos": len(raw.get("movimientos") or []),
        "incidencias": [{"codigo": i.get("codigo"), "bloqueante": bool(i.get("bloqueante")),
                         "motivo": i.get("motivo")} for i in raw.get("incidencias") or []],
    }


def _resumen_normalizada(f: dict) -> dict:
    from src.facturas.barrera_farmacia import resolver_farmacia_documental

    far = resolver_farmacia_documental(f)
    motivos = []
    if f.get("factura_completa_demostrada") is not True:
        motivos.append("FACTURA_NO_COMPLETA_DEMOSTRADA")
    if f.get("estado_validacion") not in {"VALIDADA", "VALIDADA_CON_INCIDENCIAS"}:
        motivos.append(f"ESTADO_VALIDACION:{f.get('estado_validacion')}")
    if not f.get("identidad_economica_clave"):
        motivos.append("IDENTIDAD_ECONOMICA_NO_DEMOSTRADA")
    if far.estado != "RESUELTA" or far.farmacia_documental != "PIO":
        motivos.append(f"FARMACIA:{far.estado}:{far.farmacia_documental}")
    tot = f.get("totales") or {}
    fecha = _v(f.get("fecha_factura"))
    return {
        "segment_id": (f.get("provenance") or {}).get("segment_id"),
        "numero": _v(f.get("numero_factura")),
        "fecha": fecha.get("iso") if isinstance(fecha, dict) else fecha,
        "tipo_documento": _v(f.get("tipo_documento")),
        "naturaleza_principal": f.get("naturaleza_principal"),
        "estado_validacion": f.get("estado_validacion"),
        "factura_completa_demostrada": f.get("factura_completa_demostrada"),
        "identidad_economica_clave": f.get("identidad_economica_clave"),
        "farmacia": [far.estado, far.farmacia_documental],
        "proveedor_nombre": _v((f.get("proveedor") or {}).get("nombre")),
        "proveedor_nif": _v((f.get("proveedor") or {}).get("nif")),
        "destinatario_nif": _v((f.get("destinatario") or {}).get("nif")),
        "destinatario_nombre": _v((f.get("destinatario") or {}).get("nombre")),
        "destinatario_con_evidencia": bool(((f.get("destinatario") or {}).get("nif") or {}).get("evidencia")
                                           or ((f.get("destinatario") or {}).get("nombre") or {}).get("evidencia")),
        **{k: _v(tot.get(k)) for k in ("base_imponible", "iva", "recargo_equivalencia", "otros", "total")},
        "cuadre_fiscal": cuadre_fiscal(_v(tot.get("total")), _v(tot.get("base_imponible")), _v(tot.get("iva")),
                                       _v(tot.get("recargo_equivalencia")), _v(tot.get("otros"))),
        "albaranes": [{"numero": _v(a.get("numero")),
                       "fecha": (_v(a.get("fecha")) or {}).get("iso") if isinstance(_v(a.get("fecha")), dict)
                       else _v(a.get("fecha")),
                       "importe_total": _v(a.get("importe_total")), "sentido": a.get("sentido"),
                       "tipo_pedido": _v(a.get("tipo_pedido"))} for a in f.get("albaranes") or []],
        "movimientos": [{"tipo": m.get("tipo"), "sentido": m.get("sentido"),
                         "descripcion": _v(m.get("descripcion_literal")), "importe": _v(m.get("importe")),
                         "base": _v(m.get("base"))} for m in f.get("movimientos_comerciales") or []],
        "incidencias_bloqueantes": [i.get("codigo") for i in f.get("incidencias") or [] if i.get("bloqueante")],
        "motivos_no_autorizable": motivos,
    }


class _MotorFijo:
    def __init__(self, local):
        self._local = local

    def extraer(self, _ruta):
        return self._local


class _Captura:
    """Cliente sin red: solo registra la RPC que se habria enviado."""

    def __init__(self):
        self.llamadas = []

    def rpc(self, nombre, payload):
        self.llamadas.append((nombre, payload))
        return self

    def execute(self):
        return types_simple(data=None)


def types_simple(**kw):
    import types
    return types.SimpleNamespace(**kw)


ETAPA_POR_MOTIVO = {
    "PROVEEDOR_NO_RECONOCIDO": "RECONOCIMIENTO",
    "REQUIERE_OCR_O_LUNA_NO_AUTORIZADO": "RECONOCIMIENTO",
    "PROVEEDOR_NO_SOPORTADO_MANUAL": "AUTORIDAD",
    "DOCUMENTO_INCOMPLETO": "COMPLETITUD",
    "ADAPTACION_NO_CERTIFICADA": "SEGMENTACION_MULTIFACTURA",
    "EXTRACCION_LOCAL_ERROR": "EXTRACCION",
}


def _analizar(ruta: str) -> dict:
    from src.facturas.motor_local.backend.pdfium import BackendPdfium
    from src.facturas.motor_local.servicio import MotorDocumentoLocal
    from src.facturas.runtime_supabase.compositor_manual import (
        CAMPO_DOCUMENTO, CAMPOS_REQUERIDOS_MANUAL, ExtractorDocumentalAutorizado)
    from src.facturas.runtime_supabase.modelos import DocumentoTrabajo, ResultadoExtraccionProductiva
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

    inicio = time.perf_counter()
    res: dict = {"etapa_detencion": None, "motivo": None}
    try:
        local = MotorDocumentoLocal(BackendPdfium()).extraer(ruta)
    except Exception as exc:
        res.update(etapa_detencion="EXTRACCION_MOTOR", motivo="EXCEPCION_MOTOR",
                   excepcion={"tipo": type(exc).__name__, "mensaje": str(exc)[:200], "traza": _resumen_traza(exc)})
        res["segundos"] = round(time.perf_counter() - inicio, 2)
        return res
    layout = local.documento.get("layout")
    res.update(
        layout=layout,
        reconocimientos=[{"adaptador": r["adaptador"], "estado": r["estado"], "puntuacion": r["puntuacion"]}
                         for r in local.documento.get("reconocimientos", []) if r["estado"] != "NO_RECONOCIDO"],
        documento_completo_demostrado=local.documento_completo_demostrado,
        incidencias_documento=[{"codigo": i.get("codigo"), "bloqueante": bool(i.get("bloqueante"))}
                               for i in local.incidencias],
        facturas_detectadas=len(local.facturas),
        facturas_local=[_diagnostico_factura_local(f, local.cabecera) for f in local.facturas],
    )
    if not local.facturas and local.cabecera:
        res["facturas_local"] = [_diagnostico_factura_local({}, local.cabecera)]
    if layout is None:
        codigos = [i.get("codigo") for i in local.incidencias]
        res.update(etapa_detencion="RECONOCIMIENTO", motivo=next(
            (c for c in ("PENDIENTE_OCR", "LAYOUT_AMBIGUO", "LAYOUT_NO_RECONOCIDO") if c in codigos), "SIN_LAYOUT"))
        res["segundos"] = round(time.perf_counter() - inicio, 2)
        return res
    etapa = ExtractorDocumentalAutorizado(crear_motor=lambda: _MotorFijo(local)).extraer(
        Path(ruta), CAMPOS_REQUERIDOS_MANUAL)
    motivo = etapa.provenance.get("motivo")
    if motivo != "AUTORIZADO":
        res.update(etapa_detencion=ETAPA_POR_MOTIVO.get(motivo, "EXTRACTOR_AUTORIZADO"), motivo=motivo,
                   detalle=etapa.provenance.get("error"))
        res["segundos"] = round(time.perf_counter() - inicio, 2)
        return res
    normalizado = etapa.valores[CAMPO_DOCUMENTO]
    res["facturas_normalizadas"] = [_resumen_normalizada(f) for f in normalizado.get("facturas", [])]
    captura = _Captura()
    try:
        RepositorioRuntimeSupabase(captura).persistir_documento_automatico(
            DocumentoTrabajo("banco-2ay", "no-aplica", "no-aplica", "PIO"),
            ResultadoExtraccionProductiva(valores={}, campos_pendientes=(), pasos=(), uso_luna=None, incidencias=(),
                                          documento_normalizado=normalizado),
            "banco-2ay", "banco-2ay", "MANUAL_ONE_SHOT", "banco-2ay")
        [(nombre, payload)] = captura.llamadas
        assert nombre == "cf_persistir_documento_multifactura"
        res["segmentos_autorizados"] = list(payload["p_segmentos_autorizados"])
        res.update(etapa_detencion="PREVIO_A_PERSISTIR_OK", motivo="AUTORIZADO")
    except Exception as exc:
        res["segmentos_autorizados"] = []
        res.update(etapa_detencion="AUTORIZACION", motivo=str(exc)[:200] or type(exc).__name__,
                   excepcion={"tipo": type(exc).__name__, "traza": _resumen_traza(exc)})
    for f in res["facturas_normalizadas"]:
        f["autorizable"] = f["segment_id"] in res["segmentos_autorizados"]
    res["segundos"] = round(time.perf_counter() - inicio, 2)
    return res


@contextmanager
def parche_2au():
    """Simulacion 2AU en memoria (solo en este proceso): no modifica el adaptador en disco."""
    import src.facturas.motor_local.adaptadores.alliance as al
    from src.facturas.motor_local.geometria.lineas import normalizar_texto

    tipos, clasificar = al.TIPOS_PEDIDO_MERCANCIA_ALLIANCE, al.clasificar_fila_economica_alliance

    def clasificar_2au(candidato, relacion=None):
        r = clasificar(candidato, relacion)
        if r["concepto"] != "NO_DEMOSTRABLE":
            return r
        tipo = normalizar_texto(str((candidato.get("tipo_pedido") or {}).get("valor") or ""))
        if tipo == TIPO_2AU_SERVICIO and r["sentido"] == "CARGO" and r["signo"] == "POSITIVO":
            return {**r, "concepto": "SERVICIO", "categoria_movimiento": "SERVICIO",
                    "regla": "SIMULACION_2AU_COSTO_TELEVENTA_CARGO_SERVICIO"}
        if tipo in TIPOS_2AU_ABONO and r["sentido"] == "ABONO" and r["signo"] == "NEGATIVO":
            return {**r, "concepto": "ABONO", "categoria_movimiento": "ABONO_COMERCIAL",
                    "regla": "SIMULACION_2AU_ABONO_ECOCEUTICS"}
        return r

    al.TIPOS_PEDIDO_MERCANCIA_ALLIANCE = tipos | TIPOS_2AU_MERCANCIA
    al.clasificar_fila_economica_alliance = clasificar_2au
    try:
        yield
    finally:
        al.TIPOS_PEDIDO_MERCANCIA_ALLIANCE, al.clasificar_fila_economica_alliance = tipos, clasificar


def analizar_documento(ruta: str) -> dict:
    sys.path.insert(0, str(ROOT))
    salida = {"oficial": _analizar(ruta)}
    if salida["oficial"].get("layout") == "alliance-local":
        with parche_2au():
            salida["simulado_2au"] = _analizar(ruta)
    return json.loads(json.dumps(salida, default=str))


def motor(inventario_ruta: Path, salida: Path, timeout: int) -> None:
    inv = json.loads(inventario_ruta.read_text(encoding="utf-8"))
    ctx = mp.get_context("spawn")
    pool = ctx.Pool(1)
    filas = []
    try:
        for d in inv["documentos"]:
            fila = {k: d.get(k) for k in ("id", "archivo_hash", "archivo_nombre", "estado_lectura",
                                          "estado_persistencia", "paginas", "capa_texto")}
            fila["ruta"] = d["rutas_mirror"][0] if d.get("rutas_mirror") else None
            if not fila["ruta"]:
                fila["oficial"] = {"etapa_detencion": "INVENTARIO", "motivo": "AUSENTE_DEL_MIRROR"}
            else:
                tarea = pool.apply_async(analizar_documento, (fila["ruta"],))
                try:
                    fila.update(tarea.get(timeout))
                except mp.TimeoutError:
                    pool.terminate()
                    pool = ctx.Pool(1)
                    fila["oficial"] = {"etapa_detencion": "TIEMPO_LIMITE", "motivo": f"TIMEOUT_{timeout}S"}
                except Exception as exc:
                    fila["oficial"] = {"etapa_detencion": "PROCESO_HIJO", "motivo": type(exc).__name__,
                                       "excepcion": {"tipo": type(exc).__name__, "mensaje": str(exc)[:200]}}
            o = fila["oficial"]
            print(f"{len(filas)+1:3d} {o.get('etapa_detencion'):26s} {str(o.get('motivo'))[:40]:40s} "
                  f"{str(o.get('layout')):24s} {Path(fila['ruta'] or '-').name}", flush=True)
            filas.append(fila)
    finally:
        pool.terminate()
    sha = _escribir(salida, {"timeout_s": timeout, "documentos": filas})
    print("sha256", sha)


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo == "inventario":
        inventario(Path(sys.argv[2]), _salida_fuera_del_repo(sys.argv[3]))
    elif modo == "motor":
        motor(Path(sys.argv[2]), _salida_fuera_del_repo(sys.argv[3]),
              int(sys.argv[4]) if len(sys.argv) > 4 else TIMEOUT_POR_DEFECTO)
    else:
        raise SystemExit("modo desconocido")
