# Hito 2BG: R19, ECO360 = grupo Alliance/SAFA en conciliación

2026-10-30. Solo local; producción solo con lecturas READ_ONLY de medición. Origen: diagnóstico READ_ONLY de
08007970 (DIFERENCIA 38,98): la línea 08M26912 (39,05) existe en Farmatic (280247, mismo número, fecha y PUC)
con proveedor 154 «6- PLATAF. ECO360 AH», que no entraba en el grupo SAFA.

## 1. Regla (R19, aprobada por Pio)

- ECO360 es la marca de Farmatic con la que Pio identifica compras a Alliance con precio de laboratorio; es
  **siempre** compra a Alliance/SAFA, sin excepciones. No hay otras plataformas.
- En conciliación pertenece al grupo Alliance/SAFA/Cencora: por nombre canónico (`6PLATAFECO360AH`) y por id
  (154 ≡ 2, con R9).
- Se conservan los literales; numeración, ventanas, R15 y R15b no cambian.
- R17 sigue exigiendo el mismo id con R9 (`cf_linea_r17_valida` lo revalida en la BD).
- Alternativa descartada: cambiar el proveedor en Farmatic. Se pierde la marca de Pio y cada caso exigiría una
  aprobación R18.

## 2. Medición (`CONFIRMADO POR LECTURA READ_ONLY`)

`pruebas/auditoria_2bg/medicion_readonly.py` (`lectura` y `medir`; volcado del 2BE). Evidencias en
`C:\ControlFarmacias\evidencias_2bg\` (con `SHA256SUMS.txt`).

- Proveedores con PLATAF/ECO: solo ECO360 es plataforma (70 albaranes, ids `154` y `0154 `); ECOCEUTICS (150)
  y REIG JOFRE (9028) son laboratorios y quedan fuera.
- Albaranes ECO360 en facturas de Supabase: 1 (08M26912 de 08007970).
- Banco Alliance del 2AZ (47) con la regla aplicada en memoria: 9 facturas cambian y hay 15 casados nuevos,
  todos por número exacto, en la misma fecha (uno a +1 día) y con el PUC a ±0,01. Pasan a CONCILIADA 08007970
  (38,98 → −0,07; la única en producción), 08007500, 08008428, 08008835, 08010086 y 08010462; reducen la
  diferencia 08008427, 08011304 y 08011734. Efectos colaterales: 0. Parejas R17 mixtas 2 + 154: 0.

## 3. Implementación

- `src/facturas/runtime_supabase/conciliacion.py`:
  - `6PLATAFECO360AH` en `_ALIASES_ALLIANCE_AUTORIZADOS` (camino por nombre);
  - `_ID_PROVEEDOR_GRUPO_ALLIANCE` y `_id_proveedor_grupo` (R9 + R19), usados solo en `_filas_del_proveedor`
    (camino por id);
  - la comparación de R17 sigue con `_id_proveedor_comparable` (R9 sin R19).
- Sin migración: la BD no valida el proveedor en los detalles 1:1.

## 4. Tests

- `tests/facturas/runtime_supabase/test_r19_2bg.py` (sin BD): nombre, id en ambos sentidos con R9, otros
  proveedores fuera, 08M26912 casa, ECO360 con número de proveedor distinto no casa por importe, R17 no mezcla
  ECO360 y SAFA (con control positivo), R9 sin R19.
- `tests/facturas/runtime_supabase/test_integracion_pg17_2bg.py` (`pg17_local`, plantilla 24): **08007970 real**
  (PDF del 2AO, PUC reales) CONCILIADA −0,07 con 71 casados y 280247 reservado; sin R19, DIFERENCIA 38,98.

## 5. Fuera de alcance

- Conciliar 08007970 en producción: requiere confirmación de Pio (procedimiento del 2AT). Hecho el 2026-10-30
  (CONCILIADA −0,07; ver `docs/contexto/ESTADO_ACTUAL.md`).
