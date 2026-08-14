# Recomendación arquitectónica (no implementada)

## Pipeline general

PDF → Luna V2 → validación determinista → aceptación o activación selectiva de Google Splitter → Luna V2 por segmento → deduplicación determinista → validación final. La prioridad cero es no introducir facturas, albaranes ni movimientos sin soporte documental.

## Activación sin gold

1. Activar splitter cuando el proveedor esté en el grupo de alta densidad demostrado y el documento tenga varias páginas con cabeceras/continuaciones de tabla, pero Luna devuelva cero o un conteo incompatible con indicadores documentales visibles.
2. Activar cuando existan secuencias de filas, fechas, marcadores «ALBARÁN/ALBARAN», «ABONO», «PEDIDO», PA/RE u otros identificadores repetidos y el número de registros Luna sea inferior al conteo determinista de señales. Las señales solo disparan revisión; no crean registros.
3. Activar ante tabla que cruza páginas, reinicio de cabecera, factura multifactura o no conciliación aritmética entre subtotales documentales y suma de registros Luna.
4. Deduplicar por proveedor normalizado + número de factura. Fecha e importe son apoyo; nunca deben fusionar números distintos. Ante conflicto, incidencia y conservación de ambas salidas sin elegir por inferencia.
5. Tras splitter, rechazar nuevos identificadores sin literal demostrable y comparar prefijos/componentes sin modificar el valor documental.

## Reglas por proveedor justificadas

- Alliance: justificado por 162/167 ausentes B (97,01%) concentrados en 08009277 y recuperación C 162/162. Activar con factura multipágina de alta densidad cuando Luna devuelva cero albaranes o no concilie filas/ABONOS.
- FEDEFARMA: no usar splitter como corrección automática de claves. Validar identificadores compuestos P + PA/RE + número; B y C mantienen 5/5 fallos exactos por prefijo. Conservar el literal y abrir incidencia si no puede recomponerse de evidencia estructural.
- Cofares y HEFAME: no se justifica activación por proveedor con estos errores B de albaranes (0 ausentes). Sí activar por señales generales verificables de tabla multipágina/no conciliación.
- Resto: sin regla específica por proveedor en este conjunto.

## Umbrales objetivos derivados

- Cero registros Luna con al menos dos señales documentales independientes y repetidas de filas de albarán: activar.
- Documento multipágina con continuidad de tabla y conteo Luna menor que el conteo de identificadores inequívocos: activar.
- Diferencia aritmética no explicada: activar revisión/splitter, pero preservar total fiscal y literales; nunca fabricar el concepto compensatorio.
- Toda salida del splitter pasa por la misma clave exacta y control de invenciones antes de sustituir B.
