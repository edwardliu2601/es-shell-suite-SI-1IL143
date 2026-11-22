"""Grupo 7 - Incertidumbre y factores de certeza del ES-Shell Suite.

Calcula cuanta confianza merece cada hecho derivado por el motor de inferencia.
Usa factores de certeza (FC) entre -1.0 y 1.0 con la estrategia de MYCIN:

- Las premisas de una regla se combinan con el minimo de sus FC.
- Una regla aporta FC_regla * FC_premisas, siempre que el FC de las premisas
  supere un umbral (0.2 en MYCIN).
- Los aportes de varias reglas a la misma conclusion se combinan con la
  formula de evidencias paralelas de MYCIN.

El modulo trabaja sobre diccionarios con la forma de los contratos de la
seccion 4.2 de la guia y no importa nada de otros grupos. Escribe solo en
campos que los contratos ya tienen:

- memoria_trabajo.json: derived_facts[atributo].certainty_factor
- dictamen_salida.json: certainty_score

Los contratos no tienen campo para el FC de una regla ni para el de un dato
del usuario. Por eso esos valores entran como parametros del constructor
(rule_cfs y fact_cfs). Sin parametros todo vale 1.0 y la salida coincide con
los ejemplos de la guia.

No ejecuta reglas ni decide que preguntar: lee lo que el motor dejo en la
memoria de trabajo. Las firmas publicas son provisionales hasta que los
coordinadores las acepten.
"""

from __future__ import annotations

import copy
import math
import operator as _op
from dataclasses import dataclass, field
from typing import Any, Iterable

MIN_CF = -1.0
MAX_CF = 1.0
DECIMALS = 6
DEFAULT_THRESHOLD = 0.2  # Umbral de activacion de una regla en MYCIN.

# Mismos operadores del contrato conocimiento_dominio.json.
_COMPARATORS = {
    "==": _op.eq,
    "!=": _op.ne,
    ">": _op.gt,
    "<": _op.lt,
    ">=": _op.ge,
    "<=": _op.le,
}


class UncertaintyError(ValueError):
    """Dato invalido para el calculo de certeza.

    Se lanza por un FC fuera de rango, una regla que no existe en la base de
    conocimiento o una memoria de trabajo incoherente.
    """


# --- Funciones puras de MYCIN -------------------------------------------------


def validate_cf(cf: Any, name: str = "FC") -> float:
    """Devuelve cf como float si es un numero finito entre -1.0 y 1.0."""
    if isinstance(cf, bool) or not isinstance(cf, (int, float)) or not math.isfinite(cf):
        raise UncertaintyError(f"{name} debe ser un número finito, se recibió {cf!r}.")
    if not MIN_CF <= cf <= MAX_CF:
        raise UncertaintyError(f"{name} debe estar entre -1.0 y 1.0, se recibió {cf!r}.")
    return float(cf)


def _tidy(value: float) -> float:
    """Redondea, acota a [-1, 1] y evita el -0.0."""
    return max(MIN_CF, min(MAX_CF, round(value, DECIMALS))) + 0.0


def combine_premises(cfs: Iterable[float]) -> float:
    """FC de una conjuncion de premisas: el menor de los FC."""
    values = [validate_cf(cf, "FC de premisa") for cf in cfs]
    if not values:
        raise UncertaintyError("Se necesita al menos una premisa.")
    return min(values) + 0.0


def propagate(rule_cf: float, premise_cf: float) -> float:
    """Aporte de una regla a su conclusion: FC de la regla por FC de las premisas."""
    return _tidy(
        validate_cf(rule_cf, "FC de la regla") * validate_cf(premise_cf, "FC de la premisa")
    )


def combine_evidence(cf1: float, cf2: float) -> float:
    """Combina dos evidencias sobre la misma conclusion (MYCIN).

    - Ambas no negativas: cf1 + cf2 * (1 - cf1)
    - Ambas no positivas: cf1 + cf2 * (1 + cf1)
    - Signos distintos: (cf1 + cf2) / (1 - min(|cf1|, |cf2|))

    El caso 1.0 con -1.0 divide entre cero y se define como 0.0 (evidencia
    total a favor y total en contra se cancelan).
    """
    a = validate_cf(cf1, "cf1")
    b = validate_cf(cf2, "cf2")
    if a >= 0 and b >= 0:
        result = a + b * (1 - a)
    elif a <= 0 and b <= 0:
        result = a + b * (1 + a)
    else:
        denominator = 1 - min(abs(a), abs(b))
        result = 0.0 if denominator == 0 else (a + b) / denominator
    return _tidy(result)


def combine_all(cfs: Iterable[float]) -> float:
    """Combina cualquier cantidad de evidencias. Sin evidencias devuelve 0.0."""
    total = 0.0
    for cf in cfs:
        total = combine_evidence(total, cf)
    return total


# --- Motor --------------------------------------------------------------------


@dataclass
class _Context:
    """Datos de una evaluacion: la memoria ya revisada y los FC calculados."""

    facts: dict
    derived: dict
    values: dict  # atributo -> valor, con los datos del usuario primero
    order: dict  # atributo derivado -> posicion en execution_trace
    cache: dict = field(default_factory=dict)  # atributo derivado -> FC


class UncertaintyEngine:
    """Calcula los factores de certeza de una memoria de trabajo.

    knowledge_base: conocimiento_dominio.json ya cargado (dict).
    rule_cfs: {id_de_regla: FC}. Una regla sin entrada usa default_cf.
    fact_cfs: {id_de_atributo: FC} para datos que ingresa el usuario. Un dato
        sin entrada usa default_cf.
    default_cf: FC de las reglas y de los datos sin valor propio.
    threshold: una regla solo aporta si el FC de sus premisas lo supera.
    combine_equivalent_rules: si es True, ademas de la regla registrada en
        derived_by_rule se suman las reglas que llegan al mismo valor y
        estaban disponibles cuando se derivo el hecho (ver evaluate).
    """

    def __init__(
        self,
        knowledge_base: dict,
        rule_cfs: dict[str, float] | None = None,
        fact_cfs: dict[str, float] | None = None,
        *,
        default_cf: float = 1.0,
        threshold: float = DEFAULT_THRESHOLD,
        combine_equivalent_rules: bool = True,
    ) -> None:
        if not isinstance(knowledge_base, dict) or not isinstance(
            knowledge_base.get("rules"), list
        ):
            raise UncertaintyError("knowledge_base debe ser un dict con la lista 'rules'.")
        self.rules: dict[str, dict] = {}
        for rule in knowledge_base["rules"]:
            if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
                raise UncertaintyError("Cada regla debe ser un objeto con 'id' de texto.")
            self.rules[rule["id"]] = rule

        self.default_cf = validate_cf(default_cf, "default_cf")
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not 0 <= threshold < 1
        ):
            raise UncertaintyError(f"threshold debe estar en [0, 1), se recibió {threshold!r}.")
        self.threshold = float(threshold)
        self.combine_equivalent_rules = bool(combine_equivalent_rules)

        self.rule_cfs: dict[str, float] = {}
        for rule_id, cf in (rule_cfs or {}).items():
            if rule_id not in self.rules:
                raise UncertaintyError(f"La regla '{rule_id}' no está en la base de conocimiento.")
            self.rule_cfs[rule_id] = validate_cf(cf, f"FC de la regla '{rule_id}'")

        declared = {
            a.get("id")
            for a in knowledge_base.get("attributes", [])
            if isinstance(a, dict)
        }
        self.fact_cfs: dict[str, float] = {}
        for attribute_id, cf in (fact_cfs or {}).items():
            if declared and attribute_id not in declared:
                raise UncertaintyError(
                    f"El atributo '{attribute_id}' no está declarado en la base de conocimiento."
                )
            self.fact_cfs[attribute_id] = validate_cf(cf, f"FC del atributo '{attribute_id}'")

    # --- API publica ---

    def evaluate(self, working_memory: dict) -> dict:
        """Devuelve una copia de la memoria con certainty_factor en cada hecho derivado.

        No modifica la memoria recibida y se puede llamar varias veces: ignora
        el certainty_factor que ya traiga cada hecho y lo recalcula.

        Para cada hecho derivado se combinan los aportes de la regla registrada
        en derived_by_rule y, si combine_equivalent_rules es True, de las demas
        reglas que concluyen el mismo valor, cumplen sus condiciones y solo
        usan datos del usuario o hechos derivados antes en execution_trace.
        Esto cubre el caso en que el motor de G5 deja pasar una sola regla por
        atributo, aunque otras tambien lo respalden.
        """
        context = self._read_memory(working_memory)
        result = copy.deepcopy(working_memory)
        for attribute_id in context.derived:
            cf = self._attribute_cf(attribute_id, context, frozenset())
            result["derived_facts"][attribute_id]["certainty_factor"] = cf
        return result

    def certainty_score(self, working_memory: dict, attribute_id: str) -> float:
        """FC del atributo indicado, para el campo certainty_score del dictamen."""
        evaluated = self.evaluate(working_memory)
        if attribute_id not in evaluated["derived_facts"]:
            raise UncertaintyError(f"'{attribute_id}' no es un hecho derivado de la memoria.")
        return evaluated["derived_facts"][attribute_id]["certainty_factor"]

    def complete_verdict(self, verdict: dict, working_memory: dict, attribute_id: str) -> dict:
        """Devuelve una copia del dictamen con certainty_score igual al FC de attribute_id."""
        if not isinstance(verdict, dict):
            raise UncertaintyError("El dictamen debe ser un objeto.")
        completed = copy.deepcopy(verdict)
        completed["certainty_score"] = self.certainty_score(working_memory, attribute_id)
        return completed

    # --- Lectura de la memoria ---

    def _read_memory(self, working_memory: Any) -> _Context:
        if not isinstance(working_memory, dict):
            raise UncertaintyError("La memoria de trabajo debe ser un objeto.")
        facts = working_memory.get("facts", {})
        derived = working_memory.get("derived_facts", {})
        trace = working_memory.get("execution_trace", [])
        if not isinstance(facts, dict) or not isinstance(derived, dict):
            raise UncertaintyError("'facts' y 'derived_facts' deben ser objetos.")
        if not isinstance(trace, list):
            raise UncertaintyError("'execution_trace' debe ser una lista.")

        order: dict[str, int] = {}
        for position, step in enumerate(trace):
            if isinstance(step, dict) and "added_fact" in step:
                order.setdefault(step["added_fact"], position)

        for attribute_id, entry in derived.items():
            if not isinstance(entry, dict) or "value" not in entry or "derived_by_rule" not in entry:
                raise UncertaintyError(
                    f"El hecho derivado '{attribute_id}' necesita 'value' y 'derived_by_rule'."
                )
            if attribute_id not in order:
                raise UncertaintyError(
                    f"El hecho derivado '{attribute_id}' no aparece en execution_trace."
                )

        values = {attribute_id: entry["value"] for attribute_id, entry in derived.items()}
        values.update(facts)  # Si un atributo esta en ambos, manda el dato del usuario.
        return _Context(facts=facts, derived=derived, values=values, order=order)

    # --- Calculo ---

    def _rule(self, rule_id: str) -> dict:
        if rule_id not in self.rules:
            raise UncertaintyError(f"La regla '{rule_id}' no está en la base de conocimiento.")
        return self.rules[rule_id]

    def _attribute_cf(self, attribute_id: str, context: _Context, stack: frozenset) -> float:
        """FC de un dato del usuario, de un hecho derivado o de un atributo sin valor."""
        if attribute_id in context.facts:
            return self.fact_cfs.get(attribute_id, self.default_cf)
        if attribute_id not in context.derived:
            return 0.0  # Sin dato no hay evidencia.
        if attribute_id in context.cache:
            return context.cache[attribute_id]
        if attribute_id in stack:
            raise UncertaintyError(f"Ciclo en la derivación de '{attribute_id}'.")

        entry = context.derived[attribute_id]
        rules = [self._rule(entry["derived_by_rule"])]
        if self.combine_equivalent_rules:
            rules += self._equivalent_rules(attribute_id, entry, context)

        contributions = []
        for rule in rules:
            premise_cf = self._premise_cf(rule, context, stack | {attribute_id})
            if premise_cf > self.threshold:
                contributions.append(
                    propagate(self.rule_cfs.get(rule["id"], self.default_cf), premise_cf)
                )
        # Se ordenan para que el redondeo no dependa de que regla registro el motor.
        context.cache[attribute_id] = combine_all(sorted(contributions))
        return context.cache[attribute_id]

    def _premise_cf(self, rule: dict, context: _Context, stack: frozenset) -> float:
        conditions = rule.get("conditions")
        if not isinstance(conditions, list) or not all(isinstance(c, dict) for c in conditions):
            raise UncertaintyError(
                f"La regla '{rule['id']}' necesita una lista 'conditions' de objetos."
            )
        return combine_premises(
            self._attribute_cf(condition.get("attribute_id"), context, stack)
            for condition in conditions
        )

    def _equivalent_rules(self, attribute_id: str, entry: dict, context: _Context) -> list[dict]:
        """Reglas, distintas de la registrada, que tambien sostienen el hecho derivado.

        Una regla cuenta si concluye el mismo atributo con el mismo valor, si
        sus condiciones se cumplen con los valores finales, y si cada premisa
        es un dato del usuario o un hecho derivado antes que este en la traza.
        La ultima condicion evita ciclos y deja fuera reglas que el motor no
        podia haber disparado en ese momento.
        """
        limit = context.order[attribute_id]
        found = []
        for rule in self.rules.values():
            if rule["id"] == entry["derived_by_rule"]:
                continue
            conclusion = rule.get("conclusion")
            if (
                not isinstance(conclusion, dict)
                or conclusion.get("attribute_id") != attribute_id
                or conclusion.get("value") != entry["value"]
            ):
                continue
            conditions = rule.get("conditions")
            if not isinstance(conditions, list) or not conditions:
                continue
            if all(
                self._available(condition, context, limit)
                and self._holds(condition, context.values)
                for condition in conditions
            ):
                found.append(rule)
        return found

    @staticmethod
    def _available(condition: Any, context: _Context, limit: int) -> bool:
        if not isinstance(condition, dict):
            return False
        attribute_id = condition.get("attribute_id")
        if attribute_id in context.facts:
            return True
        return attribute_id in context.derived and context.order[attribute_id] < limit

    @staticmethod
    def _holds(condition: dict, values: dict) -> bool:
        """Evalua una condicion igual que el motor: lo que no se puede comparar no se cumple."""
        attribute_id = condition.get("attribute_id")
        if attribute_id not in values or "value" not in condition:
            return False
        left, right = values[attribute_id], condition["value"]
        operator = condition.get("operator")
        try:
            if operator == "in":
                return isinstance(right, (list, tuple, set)) and left in right
            comparator = _COMPARATORS.get(operator)
            return bool(comparator(left, right)) if comparator else False
        except TypeError:
            return False
