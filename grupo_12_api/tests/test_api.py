"""Pruebas de la API REST (Grupo 12) con los modulos reales de G4, G5 y G8.

Se ejecutan desde la raiz del repositorio con: python -m pytest grupo_12_api
"""

import copy

import pytest
from fastapi.testclient import TestClient

from grupo_04_schema.esb_schema import SchemaManager
from grupo_12_api.adaptadores import CONTRATOS, Integraciones
from grupo_12_api.esb_api import app, obtener_servicio
from grupo_12_api.servicio import KB_ACADEMICO, KB_EJEMPLO, ServicioESB, cargar_ejemplo

KB = cargar_ejemplo("conocimiento_dominio")
VALIDADOR = SchemaManager(carpeta_esquemas=CONTRATOS)
DICTAMEN_A = "Calificación A - Sobresaliente"


def _cliente(servicio):
    app.dependency_overrides[obtener_servicio] = lambda: servicio
    return TestClient(app)


@pytest.fixture
def servicio():
    return ServicioESB()


@pytest.fixture
def cliente(servicio):
    """Cliente con un servicio nuevo en cada prueba, para que no compartan sesiones."""
    yield _cliente(servicio)
    app.dependency_overrides.clear()


def nueva_sesion(cliente, hechos=None, kb_id=KB_ACADEMICO):
    r = cliente.post("/consultas", json={"kb_id": kb_id, "hechos": hechos or {}})
    assert r.status_code == 201, r.json()
    return r.json()["session_id"]


def consultar(cliente, hechos, kb_id=KB_ACADEMICO):
    session_id = nueva_sesion(cliente, hechos, kb_id)
    assert cliente.post(f"/consultas/{session_id}/inferir").status_code == 200
    return session_id


# --- Caso normal ---

def test_salud_muestra_modulos_reales(cliente):
    modulos = cliente.get("/salud").json()["modulos"]
    for grupo in ("G4 SchemaManager", "G5 ForwardEngine", "G8 XAIExplainer"):
        assert modulos[grupo] == "real"
    assert modulos["G6 BackwardEngine"] == "simulado"
    assert cliente.get("/docs").status_code == 200


def test_cargar_y_leer_conocimiento(cliente):
    r = cliente.post("/conocimiento", json=KB)
    assert r.status_code == 201
    cargada = r.json()
    assert (cargada["kb_id"], cargada["atributos"], cargada["reglas"]) == ("kb_001", 2, 1)
    assert cliente.get("/conocimiento/kb_001").json() == KB
    preguntas = cliente.get(f"/conocimiento/{KB_ACADEMICO}/preguntas").json()
    assert [p["attribute_id"] for p in preguntas] == ["tipo_consulta", "puntaje_final",
                                                      "nota_obtenida"]


@pytest.mark.parametrize("hechos, regla, resultado", [
    ({"tipo_consulta": "Calificacion", "puntaje_final": 95}, "reg_calificacion_a", DICTAMEN_A),
    ({"tipo_consulta": "Calificacion", "puntaje_final": 60}, "reg_calificacion_f",
     "Calificación F - Fracaso"),
    ({"tipo_consulta": "Repeticion", "nota_obtenida": "D"}, "reg_repeticion_d",
     "La calificación D cumple el criterio de nota D o F para repetir con el fin de "
     "mejorar el índice."),
])
def test_inferencia_y_dictamen_cumplen_contratos(cliente, hechos, regla, resultado):
    session_id = consultar(cliente, hechos)
    memoria = cliente.get(f"/consultas/{session_id}/memoria").json()
    assert memoria["derived_facts"]["dictamen"]["derived_by_rule"] == regla
    assert memoria["execution_trace"] == [{"step": 1, "rule_fired": regla, "added_fact": "dictamen"}]

    dictamen = cliente.get(f"/consultas/{session_id}/dictamen").json()
    assert dictamen["final_outcome"] == resultado
    assert dictamen["certainty_score"] == 1.0
    assert dictamen["explanation_how"][0] == f"Se determinó {resultado!r} debido a la regla {regla}."
    assert regla in dictamen["explanation_why"]

    kb = cliente.get(f"/conocimiento/{KB_ACADEMICO}").json()
    assert VALIDADOR.validar_conjunto(kb, memoria, dictamen, "dictamen") == {
        "valido": True, "errores": []}


def test_how_why_y_traza(cliente):
    session_id = consultar(cliente, {"tipo_consulta": "Calificacion", "puntaje_final": 95})
    base = f"/consultas/{session_id}"
    how = cliente.get(f"{base}/explicacion/how").json()["explanation_how"]
    assert how[1:3] == ["Premisa 1: tipo_consulta == 'Calificacion' (Verificado)",
                        "Premisa 2: puntaje_final >= 91 (Valor ingresado: 95)"]
    how_dato = cliente.get(f"{base}/explicacion/how", params={"atributo": "puntaje_final"}).json()
    assert how_dato["explanation_how"] == ["'puntaje_final' fue ingresado por el usuario: 95."]

    why = cliente.get(f"{base}/explicacion/why",
                      params={"atributo": "puntaje_final", "regla": "reg_calificacion_a"}).json()
    assert why["explanation_why"].startswith(
        "Se solicitó 'puntaje_final' para evaluar la condición de la regla reg_calificacion_a")

    traza = cliente.get(f"{base}/traza").json()["pasos"]
    assert traza == [f"Paso 1: reg_calificacion_a agregó dictamen = {DICTAMEN_A!r}"]


def test_siguiente_pregunta_sigue_las_reglas_posibles(cliente):
    session_id = nueva_sesion(cliente)
    url = f"/consultas/{session_id}/siguiente-pregunta"
    assert cliente.get(url).json()["pregunta"]["attribute_id"] == "tipo_consulta"

    cliente.post(f"/consultas/{session_id}/hechos", json={"hechos": {"tipo_consulta": "Repeticion"}})
    pendiente = cliente.get(url).json()
    assert pendiente["pregunta"]["attribute_id"] == "nota_obtenida"
    assert pendiente["pregunta"]["options"] == ["A", "B", "C", "D", "F"]
    assert "reg_repeticion_" in pendiente["explanation_why"]

    cliente.post(f"/consultas/{session_id}/hechos", json={"hechos": {"nota_obtenida": "F"}})
    cliente.post(f"/consultas/{session_id}/inferir")
    assert cliente.get(url).json() == {"session_id": session_id, "completa": True,
                                       "pregunta": None, "explanation_why": None}
    why = cliente.get(f"/consultas/{session_id}/dictamen").json()["explanation_why"]
    assert why.startswith("Se solicitó 'nota_obtenida' para evaluar la condición de la regla "
                          "reg_repeticion_f")


def test_registrar_hechos_descarta_conclusiones_anteriores(cliente):
    session_id = consultar(cliente, {"tipo_consulta": "Calificacion", "puntaje_final": 95})
    memoria = cliente.post(f"/consultas/{session_id}/hechos",
                           json={"hechos": {"puntaje_final": 85}}).json()
    assert memoria["derived_facts"] == {} and memoria["execution_trace"] == []
    cliente.post(f"/consultas/{session_id}/inferir")
    assert cliente.get(f"/consultas/{session_id}/dictamen").json()["final_outcome"] == \
        "Calificación B - Bueno"


def test_reporte_markdown_y_html(cliente):
    session_id = consultar(cliente, {"tipo_consulta": "Calificacion", "puntaje_final": 95})
    md = cliente.get(f"/consultas/{session_id}/reporte")
    assert md.status_code == 200
    assert md.text.startswith(f"# Dictamen {session_id}")
    assert DICTAMEN_A in md.text and "reg_calificacion_a" in md.text
    html = cliente.get(f"/consultas/{session_id}/reporte", params={"formato": "html"})
    assert html.headers["content-type"].startswith("text/html")
    assert "<h1>" in html.text


# --- Datos invalidos ---

@pytest.mark.parametrize("cambio, fragmento", [
    (lambda kb: kb["attributes"][1].update(options=[]), "attributes[1]"),
    (lambda kb: kb["attributes"].append(copy.deepcopy(kb["attributes"][0])), "repetido"),
    (lambda kb: kb["rules"][0]["conditions"][0].update(attribute_id="edad"), "no existe"),
    (lambda kb: kb["rules"][0]["conditions"][1].update(value="alto"), "Se esperaba un número"),
])
def test_base_rechazada_por_g4(cliente, cambio, fragmento):
    kb = copy.deepcopy(KB)
    cambio(kb)
    r = cliente.post("/conocimiento", json=kb)
    assert r.status_code == 422
    assert any(fragmento in e for e in r.json()["errores"]), r.json()


@pytest.mark.parametrize("cambio", [
    lambda kb: kb.pop("rules"),
    lambda kb: kb["rules"][0].update(conditions=[]),
    lambda kb: kb["rules"][0]["conditions"][0].update(operator="~="),
    lambda kb: kb["meta"].pop("author_group"),
])
def test_base_que_no_cumple_la_forma_del_contrato(cliente, cambio):
    kb = copy.deepcopy(KB)
    cambio(kb)
    assert cliente.post("/conocimiento", json=kb).status_code == 422


@pytest.mark.parametrize("hechos, fragmento", [
    ({"puntaje_final": 150}, "fuera del rango"),
    ({"nota_obtenida": "E"}, "opciones permitidas"),
    ({"puntaje_final": "noventa"}, "Se esperaba un número"),
    ({"edad": 20}, "no está declarado"),
])
def test_hechos_rechazados_por_g4(cliente, hechos, fragmento):
    r = cliente.post("/consultas", json={"kb_id": KB_ACADEMICO, "hechos": hechos})
    assert r.status_code == 422
    assert fragmento in r.json()["errores"][0]

    session_id = nueva_sesion(cliente, {"tipo_consulta": "Calificacion"})
    r = cliente.post(f"/consultas/{session_id}/hechos", json={"hechos": hechos})
    assert r.status_code == 422
    memoria = cliente.get(f"/consultas/{session_id}/memoria").json()
    assert memoria["facts"] == {"tipo_consulta": "Calificacion"}


def test_cuerpos_invalidos(cliente):
    assert cliente.post("/consultas", json={"kb_id": KB_ACADEMICO, "motor": "lateral"}).status_code == 422
    session_id = nueva_sesion(cliente)
    assert cliente.post(f"/consultas/{session_id}/hechos", json={"hechos": {}}).status_code == 422
    assert cliente.get(f"/consultas/{session_id}/reporte", params={"formato": "pdf"}).status_code == 422


def test_recursos_inexistentes(cliente):
    assert cliente.get("/conocimiento/kb_999").status_code == 404
    assert cliente.post("/consultas", json={"kb_id": "kb_999"}).status_code == 404
    r = cliente.get("/consultas/sess_0000_00000/memoria")
    assert r.status_code == 404 and "sess_0000_00000" in r.json()["detail"]


def test_why_con_atributo_o_regla_desconocidos(cliente):
    url = f"/consultas/{nueva_sesion(cliente)}/explicacion/why"
    r = cliente.get(url, params={"atributo": "edad"})
    assert r.status_code == 404 and "Ninguna regla" in r.json()["detail"]
    r = cliente.get(url, params={"atributo": "puntaje_final", "regla": "reg_99"})
    assert r.status_code == 404 and "reg_99" in r.json()["detail"]


# --- Reglas que no se activan ---

def test_inferir_sin_hechos(cliente):
    assert cliente.post(f"/consultas/{nueva_sesion(cliente)}/inferir").status_code == 409


def test_ninguna_regla_se_activa(cliente):
    session_id = nueva_sesion(cliente, {"tipo_consulta": "Calificacion"})
    r = cliente.post(f"/consultas/{session_id}/inferir")
    assert r.status_code == 200
    assert r.json()["derived_facts"] == {} and r.json()["halted_reason"] == "quiescence"
    assert cliente.get(f"/consultas/{session_id}/traza").json()["pasos"] == []
    r = cliente.get(f"/consultas/{session_id}/dictamen")
    assert r.status_code == 409 and "Ninguna regla" in r.json()["detail"]
    r = cliente.get(f"/consultas/{session_id}/explicacion/how")
    assert r.status_code == 404 and "no tiene valor" in r.json()["detail"]


# --- Reglas en conflicto ---

def test_conflicto_gana_la_regla_de_mayor_prioridad(cliente):
    kb = cliente.get(f"/conocimiento/{KB_ACADEMICO}").json()
    kb["rules"].append({
        "id": "reg_excelencia", "description": "Puntaje perfecto", "priority": 50,
        "conditions": [{"attribute_id": "puntaje_final", "operator": "==", "value": 100}],
        "conclusion": {"attribute_id": "dictamen", "value": "Excelencia académica"},
        "explanation_template": "El puntaje es perfecto."})
    kb_id = cliente.post("/conocimiento", json=kb).json()["kb_id"]

    session_id = consultar(cliente, {"tipo_consulta": "Calificacion", "puntaje_final": 100}, kb_id)
    memoria = cliente.get(f"/consultas/{session_id}/memoria").json()
    assert [p["rule_fired"] for p in memoria["execution_trace"]] == ["reg_excelencia"]
    assert cliente.get(f"/consultas/{session_id}/dictamen").json()["final_outcome"] == \
        "Excelencia académica"


# --- Respaldo cuando falta un modulo ---

@pytest.mark.parametrize("grupo, nombre", [("G5", "G5 ForwardEngine"), ("G8", "G8 XAIExplainer"),
                                           ("G4", "G4 SchemaManager")])
def test_la_api_sigue_respondiendo_sin_un_modulo(grupo, nombre):
    cliente = _cliente(ServicioESB(Integraciones(deshabilitar={grupo})))
    try:
        assert cliente.get("/salud").json()["modulos"][nombre] == "simulado"
        session_id = consultar(cliente, {"tipo_consulta": "Calificacion", "puntaje_final": 95})
        dictamen = cliente.get(f"/consultas/{session_id}/dictamen").json()
        assert dictamen["final_outcome"] == DICTAMEN_A
        assert dictamen["explanation_how"][0].startswith(f"Se determinó {DICTAMEN_A!r}")
    finally:
        app.dependency_overrides.clear()


def test_base_de_ejemplo_de_la_guia(cliente):
    session_id = consultar(cliente, {"materia": "Trabajo de Graduacion", "promedio": 2.25},
                           KB_EJEMPLO)
    dictamen = cliente.get(f"/consultas/{session_id}/dictamen").json()
    assert dictamen["final_outcome"] == "Elegible"
    assert dictamen["explanation_how"][:3] == cargar_ejemplo("dictamen_salida")["explanation_how"]
