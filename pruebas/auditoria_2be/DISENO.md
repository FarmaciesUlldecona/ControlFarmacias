# Hito 2BE: R17, una línea del PDF = albarán de su número + 1 interno de la misma recepción

2026-10-29. Solo local; producción solo con lecturas READ_ONLY de medición. Origen: patrón medido en el 2BD
(`pruebas/auditoria_2bd/DISENO.md`, apartado 2f). Regla aprobada por Pio.

## 1. Regla (R17, aprobada por Pio)

Una línea documental puede casar con la suma de **dos** albaranes de la **misma recepción** de Farmatic
(`albaranes.id_recepcion`, migración 22):

- **A**: el albarán de su número, exacto o con letra final (decisión del 2BA: si hay exacto, la letra final
  no cuenta). Ventana de ±15 días, la de las coincidencias de número.
- **B**: un albarán con numeración interna de Farmatic, `[A-Z]\d{6}/\d{4}` (p. ej. `Q039921/2026`).

Condiciones:
- ninguno de los dos está reservado (R15) ni casado por otra línea;
- mismo proveedor (R9);
- PUC(A) + PUC(B) dentro de la tolerancia por línea (0,05);
- ambos quedan reservados;
- solo 1+1 y solo cargos.

Decisiones de implementación (no cambian la regla; tomadas por Claude, a confirmar por Pio):
- R17 solo se intenta en las líneas que quedan `SIN_COINCIDENCIA` tras el casado 1:1: el 1:1 tiene prioridad y
  sus albaranes ya no están libres.
- Falla cerrado sin depender del orden:
  - más de una pareja para una línea → `AMBIGUO_R17`;
  - un albarán en las parejas de dos líneas → `CONFLICTO_R17` en ambas.
  En los dos casos la línea queda sin casar.
- B no puede tener un número que sea una línea documental de otra factura (opción 2 de R15).
- No se aplica a HEFAME (casado propio por número exacto) ni a abonos.
- R11: una línea R17 cuenta como **un** albarán casado (n = líneas documentales casadas). Igual que en la
  medición. Para 08007969 no cambia nada: está en el tope de 0,50.

## 2. Medición (paso 1, `CONFIRMADO POR LECTURA READ_ONLY`)

`pruebas/auditoria_2be/medicion_readonly.py`. Evidencias en `C:\ControlFarmacias\evidencias_2be\` (con
`SHA256SUMS.txt`).

- **`volcado`** (Usuari, sesión de solo lectura del 2AT, 2026-10-29 16:45 UTC):
  - 5.970 albaranes, 5.969 con `id_recepcion`;
  - 285 reservas;
  - 0 ausentes;
  - 12 facturas.
- **`medir`**, sin conexión: banco Alliance del 2AZ (47 facturas) con el código de `src`, partiendo de las
  reservas vigentes.
  - **14 líneas R17, todas con una única pareja**:
    - las 12 del 2BD, idénticas;
    - 08007969 / 08C20268 = 280005 (500,86) + Q039921/2026 (280004, 3,16), recepción 50898;
    - 08010085 / 08C73435 = 685,43 + Q040394/2026 8,79, recepción 52272. Aceptada por Pio: el 2BD no la medía
      porque su banco daba 08010085 como no apta.
  - Facturas afectadas: 9. Solo **08007969 cambia de resultado**: DIFERENCIA 504,09 → CONCILIADA 0,07. Las otras
    8 reducen la diferencia y siguen en DIFERENCIA; ninguna está en producción.
  - **Riesgo de casado falso**:
    - 0 líneas ambiguas;
    - todas las recepciones implicadas tienen 2 albaranes;
    - control con internos de **otra** recepción (±3 días): 0 parejas;
    - 3 internos igualan el importe de una línea de otra factura (Q040020, Q040035, Q040654). Esas líneas tienen
      su propio albarán con número exacto, que se impone, así que no hay conflicto real.
- **`verificar`** (tras implementar): el código de `src` (`id_recepcion` en los candidatos y
  `detalles_desde_busqueda`) reproduce las 14 líneas y los resultados de las 47 facturas
  (`verificacion_src_2be.json`).

## 3. Implementación

- **`src/facturas/runtime_supabase/conciliacion.py`**:
  - `CandidatoAlbaranSupabase.id_recepcion`;
  - `ResultadoBusquedaAlbaran.complementario` e `importe_complementario`;
  - `_parejas_r17` y `_aplicar_r17`, en la segunda pasada de `buscar_albaranes_factura`;
  - `detalles_desde_busqueda`: una línea R17 son dos detalles `UNO_A_VARIOS` con el mismo origen documental, cada
    uno con el PUC de su albarán, y con `regla`, `papel_r17` e `id_recepcion` en la provenance;
  - `detalle_desde_busqueda` falla cerrado ante un resultado R17;
  - R11 cuenta la línea R17 como una.
- **`repositorios.py`**: lee `albaranes.id_recepcion` y usa `detalles_desde_busqueda`.
- **Simulador 2AT** (`pruebas/auditoria_2at/auditoria_readonly.py`): `resumen_detalles.lineas_r17` e
  `id_recepcion` del albarán operacional.
- **Migración 24** `24_cf_r17_recepcion.sql` (+ rollback), generada por
  `pruebas/auditoria_2be/generar_migracion_24.py` desde el texto exacto de la 22. Sin tablas nuevas: las reservas
  R15 ya admiten dos albaranes por línea.
  - `cf_persistir_conciliacion`: R11 con la línea R17 como una; cada línea `UNO_A_VARIOS` se revalida con
    `cf_linea_r17_valida` (auxiliar, solo propietario):
    - exactamente 2 detalles y ningún otro detalle en la línea;
    - la línea es un cargo de la propia factura;
    - los dos albaranes existen y cada detalle aplica su PUC;
    - uno, y solo uno, tiene numeración interna;
    - misma recepción, no nula;
    - mismo proveedor (R9);
    - el otro tiene el número de la línea, exacto o con letra final;
    - la suma está dentro de 0,05.

    Si no se cumple → `LINEA_R17_NO_VALIDA` y nada escrito.
  - Privilegios del patrón 22: la RPC solo `service_role`; la auxiliar, nadie.
  - Rollback = esquema 23 exacto.
- **`pruebas/auditoria_2be/desplegar_24.py`** (patrón del 23): SHA contra el commit, 9 precondiciones de solo
  lectura y postcondiciones de datos sin cambios, RPC y privilegios.
- **Orden de despliegue: primero la 24 y después conciliar.** El código 2BE con la 23 no persiste una línea R17:
  R11 de la BD no la cuenta → `TOLERANCIA_REGLA_NO_COINCIDE`, se registra un fallo y se consume un intento. El
  simulador 2AT no lo detecta, porque no conoce la versión de la BD. Las facturas sin líneas R17 no cambian.
  Las tareas nocturnas no importan `runtime_supabase`.

## 4. Tests

- `tests/facturas/runtime_supabase/test_r17_2be.py`, sin BD:
  - caso real;
  - letra final y prioridad del exacto;
  - prioridad del 1:1;
  - variantes que no casan: otra recepción, sin recepción, sin interno, otro número, suma fuera, otro proveedor,
    reservados, número de otra factura, fuera de ventana;
  - abono y HEFAME;
  - interno ya casado 1:1;
  - ambigüedad y conflicto;
  - varias líneas R17.
- `tests/facturas/runtime_supabase/test_integracion_pg17_2be.py` (`pg17_local`; plantillas `24`/`24_rollback`):
  - rollback = 23 y datos intactos; la 24 exige la 23; privilegios;
  - **08007969 real**, con el PDF del 2AO y la recepción 50898: CONCILIADA 0,07, 127 + 1 casados, las dos
    reservas;
  - sin recepción común: DIFERENCIA 504,09;
  - código sin la 24: no persiste;
  - simulador 2AT con la línea R17;
  - la BD rechaza 13 parejas falsas y acepta la letra final y la pareja válida;
  - R15 sobre un albarán R17;
  - precondiciones de solo lectura y ensayo completo de `desplegar_24.py`.

## 5. Fuera de alcance

- Desplegar la 24 y conciliar 08007969 en producción: hito 2BE-D, con confirmación de Pio.
- Parejas 1+N o N+1, y abonos.
- Modificar Farmatic.
