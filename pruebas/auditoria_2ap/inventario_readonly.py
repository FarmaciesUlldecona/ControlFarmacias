"""Inventario 2AP READ_ONLY: proveedor por contenido de los PDF PIO elegibles.

Solo lee C:\\GoogleDrive\\FACTURES PIO. Escribe unicamente en la ruta indicada como argumento (fuera del repo).
No conecta a Supabase ni a Farmatic.
"""
import hashlib
import json
import sys
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\ControlFarmacias\Programa")
sys.path.insert(0, str(ROOT))

from src.facturas.motor_local.backend.pdfium import BackendPdfium  # noqa: E402
from src.facturas.motor_local.servicio import MotorDocumentoLocal  # noqa: E402
from src.facturas.runtime_supabase.multifactura import adaptar_resultado_local  # noqa: E402
from src.facturas.barrera_farmacia import resolver_farmacia_documental  # noqa: E402

DRIVE = Path(r"C:\GoogleDrive\FACTURES PIO")
MESES = ["JUNY 26", "JULIOL 26", "AGOST 26", "SETEMBRE 26"]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("inventario_2ap.json")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    pdfs = sorted(
        p for m in MESES for p in (DRIVE / m).rglob("*")
        if p.is_file() and p.suffix.lower() == ".pdf"
        and not p.stem.rstrip().casefold().endswith("rita")
    )
    motor = MotorDocumentoLocal(BackendPdfium())
    filas, vistos = [], set()
    for p in pdfs:
        digest = sha(p)
        if digest in vistos:
            continue
        vistos.add(digest)
        fila = {"ruta": str(p.relative_to(DRIVE)), "sha256": digest}
        try:
            local = motor.extraer(p)
            fila.update(
                layout=local.documento.get("layout"),
                paginas=local.documento.get("pages"),
                facturas_detectadas=len(local.facturas),
                completo=local.documento_completo_demostrado,
                incidencias=[i.get("codigo") for i in local.incidencias],
            )
            if fila["layout"] == "alliance-local":
                try:
                    doc = adaptar_resultado_local(local)
                    autorizables = []
                    for f in doc["facturas"]:
                        far = resolver_farmacia_documental(f)
                        ok = (f.get("factura_completa_demostrada") is True
                              and f.get("estado_validacion") in {"VALIDADA", "VALIDADA_CON_INCIDENCIAS"}
                              and bool(f.get("identidad_economica_clave"))
                              and far.estado == "RESUELTA" and far.farmacia_documental == "PIO")
                        autorizables.append({
                            "numero": (f.get("numero_factura") or {}).get("valor"),
                            "total": ((f.get("totales") or {}).get("total") or {}).get("valor"),
                            "estado_validacion": f.get("estado_validacion"),
                            "completa": f.get("factura_completa_demostrada"),
                            "farmacia": [far.estado, far.farmacia_documental],
                            "identidad": bool(f.get("identidad_economica_clave")),
                            "autorizable": ok,
                        })
                    fila["alliance"] = autorizables
                except Exception as exc:  # fail-closed del puente
                    fila["alliance_error"] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            fila["error"] = f"{type(exc).__name__}: {exc}"
            fila["traza"] = traceback.format_exc(limit=2)
        filas.append(fila)
        print(fila["ruta"], fila.get("layout"), fila.get("facturas_detectadas"), fila.get("error", ""), flush=True)
    resumen = {
        "pdfs_elegibles": len(pdfs),
        "documentos_unicos": len(filas),
        "por_layout": Counter(str(f.get("layout")) for f in filas),
        "multifactura": sum(1 for f in filas if (f.get("facturas_detectadas") or 0) > 1),
        "errores": sum(1 for f in filas if "error" in f),
    }
    OUT.write_text(json.dumps({"resumen": resumen, "filas": filas}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
