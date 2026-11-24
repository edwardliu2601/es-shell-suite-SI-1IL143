"""Pruebas del generador de reportes con los contratos"""

import json

import pytest

from grupo_09_reporter import ReportGenerator

KB = {
    "meta": {"project_title": "Sistema Experto de Evaluacion Academica UTP",
             "version": "1.0", "author_group": "Grupo 4 - Schema Manager"},
    "attributes": [
        {"id": "promedio", "name": "Promedio Ponderado Acumulado", "type": "numeric",
         "question": "¿Cuál es el promedio ponderado del estudiante?", "range": [0.0, 3.0]},
        {"id": "materia", "name": "Tipo de Asignatura Solicitada", "type": "categorical",
         "question": "Seleccione el tipo de asignatura:",
         "options": ["Obligatoria", "Electiva", "Trabajo de Graduacion"]},
    ],
    "rules": [{
        "id": "rule_01", "description": "Elegibilidad para un trámite", "priority": 10,
        "conditions": [
            {"attribute_id": "materia", "operator": "==", "value": "Trabajo de Graduacion"},
            {"attribute_id": "promedio", "operator": ">=", "value": 2.0}],
        "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
        "explanation_template": "El promedio cumple el mínimo requerido."}],
}
WM = {
    "session_id": "sess_2026_10123",
    "facts": {"materia": "Trabajo de Graduacion", "promedio": 2.25},
    "derived_facts": {"dictamen": {"value": "Elegible", "derived_by_rule": "rule_01",
                                   "certainty_factor": 1.0, "timestamp": "2026-10-23T10:15:00Z"}},
    "execution_trace": [{"step": 1, "rule_fired": "rule_01", "added_fact": "dictamen"}],
}
DICTAMEN = {
    "session_id": "sess_2026_10123", "final_outcome": "Elegible", "certainty_score": 1.0,
    "explanation_how": ["Se determinó 'Elegible' debido a la regla rule_01.",
                        "Premisa 1: materia == 'Trabajo de Graduacion' (Verificado)",
                        "Premisa 2: promedio >= 2.0 (Valor ingresado: 2.25)"],
    "explanation_why": "Se solicitó 'promedio' para evaluar la condición de la regla rule_01.",
}


def escribir(carpeta, nombre, datos):
    ruta = carpeta / nombre
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


@pytest.fixture
def rutas(tmp_path):
    return (escribir(tmp_path, "conocimiento_dominio.json", KB),
            escribir(tmp_path, "memoria_trabajo.json", WM),
            escribir(tmp_path, "dictamen_salida.json", DICTAMEN))


# Casos normales

def test_informe_completo(rutas):
    texto = ReportGenerator(*rutas).generar_markdown()
    assert texto.startswith("# Dictamen sess_2026_10123")
    assert "**Sistema experto:** Sistema Experto de Evaluacion Academica UTP" in texto
    assert "**Resultado:** Elegible" in texto
    assert "**Nivel de certeza:** 1.0" in texto
    assert "Promedio Ponderado Acumulado (promedio): 2.25" in texto
    assert "dictamen: Elegible, regla rule_01, certeza 1.0" in texto
    assert "### Paso 1: rule_01" in texto
    assert "Elegibilidad para un trámite" in texto
    assert "Premisa 2: promedio >= 2.0 (Valor ingresado: 2.25)" in texto
    assert "## Advertencias" not in texto


def test_guardar_reporte(rutas, tmp_path):
    destino = ReportGenerator(*rutas).guardar_reporte(tmp_path / "salida" / "informe.md")
    assert destino.read_text(encoding="utf-8").startswith("# Dictamen sess_2026_10123")


def test_solo_con_dictamen(tmp_path):
    ruta = escribir(tmp_path, "dictamen_salida.json", DICTAMEN)
    texto = ReportGenerator(ruta_dictamen=ruta).generar_markdown()
    assert "**Resultado:** Elegible" in texto
    assert "_No hay datos ingresados registrados._" in texto


def test_sin_certeza_ni_campos_opcionales(tmp_path):
    ruta = escribir(tmp_path, "d.json", {"session_id": "s1", "final_outcome": "No elegible"})
    texto = ReportGenerator(ruta_dictamen=ruta).generar_markdown()
    assert "Nivel de certeza" not in texto
    assert "_No hay explicación disponible._" in texto


def test_explicaciones_como_texto(tmp_path):
    ruta = escribir(tmp_path, "d.json", {"session_id": "s1", "final_outcome": "X",
                                         "explanation_how": "Una sola línea",
                                         "explanation_why": ["Parte 1", "Parte 2"]})
    texto = ReportGenerator(ruta_dictamen=ruta).generar_markdown()
    assert "Una sola línea" in texto
    assert "Parte 1 Parte 2" in texto


# Datos inválidos

def test_archivo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        ReportGenerator(ruta_dictamen=tmp_path / "no_existe.json").generar_markdown()


def test_json_invalido(tmp_path):
    ruta = tmp_path / "dictamen_salida.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(ValueError, match="no es un JSON válido"):
        ReportGenerator(ruta_dictamen=ruta).generar_markdown()


def test_json_que_no_es_objeto(tmp_path):
    ruta = tmp_path / "dictamen_salida.json"
    ruta.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="objeto JSON"):
        ReportGenerator(ruta_dictamen=ruta).generar_markdown()


def test_sin_ruta_de_dictamen():
    with pytest.raises(ValueError, match="dictamen_salida.json"):
        ReportGenerator().generar_markdown()


# Reglas que no se activan o entran en conflicto

def test_ninguna_regla_activada(tmp_path):
    wm = {"session_id": "s1", "facts": {"promedio": 1.0}, "derived_facts": {}, "execution_trace": []}
    d = {"session_id": "s1", "final_outcome": "Sin conclusión"}
    texto = ReportGenerator(escribir(tmp_path, "k.json", KB), escribir(tmp_path, "m.json", wm),
                            escribir(tmp_path, "d.json", d)).generar_markdown()
    assert "_No se activó ninguna regla._" in texto
    assert "_No se derivó ningún hecho._" in texto


def test_advertencia_por_sesiones_distintas(tmp_path):
    d = dict(DICTAMEN, session_id="otra_sesion")
    texto = ReportGenerator(escribir(tmp_path, "k.json", KB), escribir(tmp_path, "m.json", WM),
                            escribir(tmp_path, "d.json", d)).generar_markdown()
    assert "## Advertencias" in texto
    assert "no coincide" in texto


def test_advertencia_por_regla_desconocida(tmp_path):
    wm = dict(WM, execution_trace=[{"step": 1, "rule_fired": "rule_99", "added_fact": "dictamen"}])
    texto = ReportGenerator(escribir(tmp_path, "k.json", KB), escribir(tmp_path, "m.json", wm),
                            escribir(tmp_path, "d.json", DICTAMEN)).generar_markdown()
    assert "rule_99" in texto
    assert "no está en la base de conocimiento" in texto
