"""Pruebas del Grupo 10: ESB_Interactive_UI.

Las respuestas del usuario se simulan con una lista; la salida de la consola
se captura en texto para revisar lo que vio el usuario.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from grupo_04_schema.esb_schema import SchemaManager
from grupo_10_ui import ESB_Interactive_UI, convertir_respuesta
from grupo_12_api.servicio import KB_ACADEMICO, KB_EJEMPLO, ContratoInvalido

CONTRATOS = Path(__file__).resolve().parents[2] / "contracts"

# Caso de prueba documentado (seccion 6 de la guia, ultimo punto).
CASO_A = {"tipo_consulta": "Calificacion", "puntaje_final": 95}
DICTAMEN_A = "Calificación A - Sobresaliente"


def crear_ui(respuestas: list[str], carpeta: Path | None = None):
    """UI con respuestas simuladas; devuelve (ui, funcion que lee la salida)."""
    pendientes = iter(respuestas)

    def entrada(_indicacion: str) -> str:
        try:
            return next(pendientes)
        except StopIteration:
            raise EOFError from None

    buffer = io.StringIO()
    consola = Console(file=buffer, width=200, color_system=None, force_terminal=False)
    ui = ESB_Interactive_UI(entrada=entrada, consola=consola,
                            carpeta_salida=carpeta or Path("no-usar"))
    return ui, buffer.getvalue


def base_una_regla(prioridades: dict[str, int] | None = None) -> dict:
    """Base minima de la seccion 4.2; con prioridades agrega reglas en conflicto."""
    base = {
        "meta": {"project_title": "Prueba G10", "version": "1.0", "author_group": "Grupo 10"},
        "attributes": [
            {"id": "promedio", "name": "Promedio", "type": "numeric",
             "question": "¿Cuál es el promedio?", "range": [0.0, 3.0]},
            {"id": "dictamen", "name": "Dictamen", "type": "text"},
        ],
        "rules": [],
    }
    for valor, prioridad in (prioridades or {"Elegible": 10}).items():
        base["rules"].append({
            "id": f"rule_{valor.lower()}", "description": valor, "priority": prioridad,
            "conditions": [{"attribute_id": "promedio", "operator": ">=", "value": 2.0}],
            "conclusion": {"attribute_id": "dictamen", "value": valor},
            "explanation_template": f"Concluye {valor}.",
        })
    return base


# --- Conversion de respuestas ---

@pytest.mark.parametrize("texto, pregunta, esperado", [
    ("95", {"type": "numeric"}, 95),
    ("2,25", {"type": "numeric"}, 2.25),
    ("Sí", {"type": "boolean"}, True),
    ("no", {"type": "boolean"}, False),
    ("2", {"type": "categorical", "options": ["Calificacion", "Repeticion"]}, "Repeticion"),
    ("repetición", {"type": "categorical", "options": ["Calificacion", "Repeticion"]}, "Repeticion"),
    ("hola", {"type": "text"}, "hola"),
])
def test_convierte_la_respuesta_al_tipo_del_atributo(texto, pregunta, esperado):
    assert convertir_respuesta(texto, pregunta) == esperado


@pytest.mark.parametrize("texto, pregunta", [
    ("abc", {"type": "numeric"}),
    ("tal vez", {"type": "boolean"}),
    ("   ", {"type": "text"}),
])
def test_rechaza_respuestas_con_formato_invalido(texto, pregunta):
    with pytest.raises(ValueError):
        convertir_respuesta(texto, pregunta)


# --- Uso programatico ---

def test_caso_documentado_puntaje_95_da_calificacion_a():
    ui, _ = crear_ui([])
    resultado = ui.consultar(KB_ACADEMICO, CASO_A)

    assert resultado["dictamen"]["final_outcome"] == DICTAMEN_A
    derivado = resultado["memoria"]["derived_facts"]["dictamen"]
    assert derivado["derived_by_rule"] == "reg_calificacion_a"
    assert any("reg_calificacion_a" in linea for linea in resultado["traza"])


def test_consulta_programatica_rechaza_datos_fuera_de_rango():
    ui, _ = crear_ui([])
    with pytest.raises(ContratoInvalido):
        ui.consultar(KB_ACADEMICO, {"tipo_consulta": "Calificacion", "puntaje_final": 150})


def test_si_ninguna_regla_se_activa_no_hay_dictamen():
    ui, _ = crear_ui([])
    kb_id, _ = ui.servicio.cargar_conocimiento(base_una_regla())
    resultado = ui.consultar(kb_id, {"promedio": 1.5})

    assert resultado["dictamen"] is None
    assert resultado["memoria"]["derived_facts"] == {}


def test_reglas_en_conflicto_gana_la_de_mayor_prioridad():
    ui, _ = crear_ui([])
    kb_id, _ = ui.servicio.cargar_conocimiento(
        base_una_regla({"Condicional": 5, "Elegible": 20}))
    resultado = ui.consultar(kb_id, {"promedio": 2.5})

    assert resultado["dictamen"]["final_outcome"] == "Elegible"


# --- Uso interactivo ---

def test_consulta_interactiva_completa_con_why_y_datos_invalidos():
    # base 1, opcion 1 (Calificacion), pide WHY, fuera de rango, texto, 95, salir
    ui, salida = crear_ui(["1", "1", "por qué", "150", "abc", "95", "5"])
    ui.ejecutar()
    texto = salida()

    assert "WHY: Se solicitó 'puntaje_final'" in texto
    assert "fuera del rango [0, 100]" in texto
    assert "'abc' no es un número." in texto
    assert DICTAMEN_A in texto
    assert "Paso 1: reg_calificacion_a" in texto
    assert "Hasta luego." in texto


def test_repeticion_con_nota_d_escrita_a_mano():
    ui, salida = crear_ui(["1", "repeticion", "d", "5"])
    ui.ejecutar()

    assert "La calificación D cumple el criterio" in salida()


def test_opcion_inexistente_vuelve_a_preguntar():
    ui, salida = crear_ui(["1", "Matricula", "1", "95", "5"])
    ui.ejecutar()
    texto = salida()

    assert "Respuesta no válida." in texto
    assert DICTAMEN_A in texto


def test_solo_pregunta_lo_necesario():
    # Con "Repeticion" no debe pedirse el puntaje final.
    ui, salida = crear_ui(["1", "2", "A", "5"])
    ui.ejecutar()

    assert "puntaje final" not in salida()


def test_salir_en_medio_de_la_consulta_termina_sin_error():
    ui, salida = crear_ui(["1", "salir"])
    ui.ejecutar()

    assert "Hasta luego." in salida()


def test_fin_de_entrada_termina_sin_error():
    ui, salida = crear_ui(["2"])  # luego Ctrl+D
    ui.ejecutar()

    assert "Hasta luego." in salida()


def test_sin_dictamen_muestra_aviso_y_no_ofrece_reporte(tmp_path):
    ruta = tmp_path / "base.json"
    ruta.write_text(json.dumps(base_una_regla()), encoding="utf-8")
    ui, salida = crear_ui(["a", str(ruta), "1.5", "5"])
    ui.ejecutar()
    texto = salida()

    assert "Sin dictamen" in texto
    assert "Exportar reporte" not in texto


# --- Carga de bases ---

def test_carga_base_valida_desde_archivo(tmp_path):
    ruta = tmp_path / "base.json"
    ruta.write_text(json.dumps(base_una_regla()), encoding="utf-8")
    ui, _ = crear_ui([])

    kb_id = ui.cargar_base(str(ruta))
    assert kb_id in ui.bases


def test_base_invalida_muestra_errores_de_g4(tmp_path):
    base = base_una_regla()
    del base["rules"]
    ruta = tmp_path / "base.json"
    ruta.write_text(json.dumps(base), encoding="utf-8")
    ui, salida = crear_ui([])

    assert ui.cargar_base(str(ruta)) is None
    assert "no cumple el contrato" in salida()


@pytest.mark.parametrize("contenido", [None, "{no es json"])
def test_archivo_inexistente_o_roto_no_rompe_la_ui(tmp_path, contenido):
    ruta = tmp_path / "base.json"
    if contenido is not None:
        ruta.write_text(contenido, encoding="utf-8")
    ui, _ = crear_ui([])

    assert ui.cargar_base(str(ruta)) is None


# --- Exportacion ---

def test_json_exportados_cumplen_los_contratos(tmp_path):
    ui, _ = crear_ui([], carpeta=tmp_path)
    resultado = ui.consultar(KB_ACADEMICO, CASO_A)
    rutas = ui.guardar_json(resultado)

    gestor = SchemaManager(carpeta_esquemas=str(CONTRATOS))
    for ruta in rutas:
        tipo = ruta.stem
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        validacion = gestor.validar_datos(datos, tipo)
        assert validacion["valido"], validacion["errores"]
    assert {r.name for r in rutas} == {"memoria_trabajo.json", "dictamen_salida.json"}


@pytest.mark.parametrize("formato", ["md", "html"])
def test_exporta_reporte(tmp_path, formato):
    ui, _ = crear_ui([], carpeta=tmp_path)
    resultado = ui.consultar(KB_EJEMPLO, {"materia": "Trabajo de Graduacion", "promedio": 2.25})
    ruta = ui.exportar_reporte(resultado, formato)

    assert ruta.suffix == f".{formato}"
    assert "Elegible" in ruta.read_text(encoding="utf-8")
