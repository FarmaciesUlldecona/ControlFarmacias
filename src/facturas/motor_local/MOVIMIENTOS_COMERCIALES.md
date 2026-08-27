# Movimientos comerciales y sentido

La existencia del movimiento, su concepto/categoría y su sentido económico son dimensiones independientes.

- `descripcion_literal` conserva siempre el concepto visible y su evidencia.
- `tipo` permite una categorización conservadora (`SERVICIO`, `RAPPEL`, `BONIFICACION`, `DESCUENTO`, `CONDICION_COMERCIAL`, `CONDICION_COOPERATIVA` u `OTRO`) sin determinar sentido.
- `sentido` solo es `CARGO` o `ABONO` con evidencia literal o estructural inequívoca; en otro caso es `null`.
- `SENTIDO_NO_DOCUMENTADO` es una incidencia no bloqueante y los controles dependientes quedan `NO_EVALUABLE`.

No se infiere sentido por descripción, signo, proveedor, ID, prefijo, nombre de archivo, DIRECT, posición, orden ni gold. Un movimiento indeterminado conserva descripción, categoría, base, importe, IVA, recargo y evidencias.

Una explotación histórica futura debe mantener tres conjuntos disjuntos: `CARGOS_CONFIRMADOS`, `ABONOS_CONFIRMADOS` y `SENTIDO_INDETERMINADO`. Los indeterminados nunca se suman automáticamente a cargos o abonos.

`CONDICION_COOPERATIVA` identifica un concepto económico explícitamente cooperativo y no es sinónimo de `CONDICION_COMERCIAL`, `SERVICIO` ni `CUOTA` genérica. Puede consultarse y agregarse por categoría, proveedor, factura y fecha; no implica automáticamente `CARGO`.
