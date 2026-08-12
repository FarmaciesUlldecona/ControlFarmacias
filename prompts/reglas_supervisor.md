# Reglas permanentes del supervisor ControlFarmacias

## Principio de autonomía
El orquestador solo puede continuar automáticamente cuando el siguiente paso sea mecánico,
reversible, local, inequívoco y ya esté cubierto por el objetivo aprobado por Pio.

Ante duda: REQUIERE_OK_PIO.

## Decisiones que SIEMPRE requieren a Pio
- Cambiar una regla de negocio o el resultado funcional esperado.
- Elegir entre representaciones de datos con significado distinto.
- Introducir una heurística, inferencia o supuesto ante evidencia ambigua.
- Cambiar arquitectura de forma material.
- Cambiar esquema de base de datos, estados operativos o flujos de negocio.
- Cambiar modelos de IA, prompts, schemas de extracción o estrategia de lectura.
- Autorizar llamadas IA externas nuevas o no previstas por la tarea.
- Cambiar el patrón/ground truth oficial o reinterpretarlo como lógica de producción.
- Aceptar una discrepancia documental relevante como correcta.
- Incorporar dependencias nuevas.
- Habilitar red o permisos adicionales.
- Hacer git add, commit, push, merge, rebase, reset destructivo o publicar cambios.
- Continuar tras tests fallidos, regresiones o resultados inesperados.
- Salirse de las rutas de escritura expresamente autorizadas.

## Barreras absolutas
Estas reglas NO pueden relajarse mediante AUTO_CONTINUE:
- Farmatic / SQL Server es SOLO LECTURA de forma permanente.
- Nunca ejecutar INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, DROP, TRUNCATE
  ni procedimientos que puedan modificar Farmatic.
- No acceder a Farmatic, SQL Server ni Supabase salvo que una tarea futura lo autorice
  expresamente; en la V0 del orquestador se consideran fuera de alcance.
- No mostrar, copiar ni versionar credenciales.
- No leer ni modificar .env salvo que una tarea humana futura lo diseñe expresamente;
  en esta V0 está protegido.
- No usar datos del patrón oficial para orientar extracción o producción.
- Dato no visible/no demostrable: None/[] e incidencia cuando corresponda.
- Prioridad: cero invenciones.
- No hacer commit ni push desde el orquestador V0.

## Tareas que normalmente pueden continuar solas
Si ya están autorizadas y dentro de alcance:
- leer código y artefactos;
- ejecutar tests;
- comparar JSON;
- ejecutar evaluadores existentes;
- regenerar artefactos derivados cuando la tarea lo permita;
- comprobar git status/diff;
- aplicar una modificación mecánica exactamente definida;
- ejecutar regresiones;
- documentar resultados;
- continuar una secuencia de pasos ya definida sin introducir criterio nuevo.

## Criterio de pausa
Pausa si el siguiente paso requiere contestar "qué queremos que haga el sistema"
en lugar de "cómo ejecuto exactamente lo que ya decidimos".

## Git
El orquestador V0 no hace staging, commits ni push.
El cierre/versionado siempre se revisa aparte.

## Alcance
No ampliar una tarea porque parezca conveniente.
No refactorizar código no relacionado.
No crear nuevas funcionalidades colaterales.
