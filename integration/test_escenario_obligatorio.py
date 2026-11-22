"""Prueba end-to-end del escenario obligatorio de la seccion 6 de la guia.

Ejercita juntos G1 (atributos), G4 (schema), G5 (forward engine) y G8 (XAI).
Reproduce el ejemplo minimo de la seccion 4.2: elegibilidad para trabajo de
graduacion segun promedio.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# --- Base de conocimiento del escenario (seccion 4.2 de la guia) ---

BASE_CONOCIMIENTO = {
    "meta": {
        "project_title": "Prueba E2E - Escenario obligatorio",
        "version": "1.0",
        "author_group": "Grupo 1 - integracion",
    },
    "attributes": [
        {
            "id": "materia",
            "name": "Tipo de Asignatura Solicitada",
            "type": "categorical",
            "question": "Seleccione el tipo de asignatura que desea matricular:",
            "options": ["Obligatoria", "Electiva", "Trabajo de Graduacion"],
        },
        {
            "id": "promedio",
            "name": "Promedio Ponderado Acumulado",
            "type": "numeric",
            "question": "Cual es el promedio ponderado del estudiante?",
            "range": [0.0, 3.0],
        },
        {
            "id": "dictamen",
            "name": "Dictamen de elegibilidad",
            "type": "text",
        },
    ],
    "rules": [
        {
            "id": "rule_01",
            "description": "Elegibilidad para un tramite",
            "priority": 10,
            "conditions": [
                {"attribute_id": "materia", "operator": "==",
                 "value": "Trabajo de Graduacion"},
                {"attribute_id": "promedio", "operator": ">=", "value": 2.0},
            ],
            "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
            "explanation_template": "El promedio cumple el minimo requerido.",
        }
    ],
}


# --- Paso 1: el editor del Grupo 1 define los atributos ---

def test_paso_1_g1_crea_los_atributos_del_dominio():
    """G1: el QuestionEditor construye los atributos y los serializa."""
    from grupo_01_questions import Attribute, QuestionEditor

    editor = QuestionEditor()
    for datos in BASE_CONOCIMIENTO["attributes"]:
        editor.add_attribute(Attribute.from_dict(datos))

    assert len(editor.list_attributes()) == 3
    assert editor.get_attribute("promedio").range == [0.0, 3.0]
    assert "Trabajo de Graduacion" in editor.get_attribute("materia").options


# --- Paso 2: el SchemaManager del Grupo 4 valida el contrato ---

def test_paso_2_g4_valida_el_contrato_completo():
    """G4: el SchemaManager acepta la base de conocimiento del escenario."""
    try:
        from grupo_04_schema.esb_schema import SchemaManager
    except ImportError:
        pytest.skip("SchemaManager del Grupo 4 todavia no esta integrado.")

    carpeta_schemas = Path(__file__).resolve().parents[1] / "contracts"
    gestor = SchemaManager(carpeta_esquemas=str(carpeta_schemas))
    resultado = gestor.validar_datos(BASE_CONOCIMIENTO, "conocimiento_dominio")
    assert resultado["valido"] is True, resultado.get("errores")


# --- Pasos 3 a 5: el ForwardEngine del Grupo 5 infiere y traza ---

@pytest.fixture
def resultado_inferencia():
    """Ejecuta el motor forward con los hechos del escenario obligatorio."""
    from grupo_05_forward.engine import ForwardEngine
    from grupo_05_forward.io import parse_knowledge_base

    kb = parse_knowledge_base(BASE_CONOCIMIENTO)
    motor = ForwardEngine(kb)
    resultado = motor.run_from_facts(
        session_id="sess_e2e_0001",
        facts={"materia": "Trabajo de Graduacion", "promedio": 2.25},
    )
    return resultado


def test_paso_3_la_memoria_registra_los_hechos_del_usuario(resultado_inferencia):
    memoria = resultado_inferencia.working_memory
    assert memoria.known_value("materia") == "Trabajo de Graduacion"
    assert memoria.known_value("promedio") == 2.25


def test_paso_4_la_regla_dispara_y_deriva_el_dictamen(resultado_inferencia):
    memoria = resultado_inferencia.working_memory
    assert memoria.known_value("dictamen") == "Elegible"
    assert "dictamen" in memoria.derived_facts
    assert memoria.derived_facts["dictamen"].derived_by_rule == "rule_01"


def test_paso_5_la_traza_identifica_la_regla_aplicada(resultado_inferencia):
    traza = resultado_inferencia.working_memory.execution_trace
    assert len(traza) >= 1
    assert any(paso.rule_fired == "rule_01" for paso in traza)
    assert any(paso.added_fact == "dictamen" for paso in traza)


# --- Paso 6: el XAIExplainer del Grupo 8 responde HOW y WHY ---

def test_paso_6_g8_produce_explicacion_how_y_why(resultado_inferencia):
    """G8: a partir de la memoria, genera explanation_how y explanation_why."""
    from grupo_05_forward.io import working_memory_to_dict
    from grupo_08_explainer import XAIExplainer

    memoria_dict = working_memory_to_dict(resultado_inferencia.working_memory)
    explicador = XAIExplainer(BASE_CONOCIMIENTO)

    how = explicador.explain_how(memoria_dict, "dictamen")
    assert len(how) >= 2, "explanation_how debe tener al menos la conclusion y una premisa"
    assert any("rule_01" in linea for linea in how)
    assert any("Trabajo de Graduacion" in linea for linea in how)

    why = explicador.explain_why("promedio", rule_id="rule_01")
    assert "promedio" in why
    assert "rule_01" in why


# --- Paso 7: dictamen final armado desde todas las piezas ---

def test_paso_7_dictamen_final_coincide_con_el_contrato(resultado_inferencia):
    """Arma el dictamen_salida.json con los resultados de G5 y G8."""
    from grupo_05_forward.io import working_memory_to_dict
    from grupo_08_explainer import XAIExplainer

    memoria_dict = working_memory_to_dict(resultado_inferencia.working_memory)
    explicador = XAIExplainer(BASE_CONOCIMIENTO)

    dictamen = {
        "session_id": memoria_dict["session_id"],
        "final_outcome": resultado_inferencia.working_memory.known_value("dictamen"),
        "explanation_how": explicador.explain_how(memoria_dict, "dictamen"),
        "explanation_why": explicador.explain_why("promedio", rule_id="rule_01"),
    }

    assert dictamen["final_outcome"] == "Elegible"
    assert isinstance(dictamen["explanation_how"], list)
    assert isinstance(dictamen["explanation_why"], str)

    # Serializable como JSON (requisito del contrato dictamen_salida.json).
    json.dumps(dictamen, ensure_ascii=False)


# --- Paso 8 (opcional): el SchemaManager valida el dictamen final ---

def test_paso_8_g4_valida_el_dictamen_final(resultado_inferencia):
    """G4: el dictamen producido cumple el schema dictamen_salida.schema.json."""
    try:
        from grupo_04_schema.esb_schema import SchemaManager
    except ImportError:
        pytest.skip("SchemaManager del Grupo 4 todavia no esta integrado.")

    from grupo_05_forward.io import working_memory_to_dict
    from grupo_08_explainer import XAIExplainer

    memoria_dict = working_memory_to_dict(resultado_inferencia.working_memory)
    explicador = XAIExplainer(BASE_CONOCIMIENTO)

    dictamen = {
        "session_id": memoria_dict["session_id"],
        "final_outcome": resultado_inferencia.working_memory.known_value("dictamen"),
        "explanation_how": explicador.explain_how(memoria_dict, "dictamen"),
        "explanation_why": explicador.explain_why("promedio", rule_id="rule_01"),
    }

    carpeta_schemas = Path(__file__).resolve().parents[1] / "contracts"
    gestor = SchemaManager(carpeta_esquemas=str(carpeta_schemas))
    resultado = gestor.validar_datos(dictamen, "dictamen_salida")
    assert resultado["valido"] is True, resultado.get("errores")
