from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _bat(nombre: str) -> str:
    return (ROOT / nombre).read_text(encoding="utf-8").lower()


def test_wrapper_importacion_es_absoluto_auditable_y_propaga_error() -> None:
    contenido = _bat("ejecutar_importacion_facturas.bat")

    assert "cd /d c:\\controlfarmacias\\programa" in contenido
    assert "c:\\controlfarmacias\\programa\\.venv\\scripts\\python.exe" in contenido
    assert "-m src.facturas.importar_facturas_drive" in contenido
    assert "2>&1" in contenido
    assert "set codigo_salida=%errorlevel%" in contenido
    assert "exit /b %codigo_salida%" in contenido


def test_wrapper_sincronizacion_es_absoluto_auditable_y_propaga_error() -> None:
    contenido = _bat("ejecutar_sincronizacion.bat")

    assert "cd /d c:\\controlfarmacias\\programa" in contenido
    assert "c:\\controlfarmacias\\programa\\.venv\\scripts\\python.exe" in contenido
    assert "-m src.sincronizar_albaranes" in contenido
    assert "automatizacion_albaranes.log" in contenido
    assert "2>&1" in contenido
    assert "set codigo_salida=%errorlevel%" in contenido
    assert "exit /b %codigo_salida%" in contenido


def test_wrappers_no_contienen_credenciales() -> None:
    contenido = _bat("ejecutar_importacion_facturas.bat") + _bat(
        "ejecutar_sincronizacion.bat"
    )

    for nombre in ("supabase_key", "supabase_url", "password", "token"):
        assert nombre not in contenido
