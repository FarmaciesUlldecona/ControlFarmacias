# Evaluación independiente de la normalización Alliance 08008427

## Aislamiento

El resultado normalizado ya existía antes de cargar el patrón. La inspección estática del módulo y del CLI de normalización no encontró referencias al patrón, análisis comparativos, Azure, Google ni la extracción especializada anterior.

## Resumen

| Métrica | Resultado |
|---|---:|
| Campos atómicos evaluados | 1056 |
| Correctos | 1003 |
| Diferencias reales | 52 |
| Diferencias de formato | 1 |
| Deliberadamente no completados | 0 |
| Nota de acierto estricto | 94.98 % |
| Cobertura | 100.00 % |
| Albaranes esperados / normalizados | 147 / 147 |
| Albaranes con contenido correcto | 147 |
| Albaranes completamente correctos incluido orden | 96 |
| Albaranes inventados | 0 |

## Diferencias relevantes

- El importe del vencimiento queda deliberadamente en null porque no está unido visualmente a la fecha.
- Los 147 albaranes conservan número, fecha, movimiento, descripción, base y total. El orden difiere para 146 porque el normalizador usa orden físico determinista por tablas paralelas y lo marca como reconstruido.
- `impuestos=[]` coincide con el patrón; la incidencia conserva que el desglose literal era incompleto.
- El ajuste Servicio básico se reconstruye desde GASTOS y sus indicadores de inclusión quedan sustentados por sumas visibles.
- El nombre visible del destinatario puede diferir del nombre interno esperado; ID y método proceden explícitamente de configuración interna.

## Estados de albaranes

- CORRECTO_COMPLETO: 96
- CORRECTO_CONTENIDO_ORDEN_DIFERENTE: 51

## Configuración interna

Los campos `categoria`, `requiere_conciliacion_albaranes`, `destinatario.id_farmacia` y `destinatario.metodo_identificacion` están etiquetados como configuración interna, no como extracción de IA.
