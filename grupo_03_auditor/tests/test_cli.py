"""Pruebas unitarias de la interfaz CLI del Grupo 3 (esb_auditor_cli.py)."""

from __future__ import annotations

import json
from pathlib import Path

from grupo_03_auditor.esb_auditor_cli import main

G3_EJEMPLOS = Path(__file__).resolve().parents[1] / "datos_ejemplo"


def test_cli_retorna_0_en_base_valida(capsys):
    codigo = main([str(G3_EJEMPLOS / "conocimiento_valido.json"), "--tabla-decision"])
    salida = capsys.readouterr().out

    assert codigo == 0
    assert "Estado    : VALIDA" in salida
    assert "Tabla de Decisión:" in salida
    assert "regla_beca_completa" in salida


def test_cli_retorna_1_en_base_con_errores_y_exporta_archivos(tmp_path, capsys):
    out_json = tmp_path / "salida.json"
    out_md = tmp_path / "salida.md"

    codigo = main(
        [
            str(G3_EJEMPLOS / "conocimiento_con_errores.json"),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
        ]
    )
    salida = capsys.readouterr().out

    assert codigo == 1
    assert "INVALIDA" in salida
    assert out_json.exists()
    assert out_md.exists()

    datos = json.loads(out_json.read_text(encoding="utf-8"))
    assert datos["es_valida"] is False
    assert datos["resumen"]["conteo_severidad"]["ERROR"] > 0
    assert "## Tabla de Decisión" in out_md.read_text(encoding="utf-8")


def test_cli_modo_estricto_con_advertencias(tmp_path):
    kb_warning = {
        "meta": {
            "project_title": "Solo advertencia",
            "version": "1.0",
            "author_group": "Grupo 3 - Test CLI",
        },
        "attributes": [
            {
                "id": "promedio",
                "name": "Promedio",
                "type": "numeric",
                "question": "¿Promedio?",
                "range": [0.0, 3.0],
            },
            {
                "id": "dictamen",
                "name": "Dictamen",
                "type": "categorical",
                "options": ["A", "B"],
            },
        ],
        "rules": [
            {
                "id": "r1",
                "description": "Alta prioridad",
                "priority": 20,
                "conditions": [{"attribute_id": "promedio", "operator": ">=", "value": 2.0}],
                "conclusion": {"attribute_id": "dictamen", "value": "A"},
                "explanation_template": "Alta.",
            },
            {
                "id": "r2",
                "description": "Baja prioridad solapada",
                "priority": 10,
                "conditions": [{"attribute_id": "promedio", "operator": ">=", "value": 2.5}],
                "conclusion": {"attribute_id": "dictamen", "value": "B"},
                "explanation_template": "Baja.",
            },
        ],
    }
    ruta = tmp_path / "warning.json"
    ruta.write_text(json.dumps(kb_warning), encoding="utf-8")

    assert main([str(ruta)]) == 0
    assert main([str(ruta), "--estricto"]) == 1


def test_cli_acepta_bandera_archivo_y_sin_schema(tmp_path):
    codigo = main(
        [
            "--archivo",
            str(G3_EJEMPLOS / "conocimiento_con_ciclos.json"),
            "--sin-schema",
        ]
    )
    assert codigo == 1

    codigo_inexistente = main([str(tmp_path / "faltante.json")])
    assert codigo_inexistente == 1
