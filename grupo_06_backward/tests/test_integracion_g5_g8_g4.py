"""Integracion del BackwardEngine (G6) con G5, G8 y G4.

- G5: ambos motores deben llegar al mismo dictamen con los mismos datos.
- G8: el XAIExplainer explica HOW y WHY a partir de lo que deja G6.
- G4: la memoria de trabajo y el dictamen cumplen los contratos JSON.

Cada prueba se omite si el modulo del otro grupo no esta disponible.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from grupo_06_backward import BackwardEngine

EJEMPLO = Path(__file__).resolve().parents[1] / "datos_ejemplo" / "conocimiento_encadenado.json"
CONTRATOS = _REPO_ROOT / "contracts"

MATERIAS = ["Obligatoria", "Electiva", "Trabajo de Graduacion"]
PROMEDIOS = [1.5, 2.0, 2.5]
CREDITOS = [100, 140, 150]


@pytest.fixture(scope="module")
def kb():
    with EJEMPLO.open(encoding="utf-8") as handle:
        return json.load(handle)


def consulta_atras(kb, respuestas, session_id="sess_g6_0001"):
    """Corre G6 respondiendo desde un dict; devuelve (resultado, atributos preguntados)."""
    preguntados = []

    def ask(pregunta):
        preguntados.append(pregunta)
        return respuestas.get(pregunta.attribute_id)

    resultado = BackwardEngine(kb, ask).prove("dictamen", session_id=session_id)
    return resultado, preguntados


# --- G5: mismo resultado con los mismos datos ------------------------------------


@pytest.mark.parametrize("materia, promedio, creditos",
                         list(itertools.product(MATERIAS, PROMEDIOS, CREDITOS)))
def test_g5_y_g6_coinciden_en_el_dictamen_y_en_la_regla(kb, materia, promedio, creditos):
    g5 = pytest.importorskip("grupo_05_forward")
    hechos = {"materia": materia, "promedio": promedio, "creditos": creditos}

    adelante = g5.ForwardEngine(g5.parse_knowledge_base(kb)).run_from_facts("sess_g5", hechos)
    atras, _ = consulta_atras(kb, hechos)

    esperado = adelante.working_memory.derived_facts.get("dictamen")
    obtenido = atras.memory["derived_facts"].get("dictamen")
    assert (esperado is None) == (obtenido is None)
    if esperado is not None:
        assert obtenido["value"] == esperado.value
        assert obtenido["derived_by_rule"] == esperado.derived_by_rule


def test_g6_pregunta_menos_que_el_total_de_hechos_que_necesita_g5(kb):
    """Ventaja del encadenamiento hacia atras: no pide datos que no hacen falta."""
    atras, preguntados = consulta_atras(kb, {"materia": "Electiva", "promedio": 2.5, "creditos": 150})
    assert [p.attribute_id for p in preguntados] == ["materia"]
    assert atras.value == "Elegible"


def test_diferencia_conocida_con_g5_en_prioridades_entre_niveles():
    """Documenta el unico caso donde los motores pueden discrepar.

    G5 dispara siempre la regla de mayor prioridad *entre todas las activables*;
    G6 prueba por meta, de mayor a menor prioridad. Si una regla de baja prioridad
    ya es activable y la de alta prioridad necesita un hecho derivado antes, G5
    dispara primero la de baja y la de alta ya no puede sobrescribirla ("primera
    asercion gana"), mientras que G6 llega a la de alta. Hay que acordarlo con G5.
    """
    g5 = pytest.importorskip("grupo_05_forward")
    kb = {"attributes": [], "rules": [
        {"id": "rX", "priority": 1, "conditions": [{"attribute_id": "x", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "meta", "value": "por_X"}},
        {"id": "rY", "priority": 10, "conditions": [{"attribute_id": "req", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "meta", "value": "por_Y"}},
        {"id": "rZ", "priority": 0, "conditions": [{"attribute_id": "x", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "req", "value": 1}}]}
    adelante = g5.ForwardEngine(g5.parse_knowledge_base(kb)).run_from_facts("s", {"x": 1})
    atras = BackwardEngine(kb).prove(
        "meta", memory={"session_id": "s", "facts": {"x": 1}, "derived_facts": {}, "execution_trace": []})

    assert adelante.working_memory.known_value("meta") == "por_X"
    assert atras.value == "por_Y"


# --- G8: HOW y WHY ---------------------------------------------------------------


def test_g8_explica_how_sobre_la_memoria_de_g6(kb):
    explicador = pytest.importorskip("grupo_08_explainer").XAIExplainer(kb)
    atras, _ = consulta_atras(kb, {"materia": "Trabajo de Graduacion", "promedio": 2.5, "creditos": 150})

    how = explicador.explain_how(atras.memory, "dictamen")
    texto = "\n".join(how)
    assert "rule_01" in texto
    assert "rule_04" in texto  # la sub-meta 'requisitos' aparece anidada
    assert "Trabajo de Graduacion" in texto
    assert explicador.explain_trace(atras.memory)[0].startswith("Paso 1: rule_04")


def test_g8_explica_why_de_cada_pregunta_con_la_regla_que_informa_g6(kb):
    explicador = pytest.importorskip("grupo_08_explainer").XAIExplainer(kb)
    atras, preguntados = consulta_atras(
        kb, {"materia": "Trabajo de Graduacion", "promedio": 2.5, "creditos": 150})

    assert preguntados, "debio hacer preguntas"
    for pregunta in preguntados:
        why = explicador.explain_why(pregunta.attribute_id, pregunta.rule_id)
        assert pregunta.attribute_id in why and pregunta.rule_id in why

    creditos = next(p for p in preguntados if p.attribute_id == "creditos")
    assert "requisitos" in explicador.explain_why(creditos.attribute_id, creditos.rule_id)


# --- G4: contratos ---------------------------------------------------------------


def test_g4_valida_conocimiento_memoria_y_dictamen_de_g6(kb):
    esb_schema = pytest.importorskip("grupo_04_schema.esb_schema")
    pytest.importorskip("jsonschema")
    explicador = pytest.importorskip("grupo_08_explainer").XAIExplainer(kb)
    atras, preguntados = consulta_atras(
        kb, {"materia": "Trabajo de Graduacion", "promedio": 2.5, "creditos": 150})

    ultima = preguntados[-1]
    dictamen = {
        "session_id": atras.memory["session_id"],
        "final_outcome": atras.value,
        "certainty_score": atras.memory["derived_facts"]["dictamen"]["certainty_factor"],
        "explanation_how": explicador.explain_how(atras.memory, "dictamen"),
        "explanation_why": explicador.explain_why(ultima.attribute_id, ultima.rule_id),
    }
    gestor = esb_schema.SchemaManager(carpeta_esquemas=str(CONTRATOS))
    resultado = gestor.validar_conjunto(kb, atras.memory, dictamen, "dictamen")
    assert resultado["valido"] is True, resultado.get("errores")


def test_g4_valida_la_memoria_cuando_la_meta_no_se_cumple(kb):
    esb_schema = pytest.importorskip("grupo_04_schema.esb_schema")
    pytest.importorskip("jsonschema")
    atras, _ = consulta_atras(kb, {"materia": "Trabajo de Graduacion", "promedio": 2.5})  # sin creditos

    assert not atras.achieved
    gestor = esb_schema.SchemaManager(carpeta_esquemas=str(CONTRATOS))
    assert gestor.validar_traza(atras.memory, kb)["valido"] is True
