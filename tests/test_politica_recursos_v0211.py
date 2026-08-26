import pytest

from politica_recursos import (
    ErrorPoliticaRecursos,
    EvaluacionRecursos,
    NivelRecurso,
    NivelTests,
    PoliticaRecursos,
    SolicitudRecursos,
    TipoTrabajo,
)


@pytest.mark.parametrize(
    "accion",
    [
        "CONSULTAR_ESTADO",
        "CONSULTAR_RESULTADO",
        "CONSULTAR_PRESUPUESTO",
        "CONSULTAR_CONSUMO",
        "GIT_STATUS",
        "GIT_BRANCH",
        "GIT_HEAD",
        "CALCULAR_SHA256",
        "COMPROBAR_HASH",
        "COMPROBAR_ARCHIVO",
        "LISTAR_ARCHIVOS",
        "VALIDAR_JSON",
        "PY_COMPILE",
        "EJECUTAR_TESTS",
        "ELIMINAR_TEMPORAL_AUTORIZADO",
        "CERRAR_RUN_ADMINISTRATIVO",
    ],
)
def test_acciones_deterministas_conocidas_son_local_only(accion):
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DETERMINISTA,
            accion=accion,
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.LOCAL_ONLY
    assert evaluacion.requiere_codex is False
    assert evaluacion.requiere_ok_pio_coste is False


def test_ejecutar_test_conocido_es_local_y_test_focal_por_defecto():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DETERMINISTA,
            accion="EJECUTAR_TESTS",
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.LOCAL_ONLY
    assert evaluacion.nivel_tests is NivelTests.TEST_FOCAL
    assert evaluacion.requiere_codex is False


def test_cambio_sencillo_un_archivo_es_codex_light_y_test_focal():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="MODIFICAR_CODIGO",
            archivos_afectados=1,
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.CODEX_LIGHT
    assert evaluacion.nivel_tests is NivelTests.TEST_FOCAL
    assert evaluacion.requiere_codex is True
    assert evaluacion.requiere_ok_pio_coste is False


def test_bug_multiarchivo_es_codex_standard_y_test_modulo():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DEBUG,
            accion="CORREGIR_BUG",
            archivos_afectados=3,
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.CODEX_STANDARD
    assert evaluacion.nivel_tests is NivelTests.TEST_MODULO
    assert evaluacion.requiere_codex is True


def test_refactor_transversal_es_heavy_suite_completa_y_requiere_ok_coste():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.REFACTOR,
            accion="REFACTOR_TRANSVERSAL",
            archivos_afectados=6,
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
            multiples_modulos=True,
            riesgo_transversal=True,
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.CODEX_HEAVY
    assert evaluacion.nivel_tests is NivelTests.SUITE_COMPLETA
    assert evaluacion.requiere_codex is True
    assert evaluacion.requiere_ok_pio_coste is True


def test_cierre_hito_fuerza_suite_completa_sin_forzar_codex():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DETERMINISTA,
            accion="GIT_STATUS",
            cierre_hito=True,
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.LOCAL_ONLY
    assert evaluacion.nivel_tests is NivelTests.SUITE_COMPLETA
    assert evaluacion.requiere_codex is False


def test_nivel_tests_explicito_prevalece():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="MODIFICAR_CODIGO",
            archivos_afectados=1,
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
            nivel_tests_explicito=NivelTests.TEST_MODULO,
        )
    )

    assert evaluacion.nivel_tests is NivelTests.TEST_MODULO


def test_accion_no_demostrada_como_local_escala_conservadoramente():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DETERMINISTA,
            accion="ACCION_DESCONOCIDA",
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.CODEX_LIGHT
    assert evaluacion.requiere_codex is True


def test_local_only_deja_de_ser_local_si_requiere_razonamiento():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DETERMINISTA,
            accion="GIT_STATUS",
            requiere_razonamiento=True,
        )
    )

    assert evaluacion.nivel_recurso is not NivelRecurso.LOCAL_ONLY
    assert evaluacion.requiere_codex is True


def test_archivos_afectados_rechaza_booleanos_y_negativos():
    with pytest.raises(ErrorPoliticaRecursos):
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="CAMBIO",
            archivos_afectados=True,
        )

    with pytest.raises(ErrorPoliticaRecursos):
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="CAMBIO",
            archivos_afectados=-1,
        )


def test_accion_vacia_se_rechaza():
    with pytest.raises(ErrorPoliticaRecursos):
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DETERMINISTA,
            accion="   ",
        )


def test_evaluacion_rechaza_incoherencia_codex():
    with pytest.raises(ErrorPoliticaRecursos):
        EvaluacionRecursos(
            nivel_recurso=NivelRecurso.LOCAL_ONLY,
            nivel_tests=None,
            requiere_codex=True,
            requiere_ok_pio_coste=False,
            motivos=("prueba",),
        )


def test_standard_selecciona_test_modulo_y_no_suite_completa():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="IMPLEMENTAR_MODULO",
            archivos_afectados=3,
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.CODEX_STANDARD
    assert evaluacion.nivel_tests is NivelTests.TEST_MODULO
    assert evaluacion.requiere_ok_pio_coste is False


def test_alcance_de_archivos_desconocido_no_se_rebaja_a_light():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="MODIFICAR_CODIGO",
            archivos_afectados=0,
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.CODEX_STANDARD
    assert evaluacion.nivel_tests is NivelTests.TEST_MODULO


def test_suite_completa_solo_aparece_con_motivo_representado():
    modulo = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="CAMBIO_MULTIARCHIVO",
            archivos_afectados=3,
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
            nivel_tests_anterior=NivelTests.TEST_FOCAL,
        )
    )
    explicita = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="CAMBIO_ACOTADO",
            archivos_afectados=1,
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
            nivel_tests_anterior=NivelTests.TEST_FOCAL,
            nivel_tests_explicito=NivelTests.SUITE_COMPLETA,
        )
    )

    assert modulo.nivel_tests is NivelTests.TEST_MODULO
    assert explicita.nivel_tests is NivelTests.SUITE_COMPLETA
    assert "explícitamente" in explicita.motivos[-1]


def test_heavy_requiere_ok_coste_sin_inventar_estimacion():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.AUDITORIA,
            accion="AUDITORIA_TRANSVERSAL",
            riesgo_transversal=True,
            multiples_modulos=True,
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.CODEX_HEAVY
    assert evaluacion.nivel_tests is NivelTests.SUITE_COMPLETA
    assert evaluacion.requiere_ok_pio_coste is True
    assert evaluacion.coste_estimado is None
    assert evaluacion.a_dict()["motivo_barrera_coste"]


def test_escalado_light_a_heavy_registra_niveles_y_motivo():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="CAMBIO_ESCALADO",
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
            riesgo_transversal=True,
            nivel_recurso_anterior=NivelRecurso.CODEX_LIGHT,
        )
    )

    assert evaluacion.requiere_ok_pio_coste is True
    assert evaluacion.nivel_recurso_anterior is NivelRecurso.CODEX_LIGHT
    assert evaluacion.motivo_escalado == "escalado de CODEX_LIGHT a CODEX_HEAVY"


def test_coste_superior_a_presupuesto_crea_barrera_sin_cambiar_nivel():
    evaluacion = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            tipo_trabajo=TipoTrabajo.DESARROLLO,
            accion="CAMBIO_ACOTADO",
            archivos_afectados=1,
            requiere_escritura_codigo=True,
            requiere_razonamiento=True,
            coste_estimado=4,
            presupuesto_disponible=3,
        )
    )

    assert evaluacion.nivel_recurso is NivelRecurso.CODEX_LIGHT
    assert evaluacion.requiere_ok_pio_coste is True
    assert evaluacion.coste_estimado == 4
    assert evaluacion.presupuesto_disponible == 3


def test_retry_full_run_costoso_requiere_ok_y_checkpoint_barato_no():
    comun = dict(
        tipo_trabajo=TipoTrabajo.DETERMINISTA,
        accion="REINTENTAR",
        retry=True,
        potencial_nuevo_coste=True,
    )
    full = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            **comun,
            estrategia_retry="RETRY_FULL_RUN",
            repite_trabajo=True,
        )
    )
    checkpoint = PoliticaRecursos.evaluar(
        SolicitudRecursos(
            **comun,
            estrategia_retry="RETRY_FROM_CHECKPOINT",
            repite_trabajo=False,
        )
    )

    assert full.requiere_ok_pio_coste is True
    assert checkpoint.requiere_ok_pio_coste is False
    assert full.a_dict()["coste_estimado"] is None
    assert "repite trabajo" in full.a_dict()["motivo_barrera_coste"]
