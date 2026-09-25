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
        pgl._docker("rm", "-f", nombre, comprobar=False)


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
    def crear(variante: str) -> pgl._Pg:
        return pgl.base_desde(pg17_contenedor, pg17_plantilla(variante))

    return crear
