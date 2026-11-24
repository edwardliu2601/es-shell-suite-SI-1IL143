"""Pruebas de la consola de demostracion del Grupo 6."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from grupo_06_backward.esb_backward_cli import main

EJEMPLO = Path(__file__).resolve().parents[1] / "datos_ejemplo" / "conocimiento_encadenado.json"


def ejecutar(argumentos, respuestas):
    """Corre la consola con respuestas simuladas; devuelve (codigo, texto impreso)."""
    pendientes = iter(respuestas)
    impreso: list[str] = []
    codigo = main([str(a) for a in argumentos], entrada=lambda _: next(pendientes),
                  salida=impreso.append)
    return codigo, "\n".join(impreso)


def test_consulta_completa_y_guarda_la_memoria(tmp_path):
    destino = tmp_path / "memoria.json"
    codigo, texto = ejecutar([EJEMPLO, "--salida", destino],
                             ["Trabajo de Graduacion", "2,5", "150"])

    assert codigo == 0
    assert "dictamen = 'Elegible'" in texto
    assert "Paso 1: rule_04 agrego requisitos" in texto
    memoria = json.loads(destino.read_text(encoding="utf-8"))
    assert memoria["facts"]["promedio"] == 2.5
    assert memoria["derived_facts"]["dictamen"]["derived_by_rule"] == "rule_01"


def test_signo_de_interrogacion_muestra_el_why_y_vuelve_a_preguntar():
    codigo, texto = ejecutar([EJEMPLO], ["?", "Electiva"])
    assert codigo == 0
    assert "rule_01" in texto  # el WHY cita la regla que pide 'materia'


def test_respuesta_invalida_se_vuelve_a_preguntar():
    codigo, texto = ejecutar([EJEMPLO], ["Maestria", "Electiva"])
    assert codigo == 0
    assert "debe ser una de" in texto


def test_no_se_deja_la_meta_sin_concluir():
    # Sin promedio, el motor aun prueba otra regla que pregunta los creditos.
    codigo, texto = ejecutar([EJEMPLO], ["Trabajo de Graduacion", "no sé", ""])
    assert codigo == 1
    assert "No se pudo concluir" in texto


def test_hipotesis_y_razonamiento():
    codigo, texto = ejecutar([EJEMPLO, "--valor", "Elegible", "--razonamiento"], ["Electiva"])
    assert codigo == 0
    assert "Razonamiento" in texto and "Probando rule_02" in texto


def test_archivo_inexistente(tmp_path):
    codigo, texto = ejecutar([tmp_path / "no_existe.json"], [])
    assert codigo == 2 and "No se pudo leer" in texto


def test_meta_inexistente():
    codigo, texto = ejecutar([EJEMPLO, "--meta", "inventado"], [])
    assert codigo == 2 and "no existe" in texto
