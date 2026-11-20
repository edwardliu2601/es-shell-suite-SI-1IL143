"""Grupo 2: editor IF-THEN y prioridades, compatible con los esquemas del repositorio (G4).

No ejecuta reglas. Python >= 3.11, sin dependencias externas para su lógica interna.
Firmas públicas provisionales: deben aprobarse entre los representantes.
"""
from __future__ import annotations

import copy
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

OPERADORES = {"==", "!=", ">", "<", ">=", "<=", "in"}
OPERADORES_ORDEN = {">", "<", ">=", "<="}
TIPOS = {"numeric", "categorical", "boolean", "text"}
CAMPOS = {"id", "description", "priority", "conditions", "conclusion", "explanation_template"}


class RuleEditorError(ValueError):
    """Error controlado del editor de reglas."""


class RuleEditor:
    """Administra las reglas de un conocimiento_dominio.json existente.

    Los cambios se mantienen en memoria hasta llamar a save_rules().
    schema_manager es una instancia OPCIONAL que expone validar_datos(datos, tipo).
    """

    def __init__(self, json_path: str | Path, schema_manager: Any = None):
        self.path = Path(json_path)
        self.schema_manager = schema_manager
        self.data = {}
        self._snapshot_rules = []
        self.load_rules()

    @staticmethod
    def _reject_constant(value: str):
        """Evita NaN/Infinity, que Python acepta pero JSON estándar prohíbe."""
        raise ValueError(f"Constante JSON no válida: {value}")

    def _read(self) -> dict:
        try:
            with self.path.open(encoding="utf-8-sig") as f:
                obj = json.load(f, parse_constant=self._reject_constant)
        except (OSError, UnicodeError, ValueError) as exc:
            raise RuleEditorError(f"No se pudo leer {self.path}: {exc}") from exc
        if not isinstance(obj, dict):
            raise RuleEditorError("La raíz del JSON debe ser un objeto.")
        for key, expected in (("meta", dict), ("attributes", list), ("rules", list)):
            if not isinstance(obj.get(key), expected):
                raise RuleEditorError(f"El campo '{key}' debe ser {expected.__name__}.")
        return obj

    def load_rules(self) -> list[dict]:
        """Vuelve a leer el archivo, descartando cambios sin guardar."""
        self.data = self._read()
        self._snapshot_rules = copy.deepcopy(self.data["rules"])
        return self.list_rules()

    def list_rules(self) -> list[dict]:
        return copy.deepcopy(self.data["rules"])

    def _index(self, rule_id: str) -> int:
        for i, rule in enumerate(self.data["rules"]):
            if isinstance(rule, dict) and rule.get("id") == rule_id:
                return i
        raise KeyError(f"No existe la regla '{rule_id}'.")

    def get_rule(self, rule_id: str) -> dict:
        return copy.deepcopy(self.data["rules"][self._index(rule_id)])

    @staticmethod
    def _number(value: Any) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        return isinstance(value, float) and math.isfinite(value)

    def _check_value(self, attr: dict, value: Any, where: str,
                     errors: list[str], warnings: list[str]) -> None:
        kind = attr.get("type")
        if kind not in TIPOS:
            errors.append(f"{where}: tipo de atributo desconocido {kind!r}.")
        elif kind == "numeric":
            if not self._number(value):
                errors.append(f"{where}: el valor debe ser numérico y finito.")
            else:
                bounds = attr.get("range")
                if (isinstance(bounds, list) and len(bounds) == 2
                    and all(self._number(x) for x in bounds)
                    and bounds[0] <= bounds[1]
                    and not bounds[0] <= value <= bounds[1]):
                    warnings.append(f"{where}: {value} está fuera del rango {bounds}.")
        elif kind == "categorical":
            if not isinstance(value, str):
                errors.append(f"{where}: el valor categórico debe ser texto.")
            else:
                options = attr.get("options")
                if isinstance(options, list) and options:
                    if value not in options:
                        errors.append(f"{where}: {value!r} no está en las opciones {options}.")
                else:
                    warnings.append(f"{where}: atributo categórico sin opciones declaradas.")
        elif kind == "boolean" and not isinstance(value, bool):
            errors.append(f"{where}: el valor debe ser true o false.")
        elif kind == "text" and not isinstance(value, str):
            errors.append(f"{where}: el valor debe ser texto.")

    def validate_rule(self, rule: Any, exclude_rule_id: str | None = None,
                      *, data: dict | None = None) -> dict:
        """Devuelve {'valido': bool, 'errores': list, 'advertencias': list}."""
        errors, warnings = [], []
        if not isinstance(rule, dict):
            return {"valido": False, "errores": ["La regla debe ser un objeto."],
                    "advertencias": []}
        doc = self.data if data is None else data
        attrs = {a["id"]: a for a in doc["attributes"]
                 if isinstance(a, dict) and isinstance(a.get("id"), str)}
        missing = CAMPOS - rule.keys()
        if missing:
            errors.append("Faltan campos: " + ", ".join(sorted(missing)))
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid.strip():
            errors.append("'id' debe ser texto no vacío.")
        elif any(isinstance(r, dict) and r.get("id") == rid
                 and rid != exclude_rule_id for r in doc["rules"]):
            errors.append(f"El identificador '{rid}' ya existe.")
        if "description" in rule and (
            not isinstance(rule["description"], str) or not rule["description"].strip()
        ):
            errors.append("'description' debe ser texto no vacío.")
        if "explanation_template" in rule and not isinstance(rule["explanation_template"], str):
            errors.append("'explanation_template' debe ser texto.")
        if not isinstance(rule.get("priority"), int) or isinstance(rule.get("priority"), bool):
            errors.append("'priority' debe ser un entero.")
        conditions = rule.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            errors.append("'conditions' debe ser lista no vacía.")
        else:
            for i, cond in enumerate(conditions, 1):
                where = f"Condición {i}"
                if not isinstance(cond, dict):
                    errors.append(f"{where}: debe ser objeto.")
                    continue
                aid, op = cond.get("attribute_id"), cond.get("operator")
                if not isinstance(aid, str) or aid not in attrs:
                    errors.append(f"{where}: atributo {aid!r} no declarado.")
                    continue
                if not isinstance(op, str) or op not in OPERADORES:
                    errors.append(f"{where}: operador {op!r} no válido.")
                elif op in OPERADORES_ORDEN and attrs[aid].get("type") != "numeric":
                    errors.append(f"{where}: {op!r} solo admite numeric.")
                if "value" not in cond:
                    errors.append(f"{where}: falta 'value'.")
                elif op == "in":
                    values = cond["value"]
                    if not isinstance(values, list) or not values:
                        errors.append(f"{where}: 'in' requiere una lista no vacía.")
                    else:
                        for j, item in enumerate(values):
                            self._check_value(attrs[aid], item, f"{where}.value[{j}]",
                                              errors, warnings)
                elif isinstance(cond["value"], list):
                    errors.append(f"{where}: el operador {op!r} no admite una lista.")
                else:
                    self._check_value(attrs[aid], cond["value"], where, errors, warnings)
        conclusion = rule.get("conclusion")
        if not isinstance(conclusion, dict):
            errors.append("'conclusion' debe ser un objeto.")
        else:
            aid = conclusion.get("attribute_id")
            if not isinstance(aid, str) or not aid.strip():
                errors.append("Conclusión: 'attribute_id' no puede estar vacío.")
            elif aid not in attrs:
                warnings.append(f"Conclusión: atributo nuevo '{aid}'; se recomienda declararlo.")
            if "value" not in conclusion:
                errors.append("Conclusión: falta 'value'.")
            elif isinstance(aid, str) and aid in attrs:
                self._check_value(attrs[aid], conclusion["value"],
                                  "Conclusión", errors, warnings)
        try:
            json.dumps(rule, allow_nan=False)
        except (TypeError, ValueError):
            errors.append("La regla contiene valores no serializables en JSON.")
        return {"valido": not errors, "errores": errors, "advertencias": warnings}

    @staticmethod
    def _require_valid(result: dict) -> None:
        if not result["valido"]:
            raise RuleEditorError("Regla inválida: " + "; ".join(result["errores"]))

    def create_rule(self, rule: dict) -> dict:
        """Agrega una regla EN MEMORIA; después llamar a save_rules()."""
        self._require_valid(self.validate_rule(rule))
        new = copy.deepcopy(rule)
        self.data["rules"].append(new)
        return copy.deepcopy(new)

    def edit_rule(self, rule_id: str, changes: dict) -> dict:
        """Edita campos de una regla. No permite renombrar su id."""
        if not isinstance(changes, dict):
            raise RuleEditorError("'changes' debe ser un diccionario.")
        if "id" in changes and changes["id"] != rule_id:
            raise RuleEditorError("No se permite cambiar el id de una regla existente.")
        index = self._index(rule_id)
        new = copy.deepcopy(self.data["rules"][index])
        new.update(copy.deepcopy(changes))
        self._require_valid(self.validate_rule(new, exclude_rule_id=rule_id))
        self.data["rules"][index] = new
        return copy.deepcopy(new)

    def set_priority(self, rule_id: str, priority: int) -> dict:
        """Asigna un entero, sin resolver cómo se ejecutan las reglas en conflicto."""
        return self.edit_rule(rule_id, {"priority": priority})

    def delete_rule(self, rule_id: str) -> None:
        """Elimina una regla en memoria; no elimina trazas históricas."""
        self.data["rules"].pop(self._index(rule_id))

    def save_rules(self) -> None:
        """Guarda únicamente 'rules'; conserva los demás cambios en disco.

        Usa escritura atómica y evita reemplazar una lista de reglas modificada
        externamente desde la última carga. No implementa bloqueo multiproceso.
        """
        current = self._read()
        if current["rules"] != self._snapshot_rules:
            raise RuleEditorError(
                "Las reglas cambiaron en disco; no se sobrescriben cambios externos. "
                "Recarga con load_rules() y vuelve a aplicar tus cambios."
            )
        output = copy.deepcopy(current)
        output["rules"] = copy.deepcopy(self.data["rules"])
        # El esquema del G4 exige rules con al menos una regla al validar.
        if not output["rules"]:
            raise RuleEditorError(
                "El contrato actual exige una regla como mínimo al guardar. "
                "Agrega una regla o acuerda un cambio de contrato con G4."
            )
        ids = []
        for r in output["rules"]:
            if isinstance(r, dict) and isinstance(r.get("id"), str):
                ids.append(r["id"])
        if len(ids) != len(set(ids)):
            raise RuleEditorError("Existen identificadores de reglas duplicados.")
        for rule in output["rules"]:
            self._require_valid(self.validate_rule(
                rule, exclude_rule_id=rule.get("id") if isinstance(rule, dict) else None,
                data=output))
        if self.schema_manager is not None:
            fn = getattr(self.schema_manager, "validar_datos", None)
            if not callable(fn):
                raise RuleEditorError("SchemaManager no expone validar_datos().")
            verdict = fn(output, "conocimiento_dominio")
            if not isinstance(verdict, dict) or verdict.get("valido") is not True:
                errors = verdict.get("errores", []) if isinstance(verdict, dict) else []
                raise RuleEditorError("SchemaManager rechazó el JSON: " + "; ".join(map(str, errors)))
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False,
                prefix=".rules_", suffix=".tmp") as f:
                temp_path = f.name
                json.dump(output, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.path)
            temp_path = None
        except (OSError, ValueError, TypeError) as exc:
            raise RuleEditorError(f"No se pudieron guardar las reglas: {exc}") from exc
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
        self.data = output
        self._snapshot_rules = copy.deepcopy(output["rules"])

    def validate_rules(self) -> dict:
        """Valida todas las reglas en memoria sin modificar el archivo.

        Devuelve valido, errores y advertencias con el identificador de regla.
        La validación formal del documento completo corresponde a SchemaManager.
        """
        errors, warnings = [], []
        for i, rule in enumerate(self.data["rules"]):
            rid = rule.get("id", f"índice {i}") if isinstance(rule, dict) else f"índice {i}"
            result = self.validate_rule(rule, exclude_rule_id=rid)
            errors.extend(f"{rid}: {error}" for error in result["errores"])
            warnings.extend(f"{rid}: {warning}" for warning in result["advertencias"])
        ids = [r.get("id") for r in self.data["rules"]
               if isinstance(r, dict) and isinstance(r.get("id"), str)]
        if len(ids) != len(set(ids)):
            errors.append("Existen identificadores de reglas duplicados.")
        if not self.data["rules"]:
            errors.append("La lista de reglas está vacía; el contrato actual exige una regla.")
        return {"valido": not errors, "errores": errors, "advertencias": warnings}

    # Alias para facilitar la coordinación con QuestionEditor del Grupo 1.
    def add_rule(self, rule: dict) -> dict:
        """Sinónimo de create_rule()."""
        return self.create_rule(rule)
