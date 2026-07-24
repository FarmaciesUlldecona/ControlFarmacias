# Análisis automático: dbo.Albaran

> Informe técnico generado automáticamente.
> Las relaciones probables deben validarse antes de
> incorporarlas a la documentación funcional.

Fecha de generación: 2026-07-24 18:24:30

## Información general

- Esquema: `dbo`
- Tabla: `Albaran`
- Número aproximado de registros: `51498`
- Fecha de creación SQL: `2004-06-28 16:50:24.513000`
- Fecha de modificación SQL: `2026-07-23 20:31:32.370000`

## Columnas

| Posición | Columna | Tipo | Nulos | Identidad | Calculada | Valor predeterminado |
|---:|---|---|---|---|---|---|
| 1 | `IdProveedor` | `char(5)` | No | No | No | `` |
| 2 | `IdAlbaran` | `char(20)` | No | No | No | `` |
| 3 | `IdContador` | `int` | No | No | No | `` |
| 4 | `Fecha` | `datetime` | No | No | No | `` |
| 5 | `ImportePVP` | `float` | No | No | No | `` |
| 6 | `ImportePUC` | `float` | No | No | No | `` |
| 7 | `Dto` | `float` | No | No | No | `` |
| 8 | `Observaciones` | `varchar(80)` | Sí | No | No | `` |
| 9 | `Tipo` | `char(1)` | No | No | No | `` |
| 10 | `Estado` | `char(1)` | No | No | No | `` |
| 11 | `Empresa` | `int` | Sí | No | No | `(0)` |
| 12 | `ImportePAlb` | `float` | No | No | No | `((0))` |
| 13 | `ImportePVer` | `float` | No | No | No | `((0))` |
| 14 | `IdAE` | `char(20)` | Sí | No | No | `` |
| 15 | `ClienteAE` | `char(20)` | Sí | No | No | `` |

## Clave primaria

- `IdProveedor` (orden 1)
- `IdAlbaran` (orden 2)

## Índices

| Índice | Tipo | Columna | Orden | Único | Clave primaria | Incluida |
|---|---|---|---:|---|---|---|
| `PK_Albaran` | CLUSTERED | `IdProveedor` | 1 | Sí | Sí | No |
| `PK_Albaran` | CLUSTERED | `IdAlbaran` | 2 | Sí | Sí | No |

## Relaciones oficiales salientes

- `dbo.Albaran.IdProveedor` → `dbo.Proveedor.IDPROVEEDOR` (`FK_ALBARAN_IDPROVEE`)

## Relaciones oficiales entrantes

- `dbo.AlbaranRecep.IdProveedor` → `dbo.Albaran.IdProveedor` (`FK_AlbaranRecep_Albaran`)
- `dbo.AlbaranRecep.IdAlbaran` → `dbo.Albaran.IdAlbaran` (`FK_AlbaranRecep_Albaran`)
- `dbo.LineaFacturaCompra.IdProveedor` → `dbo.Albaran.IdProveedor` (`FK_LineaFacturaCompra_Albaran`)
- `dbo.LineaFacturaCompra.IdAlbaran` → `dbo.Albaran.IdAlbaran` (`FK_LineaFacturaCompra_Albaran`)

## Relaciones probables

Estas coincidencias no demuestran por sí solas que exista
una relación funcional.

| Columna analizada | Tabla candidata | Columna candidata | Tipo | PK | Única |
|---|---|---|---|---|---|
| `Empresa` | `dbo.AllianceUsuarios` | `Empresa` | `int` | Sí | Sí |
| `Empresa` | `dbo.Asiento` | `Empresa` | `int` | Sí | Sí |
| `Empresa` | `dbo.AsientoDividiblePlazos` | `Empresa` | `int` | Sí | Sí |
| `Empresa` | `dbo.MedioPago_SERMEPAACT` | `Empresa` | `int` | Sí | Sí |
| `Empresa` | `dbo.MedioPago_SERMEPATPVS` | `Empresa` | `int` | Sí | Sí |
| `Empresa` | `dbo.TBAIProvinciaTributa` | `Empresa` | `int` | Sí | Sí |
| `Empresa` | `dbo.TextoFacturasMail` | `Empresa` | `int` | Sí | Sí |
| `Empresa` | `dbo.TextoParam` | `Empresa` | `int` | Sí | Sí |
| `Fecha` | `dbo.Apunte` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.ApunteAux` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.HistoEstup` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.HistoLibroOrtopedia` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.HistoLibroOrtopediaCart` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.HistoLibroReceta` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.HistoLibroRecetaVet` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.InventaAlmacen` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.InventaMA` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.ProgCarteraEnviado` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.ProgCarteraTraza` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.ProgEnvioEnviado` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.ProgEnvioInc` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.ProgEnvioObs` | `Fecha` | `datetime` | Sí | Sí |
| `Fecha` | `dbo.ProgEnvioTraza` | `Fecha` | `datetime` | Sí | Sí |
| `IdAlbaran` | `dbo.AlbaranDevol` | `IdAlbaran` | `char` | Sí | Sí |
| `IdAlbaran` | `dbo.AlbaranFamilia` | `IdAlbaran` | `char` | Sí | Sí |
| `IdAlbaran` | `dbo.AlbaranFamiliaIVA` | `IdAlbaran` | `char` | Sí | Sí |
| `IdAlbaran` | `dbo.AlbaranGrupo` | `IdAlbaran` | `char` | Sí | Sí |
| `IdAlbaran` | `dbo.AlbaranPed` | `IdAlbaran` | `char` | Sí | Sí |
| `IdAlbaran` | `dbo.AlbaranRecep` | `IdAlbaran` | `char` | Sí | Sí |
| `IdAlbaran` | `dbo.LineaAlbaran` | `IdAlbaran` | `char` | Sí | Sí |
| `IdAlbaran` | `dbo.LineaFacturaCompra` | `IdAlbaran` | `char` | Sí | Sí |
| `IdContador` | `dbo.Bases` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.CajaMon` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.CajaVen` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.CONTADORES` | `IDCONTADOR` | `int` | Sí | Sí |
| `IdContador` | `dbo.DetConfiguracion` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.Encargo` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.EncargoPendienteDispensar` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.Factura` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.FacturaAux` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.FacturaGrupo` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.FacturaRectificativaCredito` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.FacturaRedirec` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.FHISTOFORMUCOMPON` | `IDCONTADOR` | `int` | Sí | Sí |
| `IdContador` | `dbo.HistoBloqueAux` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.HistoBloqueAuxHCP` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.HistoBloqueRE` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.HistoBloqueRedir` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.LineaFactura` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.LineaFacturaCompra` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.LineaFacturaE` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.ObservacionesFactura` | `IdContador` | `int` | Sí | Sí |
| `IdContador` | `dbo.VerifactuFacturasRectificadas` | `IdContador` | `int` | Sí | Sí |
| `IdProveedor` | `dbo.AlbaranDevol` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.AlbaranDevolucionAH` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.AlbaranFamilia` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.AlbaranFamiliaIVA` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.AlbaranGrupo` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.AlbaranPed` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.AlbaranRecep` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.Bonus` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.BonusMisce` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.CLineaPedProvee` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.CLineaProvee` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.CLineaProveeAux` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.CPedProvee` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.CProvee` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.CProveeAux` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.LineaFacturaCompra` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.MatrizAlmArticu` | `IDPROVEEDOR` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.MatrizAlmGrupo` | `IDPROVEEDOR` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.MatrizAlmProveedor` | `IDPROVEEDOR` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.ProveedorAux` | `IDPROVEEDOR` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.ProveedorMargen` | `IDPROVEEDOR` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.ProveedorMargenElm` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.ProveedorNumAutoVET` | `IDPROVEEDOR` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.ProveedorProt` | `IDPROVEEDOR` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.ProveedorStockOnline` | `IdProveedor` | `char` | Sí | Sí |
| `IdProveedor` | `dbo.ProveedorValesIds` | `IDPROVEEDOR` | `char` | Sí | Sí |
| `Tipo` | `dbo.ExpReceta` | `Tipo` | `char` | Sí | Sí |
| `Tipo` | `dbo.Informe` | `Tipo` | `char` | Sí | Sí |
| `Fecha` | `dbo.Inventa` | `Fecha` | `datetime` | No | Sí |
| `IdContador` | `dbo.DetConfiguracion` | `IdContador` | `int` | No | Sí |
| `IdContador` | `dbo.Encargo` | `IdContador` | `int` | No | Sí |
| `Dto` | `dbo.AlbaranFamilia` | `Dto` | `float` | No | No |
| `Dto` | `dbo.Inventa` | `Dto` | `float` | No | No |
| `Dto` | `dbo.InventaAlmacen` | `Dto` | `float` | No | No |
| `Dto` | `dbo.InventaMA` | `Dto` | `float` | No | No |
| `Empresa` | `dbo.Alliance360Pedidos` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.AllianceDevol_DevolCaducidades` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.AllianceDevol_MOSTRADOR` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.AllianceDevol_PORTATIL` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.AllianceStockOnline_MOSTRADOR` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.AllianceStockOnline_MOSTRADOR1R` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.AllianceStockOnline_PORTATIL` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.AllianceStockOnline_REBOTICA2` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.AllianceStockOnline_REBOTICAR` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.Almacen` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.Apunte` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.CajaMon` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.CajaMonTxt` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.CashLogyContab` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.CM_CuadroMando` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.DividiblePlazos` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.Factura` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.Familia` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.LineaAlbaran` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.LineaDevolucionAH` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.LineaSaldoBloqueo` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.LineaVentaMkt` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.ModLineaVenta` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.Moneda` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.PedidoStockOnline` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.TMP_Fact_MOSTRADOR_Lineas` | `empresa` | `int` | No | No |
| `Empresa` | `dbo.TMP_Fact_MOSTRADOR3_Lineas` | `empresa` | `int` | No | No |
| `Empresa` | `dbo.TMP_Fact_REBOTICA2_Lineas` | `empresa` | `int` | No | No |
| `Empresa` | `dbo.TMP_Fact_REBOTICA4_Lineas` | `empresa` | `int` | No | No |
| `Empresa` | `dbo.TMP_Fact_REBOTICAR_Lineas` | `empresa` | `int` | No | No |
| `Empresa` | `dbo.TMP_Fact_SERVERIOF_Lineas` | `empresa` | `int` | No | No |
| `Empresa` | `dbo.Venta` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.VerifactuEnvio` | `Empresa` | `int` | No | No |
| `Empresa` | `dbo.VerifactuIncidencia` | `Empresa` | `int` | No | No |
| `Estado` | `dbo.FHISTOFORMULOTE` | `Estado` | `char` | No | No |
| `Estado` | `dbo.FLoteCalidad` | `ESTADO` | `char` | No | No |
| `Estado` | `dbo.HistoricoAlertas` | `Estado` | `char` | No | No |
| `Estado` | `dbo.LineaControlDev` | `Estado` | `char` | No | No |
| `Estado` | `dbo.LogAlertas` | `ESTADO` | `char` | No | No |
| `Estado` | `dbo.Vencimiento` | `Estado` | `char` | No | No |
| `Fecha` | `dbo.AlbaranDevol` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.AllianceFidel_CancelPendientes` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Apunte` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Asiento` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Bloque` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.BloqueEnviado` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.CajaMon` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.CajaMonTxt` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Cartera` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.CarteraAutoCartera` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.CashFarmaHistorico` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.CashLogyHistorico` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Categoria` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.ChgBloque` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.CloseUp` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.COMENTARIO` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.DelVenta` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.DispensacionREPrivadaNF` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.DividiblePlazos` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.EncargoLibroRecetaFM` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.ERCATA_FM_VARIOS` | `FECHA` | `datetime` | No | No |
| `Fecha` | `dbo.Estup` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.ESTUP_CantidadTraducida` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Estup_MOSTRADOR` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Estup_MOSTRADOR3` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Estup_PORTATIL` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Estup_REBOTICA2` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Estup_REBOTICA4` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Estup_SERVERIOF` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Fedicom_ConfAlb` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.GS1Registro` | `FECHA` | `datetime` | No | No |
| `Fecha` | `dbo.HistoBloque` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoChgFormaPago` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoEncargoFormulaReceta` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoEncargoLibroRecetaFM` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoEnvio` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoEstupDosis` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoFormulaReceta` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoFormulaRecetaVet` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoOferta` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoProgMinMax` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoPvpIndep` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Historico` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoricoAlertas` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoricoCashDro` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.HistoValeEstu` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.IncidenciaImportacion` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroOrtopedia` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroOrtopediaOff` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroReceta` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroReceta_MOSTRADOR` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroReceta_MOSTRADOR3` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroReceta_REBOTICA2` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroReceta_REBOTICA4` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroReceta_SERVERIOF` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroRecetaElecDilig` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroRecetaOFF` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroRecetaVet` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LibroRecetaVetOff` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LineaRE` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LineaRecepcionLote` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LineaRecepPvpIndepOff` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LineaREPriv` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LineaREVet` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LineaVentaLote` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.ListaArticu` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.ListaCliente` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LogAlertas` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LogNet` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LogPreciosCGCOF` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.LR` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Pedido` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.PedidoCISMED` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.PP_Pedido` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.PreciosLastActDieto` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.PreNo_Recepcion` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.PvpIndep` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Recep` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.SubastadosAndalucia` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.TelematicaBonus` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.TelematicaCambios` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.TelematicaCatalogo` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Temporales` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.TMP_Fact_MOSTRADOR_Lineas` | `fecha` | `datetime` | No | No |
| `Fecha` | `dbo.TMP_Fact_MOSTRADOR3_Lineas` | `fecha` | `datetime` | No | No |
| `Fecha` | `dbo.TMP_Fact_REBOTICA2_Lineas` | `fecha` | `datetime` | No | No |
| `Fecha` | `dbo.TMP_Fact_REBOTICA4_Lineas` | `fecha` | `datetime` | No | No |
| `Fecha` | `dbo.TMP_Fact_REBOTICAR_Lineas` | `fecha` | `datetime` | No | No |
| `Fecha` | `dbo.TMP_Fact_SERVERIOF_Lineas` | `fecha` | `datetime` | No | No |
| `Fecha` | `dbo.ValeEstupef` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.Vencimiento` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.VendedorTurno` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.VentaFicherosSeleccionadosRE` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.VentaTarjetaDto` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.VESTUP_CantidadTraducida` | `Fecha` | `datetime` | No | No |
| `Fecha` | `dbo.VESTUPMOVIMIENTOS_CantidadTraducida` | `Fecha` | `datetime` | No | No |
| `IdAlbaran` | `dbo.LineaFacturaCompra` | `IdAlbaran` | `char` | No | No |
| `IdContador` | `dbo.CajaMon` | `IdContador` | `int` | No | No |
| `IdContador` | `dbo.CajaMonTxt` | `IdContador` | `int` | No | No |
| `IdContador` | `dbo.Factura` | `IdContador` | `int` | No | No |
| `IdContador` | `dbo.Farmacia` | `IdContador` | `int` | No | No |
| `IdContador` | `dbo.FCOMPONENTE` | `IDCONTADOR` | `int` | No | No |
| `IdContador` | `dbo.Fformula` | `IDCONTADOR` | `int` | No | No |
| `IdContador` | `dbo.FHistoFormula` | `IDCONTADOR` | `int` | No | No |
| `IdContador` | `dbo.FHISTOFORMULOTE` | `IDCONTADOR` | `int` | No | No |
| `IdContador` | `dbo.FHONORARIO` | `IDCONTADOR` | `int` | No | No |
| `IdContador` | `dbo.FPACIENTE` | `IDCONTADOR` | `int` | No | No |
| `IdContador` | `dbo.HistoBloque` | `IdContador` | `int` | No | No |
| `IdContador` | `dbo.Medico` | `IdContador` | `int` | No | No |
| `IdContador` | `dbo.TMP_Saldos_MOSTRADOR2_VFacturaPagada` | `IdContador` | `int` | No | No |
| `IdContador` | `dbo.TMP_Saldos_PUIGPC_VFacturaPagada` | `IdContador` | `int` | No | No |
| `IdContador` | `dbo.Venta` | `IdContador` | `int` | No | No |
| `IdProveedor` | `dbo.AllianceDevol_DevolCaducidades` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA21042342` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA21346912` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA21349081` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA21373613` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA21661693` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA21872312` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA21973372` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA22074252` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA22173693` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA22455611` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA22674311` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA22761838` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA22872829` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusMisceREBOTICA23160521` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA2` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA21042342` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA21346912` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA21349081` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA21373613` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA21661693` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA21872312` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA21973372` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA22074252` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA22173693` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA22455611` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA22674311` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA22761838` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA22872829` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.BonusREBOTICA23160521` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.CarteraPedEsp` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.ChgDescripcion` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.ChgPmc` | `idProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.ChgPuc` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.ChgPvl` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.clineaPedproveerangofamilias` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.clineaproveeRangoFamilias` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.DesabasInfo` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.EncargoRecep` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.FLote` | `IDPROVEEDOR` | `char` | No | No |
| `IdProveedor` | `dbo.HistoEnvio` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.LineaDevolucion` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.LineaFacturaCompra` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.LineaVentaProveedor` | `idProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.ProgCarteraEnviado` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.ProgCarteraPedido` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.ProgEnvioEnviado` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.ProgEnvioPedido` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.TmpDesabas_MOSTRADOR` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.TmpDesabas_PUIGPC` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.TmpDesabas_REBOTICA2` | `IdProveedor` | `char` | No | No |
| `IdProveedor` | `dbo.TmpDesabas_SERVERIOF` | `IdProveedor` | `char` | No | No |
| `ImportePAlb` | `dbo.AlbaranFamilia` | `ImportePAlb` | `float` | No | No |
| `ImportePUC` | `dbo.AlbaranFamilia` | `ImportePUC` | `float` | No | No |
| `ImportePUC` | `dbo.AlbaranFamiliaIVA` | `ImportePUC` | `float` | No | No |
| `ImportePUC` | `dbo.LineaAlbaran` | `ImportePuc` | `float` | No | No |
| `ImportePUC` | `dbo.LINEARECEP` | `ImportePuc` | `float` | No | No |
| `ImportePUC` | `dbo.Pedido` | `ImportePuc` | `float` | No | No |
| `ImportePUC` | `dbo.PedidoCISMED` | `ImportePuc` | `float` | No | No |
| `ImportePUC` | `dbo.PP_Pedido` | `ImportePuc` | `float` | No | No |
| `ImportePVer` | `dbo.AlbaranFamilia` | `ImportePVer` | `float` | No | No |
| `ImportePVP` | `dbo.AlbaranFamilia` | `ImportePVP` | `float` | No | No |
| `ImportePVP` | `dbo.LineaAlbaran` | `ImportePvp` | `float` | No | No |
| `ImportePVP` | `dbo.LINEARECEP` | `ImportePvp` | `float` | No | No |
| `ImportePVP` | `dbo.Pedido` | `ImportePvp` | `float` | No | No |
| `ImportePVP` | `dbo.PedidoCISMED` | `ImportePvp` | `float` | No | No |
| `ImportePVP` | `dbo.PP_Pedido` | `ImportePvp` | `float` | No | No |
| `Tipo` | `dbo.AportacionDietoCatalunya` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.AportacionNoREPrivada` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.CajaMon` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.CajaMonTxt` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.CARTERAS` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Categoria` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.CM_Filtro` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.CM_LineaFiltro` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.CopiaAportaciones_REGIMEN_RE_CAT` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.CopiaNuevasAportaciones` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.CProvee` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.DividiblePlazos` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Encargo` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.EncargoLibroRecetaFM` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Estup` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.ESTUP_CantidadTraducida` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Estup_MOSTRADOR` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Estup_MOSTRADOR3` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Estup_PORTATIL` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Estup_REBOTICA2` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Estup_REBOTICA4` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Estup_SERVERIOF` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.FacturaRectificativaCredito` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Grupoiva` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.HistoEncargoLibroRecetaFM` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.HistoEstup` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.HistoLibroOrtopedia` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.HistoLibroReceta` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.HistoLibroRecetaVet` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.ImplicitaExcluye` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Iteminci` | `TIPO` | `char` | No | No |
| `Tipo` | `dbo.Laboratorio` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroOrtopedia` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroOrtopediaOff` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroReceta` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroReceta_MOSTRADOR` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroReceta_MOSTRADOR3` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroReceta_REBOTICA2` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroReceta_REBOTICA4` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroReceta_SERVERIOF` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroRecetaElecDilig` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroRecetaOFF` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroRecetaVet` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LibroRecetaVetOff` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LineaOfertaDescuento` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LineaVentaCruzada` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LineaVentaOfertaDto` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LineaVentaRectificativa` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.LR` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.MKT_EjeHorizontal` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.MKT_EjeVertical` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.MKT_Elemento` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.NuevaAportacionOrtopediaCatalunya` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.NuevasAportacionesMutuasCatalunya` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.OfertaValeAux` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.PlanIteminci` | `TIPO` | `char` | No | No |
| `Tipo` | `dbo.PromoVale` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.PromoValeAux` | `Tipo` | `char` | No | No |
| `Tipo` | `dbo.Vendedor` | `TIPO` | `char` | No | No |
| `Tipo` | `dbo.VentaTarjetaDto` | `Tipo` | `char` | No | No |

## Objetos que dependen de la tabla

- `dbo.SP_CalculoImportePAlb` — SQL_STORED_PROCEDURE
- `dbo.SP_CancelacionDevolucion` — SQL_STORED_PROCEDURE
- `dbo.sp_ImportaPharmaPlus_TraspasarAlbCompra` — SQL_STORED_PROCEDURE
- `dbo.sp_ImportaPharmaPlus_TraspasarProveedores` — SQL_STORED_PROCEDURE
- `dbo.vAlbaran` — VIEW
- `dbo.vLineaAlbaranExt` — VIEW
- `dbo.VRastroArticuloMOSTRADOR` — VIEW
- `dbo.VRastroArticuloMOSTRADOR2` — VIEW
- `dbo.VRastroArticuloMOSTRADOR3` — VIEW
- `dbo.VRastroArticuloPEDIDOS` — VIEW
- `dbo.VRastroArticuloPORTATIL` — VIEW
- `dbo.VRastroArticuloREBOTICA2` — VIEW
- `dbo.VRastroArticuloREBOTICA4` — VIEW
- `dbo.VRastroArticuloREBOTICAR` — VIEW
- `dbo.VRastroArticuloSERVERIOF` — VIEW

## Validación funcional

Pendiente de completar manualmente en:

`docs/tablas/albaran.md`

Aspectos que deben validarse:

- Significado funcional de cada columna importante.
- Valores posibles de estados y tipos.
- Relaciones reales utilizadas por Farmatic.
- Casos especiales y excepciones.
- Utilidad para ControlFarmacias.
