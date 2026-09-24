# Revalidacion previa al despliegue 2P

Archivo sin modificaciones: sql/migrations/15_cf_multifactura.sql.
SHA256: aa28b84225f62f0337e71b3b869b6c1e6030f4a1d8a56f9a5eb787d2de60f8a3.

Repetido `pruebas/certificacion_multifactura_2o1.py` con el Python existente
`C:\ControlFarmacias\Programa\.venv\Scripts\python.exe`.
Resultado: exit 0, dos ciclos PostgreSQL 17 aislados completos.
Ambos ciclos verifican esquema, RLS/policies/grants, rol service_role, rechazo anon,
N=1/3/5, claves economicas, B/relectura/C, incompletas, duplicadas y versiones,
copias internas, rollback transaccional, claim individual, conciliaciones
independientes, reaplicacion idempotente y postflight. Contenedores/volumenes
exclusivos de prueba eliminados al terminar cada ciclo.

Migracion 14 local intacta, SHA256:
7f13eeac1e395e30c7707df5f4b7708f8ebcafd4763121a3dfd5adc429d2ab15.

Preflight productivo READ ONLY: proyecto, flags, facturas, conteos, huellas,
funciones V2, restriccion, RLS, policies y grants coinciden con snapshot_post del
Hito 2N. Dos facturas, flags false/false/false, farmacias [PIO], locks 0/0.
Ninguna funcion/columna de 15 existe previamente. Procesos Python Windows: cero,
comprobados via CIM fuera del sandbox; sesiones worker/runtime en PostgreSQL: cero.
El primer intento CIM en sandbox fue denegado; no se modificaron permisos.

Snapshot_pre.json conserva definiciones, columnas, constraints, indices, permisos,
RLS, policies y huellas. Rollback_15.sql preparado antes de despliegue; NO ejecutado.
No hay credenciales ni PDFs dentro de estos artefactos.
