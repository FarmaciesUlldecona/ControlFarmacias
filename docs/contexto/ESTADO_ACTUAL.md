# Estado actual

Actualizado: 2026-09-24.

## Git y respaldo

- Repositorio: `C:\ControlFarmacias\Programa`.
- Rama operativa: `main`.
- Baseline del Hito 0: `f87b32ba804aa6676fa7866b131b46e6c16540e5`.
- En el preflight posterior al push, `main` y `origin/main` quedaron alineadas:
  `0 ahead / 0 behind`.
- Copias remotas adicionales verificadas:
  `backup/hito-0-preparacion-2026-09-24` en `e18acf0` y
  `hito-0-preparacion-2026-09-24` en `f87b32b`.

## Operación vigente

- PIO es la única farmacia autorizada. RITA está bloqueada.
- Valores seguros por defecto: `normalizacion_automatica=false`,
  `conciliacion_automatica=false`, `luna_habilitada=false`.
- Estos valores describen el contrato y la última certificación. El estado remoto
  vivo no se presume sin preflight productivo autorizado.
- La autoridad productiva de todos los extractores locales es `false`.
- El shadow local está apagado por defecto y, aun habilitado para observar, conserva
  la salida oficial y no aplica la salida local.
- `MANUAL_ONE_SHOT` está limitado a un documento y no admite preselección.

## Versiones y certificación

- Migración más reciente: `16_cf_worker_manual_one_shot.sql`.
- Normalizador V2 declarado por el pipeline: `2.2.0`.
- Motor documental local declarado por el servicio: `0.5.0`.
- El orquestador productivo no declara versión propia. V0.1.3 identifica una
  validación histórica del ejecutor.
- Certificación focal del Hito 0: `66 passed`.
- Suite completa recertificada del Hito 0: `1058 passed` en 53,54 s.

## Límites conocidos

- La extracción completa no está certificada para cualquier layout posible.
- La barrera documental de identidad/farmacia no está demostrada como universal en
  todos los ensambladores históricos.
- Permanecen gaps funcionales registrados para el sentido del descuento por pronto
  pago de COFARES y la relación de abonos de DERMOFARM con la factura del mes
  siguiente.
- SAFA y BEIERSDORF figuran como proveedores locales no implementados.
