"""Cierre posterior 2AN: solo lecturas, sin reaplicar DDL ni invocar RPC."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import auditar_readonly as audit
from desplegar_16 import validate_post


def main() -> None:
    backup = json.loads((HERE / "backup_pre.json").read_text(encoding="utf-8"))
    pre = {
        "project_ref": backup["project_ref"],
        "flags": [backup["flags"]],
        "conteos": backup["conteos"],
        "locks": [backup["locks"]],
        "workers": backup["workers"],
        "huellas": {k: [v] for k, v in backup["huellas"].items()},
        "marcadores_07_15": [[True] * 9],
    }
    post = audit.snapshot()
    structural = validate_post(pre, post)
    print(json.dumps({
        "project_ref": post["project_ref"],
        "estructural": structural,
        "conteos_antes": pre["conteos"],
        "conteos_despues": post["conteos"],
        "flags_finales": post["flags"],
        "locks_finales": post["locks"],
        "workers_finales": post["workers"],
        "huellas_sin_cambios": post["huellas"] == pre["huellas"],
        "documento_reclamado": False,
        "produccion_economica_modificada": False,
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
