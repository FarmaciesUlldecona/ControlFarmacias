---
name: farmatic-sql-explorer
description: Explorar la base de datos Farmatic (SQL Server, solo lectura) con las herramientas de src/sql_explorer. Úsala antes de cualquier consulta a Farmatic, para buscar tablas, vistas, columnas, claves, relaciones o valores, o para consultar albaranes, proveedores u otros objetos de Farmatic.
---

# Explorar Farmatic con src/sql_explorer

## Autoridad

Esta skill es una guía operativa, no una fuente de reglas. Mandan, por este
orden, los documentos canónicos:

- `docs/contexto/CONTEXTO_MAESTRO.md`, apartados "Restricciones absolutas" y
  "Seguridad de Farmatic";
- `docs/contexto/REGLAS_CRITICAS.md`;
- `CERTIFICACION_SEGURIDAD_SQL.md`, que fija las condiciones de la conexión.

Si algo de esta skill contradice esos documentos, prevalecen ellos. En resumen:
Farmatic es estrictamente de solo lectura. Solo se ejecutan consultas
`SELECT`/`WITH` a través de los wrappers, sin bypass.

## Identidad y capas de protección

- La sesión debe ejecutarse como `MOSTRADOR\ControlFarmaciasRO` (Visual Studio
  Code abierto con ese usuario).
- El hook `.claude/hooks/verificar_identidad_farmatic.py` comprueba `whoami`
  antes del comando. Es una capa previa y no sustituye a `obtener_conexion()`.
- `obtener_conexion()` (`src/database/conexion_sql.py`) certifica en SQL Server
  la identidad, la base y los permisos, y cierra la conexión si falla alguna
  condición. Esa es la barrera efectiva.
- Nunca abras conexiones propias (`pyodbc`, `sqlcmd`, etc.) fuera de los
  wrappers.

## Herramientas

Todas usan `input()`. Desde Claude Code, pasa la entrada por tubería o llama a
la función con `-c`. Ejemplo en PowerShell:

```powershell
"Familia" | .\.venv\Scripts\python.exe -B -m src.sql_explorer.buscar_objetos
```

Timeouts del wrapper: 5 s de conexión y 30 s de consulta.

| Herramienta | Qué hace | Cuándo usarla |
|---|---|---|
| `listar_objetos` | Lista todas las tablas y vistas | Inventario completo |
| `buscar_objetos` | Tablas y vistas cuyo nombre o esquema contiene un texto | Localizar un objeto |
| `buscar_columnas` | Columnas cuyo nombre contiene un texto | Localizar un dato sin conocer la tabla |
| `describir_tabla` | Columnas y tipos de una tabla | Estructura |
| `clave_primaria` | Clave primaria de una tabla | Identidad de las filas |
| `valores_columna` | Valores de una columna: TOP 50 por defecto, máximo 500 | Dominio de un código o estado |
| `buscar_registros` | Filas filtradas por columna: 10 por defecto, máximo 100 | Contrastar registros concretos |
| `ver_tabla` | `SELECT TOP (n) *`: 20 por defecto, máximo 100 | Muestra general; evítala en tablas con datos de personas |
| `analizar_tabla` | Informe Markdown en `docs/exportaciones/analisis_tablas/` | Solo con OK de Pio: escribe en el repositorio |
| `exportar_diccionario` | Excel en `docs/exportaciones/diccionario_farmatic.xlsx` | Solo con OK de Pio: sobrescribe el diccionario |
| `mapa_relaciones` | Excel y Mermaid en `docs/exportaciones` y `docs/diagramas` | Solo con OK de Pio: escribe en el repositorio |
| `seguridad_sql` | Validador local de solo lectura; no conecta | Comprobar una consulta antes de usarla |

## Orden de trabajo

1. **Diccionario local, sin conectar.** Consulta
   `docs/exportaciones/diccionario_farmatic.xlsx`,
   `docs/exportaciones/relaciones_farmatic.xlsx`,
   `docs/exportaciones/analisis_tablas/`,
   `docs/diagramas/relaciones_farmatic.md`, `docs/tablas/` y
   `docs/DOCUMENTACION_FARMATIC.md`. Son exportaciones con fecha y pueden estar
   desactualizadas: comprueba su fecha de generación.
2. **Metadatos:** `buscar_objetos`, `buscar_columnas`, `describir_tabla` y
   `clave_primaria`.
3. **Muestra pequeña:** `valores_columna` o `buscar_registros`, con el límite
   más bajo que responda a la pregunta.
4. **Contraste con Farmatic:** el significado funcional se valida frente a lo
   que se ve en la aplicación Farmatic y con registros reales, con Pio.

## Objetos candidatos

- Los estados 🟡 Probable y ❓ Pendiente de `docs/DOCUMENTACION_FARMATIC.md`
  están pendientes de validación.
- También lo están las "relaciones probables" de los informes generados
  automáticamente.
- No los presentes como confirmados. Clasifica cada afirmación con las
  etiquetas de certeza de `CONTEXTO_MAESTRO.md`.
- Esta skill no mantiene su propia lista de candidatos: consulta esas fuentes.

## Minimización de datos personales

- Pide solo las columnas y filas necesarias para la pregunta.
- En tablas con datos de personas (clientes, pacientes, agenda, usuarios),
  usa `valores_columna` o `buscar_registros` en lugar de `ver_tabla`.
- No copies datos personales al repositorio, a la documentación ni a la
  conversación. Resume con recuentos o con valores no identificativos.
