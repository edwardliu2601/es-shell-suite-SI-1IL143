"""Pruebas del motor de incertidumbre con los contratos de referencia de la seccion 4.2."""

import copy
import itertools
import json
import math

import pytest

from grupo_07_uncertainty import (
    UncertaintyEngine,
    UncertaintyError,
    combine_all,
    combine_evidence,
    combine_premises,
    propagate,
    validate_cf,
)

# Ejemplos de la seccion 4.2 de la guia (datos ficticios).
KB = {
    "meta": {"project_title": "Evaluacion academica", "version": "1.0", "author_group": "Grupo 4"},
    "attributes": [
        {"id": "promedio", "name": "Promedio", "type": "numeric", "range": [0.0, 3.0]},
        {"id": "materia", "name": "Materia", "type": "categorical",
         "options": ["Obligatoria", "Electiva", "Trabajo de Graduacion"]},
    ],
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
    ],
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
VERDICT = {
    "session_id": "sess_2026_10123",
    "final_outcome": "Elegible",
    "certainty_score": 1.0,
    "explanation_how": ["Se determinó 'Elegible' debido a la regla rule_01."],
    "explanation_why": "Se solicitó 'promedio' para evaluar la condición de la regla rule_01.",
}


def regla(rule_id, conditions, attribute_id, value):
    return {
        "id": rule_id,
        "description": f"Regla {rule_id}",
        "priority": 10,
        "conditions": [{"attribute_id": a, "operator": "==", "value": v} for a, v in conditions],
        "conclusion": {"attribute_id": attribute_id, "value": value},
        "explanation_template": "",
    }


def memoria(facts, derivados):
    """Memoria de trabajo con hechos derivados dados como [(atributo, valor, regla), ...]."""
    return {
        "session_id": "sess_prueba",
        "facts": facts,
        "derived_facts": {a: {"value": v, "derived_by_rule": r} for a, v, r in derivados},
        "execution_trace": [
            {"step": i, "rule_fired": r, "added_fact": a}
            for i, (a, _, r) in enumerate(derivados, 1)
        ],
    }


def cf_derivado(motor, wm, atributo="dictamen"):
    return motor.evaluate(wm)["derived_facts"][atributo]["certainty_factor"]


# --- Funciones puras ---


@pytest.mark.parametrize("valor", [-1, -1.0, 0, 0.5, 1, 1.0])
def test_validate_cf_acepta_el_rango_completo(valor):
    assert validate_cf(valor) == float(valor)


@pytest.mark.parametrize("valor", [1.01, -1.5, 2, math.nan, math.inf, -math.inf, True, "0.5", None])
def test_validate_cf_rechaza_valores_invalidos(valor):
    with pytest.raises(UncertaintyError):
        validate_cf(valor)


def test_combine_premises_toma_el_menor():
    assert combine_premises([0.9, 0.4, 1.0]) == 0.4
    assert combine_premises([-0.2, 0.7]) == -0.2


def test_combine_premises_sin_premisas_falla():
    with pytest.raises(UncertaintyError):
        combine_premises([])


def test_propagate_multiplica():
    assert propagate(0.8, 0.5) == pytest.approx(0.4)
    assert propagate(-0.6, 0.5) == pytest.approx(-0.3)
    assert propagate(1.0, 1.0) == 1.0
    assert propagate(0.0, 0.9) == 0.0


def test_combine_evidence_mismo_signo():
    assert combine_evidence(0.6, 0.5) == pytest.approx(0.8)
    assert combine_evidence(-0.6, -0.5) == pytest.approx(-0.8)


def test_combine_evidence_signos_distintos():
    assert combine_evidence(0.8, -0.6) == pytest.approx(0.5)
    assert combine_evidence(-0.6, 0.8) == pytest.approx(0.5)


def test_combine_evidence_cero_es_neutro_y_uno_absorbe():
    for cf in (-1.0, -0.3, 0.0, 0.7, 1.0):
        assert combine_evidence(0.0, cf) == pytest.approx(cf)
    assert combine_evidence(1.0, 0.5) == 1.0
    assert combine_evidence(-1.0, -0.5) == -1.0


def test_combine_evidence_certeza_total_opuesta_da_cero():
    assert combine_evidence(1.0, -1.0) == 0.0
    assert combine_evidence(-1.0, 1.0) == 0.0


GRILLA = [-1.0, -0.8, -0.5, -0.2, 0.0, 0.3, 0.6, 0.9, 1.0]


def test_combine_evidence_es_conmutativa_y_queda_en_rango():
    for a, b in itertools.product(GRILLA, repeat=2):
        resultado = combine_evidence(a, b)
        assert resultado == pytest.approx(combine_evidence(b, a))
        assert -1.0 <= resultado <= 1.0


def test_combine_evidence_es_asociativa_salvo_el_caso_singular():
    for a, b, c in itertools.product([-0.8, -0.3, 0.2, 0.6, 0.9], repeat=3):
        izquierda = combine_evidence(combine_evidence(a, b), c)
        derecha = combine_evidence(a, combine_evidence(b, c))
        assert izquierda == pytest.approx(derecha, abs=1e-5)


def test_combine_all():
    assert combine_all([]) == 0.0
    assert combine_all([0.7]) == 0.7
    # El orden solo cambia el ultimo decimal por el redondeo a 6 cifras.
    assert combine_all([0.6, 0.5, -0.3]) == pytest.approx(0.714286, abs=1e-5)
    assert combine_all([-0.3, 0.6, 0.5]) == pytest.approx(0.714286, abs=1e-5)


# --- Motor sobre el ejemplo de la seccion 4.2 ---


def test_sin_fc_el_resultado_coincide_con_el_ejemplo_de_la_guia():
    motor = UncertaintyEngine(KB)
    assert cf_derivado(motor, WM) == 1.0
    assert motor.certainty_score(WM, "dictamen") == 1.0


def test_fc_de_regla():
    motor = UncertaintyEngine(KB, rule_cfs={"rule_01": 0.8})
    assert cf_derivado(motor, WM) == pytest.approx(0.8)


def test_fc_de_un_dato_del_usuario_entra_como_premisa():
    motor = UncertaintyEngine(KB, rule_cfs={"rule_01": 0.8}, fact_cfs={"promedio": 0.9})
    assert cf_derivado(motor, WM) == pytest.approx(0.72)  # 0.8 * min(1.0, 0.9)


def test_default_cf_aplica_a_reglas_y_datos_sin_valor_propio():
    motor = UncertaintyEngine(KB, default_cf=0.9)
    assert cf_derivado(motor, WM) == pytest.approx(0.81)  # 0.9 * min(0.9, 0.9)


def test_evaluate_no_modifica_la_memoria_recibida_y_conserva_los_demas_campos():
    original = copy.deepcopy(WM)
    resultado = UncertaintyEngine(KB, rule_cfs={"rule_01": 0.5}).evaluate(WM)
    assert WM == original
    entrada = resultado["derived_facts"]["dictamen"]
    assert entrada["certainty_factor"] == pytest.approx(0.5)
    assert entrada["timestamp"] == "2026-10-23T10:15:00Z"
    assert resultado["facts"] == WM["facts"]
    assert resultado["execution_trace"] == WM["execution_trace"]


def test_evaluate_es_idempotente_e_ignora_el_fc_previo():
    motor = UncertaintyEngine(KB, rule_cfs={"rule_01": 0.5})
    una_vez = motor.evaluate(WM)
    assert motor.evaluate(una_vez) == una_vez


def test_la_salida_es_json_y_respeta_el_rango():
    resultado = UncertaintyEngine(KB, rule_cfs={"rule_01": -0.4}).evaluate(WM)
    json.dumps(resultado)
    assert -1.0 <= resultado["derived_facts"]["dictamen"]["certainty_factor"] <= 1.0


def test_memoria_sin_hechos_derivados_queda_igual():
    vacia = {"session_id": "s", "facts": {"promedio": 1.0}, "derived_facts": {},
             "execution_trace": []}
    assert UncertaintyEngine(KB).evaluate(vacia) == vacia


def test_complete_verdict_agrega_certainty_score_sin_tocar_el_original():
    motor = UncertaintyEngine(KB, rule_cfs={"rule_01": 0.6})
    original = copy.deepcopy(VERDICT)
    completo = motor.complete_verdict(VERDICT, WM, "dictamen")
    assert completo["certainty_score"] == pytest.approx(0.6)
    assert VERDICT == original
    assert completo["final_outcome"] == "Elegible"


# --- Umbral de activacion ---


def test_premisa_en_el_umbral_no_activa_la_regla():
    motor = UncertaintyEngine(KB, fact_cfs={"promedio": 0.2})
    assert cf_derivado(motor, WM) == 0.0


def test_premisa_sobre_el_umbral_si_activa_la_regla():
    motor = UncertaintyEngine(KB, fact_cfs={"promedio": 0.21})
    assert cf_derivado(motor, WM) == pytest.approx(0.21)


def test_umbral_configurable():
    motor = UncertaintyEngine(KB, fact_cfs={"promedio": 0.1}, threshold=0.0)
    assert cf_derivado(motor, WM) == pytest.approx(0.1)


# --- Cadenas de reglas ---

KB_CADENA = {
    "attributes": [{"id": "a", "name": "A", "type": "text"}],
    "rules": [
        regla("r1", [("a", "x")], "b", "y"),
        regla("r2", [("b", "y")], "c", "z"),
    ],
}


def test_cadena_de_dos_reglas_propaga_el_fc_del_hecho_derivado():
    wm = memoria({"a": "x"}, [("b", "y", "r1"), ("c", "z", "r2")])
    motor = UncertaintyEngine(KB_CADENA, rule_cfs={"r1": 0.9, "r2": 0.8}, fact_cfs={"a": 0.5})
    resultado = motor.evaluate(wm)["derived_facts"]
    assert resultado["b"]["certainty_factor"] == pytest.approx(0.45)  # 0.9 * 0.5
    assert resultado["c"]["certainty_factor"] == pytest.approx(0.36)  # 0.8 * 0.45


def test_un_hecho_derivado_con_fc_bajo_apaga_la_regla_siguiente():
    wm = memoria({"a": "x"}, [("b", "y", "r1"), ("c", "z", "r2")])
    motor = UncertaintyEngine(KB_CADENA, rule_cfs={"r1": 0.3}, fact_cfs={"a": 0.5})
    resultado = motor.evaluate(wm)["derived_facts"]
    assert resultado["b"]["certainty_factor"] == pytest.approx(0.15)
    assert resultado["c"]["certainty_factor"] == 0.0  # 0.15 no supera el umbral de 0.2


# --- Reglas que llegan a la misma conclusion ---


def kb_dos_reglas(valor_b="Elegible"):
    return {
        "attributes": [{"id": "x", "name": "X", "type": "text"}],
        "rules": [
            regla("rule_a", [("x", "1")], "dictamen", "Elegible"),
            regla("rule_b", [("x", "1")], "dictamen", valor_b),
        ],
    }


WM_DOS_REGLAS = memoria({"x": "1"}, [("dictamen", "Elegible", "rule_a")])


def test_dos_reglas_con_la_misma_conclusion_se_combinan():
    motor = UncertaintyEngine(kb_dos_reglas(), rule_cfs={"rule_a": 0.6, "rule_b": 0.5})
    assert cf_derivado(motor, WM_DOS_REGLAS) == pytest.approx(0.8)


def test_combinar_reglas_equivalentes_se_puede_apagar():
    motor = UncertaintyEngine(
        kb_dos_reglas(), rule_cfs={"rule_a": 0.6, "rule_b": 0.5}, combine_equivalent_rules=False
    )
    assert cf_derivado(motor, WM_DOS_REGLAS) == pytest.approx(0.6)


def test_una_regla_con_fc_negativo_resta_evidencia():
    motor = UncertaintyEngine(kb_dos_reglas(), rule_cfs={"rule_a": 0.8, "rule_b": -0.6})
    assert cf_derivado(motor, WM_DOS_REGLAS) == pytest.approx(0.5)


def test_la_regla_con_otro_valor_no_suma():
    motor = UncertaintyEngine(
        kb_dos_reglas(valor_b="No elegible"), rule_cfs={"rule_a": 0.6, "rule_b": 0.5}
    )
    assert cf_derivado(motor, WM_DOS_REGLAS) == pytest.approx(0.6)


def test_la_regla_con_condiciones_falsas_no_suma():
    kb = kb_dos_reglas()
    kb["rules"][1]["conditions"][0]["value"] = "2"  # x == "2" no se cumple
    motor = UncertaintyEngine(kb, rule_cfs={"rule_a": 0.6, "rule_b": 0.5})
    assert cf_derivado(motor, WM_DOS_REGLAS) == pytest.approx(0.6)


def test_la_regla_con_premisa_derivada_despues_no_suma():
    # rule_c concluye x = "v" pero depende de y, que se derivo despues de x:
    # el motor no pudo dispararla en ese momento.
    kb = {
        "attributes": [{"id": "a", "name": "A", "type": "text"}],
        "rules": [
            regla("r1", [("a", "1")], "x", "v"),
            regla("r2", [("a", "1")], "y", "w"),
            regla("rule_c", [("y", "w")], "x", "v"),
        ],
    }
    wm = memoria({"a": "1"}, [("x", "v", "r1"), ("y", "w", "r2")])
    motor = UncertaintyEngine(kb, rule_cfs={"r1": 0.6, "rule_c": 0.5})
    assert cf_derivado(motor, wm, "x") == pytest.approx(0.6)


def test_una_regla_equivalente_con_premisa_debil_no_suma():
    kb = kb_dos_reglas()
    kb["rules"][1]["conditions"].append({"attribute_id": "z", "operator": "==", "value": "q"})
    kb["attributes"].append({"id": "z", "name": "Z", "type": "text"})
    wm = memoria({"x": "1", "z": "q"}, [("dictamen", "Elegible", "rule_a")])
    motor = UncertaintyEngine(kb, rule_cfs={"rule_a": 0.6, "rule_b": 0.5}, fact_cfs={"z": 0.1})
    assert cf_derivado(motor, wm) == pytest.approx(0.6)


def test_operadores_in_y_orden_en_reglas_equivalentes():
    kb = {
        "attributes": [{"id": "n", "name": "N", "type": "numeric"},
                       {"id": "c", "name": "C", "type": "text"}],
        "rules": [
            regla("r1", [("c", "k")], "res", "ok"),
            {"id": "r2", "description": "", "priority": 1,
             "conditions": [{"attribute_id": "n", "operator": ">=", "value": 5},
                            {"attribute_id": "c", "operator": "in", "value": ["k", "m"]}],
             "conclusion": {"attribute_id": "res", "value": "ok"}, "explanation_template": ""},
        ],
    }
    wm = memoria({"n": 7, "c": "k"}, [("res", "ok", "r1")])
    motor = UncertaintyEngine(kb, rule_cfs={"r1": 0.6, "r2": 0.5})
    assert cf_derivado(motor, wm, "res") == pytest.approx(0.8)
    wm_bajo = memoria({"n": 3, "c": "k"}, [("res", "ok", "r1")])
    assert cf_derivado(motor, wm_bajo, "res") == pytest.approx(0.6)


def test_tipos_incomparables_en_reglas_equivalentes_no_rompen_el_calculo():
    kb = {
        "attributes": [{"id": "n", "name": "N", "type": "text"}],
        "rules": [
            regla("r1", [("n", "abc")], "res", "ok"),
            {"id": "r2", "description": "", "priority": 1,
             "conditions": [{"attribute_id": "n", "operator": ">", "value": 5}],
             "conclusion": {"attribute_id": "res", "value": "ok"}, "explanation_template": ""},
        ],
    }
    wm = memoria({"n": "abc"}, [("res", "ok", "r1")])
    assert cf_derivado(UncertaintyEngine(kb, rule_cfs={"r1": 0.7}), wm, "res") == pytest.approx(0.7)


# --- Datos invalidos ---


@pytest.mark.parametrize("cf", [1.5, -2, math.nan, "alto", None])
def test_fc_de_regla_invalido(cf):
    with pytest.raises(UncertaintyError):
        UncertaintyEngine(KB, rule_cfs={"rule_01": cf})


def test_fc_para_una_regla_que_no_existe():
    with pytest.raises(UncertaintyError, match="rule_99"):
        UncertaintyEngine(KB, rule_cfs={"rule_99": 0.5})


def test_fc_para_un_atributo_no_declarado():
    with pytest.raises(UncertaintyError, match="edad"):
        UncertaintyEngine(KB, fact_cfs={"edad": 0.5})


def test_fc_de_dato_fuera_de_rango():
    with pytest.raises(UncertaintyError):
        UncertaintyEngine(KB, fact_cfs={"promedio": 3})


@pytest.mark.parametrize("kb", [None, [], {}, {"rules": "no es lista"}, {"rules": [{"sin": "id"}]}])
def test_base_de_conocimiento_invalida(kb):
    with pytest.raises(UncertaintyError):
        UncertaintyEngine(kb)


@pytest.mark.parametrize("umbral", [-0.1, 1, 2, True, "0.2"])
def test_umbral_invalido(umbral):
    with pytest.raises(UncertaintyError):
        UncertaintyEngine(KB, threshold=umbral)


def test_default_cf_invalido():
    with pytest.raises(UncertaintyError):
        UncertaintyEngine(KB, default_cf=1.2)


def test_memoria_que_no_es_un_objeto():
    with pytest.raises(UncertaintyError):
        UncertaintyEngine(KB).evaluate(["no", "es", "dict"])


def test_hecho_derivado_incompleto():
    wm = copy.deepcopy(WM)
    del wm["derived_facts"]["dictamen"]["derived_by_rule"]
    with pytest.raises(UncertaintyError, match="derived_by_rule"):
        UncertaintyEngine(KB).evaluate(wm)


def test_regla_citada_que_no_existe_en_la_base():
    wm = copy.deepcopy(WM)
    wm["derived_facts"]["dictamen"]["derived_by_rule"] = "rule_99"
    wm["execution_trace"][0]["rule_fired"] = "rule_99"
    with pytest.raises(UncertaintyError, match="rule_99"):
        UncertaintyEngine(KB).evaluate(wm)


def test_hecho_derivado_sin_registro_en_la_traza():
    wm = copy.deepcopy(WM)
    wm["execution_trace"] = []
    with pytest.raises(UncertaintyError, match="execution_trace"):
        UncertaintyEngine(KB).evaluate(wm)


def test_ciclo_en_la_derivacion():
    kb = {
        "attributes": [],
        "rules": [regla("r1", [("y", "1")], "x", "1"), regla("r2", [("x", "1")], "y", "1")],
    }
    wm = memoria({}, [("x", "1", "r1"), ("y", "1", "r2")])
    with pytest.raises(UncertaintyError, match="Ciclo"):
        UncertaintyEngine(kb).evaluate(wm)


def test_certainty_score_de_un_atributo_que_no_se_derivo():
    motor = UncertaintyEngine(KB)
    with pytest.raises(UncertaintyError, match="promedio"):
        motor.certainty_score(WM, "promedio")
    with pytest.raises(UncertaintyError, match="inexistente"):
        motor.certainty_score(WM, "inexistente")


def test_complete_verdict_exige_un_objeto():
    with pytest.raises(UncertaintyError):
        UncertaintyEngine(KB).complete_verdict("no es dict", WM, "dictamen")
