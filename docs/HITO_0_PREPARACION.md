# Hito 0 — preparación previa a migración

Fecha: 2026-09-24.

## Alcance

1. Backup remoto de los 18 commits locales.
2. Contexto canónico compartido.
3. Cierre de accesos nativos en wrappers read-only de Farmatic.
4. Alineación de `persistir_multifactura()` con migración 16.
5. Aislamiento de logs e índice de ingesta durante pytest.
6. Certificación final y cierre Git.

## Checkpoints

- Auditoría inicial ejecutada sin conectar a Farmatic ni Supabase.
- Rama remota `backup/hito-0-preparacion-2026-09-24` verificada en `e18acf0`.
- Huecos `Connection.execute()` y `Cursor.commit()` confirmados en `__getattr__`.
- Desajuste confirmado: helper de seis parámetros frente a firma autorizada de siete
  parámetros después de migración 16.
- Escritura de logs durante importación de tests confirmada y aislada.

## Certificación final

- Pruebas focales: `66 passed` en 3,41 s.
- Suite final desde la raíz, limitada por `pytest.ini` a `tests/`:
  `1058 passed` en 51,95 s.
- Instantánea antes/después: `logs/` sin cambios.
- Instantánea antes/después: `data/` sin cambios.
- No se conectó a Farmatic ni Supabase y no se modificó producción.
- La recolección desde la raíz detectó temporales históricos con ACL denegada;
  `pytest.ini` fija `tests/` como raíz oficial y excluye temporales.
