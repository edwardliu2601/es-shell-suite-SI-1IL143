"""Escenario de demostracion obligatorio (seccion 6 de la guia) recorrido por HTTP.

Caso documentado: un estudiante consulta su calificacion con puntaje final 95.
Resultado esperado: dictamen "Calificación A - Sobresaliente" por la regla
reg_calificacion_a, con certeza 1.0.

Se ejecuta desde la raiz del repositorio con:
    python -m pytest grupo_12_api/tests/test_e2e.py -v
"""

import json

from fastapi.testclient import TestClient

from grupo_04_schema.esb_schema import SchemaManager
from grupo_12_api.adaptadores import CONTRATOS
from grupo_12_api.esb_api import app, obtener_servicio
from grupo_12_api.servicio import RUTA_KB_ACADEMICO, ServicioESB

ESPERADO = {
    "final_outcome": "Calificación A - Sobresaliente",
    "regla": "reg_calificacion_a",
    "certainty_score": 1.0,
}


def test_escenario_obligatorio_de_la_demo():
    servicio = ServicioESB(precargar_ejemplos=False)
    app.dependency_overrides[obtener_servicio] = lambda: servicio
    cliente = TestClient(app)
    validador = SchemaManager(carpeta_esquemas=CONTRATOS)
    try:
        # 1. Cargar la base de conocimiento desde el contrato acordado.
        kb = json.loads(RUTA_KB_ACADEMICO.read_text(encoding="utf-8"))
        r = cliente.post("/conocimiento", json=kb)
        assert r.status_code == 201
        kb_id = r.json()["kb_id"]

        # 2. Iniciar una consulta y pedir los datos requeridos de forma programatica.
        session_id = cliente.post("/consultas", json={"kb_id": kb_id}).json()["session_id"]
        url_pregunta = f"/consultas/{session_id}/siguiente-pregunta"
        respuestas = {"tipo_consulta": "Calificacion", "puntaje_final": 95}
        preguntados = []
        while not (pendiente := cliente.get(url_pregunta).json())["completa"]:
            atributo = pendiente["pregunta"]["attribute_id"]
            preguntados.append(atributo)
            if atributo not in respuestas:
                break

            # 3. Registrar los datos ingresados en la memoria de trabajo.
            r = cliente.post(f"/consultas/{session_id}/hechos",
                             json={"hechos": {atributo: respuestas[atributo]}})
            assert r.status_code == 200
        assert preguntados == ["tipo_consulta", "puntaje_final"]
        memoria = cliente.get(f"/consultas/{session_id}/memoria").json()
        assert memoria["facts"] == respuestas

        # 4. Activar las reglas y generar un hecho derivado.
        memoria = cliente.post(f"/consultas/{session_id}/inferir").json()
        assert memoria["derived_facts"]["dictamen"]["derived_by_rule"] == ESPERADO["regla"]
        assert validador.validar_memoria(memoria, kb)["valido"]

        # 5. Mostrar la traza con las reglas aplicadas.
        traza = cliente.get(f"/consultas/{session_id}/traza").json()["pasos"]
        assert traza == [f"Paso 1: {ESPERADO['regla']} agregó dictamen = "
                         f"{ESPERADO['final_outcome']!r}"]

        # 6. Responder una pregunta HOW y una WHY.
        how = cliente.get(f"/consultas/{session_id}/explicacion/how").json()["explanation_how"]
        assert how[0] == (f"Se determinó {ESPERADO['final_outcome']!r} debido a la regla "
                          f"{ESPERADO['regla']}.")
        why = cliente.get(f"/consultas/{session_id}/explicacion/why",
                          params={"atributo": "puntaje_final", "regla": ESPERADO["regla"]}).json()
        assert why["explanation_why"].startswith("Se solicitó 'puntaje_final'")

        # 7. Presentar el dictamen final y exportar el reporte.
        dictamen = cliente.get(f"/consultas/{session_id}/dictamen").json()
        reporte = cliente.get(f"/consultas/{session_id}/reporte").text
        assert ESPERADO["final_outcome"] in reporte

        # 8. Validar el resultado frente al caso de prueba documentado.
        assert dictamen["final_outcome"] == ESPERADO["final_outcome"]
        assert dictamen["certainty_score"] == ESPERADO["certainty_score"]
        assert dictamen["explanation_how"] == how
        assert validador.validar_conjunto(kb, memoria, dictamen, "dictamen")["valido"]
    finally:
        app.dependency_overrides.clear()
