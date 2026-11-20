"""Menú de demostración del editor de reglas (Grupo 2).

Ejecutar desde la raíz del repositorio:
    python -m grupo_02_rules.esb_rules_cli --archivo RUTA_JSON

Solo edita la sección rules; los cambios se guardan cuando se elige Guardar.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .esb_rules import RuleEditor, RuleEditorError, OPERADORES


def _elegir_atributo(editor: RuleEditor, *, permitir_nuevo: bool = False) -> str:
    attrs = editor.data["attributes"]
    print("Atributos disponibles:")
    for a in attrs:
        print(f"  {a['id']} ({a['type']}) - {a.get('name', '')}")
    if permitir_nuevo:
        print("  Se permite un identificador nuevo para un hecho derivado.")
    identificador = input("Identificador del atributo: ").strip()
    conocidos = {a["id"] for a in attrs}
    if not identificador or (identificador not in conocidos and not permitir_nuevo):
        raise RuleEditorError("Se debe indicar un identificador de atributo válido.")
    return identificador


def _valor(editor: RuleEditor, aid: str, op: str = "=="):
    attr = next((a for a in editor.data["attributes"] if a["id"] == aid), None)
    kind = attr.get("type") if attr else "text"
    if attr and kind == "categorical":
        print("Opciones:", ", ".join(map(str, attr.get("options", []))))

    def convertir(raw: str):
        if kind == "numeric":
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuleEditorError("Se esperaba un número JSON válido.") from exc
        if kind == "boolean":
            if raw.lower() in ("true", "verdadero"):
                return True
            if raw.lower() in ("false", "falso"):
                return False
            raise RuleEditorError("Para boolean, escriba true o false.")
        return raw

    if op == "in":
        entrada = input("Valores separados por coma, o un arreglo JSON: ").strip()
        if entrada.startswith("["):
            try:
                valores = json.loads(entrada)
            except json.JSONDecodeError as exc:
                raise RuleEditorError("La lista JSON no es válida.") from exc
            return valores
        return [convertir(x.strip()) for x in entrada.split(",") if x.strip()]
    return convertir(input(f"Valor ({kind}): ").strip())


def _condiciones(editor: RuleEditor) -> list[dict]:
    condiciones = []
    while True:
        aid = _elegir_atributo(editor)
        operador = input(f"Operador {', '.join(sorted(OPERADORES))}: ").strip()
        if operador not in OPERADORES:
            raise RuleEditorError(f"Operador no permitido: {operador!r}.")
        condiciones.append({
            "attribute_id": aid,
            "operator": operador,
            "value": _valor(editor, aid, operador),
        })
        if input("¿Agregar otra condición? (s/N): ").strip().lower() not in ("s", "si", "sí"):
            return condiciones


def _conclusion(editor: RuleEditor) -> dict:
    aid = _elegir_atributo(editor, permitir_nuevo=True)
    return {"attribute_id": aid, "value": _valor(editor, aid)}


def _mostrar(editor: RuleEditor) -> None:
    reglas = editor.list_rules()
    if not reglas:
        print("No hay reglas registradas.")
        return
    for regla in reglas:
        print(f"  {regla['id']} | prioridad {regla['priority']} | {regla['description']}")
        for c in regla["conditions"]:
            print(f"    SI {c['attribute_id']} {c['operator']} {c['value']}")
        print("    ENTONCES", regla["conclusion"])
        print("    Explicación:", regla["explanation_template"])


def _crear(editor: RuleEditor) -> None:
    regla = {
        "id": input("Identificador de la nueva regla: ").strip(),
        "description": input("Descripción: ").strip(),
        "priority": int(input("Prioridad (entero; mayor tiene preferencia): ").strip()),
        "conditions": _condiciones(editor),
        "conclusion": _conclusion(editor),
        "explanation_template": input("Mensaje explicativo: ").strip(),
    }
    editor.create_rule(regla)
    print("Regla creada en memoria; use Guardar para persistirla.")


def _editar(editor: RuleEditor) -> None:
    rid = input("Identificador de la regla a editar: ").strip()
    if not rid:
        raise RuleEditorError("Identificador vacío.")
    print("1) Descripción  2) Prioridad  3) Condiciones  4) Conclusión  5) Explicación")
    eleccion = input("Campo: ").strip()
    if eleccion == "1":
        changes = {"description": input("Nueva descripción: ").strip()}
    elif eleccion == "2":
        changes = {"priority": int(input("Nueva prioridad: ").strip())}
    elif eleccion == "3":
        changes = {"conditions": _condiciones(editor)}
    elif eleccion == "4":
        changes = {"conclusion": _conclusion(editor)}
    elif eleccion == "5":
        changes = {"explanation_template": input("Nueva explicación: ").strip()}
    else:
        raise RuleEditorError("Opción de edición no válida.")
    editor.edit_rule(rid, changes)
    print("Regla modificada en memoria.")


def ejecutar_menu(editor: RuleEditor) -> RuleEditor:
    """Ejecuta el menú; recibe el editor para facilitar las pruebas unitarias."""
    opciones = {
        "1": ("Listar reglas", lambda: _mostrar(editor)),
        "2": ("Crear regla", lambda: _crear(editor)),
        "3": ("Editar regla", lambda: _editar(editor)),
        "4": ("Eliminar regla", lambda: editor.delete_rule(
            input("Identificador de la regla a eliminar: ").strip())),
        "5": ("Validar reglas", lambda: print(json.dumps(
            editor.validate_rules(), ensure_ascii=False, indent=2))),
        "6": ("Guardar reglas", editor.save_rules),
        "7": ("Recargar reglas (descartar cambios sin guardar)", editor.load_rules),
    }
    while True:
        print("\n=== Grupo 2 | Editor IF-THEN y prioridades ===")
        for key, (titulo, _) in opciones.items():
            print(f"{key}) {titulo}")
        print("0) Salir")
        try:
            entrada = input("Opción: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSalida sin guardado automático.")
            return editor
        if entrada == "0":
            print("Salida sin guardado automático.")
            return editor
        if entrada not in opciones:
            print("Opción no reconocida.")
            continue
        try:
            opciones[entrada][1]()
            if entrada == "6":
                print("Reglas guardadas correctamente.")
        except (RuleEditorError, KeyError, ValueError, OSError) as exc:
            print(f"Error: {exc}")
        except (KeyboardInterrupt, EOFError):
            print("\nOperación cancelada.")


def main() -> int:
    ejemplo = Path(__file__).parent / "datos_ejemplo" / "conocimiento_dominio.json"
    parser = argparse.ArgumentParser(description="Editor de reglas del Grupo 2")
    parser.add_argument("--archivo", type=Path, default=ejemplo,
                        help="Ruta al conocimiento_dominio.json que se editará")
    parser.add_argument("--sin-schema", action="store_true",
                        help="No ejecutar SchemaManager en guardado (solo para desarrollo)")
    args = parser.parse_args()
    schema_manager = None
    if not args.sin_schema:
        try:
            from grupo_04_schema.esb_schema import SchemaManager
            schema_manager = SchemaManager()
        except ImportError as exc:
            parser.error(f"Instale las dependencias del Grupo 4 (jsonschema): {exc}")
    try:
        editor = RuleEditor(args.archivo, schema_manager=schema_manager)
    except RuleEditorError as exc:
        parser.error(str(exc))
    ejecutar_menu(editor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
