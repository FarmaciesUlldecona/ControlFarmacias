# Hito 2BN: rol PostgreSQL de solo lectura para la web y los preflights (migración 29)

Solo local. Sin push. Producción no tocada.

## 1. Objetivo

Un rol propio, `cf_lectura`, para que la web y los preflights lean sin usar nunca la credencial del sistema: lee
lo que necesitan, no puede escribir ni ejecutar RPC que escriban y no tiene acceso a secretos.

## 2. Migración 29 (`sql/migrations/29_cf_rol_lectura.sql`)

- **Rol:** `cf_lectura` con LOGIN, `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEROLE`, `NOCREATEDB`, `NOREPLICATION`,
  `NOINHERIT`, límite de 5 conexiones. Ajustes del rol: `default_transaction_read_only = on`,
  `statement_timeout = 60s`, `idle_in_transaction_session_timeout = 60s`. No es miembro de ningún rol.
- **Credencial:** la migración **no** fija contraseña (el test lo comprueba). La fija Pio después, fuera del
  repositorio, en el editor SQL; la credencial se guarda fuera del repositorio y nunca es la del sistema.
- **Lectura (lista cerrada):** `USAGE` en `public` y `SELECT` sobre `documentos_facturas`, `facturas` y sus hijas
  (`facturas_vencimientos`, `facturas_impuestos`, `facturas_albaranes_extraidos`, `facturas_ajustes`,
  `facturas_movimientos`, `facturas_incidencias`), `historial_facturas`, `normalizacion_ejecuciones`,
  `conciliaciones`, `conciliacion_detalles`, `conciliacion_albaranes_reservados`, `albaranes`, `albaranes_cambios`,
  `albaranes_aprobaciones`, `albaranes_aprobaciones_aplicadas`, `proveedores`, `proveedores_alias`,
  `cf_configuracion` y las cuatro vistas (`v_facturas_listado`, `v_dashboard_diario`, `v_vencimientos_calendario`,
  `v_proveedores_estado`, todas con `security_invoker`). Las tablas nuevas no se conceden solas.
- **Sin escritura ni RPC:** ningún `INSERT/UPDATE/DELETE/TRUNCATE`, ninguna secuencia, ningún `EXECUTE`
  concedido. Las únicas funciones de `public` ejecutables por `PUBLIC` son dos de trigger y una inmutable de
  cálculo (`cf_resultado_conciliacion`); ninguna `SECURITY DEFINER` ni volátil es ejecutable por el rol.
- **RLS coherente:** las 15 políticas de lectura de `authenticated` pasan a aplicarse también a `cf_lectura`
  (`ALTER POLICY … TO authenticated, cf_lectura`: la misma regla, farmacias habilitadas). Las 5 tablas sin política
  de lectura (`albaranes`, `albaranes_cambios`, `albaranes_aprobaciones`, `albaranes_aprobaciones_aplicadas`,
  `conciliacion_albaranes_reservados`) reciben una equivalente solo para `cf_lectura`.
- **Secretos:** sin `USAGE` en `auth`, `storage`, `vault`, `pgsodium`, `supabase_functions`, `net`, `cron`,
  `realtime` ni `graphql` (postcondición del despliegue para los que existan). El rol no se concede a
  `authenticator`, así que la API (PostgREST) no puede cambiar a él.
- Requiere la 28 (`MIGRACION_28_AUSENTE`). Sin cambios de datos ni de funciones.

**Rollback:** retira las políticas nuevas, devuelve las 15 a `authenticated`, revoca todo y elimina el rol. Un rol
es del clúster: si otra base aún le concede algo (en los tests, las bases del contenedor; en producción, una sola
base), no se elimina y queda sin privilegios en esta base. Esquema idéntico al de la 28 (test).

## 3. Despliegue (`pruebas/auditoria_2bn/desplegar_29.py`)

Patrón de `desplegar_28.py`: SQL igual al del commit, SHA, destino productivo demostrado, 9 precondiciones en la
misma transacción (29 ausente en esta base, 28 presente, políticas de la 28 solo para `authenticated`, privilegios
mínimos, flags, locks, NORMALIZANDO, reservas, owners) y postcondiciones (datos sin cambios; atributos del rol;
lectura de la lista y nada más, ninguna escritura, ninguna secuencia, ninguna función privilegiada o volátil, sin
`USAGE` en los esquemas vedados; políticas). No contiene ni fija contraseña.

Tras el despliegue, Pio fija la contraseña en el editor SQL (fuera del repositorio) y se comprueba el inicio de
sesión del rol por el pooler (usuario `cf_lectura.<project_ref>`).

## 4. Tests (`test_integracion_pg17_2bn.py`, 42)

- Lee cada objeto previsto (24); no lee nada fuera de la lista.
- La RLS oculta las filas de una farmacia no habilitada (documentos y albaranes) y deja ver las hijas a través de
  facturas de farmacias habilitadas; roles de las 20 políticas.
- Ningún privilegio de escritura ni de secuencias; intentos reales de `UPDATE`, `DELETE`, `INSERT`, `TRUNCATE` y de
  cambiar `cf_configuracion`: denegados.
- Ninguna función `SECURITY DEFINER` ni volátil ejecutable; llamadas reales a RPC de escritura: denegadas.
- Inicio de sesión real del rol: `default_transaction_read_only = on`; lee; una escritura falla.
- Atributos del rol, sin contraseña, sin pertenencia a otros roles, ninguna `password` en la migración.
- Rollback igual a la 28; exige la 28; no altera datos; `desplegar_29.py` ensayado (aplicada; el segundo intento se
  revierte) y rechazo de un SQL distinto del commit.

## 5. Pendiente (con confirmación de Pio)

1. Preflight READ_ONLY, despliegue de la 29 con `desplegar_29.py` (commit y SHA) y postcheck 2AX.
2. Contraseña del rol fijada por Pio fuera del repositorio; prueba de inicio de sesión de solo lectura.
3. Adaptar la web y los preflights para usar `cf_lectura` en lugar de la conexión actual.
