"""Hito 2BD-D (tanda RO): ``comparar`` del postcheck de la resincronizacion V2.

``conteos.albaranes`` no es operacion: solo se admite que crezca exactamente en los albaranes nuevos de PIO.
Capturas sinteticas; sin produccion ni Farmatic.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2bd_ro"))
import postcheck_readonly as pc  # noqa: E402


def _cambio(id_, campo, accion="ACTUALIZADO", motivo=None, id_contador=100, anterior=None, nuevo=1):
    return {"id": id_, "campo": campo, "accion": accion, "motivo": motivo, "origen": "RESYNC_VENTANA",
            "detalle": {}, "farmacia": "PIO", "id_contador": id_contador, "valor_nuevo": nuevo,
            "valor_anterior": anterior}


def _capturas(conteo_post: int):
    operacion = {"flags": [False, False, False, "{PIO}"], "conteos": {"albaranes": 2, "facturas": 7}}
    pre = {"capturado_utc": "pre", "recuentos": {}, "reservas": {"PIO:1": "h"}, "cambios": [],
           "albaranes": {"100": {"huella": "a", "id_recepcion": None},
                         str(pc.REVISION_PREVISTA): {"huella": "b", "id_recepcion": 9}},
           "operacion": operacion}
    post = copy.deepcopy(pre)
    post["capturado_utc"] = "post"
    post["albaranes"]["100"]["id_recepcion"] = 5
    post["albaranes"]["300000"] = {"huella": "c", "id_recepcion": 6}
    post["cambios"] = [_cambio(1, "id_recepcion"),
                       _cambio(2, "numero_albaran", "REVISION", "CAMBIO_IDENTIDAD", pc.REVISION_PREVISTA)]
    post["operacion"]["conteos"]["albaranes"] = conteo_post
    return pre, post


def _comparar(tmp_path, pre, post):
    rutas = []
    for nombre, datos in (("pre", pre), ("post", post)):
        ruta = tmp_path / f"{nombre}.json"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        rutas.append(ruta)
    salida = tmp_path / "comparacion.json"
    codigo = pc.comparar(rutas[0], rutas[1], salida)
    return codigo, json.loads(salida.read_text(encoding="utf-8"))


def test_conteo_albaranes_igual_a_nuevos_da_ok(tmp_path):
    codigo, resultado = _comparar(tmp_path, *_capturas(conteo_post=3))
    assert codigo == 0
    assert resultado["veredicto"] == "POSTCHECK_OK"
    assert resultado["conteo_albaranes"] == [2, 3] and resultado["albaranes_nuevos"] == 1


@pytest.mark.parametrize("conteo_post", [2, 4])
def test_conteo_albaranes_distinto_de_nuevos_revisar(tmp_path, conteo_post):
    codigo, resultado = _comparar(tmp_path, *_capturas(conteo_post))
    assert codigo == 1
    assert resultado["problemas"] == [f"CONTEO_ALBARANES_DISTINTO_DE_NUEVOS:2->{conteo_post}!=1"]


def test_otro_conteo_sigue_siendo_operacion(tmp_path):
    pre, post = _capturas(conteo_post=3)
    post["operacion"]["conteos"]["facturas"] = 8
    codigo, resultado = _comparar(tmp_path, pre, post)
    assert codigo == 1
    assert resultado["problemas"] == ["OPERACION_DISTINTA"]
