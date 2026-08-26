# Uso del Orquestador para Pio

## Instalación

Abre PowerShell y ejecuta:

```powershell
Set-Location C:\ControlFarmacias\ControlFarmacias_Orquestador_V0_2_dev
.\INSTALAR_CF.ps1 -AgregarPathUsuario
```

La opción para añadir la carpeta al PATH es explícita, solo afecta al usuario actual y no requiere administrador. Abre una PowerShell nueva después de instalar.

## Órdenes

```powershell
cf "estado"
cf "comprueba git"
cf "qué presupuesto queda"
cf "ejecuta los tests focales del orquestador"
cf "corrige un cambio pequeño en el orquestador y no hagas commit"
cf "corrige el extractor de Cofares, valida que quede bien y no hagas commit"
```

Usa `cf --json "estado"` si necesitas el resultado técnico completo. Ejecuta `cf` sin argumentos para entrar en modo interactivo y escribe `salir` para terminar.

## Seguridad y recursos

- `LOCAL_ONLY` significa que no se utiliza Codex: consultas, Git de lectura, presupuesto y tests locales.
- Un cambio pequeño puede usar `CODEX_LIGHT`; varios archivos usan `CODEX_STANDARD`.
- Trabajo transversal o HEAVY se detiene y pide autorización de coste.
- El presupuesto semanal es 3,80 EUR y aparece un aviso desde 3,04 EUR.
- No se inventan costes. Un coste desconocido se muestra como desconocido.
- Farmatic es siempre solo lectura.
- Commit y push necesitan autorización explícita y siguen pasando por el supervisor.
- Una referencia ambigua se detiene para que Pio la aclare.
