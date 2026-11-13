"""Pruebas del explicador con los contratos de referencia de la seccion 4.2."""

import copy

import pytest

from grupo_08_explainer import XAIExplainer

# Ejemplos de la seccion 4.2 de la guia (datos ficticios).
KB = {
    "rules": [
        {
            "id": "rule_01",
            "description": "Elegibilidad para un trámite",
            "priority": 10,
            "conditions": [
                {"attribute_id": "materia", "operator": "==", "value": "Trabajo de Graduacion"},
                {"attribute_id": "promedio", "operator": ">=", "value": 2.0},
            ],
            "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
            "explanation_template": "El promedio cumple el mínimo requerido.",
        }
    ]
}
WM = {
    "session_id": "sess_2026_10123",
    "facts": {"materia": "Trabajo de Graduacion", "promedio": 2.25},
    "derived_facts": {
        "dictamen": {"value": "Elegible", "derived_by_rule": "rule_01",
                     "certainty_factor": 1.0, "timestamp": "2026-10-23T10:15:00Z"}
    },
    "execution_trace": [{"step": 1, "rule_fired": "rule_01", "added_fact": "dictamen"}],
}


def test_how_reproduce_el_dictamen_de_referencia():
    lineas = XAIExplainer(KB).explain_how(WM, "dictamen")
    assert lineas[:3] == [
        "Se determinó 'Elegible' debido a la regla rule_01.",
        "Premisa 1: materia == 'Trabajo de Graduacion' (Verificado)",
        "Premisa 2: promedio >= 2.0 (Valor ingresado: 2.25)",
    ]
    assert lineas[3] == "El promedio cumple el mínimo requerido."


def test_how_de_un_dato_del_usuario():
    assert XAIExplainer(KB).explain_how(WM, "promedio") == [
        "'promedio' fue ingresado por el usuario: 2.25."]


def test_why_con_y_sin_regla_indicada():
    ex = XAIExplainer(KB)
    esperado = "Se solicitó 'promedio' para evaluar la condición de la regla rule_01"
    assert ex.explain_why("promedio", "rule_01").startswith(esperado)
    assert ex.explain_why("promedio").startswith(esperado)


def test_traza():
    assert XAIExplainer(KB).explain_trace(WM) == ["Paso 1: rule_01 agregó dictamen = 'Elegible'"]


def test_how_encadena_hechos_derivados_y_muestra_fc():
    kb = copy.deepcopy(KB)
    kb["rules"].append({
        "id": "rule_02", "priority": 5, "conditions": [
            {"attribute_id": "dictamen", "operator": "==", "value": "Elegible"}],
        "conclusion": {"attribute_id": "matricula", "value": "Autorizada"}})
    wm = copy.deepcopy(WM)
    wm["derived_facts"]["matricula"] = {"value": "Autorizada", "derived_by_rule": "rule_02",
                                        "certainty_factor": 0.8}
    lineas = XAIExplainer(kb).explain_how(wm, "matricula")
    assert lineas[0] == "Se determinó 'Autorizada' debido a la regla rule_02 (FC = 0.8)."
    assert lineas[1] == "Premisa 1: dictamen == 'Elegible' (Derivado por la regla rule_01)"
    assert lineas[2] == "  Se determinó 'Elegible' debido a la regla rule_01."


# Datos invalidos y reglas que no se activan.

def test_atributo_sin_valor_regla_no_activada():
    wm = copy.deepcopy(WM)
    wm["derived_facts"] = {}
    with pytest.raises(ValueError, match="no tiene valor"):
        XAIExplainer(KB).explain_how(wm, "dictamen")


def test_regla_inexistente():
    wm = copy.deepcopy(WM)
    wm["derived_facts"]["dictamen"]["derived_by_rule"] = "rule_99"
    with pytest.raises(ValueError, match="rule_99"):
        XAIExplainer(KB).explain_how(wm, "dictamen")
    with pytest.raises(ValueError, match="rule_99"):
        XAIExplainer(KB).explain_why("promedio", "rule_99")


def test_why_atributo_que_ninguna_regla_usa():
    with pytest.raises(ValueError, match="Ninguna regla"):
        XAIExplainer(KB).explain_why("edad")


def test_ciclo_en_derivacion():
    kb = {"rules": [{"id": "r_a", "conditions": [{"attribute_id": "b", "operator": "==", "value": 1}],
                     "conclusion": {"attribute_id": "a", "value": 1}},
                    {"id": "r_b", "conditions": [{"attribute_id": "a", "operator": "==", "value": 1}],
                     "conclusion": {"attribute_id": "b", "value": 1}}]}
    wm = {"facts": {}, "derived_facts": {"a": {"value": 1, "derived_by_rule": "r_a"},
                                         "b": {"value": 1, "derived_by_rule": "r_b"}}}
    with pytest.raises(ValueError, match="Ciclo"):
        XAIExplainer(kb).explain_how(wm, "a")
