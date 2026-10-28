"""Hito 2BF: copias del repositorio de la tarea nocturna con la V2 activada (sin Task Scheduler)."""
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from src.supabase_client import resincronizacion_albaranes as resync

ROOT = Path(__file__).resolve().parents[1]
COPIAS = ROOT / "pruebas" / "auditoria_2bf" / "backup_tasks"
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
SHA_ANTES = "3a880abeecbcff5ea521d37efc6c8b58429423acf39778b1c2a8749d2343713e"
SHA_VIGENTE = "b3e327db53fba6753c43f9433e5c4fd9ad3bc6674a244ed857fdc547c9010a31"
BAT = r"C:\ControlFarmacias\Programa\ejecutar_sincronizacion.bat"


def _tarea(nombre: str) -> ET.Element:
    return ET.fromstring((COPIAS / nombre).read_bytes())


def test_copias_son_las_exportaciones_reales() -> None:
    assert hashlib.sha256((COPIAS / "Sincronizacion_ControlFarmacias_antes_v2.xml").read_bytes()).hexdigest() == SHA_ANTES
    assert hashlib.sha256((COPIAS / "Sincronizacion_ControlFarmacias.xml").read_bytes()).hexdigest() == SHA_VIGENTE
    assert _tarea("Sincronizacion_ControlFarmacias_antes_v2.xml").find("t:Actions/t:Exec/t:Command", NS).text == BAT


def test_vigente_activa_la_v2_con_el_valor_exacto_y_el_wrapper_absoluto() -> None:
    exec_ = _tarea("Sincronizacion_ControlFarmacias.xml").find("t:Actions/t:Exec", NS)
    assert exec_.find("t:Command", NS).text == r"C:\Windows\System32\cmd.exe"
    argumentos = exec_.find("t:Arguments", NS).text
    assert argumentos == f'/c "set {resync.VARIABLE_ACTIVACION}=1&&{BAT}"'
    # cmd asigna hasta '&&' sin recortar: el valor debe ser exactamente "1" (activada()).
    nombre, valor = re.fullmatch(r'/c "set (\w+)=([^&]*)&&(.+)"', argumentos).groups()[:2]
    assert (nombre, valor) == (resync.VARIABLE_ACTIVACION, "1")
    assert exec_.find("t:WorkingDirectory", NS).text == r"C:\ControlFarmacias\Programa"
    assert (ROOT / "ejecutar_sincronizacion.bat").is_file()


def test_vigente_solo_cambia_la_accion() -> None:
    antes = _tarea("Sincronizacion_ControlFarmacias_antes_v2.xml")
    vigente = _tarea("Sincronizacion_ControlFarmacias.xml")
    for tarea in (antes, vigente):
        tarea.remove(tarea.find("t:Actions", NS))
    assert ET.tostring(antes) == ET.tostring(vigente)
    principal = vigente.find("t:Principals/t:Principal", NS)
    assert principal.find("t:UserId", NS).text.endswith("-1009")
    assert (principal.find("t:LogonType", NS).text, principal.find("t:RunLevel", NS).text) == (
        "Password", "LeastPrivilege")
