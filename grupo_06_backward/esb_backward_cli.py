"""Consola de demostracion del BackwardEngine (Grupo 6).

Carga una base de conocimiento, pregunta los datos que hagan falta y muestra el
resultado, la traza y el razonamiento. En cada pregunta se puede escribir:

- ``?``       para ver por que se pide el dato (WHY);
- ``no se``   (o Enter) si no se conoce la respuesta.

Uso, desde la raiz del repositorio::

    python -m grupo_06_backward.esb_backward_cli grupo_06_backward/datos_ejemplo/conocimiento_encadenado.json
    python -m grupo_06_backward.esb_backward_cli KB.json --meta dictamen --valor Elegible --salida memoria.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from .esb_engine_backward import BackwardEngine, BackwardEngineError, InvalidAnswerError, Question

NO_SE = {"", "no se", "no sé", "ns"}


def _explicar_why(pregunta: Question, kb: dict) -> str:
    """Usa el XAIExplainer de G8 si esta disponible; si no, un texto simple."""
    if pregunta.rule_id is None:
        return f"Es el dato que se busca: '{pregunta.attribute_id}'."
    try:
        from grupo_08_explainer import XAIExplainer
        return XAIExplainer(kb).explain_why(pregunta.attribute_id, pregunta.rule_id)
    except (ImportError, ValueError):
        return f"Se necesita '{pregunta.attribute_id}' para evaluar la regla {pregunta.rule_id}."


def crear_preguntador(motor: BackwardEngine, kb: dict,
                      entrada: Callable[[str], str] = input,
                      salida: Callable[[str], None] = print):
    """Devuelve el ask_fn de la consola: muestra la pregunta y valida la respuesta."""

    def preguntar(pregunta: Question):
        salida(f"\n{pregunta.question}")
        if pregunta.options:
            salida("  Opciones: " + ", ".join(str(o) for o in pregunta.options))
        if pregunta.range:
            salida(f"  Rango: {pregunta.range[0]} a {pregunta.range[1]}")
        while True:
            texto = entrada("> ").strip()
            if texto == "?":
                salida("  " + _explicar_why(pregunta, kb))
                continue
            if texto.casefold() in NO_SE:
                return None
            try:
                return motor.validate_answer(pregunta.attribute_id, texto)
            except InvalidAnswerError as error:
                salida(f"  {error}")

    return preguntar


def main(argv: list[str] | None = None,
         entrada: Callable[[str], str] = input,
         salida: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(description="Consulta con encadenamiento hacia atras.")
    parser.add_argument("conocimiento", help="ruta de conocimiento_dominio.json")
    parser.add_argument("--meta", default="dictamen", help="atributo a verificar (por defecto: dictamen)")
    parser.add_argument("--valor", help="comprueba la hipotesis meta == valor")
    parser.add_argument("--memoria", help="memoria_trabajo.json de partida")
    parser.add_argument("--salida", help="guarda la memoria de trabajo resultante en este archivo")
    parser.add_argument("--razonamiento", action="store_true", help="muestra el razonamiento paso a paso")
    args = parser.parse_args(argv)

    try:
        kb = json.loads(Path(args.conocimiento).read_text(encoding="utf-8"))
        memoria = json.loads(Path(args.memoria).read_text(encoding="utf-8")) if args.memoria else None
        motor = BackwardEngine(kb)
        motor.ask_fn = crear_preguntador(motor, kb, entrada, salida)
        resultado = motor.prove(args.meta, args.valor, memoria)
    except (OSError, json.JSONDecodeError) as error:
        salida(f"No se pudo leer el archivo: {error}")
        return 2
    except BackwardEngineError as error:
        salida(f"Error: {error}")
        return 2

    salida("\n--- Resultado ---")
    if resultado.achieved:
        salida(f"{args.meta} = {resultado.value!r}")
    else:
        salida(f"No se pudo concluir '{args.meta}' ({resultado.reason}).")
    for paso in resultado.memory["execution_trace"]:
        salida(f"  Paso {paso['step']}: {paso['rule_fired']} agrego {paso['added_fact']}")
    if args.razonamiento:
        salida("\n--- Razonamiento ---")
        salida("\n".join(resultado.proof))
    if args.salida:
        Path(args.salida).write_text(
            json.dumps(resultado.memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        salida(f"\nMemoria de trabajo guardada en {args.salida}")
    return 0 if resultado.achieved else 1


if __name__ == "__main__":
    sys.exit(main())
