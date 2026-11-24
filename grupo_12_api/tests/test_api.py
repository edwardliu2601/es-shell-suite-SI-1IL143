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
    for grupo in ("G3 KBAuditor", "G4 SchemaManager", "G5 ForwardEngine", "G6 BackwardEngine",
                  "G7 UncertaintyEngine", "G8 XAIExplainer", "G9 ReportGenerator"):
        assert modulos[grupo] == "real"
    assert modulos["G11 ESBConverter"] in {"real", "simulado"}
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
                                           ("G4", "G4 SchemaManager"),
                                           ("G7", "G7 UncertaintyEngine"),
                                           ("G6", "G6 BackwardEngine")])
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


# --- Factores de certeza (G7) ---

HECHOS_EJEMPLO = {"materia": "Trabajo de Graduacion", "promedio": 2.25}


def consulta_con_certeza(cliente, fc_reglas=None, fc_hechos=None):
    r = cliente.post("/consultas", json={"kb_id": KB_EJEMPLO, "hechos": HECHOS_EJEMPLO,
                                         "fc_reglas": fc_reglas or {},
                                         "fc_hechos": fc_hechos or {}})
    assert r.status_code == 201, r.json()
    session_id = r.json()["session_id"]
    memoria = cliente.post(f"/consultas/{session_id}/inferir").json()
    return session_id, memoria


def test_certeza_por_defecto_es_uno(cliente):
    _, memoria = consulta_con_certeza(cliente)
    assert memoria["derived_facts"]["dictamen"]["certainty_factor"] == 1.0


def test_certeza_de_reglas_y_datos(cliente):
    # Ejemplo del README de G7: FC = 0.8 (regla) * min(1.0, 0.9) (premisas) = 0.72.
    session_id, memoria = consulta_con_certeza(cliente, {"rule_01": 0.8}, {"promedio": 0.9})
    assert memoria["derived_facts"]["dictamen"]["certainty_factor"] == 0.72
    dictamen = cliente.get(f"/consultas/{session_id}/dictamen").json()
    assert dictamen["certainty_score"] == 0.72
    assert dictamen["explanation_how"][0] == \
        "Se determinó 'Elegible' debido a la regla rule_01 (FC = 0.72)."
    kb = cliente.get(f"/conocimiento/{KB_EJEMPLO}").json()
    assert VALIDADOR.validar_conjunto(kb, memoria, dictamen, "dictamen")["valido"]


def test_certeza_bajo_el_umbral_de_mycin(cliente):
    # Si las premisas no superan 0.2, la regla no aporta certeza.
    session_id, _ = consulta_con_certeza(cliente, fc_hechos={"promedio": 0.1})
    assert cliente.get(f"/consultas/{session_id}/dictamen").json()["certainty_score"] == 0.0


def test_certeza_registrada_con_los_hechos(cliente):
    session_id = nueva_sesion(cliente, {"materia": "Trabajo de Graduacion"}, KB_EJEMPLO)
    cliente.post(f"/consultas/{session_id}/hechos",
                 json={"hechos": {"promedio": 2.25}, "fc_hechos": {"promedio": 0.5}})
    memoria = cliente.post(f"/consultas/{session_id}/inferir").json()
    assert memoria["derived_facts"]["dictamen"]["certainty_factor"] == 0.5


@pytest.mark.parametrize("cuerpo, fragmento", [
    ({"fc_reglas": {"rule_99": 0.5}}, "rule_99"),
    ({"fc_hechos": {"edad": 0.5}}, "edad"),
])
def test_certezas_que_no_corresponden_a_la_base(cliente, cuerpo, fragmento):
    r = cliente.post("/consultas", json={"kb_id": KB_EJEMPLO, **cuerpo})
    assert r.status_code == 422
    assert fragmento in r.json()["errores"][0]


def test_certeza_fuera_de_rango(cliente):
    r = cliente.post("/consultas", json={"kb_id": KB_EJEMPLO, "fc_reglas": {"rule_01": 1.5}})
    assert r.status_code == 422
    session_id = nueva_sesion(cliente, {"materia": "Electiva"}, KB_EJEMPLO)
    r = cliente.post(f"/consultas/{session_id}/hechos",
                     json={"hechos": {"promedio": 2.0}, "fc_hechos": {"edad": 0.5}})
    assert r.status_code == 422
    assert cliente.get(f"/consultas/{session_id}/memoria").json()["facts"] == {"materia": "Electiva"}


def test_sin_g7_se_ignora_la_certeza():
    cliente = _cliente(ServicioESB(Integraciones(deshabilitar={"G7"})))
    try:
        session_id, memoria = consulta_con_certeza(cliente, {"rule_01": 0.8})
        assert "certainty_factor" not in memoria["derived_facts"]["dictamen"]
        assert cliente.get(f"/consultas/{session_id}/dictamen").json()["certainty_score"] == 1.0
    finally:
        app.dependency_overrides.clear()


# --- Auditoria de la base (G3) ---

class _ReporteFalso:
    def to_dict(self):
        return {"es_valida": True, "estado": "OK", "hallazgos": []}

    def to_markdown(self):
        return "# Reporte de auditoría\n"


class _AuditorFalso:
    """Imita la interfaz de KBAuditor de G3 (constructor y auditar())."""
    recibido = None

    def __init__(self, fuente, *, schema_manager=None, usar_schema_manager=True):
        _AuditorFalso.recibido = fuente

    def auditar(self):
        return _ReporteFalso()


def test_auditoria_sin_g3_responde_503():
    cliente = _cliente(ServicioESB(Integraciones(deshabilitar={"G3"})))
    try:
        assert cliente.get("/salud").json()["modulos"]["G3 KBAuditor"] == "simulado"
        r = cliente.get(f"/conocimiento/{KB_ACADEMICO}/auditoria")
        assert r.status_code == 503 and "G3" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_auditoria_delega_en_g3():
    integraciones = Integraciones()
    integraciones._g3 = _AuditorFalso
    cliente = _cliente(ServicioESB(integraciones))
    try:
        r = cliente.get(f"/conocimiento/{KB_ACADEMICO}/auditoria")
        assert r.status_code == 200 and r.json()["es_valida"] is True
        assert _AuditorFalso.recibido["meta"]["author_group"] == "Grupo 4 - Schema Manager"
        md = cliente.get(f"/conocimiento/{KB_ACADEMICO}/auditoria", params={"formato": "md"})
        assert md.text.startswith("# Reporte de auditoría")
        assert cliente.get("/conocimiento/kb_999/auditoria").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_auditoria_con_g3_real(cliente):
    if not hasattr(pytest.importorskip("grupo_03_auditor"), "KBAuditor"):
        pytest.skip("KBAuditor (G3) todavía no está en esta rama")
    r = cliente.get(f"/conocimiento/{KB_ACADEMICO}/auditoria")
    assert r.status_code == 200
    assert {"es_valida", "estado", "hallazgos", "tabla_decision"} <= set(r.json())


# --- Motor hacia atras (G6) ---

def sesion_atras(cliente, hechos=None):
    r = cliente.post("/consultas", json={"kb_id": KB_ACADEMICO, "motor": "atras",
                                         "hechos": hechos or {}})
    assert r.status_code == 201, r.json()
    return r.json()["session_id"]


def test_motor_atras_pregunta_solo_lo_necesario(cliente):
    session_id = sesion_atras(cliente)
    url = f"/consultas/{session_id}/siguiente-pregunta"
    preguntados = []
    respuestas = {"tipo_consulta": "Repeticion", "nota_obtenida": "D"}
    while not (pendiente := cliente.get(url).json())["completa"]:
        attr = pendiente["pregunta"]["attribute_id"]
        assert pendiente["explanation_why"].startswith(f"Se solicitó '{attr}'")
        preguntados.append(attr)
        cliente.post(f"/consultas/{session_id}/hechos", json={"hechos": {attr: respuestas[attr]}})
    assert preguntados == ["tipo_consulta", "nota_obtenida"]  # nunca pide puntaje_final

    memoria = cliente.post(f"/consultas/{session_id}/inferir").json()
    assert memoria["halted_reason"] == "derivado"
    assert memoria["derived_facts"]["dictamen"]["derived_by_rule"] == "reg_repeticion_d"
    dictamen = cliente.get(f"/consultas/{session_id}/dictamen").json()
    assert "reg_repeticion_d" in dictamen["explanation_why"]
    kb = cliente.get(f"/conocimiento/{KB_ACADEMICO}").json()
    assert VALIDADOR.validar_conjunto(kb, memoria, dictamen, "dictamen")["valido"]


def test_motor_atras_con_dato_faltante(cliente):
    session_id = sesion_atras(cliente, {"tipo_consulta": "Calificacion"})
    pendiente = cliente.get(f"/consultas/{session_id}/siguiente-pregunta").json()
    assert pendiente["pregunta"]["attribute_id"] == "puntaje_final"
    assert pendiente["pregunta"]["range"] == [0, 100]
    memoria = cliente.post(f"/consultas/{session_id}/inferir").json()
    assert memoria["halted_reason"] == "falta_dato" and memoria["derived_facts"] == {}
    assert cliente.get(f"/consultas/{session_id}/dictamen").status_code == 409


def test_motor_atras_y_adelante_coinciden(cliente):
    hechos = {"tipo_consulta": "Calificacion", "puntaje_final": 72}
    resultados = []
    for motor in ("adelante", "atras"):
        r = cliente.post("/consultas", json={"kb_id": KB_ACADEMICO, "motor": motor, "hechos": hechos})
        session_id = r.json()["session_id"]
        cliente.post(f"/consultas/{session_id}/inferir")
        resultados.append(cliente.get(f"/consultas/{session_id}/dictamen").json()["final_outcome"])
    assert resultados == ["Calificación C - Regular"] * 2


def test_motor_atras_con_certeza(cliente):
    r = cliente.post("/consultas", json={
        "kb_id": KB_EJEMPLO, "motor": "atras", "hechos": HECHOS_EJEMPLO,
        "fc_reglas": {"rule_01": 0.8}, "fc_hechos": {"promedio": 0.9}})
    session_id = r.json()["session_id"]
    memoria = cliente.post(f"/consultas/{session_id}/inferir").json()
    assert memoria["derived_facts"]["dictamen"]["certainty_factor"] == 0.72


# --- Persistencia de sesiones (G11) ---

class _AlmacenFalso:
    """Imita ESBConverter de G11 guardando en un diccionario."""
    guardadas: dict = {}

    def __init__(self, schema_manager=None, validate=True):
        pass

    def save_session_to_dir(self, session, directory, *, knowledge=None):
        _AlmacenFalso.guardadas[session["session_id"]] = copy.deepcopy(session)
        return directory / f"sesion_{session['session_id']}.json"

    def load_session_from_dir(self, directory, session_id, *, knowledge=None):
        if session_id not in _AlmacenFalso.guardadas:
            raise FileNotFoundError(session_id)
        return copy.deepcopy(_AlmacenFalso.guardadas[session_id])

    def list_sessions(self, directory):
        return sorted(_AlmacenFalso.guardadas)


class _G11Falso:
    ESBConverter = _AlmacenFalso

    class IncompatibleStructureError(ValueError):
        pass


def test_persistencia_sin_g11_responde_503(tmp_path):
    cliente = _cliente(ServicioESB(Integraciones(deshabilitar={"G11"}), carpeta_sesiones=tmp_path))
    try:
        assert cliente.get("/salud").json()["modulos"]["G11 ESBConverter"] == "simulado"
        session_id = nueva_sesion(cliente, {"tipo_consulta": "Calificacion"})
        r = cliente.post(f"/consultas/{session_id}/guardar")
        assert r.status_code == 503 and "G11" in r.json()["detail"]
        assert cliente.get("/sesiones-guardadas").status_code == 503
    finally:
        app.dependency_overrides.clear()


def _flujo_guardar_y_restaurar(cliente):
    session_id = consultar(cliente, {"tipo_consulta": "Calificacion", "puntaje_final": 95})
    r = cliente.post(f"/consultas/{session_id}/guardar")
    assert r.status_code == 200 and r.json()["ruta"].endswith(f"sesion_{session_id}.json")
    assert session_id in cliente.get("/sesiones-guardadas").json()
    return session_id


def test_guardar_y_restaurar_con_g11(tmp_path):
    _AlmacenFalso.guardadas = {}
    integraciones = Integraciones()
    integraciones._g11 = _G11Falso
    servicio = ServicioESB(integraciones, carpeta_sesiones=tmp_path)
    cliente = _cliente(servicio)
    try:
        session_id = _flujo_guardar_y_restaurar(cliente)
        url = f"/sesiones-guardadas/{session_id}/restaurar"
        assert cliente.post(url, json={"kb_id": KB_ACADEMICO}).status_code == 409  # sigue abierta

        otro = _cliente(ServicioESB(integraciones, carpeta_sesiones=tmp_path))
        r = otro.post(url, json={"kb_id": KB_ACADEMICO})
        assert r.status_code == 201 and r.json()["session_id"] == session_id
        assert otro.get(f"/consultas/{session_id}/dictamen").json()["final_outcome"] == DICTAMEN_A
        assert otro.post("/sesiones-guardadas/sess_x/restaurar",
                         json={"kb_id": KB_ACADEMICO}).status_code == 404
        assert otro.post(url, json={"kb_id": "kb_999"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_restaurar_no_choca_con_ids_nuevos(tmp_path):
    _AlmacenFalso.guardadas = {}
    integraciones = Integraciones()
    integraciones._g11 = _G11Falso
    cliente = _cliente(ServicioESB(integraciones, carpeta_sesiones=tmp_path))
    try:
        session_id = _flujo_guardar_y_restaurar(cliente)
        nuevo = _cliente(ServicioESB(integraciones, carpeta_sesiones=tmp_path))
        nuevo.post(f"/sesiones-guardadas/{session_id}/restaurar", json={"kb_id": KB_ACADEMICO})
        assert nueva_sesion(nuevo) != session_id
    finally:
        app.dependency_overrides.clear()


def test_persistencia_con_g11_real(tmp_path):
    if not hasattr(pytest.importorskip("grupo_11_storage"), "ESBConverter"):
        pytest.skip("ESBConverter (G11) todavía no está en esta rama")
    cliente = _cliente(ServicioESB(carpeta_sesiones=tmp_path))
    try:
        session_id = _flujo_guardar_y_restaurar(cliente)
        assert (tmp_path / f"sesion_{session_id}.json").is_file()
        otro = _cliente(ServicioESB(carpeta_sesiones=tmp_path))
        r = otro.post(f"/sesiones-guardadas/{session_id}/restaurar", json={"kb_id": KB_ACADEMICO})
        assert r.status_code == 201
        assert otro.get(f"/consultas/{session_id}/dictamen").json()["final_outcome"] == DICTAMEN_A
        r = otro.post("/sesiones-guardadas/sess_nada/restaurar", json={"kb_id": KB_ACADEMICO})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
