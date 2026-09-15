# Certificación de seguridad SQL en modo solo lectura

Fecha inicial: 14 de septiembre de 2026
Integración y validación final: 15 de septiembre de 2026
Proyecto certificado: `C:\ControlFarmacias\Programa`
Base de datos: `Farmatic`
Identidad dedicada: `MOSTRADOR\ControlFarmaciasRO`

## Resultado

**APTO PARA CONSULTAS SQL DE SOLO LECTURA.**

La conexión queda autorizada únicamente cuando se cumplen simultáneamente estas condiciones:

- La identidad de Windows y el inicio de sesión SQL efectivo son `MOSTRADOR\ControlFarmaciasRO`.
- La base de datos activa es `Farmatic`.
- La identidad pertenece a `db_datareader` y dispone de `SELECT`.
- La identidad no es `sysadmin`, `db_owner`, `db_datawriter` ni `db_ddladmin`.
- La identidad no dispone de `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `EXECUTE` ni `CONTROL`.

Si falla cualquiera de estas condiciones, la aplicación cierra la conexión y se detiene.

## Evidencias verificadas

La comprobación directa de SQL Server devolvió:

| Comprobación | Resultado |
| --- | --- |
| `SUSER_SNAME()` | `MOSTRADOR\ControlFarmaciasRO` |
| `ORIGINAL_LOGIN()` | `MOSTRADOR\ControlFarmaciasRO` |
| `USER_NAME()` | `MOSTRADOR\ControlFarmaciasRO` |
| `sysadmin` | No |
| `db_owner` | No |
| `db_datareader` | Sí |
| `db_datawriter` | No |
| `SELECT` | Sí |
| `INSERT` | No |
| `UPDATE` | No |
| `DELETE` | No |
| `ALTER` | No |
| `EXECUTE` | No |

También se verificó correctamente:

- Apertura de la conexión mediante el nuevo control centralizado.
- Lectura real e inocua de una fila de `dbo.Albaran`.
- Rechazo de una conexión iniciada con una identidad administrativa distinta.
- Bloqueo local de operaciones de escritura, cambios de estructura, ejecución, bloqueos de filas y consultas múltiples.
- Bloqueo de `commit` y `executemany` desde la envoltura de conexión.
- Tiempo máximo de conexión de 5 segundos y de consulta de 30 segundos.
- Uso de cifrado en tránsito y declaración `ApplicationIntent=ReadOnly`.

## Pruebas automáticas

Archivo: `tests/test_seguridad_sql_lectura.py`

Resultado obtenido con Python 3.13.14, pyodbc 5.3.0 y pytest 9.1.1:

```text
21 passed in 0.23s
```

Las pruebas de órdenes peligrosas son locales: ninguna orden de escritura se envió a Farmatic.

La versión integrada en `C:\ControlFarmacias\Programa` superó además la prueba final de conexión y lectura real bajo `MOSTRADOR\ControlFarmaciasRO`, con resultado `PROGRAMA CERTIFICADO - LECTURA REAL OK: 1`.

## Capas de protección

1. Usuario de Windows dedicado y sin privilegios administrativos.
2. Permisos efectivos de SQL Server limitados a lectura.
3. Certificación automática de identidad y permisos al abrir cada conexión.
4. Validador central que solo admite consultas de lectura.
5. Bloqueo adicional de métodos capaces de persistir operaciones.

## Condiciones de validez

La certificación debe repetirse si se cambia la cuenta de Windows, los permisos de SQL Server, la base de datos, el controlador ODBC o el módulo de conexión. El acceso a Farmatic debe realizarse abriendo Visual Studio Code como `ControlFarmaciasRO`.
