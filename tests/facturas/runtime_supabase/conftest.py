"""Fixtures compartidas de integracion PostgreSQL 17 local (Hitos 2AQ y 2AR)."""
from __future__ import annotations

import json
import shutil
import time
import uuid

import pytest

import pg17_local as pgl


@pytest.fixture(scope="session")
def pg17_contenedor():
    if shutil.which("docker") is None:
        pytest.skip("Docker no disponible")
    if pgl._docker("image", "inspect", pgl.IMAGEN, comprobar=False).returncode:
        pytest.skip(f"imagen local {pgl.IMAGEN} no disponible")
    if not pgl.ALLIANCE.exists() or not pgl.HEFAME.exists():
        pytest.skip("fixtures reales 2AP ausentes")
    nombre = "cf-pg17-" + uuid.uuid4().hex[:12]
    pgl._docker("run", "-d", "--rm", "--name", nombre,
                "--label", "controlfarmacias.certificacion=pg17_local",
                "--network", "none", "--tmpfs", "/var/lib/postgresql/data",
                "-e", "POSTGRES_PASSWORD=local-only", pgl.IMAGEN)
    try:
        for _ in range(120):
            if pgl._docker("exec", nombre, "pg_isready", "-U", "postgres", "-q",
                           comprobar=False).returncode == 0:
                break
            time.sleep(0.5)
        info = json.loads(pgl._docker("inspect", nombre).stdout)[0]
        assert info["HostConfig"]["NetworkMode"] == "none"
        assert not info["HostConfig"]["PortBindings"]
        yield nombre
    finally:
        pgl.cerrar_sesiones(nombre)
        pgl._docker("rm", "-f", nombre, comprobar=False)


@pytest.fixture(autouse=True)
def _cerrar_sesiones_pg17():
    """2BH: las sesiones psql persistentes no sobreviven al test (mismo aislamiento que un proceso por
    sentencia; tampoco se acumulan conexiones en el contenedor)."""
    yield
    pgl.cerrar_sesiones()


@pytest.fixture(scope="session")
def pg17_plantilla(pg17_contenedor):
    cache: dict[str, str] = {}

    def obtener(variante: str) -> str:
        if variante not in cache:
            cache[variante] = pgl.construir_plantilla(pg17_contenedor, variante)
        return cache[variante]

    return obtener


@pytest.fixture
def pg17_nueva_base(pg17_contenedor, pg17_plantilla):
    """Cada base vive solo durante su test: el contenedor guarda los datos en tmpfs (memoria de la maquina de
    Docker) y, sin borrarlas, la suite completa agotaba el espacio («No space left on device», 2026-11-15, al
    sumarse las plantillas de la 33)."""
    creadas: list[str] = []

    def crear(variante: str) -> pgl._Pg:
        pg = pgl.base_desde(pg17_contenedor, pg17_plantilla(variante))
        creadas.append(pg.db)
        return pg

    yield crear
    pgl.cerrar_sesiones()
    for db in creadas:
        pgl._docker("exec", pg17_contenedor, "dropdb", "-U", "postgres", "--force", "--if-exists", db)
