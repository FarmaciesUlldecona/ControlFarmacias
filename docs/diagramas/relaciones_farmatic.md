# Mapa global de relaciones de Farmatic

> Documento generado automáticamente.
> Las relaciones probables deben validarse manualmente.

Fecha de generación: 2026-07-24 19:59:46

## Diagrama de relaciones oficiales

```mermaid
flowchart LR
    dbo_AcoEstadillo["dbo.AcoEstadillo"] -->|"XAcoE_IdAportacion → IdAportacion"| dbo_Aportacion["dbo.Aportacion"]
    dbo_AcoEstadillo["dbo.AcoEstadillo"] -->|"IdEntrega → IdEntrega | IdNumDoc → IdNumDoc | IdNumVar → IdNumVar | IdEstadillo → IdEstadillo"| dbo_VarEstadillo["dbo.VarEstadillo"]
    dbo_AcoEstadilloAux["dbo.AcoEstadilloAux"] -->|"IdEntrega → IdEntrega | IdNumDoc → IdNumDoc | IdNumVar → IdNumVar | IdNumApor → IdNumApor | IdEstadillo → IdEstadillo"| dbo_AcoEstadillo["dbo.AcoEstadillo"]
    dbo_AdjuntoEmail["dbo.AdjuntoEmail"] -->|"fk_PlantillaEma_1 → fk_TrabajoAlert_1 | fk_PlantillaEma_2 → Ordinal"| dbo_PlantillaEmail["dbo.PlantillaEmail"]
    dbo_Agenda_Cita["dbo.Agenda_Cita"] -->|"OIDAgenda → OID"| dbo_Agenda_Agenda["dbo.Agenda_Agenda"]
    dbo_Agenda_Cita["dbo.Agenda_Cita"] -->|"OIDCitaParent → OID"| dbo_Agenda_Cita["dbo.Agenda_Cita"]
    dbo_Agenda_Cita["dbo.Agenda_Cita"] -->|"OIDCitaPattern → OID"| dbo_Agenda_Cita["dbo.Agenda_Cita"]
    dbo_Agenda_Cita["dbo.Agenda_Cita"] -->|"OIDTipoCita → OID"| dbo_Agenda_TipoCita["dbo.Agenda_TipoCita"]
    dbo_Agenda_Cita["dbo.Agenda_Cita"] -->|"OIDUsuario_Creador → OID"| dbo_Agenda_Usuario["dbo.Agenda_Usuario"]
    dbo_Agenda_Cita["dbo.Agenda_Cita"] -->|"OIDUsuario_UltMod → OID"| dbo_Agenda_Usuario["dbo.Agenda_Usuario"]
    dbo_Agenda_Proteccion["dbo.Agenda_Proteccion"] -->|"OIDAgenda → OID"| dbo_Agenda_Agenda["dbo.Agenda_Agenda"]
    dbo_Agenda_TipoCita["dbo.Agenda_TipoCita"] -->|"OIDIcono → OID"| dbo_Agenda_Icono["dbo.Agenda_Icono"]
    dbo_Agenda_TM_AgendasTipoCita["dbo.Agenda_TM_AgendasTipoCita"] -->|"OIDAgenda → OID"| dbo_Agenda_Agenda["dbo.Agenda_Agenda"]
    dbo_Agenda_TM_AgendasTipoCita["dbo.Agenda_TM_AgendasTipoCita"] -->|"OIDTipoCita → OID"| dbo_Agenda_TipoCita["dbo.Agenda_TipoCita"]
    dbo_Agenda_TM_PropietariosAgenda["dbo.Agenda_TM_PropietariosAgenda"] -->|"OIDAgenda → OID"| dbo_Agenda_Agenda["dbo.Agenda_Agenda"]
    dbo_Agenda_TM_PropietariosAgenda["dbo.Agenda_TM_PropietariosAgenda"] -->|"OIDUsuario → OID"| dbo_Agenda_Usuario["dbo.Agenda_Usuario"]
    dbo_Agenda_TM_PropietariosTipoCita["dbo.Agenda_TM_PropietariosTipoCita"] -->|"OIDTipoCita → OID"| dbo_Agenda_TipoCita["dbo.Agenda_TipoCita"]
    dbo_Agenda_TM_PropietariosTipoCita["dbo.Agenda_TM_PropietariosTipoCita"] -->|"OIDUsuario → OID"| dbo_Agenda_Usuario["dbo.Agenda_Usuario"]
    dbo_Agenda_TM_TiposCitaProteccion["dbo.Agenda_TM_TiposCitaProteccion"] -->|"OIDProteccion → OID"| dbo_Agenda_Proteccion["dbo.Agenda_Proteccion"]
    dbo_Agenda_TM_TiposCitaProteccion["dbo.Agenda_TM_TiposCitaProteccion"] -->|"OIDTipoCita → OID"| dbo_Agenda_TipoCita["dbo.Agenda_TipoCita"]
    dbo_Agenda_TM_UsuariosProteccion["dbo.Agenda_TM_UsuariosProteccion"] -->|"OIDProteccion → OID"| dbo_Agenda_Proteccion["dbo.Agenda_Proteccion"]
    dbo_Agenda_TM_UsuariosProteccion["dbo.Agenda_TM_UsuariosProteccion"] -->|"OIDUsuario → OID"| dbo_Agenda_Usuario["dbo.Agenda_Usuario"]
    dbo_Albaran["dbo.Albaran"] -->|"IdProveedor → IDPROVEEDOR"| dbo_Proveedor["dbo.Proveedor"]
    dbo_AlbaranFamilia["dbo.AlbaranFamilia"] -->|"IdProveedor → IDPROVEEDOR"| dbo_Proveedor["dbo.Proveedor"]
    dbo_AlbaranRecep["dbo.AlbaranRecep"] -->|"IdProveedor → IdProveedor | IdAlbaran → IdAlbaran"| dbo_Albaran["dbo.Albaran"]
    dbo_AlbaranRecep["dbo.AlbaranRecep"] -->|"IdRecepcion → IdRecepcion"| dbo_Recep["dbo.Recep"]
    dbo_Alliance360ArticuPed["dbo.Alliance360ArticuPed"] -->|"IdPedido → IdPedido"| dbo_Alliance360Pedidos["dbo.Alliance360Pedidos"]
    dbo_Aportacion["dbo.Aportacion"] -->|"XCuen_IdCuenta → IDCUENTA"| dbo_CUENTA["dbo.CUENTA"]
    dbo_Aportacion["dbo.Aportacion"] -->|"XGApo_IdGrupoAportacion → IdGrupoAportacion"| dbo_GrupoAportacion["dbo.GrupoAportacion"]
    dbo_AportacionAux["dbo.AportacionAux"] -->|"IdAportacion → IdAportacion"| dbo_Aportacion["dbo.Aportacion"]
    dbo_Apunte["dbo.Apunte"] -->|"Ejercicio → Ejercicio | Empresa → Empresa | IdAsiento → IdAsiento"| dbo_Asiento["dbo.Asiento"]
    dbo_ApunteAux["dbo.ApunteAux"] -->|"IdCuenta → IdCuenta | Fecha → Fecha | IdAsiento → IdAsiento | Orden → Orden"| dbo_Apunte["dbo.Apunte"]
    dbo_APUNTEPARAM["dbo.APUNTEPARAM"] -->|"XEsqu_IDEsquema → IDEsquema"| dbo_ESQUEMA["dbo.ESQUEMA"]
    dbo_ApunteParamAux["dbo.ApunteParamAux"] -->|"XEsqu_IDEsquema → XEsqu_IDEsquema | IDApunteParam → IDApunteParam"| dbo_APUNTEPARAM["dbo.APUNTEPARAM"]
    dbo_Articu["dbo.Articu"] -->|"XFam_IdFamilia → IdFamilia"| dbo_Familia["dbo.Familia"]
    dbo_Articu["dbo.Articu"] -->|"XGrup_IdGrupoIva → IdGrupoIva"| dbo_Grupoiva["dbo.Grupoiva"]
    dbo_ArticuAux["dbo.ArticuAux"] -->|"CodigoArt → IdArticu"| dbo_Articu["dbo.Articu"]
    dbo_ArticuCanjeable["dbo.ArticuCanjeable"] -->|"IdArticu → IdArticu"| dbo_Articu["dbo.Articu"]
    dbo_ArticuCat["dbo.ArticuCat"] -->|"IdCategoria → IdCategoria"| dbo_Categoria["dbo.Categoria"]
    dbo_BExterna["dbo.BExterna"] -->|"XProv_IdProveedor → IDPROVEEDOR"| dbo_Proveedor["dbo.Proveedor"]
    dbo_BExternaCalcPvp["dbo.BExternaCalcPvp"] -->|"XProv_IdProveedor → XProv_IdProveedor | IdBase → IdBase"| dbo_BExternaFtp["dbo.BExternaFtp"]
    dbo_BExternaDto["dbo.BExternaDto"] -->|"XProv_IdProveedor → XProv_IdProveedor | XBExt_IdBase → IdBase"| dbo_BExterna["dbo.BExterna"]
    dbo_BExternaExt["dbo.BExternaExt"] -->|"XProv_IdProv → XProv_IdProveedor | XBExt_IdBase → IdBase"| dbo_BExterna["dbo.BExterna"]
    dbo_Bloque["dbo.Bloque"] -->|"XApor_IdAportacion → IdAportacion"| dbo_Aportacion["dbo.Aportacion"]
    dbo_BloqueEnviado["dbo.BloqueEnviado"] -->|"IdAportacion → XApor_IdAportacion | IdNumeroBloque → IdNumeroBloque | IdNumeroReceta → IdNumeroReceta"| dbo_Bloque["dbo.Bloque"]
    dbo_BloqueExt["dbo.BloqueExt"] -->|"IdAportacion → IdAportacion"| dbo_Aportacion["dbo.Aportacion"]
    dbo_BloquePrescripcion["dbo.BloquePrescripcion"] -->|"IdAportacion → IdAportacion"| dbo_Aportacion["dbo.Aportacion"]
    dbo_BloqueRE["dbo.BloqueRE"] -->|"IdAportacion → IdAportacion"| dbo_Aportacion["dbo.Aportacion"]
    dbo_Bonus["dbo.Bonus"] -->|"IdProveedor → IDPROVEEDOR"| dbo_Proveedor["dbo.Proveedor"]
    dbo_BonusExt["dbo.BonusExt"] -->|"XArt_IdArticu → IdArticu | XProv_IdProveedor → IdProveedor | XBExt_IdBase_PK → XBExt_IdBase_PK"| dbo_Bonus["dbo.Bonus"]
    dbo_CajaMon["dbo.CajaMon"] -->|"XVend_IdVendedor → IDVENDEDOR"| dbo_Vendedor["dbo.Vendedor"]
    dbo_CampoCombinacion["dbo.CampoCombinacion"] -->|"fk_Entorno_1 → Codigo"| dbo_Entorno["dbo.Entorno"]
    dbo_Cliente["dbo.Cliente"] -->|"XCUEN_IDCUENTA → IDCUENTA"| dbo_CUENTA["dbo.CUENTA"]
    dbo_ClienteCat["dbo.ClienteCat"] -->|"IdCategoria → IdCategoria"| dbo_Categoria["dbo.Categoria"]
    dbo_CM_EstimacionIndicador["dbo.CM_EstimacionIndicador"] -->|"IdCuadroMando → IdCuadroMando"| dbo_CM_CuadroMando["dbo.CM_CuadroMando"]
    dbo_CM_EstimacionValorMeta["dbo.CM_EstimacionValorMeta"] -->|"IdCuadroMando → IdCuadroMando"| dbo_CM_CuadroMando["dbo.CM_CuadroMando"]
    dbo_CM_Indicador["dbo.CM_Indicador"] -->|"IdCuadroMando → IdCuadroMando"| dbo_CM_CuadroMando["dbo.CM_CuadroMando"]
    dbo_CM_LineaFiltro["dbo.CM_LineaFiltro"] -->|"IdFiltro → IdFiltro"| dbo_CM_Filtro["dbo.CM_Filtro"]
    dbo_CM_PrevisionIndicador["dbo.CM_PrevisionIndicador"] -->|"IdCuadroMando → IdCuadroMando"| dbo_CM_CuadroMando["dbo.CM_CuadroMando"]
    dbo_CM_ValorMeta["dbo.CM_ValorMeta"] -->|"IdCuadroMando → IdCuadroMando"| dbo_CM_CuadroMando["dbo.CM_CuadroMando"]
    dbo_CM_ValorMeta["dbo.CM_ValorMeta"] -->|"IdIndicador → IdIndicador"| dbo_CM_Indicador["dbo.CM_Indicador"]
    dbo_CompraLibroIva["dbo.CompraLibroIva"] -->|"EjercicioAs → Ejercicio | EmpresaAs → Empresa | IdAsiento → IdAsiento"| dbo_Asiento["dbo.Asiento"]
    dbo_CompraLibroIva["dbo.CompraLibroIva"] -->|"IdTipoFac → IdTipo | IdFechaFac → IdFecha | IdDocumentoFac → IdDocumento | IdContadorFac → IdContador"| dbo_Factura["dbo.Factura"]
    dbo_CompraLibroIvaTipos["dbo.CompraLibroIvaTipos"] -->|"IdOrden → IdOrden | Ejercicio → Ejercicio"| dbo_CompraLibroIva["dbo.CompraLibroIva"]
    dbo_CondicionAlerta["dbo.CondicionAlerta"] -->|"fk_TrabajoAlert_1 → Codigo"| dbo_TrabajoAlertas["dbo.TrabajoAlertas"]
    dbo_DesabasCISMED["dbo.DesabasCISMED"] -->|"IdMov → IdMov"| dbo_DesabasInfo["dbo.DesabasInfo"]
    dbo_DesabasInfoAux["dbo.DesabasInfoAux"] -->|"IdMov → IdMov"| dbo_DesabasInfo["dbo.DesabasInfo"]
    dbo_DesabasInfoAux["dbo.DesabasInfoAux"] -->|"IdVendedor → IDVENDEDOR"| dbo_Vendedor["dbo.Vendedor"]
    dbo_Destinatario["dbo.Destinatario"] -->|"fk_Cliente_1 → IDCLIENTE"| dbo_Cliente["dbo.Cliente"]
    dbo_Destinatario["dbo.Destinatario"] -->|"fk_Paciente_1 → IDPACIENTE"| dbo_FPACIENTE["dbo.FPACIENTE"]
    dbo_Destinatario["dbo.Destinatario"] -->|"fk_TipoDestinat_1 → Codigo"| dbo_TipoDestinatario["dbo.TipoDestinatario"]
    dbo_Destinatario["dbo.Destinatario"] -->|"fk_Vendedor_1 → IDVENDEDOR"| dbo_Vendedor["dbo.Vendedor"]
    dbo_DetConfiguracion["dbo.DetConfiguracion"] -->|"IdFormulario → IdFormulario | IdFormContador → IdFormContador"| dbo_Configuracion["dbo.Configuracion"]
    dbo_DividiblePlazos["dbo.DividiblePlazos"] -->|"fk_Factura_1 → IdTipo | fk_Factura_2 → IdFecha | fk_Factura_3 → IdDocumento | fk_Factura_4 → IdContador"| dbo_Factura["dbo.Factura"]
    dbo_DividiblePlazos["dbo.DividiblePlazos"] -->|"fk_FormaPago_1 → Codigo"| dbo_FormaPago["dbo.FormaPago"]
    dbo_DocEntrega["dbo.DocEntrega"] -->|"XDocE_IdEntrega → IdEntrega | XDocE_IdNumDoc → IdNumDoc | XDocE_IdEstadillo → IdEstadillo"| dbo_DocEntrega["dbo.DocEntrega"]
    dbo_DocEntrega["dbo.DocEntrega"] -->|"IdEntrega → IdEntrega | IdEstadillo → IdEstadillo"| dbo_Entrega["dbo.Entrega"]
    dbo_EMail_Envio["dbo.EMail_Envio"] -->|"fk_EMail_Message → OID"| dbo_EMail_Message["dbo.EMail_Message"]
    dbo_EncargoContacto["dbo.EncargoContacto"] -->|"IdEncargo → IdContador"| dbo_Encargo["dbo.Encargo"]
    dbo_EncargoFormulaReceta["dbo.EncargoFormulaReceta"] -->|"IdFormula → IdEncargo"| dbo_EncargoLibroRecetaFM["dbo.EncargoLibroRecetaFM"]
    dbo_EnlaceEstadillo["dbo.EnlaceEstadillo"] -->|"IdEntrega → IdEntrega | IdNumDoc → IdNumDoc | IdEstadillo → IdEstadillo"| dbo_DocEntrega["dbo.DocEntrega"]
    dbo_EnlaceEstadillo["dbo.EnlaceEstadillo"] -->|"IdEntrega → IdEntrega | IdNumDoc → IdNumDoc | XEnla_IdNumVar → IdNumVar | IdEstadillo → IdEstadillo"| dbo_VarEstadillo["dbo.VarEstadillo"]
    dbo_EnlaceEti["dbo.EnlaceEti"] -->|"IdEtiqueta → IdCodigo"| dbo_EtiFormula["dbo.EtiFormula"]
    dbo_Entorno["dbo.Entorno"] -->|"fk_EntornoPadre_1 → Codigo"| dbo_Entorno["dbo.Entorno"]
    dbo_EsquemaAux["dbo.EsquemaAux"] -->|"IDEsquema → IDEsquema"| dbo_ESQUEMA["dbo.ESQUEMA"]
    dbo_EsquemaIva["dbo.EsquemaIva"] -->|"XEsqu_IDEsquema → IDEsquema"| dbo_ESQUEMA["dbo.ESQUEMA"]
    dbo_EstaDec["dbo.EstaDec"] -->|"IdArticu → IdArticu"| dbo_Articu["dbo.Articu"]
    dbo_Estarti["dbo.Estarti"] -->|"IdArticu → IdArticu"| dbo_Articu["dbo.Articu"]
    dbo_EstartiLote["dbo.EstartiLote"] -->|"IdArticu → IdArticu"| dbo_Articu["dbo.Articu"]
    dbo_ExMinCond["dbo.ExMinCond"] -->|"IdExMin → IdExMin"| dbo_ExMin["dbo.ExMin"]
    dbo_ExMinCondLinea["dbo.ExMinCondLinea"] -->|"IdExMin → IdExMin | IdCond → IdCond"| dbo_ExMinCond["dbo.ExMinCond"]
    dbo_ExMinHistoLinea["dbo.ExMinHistoLinea"] -->|"IdExMinHisto → IdExMinHisto"| dbo_ExMinHisto["dbo.ExMinHisto"]
    dbo_Familia["dbo.Familia"] -->|"XGrup_IdGrupoIva → IdGrupoIva"| dbo_Grupoiva["dbo.Grupoiva"]
    dbo_FamiliaAux["dbo.FamiliaAux"] -->|"IdSuperFamilia → IdSuperFamilia"| dbo_SuperFamilia["dbo.SuperFamilia"]
    dbo_FFORMUCOMPON["dbo.FFORMUCOMPON"] -->|"IDARTICU → IDARTICU"| dbo_FCOMPONENTE["dbo.FCOMPONENTE"]
    dbo_Fformula["dbo.Fformula"] -->|"XENVA_IDENVASE → IDARTICU"| dbo_FCOMPONENTE["dbo.FCOMPONENTE"]
    dbo_Fformula["dbo.Fformula"] -->|"XETI_IDCODIGO → IdCodigo"| dbo_EtiFormula["dbo.EtiFormula"]
    dbo_Fformula["dbo.Fformula"] -->|"XHONO_IDHONORARIO → IDHONORARIO"| dbo_FHONORARIO["dbo.FHONORARIO"]
    dbo_Fformula["dbo.Fformula"] -->|"XPACI_IDPACIENTE → IDPACIENTE"| dbo_FPACIENTE["dbo.FPACIENTE"]
    dbo_FLINEAHONO["dbo.FLINEAHONO"] -->|"IDHONORARIO → IDHONORARIO"| dbo_FHONORARIO["dbo.FHONORARIO"]
    dbo_FormulaReceta["dbo.FormulaReceta"] -->|"IdFormula → IdLibro"| dbo_LibroReceta["dbo.LibroReceta"]
    dbo_FormulaRecetaVet["dbo.FormulaRecetaVet"] -->|"IdFormula → IdLibro"| dbo_LibroRecetaVet["dbo.LibroRecetaVet"]
    dbo_Ftexto["dbo.Ftexto"] -->|"IDFORMULA → IDFORMULA"| dbo_Fformula["dbo.Fformula"]
    dbo_GeneActi["dbo.GeneActi"] -->|"IdGrupoGen → IdGrupoGen"| dbo_GrupoGenerico["dbo.GrupoGenerico"]
    dbo_GeneApor["dbo.GeneApor"] -->|"IdAportacion → IdAportacion"| dbo_Aportacion["dbo.Aportacion"]
    dbo_GeneArti["dbo.GeneArti"] -->|"IdGrupoGen → IdGrupoGen"| dbo_GrupoGenerico["dbo.GrupoGenerico"]
    dbo_GrupoCuenta["dbo.GrupoCuenta"] -->|"XGrup_IdGrupo → IdGrupo"| dbo_Grupo["dbo.Grupo"]
    dbo_GrupoFamilia["dbo.GrupoFamilia"] -->|"Xfami_idFamilia → IdFamilia"| dbo_Familia["dbo.Familia"]
    dbo_HistoEncargoFormulaReceta["dbo.HistoEncargoFormulaReceta"] -->|"IdFormula → IdEncargo"| dbo_HistoEncargoLibroRecetaFM["dbo.HistoEncargoLibroRecetaFM"]
    dbo_HistoFormulaReceta["dbo.HistoFormulaReceta"] -->|"IdFormula → IdLibro | Fecha → Fecha"| dbo_HistoLibroReceta["dbo.HistoLibroReceta"]
    dbo_HistoFormulaRecetaVet["dbo.HistoFormulaRecetaVet"] -->|"IdFormula → IdLibro | Fecha → Fecha"| dbo_HistoLibroRecetaVet["dbo.HistoLibroRecetaVet"]
    dbo_HistoricoAlertas["dbo.HistoricoAlertas"] -->|"fk_LogAlertas_1 → Numero"| dbo_LogAlertas["dbo.LogAlertas"]
    dbo_HorarioEnvio["dbo.HorarioEnvio"] -->|"fk_Entorno_1 → Codigo"| dbo_Entorno["dbo.Entorno"]
    dbo_Impor["dbo.Impor"] -->|"XProv_IdProveedor → XProv_IdProveedor | IdBase → IdBase"| dbo_BExterna["dbo.BExterna"]
    dbo_InferidaCliente["dbo.InferidaCliente"] -->|"IdCatInferida → IdCatInferida | IdLinea → IdLinea"| dbo_InferidaItem["dbo.InferidaItem"]
    dbo_InferidaCliente["dbo.InferidaCliente"] -->|"IdCliente → IDCLIENTE"| dbo_Cliente["dbo.Cliente"]
    dbo_InferidaItem["dbo.InferidaItem"] -->|"IdCatInferida → IdCatInferida"| dbo_CatInferida["dbo.CatInferida"]
    dbo_InferidaItemPerfil["dbo.InferidaItemPerfil"] -->|"IdPerfil → IdPerfil"| dbo_InferidaPerfil["dbo.InferidaPerfil"]
    dbo_InferidaItemPerfil["dbo.InferidaItemPerfil"] -->|"IdCatInferida → IdCatInferida | IdLinea → IdLinea"| dbo_InferidaItem["dbo.InferidaItem"]
    dbo_InferidaVenta["dbo.InferidaVenta"] -->|"IdVenta → IdVenta"| dbo_Venta["dbo.Venta"]
    dbo_InferidaVenta["dbo.InferidaVenta"] -->|"IdCatInferida → IdCatInferida | IdLinea → IdLinea"| dbo_InferidaItem["dbo.InferidaItem"]
    dbo_Informe["dbo.Informe"] -->|"XGrup_IdGrupo → IdGrupo"| dbo_Grupo["dbo.Grupo"]
    dbo_InventaDetalle["dbo.InventaDetalle"] -->|"IdInventario → IdInventario"| dbo_InventaMaestro["dbo.InventaMaestro"]
    dbo_ItemListaArticu["dbo.ItemListaArticu"] -->|"XItem_IdLista → IdLista"| dbo_ListaArticu["dbo.ListaArticu"]
    dbo_ItemListaCliente["dbo.ItemListaCliente"] -->|"XItem_IdCliente → IDCLIENTE"| dbo_Cliente["dbo.Cliente"]
    dbo_ItemListaCliente["dbo.ItemListaCliente"] -->|"XItem_IdLista → IdLista"| dbo_ListaCliente["dbo.ListaCliente"]
    dbo_LibroIva["dbo.LibroIva"] -->|"EjercicioAs → Ejercicio | EmpresaAs → Empresa | IdAsiento → IdAsiento"| dbo_Asiento["dbo.Asiento"]
    dbo_LibroIva["dbo.LibroIva"] -->|"IdTipoFac → IdTipo | IdFechaFac → IdFecha | IdDocumentoFac → IdDocumento | IdContadorFac → IdContador"| dbo_Factura["dbo.Factura"]
    dbo_LibroIvaTipos["dbo.LibroIvaTipos"] -->|"IdOrden → IdOrden | Ejercicio → Ejercicio"| dbo_LibroIva["dbo.LibroIva"]
    dbo_LineaDevolucion["dbo.LineaDevolucion"] -->|"IdProveedor → IDPROVEEDOR"| dbo_Proveedor["dbo.Proveedor"]
    dbo_LineaFacturaCompra["dbo.LineaFacturaCompra"] -->|"IdProveedor → IdProveedor | IdAlbaran → IdAlbaran"| dbo_Albaran["dbo.Albaran"]
    dbo_LineaFacturaCompra["dbo.LineaFacturaCompra"] -->|"IdTipo → IdTipo | IdFecha → IdFecha | IdDocumento → IdDocumento | IdContador → IdContador"| dbo_Factura["dbo.Factura"]
    dbo_LineaFranjaOfer["dbo.LineaFranjaOfer"] -->|"IdFranja → IdFranja"| dbo_FranjaOferta["dbo.FranjaOferta"]
    dbo_LINEAINCI["dbo.LINEAINCI"] -->|"XPROT_IDRECEPCION → IDRECEPCION"| dbo_PROTRECEPCION["dbo.PROTRECEPCION"]
    dbo_LineaLote["dbo.LineaLote"] -->|"IdLote → IdLote"| dbo_Lote["dbo.Lote"]
    dbo_LineaOferta["dbo.LineaOferta"] -->|"IdOferta → IdOferta"| dbo_Oferta["dbo.Oferta"]
    dbo_LineaOfertaDescuento["dbo.LineaOfertaDescuento"] -->|"IdOferta → IdOferta | IdLinea → IdLinea"| dbo_LineaOferta["dbo.LineaOferta"]
    dbo_LineaOfertaDescuentoAux["dbo.LineaOfertaDescuentoAux"] -->|"IdOferta → IdOferta | IdLinea → IdLinea"| dbo_LineaOferta["dbo.LineaOferta"]
    dbo_LineaPedido["dbo.LineaPedido"] -->|"IdPedido → IdPedido"| dbo_Pedido["dbo.Pedido"]
    dbo_LineaPedidoCISMED["dbo.LineaPedidoCISMED"] -->|"IdPedido → IdPedido"| dbo_PedidoCISMED["dbo.PedidoCISMED"]
    dbo_LineaPedidoGrupo["dbo.LineaPedidoGrupo"] -->|"IdTipo → IdTipo | IdPedido → IdPedido"| dbo_PedidoGrupo["dbo.PedidoGrupo"]
    dbo_LINEARECEP["dbo.LINEARECEP"] -->|"IdRecepcion → IdRecepcion"| dbo_Recep["dbo.Recep"]
    dbo_LineaRecepGrupo["dbo.LineaRecepGrupo"] -->|"IdRecepcion → IdRecepcion"| dbo_RecepGrupo["dbo.RecepGrupo"]
    dbo_LineaVenta["dbo.LineaVenta"] -->|"IdVenta → IdVenta"| dbo_Venta["dbo.Venta"]
    dbo_LineaVentaVirtual["dbo.LineaVentaVirtual"] -->|"IdVenta → IdVenta"| dbo_Venta["dbo.Venta"]
    dbo_LinPedir["dbo.LinPedir"] -->|"XLPD_IdPedido → IdPedido | XLPD_IdLinea → IdLinea"| dbo_LineaPedido["dbo.LineaPedido"]
    dbo_LogAlertas["dbo.LogAlertas"] -->|"fk_TrabajoAlert_1 → Codigo"| dbo_TrabajoAlertas["dbo.TrabajoAlertas"]
    dbo_LoteAux["dbo.LoteAux"] -->|"IdLote → IdLote"| dbo_Lote["dbo.Lote"]
    dbo_MesgToHostDestin["dbo.MesgToHostDestin"] -->|"XMesg_IdMensaje → IdMensaje"| dbo_MesgVendedor["dbo.MesgVendedor"]
    dbo_MesgToHostGrupoHosts["dbo.MesgToHostGrupoHosts"] -->|"XMesg_IdGrupo → IdGrupo"| dbo_MesgToHostGrupo["dbo.MesgToHostGrupo"]
    dbo_MesgToVendedorGrupoVend["dbo.MesgToVendedorGrupoVend"] -->|"XMesg_IdGrupo → IdGrupo"| dbo_MesgToVendedorGrupo["dbo.MesgToVendedorGrupo"]
    dbo_MesgVendedorDestin["dbo.MesgVendedorDestin"] -->|"XMesg_IdMensaje → IdMensaje"| dbo_MesgVendedor["dbo.MesgVendedor"]
    dbo_MesgVendedorLinea["dbo.MesgVendedorLinea"] -->|"XMesg_IdMensaje → IdMensaje"| dbo_MesgVendedor["dbo.MesgVendedor"]
    dbo_MesgVendedorProg["dbo.MesgVendedorProg"] -->|"xMesg_IdMensaje → IdMensaje"| dbo_MesgVendedor["dbo.MesgVendedor"]
    dbo_MKT_Apartado["dbo.MKT_Apartado"] -->|"IdInforme → IdInforme"| dbo_MKT_Informe["dbo.MKT_Informe"]
    dbo_MKT_EjeHorizontal["dbo.MKT_EjeHorizontal"] -->|"IdInforme → IdInforme | IdApartado → IdApartado"| dbo_MKT_Apartado["dbo.MKT_Apartado"]
    dbo_MKT_EjeVertical["dbo.MKT_EjeVertical"] -->|"IdInforme → IdInforme | IdApartado → IdApartado"| dbo_MKT_Apartado["dbo.MKT_Apartado"]
    dbo_Oferta["dbo.Oferta"] -->|"IdFranja → IdFranja"| dbo_FranjaOferta["dbo.FranjaOferta"]
    dbo_OfertaExists["dbo.OfertaExists"] -->|"IdOferta → IdOferta"| dbo_Oferta["dbo.Oferta"]
    dbo_OfertaValidez["dbo.OfertaValidez"] -->|"IdOferta → IdOferta"| dbo_Oferta["dbo.Oferta"]
    dbo_PAlbaran["dbo.PAlbaran"] -->|"XArt_IdArticu → IdArticu"| dbo_Articu["dbo.Articu"]
    dbo_PAlbaran["dbo.PAlbaran"] -->|"XProv_IdProveedor → IDPROVEEDOR"| dbo_Proveedor["dbo.Proveedor"]
    dbo_Pedido["dbo.Pedido"] -->|"XProv_IdProveedor → IDPROVEEDOR"| dbo_Proveedor["dbo.Proveedor"]
    dbo_PedidoCISMED["dbo.PedidoCISMED"] -->|"XProv_IdProveedor → IDPROVEEDOR"| dbo_Proveedor["dbo.Proveedor"]
    dbo_PLANLINEAINCI["dbo.PLANLINEAINCI"] -->|"XPROT_IDRECEPCION → IDRECEPCION"| dbo_PLANTRECEPCION["dbo.PLANTRECEPCION"]
    dbo_PlantillaEmail["dbo.PlantillaEmail"] -->|"fk_TrabajoAlert_1 → Codigo"| dbo_TrabajoAlertas["dbo.TrabajoAlertas"]
    dbo_PLANTILLAPRO["dbo.PLANTILLAPRO"] -->|"XPARA_IDPARAMODEM → IDPARAMODEM"| dbo_PLANPARAMODEM["dbo.PLANPARAMODEM"]
    dbo_PlantillaSMS["dbo.PlantillaSMS"] -->|"fk_TrabajoAlert_1 → Codigo"| dbo_TrabajoAlertas["dbo.TrabajoAlertas"]
    dbo_PLANTRECEPCION["dbo.PLANTRECEPCION"] -->|"IDRECEPCION → IDPROTOCOLO"| dbo_PLANTILLAPRO["dbo.PLANTILLAPRO"]
    dbo_Plazo["dbo.Plazo"] -->|"fk_FormaPago_1 → Codigo"| dbo_FormaPago["dbo.FormaPago"]
    dbo_PROTOCOLO["dbo.PROTOCOLO"] -->|"XPARA_IDPARAMODEM → IDPARAMODEM"| dbo_PARAMODEM["dbo.PARAMODEM"]
    dbo_Proveedor["dbo.Proveedor"] -->|"XCUEN_IDCUENTA → IDCUENTA"| dbo_CUENTA["dbo.CUENTA"]
    dbo_Proveedor["dbo.Proveedor"] -->|"fk_FormaPago_1 → Codigo"| dbo_FormaPago["dbo.FormaPago"]
    dbo_ProveedorRepresentantes["dbo.ProveedorRepresentantes"] -->|"XProv_IdProveedor → IDPROVEEDOR"| dbo_Proveedor["dbo.Proveedor"]
    dbo_Recep["dbo.Recep"] -->|"XVend_IdVendedor → IDVENDEDOR"| dbo_Vendedor["dbo.Vendedor"]
    dbo_RecetaTSI["dbo.RecetaTSI"] -->|"XVent_IdVenta → IdVenta"| dbo_Venta["dbo.Venta"]
    dbo_RG_Acotacion["dbo.RG_Acotacion"] -->|"IdInforme → IdInforme | IdLinea → IdLinea"| dbo_RG_CamposInformes["dbo.RG_CamposInformes"]
    dbo_RG_CamposInformes["dbo.RG_CamposInformes"] -->|"IdInforme → idInforme"| dbo_RG_Informes["dbo.RG_Informes"]
    dbo_Tarifa["dbo.Tarifa"] -->|"IDTIPOCLIENTE → IDTIPOCLIENTE | IDTIPOFAMILIA → IDTIPOFAMILIA"| dbo_TIPOTARIFA["dbo.TIPOTARIFA"]
    dbo_TM_iosDestinatario["dbo.TM_iosDestinatario"] -->|"fk_CjtoDestinat_1 → Codigo"| dbo_CjtoDestinatarios["dbo.CjtoDestinatarios"]
    dbo_TM_iosDestinatario["dbo.TM_iosDestinatario"] -->|"fk_Destinatario_1 → Codigo"| dbo_Destinatario["dbo.Destinatario"]
    dbo_TM_nteListaCliente["dbo.TM_nteListaCliente"] -->|"fk_Cliente_1 → IDCLIENTE"| dbo_Cliente["dbo.Cliente"]
    dbo_TM_nteListaCliente["dbo.TM_nteListaCliente"] -->|"fk_ListaCliente_1 → IdLista"| dbo_ListaCliente["dbo.ListaCliente"]
    dbo_TM_sTrabajoAlertas["dbo.TM_sTrabajoAlertas"] -->|"fk_CjtoDestinat_1 → Codigo"| dbo_CjtoDestinatarios["dbo.CjtoDestinatarios"]
    dbo_TM_sTrabajoAlertas["dbo.TM_sTrabajoAlertas"] -->|"fk_TrabajoAlert_1 → Codigo"| dbo_TrabajoAlertas["dbo.TrabajoAlertas"]
    dbo_TM_toDestinatarios["dbo.TM_toDestinatarios"] -->|"fk_ListaCliente_1 → IdLista"| dbo_ListaCliente["dbo.ListaCliente"]
    dbo_TM_toDestinatarios["dbo.TM_toDestinatarios"] -->|"fk_CjtoDestinat_1 → Codigo"| dbo_CjtoDestinatarios["dbo.CjtoDestinatarios"]
    dbo_TrabajoAlertas["dbo.TrabajoAlertas"] -->|"fk_Entorno_1 → Codigo"| dbo_Entorno["dbo.Entorno"]
    dbo_VarEstadillo["dbo.VarEstadillo"] -->|"IdEntrega → IdEntrega | IdNumDoc → IdNumDoc | IdEstadillo → IdEstadillo"| dbo_DocEntrega["dbo.DocEntrega"]
    dbo_VariableCondicion["dbo.VariableCondicion"] -->|"fk_Entorno_1 → Codigo"| dbo_Entorno["dbo.Entorno"]
    dbo_Vencimiento["dbo.Vencimiento"] -->|"fk_DividiblePla_1 → Codigo"| dbo_DividiblePlazos["dbo.DividiblePlazos"]
    dbo_Vencimiento["dbo.Vencimiento"] -->|"fk_VencimientoO_1 → fk_DividiblePla_1 | fk_VencimientoO_2 → Numero"| dbo_Vencimiento["dbo.Vencimiento"]
    dbo_Venta["dbo.Venta"] -->|"XClie_IdCliente → IDCLIENTE"| dbo_Cliente["dbo.Cliente"]
    dbo_Venta["dbo.Venta"] -->|"XVend_IdVendedor → IDVENDEDOR"| dbo_Vendedor["dbo.Vendedor"]
    dbo_VentaAux["dbo.VentaAux"] -->|"IdVenta → IdVenta"| dbo_Venta["dbo.Venta"]
    dbo_VentaAuxChile["dbo.VentaAuxChile"] -->|"IdVenta → IdVenta"| dbo_Venta["dbo.Venta"]
```

## Relaciones oficiales

- `dbo.AcoEstadillo.XAcoE_IdAportacion` → `dbo.Aportacion.IdAportacion`
- `dbo.AcoEstadillo.IdEntrega` → `dbo.VarEstadillo.IdEntrega`
- `dbo.AcoEstadillo.IdNumDoc` → `dbo.VarEstadillo.IdNumDoc`
- `dbo.AcoEstadillo.IdNumVar` → `dbo.VarEstadillo.IdNumVar`
- `dbo.AcoEstadillo.IdEstadillo` → `dbo.VarEstadillo.IdEstadillo`
- `dbo.AcoEstadilloAux.IdEntrega` → `dbo.AcoEstadillo.IdEntrega`
- `dbo.AcoEstadilloAux.IdNumDoc` → `dbo.AcoEstadillo.IdNumDoc`
- `dbo.AcoEstadilloAux.IdNumVar` → `dbo.AcoEstadillo.IdNumVar`
- `dbo.AcoEstadilloAux.IdNumApor` → `dbo.AcoEstadillo.IdNumApor`
- `dbo.AcoEstadilloAux.IdEstadillo` → `dbo.AcoEstadillo.IdEstadillo`
- `dbo.AdjuntoEmail.fk_PlantillaEma_1` → `dbo.PlantillaEmail.fk_TrabajoAlert_1`
- `dbo.AdjuntoEmail.fk_PlantillaEma_2` → `dbo.PlantillaEmail.Ordinal`
- `dbo.Agenda_Cita.OIDAgenda` → `dbo.Agenda_Agenda.OID`
- `dbo.Agenda_Cita.OIDCitaParent` → `dbo.Agenda_Cita.OID`
- `dbo.Agenda_Cita.OIDCitaPattern` → `dbo.Agenda_Cita.OID`
- `dbo.Agenda_Cita.OIDTipoCita` → `dbo.Agenda_TipoCita.OID`
- `dbo.Agenda_Cita.OIDUsuario_Creador` → `dbo.Agenda_Usuario.OID`
- `dbo.Agenda_Cita.OIDUsuario_UltMod` → `dbo.Agenda_Usuario.OID`
- `dbo.Agenda_Proteccion.OIDAgenda` → `dbo.Agenda_Agenda.OID`
- `dbo.Agenda_TipoCita.OIDIcono` → `dbo.Agenda_Icono.OID`
- `dbo.Agenda_TM_AgendasTipoCita.OIDAgenda` → `dbo.Agenda_Agenda.OID`
- `dbo.Agenda_TM_AgendasTipoCita.OIDTipoCita` → `dbo.Agenda_TipoCita.OID`
- `dbo.Agenda_TM_PropietariosAgenda.OIDAgenda` → `dbo.Agenda_Agenda.OID`
- `dbo.Agenda_TM_PropietariosAgenda.OIDUsuario` → `dbo.Agenda_Usuario.OID`
- `dbo.Agenda_TM_PropietariosTipoCita.OIDTipoCita` → `dbo.Agenda_TipoCita.OID`
- `dbo.Agenda_TM_PropietariosTipoCita.OIDUsuario` → `dbo.Agenda_Usuario.OID`
- `dbo.Agenda_TM_TiposCitaProteccion.OIDProteccion` → `dbo.Agenda_Proteccion.OID`
- `dbo.Agenda_TM_TiposCitaProteccion.OIDTipoCita` → `dbo.Agenda_TipoCita.OID`
- `dbo.Agenda_TM_UsuariosProteccion.OIDProteccion` → `dbo.Agenda_Proteccion.OID`
- `dbo.Agenda_TM_UsuariosProteccion.OIDUsuario` → `dbo.Agenda_Usuario.OID`
- `dbo.Albaran.IdProveedor` → `dbo.Proveedor.IDPROVEEDOR`
- `dbo.AlbaranFamilia.IdProveedor` → `dbo.Proveedor.IDPROVEEDOR`
- `dbo.AlbaranRecep.IdProveedor` → `dbo.Albaran.IdProveedor`
- `dbo.AlbaranRecep.IdAlbaran` → `dbo.Albaran.IdAlbaran`
- `dbo.AlbaranRecep.IdRecepcion` → `dbo.Recep.IdRecepcion`
- `dbo.Alliance360ArticuPed.IdPedido` → `dbo.Alliance360Pedidos.IdPedido`
- `dbo.Aportacion.XCuen_IdCuenta` → `dbo.CUENTA.IDCUENTA`
- `dbo.Aportacion.XGApo_IdGrupoAportacion` → `dbo.GrupoAportacion.IdGrupoAportacion`
- `dbo.AportacionAux.IdAportacion` → `dbo.Aportacion.IdAportacion`
- `dbo.Apunte.Ejercicio` → `dbo.Asiento.Ejercicio`
- `dbo.Apunte.Empresa` → `dbo.Asiento.Empresa`
- `dbo.Apunte.IdAsiento` → `dbo.Asiento.IdAsiento`
- `dbo.ApunteAux.IdCuenta` → `dbo.Apunte.IdCuenta`
- `dbo.ApunteAux.Fecha` → `dbo.Apunte.Fecha`
- `dbo.ApunteAux.IdAsiento` → `dbo.Apunte.IdAsiento`
- `dbo.ApunteAux.Orden` → `dbo.Apunte.Orden`
- `dbo.APUNTEPARAM.XEsqu_IDEsquema` → `dbo.ESQUEMA.IDEsquema`
- `dbo.ApunteParamAux.XEsqu_IDEsquema` → `dbo.APUNTEPARAM.XEsqu_IDEsquema`
- `dbo.ApunteParamAux.IDApunteParam` → `dbo.APUNTEPARAM.IDApunteParam`
- `dbo.Articu.XFam_IdFamilia` → `dbo.Familia.IdFamilia`
- `dbo.Articu.XGrup_IdGrupoIva` → `dbo.Grupoiva.IdGrupoIva`
- `dbo.ArticuAux.CodigoArt` → `dbo.Articu.IdArticu`
- `dbo.ArticuCanjeable.IdArticu` → `dbo.Articu.IdArticu`
- `dbo.ArticuCat.IdCategoria` → `dbo.Categoria.IdCategoria`
- `dbo.BExterna.XProv_IdProveedor` → `dbo.Proveedor.IDPROVEEDOR`
- `dbo.BExternaCalcPvp.XProv_IdProveedor` → `dbo.BExternaFtp.XProv_IdProveedor`
- `dbo.BExternaCalcPvp.IdBase` → `dbo.BExternaFtp.IdBase`
- `dbo.BExternaDto.XProv_IdProveedor` → `dbo.BExterna.XProv_IdProveedor`
- `dbo.BExternaDto.XBExt_IdBase` → `dbo.BExterna.IdBase`
- `dbo.BExternaExt.XProv_IdProv` → `dbo.BExterna.XProv_IdProveedor`
- `dbo.BExternaExt.XBExt_IdBase` → `dbo.BExterna.IdBase`
- `dbo.Bloque.XApor_IdAportacion` → `dbo.Aportacion.IdAportacion`
- `dbo.BloqueEnviado.IdAportacion` → `dbo.Bloque.XApor_IdAportacion`
- `dbo.BloqueEnviado.IdNumeroBloque` → `dbo.Bloque.IdNumeroBloque`
- `dbo.BloqueEnviado.IdNumeroReceta` → `dbo.Bloque.IdNumeroReceta`
- `dbo.BloqueExt.IdAportacion` → `dbo.Aportacion.IdAportacion`
- `dbo.BloquePrescripcion.IdAportacion` → `dbo.Aportacion.IdAportacion`
- `dbo.BloqueRE.IdAportacion` → `dbo.Aportacion.IdAportacion`
- `dbo.Bonus.IdProveedor` → `dbo.Proveedor.IDPROVEEDOR`
- `dbo.BonusExt.XArt_IdArticu` → `dbo.Bonus.IdArticu`
- `dbo.BonusExt.XProv_IdProveedor` → `dbo.Bonus.IdProveedor`
- `dbo.BonusExt.XBExt_IdBase_PK` → `dbo.Bonus.XBExt_IdBase_PK`
- `dbo.CajaMon.XVend_IdVendedor` → `dbo.Vendedor.IDVENDEDOR`
- `dbo.CampoCombinacion.fk_Entorno_1` → `dbo.Entorno.Codigo`
- `dbo.Cliente.XCUEN_IDCUENTA` → `dbo.CUENTA.IDCUENTA`
- `dbo.ClienteCat.IdCategoria` → `dbo.Categoria.IdCategoria`
- `dbo.CM_EstimacionIndicador.IdCuadroMando` → `dbo.CM_CuadroMando.IdCuadroMando`
- `dbo.CM_EstimacionValorMeta.IdCuadroMando` → `dbo.CM_CuadroMando.IdCuadroMando`
- `dbo.CM_Indicador.IdCuadroMando` → `dbo.CM_CuadroMando.IdCuadroMando`
- `dbo.CM_LineaFiltro.IdFiltro` → `dbo.CM_Filtro.IdFiltro`
- `dbo.CM_PrevisionIndicador.IdCuadroMando` → `dbo.CM_CuadroMando.IdCuadroMando`
- `dbo.CM_ValorMeta.IdCuadroMando` → `dbo.CM_CuadroMando.IdCuadroMando`
- `dbo.CM_ValorMeta.IdIndicador` → `dbo.CM_Indicador.IdIndicador`
- `dbo.CompraLibroIva.EjercicioAs` → `dbo.Asiento.Ejercicio`
- `dbo.CompraLibroIva.EmpresaAs` → `dbo.Asiento.Empresa`
- `dbo.CompraLibroIva.IdAsiento` → `dbo.Asiento.IdAsiento`
- `dbo.CompraLibroIva.IdTipoFac` → `dbo.Factura.IdTipo`
- `dbo.CompraLibroIva.IdFechaFac` → `dbo.Factura.IdFecha`
- `dbo.CompraLibroIva.IdDocumentoFac` → `dbo.Factura.IdDocumento`
- `dbo.CompraLibroIva.IdContadorFac` → `dbo.Factura.IdContador`
- `dbo.CompraLibroIvaTipos.IdOrden` → `dbo.CompraLibroIva.IdOrden`
- `dbo.CompraLibroIvaTipos.Ejercicio` → `dbo.CompraLibroIva.Ejercicio`
- `dbo.CondicionAlerta.fk_TrabajoAlert_1` → `dbo.TrabajoAlertas.Codigo`
- `dbo.DesabasCISMED.IdMov` → `dbo.DesabasInfo.IdMov`
- `dbo.DesabasInfoAux.IdMov` → `dbo.DesabasInfo.IdMov`
- `dbo.DesabasInfoAux.IdVendedor` → `dbo.Vendedor.IDVENDEDOR`
- `dbo.Destinatario.fk_Cliente_1` → `dbo.Cliente.IDCLIENTE`
- `dbo.Destinatario.fk_Paciente_1` → `dbo.FPACIENTE.IDPACIENTE`
- `dbo.Destinatario.fk_TipoDestinat_1` → `dbo.TipoDestinatario.Codigo`
- `dbo.Destinatario.fk_Vendedor_1` → `dbo.Vendedor.IDVENDEDOR`
- `dbo.DetConfiguracion.IdFormulario` → `dbo.Configuracion.IdFormulario`
- `dbo.DetConfiguracion.IdFormContador` → `dbo.Configuracion.IdFormContador`
- `dbo.DividiblePlazos.fk_Factura_1` → `dbo.Factura.IdTipo`
- `dbo.DividiblePlazos.fk_Factura_2` → `dbo.Factura.IdFecha`
- `dbo.DividiblePlazos.fk_Factura_3` → `dbo.Factura.IdDocumento`
- `dbo.DividiblePlazos.fk_Factura_4` → `dbo.Factura.IdContador`
- `dbo.DividiblePlazos.fk_FormaPago_1` → `dbo.FormaPago.Codigo`
- `dbo.DocEntrega.XDocE_IdEntrega` → `dbo.DocEntrega.IdEntrega`
- `dbo.DocEntrega.XDocE_IdNumDoc` → `dbo.DocEntrega.IdNumDoc`
- `dbo.DocEntrega.XDocE_IdEstadillo` → `dbo.DocEntrega.IdEstadillo`
- `dbo.DocEntrega.IdEntrega` → `dbo.Entrega.IdEntrega`
- `dbo.DocEntrega.IdEstadillo` → `dbo.Entrega.IdEstadillo`
- `dbo.EMail_Envio.fk_EMail_Message` → `dbo.EMail_Message.OID`
- `dbo.EncargoContacto.IdEncargo` → `dbo.Encargo.IdContador`
- `dbo.EncargoFormulaReceta.IdFormula` → `dbo.EncargoLibroRecetaFM.IdEncargo`
- `dbo.EnlaceEstadillo.IdEntrega` → `dbo.DocEntrega.IdEntrega`
- `dbo.EnlaceEstadillo.IdNumDoc` → `dbo.DocEntrega.IdNumDoc`
- `dbo.EnlaceEstadillo.IdEstadillo` → `dbo.DocEntrega.IdEstadillo`
- `dbo.EnlaceEstadillo.IdEntrega` → `dbo.VarEstadillo.IdEntrega`
- `dbo.EnlaceEstadillo.IdNumDoc` → `dbo.VarEstadillo.IdNumDoc`
- `dbo.EnlaceEstadillo.XEnla_IdNumVar` → `dbo.VarEstadillo.IdNumVar`
- `dbo.EnlaceEstadillo.IdEstadillo` → `dbo.VarEstadillo.IdEstadillo`
- `dbo.EnlaceEti.IdEtiqueta` → `dbo.EtiFormula.IdCodigo`
- `dbo.Entorno.fk_EntornoPadre_1` → `dbo.Entorno.Codigo`
- `dbo.EsquemaAux.IDEsquema` → `dbo.ESQUEMA.IDEsquema`
- `dbo.EsquemaIva.XEsqu_IDEsquema` → `dbo.ESQUEMA.IDEsquema`
- `dbo.EstaDec.IdArticu` → `dbo.Articu.IdArticu`
- `dbo.Estarti.IdArticu` → `dbo.Articu.IdArticu`
- `dbo.EstartiLote.IdArticu` → `dbo.Articu.IdArticu`
- `dbo.ExMinCond.IdExMin` → `dbo.ExMin.IdExMin`
- `dbo.ExMinCondLinea.IdExMin` → `dbo.ExMinCond.IdExMin`
- `dbo.ExMinCondLinea.IdCond` → `dbo.ExMinCond.IdCond`
- `dbo.ExMinHistoLinea.IdExMinHisto` → `dbo.ExMinHisto.IdExMinHisto`
- `dbo.Familia.XGrup_IdGrupoIva` → `dbo.Grupoiva.IdGrupoIva`
- `dbo.FamiliaAux.IdSuperFamilia` → `dbo.SuperFamilia.IdSuperFamilia`
- `dbo.FFORMUCOMPON.IDARTICU` → `dbo.FCOMPONENTE.IDARTICU`
- `dbo.Fformula.XENVA_IDENVASE` → `dbo.FCOMPONENTE.IDARTICU`
- `dbo.Fformula.XETI_IDCODIGO` → `dbo.EtiFormula.IdCodigo`
- `dbo.Fformula.XHONO_IDHONORARIO` → `dbo.FHONORARIO.IDHONORARIO`
- `dbo.Fformula.XPACI_IDPACIENTE` → `dbo.FPACIENTE.IDPACIENTE`
- `dbo.FLINEAHONO.IDHONORARIO` → `dbo.FHONORARIO.IDHONORARIO`
- `dbo.FormulaReceta.IdFormula` → `dbo.LibroReceta.IdLibro`
- `dbo.FormulaRecetaVet.IdFormula` → `dbo.LibroRecetaVet.IdLibro`
- `dbo.Ftexto.IDFORMULA` → `dbo.Fformula.IDFORMULA`
- `dbo.GeneActi.IdGrupoGen` → `dbo.GrupoGenerico.IdGrupoGen`
- `dbo.GeneApor.IdAportacion` → `dbo.Aportacion.IdAportacion`
- `dbo.GeneArti.IdGrupoGen` → `dbo.GrupoGenerico.IdGrupoGen`
- `dbo.GrupoCuenta.XGrup_IdGrupo` → `dbo.Grupo.IdGrupo`
- `dbo.GrupoFamilia.Xfami_idFamilia` → `dbo.Familia.IdFamilia`
- `dbo.HistoEncargoFormulaReceta.IdFormula` → `dbo.HistoEncargoLibroRecetaFM.IdEncargo`
- `dbo.HistoFormulaReceta.IdFormula` → `dbo.HistoLibroReceta.IdLibro`
- `dbo.HistoFormulaReceta.Fecha` → `dbo.HistoLibroReceta.Fecha`
- `dbo.HistoFormulaRecetaVet.IdFormula` → `dbo.HistoLibroRecetaVet.IdLibro`
- `dbo.HistoFormulaRecetaVet.Fecha` → `dbo.HistoLibroRecetaVet.Fecha`
- `dbo.HistoricoAlertas.fk_LogAlertas_1` → `dbo.LogAlertas.Numero`
- `dbo.HorarioEnvio.fk_Entorno_1` → `dbo.Entorno.Codigo`
- `dbo.Impor.XProv_IdProveedor` → `dbo.BExterna.XProv_IdProveedor`
- `dbo.Impor.IdBase` → `dbo.BExterna.IdBase`
- `dbo.InferidaCliente.IdCatInferida` → `dbo.InferidaItem.IdCatInferida`
- `dbo.InferidaCliente.IdLinea` → `dbo.InferidaItem.IdLinea`
- `dbo.InferidaCliente.IdCliente` → `dbo.Cliente.IDCLIENTE`
- `dbo.InferidaItem.IdCatInferida` → `dbo.CatInferida.IdCatInferida`
- `dbo.InferidaItemPerfil.IdPerfil` → `dbo.InferidaPerfil.IdPerfil`
- `dbo.InferidaItemPerfil.IdCatInferida` → `dbo.InferidaItem.IdCatInferida`
- `dbo.InferidaItemPerfil.IdLinea` → `dbo.InferidaItem.IdLinea`
- `dbo.InferidaVenta.IdVenta` → `dbo.Venta.IdVenta`
- `dbo.InferidaVenta.IdCatInferida` → `dbo.InferidaItem.IdCatInferida`
- `dbo.InferidaVenta.IdLinea` → `dbo.InferidaItem.IdLinea`
- `dbo.Informe.XGrup_IdGrupo` → `dbo.Grupo.IdGrupo`
- `dbo.InventaDetalle.IdInventario` → `dbo.InventaMaestro.IdInventario`
- `dbo.ItemListaArticu.XItem_IdLista` → `dbo.ListaArticu.IdLista`
- `dbo.ItemListaCliente.XItem_IdCliente` → `dbo.Cliente.IDCLIENTE`
- `dbo.ItemListaCliente.XItem_IdLista` → `dbo.ListaCliente.IdLista`
- `dbo.LibroIva.EjercicioAs` → `dbo.Asiento.Ejercicio`
- `dbo.LibroIva.EmpresaAs` → `dbo.Asiento.Empresa`
- `dbo.LibroIva.IdAsiento` → `dbo.Asiento.IdAsiento`
- `dbo.LibroIva.IdTipoFac` → `dbo.Factura.IdTipo`
- `dbo.LibroIva.IdFechaFac` → `dbo.Factura.IdFecha`
- `dbo.LibroIva.IdDocumentoFac` → `dbo.Factura.IdDocumento`
- `dbo.LibroIva.IdContadorFac` → `dbo.Factura.IdContador`
- `dbo.LibroIvaTipos.IdOrden` → `dbo.LibroIva.IdOrden`
- `dbo.LibroIvaTipos.Ejercicio` → `dbo.LibroIva.Ejercicio`
- `dbo.LineaDevolucion.IdProveedor` → `dbo.Proveedor.IDPROVEEDOR`
- `dbo.LineaFacturaCompra.IdProveedor` → `dbo.Albaran.IdProveedor`
- `dbo.LineaFacturaCompra.IdAlbaran` → `dbo.Albaran.IdAlbaran`
- `dbo.LineaFacturaCompra.IdTipo` → `dbo.Factura.IdTipo`
- `dbo.LineaFacturaCompra.IdFecha` → `dbo.Factura.IdFecha`
- `dbo.LineaFacturaCompra.IdDocumento` → `dbo.Factura.IdDocumento`
- `dbo.LineaFacturaCompra.IdContador` → `dbo.Factura.IdContador`
- `dbo.LineaFranjaOfer.IdFranja` → `dbo.FranjaOferta.IdFranja`
- `dbo.LINEAINCI.XPROT_IDRECEPCION` → `dbo.PROTRECEPCION.IDRECEPCION`
- `dbo.LineaLote.IdLote` → `dbo.Lote.IdLote`
- `dbo.LineaOferta.IdOferta` → `dbo.Oferta.IdOferta`
- `dbo.LineaOfertaDescuento.IdOferta` → `dbo.LineaOferta.IdOferta`
- `dbo.LineaOfertaDescuento.IdLinea` → `dbo.LineaOferta.IdLinea`
- `dbo.LineaOfertaDescuentoAux.IdOferta` → `dbo.LineaOferta.IdOferta`
- `dbo.LineaOfertaDescuentoAux.IdLinea` → `dbo.LineaOferta.IdLinea`
- `dbo.LineaPedido.IdPedido` → `dbo.Pedido.IdPedido`
- `dbo.LineaPedidoCISMED.IdPedido` → `dbo.PedidoCISMED.IdPedido`
- `dbo.LineaPedidoGrupo.IdTipo` → `dbo.PedidoGrupo.IdTipo`
- `dbo.LineaPedidoGrupo.IdPedido` → `dbo.PedidoGrupo.IdPedido`
- `dbo.LINEARECEP.IdRecepcion` → `dbo.Recep.IdRecepcion`
- `dbo.LineaRecepGrupo.IdRecepcion` → `dbo.RecepGrupo.IdRecepcion`
- `dbo.LineaVenta.IdVenta` → `dbo.Venta.IdVenta`
- `dbo.LineaVentaVirtual.IdVenta` → `dbo.Venta.IdVenta`
- `dbo.LinPedir.XLPD_IdPedido` → `dbo.LineaPedido.IdPedido`
- `dbo.LinPedir.XLPD_IdLinea` → `dbo.LineaPedido.IdLinea`
- `dbo.LogAlertas.fk_TrabajoAlert_1` → `dbo.TrabajoAlertas.Codigo`
- `dbo.LoteAux.IdLote` → `dbo.Lote.IdLote`
- `dbo.MesgToHostDestin.XMesg_IdMensaje` → `dbo.MesgVendedor.IdMensaje`
- `dbo.MesgToHostGrupoHosts.XMesg_IdGrupo` → `dbo.MesgToHostGrupo.IdGrupo`
- `dbo.MesgToVendedorGrupoVend.XMesg_IdGrupo` → `dbo.MesgToVendedorGrupo.IdGrupo`
- `dbo.MesgVendedorDestin.XMesg_IdMensaje` → `dbo.MesgVendedor.IdMensaje`
- `dbo.MesgVendedorLinea.XMesg_IdMensaje` → `dbo.MesgVendedor.IdMensaje`
- `dbo.MesgVendedorProg.xMesg_IdMensaje` → `dbo.MesgVendedor.IdMensaje`
- `dbo.MKT_Apartado.IdInforme` → `dbo.MKT_Informe.IdInforme`
- `dbo.MKT_EjeHorizontal.IdInforme` → `dbo.MKT_Apartado.IdInforme`
- `dbo.MKT_EjeHorizontal.IdApartado` → `dbo.MKT_Apartado.IdApartado`
- `dbo.MKT_EjeVertical.IdInforme` → `dbo.MKT_Apartado.IdInforme`
- `dbo.MKT_EjeVertical.IdApartado` → `dbo.MKT_Apartado.IdApartado`
- `dbo.Oferta.IdFranja` → `dbo.FranjaOferta.IdFranja`
- `dbo.OfertaExists.IdOferta` → `dbo.Oferta.IdOferta`
- `dbo.OfertaValidez.IdOferta` → `dbo.Oferta.IdOferta`
- `dbo.PAlbaran.XArt_IdArticu` → `dbo.Articu.IdArticu`
- `dbo.PAlbaran.XProv_IdProveedor` → `dbo.Proveedor.IDPROVEEDOR`
- `dbo.Pedido.XProv_IdProveedor` → `dbo.Proveedor.IDPROVEEDOR`
- `dbo.PedidoCISMED.XProv_IdProveedor` → `dbo.Proveedor.IDPROVEEDOR`
- `dbo.PLANLINEAINCI.XPROT_IDRECEPCION` → `dbo.PLANTRECEPCION.IDRECEPCION`
- `dbo.PlantillaEmail.fk_TrabajoAlert_1` → `dbo.TrabajoAlertas.Codigo`
- `dbo.PLANTILLAPRO.XPARA_IDPARAMODEM` → `dbo.PLANPARAMODEM.IDPARAMODEM`
- `dbo.PlantillaSMS.fk_TrabajoAlert_1` → `dbo.TrabajoAlertas.Codigo`
- `dbo.PLANTRECEPCION.IDRECEPCION` → `dbo.PLANTILLAPRO.IDPROTOCOLO`
- `dbo.Plazo.fk_FormaPago_1` → `dbo.FormaPago.Codigo`
- `dbo.PROTOCOLO.XPARA_IDPARAMODEM` → `dbo.PARAMODEM.IDPARAMODEM`
- `dbo.Proveedor.XCUEN_IDCUENTA` → `dbo.CUENTA.IDCUENTA`
- `dbo.Proveedor.fk_FormaPago_1` → `dbo.FormaPago.Codigo`
- `dbo.ProveedorRepresentantes.XProv_IdProveedor` → `dbo.Proveedor.IDPROVEEDOR`
- `dbo.Recep.XVend_IdVendedor` → `dbo.Vendedor.IDVENDEDOR`
- `dbo.RecetaTSI.XVent_IdVenta` → `dbo.Venta.IdVenta`
- `dbo.RG_Acotacion.IdInforme` → `dbo.RG_CamposInformes.IdInforme`
- `dbo.RG_Acotacion.IdLinea` → `dbo.RG_CamposInformes.IdLinea`
- `dbo.RG_CamposInformes.IdInforme` → `dbo.RG_Informes.idInforme`
- `dbo.Tarifa.IDTIPOCLIENTE` → `dbo.TIPOTARIFA.IDTIPOCLIENTE`
- `dbo.Tarifa.IDTIPOFAMILIA` → `dbo.TIPOTARIFA.IDTIPOFAMILIA`
- `dbo.TM_iosDestinatario.fk_CjtoDestinat_1` → `dbo.CjtoDestinatarios.Codigo`
- `dbo.TM_iosDestinatario.fk_Destinatario_1` → `dbo.Destinatario.Codigo`
- `dbo.TM_nteListaCliente.fk_Cliente_1` → `dbo.Cliente.IDCLIENTE`
- `dbo.TM_nteListaCliente.fk_ListaCliente_1` → `dbo.ListaCliente.IdLista`
- `dbo.TM_sTrabajoAlertas.fk_CjtoDestinat_1` → `dbo.CjtoDestinatarios.Codigo`
- `dbo.TM_sTrabajoAlertas.fk_TrabajoAlert_1` → `dbo.TrabajoAlertas.Codigo`
- `dbo.TM_toDestinatarios.fk_ListaCliente_1` → `dbo.ListaCliente.IdLista`
- `dbo.TM_toDestinatarios.fk_CjtoDestinat_1` → `dbo.CjtoDestinatarios.Codigo`
- `dbo.TrabajoAlertas.fk_Entorno_1` → `dbo.Entorno.Codigo`
- `dbo.VarEstadillo.IdEntrega` → `dbo.DocEntrega.IdEntrega`
- `dbo.VarEstadillo.IdNumDoc` → `dbo.DocEntrega.IdNumDoc`
- `dbo.VarEstadillo.IdEstadillo` → `dbo.DocEntrega.IdEstadillo`
- `dbo.VariableCondicion.fk_Entorno_1` → `dbo.Entorno.Codigo`
- `dbo.Vencimiento.fk_DividiblePla_1` → `dbo.DividiblePlazos.Codigo`
- `dbo.Vencimiento.fk_VencimientoO_1` → `dbo.Vencimiento.fk_DividiblePla_1`
- `dbo.Vencimiento.fk_VencimientoO_2` → `dbo.Vencimiento.Numero`
- `dbo.Venta.XClie_IdCliente` → `dbo.Cliente.IDCLIENTE`
- `dbo.Venta.XVend_IdVendedor` → `dbo.Vendedor.IDVENDEDOR`
- `dbo.VentaAux.IdVenta` → `dbo.Venta.IdVenta`
- `dbo.VentaAuxChile.IdVenta` → `dbo.Venta.IdVenta`

## Relaciones probables

Estas relaciones se han inferido por coincidencia de nombres, tipos y claves simples.

- `dbo.AllianceDevol_LineaCanje.IdCanje` ⇢ `dbo.AllianceDevol_Canje.IdCanje` — MUY ALTA (100/100)
- `dbo.AlmLineaVenta.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.ChgStockMinMax.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.EstaDecEmp.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.EstaDiaCompraEmp.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.EstaDiaEmp.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.EstartiEmp.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.EstartiLoteEmp.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.HistoCaducidadLotes.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.InventaAlmacen.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.InventaDetalleAlmacen.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.InventarioLote.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.LineaRecepLoteOff.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.LineaRecepLoteTemp.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.LineaRecepcionLote.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.LineaVentaLote.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.LoteCaducidad.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.LoteCaducidadNumSerie.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.SICS_Historico.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.SICS_Lista.IdAlmacen` ⇢ `dbo.Almacen.IdAlmacen` — MUY ALTA (100/100)
- `dbo.AportacionDietoCatalunya.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.AportacionNoREPrivada.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.AportacionesOrdenSCO29582003.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.BloqueAux.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.BloqueConcil.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.BloqueEnviado.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.BloqueRD.XApor_IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.BloqueRedir.XApor_IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.ChgBloque.XApor_IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.CloseUpAportacion.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.CopiaAportaciones_REGIMEN_RE_CAT.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.CopiaNuevasAportaciones.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.ExportaBloque.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.FilesRXXI_IO.PAC_Aportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.HistoBloque.XApor_IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.HistoBloqueRE.XApor_IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.LineaRE.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.LineaREPriv.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.LiquidacionAportacion.XId_Aportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.NuevaAportacionOrtopediaCatalunya.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.NuevasAportacionesMutuasCatalunya.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.RecetaTSI.XApor_IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.RecetaTSICancel.XApor_IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.RecetaTsiCajon.IdAportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.TmpAportacion_PEDIDOS.Aportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.TmpAportacion_REBOTICA2.Aportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.TmpAportacion_REBOTICA4.Aportacion` ⇢ `dbo.Aportacion.IdAportacion` — MUY ALTA (100/100)
- `dbo.AH_Stocks2015.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.AH_Stocks2015_Universo.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ActGen_Julio2026_Precios.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ActGen_Marzo2019_Copia.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Alliance360ArticuPed.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.AllianceDevol_LineaCanje.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.AllianceDevol_LineaDevolCaducidades.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.AllianceStockOnline_CurrentConsulta_MOSTRADOR.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.AllianceStockOnline_CurrentConsulta_PORTATIL.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.AllianceStockOnline_CurrentConsulta_REBOTICA2.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.AntibioticosVetManual.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ArticuColores.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ArticuDescOrtopedia.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ArticuExcluidoEmp.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ArticuExcluidoPromo.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ArticuMonoDosis.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Bonus.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExt.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascada.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21042342.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21346912.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21349081.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21373613.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21661693.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21872312.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21973372.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22074252.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22455611.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22674311.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22761838.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22872829.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA23160521.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA2.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21042342.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21346912.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21349081.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21373613.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21661693.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21872312.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21973372.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22074252.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22173693.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22455611.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22674311.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22761838.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22872829.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA23160521.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisce.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21042342.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21346912.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21349081.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21373613.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21661693.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21872312.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21973372.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22074252.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22173693.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22455611.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22674311.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22761838.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22872829.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA23160521.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA2.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21042342.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21346912.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21349081.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21373613.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21661693.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21872312.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21973372.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22074252.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22173693.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22455611.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22674311.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22761838.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22872829.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA23160521.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CalcPVPItemBackup.XArticu_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Cartera.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CarteraAutoCartera.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CarteraAux.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CarteraPedEsp.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ChgCodigoArt.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ChgDescripcion.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ChgPmc.idArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ChgPuc.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ChgPvl.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ChgPvp.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ChgPvpAux.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ChgStockMinMax.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CopiaBajadasVol06Junio2019.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CopiaBajadasVol07Julio2019.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CopiaBajadasVol08Agosto2019.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CopiaBajadasVol08Agosto2020.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CopiaBajadasVol09Septiembre2019.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CopiaBajadasVol10Octubre2024.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CopiaBajadasVol12Diciembre2020.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CopiaProductosSanitarios2012.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.DesabasInfo.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.DetalleOrdenSCO29582003.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.DispAF_IncidenciaArticu.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Encargo.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.EstaDecEmp.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.EstartiEmp.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.EstartiLoteEmp.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ExMin.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ExMinCond.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ExMinHistoLinea.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.FCOMPOACTI.IDARTICU` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.FEspecificacion.IDARTICU` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.FFORMUCOMPON.IDARTICU` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.FHISTOFORMUCOMPON.IDARTICU` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.FHISTOFORMULOTE.IDARTICU` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.FLote.IDARTICU` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.FLoteCalidad.IDARTICU` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Fedicom_LineaConfAlb.idArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.GeneArti.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.HistoCaducidadLotes.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.HistoConsejoPvpCGCOF.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.HistoEnvioArticu.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.HistoOfertaAux.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.HistoPvpIndep.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.HistoValeEstu.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Historico.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.HistoricoAux.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.HistoricoRobot.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.InciAF_ComunicadoArticu.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.InciAF_HojaAmarArticu.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.InventaDetalle.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.InventaDetalleAlmacen.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.InventaDetalleMA.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.InventarioEnvase.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.InventarioLote.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.InventarioLoteNumSerie.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ItemAutoCartera.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ItemListaArticu.XItem_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ItemListaArticuAux.XItem_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LINEARECEP.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaAlbaran.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaControlDev.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaControlDevEstu.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaDevolucion.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaDevolucionAH.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaDevolucionAux.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaDevolucionBulto.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaDevolucionEnvase.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaDevolucionEstu.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaLote.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaPedido.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaPedidoAux.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaPedidoCISMED.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaPedidoEstu.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaPedidoGrupo.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaRecepCliente.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaRecepEnvase.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaRecepEstu.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaRecepEstuDev.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaRecepOFF.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineaRecepPvpIndepOff.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LineasOrdenSCO29582003.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LoteCaducidad.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.LoteCaducidadNumSerie.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.MatrizAlmArticu.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.OfertaExists.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PP_LineaPedido.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PP_LineaPedidoAux.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PatientConnect_Articu.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PatientConnect_Mensaje.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PreNoCGCOF.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PreNo_Recepcion.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PreciosBonifOff.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PreciosCGCOF.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PreciosLastActDieto.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PreciosOrdenSCO29582003.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ProductosSanitarios2012.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ProxDispens.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PvpBajadasVoluntarias.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.PvpIndep.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.RPrivadaPapel.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.SICS_Articu.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.SICS_ArticuSel.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.SICS_Historico.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.SerializablesCGCOF.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Sinonimo.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.SinonimoAux.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR3_Lineas.idarticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR_Lineas.idarticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA2_Lineas.idarticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA4_Lineas.idarticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICAR_Lineas.idarticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_Fact_SERVERIOF_Lineas.idarticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_INILIBROESTUP_NELEMS_ENVASE.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_ListaCEV_MOSTRADOR.XItem_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_ListaCEV_REBOTICA4.XItem_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TMP_ListaCEV_SERVERIOF.XItem_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TempDetalleCGCOF.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TmpCarteraBoniPrecios_Coef_REBOTICA2.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TmpDesabas_MOSTRADOR.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TmpDesabas_PUIGPC.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TmpDesabas_REBOTICA2.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TmpDesabas_SERVERIOF.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TmpListaFiltro_MOSTRADOR3.XItem_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TmpListaFiltro_REBOTICA2.XItem_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.TmpListaFiltro_REBOTICA4.XItem_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Tmp_ItemListaArticuDV.XItem_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Tmp_ListaArticuExcluidos2012.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.Tmp_TraspasoP360.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ValeEstupef.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ValeEstupefAux.XArt_IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.ValeEstupef_DM.IdArticu` ⇢ `dbo.Articu.IdArticu` — MUY ALTA (100/100)
- `dbo.CarteraAutoCartera.IdAutoCartera` ⇢ `dbo.AutoCartera.IdAutoCartera` — MUY ALTA (100/100)
- `dbo.ItemAutoCartera.IdAutoCartera` ⇢ `dbo.AutoCartera.IdAutoCartera` — MUY ALTA (100/100)
- `dbo.CM_EstimacionValorMeta.IdIndicador` ⇢ `dbo.CM_Indicador.IdIndicador` — MUY ALTA (100/100)
- `dbo.Acreedor.XCuen_IdCuenta` ⇢ `dbo.CUENTA.IDCUENTA` — MUY ALTA (100/100)
- `dbo.Apunte.IdCuenta` ⇢ `dbo.CUENTA.IDCUENTA` — MUY ALTA (100/100)
- `dbo.ApunteAux.IdCuenta` ⇢ `dbo.CUENTA.IDCUENTA` — MUY ALTA (100/100)
- `dbo.ClienteXNewTemporal.XCUEN_IDCUENTA` ⇢ `dbo.CUENTA.IDCUENTA` — MUY ALTA (100/100)
- `dbo.ConfigRemesaAux.IdCuenta` ⇢ `dbo.CUENTA.IDCUENTA` — MUY ALTA (100/100)
- `dbo.GrupoCuenta.IdCuenta` ⇢ `dbo.CUENTA.IDCUENTA` — MUY ALTA (100/100)
- `dbo.InferidaCliente.IdCatInferida` ⇢ `dbo.CatInferida.IdCatInferida` — MUY ALTA (100/100)
- `dbo.InferidaItemPerfil.IdCatInferida` ⇢ `dbo.CatInferida.IdCatInferida` — MUY ALTA (100/100)
- `dbo.InferidaVenta.IdCatInferida` ⇢ `dbo.CatInferida.IdCatInferida` — MUY ALTA (100/100)
- `dbo.CatInferida.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.InferidaItem.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.LineaPedidoMatrizAlm.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.MKT_EjeHorizontal.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.MKT_EjeVertical.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.Tmp_ArticuCat_MOSTRADOR.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.Tmp_ArticuCat_PEDIDOS.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.Tmp_ArticuCat_PORTATIL.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.Tmp_ArticuCat_REBOTICA2.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.Tmp_ArticuCat_REBOTICA4.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.Tmp_ArticuCat_REBOTICAR.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.Tmp_ArticuCat_SERVERIOF.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.Tmp_CategoriasComunes_MOSTRADOR.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.Tmp_CategoriasComunes_PEDIDOS.IdCategoria` ⇢ `dbo.Categoria.IdCategoria` — MUY ALTA (100/100)
- `dbo.ClienteExcluidoPromo.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.ClienteIdREPNF.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.ClienteProfSanitario.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.ClienteTarjetas.IDCLIENTE` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.ClienteXNewTemporal.IDCLIENTE` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.CondiFedicom.CodCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.DispAF_ENFERMEDAD.xClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.DispAF_TRATAMIENTO.xClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Encargo.XCli_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_Albaran.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_AlbaranFactura.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_Cargo.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_CargoFactura.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_Descuento.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_Devolucion.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_Factura.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_Impuesto.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_InformacionLote.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_LineaAlbaran.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_Pedido.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Fedicom_PedidoAlbaran.codigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.HISTOLOTE.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.HistoOferta.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.HistoricoAlertas.CLIENTE` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.IndicAF_ENFERMEDAD.xClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.IndicAF_TRATAMIENTO.xClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.LineaSaldoBloqueo.XClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.LineaVentaHistoCli.XClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.LineaVentaMkt.XClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.Oferta.CodigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.OfertasNoAplicadas.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.PACIENTE.XClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.ProveedorStockOnline.CodCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.ProxDispens.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.SMSProgramado.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_MOSTRADOR.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_MOSTRADOR2.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_MOSTRADOR3.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_PEDIDOS.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_PORTATIL.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_REBOTICA2.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_REBOTICA4.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_REBOTICAR.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_SERVERIOF.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Clientes_SURFACE_XAVIER.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR3_Lineas.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR3_Lineas.Xclie_idcliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR_Lineas.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR_Lineas.Xclie_idcliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA2_Lineas.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA2_Lineas.Xclie_idcliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA4_Lineas.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA4_Lineas.Xclie_idcliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICAR_Lineas.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICAR_Lineas.Xclie_idcliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_SERVERIOF_Lineas.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_Fact_SERVERIOF_Lineas.Xclie_idcliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.TMP_vEurosClientes.IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.VentaCruzada.CodigoCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.VentaOFF.XClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.VentaPresupuesto.XClie_IdCliente` ⇢ `dbo.Cliente.IDCLIENTE` — MUY ALTA (100/100)
- `dbo.DispAF_IncidenciaArticu.IdIncidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.DispAF_ListaPRM.IdIncidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.Fedicom_Incidencia.IdIncidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.Fedicom_IncidenciaDevolucion.IdIncidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.FilesRXXIInfo_IO.Tipo_Incidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.HistoeRLibroEstupefacientesMovimientos.Incidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.InciAF_Comunicado.IdIncidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.InciAF_HojaAmarilla.IdIncidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.TelematicaBonus.Incidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.TelematicaCambios.Incidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.TelematicaCatalogo.Incidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.eRLibroEstupefacientesMovimientos.Incidencia` ⇢ `dbo.DispAF_INCIDENCIA.IdIncidencia` — MUY ALTA (100/100)
- `dbo.ApunteParamAux.XEsqu_IDEsquema` ⇢ `dbo.ESQUEMA.IDEsquema` — MUY ALTA (100/100)
- `dbo.InferidaVenta.IdVenta` ⇢ `dbo.EcoceuticsFidel_Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVenta.IdVenta` ⇢ `dbo.EcoceuticsFidel_Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaVirtual.IdVenta` ⇢ `dbo.EcoceuticsFidel_Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.RecetaTSI.XVent_IdVenta` ⇢ `dbo.EcoceuticsFidel_Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ESTUP_CantidadTraducida.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAjuste_MOSTRADOR.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAjuste_MOSTRADOR3.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAjuste_PORTATIL.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAjuste_REBOTICA2.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAjuste_REBOTICA4.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAjuste_SERVERIOF.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAux.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAux_CantidadTraducida.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAux_MOSTRADOR.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAux_MOSTRADOR3.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAux_PORTATIL.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAux_REBOTICA2.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAux_REBOTICA4.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAux_SERVERIOF.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupInfoCat_MOSTRADOR.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupInfoCat_MOSTRADOR3.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupInfoCat_PORTATIL.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupInfoCat_REBOTICA2.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupInfoCat_REBOTICA4.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupInfoCat_SERVERIOF.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupVale.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupVale_MOSTRADOR.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupVale_MOSTRADOR3.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupVale_PORTATIL.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupVale_REBOTICA2.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupVale_REBOTICA4.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupVale_SERVERIOF.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.Estup_MOSTRADOR.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.Estup_MOSTRADOR3.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.Estup_PORTATIL.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.Estup_REBOTICA2.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.Estup_REBOTICA4.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.Estup_SERVERIOF.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.HistoERGAL_Estupefaciente.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.HistoEstup.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.HistoEstupAux.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.HistoEstupDosis.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.HistoeRLibroEstupefacientesMovimientos.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.LibroEstup_Recep.Estup_IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.VESTUPMOVIMIENTOS_CantidadTraducida.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.VESTUP_CantidadTraducida.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.eRLibroEstupefacientesMovimientos.IdEstup` ⇢ `dbo.Estup.IdEstup` — MUY ALTA (100/100)
- `dbo.EstupAux_CantidadTraducida.IdEstupAux` ⇢ `dbo.EstupAux.IdEstupAux` — MUY ALTA (100/100)
- `dbo.EstupAux_MOSTRADOR.IdEstupAux` ⇢ `dbo.EstupAux.IdEstupAux` — MUY ALTA (100/100)
- `dbo.EstupAux_MOSTRADOR3.IdEstupAux` ⇢ `dbo.EstupAux.IdEstupAux` — MUY ALTA (100/100)
- `dbo.EstupAux_PORTATIL.IdEstupAux` ⇢ `dbo.EstupAux.IdEstupAux` — MUY ALTA (100/100)
- `dbo.EstupAux_REBOTICA2.IdEstupAux` ⇢ `dbo.EstupAux.IdEstupAux` — MUY ALTA (100/100)
- `dbo.EstupAux_REBOTICA4.IdEstupAux` ⇢ `dbo.EstupAux.IdEstupAux` — MUY ALTA (100/100)
- `dbo.EstupAux_SERVERIOF.IdEstupAux` ⇢ `dbo.EstupAux.IdEstupAux` — MUY ALTA (100/100)
- `dbo.HistoEstupAux.IdEstupAux` ⇢ `dbo.EstupAux.IdEstupAux` — MUY ALTA (100/100)
- `dbo.EstupVale_MOSTRADOR.IdEstupVale` ⇢ `dbo.EstupVale.IdEstupVale` — MUY ALTA (100/100)
- `dbo.EstupVale_MOSTRADOR3.IdEstupVale` ⇢ `dbo.EstupVale.IdEstupVale` — MUY ALTA (100/100)
- `dbo.EstupVale_PORTATIL.IdEstupVale` ⇢ `dbo.EstupVale.IdEstupVale` — MUY ALTA (100/100)
- `dbo.EstupVale_REBOTICA2.IdEstupVale` ⇢ `dbo.EstupVale.IdEstupVale` — MUY ALTA (100/100)
- `dbo.EstupVale_REBOTICA4.IdEstupVale` ⇢ `dbo.EstupVale.IdEstupVale` — MUY ALTA (100/100)
- `dbo.EstupVale_SERVERIOF.IdEstupVale` ⇢ `dbo.EstupVale.IdEstupVale` — MUY ALTA (100/100)
- `dbo.LineaContingenciaCatVale.IdEstupVale` ⇢ `dbo.EstupVale.IdEstupVale` — MUY ALTA (100/100)
- `dbo.ExMinCondLinea.IdExMin` ⇢ `dbo.ExMin.IdExMin` — MUY ALTA (100/100)
- `dbo.AlbaranFamilia.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.AlbaranFamiliaIVA.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.FilesRXXIInfo_IO.Familia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.Impor.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA2.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21042342.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21346912.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21349081.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21373613.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21661693.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21872312.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21973372.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22074252.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22173693.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22455611.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22674311.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22761838.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22872829.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA23160521.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.ImporTxt.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.Inventa.XFam_IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.InventaAlmacen.XFam_IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.InventaDetalle.XFam_IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.InventaDetalleAlmacen.XFam_IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.InventaDetalleMA.XFam_IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.InventaMA.XFam_IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.OfertaAux.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR3_Lineas.xfam_idfamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR_Lineas.xfam_idfamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA2_Lineas.xfam_idfamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA4_Lineas.xfam_idfamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICAR_Lineas.xfam_idfamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.TMP_Fact_SERVERIOF_Lineas.xfam_idfamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.VentaCruzadaAux.IdFamilia` ⇢ `dbo.Familia.IdFamilia` — MUY ALTA (100/100)
- `dbo.CM_Indicador.IdFiltro` ⇢ `dbo.Filtro.IdFiltro` — MUY ALTA (100/100)
- `dbo.CM_LineaFiltro.IdFiltro` ⇢ `dbo.Filtro.IdFiltro` — MUY ALTA (100/100)
- `dbo.ListaArticu.XList_IdFiltro` ⇢ `dbo.Filtro.IdFiltro` — MUY ALTA (100/100)
- `dbo.ListaCliente.XList_IdFiltro` ⇢ `dbo.Filtro.IdFiltro` — MUY ALTA (100/100)
- `dbo.ActGen_Julio2026_Precios.IdGrupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.CabeceraOrdenSCO29582003.IdGrupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.DetalleOrdenSCO29582003.IdGrupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.MatrizAlmGrupo.IdGrupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.MesgToHostGrupoHosts.XMesg_IdGrupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.MesgToVendedorGrupoVend.XMesg_IdGrupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.PANACIONAL.CodigoGrupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.PGNACIONALESPE.CodigoGrupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.PGNACIONALPARA.CodigoGrupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.RG_Acotacion.Grupo` ⇢ `dbo.Grupo.IdGrupo` — MUY ALTA (100/100)
- `dbo.AlbaranElectronicoIVA.IdGrupoIva` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.AlbaranFamiliaIVA.IdGrupoIva` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.Bases.IdGrupoIva` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.Cliente.GRUPOIVA` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.ClienteXNewTemporal.GRUPOIVA` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.CopiaIdIva2012.IdGrupoIva` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.LineaFactura.XGrup_IdGrupoIva` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.LineaVentaBasesIVA.XGrup_IdGrupoIva` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.LineaVentaIVA.XGrup_IdGrupoIva` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.Proveedor.GRUPOIVA` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.TBaiBases.IdGrupoIva` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.VeriFactuBases.IdGrupoIva` ⇢ `dbo.Grupoiva.IdGrupoIva` — MUY ALTA (100/100)
- `dbo.BloqueAux.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.BloqueRE_OFF.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.DispensacionREPrivadaNF.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.FilesRXXIInfo.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.FilesRXXIInfo_IO.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.HistoBloqueAux.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.LineaRE.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpHCP_MOSTRADOR.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpHCP_MOSTRADOR2.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpHCP_MOSTRADOR3.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpHCP_PEDIDOS.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpHCP_REBOTICA2.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpHCP_REBOTICA4.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpHCP_SERVERIOF.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpNOHCP_MOSTRADOR.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpNOHCP_MOSTRADOR2.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpNOHCP_MOSTRADOR3.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpNOHCP_PEDIDOS.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpNOHCP_REBOTICA2.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpNOHCP_REBOTICA4.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.TmpNOHCP_SERVERIOF.HCP` ⇢ `dbo.HCP.HCP` — MUY ALTA (100/100)
- `dbo.LineaVentaOferta.IdHistoOferta` ⇢ `dbo.HistoOferta.IdHistoOferta` — MUY ALTA (100/100)
- `dbo.PromoCanjeada.IdHistoOferta` ⇢ `dbo.HistoOferta.IdHistoOferta` — MUY ALTA (100/100)
- `dbo.PromoVale.IdHistoOferta` ⇢ `dbo.HistoOferta.IdHistoOferta` — MUY ALTA (100/100)
- `dbo.Tmp_PromoVale.IdHistoOferta` ⇢ `dbo.HistoOferta.IdHistoOferta` — MUY ALTA (100/100)
- `dbo.InciAF_ComunicadoArticu.IdComunicado` ⇢ `dbo.InciAF_Comunicado.IdComunicado` — MUY ALTA (100/100)
- `dbo.InciAF_HojaAmarArticu.IdHojaAmarilla` ⇢ `dbo.InciAF_HojaAmarilla.IdHojaAmarilla` — MUY ALTA (100/100)
- `dbo.InciAF_HojaAmarReaccion.IdHojaAmarilla` ⇢ `dbo.InciAF_HojaAmarilla.IdHojaAmarilla` — MUY ALTA (100/100)
- `dbo.DispAF_INCIDENCIA.IdIndicacion` ⇢ `dbo.IndicAF_INDICACION.IdIndicacion` — MUY ALTA (100/100)
- `dbo.DispAF_LINEADISPENSACION.IdIndicacion` ⇢ `dbo.IndicAF_INDICACION.IdIndicacion` — MUY ALTA (100/100)
- `dbo.InciAF_Comunicado.IdIndicacion` ⇢ `dbo.IndicAF_INDICACION.IdIndicacion` — MUY ALTA (100/100)
- `dbo.InciAF_HojaAmarilla.IdIndicacion` ⇢ `dbo.IndicAF_INDICACION.IdIndicacion` — MUY ALTA (100/100)
- `dbo.IndicAF_ENFERMEDAD.IdIndicacion` ⇢ `dbo.IndicAF_INDICACION.IdIndicacion` — MUY ALTA (100/100)
- `dbo.IndicAF_MEDICAMENTO.IdIndicacion` ⇢ `dbo.IndicAF_INDICACION.IdIndicacion` — MUY ALTA (100/100)
- `dbo.IndicAF_RAZON.IdIndicacion` ⇢ `dbo.IndicAF_INDICACION.IdIndicacion` — MUY ALTA (100/100)
- `dbo.IndicAF_TRATAMIENTO.IdIndicacion` ⇢ `dbo.IndicAF_INDICACION.IdIndicacion` — MUY ALTA (100/100)
- `dbo.IndicAF_TratamientoRazon.IdIndicacion` ⇢ `dbo.IndicAF_INDICACION.IdIndicacion` — MUY ALTA (100/100)
- `dbo.LineaRecepcionLoteTempNumSerie.IdLineaRecepcionLote` ⇢ `dbo.LineaRecepcionLote.IdLineaRecepcionLote` — MUY ALTA (100/100)
- `dbo.AH_LineaventaOferta.idlineaventaoferta` ⇢ `dbo.LineaVentaOferta.IdLineaVentaOferta` — MUY ALTA (100/100)
- `dbo.FHISTOFORMULOTE.IDLOTE` ⇢ `dbo.Lote.IdLote` — MUY ALTA (100/100)
- `dbo.FLoteCalidad.IDLOTE` ⇢ `dbo.Lote.IdLote` — MUY ALTA (100/100)
- `dbo.HISTOLOTE.IdLote` ⇢ `dbo.Lote.IdLote` — MUY ALTA (100/100)
- `dbo.InventarioLote.IdLote` ⇢ `dbo.Lote.IdLote` — MUY ALTA (100/100)
- `dbo.InventarioLoteNumSerie.IdLote` ⇢ `dbo.Lote.IdLote` — MUY ALTA (100/100)
- `dbo.LineaRecepLoteOff.IdLote` ⇢ `dbo.Lote.IdLote` — MUY ALTA (100/100)
- `dbo.LineaRecepLoteTemp.IdLote` ⇢ `dbo.Lote.IdLote` — MUY ALTA (100/100)
- `dbo.SinonimoLote.IDLOTE` ⇢ `dbo.Lote.IdLote` — MUY ALTA (100/100)
- `dbo.MKT_Conjunto.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.MKT_EjeHorizontal.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.MKT_EjeVertical.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.MKT_Elemento.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.MKT_Resultado.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.MKT_Totales.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.RG_Acotacion.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.RG_ArticuloAcotacion.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.RG_CamposInformes.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.RG_FormatoCampoInforme.IdInforme` ⇢ `dbo.MKT_Informe.IdInforme` — MUY ALTA (100/100)
- `dbo.CloseUp.CodMedico` ⇢ `dbo.Medico.IdMedico` — MUY ALTA (100/100)
- `dbo.FHistoFormula.XMEDI_IDMEDICO` ⇢ `dbo.Medico.IdMedico` — MUY ALTA (100/100)
- `dbo.Fformula.XMEDI_IDMEDICO` ⇢ `dbo.Medico.IdMedico` — MUY ALTA (100/100)
- `dbo.InciAF_Comunicado.Medico` ⇢ `dbo.Medico.IdMedico` — MUY ALTA (100/100)
- `dbo.MsgMailAutomatizaciones.IdMsgMail` ⇢ `dbo.MsgMail.IdMsgMail` — MUY ALTA (100/100)
- `dbo.MsgMailCuerpoError.IdMsgMailError` ⇢ `dbo.MsgMailError.IdMsgMailError` — MUY ALTA (100/100)
- `dbo.GS1Registro.CN` ⇢ `dbo.NotifMES_CN.CN` — MUY ALTA (100/100)
- `dbo.LineaDevolucionEnvase.CN` ⇢ `dbo.NotifMES_CN.CN` — MUY ALTA (100/100)
- `dbo.LineaRecepEnvase.CN` ⇢ `dbo.NotifMES_CN.CN` — MUY ALTA (100/100)
- `dbo.LineaVentaEnvase.CN` ⇢ `dbo.NotifMES_CN.CN` — MUY ALTA (100/100)
- `dbo.PeticionSevem.CN` ⇢ `dbo.NotifMES_CN.CN` — MUY ALTA (100/100)
- `dbo.SevemBulkResponse.CN` ⇢ `dbo.NotifMES_CN.CN` — MUY ALTA (100/100)
- `dbo.HistoOferta.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.LineaOfertaDescuento.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.LineaOfertaDescuentoAux.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.LineaVentaOferta.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.LineaVentaOfertaDto.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.OfertaAux.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.OfertaValeAux.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.OfertasNoAplicadas.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.OfertasNoEnFranja.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.SuperFamiliaOferta.IdOferta` ⇢ `dbo.Oferta.IdOferta` — MUY ALTA (100/100)
- `dbo.ERCATA_FM_TARIFADAS_ESTUP.IDPACIENTE` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.ERCATA_TASA.PACIENTE` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.ESTUP_CantidadTraducida.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.EncargoLibroRecetaFM.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.Estup.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.Estup_MOSTRADOR.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.Estup_MOSTRADOR3.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.Estup_PORTATIL.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.Estup_REBOTICA2.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.Estup_REBOTICA4.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.Estup_SERVERIOF.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.FHistoFormula.XPACI_IDPACIENTE` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.Fformula.XPACI_IDPACIENTE` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.HistoEncargoLibroRecetaFM.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.HistoEstup.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.HistoLibroOrtopedia.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.HistoLibroReceta.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.HistoLibroRecetaVet.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.InciAF_Comunicado.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LR.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroOrtopedia.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroOrtopediaOff.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroReceta.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroRecetaElecDilig.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroRecetaOFF.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroRecetaVet.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroRecetaVetOff.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroReceta_MOSTRADOR.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroReceta_MOSTRADOR3.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroReceta_REBOTICA2.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroReceta_REBOTICA4.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.LibroReceta_SERVERIOF.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.VESTUPMOVIMIENTOS_CantidadTraducida.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.VESTUP_CantidadTraducida.Paciente` ⇢ `dbo.PACIENTE.IdPaciente` — MUY ALTA (100/100)
- `dbo.PLANTILLAPRO.XPARA_IDPARAMODEM` ⇢ `dbo.PARAMODEM.IDPARAMODEM` — MUY ALTA (100/100)
- `dbo.LineaPedido.IdPedido` ⇢ `dbo.PP_Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.CondiFedicomProt.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.FacturaDoc.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.FacturaDocExt.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.Fedicom_Devolucion.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.Fedicom_IncidenciaDevolucion.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.Fedicom_LineaDevolucion.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.Fedicom_Pedido.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.Fedicom_Peticion.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.HistoEnvio.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.PP_PedidoAux.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.PedidoAux.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.ProgEnvioEnviado.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.ProgEnvioPedido.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.ProtocoloIPs.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.Proveedor.XPROT_IDPROTOCOLO` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.ProveedorProt.IdProtocolo` ⇢ `dbo.PROTOCOLO.IDPROTOCOLO` — MUY ALTA (100/100)
- `dbo.Acreedor.Provincia` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.Cliente.FIS_PROVINCIA` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.Cliente.PER_PROVINCIA` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.ClienteXNewTemporal.FIS_PROVINCIA` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.ClienteXNewTemporal.PER_PROVINCIA` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.EE_Almacenes.Provincia` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.FPACIENTE.PROVINCIA` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.Farmacia.Provincia` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.Laboratorio.Provincia` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.Medico.Provincia` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.Proveedor.FIS_PROVINCIA` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.Proveedor.PER_PROVINCIA` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.TBAIProvinciaTributa.Provincia` ⇢ `dbo.PROVINCIA.IDProvincia` — MUY ALTA (100/100)
- `dbo.Alliance360ArticuPed.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.AllianceDevol_Canje.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.Fedicom_Incidencia.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.Fedicom_LineaPedido.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.HistoEnvioArticu.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.HistoEnvioIncFedicomV3.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LINEARECEP.XPed_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LinPedir.XLPD_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LinPedirAux.XLPD_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaAlbaran.XPed_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaDevolucionEnvase.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaPedidoAux.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaPedidoCISMED.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaPedidoEstu.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaPedidoFedicom3.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaPedidoGrupo.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaPedidoMatrizAlm.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaRecepCliente.XPed_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaRecepEnvase.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaRecepEstu.XPed_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaRecepEstuDev.XPed_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaRecepFedicom3.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaRecepFedicom3_Otros.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaRecepGrupo.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaRecepOFF.XPed_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.PP_LinPedir.XLPD_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.PP_LinPedirAux.XLPD_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.PP_LineaPedido.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.PP_LineaPedidoAux.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.PP_LineaPedidoFedicom3.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.PedidoGrupo.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.PedidoStockOnline.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.ProgEnvioEnviado.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.ProgEnvioPedGenFaltas.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.ProgEnvioPedido.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.RecepPedidoLP.XPed_IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.ValeEstupefAux.IdPedido` ⇢ `dbo.Pedido.IdPedido` — MUY ALTA (100/100)
- `dbo.LineaVentaOFF.IdPromoVale` ⇢ `dbo.PromoVale.IdPromoVale` — MUY ALTA (100/100)
- `dbo.PromoValeAux.IdPromoVale` ⇢ `dbo.PromoVale.IdPromoVale` — MUY ALTA (100/100)
- `dbo.PromoValeObs.IdPromoVale` ⇢ `dbo.PromoVale.IdPromoVale` — MUY ALTA (100/100)
- `dbo.AlbaranDevol.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.AlbaranDevolucionAH.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.AlbaranFamiliaIVA.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.AlbaranGrupo.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.AlbaranPed.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.AlbaranRecep.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.AllianceDevol_Canje.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.AllianceDevol_DevolCaducidades.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BExternaCalcPvp.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BExternaCategoria.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BExternaColor.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BExternaDto.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BExternaDtoCascada.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BExternaFtp.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BExternaImporQueue.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BExternaMisce.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BExternaPos.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExt.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascada.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21042342.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21346912.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21349081.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21373613.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21661693.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21872312.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA21973372.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22074252.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22455611.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22674311.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22761838.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA22872829.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtDtoCascadaREBOTICA23160521.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA2.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21042342.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21346912.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21349081.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21373613.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21661693.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21872312.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA21973372.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22074252.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22173693.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22455611.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22674311.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22761838.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA22872829.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusExtREBOTICA23160521.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisce.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21042342.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21346912.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21349081.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21373613.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21661693.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21872312.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA21973372.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22074252.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22173693.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22455611.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22674311.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22761838.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA22872829.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusMisceREBOTICA23160521.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA2.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21042342.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21346912.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21349081.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21373613.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21661693.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21872312.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA21973372.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22074252.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22173693.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22455611.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22674311.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22761838.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA22872829.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.BonusREBOTICA23160521.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.CLineaPedProvee.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.CLineaProvee.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.CLineaProveeAux.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.CPedProvee.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.CProvee.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.CProveeAux.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Cartera.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.CarteraPedEsp.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ChgDescripcion.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ChgPmc.idProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ChgPuc.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ChgPvl.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.DesabasInfo.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ESTUP_CantidadTraducida.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.EncargoRecep.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.EncargoRecep.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Estup.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Estup_MOSTRADOR.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Estup_MOSTRADOR3.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Estup_PORTATIL.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Estup_REBOTICA2.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Estup_REBOTICA4.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Estup_SERVERIOF.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.FLote.IDPROVEEDOR` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.HistoEnvio.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.HistoEstup.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.HistoLibroOrtopedia.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.HistoLibroRecetaVet.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.HistoValeEstu.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.HistoValeEstu.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Impor.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporCategoria.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporCategoriaArticu.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporEx.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA2.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA21042342.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA21346912.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA21349081.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA21373613.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA21661693.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA21872312.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA21973372.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA22074252.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA22173693.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA22455611.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA22674311.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA22761838.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA22872829.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporExREBOTICA23160521.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA2.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21042342.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21346912.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21349081.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21373613.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21661693.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21872312.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA21973372.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22074252.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22173693.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22455611.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22674311.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22761838.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA22872829.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporREBOTICA23160521.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ImporTxt.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.LibroOrtopedia.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.LibroOrtopediaOff.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.LibroRecetaVet.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.LibroRecetaVetOff.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.LineaControlDev.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.LineaFacturaCompra.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.LineaVentaProveedor.idProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.MatrizAlmArticu.IDPROVEEDOR` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.MatrizAlmGrupo.IDPROVEEDOR` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PP_Pedido.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PP_PedidoFedicom3.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PedidoFedicom3.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PlanBExterna.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PlanBExternaCategoria.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PlanBExternaDto.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PlanBExternaFtp.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PlanBExternaMisce.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PlanBExternaPos.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.PreNo_DistriProv.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ProgCarteraEnviado.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ProgCarteraPedido.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ProgEnvioEnviado.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ProgEnvioPedido.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ProveedorMargenElm.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ProveedorNumAutoVET.IDPROVEEDOR` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.ProveedorProt.IDPROVEEDOR` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.Recep.XProv_IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.TelematicaBonus.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.TelematicaCambios.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.TelematicaCatalogo.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.TmpDesabas_MOSTRADOR.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.TmpDesabas_PUIGPC.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.TmpDesabas_REBOTICA2.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.TmpDesabas_SERVERIOF.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.VESTUPMOVIMIENTOS_CantidadTraducida.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.VESTUP_CantidadTraducida.Proveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.clineaPedproveerangofamilias.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.clineaproveeRangoFamilias.IdProveedor` ⇢ `dbo.Proveedor.IDPROVEEDOR` — MUY ALTA (100/100)
- `dbo.SICS_Articu.IdHistorico` ⇢ `dbo.SICS_Historico.IdHistorico` — MUY ALTA (100/100)
- `dbo.AutoCarteraExt.IdProgramacion` ⇢ `dbo.SICS_Programacion.IdProgramacion` — MUY ALTA (100/100)
- `dbo.BExternaFtp.IdProgramacion` ⇢ `dbo.SICS_Programacion.IdProgramacion` — MUY ALTA (100/100)
- `dbo.FacturaSASProgExt.IdProgramacion` ⇢ `dbo.SICS_Programacion.IdProgramacion` — MUY ALTA (100/100)
- `dbo.HistoProgMinMax.IdProgramacion` ⇢ `dbo.SICS_Programacion.IdProgramacion` — MUY ALTA (100/100)
- `dbo.LibroEstupefProgExt.IdProgramacion` ⇢ `dbo.SICS_Programacion.IdProgramacion` — MUY ALTA (100/100)
- `dbo.PlanBExternaFtp.IdProgramacion` ⇢ `dbo.SICS_Programacion.IdProgramacion` — MUY ALTA (100/100)
- `dbo.SICS_Lista.IdProgramacion` ⇢ `dbo.SICS_Programacion.IdProgramacion` — MUY ALTA (100/100)
- `dbo.SuperFamiliaOferta.IdSuperFamilia` ⇢ `dbo.SuperFamilia.IdSuperFamilia` — MUY ALTA (100/100)
- `dbo.Situacion.IdSuperSituacion` ⇢ `dbo.SuperSituacion.IdSuperSituacion` — MUY ALTA (100/100)
- `dbo.TBaiEnvio.IdTBAIVenta` ⇢ `dbo.TBaiVenta.IdTBAIVenta` — MUY ALTA (100/100)
- `dbo.Oferta.TipoCliente` ⇢ `dbo.TIPOCLIENTE.IDTIPOCLIENTE` — MUY ALTA (100/100)
- `dbo.TIPOTARIFA.IDTIPOCLIENTE` ⇢ `dbo.TIPOCLIENTE.IDTIPOCLIENTE` — MUY ALTA (100/100)
- `dbo.Tarifa.IDTIPOCLIENTE` ⇢ `dbo.TIPOCLIENTE.IDTIPOCLIENTE` — MUY ALTA (100/100)
- `dbo.VentaCruzada.TipoCliente` ⇢ `dbo.TIPOCLIENTE.IDTIPOCLIENTE` — MUY ALTA (100/100)
- `dbo.CajaMon.XTarj_IdTarjeta` ⇢ `dbo.Tarjeta.IdTarjeta` — MUY ALTA (100/100)
- `dbo.CajaMonTxt.XTarj_IdTarjeta` ⇢ `dbo.Tarjeta.IdTarjeta` — MUY ALTA (100/100)
- `dbo.VentaTarjetaDto.XTarj_IdTarjeta` ⇢ `dbo.Tarjeta.IdTarjeta` — MUY ALTA (100/100)
- `dbo.CajaMonTxt.XVend_IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.CashFarmaAccion.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.CashFarmaHistorico.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.CashFarmaInfoCobro.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.CashLogyAccion.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.CashLogyHistorico.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.CashLogyInfoCobro.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ChgCodigoArt.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ChgDescripcion.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ChgPmc.idVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ChgPuc.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ChgPvl.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ChgPvp.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ChgPvpAux.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ChgStockMinMax.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.Cliente.XVEND_IDVENDEDOR` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ClienteXNewTemporal.XVEND_IDVENDEDOR` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.Encargo.Vendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.EstaSevemAlertas.Vendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.EstaSevemDesactivaciones.Vendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.FHistoFormula.XVEND_IDVENDEDOR` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.Fformula.XVEND_IDVENDEDOR` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.HistoChgFormaPago.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.HistoEnvio.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.HistoOferta.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.Historico.XVend_IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.HistoricoCashDro.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.LineaVentaMkt.XVend_IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.MesgToVendedorGrupoVend.XVend_IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.MesgVendedorGrupo.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.PP_PedidoAux.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.PedidoAux.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.PerfilProtecc.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.PeticionSevem.Vendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.PreNo_Operacion.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.Protecc.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.RPrivadaPapel.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.RXXIVendLicen.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.SICS_Lista.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.Serie.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.SevemBulkTransaction.Vendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.TmpDesabas_MOSTRADOR.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.TmpDesabas_PUIGPC.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.TmpDesabas_REBOTICA2.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.TmpDesabas_SERVERIOF.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.ValeEstupef.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.VendedorAux.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.VendedorTurno.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.VendedorTurnoHisto.IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.VentaPresupuesto.XVend_IdVendedor` ⇢ `dbo.Vendedor.IDVENDEDOR` — MUY ALTA (100/100)
- `dbo.AH_BloqueRE.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_CantidadPuntos.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_EC_Venta.EC_IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_HistoBloqueRE.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_IssuedVouchers.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_LV_ean13_Scanned.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_LineaventaOferta.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_NumberPromoEuros.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_NumberPromoPuntos.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_Promociones.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_PromosTipoA.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_PromosTipoA_Detalle.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_ReceiptTotalPrice.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AH_UsedVouchers.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AllianceFidel_Venta.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.AlmLineaVenta.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.BloqueRE_OFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.BloqueRedir.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.CajaMon.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.CajaMonTxt.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ChgDescripcion.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ChgPmc.idVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ChgPuc.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ChgPvl.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ChgPvp.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ChgPvpAux.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ClienteProfSanitario.XVen_IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.CloseUp.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.CosteVenta.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.CosteVentaAux.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.DispAF_DISPENSACION.XVen_IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.FPLus_Operaciones.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.FPlus_ListaRegalos.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.FilesRXXIVenta.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.FormulaRecetaOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.FormulaRecetaVetOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.GS1Registro.IDVENTA` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.HISTOLOTE.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.HistoBloqueRedir.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.HistoChgFormaPago.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.HistoLibroOrtopedia.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.HistoOferta.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.HistoPvpIndep.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.IndicAF_INDICACION.XVen_IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LibroOrtopedia.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LibroOrtopediaAuxOff.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LibroOrtopediaCartOff.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LibroOrtopediaOff.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LibroRecetaAuxOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LibroRecetaOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LibroRecetaVetAuxOff.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LibroRecetaVetOff.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaContingencia.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaContingenciaCat.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaContingenciaCatVale.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaFactura.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaFacturaE.Idventa` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaFromVentaCruzada.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaFromVentaCruzadaAux.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaRE.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaREPriv.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaREVet.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaSaldoBloqueo.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaAbonoEuros.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaAux.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaBasesIVA.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaCip.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaCipOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaDevol.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaEAN.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaEANOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaEnvase.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaEnvasesOff.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaHistoCli.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaIVA.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaLote.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaLoteNumSerie.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaMkt.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaOferta.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaOfertaDto.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaOrtopedia.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaOrtopediaDesc.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaPresupuesto.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaProveedor.idVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaRectificativa.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaReden.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaRobot_OFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVentaVale.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaVtaLotePromoTicket.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ListaLotesOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.MA_OFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ModLineaVenta.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ObservacionesVenta.Idventa` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ObservacionesVentaOFF.Idventa` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.PAGOLINEA.XLine_IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.PeticionSevem.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.PromoExternaLineasTicket.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.PromoVale.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.ProxDispens.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.RPrivadaPapel.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.RecetaTSICancel.XVen_IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.RecetaTsiOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.TBaiBases.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.TBaiVenta.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR3_Lineas.idventa` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.TMP_Fact_MOSTRADOR_Lineas.idventa` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA2_Lineas.idventa` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICA4_Lineas.idventa` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.TMP_Fact_REBOTICAR_Lineas.idventa` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.TMP_Fact_SERVERIOF_Lineas.idventa` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.Tmp_LineasRectificadas.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.Tmp_PromoVale.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.TotalVentaCEV.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.VentaAnulacionSustitutiva.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.VentaCliente.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.VentaFicherosProcesadosRE.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.VentaLote.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.VentaRE.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.VentaREOFF.IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.VentaReimpresion.XVen_IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.VentaTarjetaDto.XVen_IdVenta` ⇢ `dbo.Venta.IdVenta` — MUY ALTA (100/100)
- `dbo.LineaFromVentaCruzada.IdVentaCruzada` ⇢ `dbo.VentaCruzada.IdVentaCruzada` — MUY ALTA (100/100)
- `dbo.LineaVentaCruzada.IdVentaCruzada` ⇢ `dbo.VentaCruzada.IdVentaCruzada` — MUY ALTA (100/100)
- `dbo.LineaVentaOFF.IdVentaCruzada` ⇢ `dbo.VentaCruzada.IdVentaCruzada` — MUY ALTA (100/100)
- `dbo.VentaCruzadaAux.IdVentaCruzada` ⇢ `dbo.VentaCruzada.IdVentaCruzada` — MUY ALTA (100/100)
- `dbo.VentaCruzadaAux2.IdVentaCruzada` ⇢ `dbo.VentaCruzada.IdVentaCruzada` — MUY ALTA (100/100)
- `dbo.VeriFactuEnvioItemError.IdVerifactuEnvio` ⇢ `dbo.VerifactuEnvio.IdVerifactuEnvio` — MUY ALTA (100/100)
- `dbo.VerifactuEnvioItem.IdVerifactuEnvio` ⇢ `dbo.VerifactuEnvio.IdVerifactuEnvio` — MUY ALTA (100/100)
- `dbo.VerifactuItem.IdVerifactuFactura` ⇢ `dbo.VerifactuFactura.IdVerifactuFactura` — MUY ALTA (100/100)
- `dbo.VeriFactuBases.IdVerifactuItem` ⇢ `dbo.VerifactuItem.IdVerifactuItem` — MUY ALTA (100/100)
- `dbo.VeriFactuEnvioItemError.IdVerifactuItem` ⇢ `dbo.VerifactuItem.IdVerifactuItem` — MUY ALTA (100/100)
- `dbo.VerifactuEncadenamiento.IdVerifactuItem` ⇢ `dbo.VerifactuItem.IdVerifactuItem` — MUY ALTA (100/100)
- `dbo.VerifactuEnvioItem.IdVerifactuItem` ⇢ `dbo.VerifactuItem.IdVerifactuItem` — MUY ALTA (100/100)
- `dbo.VerifactuFactura.IdVerifactuItem` ⇢ `dbo.VerifactuItem.IdVerifactuItem` — MUY ALTA (100/100)
- `dbo.VerifactuItemRectificadas.IdVeriFactuItem` ⇢ `dbo.VerifactuItem.IdVerifactuItem` — MUY ALTA (100/100)
- `dbo.AutoCartera.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.EncargoFormulaReceta.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.EncargoLibroRecetaFM.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.FormulaReceta.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.FormulaRecetaVet.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.HistoEncargoFormulaReceta.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.HistoEncargoLibroRecetaFM.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.HistoFormulaReceta.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.HistoFormulaRecetaVet.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.HistoLibroReceta.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.HistoLibroRecetaVet.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LR.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroReceta.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroRecetaElecDilig.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroRecetaOFF.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroRecetaVet.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroRecetaVetOff.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroReceta_MOSTRADOR.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroReceta_MOSTRADOR3.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroReceta_REBOTICA2.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroReceta_REBOTICA4.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LibroReceta_SERVERIOF.XForm_IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.LinPedir.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.PP_LinPedir.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.ProgMinMaxAux.IdFormula` ⇢ `dbo.Formula.IdFormula` — ALTA (90/100)
- `dbo.AlbaranPed.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.FLote.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.Fedicom_LineaConfAlb.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.Iteminci.XPROT_IDRECEPCION` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LINEAINCI.XPROT_IDRECEPCION` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LibroEstup_Recep.Recep_IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LibroRecetaVet_Recep.Recep_IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaAlbaran.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepAE.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepAux.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepCliente.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepEnvase.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepEnvasesOff.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepEstu.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepEstuDev.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepFedicom3.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepFedicom3_Otros.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepGrupo.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepLoteOff.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepLoteOffNumSerie.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepLoteTemp.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepLoteTempNumSerie.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepOFF.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepPvpIndepOff.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepcionLote.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.LineaRecepcionLoteNumSerie.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.PLANLINEAINCI.XPROT_IDRECEPCION` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.PeticionSevem.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.PlanIteminci.XPROT_IDRECEPCION` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.PreNo_Recepcion.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.PreciosBonifOff.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.RecepAE.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.RecepCliente.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.RecepPedidoLP.IdRecepcion` ⇢ `dbo.Recep.IdRecepcion` — ALTA (90/100)
- `dbo.AcoEstadillo.XAcoE_IdAportacion` ⇢ `dbo.AportacionRD.IdAportacion` — MEDIA (80/100)
- `dbo.Bloque.XApor_IdAportacion` ⇢ `dbo.AportacionRD.IdAportacion` — MEDIA (80/100)
- `dbo.BloqueExt.IdAportacion` ⇢ `dbo.AportacionRD.IdAportacion` — MEDIA (80/100)
- `dbo.BloquePrescripcion.IdAportacion` ⇢ `dbo.AportacionRD.IdAportacion` — MEDIA (80/100)
- `dbo.BloqueRE.IdAportacion` ⇢ `dbo.AportacionRD.IdAportacion` — MEDIA (80/100)
- `dbo.GeneApor.IdAportacion` ⇢ `dbo.AportacionRD.IdAportacion` — MEDIA (80/100)
- `dbo.DispAF_LINEADISPENSACION.CodigoArt` ⇢ `dbo.ArticuAux.CodigoArt` — MEDIA (80/100)
- `dbo.IndicAF_TratamientoRazon.CodigoArt` ⇢ `dbo.ArticuAux.CodigoArt` — MEDIA (80/100)
- `dbo.Estarti.IdArticu` ⇢ `dbo.ArticuBolsas.IdArticu` — MEDIA (80/100)
- `dbo.EstartiLote.IdArticu` ⇢ `dbo.ArticuBolsas.IdArticu` — MEDIA (80/100)
- `dbo.PAlbaran.XArt_IdArticu` ⇢ `dbo.ArticuBolsas.IdArticu` — MEDIA (80/100)
- `dbo.ArticuColores.IdGrupoColor` ⇢ `dbo.ArticuGrupoColor.IdGrupoColor` — MEDIA (80/100)
- `dbo.AutoCartera.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.Cartera.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.CarteraAutoCartera.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.CarteraAux.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.CarteraPedEsp.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.LineaDevolucion.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.LineaDevolucionAH.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.LineaDevolucionAux.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.LineaDevolucionBulto.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.LineaDevolucionEnvase.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.LineaDevolucionEstu.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.ProgCarteraEnviado.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.ProgCarteraPedido.IdCartera` ⇢ `dbo.CARTERAS.IdCartera` — MEDIA (80/100)
- `dbo.CM_ValorMeta.IdIndicador` ⇢ `dbo.CM_PrevisionIndicador.IdIndicador` — MEDIA (80/100)
- `dbo.CalcPVPItemBackup.XBackup_IdBackup` ⇢ `dbo.CalcPVPBackup.IdBackup` — MEDIA (80/100)
- `dbo.CalcPVPItemTablaAux.IdItem` ⇢ `dbo.CalcPVPItemTabla.IdItem` — MEDIA (80/100)
- `dbo.Iteminci.IDITEM` ⇢ `dbo.CalcPVPItemTabla.IdItem` — MEDIA (80/100)
- `dbo.PlanIteminci.IDITEM` ⇢ `dbo.CalcPVPItemTabla.IdItem` — MEDIA (80/100)
- `dbo.BExternaCalcPvp.IdTabla` ⇢ `dbo.CalcPVPTabla.IdTabla` — MEDIA (80/100)
- `dbo.CalcPVPBackup.XTabla_IdTabla` ⇢ `dbo.CalcPVPTabla.IdTabla` — MEDIA (80/100)
- `dbo.CalcPVPItemTabla.XTabla_IdTabla` ⇢ `dbo.CalcPVPTabla.IdTabla` — MEDIA (80/100)
- `dbo.CalcPVPItemTablaAux.IdTabla` ⇢ `dbo.CalcPVPTabla.IdTabla` — MEDIA (80/100)
- `dbo.CashLogyConfigCajon.IdCajon` ⇢ `dbo.CashFarmaConfigCajon.IdCajon` — MEDIA (80/100)
- `dbo.CashLogyContab.IdCajon` ⇢ `dbo.CashFarmaConfigCajon.IdCajon` — MEDIA (80/100)
- `dbo.Accesos.IdMaquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.AccesosLopd.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.AutoCarteraExt.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.BExternaFtp.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.BExternaImporQueue.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CajonCashDro.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CajonCashDroAux.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashFarmaAccion.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashFarmaHistorico.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashFarmaInfoCobro.IdMaquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashFarmaMonitorParam.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashFarmaParametro.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashLogyAccion.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashLogyConfigCajon.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashLogyHistorico.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashLogyInfoCobro.IdMaquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CashLogyParametro.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.ContadoresMaq.IdMaquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.EMail_Message.Envio_Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.FacturaSASProgExt.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoAutoCierreBloques.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoCISMED.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoCaducidadLotes.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoEnvio.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoInventario.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoInventarioDetalle.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoLREA.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoLista.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoListaCliente.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoPreciosCGCOF.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoProgMinMax.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoPvpIndep.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoValeEstu.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoVentaCruzada.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoVentaCruzadaLista.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.Historico.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.HistoricoCashDro.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.Imagenes.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.LibroEstupefProgExt.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.ParametroCashDro.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.PlanBExternaFtp.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.ProgCartera.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.ProgEnvio.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.ProgMinMaxAux.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.RecepAux.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.SICS_Historico.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.SICS_Lista.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.Temporales.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.Venta.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.VentaFicherosProcesadosRE.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.VentaFicherosSeleccionadosRE.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.VentaOFF.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.VentaPresupuesto.Maquina` ⇢ `dbo.CashLogyMaquinas.Maquina` — MEDIA (80/100)
- `dbo.CajaMon.XVend_IdVendedor` ⇢ `dbo.CashLogyVendedor.IdVendedor` — MEDIA (80/100)
- `dbo.DesabasInfoAux.IdVendedor` ⇢ `dbo.CashLogyVendedor.IdVendedor` — MEDIA (80/100)
- `dbo.Recep.XVend_IdVendedor` ⇢ `dbo.CashLogyVendedor.IdVendedor` — MEDIA (80/100)
- `dbo.Venta.XVend_IdVendedor` ⇢ `dbo.CashLogyVendedor.IdVendedor` — MEDIA (80/100)
- `dbo.InferidaCliente.IdCliente` ⇢ `dbo.ClienteAux.IdCliente` — MEDIA (80/100)
- `dbo.ItemListaCliente.XItem_IdCliente` ⇢ `dbo.ClienteAux.IdCliente` — MEDIA (80/100)
- `dbo.Venta.XClie_IdCliente` ⇢ `dbo.ClienteAux.IdCliente` — MEDIA (80/100)
- `dbo.CondiFedicomProt.IdCondi` ⇢ `dbo.CondiFedicom.IdCondi` — MEDIA (80/100)
- `dbo.DesabasInfo.Causa` ⇢ `dbo.DesabasCausa.CodCausa` — MEDIA (80/100)
- `dbo.DesabasTipoMov.CodCausa` ⇢ `dbo.DesabasCausa.CodCausa` — MEDIA (80/100)
- `dbo.TmpDesabas_MOSTRADOR.Causa` ⇢ `dbo.DesabasCausa.CodCausa` — MEDIA (80/100)
- `dbo.TmpDesabas_PUIGPC.Causa` ⇢ `dbo.DesabasCausa.CodCausa` — MEDIA (80/100)
- `dbo.TmpDesabas_REBOTICA2.Causa` ⇢ `dbo.DesabasCausa.CodCausa` — MEDIA (80/100)
- `dbo.TmpDesabas_SERVERIOF.Causa` ⇢ `dbo.DesabasCausa.CodCausa` — MEDIA (80/100)
- `dbo.EncargoAux.IdEncargo` ⇢ `dbo.EncargoCar.IdEncargo` — MEDIA (80/100)
- `dbo.SMSProgramado.IdEncargo` ⇢ `dbo.EncargoCar.IdEncargo` — MEDIA (80/100)
- `dbo.CashFarmaAccion.IdEstado` ⇢ `dbo.EncargoEstados.IdEstado` — MEDIA (80/100)
- `dbo.CashFarmaEstado.IdEstado` ⇢ `dbo.EncargoEstados.IdEstado` — MEDIA (80/100)
- `dbo.CashLogyAccion.IdEstado` ⇢ `dbo.EncargoEstados.IdEstado` — MEDIA (80/100)
- `dbo.DispAF_INCIDENCIA.IdEstado` ⇢ `dbo.EncargoEstados.IdEstado` — MEDIA (80/100)
- `dbo.APUNTEPARAM.XEsqu_IDEsquema` ⇢ `dbo.EsquemaAux.IDEsquema` — MEDIA (80/100)
- `dbo.EsquemaIva.XEsqu_IDEsquema` ⇢ `dbo.EsquemaAux.IDEsquema` — MEDIA (80/100)
- `dbo.FCOMPONENTE.XHONO_IDHONORARIO` ⇢ `dbo.FHONORARIO.IDHONORARIO` — MEDIA (80/100)
- `dbo.FHistoFormula.XHONO_IDHONORARIO` ⇢ `dbo.FHONORARIO.IDHONORARIO` — MEDIA (80/100)
- `dbo.LineaLote.IdLote` ⇢ `dbo.FLote.IDLOTE` — MEDIA (80/100)
- `dbo.FLineaPlantilla.IdPlantilla` ⇢ `dbo.FPlantilla.IdPlantilla` — MEDIA (80/100)
- `dbo.PlanBExternaDto.IdPlantilla` ⇢ `dbo.FPlantilla.IdPlantilla` — MEDIA (80/100)
- `dbo.ExportaBloque.Entidad` ⇢ `dbo.FacturaSASEntidades.IdEntidad` — MEDIA (80/100)
- `dbo.Articu.XFam_IdFamilia` ⇢ `dbo.FamiliaAux.IdFamilia` — MEDIA (80/100)
- `dbo.GrupoFamilia.Xfami_idFamilia` ⇢ `dbo.FamiliaAux.IdFamilia` — MEDIA (80/100)
- `dbo.ESTUP_CantidadTraducida.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.Estup.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.Estup_MOSTRADOR.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.Estup_MOSTRADOR3.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.Estup_PORTATIL.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.Estup_REBOTICA2.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.Estup_REBOTICA4.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.Estup_SERVERIOF.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.FFORMUCOMPON.IDFORMULA` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.FHISTOFORMUCOMPON.IDFORMULA` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.FHISTOFORMULOTE.IDFORMULA` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.FHistoFormula.IDFORMULA` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.FHistoObserva.IDFORMULA` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.FHistoTexto.IDFORMULA` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.Grupo.Formula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.HistoEstup.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.HistoLibroReceta.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.HistoLibroRecetaVet.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroReceta.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroRecetaElecDilig.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroRecetaOFF.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroRecetaVet.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroRecetaVetOff.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroReceta_MOSTRADOR.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroReceta_MOSTRADOR3.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroReceta_REBOTICA2.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroReceta_REBOTICA4.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.LibroReceta_SERVERIOF.CodFormula` ⇢ `dbo.Fformula.IDFORMULA` — MEDIA (80/100)
- `dbo.Aportacion.XGApo_IdGrupoAportacion` ⇢ `dbo.GrupoAportacionExt.IdGrupoAportacion` — MEDIA (80/100)
- `dbo.ActGen_Julio2026_CH.IdGrupoGen` ⇢ `dbo.GrupoGenerico.IdGrupoGen` — MEDIA (80/100)
- `dbo.AportacionesOrdenSCO29582003.IdGrupoGen` ⇢ `dbo.GrupoGenerico.IdGrupoGen` — MEDIA (80/100)
- `dbo.ConjuntosOrdenSCO29582003.IdGrupoGen` ⇢ `dbo.GrupoGenerico.IdGrupoGen` — MEDIA (80/100)
- `dbo.GeneApor.IdGrupoGen` ⇢ `dbo.GrupoGenerico.IdGrupoGen` — MEDIA (80/100)
- `dbo.LineasOrdenSCO29582003.IdGrupoGen` ⇢ `dbo.GrupoGenerico.IdGrupoGen` — MEDIA (80/100)
- `dbo.HistoEnvioArticu.IdEnvio` ⇢ `dbo.HistoEnvio.IdEnvio` — MEDIA (80/100)
- `dbo.HistoEnvioInc.IdEnvio` ⇢ `dbo.HistoEnvio.IdEnvio` — MEDIA (80/100)
- `dbo.HistoEnvioIncFedicomV3.IdEnvio` ⇢ `dbo.HistoEnvio.IdEnvio` — MEDIA (80/100)
- `dbo.HistoEnvioObs.IdEnvio` ⇢ `dbo.HistoEnvio.IdEnvio` — MEDIA (80/100)
- `dbo.HistoEnvioTraza.IdEnvio` ⇢ `dbo.HistoEnvio.IdEnvio` — MEDIA (80/100)
- `dbo.HistoChgFormaPagoLinea.IdHisto` ⇢ `dbo.HistoEstupDosis.IdHisto` — MEDIA (80/100)
- `dbo.ESTUP_CantidadTraducida.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.Estup.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.Estup_MOSTRADOR.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.Estup_MOSTRADOR3.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.Estup_PORTATIL.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.Estup_REBOTICA2.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.Estup_REBOTICA4.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.Estup_SERVERIOF.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.FHistoFormula.LIBRO` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.Fformula.LIBRO` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.HistoEstup.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.HistoLibroOrtopedia.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.HistoLibroOrtopediaAux.XLibro_IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.HistoLibroOrtopediaCart.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.HistoLibroReceta.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.HistoLibroRecetaAux.XLibro_IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.HistoLibroRecetaVet.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.HistoLibroRecetaVetAux.XLibro_IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroOrtopediaCart.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaAux_MOSTRADOR.XLibro_IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaAux_MOSTRADOR3.XLibro_IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaAux_REBOTICA2.XLibro_IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaAux_REBOTICA4.XLibro_IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaAux_SERVERIOF.XLibro_IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaElecDilig.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaInfoCat_MOSTRADOR.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaInfoCat_MOSTRADOR3.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaInfoCat_REBOTICA2.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaInfoCat_REBOTICA4.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaInfoCat_SERVERIOF.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroRecetaVet_Recep.LibroRecetaVet_IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroReceta_MOSTRADOR.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroReceta_MOSTRADOR3.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroReceta_REBOTICA2.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroReceta_REBOTICA4.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.LibroReceta_SERVERIOF.IdLibro` ⇢ `dbo.LibroReceta.IdLibro` — MEDIA (80/100)
- `dbo.AportacionAux.IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.ItemListaArticu.XItem_IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.ItemListaArticuAux.XItem_IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.ItemListaCliente.XItem_IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.ProgMinMaxAux.IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.SICS_Historico.IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.SICS_Lista.IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.TmpListaFiltro_MOSTRADOR3.XItem_IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.TmpListaFiltro_REBOTICA2.XItem_IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.TmpListaFiltro_REBOTICA4.XItem_IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.Tmp_ItemListaArticuDV.XItem_IdLista` ⇢ `dbo.ListaGrupo.IdLista` — MEDIA (80/100)
- `dbo.GrupoCuenta.XGrup_IdGrupo` ⇢ `dbo.MesgToHostGrupo.IdGrupo` — MEDIA (80/100)
- `dbo.Informe.XGrup_IdGrupo` ⇢ `dbo.MesgToHostGrupo.IdGrupo` — MEDIA (80/100)
- `dbo.MesgVendedor.IdProg` ⇢ `dbo.MesgVendedorProg.IdProg` — MEDIA (80/100)
- `dbo.LineaOferta.IdOferta` ⇢ `dbo.OfertaLote.IdOferta` — MEDIA (80/100)
- `dbo.PROTOCOLO.XPARA_IDPARAMODEM` ⇢ `dbo.PLANPARAMODEM.IDPARAMODEM` — MEDIA (80/100)
- `dbo.AlbaranRecep.IdRecepcion` ⇢ `dbo.PROTRECEPCION.IDRECEPCION` — MEDIA (80/100)
- `dbo.LINEARECEP.IdRecepcion` ⇢ `dbo.PROTRECEPCION.IDRECEPCION` — MEDIA (80/100)
- `dbo.ConfigRemesa.Provincia` ⇢ `dbo.PROVINCIAS.COD_PROVINCIA` — MEDIA (80/100)
- `dbo.Albaran.IdProveedor` ⇢ `dbo.ProveedorAux.IDPROVEEDOR` — MEDIA (80/100)
- `dbo.AlbaranFamilia.IdProveedor` ⇢ `dbo.ProveedorAux.IDPROVEEDOR` — MEDIA (80/100)
- `dbo.BExterna.XProv_IdProveedor` ⇢ `dbo.ProveedorAux.IDPROVEEDOR` — MEDIA (80/100)
- `dbo.Bonus.IdProveedor` ⇢ `dbo.ProveedorAux.IDPROVEEDOR` — MEDIA (80/100)
- `dbo.LineaDevolucion.IdProveedor` ⇢ `dbo.ProveedorAux.IDPROVEEDOR` — MEDIA (80/100)
- `dbo.PAlbaran.XProv_IdProveedor` ⇢ `dbo.ProveedorAux.IDPROVEEDOR` — MEDIA (80/100)
- `dbo.Pedido.XProv_IdProveedor` ⇢ `dbo.ProveedorAux.IDPROVEEDOR` — MEDIA (80/100)
- `dbo.PedidoCISMED.XProv_IdProveedor` ⇢ `dbo.ProveedorAux.IDPROVEEDOR` — MEDIA (80/100)
- `dbo.ProveedorRepresentantes.XProv_IdProveedor` ⇢ `dbo.ProveedorAux.IDPROVEEDOR` — MEDIA (80/100)
- `dbo.ClienteIdREPNF.IdMutua` ⇢ `dbo.REPNFMutuas.IdMutua` — MEDIA (80/100)
- `dbo.REPNFRepositorio.IdMutua` ⇢ `dbo.REPNFMutuas.IdMutua` — MEDIA (80/100)
- `dbo.Categoria.Entorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.ChgDescripcion.IdEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.ChgPmc.idEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.ChgPuc.IdEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.ChgPvl.IdEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.ChgPvp.IdEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.ChgPvpAux.IdEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.ChgStockMinMax.IdEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.Etiqueta_Info.IdEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.Etiqueta_Info_Aux.IdEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.Etiqueta_Items.IdEntorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.ImplicitaExcluye.Entorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.ImplicitaParam.Entorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.MKT_EjeHorizontal.Entorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.MKT_EjeVertical.Entorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.SMSProgramado.Entorno` ⇢ `dbo.RG_Entornos.IdEntorno` — MEDIA (80/100)
- `dbo.Etiqueta_Info.Estilo` ⇢ `dbo.RG_EstiloInforme.IdEstilo` — MEDIA (80/100)
- `dbo.RG_FormatoCampoInforme.Estilo` ⇢ `dbo.RG_EstiloInforme.IdEstilo` — MEDIA (80/100)
- `dbo.RG_Informes.IdEstilo` ⇢ `dbo.RG_EstiloInforme.IdEstilo` — MEDIA (80/100)
- `dbo.MKT_Apartado.IdInforme` ⇢ `dbo.RG_Informes.idInforme` — MEDIA (80/100)
- `dbo.TBAIFacturaRecetasTipos.IdFacturaRecetas` ⇢ `dbo.TBAIFacturaRecetas.IdFacturaRecetas` — MEDIA (80/100)
- `dbo.Venta.TipoFactura` ⇢ `dbo.VerifactuTipoFactura.IdTipoFactura` — MEDIA (80/100)
- `dbo.VerifactuFactura.TipoFactura` ⇢ `dbo.VerifactuTipoFactura.IdTipoFactura` — MEDIA (80/100)
- `dbo.VerifactuIncidencia.TipoIncidencia` ⇢ `dbo.VerifactuTipoIncidencia.IdTipoIncidencia` — MEDIA (80/100)
- `dbo.DispAF_INCIDENCIA.CodResultado` ⇢ `dbo.VerifactuTipoResultado.IdResultado` — MEDIA (80/100)
- `dbo.DispAF_LINEADISPENSACION.CodResultado` ⇢ `dbo.VerifactuTipoResultado.IdResultado` — MEDIA (80/100)

## Validación pendiente

Las relaciones oficiales proceden de las claves externas declaradas en SQL Server.

Las relaciones probables son hipótesis técnicas y deben comprobarse con datos reales y conocimiento funcional de Farmatic.
