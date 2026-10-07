"""Hito 2AZ: compara el banco 2AY antes (codigo e12cc09) y despues (codigo 2AZ).

Uso: python -B pruebas/auditoria_2az/comparar_banco.py <metricas_2ay.json> <metricas_2az.json> <salida.json>

No se conecta a nada. Lista toda factura cuyo resultado cambia (elegibilidad,
albaranes casados, emparejamientos, estado con T1 y con R11), separando las
afectadas por D11 (emparejamientos que dejan de casar o cambian sin numero exacto).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def _oficiales(metricas: dict) -> dict[str, dict]:
    return {f["numero"]: f for f in metricas["conciliacion_simulada"]["facturas"] if f["origen"] == "oficial"}


def _estado(f: dict, regla: str) -> str | None:
    return (f.get("estado_por_tolerancia") or {}).get(regla)


def main(antes_ruta: Path, despues_ruta: Path, salida: Path) -> None:
    antes, despues = (json.loads(p.read_text(encoding="utf-8")) for p in (antes_ruta, despues_ruta))
    a, d = _oficiales(antes), _oficiales(despues)
    cambios = []
    for numero in sorted(set(a) | set(d)):
        x, y = a.get(numero, {}), d.get(numero, {})
        campos = {
            "elegibilidad": [x.get("elegibilidad"), y.get("elegibilidad")],
            "albaranes_documentales": [x.get("albaranes_documentales"), y.get("albaranes_documentales")],
            "albaranes_casados": [x.get("albaranes_casados"), y.get("albaranes_casados")],
            "matching": [x.get("matching"), y.get("matching")],
            "diferencia": [x.get("diferencia"), y.get("diferencia")],
            "estado_T1": [_estado(x, "T1"), _estado(y, "T1")],
            "estado_R11": [_estado(x, "R11") or _estado(x, "T3"), _estado(y, "R11")],
        }
        distintos = {k: v for k, v in campos.items() if v[0] != v[1]}
        if distintos:
            mismos_documentales = campos["albaranes_documentales"][0] == campos["albaranes_documentales"][1]
            cambios.append({"numero": numero, "posible_D11": bool(mismos_documentales and (
                "albaranes_casados" in distintos or "matching" in distintos)), "cambios": distintos})
    resumen = {
        "aptas_antes": antes["alliance_2au"]["aptas_conciliacion_oficial"],
        "aptas_despues": despues["alliance_2au"]["aptas_conciliacion_oficial"],
        "estados_T1_antes": Counter(str(_estado(f, "T1")).split(":")[0] for f in a.values()),
        "estados_T1_despues": Counter(str(_estado(f, "T1")).split(":")[0] for f in d.values()),
        "estados_R11_despues": Counter(str(_estado(f, "R11")).split(":")[0] for f in d.values()),
        "facturas_que_cambian": len(cambios),
        "afectadas_por_D11": [c["numero"] for c in cambios if c["posible_D11"]],
    }
    salida.write_text(json.dumps({"resumen": resumen, "cambios": cambios}, ensure_ascii=False, indent=1, default=str),
                      encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    for c in cambios:
        print(c["numero"], "D11" if c["posible_D11"] else "   ", json.dumps(c["cambios"], ensure_ascii=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
