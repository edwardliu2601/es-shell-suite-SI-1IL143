"""Integracion real con ForwardEngine (G5), XAIExplainer (G8) y SchemaManager (G4).

No usa mocks: la memoria sale del motor de G5, G7 le calcula los FC, G8 los
muestra en el HOW y G4 valida el resultado contra los contratos. Se omite si
falta alguno de esos modulos o la libreria jsonschema.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("grupo_05_forward")
pytest.importorskip("grupo_08_explainer")

from grupo_04_schema.esb_schema import SchemaManager  # noqa: E402
from grupo_05_forward.engine import ForwardEngine  # noqa: E402
from grupo_05_forward.io import parse_knowledge_base, working_memory_to_dict  # noqa: E402
from grupo_07_uncertainty import UncertaintyEngine  # noqa: E402
from grupo_08_explainer import XAIExplainer  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
G4_KB = ROOT / "grupo_04_schema/ejemplos/conocimiento_dominio.json"


def inferir(kb, session_id, hechos):
    """Ejecuta G5 y devuelve la memoria como dict, tal como la guarda el contrato."""
    resultado = ForwardEngine(parse_knowledge_base(kb)).run_from_facts(session_id, hechos)
    return working_memory_to_dict(resultado.working_memory)


def test_recorrido_completo_g5_g7_g8_g4():
    kb = json.loads(G4_KB.read_text(encoding="utf-8"))
    memoria = inferir(kb, "sess_g7", {"tipo_consulta": "Calificacion", "puntaje_final": 85})
    assert memoria["derived_facts"]["dictamen"]["derived_by_rule"] == "reg_calificacion_b"

    motor = UncertaintyEngine(kb, rule_cfs={"reg_calificacion_b": 0.9})
    evaluada = motor.evaluate(memoria)
    assert evaluada["derived_facts"]["dictamen"]["certainty_factor"] == pytest.approx(0.9)

    # G4 acepta la memoria con los FC calculados por G7.
    assert SchemaManager().validar_traza(evaluada, kb) == {"valido": True, "errores": []}

    # G8 muestra el FC en la primera linea del HOW.
    explicador = XAIExplainer(kb)
    como = explicador.explain_how(evaluada, "dictamen")
    assert como[0].endswith("(FC = 0.9).")

    # El dictamen con certainty_score tambien pasa la validacion de G4.
    dictamen = {
        "session_id": "sess_g7",
        "final_outcome": evaluada["derived_facts"]["dictamen"]["value"],
        "explanation_how": como,
        "explanation_why": explicador.explain_why("puntaje_final", "reg_calificacion_b"),
    }
    completo = motor.complete_verdict(dictamen, memoria, "dictamen")
    assert completo["certainty_score"] == pytest.approx(0.9)
    assert SchemaManager().validar_dictamen(completo, evaluada, "dictamen")["valido"] is True


def test_sin_fc_la_memoria_de_g5_queda_con_fc_uno():
    kb = json.loads(G4_KB.read_text(encoding="utf-8"))
    memoria = inferir(kb, "sess_g7", {"tipo_consulta": "Calificacion", "puntaje_final": 85})
    evaluada = UncertaintyEngine(kb).evaluate(memoria)
    assert evaluada["derived_facts"]["dictamen"]["certainty_factor"] == 1.0


def test_g7_combina_la_regla_que_g5_no_registro():
    # G5 deja pasar una sola regla por atributo (la de mayor prioridad).
    # G7 suma la otra regla, que tambien respalda el mismo dictamen.
    kb = {
        "meta": {"project_title": "Prueba G7", "version": "1.0", "author_group": "Grupo 7"},
        "attributes": [{"id": "promedio", "name": "Promedio", "type": "numeric",
                        "range": [0.0, 3.0]}],
        "rules": [
            {"id": "rule_alta", "description": "Promedio alto", "priority": 10,
             "conditions": [{"attribute_id": "promedio", "operator": ">=", "value": 2.0}],
             "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
             "explanation_template": "El promedio supera 2.0."},
            {"id": "rule_media", "description": "Promedio medio", "priority": 5,
             "conditions": [{"attribute_id": "promedio", "operator": ">=", "value": 1.5}],
             "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
             "explanation_template": "El promedio supera 1.5."},
        ],
    }
    memoria = inferir(kb, "sess_g7_b", {"promedio": 2.25})
    assert memoria["derived_facts"]["dictamen"]["derived_by_rule"] == "rule_alta"
    assert [paso["rule_fired"] for paso in memoria["execution_trace"]] == ["rule_alta"]

    motor = UncertaintyEngine(kb, rule_cfs={"rule_alta": 0.6, "rule_media": 0.5})
    evaluada = motor.evaluate(memoria)
    assert evaluada["derived_facts"]["dictamen"]["certainty_factor"] == pytest.approx(0.8)
    assert SchemaManager().validar_traza(evaluada, kb)["valido"] is True
