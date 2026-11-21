"""Suite completa de pruebas unitarias e integración del Grupo 3 (KBAuditor).

Ejecución desde la raíz del repositorio:

    python -m pytest grupo_03_auditor/tests -v
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from grupo_03_auditor import (
    CAT_CICLO,
    CAT_CONTRADICCION,
    CAT_ESQUEMA,
    CAT_INALCANZABLE,
    CAT_REDUNDANCIA,
    SEVERIDAD_ERROR,
    SEVERIDAD_WARNING,
    KBAuditor,
    ReporteAuditoria,
)

ROOT = Path(__file__).resolve().parents[2]
G3_EJEMPLOS = Path(__file__).resolve().parents[1] / "datos_ejemplo"
G1_EJEMPLO = ROOT / "grupo_01_questions" / "datos_ejemplo" / "conocimiento_dominio.sample.json"
G2_EJEMPLO = ROOT / "grupo_02_rules" / "datos_ejemplo" / "conocimiento_dominio.json"
G4_EJEMPLO = ROOT / "grupo_04_schema" / "ejemplos" / "conocimiento_dominio.json"


def _kb_base(rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Construye una base de conocimiento mínima válida para pruebas unitarias."""
    return {
        "meta": {
            "project_title": "Dominio académico de prueba",
            "version": "1.0",
            "author_group": "Grupo 3 - Tests",
        },
        "attributes": [
            {
                "id": "materia",
                "name": "Tipo de materia",
                "type": "categorical",
                "question": "¿Qué tipo de materia cursa?",
                "options": ["Obligatoria", "Electiva", "Trabajo de Graduacion"],
            },
            {
                "id": "promedio",
                "name": "Promedio académico",
                "type": "numeric",
                "question": "¿Cuál es su promedio?",
                "range": [0.0, 3.0],
            },
            {
                "id": "activo",
                "name": "Estudiante activo",
                "type": "boolean",
                "question": "¿Está matriculado actualmente?",
            },
            {
                "id": "dictamen",
                "name": "Dictamen final",
                "type": "categorical",
                "options": ["Elegible", "No elegible", "Revision"],
            },
        ],
        "rules": rules
        if rules is not None
        else [
            {
                "id": "r1",
                "description": "Elegible con promedio >= 2.0",
                "priority": 10,
                "conditions": [
                    {"attribute_id": "promedio", "operator": ">=", "value": 2.0}
                ],
                "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
                "explanation_template": "Cumple el promedio mínimo.",
            },
            {
                "id": "r2",
                "description": "No elegible con promedio < 2.0",
                "priority": 10,
                "conditions": [
                    {"attribute_id": "promedio", "operator": "<", "value": 2.0}
                ],
                "conclusion": {"attribute_id": "dictamen", "value": "No elegible"},
                "explanation_template": "No alcanza el promedio mínimo.",
            },
        ],
    }


def _regla(
    rid: str,
    conditions: list[dict[str, Any]],
    conclusion_attr: str = "dictamen",
    conclusion_val: Any = "Elegible",
    priority: int = 10,
) -> dict[str, Any]:
    return {
        "id": rid,
        "description": f"Regla {rid}",
        "priority": priority,
        "conditions": conditions,
        "conclusion": {"attribute_id": conclusion_attr, "value": conclusion_val},
        "explanation_template": f"Explicación de {rid}.",
    }


# ---------------------------------------------------------------------------
# 1. Casos normales (KB limpia y válida)
# ---------------------------------------------------------------------------


def test_kb_valida_desde_dict_sin_errores():
    auditor = KBAuditor.desde_dict(_kb_base())
    reporte = auditor.auditar()

    assert isinstance(reporte, ReporteAuditoria)
    assert reporte.es_valida is True
    assert reporte.estado == "VALIDA"
    assert reporte.hallazgos == []
    assert reporte.resumen["total_atributos"] == 4
    assert reporte.resumen["total_reglas"] == 2
    assert reporte.resumen["conteo_severidad"] == {"ERROR": 0, "WARNING": 0, "INFO": 0}


def test_kb_valida_desde_dict_en_modo_aislado_sin_schema_manager():
    auditor = KBAuditor(_kb_base(), usar_schema_manager=False)
    reporte = auditor.auditar()

    assert reporte.es_valida is True
    assert reporte.estado == "VALIDA"
    assert reporte.hallazgos == []


def test_ejemplo_valido_g3_pasa_auditoria_completa():
    ruta = G3_EJEMPLOS / "conocimiento_valido.json"
    auditor = KBAuditor.desde_archivo(ruta)
    reporte = auditor.auditar()

    assert reporte.es_valida is True
    assert reporte.estado == "VALIDA"
    assert reporte.hallazgos == []
    assert reporte.resumen["total_reglas"] == 7
    assert reporte.resumen["total_atributos"] == 6


# ---------------------------------------------------------------------------
# 2. Datos inválidos, JSON malformado y entradas incompletas
# ---------------------------------------------------------------------------


def test_archivo_inexistente_devuelve_reporte_sin_excepcion(tmp_path):
    auditor = KBAuditor(tmp_path / "no_existe.json")
    reporte = auditor.auditar()

    assert reporte.es_valida is False
    assert reporte.estado == "INVALIDA"
    assert any(h.categoria == CAT_ESQUEMA and h.severidad == SEVERIDAD_ERROR for h in reporte.hallazgos)


def test_json_malformado_devuelve_hallazgo_controlado(tmp_path):
    ruta = tmp_path / "roto.json"
    ruta.write_text('{"meta": { "project_title": "X"', encoding="utf-8")

    reporte = KBAuditor(ruta).auditar()
    assert reporte.es_valida is False
    assert any(h.categoria == CAT_ESQUEMA for h in reporte.hallazgos)


def test_json_con_nan_rechazado_sin_excepcion(tmp_path):
    ruta = tmp_path / "nan.json"
    ruta.write_text('{"meta": {}, "attributes": [], "rules": [NaN]}', encoding="utf-8")

    reporte = KBAuditor(ruta).auditar()
    assert reporte.es_valida is False
    assert any(h.categoria == CAT_ESQUEMA for h in reporte.hallazgos)


@pytest.mark.parametrize("entrada", [[], "texto", 123, None])
def test_entradas_no_dict_no_lanzan_excepciones(entrada):
    auditor = KBAuditor()
    reporte = auditor.auditar(entrada)

    assert reporte.es_valida is False
    assert any(h.categoria == CAT_ESQUEMA for h in reporte.hallazgos)


def test_campos_faltantes_en_modo_aislado():
    kb_incompleta = {
        "meta": {"project_title": "Solo título"},
        "attributes": [{"id": "a1", "name": "A1", "type": "desconocido"}],
        "rules": [{"id": "r1"}],
    }
    reporte = KBAuditor(kb_incompleta, usar_schema_manager=False).auditar()

    assert reporte.es_valida is False
    errores_esquema = [h for h in reporte.hallazgos if h.categoria == CAT_ESQUEMA]
    assert len(errores_esquema) >= 3


# ---------------------------------------------------------------------------
# 3. Reglas contradictorias (conflictos)
# ---------------------------------------------------------------------------


def test_contradiccion_misma_prioridad_es_error():
    kb = _kb_base(
        rules=[
            _regla(
                "r1",
                [{"attribute_id": "promedio", "operator": ">=", "value": 2.0}],
                conclusion_val="Elegible",
                priority=10,
            ),
            _regla(
                "r2",
                [{"attribute_id": "promedio", "operator": "<=", "value": 2.5}],
                conclusion_val="No elegible",
                priority=10,
            ),
        ]
    )
    reporte = KBAuditor(kb).auditar()

    conflictos = [h for h in reporte.hallazgos if h.categoria == CAT_CONTRADICCION]
    assert len(conflictos) == 1
    assert conflictos[0].severidad == SEVERIDAD_ERROR
    assert conflictos[0].reglas == ["r1", "r2"]
    assert conflictos[0].detalles["empate_prioridad"] is True
    assert reporte.es_valida is False


def test_contradiccion_distinta_prioridad_es_warning():
    kb = _kb_base(
        rules=[
            _regla(
                "r_alta",
                [{"attribute_id": "promedio", "operator": ">=", "value": 2.0}],
                conclusion_val="Elegible",
                priority=30,
            ),
            _regla(
                "r_baja",
                [{"attribute_id": "promedio", "operator": "<=", "value": 2.5}],
                conclusion_val="No elegible",
                priority=10,
            ),
        ]
    )
    reporte = KBAuditor(kb).auditar()

    conflictos = [h for h in reporte.hallazgos if h.categoria == CAT_CONTRADICCION]
    assert len(conflictos) == 1
    assert conflictos[0].severidad == SEVERIDAD_WARNING
    assert conflictos[0].detalles["empate_prioridad"] is False
    assert reporte.es_valida is True
    assert reporte.estado == "CON_ADVERTENCIAS"


def test_contradiccion_frontera_numerica_cerrada_vs_abierta():
    # >= 2.0 y <= 2.0 se solapan exactamente en 2.0
    kb_solapa = _kb_base(
        rules=[
            _regla("r1", [{"attribute_id": "promedio", "operator": ">=", "value": 2.0}], conclusion_val="Elegible"),
            _regla("r2", [{"attribute_id": "promedio", "operator": "<=", "value": 2.0}], conclusion_val="No elegible"),
        ]
    )
    assert len(KBAuditor(kb_solapa).detectar_contradicciones()) == 1

    # > 2.0 y <= 2.0 son disjuntos
    kb_disjunto = _kb_base(
        rules=[
            _regla("r1", [{"attribute_id": "promedio", "operator": ">", "value": 2.0}], conclusion_val="Elegible"),
            _regla("r2", [{"attribute_id": "promedio", "operator": "<=", "value": 2.0}], conclusion_val="No elegible"),
        ]
    )
    assert len(KBAuditor(kb_disjunto).detectar_contradicciones()) == 0


def test_contradiccion_con_operador_in_y_desigualdad():
    kb = _kb_base(
        rules=[
            _regla(
                "r1",
                [{"attribute_id": "materia", "operator": "in", "value": ["Obligatoria", "Electiva"]}],
                conclusion_val="Elegible",
                priority=10,
            ),
            _regla(
                "r2",
                [{"attribute_id": "materia", "operator": "!=", "value": "Trabajo de Graduacion"}],
                conclusion_val="Revision",
                priority=10,
            ),
        ]
    )
    conflictos = KBAuditor(kb).detectar_contradicciones()
    assert len(conflictos) == 1
    assert conflictos[0].detalles["tipo"] == "equivalentes"
    assert conflictos[0].severidad == SEVERIDAD_ERROR


# ---------------------------------------------------------------------------
# 4. Reglas redundantes y subsumidas
# ---------------------------------------------------------------------------


def test_reglas_duplicadas_exactas_y_equivalentes():
    kb = _kb_base(
        rules=[
            _regla(
                "r1",
                [{"attribute_id": "materia", "operator": "!=", "value": "Trabajo de Graduacion"}],
                conclusion_val="Elegible",
            ),
            _regla(
                "r2",
                [{"attribute_id": "materia", "operator": "in", "value": ["Obligatoria", "Electiva"]}],
                conclusion_val="Elegible",
            ),
        ]
    )
    redundancias = KBAuditor(kb).detectar_redundancias()
    assert len(redundancias) == 1
    assert redundancias[0].categoria == CAT_REDUNDANCIA
    assert redundancias[0].detalles["tipo"] == "duplicada"


def test_regla_subsumida_en_ambos_ordenes():
    # r_general subsume a r_especifica (r_especifica es más restrictiva)
    r_general = _regla(
        "r_general",
        [{"attribute_id": "materia", "operator": "==", "value": "Obligatoria"}],
        conclusion_val="Elegible",
    )
    r_especifica = _regla(
        "r_especifica",
        [
            {"attribute_id": "materia", "operator": "==", "value": "Obligatoria"},
            {"attribute_id": "promedio", "operator": ">=", "value": 2.5},
        ],
        conclusion_val="Elegible",
    )

    for orden in ([r_general, r_especifica], [r_especifica, r_general]):
        redundancias = KBAuditor(_kb_base(rules=orden)).detectar_redundancias()
        assert len(redundancias) == 1
        assert redundancias[0].detalles["tipo"] == "subsumida"
        assert redundancias[0].detalles["regla_general"] == "r_general"
        assert redundancias[0].detalles["regla_redundante"] == "r_especifica"


# ---------------------------------------------------------------------------
# 5. Condiciones inalcanzables, reglas muertas y depends_on
# ---------------------------------------------------------------------------


def test_contradiccion_interna_numerica_y_categorica():
    kb = _kb_base(
        rules=[
            _regla(
                "r_num_imposible",
                [
                    {"attribute_id": "promedio", "operator": ">=", "value": 2.5},
                    {"attribute_id": "promedio", "operator": "<", "value": 2.0},
                ],
            ),
            _regla(
                "r_cat_imposible",
                [
                    {"attribute_id": "materia", "operator": "==", "value": "Obligatoria"},
                    {"attribute_id": "materia", "operator": "==", "value": "Electiva"},
                ],
            ),
        ]
    )
    hallazgos = KBAuditor(kb).detectar_condiciones_inalcanzables()
    reglas_muertas = {r for h in hallazgos if h.detalles.get("motivo") == "contradiccion_interna" for r in h.reglas}
    assert reglas_muertas == {"r_num_imposible", "r_cat_imposible"}


def test_in_lista_vacia_es_inalcanzable():
    kb = _kb_base(
        rules=[
            _regla("r_vacia", [{"attribute_id": "materia", "operator": "in", "value": []}])
        ]
    )
    hallazgos = KBAuditor(kb, usar_schema_manager=False).detectar_condiciones_inalcanzables()
    assert any(h.detalles.get("motivo") == "in_lista_vacia" and "r_vacia" in h.reglas for h in hallazgos)


def test_valores_fuera_de_rango_y_opciones_invalidas():
    kb = _kb_base(
        rules=[
            _regla("r_rango", [{"attribute_id": "promedio", "operator": ">", "value": 3.5}]),
            _regla("r_opcion", [{"attribute_id": "materia", "operator": "==", "value": "Inexistente"}]),
        ]
    )
    hallazgos = KBAuditor(kb, usar_schema_manager=False).detectar_condiciones_inalcanzables()
    motivos = {(h.reglas[0], h.detalles.get("motivo")) for h in hallazgos if h.reglas}
    assert ("r_rango", "fuera_de_rango") in motivos
    assert ("r_opcion", "opcion_invalida") in motivos


def test_opciones_categoricas_en_formato_objeto_value_label():
    kb = _kb_base(
        rules=[
            _regla("r_ok", [{"attribute_id": "nivel", "operator": "==", "value": "alto"}]),
            _regla("r_mal", [{"attribute_id": "nivel", "operator": "==", "value": "invalido"}]),
        ]
    )
    kb["attributes"].append(
        {
            "id": "nivel",
            "name": "Nivel",
            "type": "categorical",
            "question": "¿Nivel?",
            "options": [
                {"value": "bajo", "label": "Nivel Bajo"},
                {"value": "alto", "label": "Nivel Alto"},
            ],
        }
    )
    hallazgos = KBAuditor(kb, usar_schema_manager=False).detectar_condiciones_inalcanzables()
    assert not any("r_ok" in h.reglas for h in hallazgos)
    assert any("r_mal" in h.reglas and h.detalles.get("motivo") == "opcion_invalida" for h in hallazgos)


def test_atributo_inexistente_y_atributo_sin_question_ni_regla():
    kb = _kb_base(
        rules=[
            _regla("r_inexistente", [{"attribute_id": "fantasma", "operator": "==", "value": "x"}]),
            _regla("r_huerfano", [{"attribute_id": "sin_fuente", "operator": "==", "value": True}]),
        ]
    )
    kb["attributes"].append(
        {"id": "sin_fuente", "name": "Atributo huérfano", "type": "boolean"}
    )
    hallazgos = KBAuditor(kb, usar_schema_manager=False).detectar_condiciones_inalcanzables()
    motivos = {(h.reglas[0], h.detalles.get("motivo")) for h in hallazgos if h.reglas}
    assert ("r_inexistente", "atributo_inexistente") in motivos
    assert ("r_huerfano", "atributo_sin_fuente") in motivos
    # Las reglas muertas por atributos inexistentes/huérfanos no generan falsos conflictos
    assert KBAuditor(kb, usar_schema_manager=False).detectar_contradicciones() == []


def test_depends_on_inexistente_valor_imposible_y_ciclo():
    kb = _kb_base()
    kb["attributes"].extend(
        [
            {
                "id": "dep_rota",
                "name": "Depende de inexistente",
                "type": "text",
                "question": "¿Dato?",
                "depends_on": {"attribute_id": "no_existe", "operator": "==", "value": "A"},
            },
            {
                "id": "dep_imposible",
                "name": "Depende de opción imposible",
                "type": "text",
                "question": "¿Dato?",
                "depends_on": {"attribute_id": "materia", "operator": "==", "value": "NoExiste"},
            },
            {
                "id": "ciclo_1",
                "name": "Ciclo 1",
                "type": "boolean",
                "question": "¿C1?",
                "depends_on": {"attribute_id": "ciclo_2", "operator": "==", "value": True},
            },
            {
                "id": "ciclo_2",
                "name": "Ciclo 2",
                "type": "boolean",
                "question": "¿C2?",
                "depends_on": {"attribute_id": "ciclo_1", "operator": "==", "value": True},
            },
        ]
    )
    auditor = KBAuditor(kb, usar_schema_manager=False)
    inalc = auditor.detectar_condiciones_inalcanzables()
    ciclos = auditor.detectar_ciclos()

    assert any(h.detalles.get("motivo") == "depends_on_atributo_inexistente" for h in inalc)
    assert any(h.detalles.get("origen") == "depends_on" and h.detalles.get("motivo") == "opcion_invalida" for h in inalc)
    assert any(h.categoria == CAT_CICLO and h.detalles.get("origen") == "depends_on" for h in ciclos)


# ---------------------------------------------------------------------------
# 6. Detección de ciclos en reglas (directo, 2 reglas, 3+ reglas)
# ---------------------------------------------------------------------------


def test_ciclo_directo_una_regla():
    kb = _kb_base(
        rules=[
            _regla(
                "r_auto",
                [{"attribute_id": "dictamen", "operator": "==", "value": "Elegible"}],
                conclusion_attr="dictamen",
                conclusion_val="No elegible",
            )
        ]
    )
    ciclos = KBAuditor(kb).detectar_ciclos()
    assert len(ciclos) == 1
    assert ciclos[0].detalles["tipo"] == "directo"
    assert ciclos[0].reglas == ["r_auto"]
    assert "dictamen" in ciclos[0].atributos


def test_ciclos_indirectos_2_y_3_reglas_desde_ejemplo():
    ruta = G3_EJEMPLOS / "conocimiento_con_ciclos.json"
    reporte = KBAuditor(ruta).auditar()

    assert reporte.es_valida is False
    ciclos_reglas = [
        h for h in reporte.hallazgos
        if h.categoria == CAT_CICLO and h.detalles.get("origen") == "reglas"
    ]
    longitudes = sorted(h.detalles["longitud_reglas"] for h in ciclos_reglas)
    assert longitudes == [1, 2, 3]

    ciclos_dep = [
        h for h in reporte.hallazgos
        if h.categoria == CAT_CICLO and h.detalles.get("origen") == "depends_on"
    ]
    assert len(ciclos_dep) == 1


def test_cadena_aciclica_no_reporta_ciclos():
    kb = _kb_base(
        rules=[
            _regla(
                "r_paso1",
                [{"attribute_id": "promedio", "operator": ">=", "value": 2.0}],
                conclusion_attr="paso_intermedio",
                conclusion_val="OK",
            ),
            _regla(
                "r_paso2",
                [{"attribute_id": "paso_intermedio", "operator": "==", "value": "OK"}],
                conclusion_attr="dictamen",
                conclusion_val="Elegible",
            ),
        ]
    )
    kb["attributes"].append(
        {
            "id": "paso_intermedio",
            "name": "Paso intermedio",
            "type": "categorical",
            "options": ["OK", "FAIL"],
        }
    )
    reporte = KBAuditor(kb).auditar()
    assert reporte.es_valida is True
    assert not any(h.categoria == CAT_CICLO for h in reporte.hallazgos)


# ---------------------------------------------------------------------------
# 7. Tabla de Decisión y exportación de reportes (JSON y Markdown)
# ---------------------------------------------------------------------------


def test_tabla_decision_y_exportacion_json_markdown(tmp_path):
    ruta = G3_EJEMPLOS / "conocimiento_con_errores.json"
    auditor = KBAuditor(ruta)
    reporte = auditor.auditar()

    assert reporte.es_valida is False
    tabla = reporte.tabla_decision
    assert len(tabla["filas"]) == 10
    assert "promedio" in tabla["atributos_condicion"]
    assert "modalidad" in tabla["atributos_condicion"]

    estados_por_regla = {f["regla_id"]: f["estado"] for f in tabla["filas"]}
    assert "CONFLICTO" in estados_por_regla["regla_conflicto_1"]
    assert "REDUNDANTE" in estados_por_regla["regla_duplicada"]
    assert "REDUNDANTE" in estados_por_regla["regla_subsumida"]
    assert "INALCANZABLE" in estados_por_regla["regla_contradiccion_interna"]

    md_tabla = auditor.exportar_tabla_decision_markdown(tabla)
    consola_tabla = auditor.exportar_tabla_decision_consola(tabla)
    assert "| Regla | Prioridad |" in md_tabla
    assert "regla_conflicto_1" in consola_tabla

    out_json = tmp_path / "reporte.json"
    out_md = tmp_path / "reporte.md"
    json_str = auditor.exportar_json(out_json, reporte=reporte)
    md_str = auditor.exportar_markdown(out_md, reporte=reporte)

    assert out_json.exists()
    assert out_md.exists()
    cargado = json.loads(json_str)
    assert cargado["es_valida"] is False
    assert cargado["resumen"]["total_reglas"] == 10
    assert "## Tabla de Decisión" in md_str
    assert "regla_conflicto_1" in md_str


# ---------------------------------------------------------------------------
# 8. Compatibilidad con ejemplos reales de G1, G2 y G4 en el repositorio
# ---------------------------------------------------------------------------


def test_compatibilidad_ejemplo_oficial_grupo_04():
    assert G4_EJEMPLO.exists()
    reporte = KBAuditor(G4_EJEMPLO).auditar()
    assert reporte.es_valida is True
    assert reporte.estado == "VALIDA"
    assert reporte.hallazgos == []
    assert reporte.resumen["total_reglas"] == 10


def test_compatibilidad_ejemplo_oficial_grupo_02():
    assert G2_EJEMPLO.exists()
    reporte = KBAuditor(G2_EJEMPLO).auditar()
    assert reporte.es_valida is True
    assert reporte.estado == "VALIDA"
    assert reporte.hallazgos == []


def test_compatibilidad_ejemplo_borrador_grupo_01():
    assert G1_EJEMPLO.exists()
    # El borrador de G1 tiene rules: [], por lo que SchemaManager reporta error de esquema,
    # pero KBAuditor debe manejarlo sin excepciones.
    reporte = KBAuditor(G1_EJEMPLO).auditar()
    assert reporte.es_valida is False
    assert any(h.categoria == CAT_ESQUEMA for h in reporte.hallazgos)
    assert reporte.resumen["total_atributos"] == 3
    assert reporte.resumen["total_reglas"] == 0
