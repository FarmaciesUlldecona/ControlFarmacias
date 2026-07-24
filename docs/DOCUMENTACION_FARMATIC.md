# Documentación funcional de Farmatic

## Objetivo

Este documento recoge el significado funcional de las tablas, columnas, códigos y relaciones de la base de datos de Farmatic utilizados en el proyecto ControlFarmacias.

La información documentada se obtiene mediante:

- consultas de solo lectura sobre SQL Server;
- comparación con información visible en Farmatic;
- validación mediante registros reales;
- comprobación de procesos de negocio de la farmacia.

## Regla de seguridad

La base de datos SQL Server de Farmatic es siempre de solo lectura.

Nunca se realizarán operaciones de escritura, modificación o eliminación sobre Farmatic.

Operaciones prohibidas:

- INSERT
- UPDATE
- DELETE
- MERGE
- CREATE
- ALTER
- DROP
- TRUNCATE

Toda la información propia de ControlFarmacias se almacenará fuera de Farmatic, principalmente en Supabase.

---

# Estados de validación

| Estado | Significado |
|---|---|
| ✅ Confirmado | Significado comprobado directamente en Farmatic mediante registros reales |
| 🟡 Probable | Existen indicios suficientes, pero todavía falta validación definitiva |
| ❓ Pendiente | Significado todavía desconocido o pendiente de investigación |

---

## Campos documentados

### Estado

Tipo de dato observado:

```text
Carácter de un solo valor