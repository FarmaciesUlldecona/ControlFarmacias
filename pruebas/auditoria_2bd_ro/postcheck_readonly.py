"""Hito 2BD-D (tanda RO): captura y postcheck ESTRICTAMENTE READ_ONLY de la resincronizacion V2 manual.

Uso:
  python -B pruebas/auditoria_2bd_ro/postcheck_readonly.py captura <pre|post> <salida.json>
  python -B pruebas/auditoria_2bd_ro/postcheck_readonly.py comparar <pre.json> <post.json> <salida.json>

Puerta certificada del 2AT (``pruebas/auditoria_2at/auditoria_readonly.py``): project ref demostrado, sesion
READ_ONLY REPEATABLE READ, solo SELECT/WITH, rollback. Salidas FUERA del repositorio. Sin DML, sin RPC, sin
Farmatic.

Captura: las reservas R15 con huella por fila; ``albaranes_cambios`` completa (recuento y filas); de
``albaranes`` (PIO) la huella por fila sin ``id_recepcion`` ni ``fecha_actualizacion`` (las dos columnas que
la RPC toca al rellenar el metadato) y el ``id_recepcion``; operacion y flags.

Comparacion (``POSTCHECK_OK`` o ``POSTCHECK_REVISAR``):
- reservas identicas fila a fila;
- ``albaranes_cambios`` append-only: las filas previas siguen identicas; las nuevas solo pueden ser
  ``RESYNC_VENTANA`` + ``ACTUALIZADO`` de ``id_recepcion`` o ``REVISION CAMBIO_IDENTIDAD`` de 279410;
- ``albaranes``: ninguna fila desaparece ni cambia fuera de ``id_recepcion``; ``id_recepcion`` solo pasa de
  NULL a un valor; las filas nuevas (tarea nocturna) se listan aparte;
- operacion y flags identicos, salvo ``conteos.albaranes``, que debe crecer exactamente en los albaranes
  nuevos.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import _Lector, _ejecutar_lectura, _escribir, _operacion, _salida_fuera_del_repo  # noqa: E402

FARMACIA = "PIO"
REVISION_PREVISTA = 279410
EXCLUIDAS_HUELLA = ("id_recepcion", "fecha_actualizacion")


def _captura(lector: _Lector) -> dict:
    datos: dict = {"farmacia": FARMACIA}
    datos["reservas"] = {f"{r[0]}:{r[1]}": r[2] for r in lector.filas(
        "select albaran_farmacia, albaran_id_contador, md5(to_jsonb(r)::text) "
        "from public.conciliacion_albaranes_reservados r order by 1, 2")}
    datos["cambios"] = [json.loads(r[0]) for r in lector.filas(
        "select to_jsonb(c)::text from public.albaranes_cambios c order by id")]
    excluir = " - ".join(f"'{c}'" for c in EXCLUIDAS_HUELLA)
    datos["albaranes"] = {str(r[0]): {"huella": r[1], "id_recepcion": r[2]} for r in lector.filas(
        f"select id_contador, md5((to_jsonb(a) - {excluir})::text), id_recepcion "
        "from public.albaranes a where farmacia = %s order by id_contador", (FARMACIA,))}
    datos["recuentos"] = {
        "reservas": len(datos["reservas"]),
        "albaranes_cambios": len(datos["cambios"]),
        "albaranes": len(datos["albaranes"]),
        "albaranes_con_recepcion": sum(1 for a in datos["albaranes"].values() if a["id_recepcion"] is not None),
    }
    datos["operacion"] = _operacion(lector)
    return datos


def captura(momento: str, salida: Path) -> int:
    if momento not in ("pre", "post"):
        raise SystemExit("momento debe ser pre o post")
    _, datos = _ejecutar_lectura(_captura)
    datos["momento"] = momento
    sha = _escribir(salida, datos)
    print(json.dumps({"momento": momento, "capturado_utc": datos["capturado_utc"],
                      "recuentos": datos["recuentos"], "sha256": sha}, ensure_ascii=False, indent=1))
    return 0


def _clave_cambio(c: dict) -> str:
    return json.dumps(c, sort_keys=True, ensure_ascii=False, default=str)


def _sin_conteo_albaranes(operacion: dict) -> dict:
    conteos = {t: n for t, n in operacion["conteos"].items() if t != "albaranes"}
    return {**operacion, "conteos": conteos}


def comparar(pre_ruta: Path, post_ruta: Path, salida: Path) -> int:
    pre = json.loads(pre_ruta.read_text(encoding="utf-8"))
    post = json.loads(post_ruta.read_text(encoding="utf-8"))
    problemas: list[str] = []

    reservas_iguales = pre["reservas"] == post["reservas"]
    if not reservas_iguales:
        problemas.append("RESERVAS_DISTINTAS")

    pre_por_id = {c["id"]: c for c in pre["cambios"]}
    post_por_id = {c["id"]: c for c in post["cambios"]}
    ids_pre = set(pre_por_id)
    alterados = [i for i in ids_pre
                 if i not in post_por_id or _clave_cambio(post_por_id[i]) != _clave_cambio(pre_por_id[i])]
    if alterados:
        problemas.append(f"CAMBIOS_PREVIOS_ALTERADOS:{sorted(alterados)[:20]}")
    nuevos_cambios = [c for c in post["cambios"] if c["id"] not in ids_pre]
    inesperados = []
    for c in nuevos_cambios:
        recepcion = (c["origen"] == "RESYNC_VENTANA" and c["accion"] == "ACTUALIZADO"
                     and c["campo"] == "id_recepcion" and c["valor_anterior"] is None)
        revision = (c["origen"] == "RESYNC_VENTANA" and c["accion"] == "REVISION"
                    and c["motivo"] == "CAMBIO_IDENTIDAD" and int(c["id_contador"]) == REVISION_PREVISTA)
        if not (recepcion or revision):
            inesperados.append(c)
    if inesperados:
        problemas.append(f"CAMBIOS_NUEVOS_INESPERADOS:{len(inesperados)}")
    revisiones_279410 = [c for c in nuevos_cambios
                         if c["accion"] == "REVISION" and int(c["id_contador"]) == REVISION_PREVISTA]
    if not revisiones_279410:
        problemas.append("SIN_REVISION_279410")

    a_pre, a_post = pre["albaranes"], post["albaranes"]
    desaparecidos = sorted(set(a_pre) - set(a_post), key=int)
    if desaparecidos:
        problemas.append(f"ALBARANES_DESAPARECIDOS:{len(desaparecidos)}")
    huella_cambiada = sorted((k for k in a_pre if k in a_post and a_pre[k]["huella"] != a_post[k]["huella"]), key=int)
    if huella_cambiada:
        problemas.append(f"ALBARANES_CAMBIADOS_FUERA_DE_RECEPCION:{len(huella_cambiada)}")
    recepcion = Counter()
    recepcion_anomala = []
    for k in a_pre.keys() & a_post.keys():
        antes, despues = a_pre[k]["id_recepcion"], a_post[k]["id_recepcion"]
        if antes == despues:
            recepcion["igual_nula" if antes is None else "igual_valor"] += 1
        elif antes is None:
            recepcion["nula_a_valor"] += 1
        else:
            recepcion_anomala.append(k)
    if recepcion_anomala:
        problemas.append(f"RECEPCION_SOBRESCRITA:{len(recepcion_anomala)}")
    nuevos_albaranes = sorted(set(a_post) - set(a_pre), key=int)
    max_pre = max((int(k) for k in a_pre), default=0)
    nuevos_antiguos = [k for k in nuevos_albaranes if int(k) <= max_pre]

    ids_cambio_recepcion = {str(c["id_contador"]) for c in nuevos_cambios if c["campo"] == "id_recepcion"}
    rellenados = {k for k in a_pre.keys() & a_post.keys()
                  if a_pre[k]["id_recepcion"] is None and a_post[k]["id_recepcion"] is not None}
    if rellenados - ids_cambio_recepcion:
        problemas.append(f"RECEPCION_SIN_HISTORIAL:{len(rellenados - ids_cambio_recepcion)}")

    # conteos.albaranes no es operacion: crece con los nuevos que inserta la propia sincronizacion. Se
    # compara aparte y solo se admite el incremento igual a los albaranes nuevos de PIO.
    conteo_pre = pre["operacion"]["conteos"]["albaranes"]
    conteo_post = post["operacion"]["conteos"]["albaranes"]
    if conteo_post - conteo_pre != len(nuevos_albaranes):
        problemas.append(f"CONTEO_ALBARANES_DISTINTO_DE_NUEVOS:{conteo_pre}->{conteo_post}"
                         f"!={len(nuevos_albaranes)}")
    operacion_igual = _sin_conteo_albaranes(pre["operacion"]) == _sin_conteo_albaranes(post["operacion"])
    if not operacion_igual:
        problemas.append("OPERACION_DISTINTA")

    resultado = {
        "veredicto": "POSTCHECK_OK" if not problemas else "POSTCHECK_REVISAR",
        "problemas": problemas,
        "pre": {"capturado_utc": pre["capturado_utc"], "recuentos": pre["recuentos"]},
        "post": {"capturado_utc": post["capturado_utc"], "recuentos": post["recuentos"]},
        "reservas_identicas": reservas_iguales,
        "cambios_nuevos": len(nuevos_cambios),
        "cambios_nuevos_por_tipo": [list(k) + [n] for k, n in sorted(Counter(
            (c["origen"], c["accion"], c["campo"], c["motivo"]) for c in nuevos_cambios).items(),
            key=lambda x: str(x[0]))],
        "cambios_nuevos_inesperados": inesperados[:50],
        "revisiones_279410": revisiones_279410,
        "albaranes_desaparecidos": desaparecidos[:50],
        "albaranes_huella_cambiada": huella_cambiada[:50],
        "id_recepcion": dict(recepcion),
        "id_recepcion_sobrescrita": recepcion_anomala[:50],
        "albaranes_nuevos": len(nuevos_albaranes),
        "albaranes_nuevos_con_contador_antiguo": nuevos_antiguos[:50],
        "conteo_albaranes": [conteo_pre, conteo_post],
        "operacion_identica": operacion_igual,
        "sha256_pre": hashlib.sha256(pre_ruta.read_bytes()).hexdigest(),
        "sha256_post": hashlib.sha256(post_ruta.read_bytes()).hexdigest(),
    }
    sha = _escribir(salida, resultado)
    print(json.dumps({k: resultado[k] for k in (
        "veredicto", "problemas", "pre", "post", "reservas_identicas", "cambios_nuevos",
        "cambios_nuevos_por_tipo", "id_recepcion", "albaranes_nuevos")}, ensure_ascii=False, indent=1))
    print("sha256:", sha)
    return 0 if not problemas else 1


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "captura":
        sys.exit(captura(sys.argv[2], _salida_fuera_del_repo(sys.argv[3])))
    if len(sys.argv) == 5 and sys.argv[1] == "comparar":
        sys.exit(comparar(Path(sys.argv[2]), Path(sys.argv[3]), _salida_fuera_del_repo(sys.argv[4])))
    raise SystemExit(__doc__)
