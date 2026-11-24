"""G8 contra la memoria real de G5: sin mocks, con una cadena de dos reglas."""

import pytest

pytest.importorskip("grupo_05_forward")

from grupo_05_forward.engine import ForwardEngine  # noqa: E402
from grupo_05_forward.io import parse_knowledge_base, working_memory_to_dict  # noqa: E402

from grupo_08_explainer import XAIExplainer  # noqa: E402

KB = {
    "meta": {"project_title": "Cadena G8", "version": "1.0", "author_group": "Grupo 8"},
    "attributes": [
        {"id": "promedio", "name": "Promedio", "type": "numeric", "range": [0.0, 3.0]},
        {"id": "nivel", "name": "Nivel", "type": "text"},
        {"id": "dictamen", "name": "Dictamen", "type": "text"},
    ],
    "rules": [
        {"id": "r_nivel", "description": "Nivel academico", "priority": 10,
         "conditions": [{"attribute_id": "promedio", "operator": ">=", "value": 2.0}],
         "conclusion": {"attribute_id": "nivel", "value": "Alto"},
         "explanation_template": "El promedio es alto."},
        {"id": "r_dictamen", "description": "Elegibilidad", "priority": 5,
         "conditions": [{"attribute_id": "nivel", "operator": "==", "value": "Alto"}],
         "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
         "explanation_template": "Un nivel alto es elegible."},
    ],
}


@pytest.fixture
def memoria():
    r = ForwardEngine(parse_knowledge_base(KB)).run_from_facts("sess_g8", {"promedio": 2.5})
    return working_memory_to_dict(r.working_memory)


def test_how_recursivo_sobre_memoria_real(memoria):
    how = XAIExplainer(KB).explain_how(memoria, "dictamen")
    assert how[0] == "Se determinó 'Elegible' debido a la regla r_dictamen."
    assert "Premisa 1: nivel == 'Alto' (Derivado por la regla r_nivel)" in how
    assert "  Se determinó 'Alto' debido a la regla r_nivel." in how
    assert "  Premisa 1: promedio >= 2.0 (Valor ingresado: 2.5)" in how


def test_traza_sobre_memoria_real(memoria):
    assert XAIExplainer(KB).explain_trace(memoria) == [
        "Paso 1: r_nivel agregó nivel = 'Alto'",
        "Paso 2: r_dictamen agregó dictamen = 'Elegible'",
    ]
