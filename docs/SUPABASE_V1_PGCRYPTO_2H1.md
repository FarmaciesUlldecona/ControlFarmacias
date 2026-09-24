# Hito 2H.1 — compatibilidad pgcrypto/digest

## Diagnóstico productivo READ_ONLY

- `search_path`: `"$user", public, extensions`.
- pgcrypto: instalada, versión 1.3, schema `extensions`.
- firmas: `extensions.digest(text,text) -> bytea` y
  `extensions.digest(bytea,text) -> bytea`.
- En la sesión, las cuatro formas consultadas mediante `to_regprocedure`
  (cualificadas/no cualificadas, text/bytea) resuelven.

El fallo corresponde al CASO A. La sesión incluye `extensions`, pero
`cf_preflight_pio_valido()` declara `SET search_path = public`. PostgreSQL valida
el cuerpo SQL con ese entorno y no resuelve `digest(text,text)` sin schema.
La migración 07 productiva falló dentro de su transacción y dejó cero cambios.

## Corrección local

Todas las llamadas SQL se cualifican como `extensions.digest(...)`: migración
07, preflight, postflight, seed y guard de staging. No se cambió ningún
`search_path` productivo ni se añadió 07b: 07 nunca llegó a aplicarse.

El baseline crea `extensions` e instala ahí pgcrypto, y mantiene el search path
de sesión equivalente. La función conserva `SET search_path=public`, por lo que
una llamada antigua vuelve a fallar localmente y la referencia cualificada es
necesaria. `encode` pertenece al catálogo PostgreSQL y no precisó cambio.

La búsqueda final no encuentra `digest(` SQL no cualificado. Los usos restantes
de SHA-256 en Python emplean `hashlib` y no dependen de pgcrypto. Las menciones
no cualificadas restantes están limitadas al diagnóstico/test deliberado que
demuestra SQLSTATE 42883 y a documentación.

## Regresión y certificación

La prueba PostgreSQL específica demuestra:

1. pgcrypto se instala en `extensions`;
2. `SET search_path=public; SELECT digest(...)` falla con 42883;
3. `extensions.digest(...)` produce el SHA-256 conocido de `abc`;
4. la migración 07 crea `cf_preflight_pio_valido()`;
5. el dataset PIO certificado conserva 116 hashes y manifiesto
   `3edc9214c5443c7e6937b91a73d24519c6954fce441842ade46501188f8082cf`;
6. la atestación falsa sigue bloqueada.

Dos ciclos completos PostgreSQL 17 desde cero terminaron OK: baseline → 06b →
07 → 08 → 08b → 09 → 10 → 11 → 12 → postflight/guards → 13 → validación.
También pasaron RPC, rollback, idempotencia, concurrencia real de dos sesiones,
aislamiento PIO/RITA y flags apagados. Cada base fue destruida.

Tests focales: 120 passed. Suite oficial: 785 passed en 43.74 s.
Regresiones detectadas: 0.

Producción recibió en este hito exclusivamente SELECT de catálogo. No se aplicó
ninguna migración ni se ejecutó CREATE EXTENSION, ALTER, DDL o DML productivo.
