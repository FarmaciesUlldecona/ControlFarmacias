"""Inspeccion read-only y sin valores personales del modo de Google DriveFS."""
from __future__ import annotations

import sqlite3
from pathlib import Path


DB = Path(r"C:\Users\Usuari\AppData\Local\Google\DriveFS\root_preference_sqlite.db")


with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as conexion:
    for nombre, sql in conexion.execute(
        "select name, sql from sqlite_master where type='table' order by name"
    ):
        print(f"{nombre}|{sql}")
    print("---ROOTS_SANITIZED---")
    for fila in conexion.execute(
        "select root_path, sync_type, destination, medium, state, "
        "one_shot, is_my_drive, last_seen_absolute_path from roots order by root_id"
    ):
        print("|".join(str(valor) for valor in fila))
    print("---MEDIA_SANITIZED---")
    for fila in conexion.execute(
        "select last_mount_point, fs_type, device_type, capacity, ignored from media"
    ):
        print("|".join(str(valor) for valor in fila))
