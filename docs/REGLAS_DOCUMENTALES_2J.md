# Auditoria local 2J

No se ejecutaron importadores, workers, servicios externos ni escrituras productivas.

## Clasificacion de usos

| Clase | Componentes | Uso / resultado |
|---|---|---|
| A TECNICO_VALIDO | importador, Storage, SQLite | Ruta de localizacion, SHA binario, cache e idempotencia. No identifican obligacion economica. |
| A TECNICO_VALIDO | pipeline V2, observabilidad, backend | Apertura de PDF, trazas, archivo_origen y provenance de pagina/SHA. |
| A TECNICO_VALIDO | motor_local, segmentacion, adaptadores | Routing por texto y geometria. SHA en provenance. RUTA dentro de una cabecera es texto documental de reparto. |
| A TECNICO_VALIDO | scripts de evaluacion, tests | Nombres seleccionan fixtures/corpus; no son evidencia fiscal. |
| B OPERATIVO_PERO_NO_FUNCIONAL | es_factura_rita, manifiesto_pio | Encaminamiento por sufijo y periodo de carpeta. No prueba farmacia documental. |
| C FUNCIONAL_INCORRECTO / riesgo de contaminacion | probar_extraccion_alliance | Enviaba filename original al modelo. Cambiado localmente por documento.pdf; no se ejecuto API. |
| D DUDA_REQUIERE_REVISION | clave_funcional V2 | Proveedor/numero insuficientes para duplicidad. detector ahora exige ademas destinatario y tipo; solo genera revision. |
| D DUDA_REQUIERE_REVISION | adaptadores pequenos | Algunos layouts tienen constantes y posiciones especificas del corpus. La lectura universal de todos los layouts no esta certificada. |

## Cambios

- Contrato local de identidad documental con evidencia de contenido, separado del SHA binario. Comparar no fusiona, paga ni marca versiones.
- Contraste de farmacia operacional/documental con resultado contradictorio o no demostrable.
- Guard puro de snapshots conserva SOLO_SQLITE/SOLO_SUPABASE, valida hashes y bloquea cruces de farmacia. No elimina historicos HEFAME.
- Test pgcrypto/manifiesto usa fixture sintetica ordenada, deduplicada y unida por LF; deja de consultar SQLite vivo.
- Logista recorre filas de todas las paginas del segmento; conserva numeros y evidencia individual. No inventa pedidos comunes para varios albaranes.
- Repositorio de conciliacion: imports ausentes corregidos. Reglas economicas previas preservadas.

## Limites de certificacion

La capa de identidad y contraste es un contrato local; no se ha integrado como
barrera universal antes de cada persistencia V1 ni en todos los ensambladores
historicos. Tampoco se ha demostrado extraccion completa para cualquier layout.
Una suite verde por si sola no permite declarar USOS_FUNCIONALES_FILENAME=0 en
todo el repositorio ni certificar la regla transversal. No se modifica SQL ni
se presenta esta auditoria como autorizacion para nuevas pruebas productivas.
