"""Pruebas unitarias del BackwardEngine (Grupo 6).

Cubren casos normales, datos invalidos y reglas que no se activan o entran en
conflicto, como pide la seccion 7 de la guia. No dependen de otros grupos.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from grupo_06_backward import (
    BackwardEngine,
    BackwardEngineError,
    InvalidAnswerError,
    InvalidKnowledgeBaseError,
    InvalidWorkingMemoryError,
    Question,
)

EJEMPLO = Path(__file__).resolve().parents[1] / "datos_ejemplo" / "conocimiento_encadenado.json"

# Ejemplo minimo de la seccion 4.2 de la guia.
KB_MINIMA = {
    "meta": {"project_title": "Guia 4.2", "version": "1.0", "author_group": "G6"},
    "attributes": [
        {"id": "promedio", "name": "Promedio", "type": "numeric",
         "question": "¿Cuál es el promedio ponderado del estudiante?", "range": [0.0, 3.0]},
        {"id": "materia", "name": "Tipo de asignatura", "type": "categorical",
         "question": "Seleccione el tipo de asignatura:",
         "options": ["Obligatoria", "Electiva", "Trabajo de Graduacion"]},
    ],
    "rules": [
        {"id": "rule_01", "description": "Elegibilidad para un trámite", "priority": 10,
         "conditions": [
             {"attribute_id": "materia", "operator": "==", "value": "Trabajo de Graduacion"},
             {"attribute_id": "promedio", "operator": ">=", "value": 2.0}],
         "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
         "explanation_template": "El promedio cumple el mínimo requerido."}
    ],
}


@pytest.fixture
def kb():
    with EJEMPLO.open(encoding="utf-8") as handle:
        return json.load(handle)


def preguntador(respuestas: dict):
    """ask_fn de prueba: responde desde un dict y registra el orden de las preguntas."""
    hechas: list[Question] = []

    def ask(pregunta: Question):
        hechas.append(pregunta)
        return respuestas.get(pregunta.attribute_id)

    ask.hechas = hechas
    return ask


def atributos_preguntados(ask) -> list[str]:
    return [p.attribute_id for p in ask.hechas]


# --- Casos normales -------------------------------------------------------------


def test_ejemplo_minimo_de_la_guia_con_hechos_ya_conocidos():
    memoria = {"session_id": "sess_2026_10123", "facts": {
        "materia": "Trabajo de Graduacion", "promedio": 2.25},
        "derived_facts": {}, "execution_trace": []}
    resultado = BackwardEngine(KB_MINIMA).prove("dictamen", memory=memoria)

    assert resultado.achieved and resultado.value == "Elegible"
    assert resultado.reason == "derivado"
    assert resultado.questions_asked == [] and resultado.pending_question is None
    derivado = resultado.memory["derived_facts"]["dictamen"]
    assert derivado["derived_by_rule"] == "rule_01"
    assert resultado.memory["execution_trace"] == [
        {"step": 1, "rule_fired": "rule_01", "added_fact": "dictamen"}]


def test_pregunta_los_datos_y_los_guarda_en_la_memoria():
    ask = preguntador({"materia": "Trabajo de Graduacion", "promedio": 2.25})
    resultado = BackwardEngine(KB_MINIMA, ask).prove("dictamen", session_id="sess_x")

    assert resultado.achieved
    assert atributos_preguntados(ask) == ["materia", "promedio"]
    assert resultado.memory["session_id"] == "sess_x"
    assert resultado.memory["facts"] == {"materia": "Trabajo de Graduacion", "promedio": 2.25}


def test_cada_pregunta_informa_la_regla_y_la_meta_para_el_why():
    ask = preguntador({"materia": "Trabajo de Graduacion", "promedio": 2.25})
    BackwardEngine(KB_MINIMA, ask).prove("dictamen")

    promedio = ask.hechas[1]
    assert promedio.rule_id == "rule_01"
    assert promedio.goal == "dictamen"
    assert promedio.question == "¿Cuál es el promedio ponderado del estudiante?"
    assert promedio.type == "numeric" and promedio.range == (0.0, 3.0)


def test_encadena_subgoales_y_la_traza_sigue_el_orden_de_derivacion(kb):
    ask = preguntador({"materia": "Trabajo de Graduacion", "promedio": 2.5, "creditos": 150})
    resultado = BackwardEngine(kb, ask).prove("dictamen")

    assert resultado.value == "Elegible"
    assert resultado.fired_rules == ["rule_04", "rule_01"]
    assert resultado.memory["derived_facts"]["requisitos"]["derived_by_rule"] == "rule_04"
    creditos = next(p for p in ask.hechas if p.attribute_id == "creditos")
    assert (creditos.rule_id, creditos.goal) == ("rule_04", "requisitos")
    assert [p["step"] for p in resultado.memory["execution_trace"]] == [1, 2]


def test_solo_pregunta_lo_necesario(kb):
    """Con 'Electiva' basta rule_02: no hay que pedir promedio ni creditos."""
    ask = preguntador({"materia": "Electiva", "promedio": 1.0, "creditos": 10})
    resultado = BackwardEngine(kb, ask).prove("dictamen")

    assert resultado.value == "Elegible"
    assert resultado.fired_rules == ["rule_02"]
    assert atributos_preguntados(ask) == ["materia"]


def test_descarta_una_regla_con_un_hecho_conocido_antes_de_preguntar_el_resto(kb):
    """materia ya es 'Electiva': rule_01 se descarta sin pedir promedio."""
    ask = preguntador({})
    memoria = {"session_id": "s", "facts": {"materia": "Electiva"},
               "derived_facts": {}, "execution_trace": []}
    resultado = BackwardEngine(kb, ask).prove("dictamen", memory=memoria)

    assert resultado.value == "Elegible"
    assert ask.hechas == []


def test_meta_que_es_un_dato_del_usuario_se_pregunta_directo():
    ask = preguntador({"promedio": 2.8})
    resultado = BackwardEngine(KB_MINIMA, ask).prove("promedio")

    assert resultado.achieved and resultado.value == 2.8
    assert resultado.reason == "dato_conocido"
    assert ask.hechas[0].rule_id is None and ask.hechas[0].goal is None


def test_hipotesis_confirmada(kb):
    ask = preguntador({"materia": "Trabajo de Graduacion", "promedio": 2.5, "creditos": 150})
    resultado = BackwardEngine(kb, ask).prove("dictamen", "Elegible")
    assert resultado.achieved and resultado.reason == "derivado"


def test_hipotesis_refutada_por_otro_valor(kb):
    ask = preguntador({"materia": "Trabajo de Graduacion", "promedio": 1.5})
    resultado = BackwardEngine(kb, ask).prove("dictamen", "Elegible")

    assert not resultado.achieved
    assert resultado.value == "No elegible" and resultado.reason == "valor_distinto"


def test_operador_in(kb):
    ask = preguntador({"materia": "Obligatoria"})
    assert BackwardEngine(kb, ask).prove("dictamen").fired_rules == ["rule_02"]


def test_no_modifica_la_memoria_recibida():
    memoria = {"session_id": "s", "facts": {"materia": "Trabajo de Graduacion", "promedio": 2.5},
               "derived_facts": {}, "execution_trace": []}
    original = copy.deepcopy(memoria)
    BackwardEngine(KB_MINIMA).prove("dictamen", memory=memoria)
    assert memoria == original


def test_reutiliza_hechos_derivados_que_ya_estan_en_la_memoria(kb):
    memoria = {"session_id": "s",
               "facts": {"materia": "Trabajo de Graduacion", "promedio": 2.5},
               "derived_facts": {"requisitos": {"value": "Cumple", "derived_by_rule": "rule_04"}},
               "execution_trace": [{"step": 1, "rule_fired": "rule_04", "added_fact": "requisitos"}]}
    ask = preguntador({})
    resultado = BackwardEngine(kb, ask).prove("dictamen", memory=memoria)

    assert resultado.value == "Elegible" and ask.hechas == []
    assert [p["step"] for p in resultado.memory["execution_trace"]] == [1, 2]


def test_un_hecho_del_usuario_no_se_sobrescribe_con_una_regla():
    kb = copy.deepcopy(KB_MINIMA)
    memoria = {"session_id": "s", "facts": {"dictamen": "Manual"},
               "derived_facts": {}, "execution_trace": []}
    resultado = BackwardEngine(kb).prove("dictamen", memory=memoria)
    assert resultado.value == "Manual" and resultado.reason == "dato_conocido"
    assert resultado.memory["derived_facts"] == {}


# --- Reglas que no se activan, conflictos y ciclos -----------------------------


def test_ninguna_regla_se_cumple(kb):
    ask = preguntador({"materia": "Trabajo de Graduacion", "promedio": 2.5, "creditos": 100})
    resultado = BackwardEngine(kb, ask).prove("dictamen")

    # rule_01 falla (requisitos = No cumple) y rule_06 concluye "No elegible".
    assert resultado.value == "No elegible"
    assert resultado.fired_rules == ["rule_05", "rule_06"]


def test_meta_sin_reglas_aplicables_no_deriva_nada():
    ask = preguntador({"materia": "Electiva"})
    resultado = BackwardEngine(KB_MINIMA, ask).prove("dictamen")

    assert not resultado.achieved and resultado.value is None
    assert resultado.reason == "no_se_cumple_ninguna_regla"
    assert resultado.memory["derived_facts"] == {} and resultado.memory["execution_trace"] == []


def test_conflicto_gana_la_regla_de_mayor_prioridad():
    kb = {"attributes": [], "rules": [
        {"id": "r_baja", "priority": 1, "description": "",
         "conditions": [{"attribute_id": "x", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "y", "value": "bajo"}},
        {"id": "r_alta", "priority": 9, "description": "",
         "conditions": [{"attribute_id": "x", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "y", "value": "alto"}}]}
    memoria = {"session_id": "s", "facts": {"x": 1}, "derived_facts": {}, "execution_trace": []}
    resultado = BackwardEngine(kb).prove("y", memory=memoria)

    assert resultado.value == "alto" and resultado.fired_rules == ["r_alta"]


def test_empate_de_prioridad_se_resuelve_por_id():
    kb = {"attributes": [], "rules": [
        {"id": "b", "priority": 5, "conditions": [{"attribute_id": "x", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "y", "value": "b"}},
        {"id": "a", "priority": 5, "conditions": [{"attribute_id": "x", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "y", "value": "a"}}]}
    memoria = {"session_id": "s", "facts": {"x": 1}, "derived_facts": {}, "execution_trace": []}
    assert BackwardEngine(kb).prove("y", memory=memoria).value == "a"


def test_un_ciclo_entre_reglas_no_cuelga_el_motor():
    kb = {"attributes": [], "rules": [
        {"id": "r1", "priority": 1, "conditions": [{"attribute_id": "b", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "a", "value": 1}},
        {"id": "r2", "priority": 1, "conditions": [{"attribute_id": "a", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "b", "value": 1}}]}
    resultado = BackwardEngine(kb).prove("a")

    assert not resultado.achieved
    assert any("Ciclo" in linea for linea in resultado.proof)


def test_un_ciclo_no_impide_otra_via_que_si_funciona():
    kb = {"attributes": [], "rules": [
        {"id": "r1", "priority": 10, "conditions": [{"attribute_id": "b", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "a", "value": 1}},
        {"id": "r2", "priority": 1, "conditions": [{"attribute_id": "x", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "a", "value": 1}},
        {"id": "r3", "priority": 1, "conditions": [{"attribute_id": "a", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "b", "value": 1}}]}
    memoria = {"session_id": "s", "facts": {"x": 1}, "derived_facts": {}, "execution_trace": []}
    resultado = BackwardEngine(kb).prove("a", memory=memoria)
    assert resultado.achieved and resultado.fired_rules == ["r2"]


def test_condicion_resuelta_como_efecto_lateral_igual_se_evalua():
    """Al resolver la 1ª condicion queda conocido 'z'; la 2ª debe evaluarse igual."""
    kb = {"attributes": [], "rules": [
        {"id": "r_a", "priority": 1, "conditions": [{"attribute_id": "z", "operator": "==", "value": 1}],
         "conclusion": {"attribute_id": "a", "value": "ok"}},
        {"id": "r_meta", "priority": 1, "conditions": [
            {"attribute_id": "a", "operator": "==", "value": "ok"},
            {"attribute_id": "z", "operator": "==", "value": 99}],
         "conclusion": {"attribute_id": "meta", "value": "no debe disparar"}}]}
    ask = preguntador({"z": 1})
    resultado = BackwardEngine(kb, ask).prove("meta")
    assert not resultado.achieved and "r_meta" not in resultado.fired_rules


# --- Datos faltantes y entradas del usuario -----------------------------------------


def test_respuesta_desconocida_no_rompe_ni_se_vuelve_a_preguntar(kb):
    ask = preguntador({"materia": "Trabajo de Graduacion"})  # promedio -> None
    resultado = BackwardEngine(kb, ask).prove("dictamen")

    assert not resultado.achieved
    assert atributos_preguntados(ask).count("promedio") == 1


def test_una_regla_alternativa_aprovecha_cuando_falta_un_dato():
    """Si no se sabe 'promedio', rule_06 (por creditos) todavia puede concluir."""
    kb = {"attributes": [], "rules": [
        {"id": "r1", "priority": 10, "conditions": [{"attribute_id": "a", "operator": ">", "value": 1}],
         "conclusion": {"attribute_id": "meta", "value": "por_a"}},
        {"id": "r2", "priority": 1, "conditions": [{"attribute_id": "b", "operator": ">", "value": 1}],
         "conclusion": {"attribute_id": "meta", "value": "por_b"}}]}
    resultado = BackwardEngine(kb, preguntador({"b": 5})).prove("meta")
    assert resultado.value == "por_b"


def test_sin_ask_fn_informa_la_proxima_pregunta_en_vez_de_preguntar(kb):
    resultado = BackwardEngine(kb).prove("dictamen")

    assert not resultado.achieved and resultado.reason == "falta_dato"
    assert resultado.pending_question.attribute_id == "materia"
    assert resultado.pending_question.rule_id == "rule_01"


def test_next_question_avanza_conforme_se_registran_hechos(kb):
    motor = BackwardEngine(kb)
    memoria = {"session_id": "s", "facts": {}, "derived_facts": {}, "execution_trace": []}

    esperado = [("materia", {"materia": "Trabajo de Graduacion"}),
                ("promedio", {"promedio": 2.5}),
                ("creditos", {"creditos": 150})]
    for atributo, hecho in esperado:
        pregunta = motor.next_question("dictamen", memoria)
        assert pregunta.attribute_id == atributo
        memoria["facts"].update(hecho)

    assert motor.next_question("dictamen", memoria) is None
    assert motor.prove("dictamen", memory=memoria).value == "Elegible"


def test_next_question_no_llama_a_ask_fn(kb):
    llamadas = []
    motor = BackwardEngine(kb, lambda q: llamadas.append(q))
    assert motor.next_question("dictamen", None).attribute_id == "materia"
    assert llamadas == []


def test_pregunta_condicional_depends_on_solo_si_aplica():
    kb = {"attributes": [
        {"id": "materia", "name": "Materia", "type": "categorical", "options": ["TG", "Otra"]},
        {"id": "tesis", "name": "Tesis", "type": "text", "question": "¿Título de la tesis?",
         "depends_on": {"attribute_id": "materia", "operator": "==", "value": "TG"}}],
        "rules": [{"id": "r1", "priority": 1,
                   "conditions": [{"attribute_id": "tesis", "operator": "!=", "value": "x"}],
                   "conclusion": {"attribute_id": "meta", "value": 1}}]}

    ask = preguntador({"materia": "Otra", "tesis": "algo"})
    BackwardEngine(kb, ask).prove("meta")
    assert atributos_preguntados(ask) == ["materia"]  # 'tesis' no aplica

    ask = preguntador({"materia": "TG", "tesis": "algo"})
    resultado = BackwardEngine(kb, ask).prove("meta")
    assert atributos_preguntados(ask) == ["materia", "tesis"] and resultado.achieved


def test_pregunta_por_defecto_si_el_atributo_no_tiene_texto():
    kb = {"attributes": [{"id": "x", "name": "Variable X", "type": "numeric"}],
          "rules": [{"id": "r", "priority": 1,
                     "conditions": [{"attribute_id": "x", "operator": ">", "value": 0}],
                     "conclusion": {"attribute_id": "meta", "value": 1}}]}
    pregunta = BackwardEngine(kb).prove("meta").pending_question
    assert "Variable X" in pregunta.question


# --- Datos invalidos -----------------------------------------------------------------


@pytest.mark.parametrize("respuesta", [5.0, -1, "abc", True])
def test_respuesta_numerica_invalida(respuesta):
    motor = BackwardEngine(KB_MINIMA, preguntador({"materia": "Trabajo de Graduacion",
                                                   "promedio": respuesta}))
    with pytest.raises(InvalidAnswerError):
        motor.prove("dictamen")


def test_respuesta_categorica_fuera_de_las_opciones():
    motor = BackwardEngine(KB_MINIMA, preguntador({"materia": "Maestria"}))
    with pytest.raises(InvalidAnswerError):
        motor.prove("dictamen")


def test_validate_answer_normaliza_coma_decimal_y_mayusculas():
    motor = BackwardEngine(KB_MINIMA)
    assert motor.validate_answer("promedio", "2,25") == 2.25
    assert motor.validate_answer("materia", " electiva ") == "Electiva"
    assert motor.validate_answer("no_declarado", "lo que sea") == "lo que sea"


def test_validate_answer_booleanos_y_texto():
    kb = {"attributes": [{"id": "b", "name": "B", "type": "boolean"},
                         {"id": "t", "name": "T", "type": "text"}],
          "rules": [{"id": "r", "priority": 1, "conditions": [
              {"attribute_id": "b", "operator": "==", "value": True}],
              "conclusion": {"attribute_id": "m", "value": 1}}]}
    motor = BackwardEngine(kb)
    assert motor.validate_answer("b", "Sí") is True and motor.validate_answer("b", "no") is False
    with pytest.raises(InvalidAnswerError):
        motor.validate_answer("b", "quizás")
    with pytest.raises(InvalidAnswerError):
        motor.validate_answer("t", "   ")


def test_comparacion_imposible_se_trata_como_condicion_falsa():
    kb = {"attributes": [], "rules": [{"id": "r", "priority": 1, "conditions": [
        {"attribute_id": "x", "operator": ">", "value": 2}],
        "conclusion": {"attribute_id": "m", "value": 1}}]}
    memoria = {"session_id": "s", "facts": {"x": "texto"}, "derived_facts": {}, "execution_trace": []}
    assert not BackwardEngine(kb).prove("m", memory=memoria).achieved


@pytest.mark.parametrize("cambio, mensaje", [
    (lambda kb: kb.pop("rules"), "rules"),
    (lambda kb: kb.update(rules=[]), "rules"),
    (lambda kb: kb["rules"][0].update(conditions=[]), "condición"),
    (lambda kb: kb["rules"][0]["conditions"][0].update(operator="~="), "operador"),
    (lambda kb: kb["rules"][0]["conditions"][0].update(operator="in", value=3), "lista"),
    (lambda kb: kb["rules"][0].pop("conclusion"), "conclusión"),
    (lambda kb: kb["rules"][0].update(priority="alta"), "prioridad"),
    (lambda kb: kb["rules"].append(copy.deepcopy(kb["rules"][0])), "repetida"),
])
def test_base_de_conocimiento_invalida(cambio, mensaje):
    kb = copy.deepcopy(KB_MINIMA)
    cambio(kb)
    with pytest.raises(InvalidKnowledgeBaseError, match=mensaje):
        BackwardEngine(kb)


def test_base_que_no_es_un_objeto():
    with pytest.raises(InvalidKnowledgeBaseError):
        BackwardEngine(["no", "es", "dict"])  # type: ignore[arg-type]


def test_meta_inexistente():
    with pytest.raises(BackwardEngineError, match="no existe"):
        BackwardEngine(KB_MINIMA).prove("inventado")


@pytest.mark.parametrize("memoria", [
    "texto", {"facts": {}}, {"session_id": "", "facts": {}},
    {"session_id": "s", "facts": []}, {"session_id": "s", "execution_trace": {}}])
def test_memoria_invalida(memoria):
    with pytest.raises(InvalidWorkingMemoryError):
        BackwardEngine(KB_MINIMA).prove("dictamen", memory=memoria)


def test_profundidad_maxima_protege_de_cadenas_muy_largas():
    reglas = [{"id": f"r{i}", "priority": 1,
               "conditions": [{"attribute_id": f"a{i + 1}", "operator": "==", "value": 1}],
               "conclusion": {"attribute_id": f"a{i}", "value": 1}} for i in range(10)]
    motor = BackwardEngine({"attributes": [], "rules": reglas}, max_depth=3)
    with pytest.raises(BackwardEngineError, match="profundidad"):
        motor.prove("a0")


# --- Prueba y trazabilidad ---------------------------------------------------------


def test_el_registro_de_prueba_muestra_reglas_y_condiciones(kb):
    ask = preguntador({"materia": "Trabajo de Graduacion", "promedio": 1.5})
    proof = BackwardEngine(kb, ask).prove("dictamen").proof

    texto = "\n".join(proof)
    assert "Meta: dictamen" in texto
    assert "Probando rule_01" in texto
    assert "Falla: promedio >= 2.0" in texto
    assert "rule_03 probada" in texto


def test_metas_que_ya_fallaron_no_se_vuelven_a_explorar():
    """Dos reglas por nivel que dependen del siguiente: sin memoria de fallos seria exponencial."""
    niveles = 18
    reglas = [{"id": f"r{i}{letra}", "priority": 1,
               "conditions": [{"attribute_id": f"n{i + 1}", "operator": "==", "value": 1}],
               "conclusion": {"attribute_id": f"n{i}", "value": 1}}
              for i in range(niveles) for letra in "ab"]
    reglas.append({"id": "fin", "priority": 1,
                   "conditions": [{"attribute_id": "x", "operator": "==", "value": 1}],
                   "conclusion": {"attribute_id": f"n{niveles}", "value": 1}})
    memoria = {"session_id": "s", "facts": {"x": 0}, "derived_facts": {}, "execution_trace": []}

    resultado = BackwardEngine({"attributes": [], "rules": reglas}, max_depth=1000).prove(
        "n0", memory=memoria)

    assert not resultado.achieved
    assert len(resultado.proof) < 500


def test_hecho_derivado_mal_formado_en_la_memoria():
    memoria = {"session_id": "s", "facts": {}, "execution_trace": [],
               "derived_facts": {"dictamen": {"derived_by_rule": "rule_01"}}}
    with pytest.raises(InvalidWorkingMemoryError, match="value"):
        BackwardEngine(KB_MINIMA).prove("dictamen", memory=memoria)
