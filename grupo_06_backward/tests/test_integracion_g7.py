"""Integracion del BackwardEngine (G6) con G7 (factores de certeza) y G8.

G6 deja los hechos derivados con certainty_factor 1.0; G7 los recalcula sobre la
misma memoria. Se omiten si el modulo del otro grupo no esta disponible.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from grupo_06_backward import BackwardEngine

EJEMPLO = Path(__file__).resolve().parents[1] / "datos_ejemplo" / "conocimiento_encadenado.json"
RESPUESTAS = {"materia": "Trabajo de Graduacion", "promedio": 2.5, "creditos": 150}


@pytest.fixture(scope="module")
def kb():
    with EJEMPLO.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def memoria_g6(kb):
    return BackwardEngine(kb, lambda q: RESPUESTAS[q.attribute_id]).prove(
        "dictamen", session_id="sess_g6_g7").memory


def motor_g7(kb):
    g7 = pytest.importorskip("grupo_07_uncertainty")
    return g7.UncertaintyEngine(
        kb, rule_cfs={"rule_01": 0.8, "rule_04": 0.9}, fact_cfs={"promedio": 0.9})


def test_g7_recalcula_los_fc_sobre_la_memoria_de_g6(kb, memoria_g6):
    motor = motor_g7(kb)
    evaluada = motor.evaluate(memoria_g6)

    # requisitos: 0.9 (regla) x 1.0 (creditos); dictamen: 0.8 x min(1.0, 0.9, 0.9)
    assert evaluada["derived_facts"]["requisitos"]["certainty_factor"] == pytest.approx(0.9)
    assert evaluada["derived_facts"]["dictamen"]["certainty_factor"] == pytest.approx(0.72)
    assert motor.certainty_score(memoria_g6, "dictamen") == pytest.approx(0.72)
    assert memoria_g6["derived_facts"]["dictamen"]["certainty_factor"] == 1.0  # no se modifica


def test_g8_muestra_el_fc_que_calculo_g7_en_el_how(kb, memoria_g6):
    explicador = pytest.importorskip("grupo_08_explainer").XAIExplainer(kb)
    evaluada = motor_g7(kb).evaluate(memoria_g6)

    how = explicador.explain_how(evaluada, "dictamen")
    assert "FC = 0.72" in how[0]
