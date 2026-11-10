# Configuración de la web ControlFarmacias (fase 1)

Solo lectura y solo en el PC de Pío (`127.0.0.1`). Nunca nube ni Vercel.

## `web\app\.env.web` (solo modo REAL)

Fichero gitignored que crea y edita **solo Pío**. Lo leen únicamente el modo REAL
(`dev:real`) y `check:real`. Nunca el `.env` de Programa, `service_role` ni `ControlFarmaciasRO`.

| Variable | Obligatoria | Contenido |
|---|---|---|
| `CF_LECTURA_HOST` | sí | Host de la base de datos |
| `CF_LECTURA_PORT` | sí | Puerto (entero positivo) |
| `CF_LECTURA_USER` | sí | `cf_lectura` o `cf_lectura.<project_ref>` (pooler). Cualquier otro usuario: no arranca |
| `CF_LECTURA_DB` | sí | Nombre de la base de datos |
| `CF_LECTURA_PASSWORD` | sí | Contraseña del rol `cf_lectura` |
| `CF_LECTURA_CA` | no | Ruta del certificado CA (absoluta o relativa a `web\app`). Por defecto, el de `certs\` |
| `CF_WEB_PASSWORD_HASH` | sí (modo REAL) | Hash scrypt de la contraseña de acceso a la web. Lo crea o sustituye `npm run set-password`; nunca se escribe a mano ni se guarda la contraseña en claro |

Si falta el fichero o alguna variable obligatoria, no se conecta (`ENV_WEB_AUSENTE` / `ENV_WEB_INCOMPLETO`).
Sin `CF_WEB_PASSWORD_HASH` válido el modo REAL no arranca (`HASH_ACCESO_NO_VALIDO`). El hash se lee del
propio `.env.web`, no del entorno del proceso.

## Acceso con contraseña (H4b)

- Usuario único: **Pío**. Antes de cualquier pantalla o `/api` se pide la contraseña.
- Sesión en memoria del servidor: se pierde al reiniciar la web. Cookie `cf_sesion` HttpOnly,
  SameSite=Strict, sin fecha de caducidad (desaparece al cerrar el navegador). Botón **Salir** en el menú.
- 5 intentos fallidos seguidos bloquean el acceso 5 minutos (también con la contraseña correcta).
  Los mensajes de error son genéricos.
- Solo `POST /api/login` y `POST /api/logout` admiten POST (y solo desde la propia web); todo lo demás, GET.
- Modo FIXTURES: contraseña ficticia fija `fixtures-ficticia` (solo datos ficticios). El modo REAL no
  arranca si su hash admite esa contraseña (`HASH_ACCESO_ES_EL_DE_FIXTURES`).

### Fijar o cambiar la contraseña (`npm run set-password`, solo Pío)

1. Abrir una consola en `C:\ControlFarmacias\Programa_web\web\app`.
2. `npm run set-password`.
3. Escribir la contraseña (mínimo 10 caracteres, sin espacios al principio ni al final) y repetirla.
   No se muestra al escribir.
4. El script crea o sustituye la línea `CF_WEB_PASSWORD_HASH=…` de `.env.web` sin tocar las demás.
5. Reiniciar la web para aplicarla.

## Arranque con acceso directo (`iniciar_web.cmd`, solo Pío)

`web\app\iniciar_web.cmd` arranca la web en modo REAL en `http://127.0.0.1:4747` y abre el navegador
cuando responde. Cerrar su ventana detiene la web.

Crear el acceso directo en el escritorio:

1. En el Explorador, abrir `C:\ControlFarmacias\Programa_web\web\app`.
2. Clic derecho sobre `iniciar_web.cmd` → **Mostrar más opciones** (Windows 11) → **Enviar a** →
   **Escritorio (crear acceso directo)**.
3. Opcional: clic derecho sobre el acceso directo → **Propiedades** → cambiar el nombre a
   "ControlFarmacias" y, en **Ejecutar**, elegir **Minimizada**.

Requisitos: `.env.web` con las variables de la tabla (incluido `CF_WEB_PASSWORD_HASH`) y Node.js 24.

## Certificado CA

- Ubicación por defecto: `web\app\certs\` (fichero `supabase-ca.crt`).
- Debe ser un certificado X.509 PEM de una CA y estar vigente. Si no, no se conecta
  (`FALTA_CERTIFICADO_CA`, `CERTIFICADO_CA_NO_VALIDO`, `CERTIFICADO_CA_CADUCADO`).
- TLS con verificación de cadena y nombre del servidor (equivale a `sslmode=verify-full`).
- El `.crt` solo se lee; nunca se modifica.

## Comandos (en `web\app`)

| Comando | Modo | Quién | Qué hace |
|---|---|---|---|
| `npm run dev` | FIXTURES | cualquiera | Compila el front y sirve web + API en `http://127.0.0.1:4747` con datos ficticios (contraseña `fixtures-ficticia`) |
| `npm run dev:real` | REAL | **solo Pío** | Igual, con datos reales vía `cf_lectura` (lee `.env.web`). Es lo que lanza `iniciar_web.cmd` |
| `npm run set-password` | REAL | **solo Pío** | Crea o sustituye `CF_WEB_PASSWORD_HASH` en `.env.web` (ver arriba) |
| `npm run check:real` | REAL | **solo Pío** | Prueba cada consulta del contrato en transacción READ ONLY. Imprime solo nombre, OK/ERROR, nº de columnas y filas, y los diagnósticos. Las consultas por factura usan la factura más reciente sin imprimir su id |

Diagnósticos de `check:real` (solo recuentos, sí/no o nombres de columna; nunca valores):

| Línea | Contenido |
|---|---|
| `DIAGNOSTICO proveedores` | facturas, sin `proveedor_id`, catálogo, `cif_distintos`, `facturas_sin_cif` |
| `DIAGNOSTICO vencimientos` | total, con importe null, null con/sin incidencia `IMPORTE_VENCIMIENTO_NO_DOCUMENTADO`, facturas e incidencias con ese código, null sin CIF y `nulls_por_grupo_cif` (lista de recuentos por grupo de CIF, sin CIF ni nombres) |
| `DIAGNOSTICO duplicados` | candidatos (mismo proveedor R9 + número sin letra final), albaranes candidatos, grupos tras el filtro de importe, si se alcanzó el límite de 200 |
| `DIAGNOSTICO casado` | Líneas de conciliación vigentes por `clase_numero` y por `estado_matching` (provenance): `clase_numero.<etiqueta>` y `estado_matching.<etiqueta>` con etiquetas fijas y `sin_valor`. Un valor no previsto sale como `<eje>.no_previsto.<VALOR>=n` solo si es un código (`^[A-Z0-9_]{1,40}$`); cualquier otro suma en `otros_no_codigo` sin mostrarse |
| `DIAGNOSTICO par_08C66676` | filas de cada número, existen ambos, mismo proveedor R9, mismo `importe_puc` y nombres de las otras columnas numéricas de `albaranes` que coinciden |

Otros: `npm run typecheck`, `npm run fixtures:gen`, `npm run fixtures:check`, `npm run test:unit`
(acceso y set-password con fichero temporal), `npm run test:e2e` (Playwright, solo FIXTURES; puertos 5181 y
5182).

El modo se elige con `--modo=FIXTURES|REAL` (lo usan `dev` y `dev:real`) o con la variable `CF_MODO`.
Si ambos están y no coinciden, el servidor no arranca. Puerto fijo **4747**, solo `127.0.0.1`. `CF_PUERTO`
solo se admite en FIXTURES (Playwright); en REAL, cualquier valor distinto de 4747 impide arrancar.
