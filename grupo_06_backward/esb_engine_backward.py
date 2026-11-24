"""Grupo 6 - Motor de encadenamiento hacia atras (BackwardEngine).

Parte de una meta (un atributo, por ejemplo ``dictamen``) y busca las reglas que
la concluyen, de mayor a menor prioridad. Cada condicion se resuelve asi:

- si el atributo ya tiene valor, se evalua;
- si otra regla lo concluye, se vuelve una sub-meta y se resuelve igual;
- si ninguna regla lo concluye, se le pide el dato al usuario con ``ask_fn``.

Una regla se descarta apenas una condicion ya conocida resulta falsa, antes de
preguntar el resto, de modo que solo se piden los datos necesarios. Cada regla
probada agrega un hecho derivado y un paso a la traza, con el formato de
``memoria_trabajo.json``.

Trabaja sobre diccionarios con la forma de los contratos y no importa codigo de
otros grupos. Sigue la politica de G5: gana la regla de mayor prioridad y un
hecho ya presente no se sobrescribe. Cada ``Question`` lleva la regla que la
motivo, que es lo que G8 necesita para explicar el WHY.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

SUPPORTED_OPERATORS = ("==", "!=", ">", "<", ">=", "<=", "in")
DEFAULT_CERTAINTY = 1.0
DEFAULT_MAX_DEPTH = 100

_TRUE_WORDS = {"si", "sí", "s", "true", "verdadero", "yes", "y", "1"}
_FALSE_WORDS = {"no", "n", "false", "falso", "0"}


# --- Errores -------------------------------------------------------------------


class BackwardEngineError(ValueError):
    """Error base del motor hacia atras. Los mensajes estan en espanol."""


class InvalidKnowledgeBaseError(BackwardEngineError):
    """La base de conocimiento no cumple el contrato conocimiento_dominio.json."""


class InvalidWorkingMemoryError(BackwardEngineError):
    """La memoria de trabajo no cumple el contrato memoria_trabajo.json."""


class InvalidAnswerError(BackwardEngineError):
    """La respuesta del usuario no es valida para el atributo preguntado."""


class _NeedInput(Exception):
    """Interna: el motor necesita un dato y no hay ``ask_fn`` para pedirlo."""

    def __init__(self, question: "Question") -> None:
        super().__init__(question.attribute_id)
        self.question = question


# --- Tipos publicos ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Question:
    """Dato que el motor necesita del usuario.

    ``rule_id`` es la regla que el motor esta evaluando cuando pide el dato y
    ``goal`` el atributo que esa regla concluiria. Con ellos G8 arma el WHY:
    ``XAIExplainer.explain_why(question.attribute_id, question.rule_id)``.
    """

    attribute_id: str
    question: str
    type: str
    options: tuple[Any, ...] = ()
    range: tuple[float, float] | None = None
    rule_id: str | None = None
    goal: str | None = None


AskFn = Callable[[Question], Any]
"""Recibe una ``Question`` y devuelve el valor ingresado, o ``None`` si el
usuario no sabe la respuesta."""


@dataclass(slots=True)
class BackwardResult:
    """Resultado de verificar una meta."""

    goal_attribute: str
    goal_value: Any
    achieved: bool
    value: Any
    reason: str
    memory: dict[str, Any]
    questions_asked: list[Question] = field(default_factory=list)
    pending_question: Question | None = None
    proof: list[str] = field(default_factory=list)

    @property
    def fired_rules(self) -> list[str]:
        """Reglas aplicadas, en el orden en que quedaron probadas."""
        return [paso["rule_fired"] for paso in self.memory["execution_trace"]]


# --- Operadores ----------------------------------------------------------------


def evaluate(operator: str, left: Any, right: Any) -> bool:
    """Evalua ``left <operator> right``. Una comparacion imposible da False."""
    try:
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == ">":
            return left > right
        if operator == "<":
            return left < right
        if operator == ">=":
            return left >= right
        if operator == "<=":
            return left <= right
        if operator == "in":
            return left in right
    except TypeError:
        return False
    raise BackwardEngineError(f"Operador no soportado: {operator!r}.")


# --- Motor ---------------------------------------------------------------------


class BackwardEngine:
    """Encadenamiento hacia atras sobre reglas SI-ENTONCES.

    ``knowledge_base`` es ``conocimiento_dominio.json`` ya cargado como ``dict``.
    ``ask_fn`` se llama cada vez que falta un dato del usuario. Si es ``None``
    el motor no pregunta: se detiene en el primer dato que le falta y lo
    informa en ``BackwardResult.pending_question`` (modo para la API REST).
    """

    def __init__(
        self,
        knowledge_base: dict[str, Any],
        ask_fn: AskFn | None = None,
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> None:
        self.ask_fn = ask_fn
        self.max_depth = max_depth
        self._rules: dict[str, dict[str, Any]] = {}
        self._attributes: dict[str, dict[str, Any]] = {}
        self._by_conclusion: dict[str, list[dict[str, Any]]] = {}
        self._load_knowledge_base(knowledge_base)

    # --- API publica ---

    def prove(
        self,
        goal_attribute: str,
        goal_value: Any = None,
        memory: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> BackwardResult:
        """Verifica una meta y devuelve el resultado con la memoria actualizada.

        Sin ``goal_value`` busca el valor del atributo. Con ``goal_value``
        comprueba la hipotesis ``goal_attribute == goal_value``. La memoria que
        se recibe no se modifica: el resultado trae una copia actualizada.
        """
        self._require_known_goal(goal_attribute)
        state = _RunState(self._prepare_memory(memory, session_id))
        pending: Question | None = None
        try:
            state.log(0, f"Meta: {goal_attribute}"
                         + (f" == {goal_value!r}" if goal_value is not None else ""))
            self._obtain(state, goal_attribute, rule=None, depth=0)
        except _NeedInput as need:
            pending = need.question
            state.log(0, f"Falta el dato '{pending.attribute_id}' y no hay quien lo pida.")

        known = state.known(goal_attribute)
        value = state.value(goal_attribute) if known else None
        achieved = known and (goal_value is None or value == goal_value)
        return BackwardResult(
            goal_attribute=goal_attribute,
            goal_value=goal_value,
            achieved=achieved,
            value=value,
            reason=self._reason(state, goal_attribute, goal_value, known, value, pending),
            memory=state.memory,
            questions_asked=state.asked,
            pending_question=pending,
            proof=state.proof,
        )

    def next_question(
        self,
        goal_attribute: str,
        memory: dict[str, Any] | None = None,
        goal_value: Any = None,
    ) -> Question | None:
        """Proximo dato que el motor pediria, sin preguntar ni usar ``ask_fn``.

        Devuelve ``None`` si la meta ya se puede resolver (o descartar) con los
        hechos de ``memory``. Sirve para la API REST: cada llamada es independiente
        y solo depende de la memoria de la sesion.
        """
        sin_preguntar = copy.copy(self)
        sin_preguntar.ask_fn = None
        return sin_preguntar.prove(goal_attribute, goal_value, memory).pending_question

    def validate_answer(self, attribute_id: str, value: Any) -> Any:
        """Valida y normaliza una respuesta segun el atributo (tipo, opciones, rango).

        Devuelve el valor listo para guardar (``"2,25"`` -> ``2.25``) o lanza
        ``InvalidAnswerError``. G10 puede usarla para volver a preguntar.
        """
        definition = self._attributes.get(attribute_id)
        if definition is None:
            return value
        kind = definition.get("type")
        name = definition.get("name", attribute_id)

        if kind == "numeric":
            number = self._to_number(value, name)
            low_high = definition.get("range")
            if low_high and not low_high[0] <= number <= low_high[1]:
                raise InvalidAnswerError(
                    f"'{name}' debe estar entre {low_high[0]} y {low_high[1]}; se recibió {number}."
                )
            return number
        if kind == "categorical":
            options = definition.get("options") or []
            if not options:
                return value
            for option in options:
                if value == option or (
                    isinstance(value, str) and value.strip().casefold() == str(option).casefold()
                ):
                    return option
            raise InvalidAnswerError(
                f"'{name}' debe ser una de {list(options)}; se recibió {value!r}."
            )
        if kind == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                word = value.strip().casefold()
                if word in _TRUE_WORDS:
                    return True
                if word in _FALSE_WORDS:
                    return False
            raise InvalidAnswerError(f"'{name}' debe ser sí o no; se recibió {value!r}.")
        if kind == "text":
            if not isinstance(value, str) or not value.strip():
                raise InvalidAnswerError(f"'{name}' debe ser un texto no vacío.")
            return value.strip()
        return value

    # --- Nucleo recursivo ---

    def _obtain(self, state: "_RunState", attribute_id: str,
                rule: dict[str, Any] | None, depth: int) -> bool:
        """Intenta que ``attribute_id`` tenga valor: derivandolo o preguntandolo."""
        if state.known(attribute_id):
            return True
        if attribute_id in self._by_conclusion:
            return self._derive(state, attribute_id, depth)
        return self._ask(state, attribute_id, rule, depth)

    def _derive(self, state: "_RunState", attribute_id: str, depth: int) -> bool:
        """Sub-meta: prueba las reglas que concluyen el atributo, por prioridad."""
        if attribute_id in state.failed:
            return False
        if attribute_id in state.stack:
            state.cycles += 1
            state.log(depth, f"Ciclo: '{attribute_id}' depende de sí mismo; se descarta esta vía.")
            return False
        if depth > self.max_depth:
            raise BackwardEngineError(
                f"Se superó la profundidad máxima ({self.max_depth}) al resolver '{attribute_id}'."
            )
        state.stack.append(attribute_id)
        ciclos_antes = state.cycles
        try:
            for rule in self._by_conclusion[attribute_id]:
                if self._try_rule(state, rule, depth):
                    return True
            state.log(depth, f"Ninguna regla permitió concluir '{attribute_id}'.")
            # Un fallo es definitivo en esta corrida (los hechos no cambian), salvo
            # que dependa de un ciclo abierto: ahi puede cambiar segun el contexto.
            if state.cycles == ciclos_antes:
                state.failed.add(attribute_id)
            return False
        finally:
            state.stack.pop()

    def _try_rule(self, state: "_RunState", rule: dict[str, Any], depth: int) -> bool:
        goal = rule["conclusion"]["attribute_id"]
        state.log(depth, f"Probando {rule['id']} para concluir '{goal}'"
                         + (f" ({rule['description']})" if rule.get("description") else ""))

        # Primero lo barato: si una condicion ya conocida es falsa, se descarta
        # la regla sin preguntar nada mas.
        verified: set[int] = set()
        for index, cond in enumerate(rule["conditions"]):
            if state.known(cond["attribute_id"]):
                if not self._holds(state, cond, depth + 1):
                    state.log(depth, f"{rule['id']} descartada.")
                    return False
                verified.add(index)

        # Despues lo que falta: se deriva o se pregunta, en el orden de la regla.
        # Resolver una condicion puede dejar conocido el atributo de otra, por
        # eso se evalua toda condicion que no se haya verificado arriba.
        for index, cond in enumerate(rule["conditions"]):
            if index in verified:
                continue
            if not self._obtain(state, cond["attribute_id"], rule, depth + 1):
                state.log(depth, f"{rule['id']} descartada: sin valor para '{cond['attribute_id']}'.")
                return False
            if not self._holds(state, cond, depth + 1):
                state.log(depth, f"{rule['id']} descartada.")
                return False

        state.fire(rule)
        state.log(depth, f"{rule['id']} probada: {goal} = {rule['conclusion']['value']!r}")
        return True

    def _holds(self, state: "_RunState", cond: dict[str, Any], depth: int) -> bool:
        actual = state.value(cond["attribute_id"])
        ok = evaluate(cond["operator"], actual, cond["value"])
        state.log(depth, f"{'Cumple' if ok else 'Falla'}: {cond['attribute_id']} {cond['operator']} "
                         f"{cond['value']!r} (valor: {actual!r})")
        return ok

    def _ask(self, state: "_RunState", attribute_id: str,
             rule: dict[str, Any] | None, depth: int) -> bool:
        """Pide al usuario un dato que ninguna regla concluye."""
        if attribute_id in state.unanswered:
            return False

        definition = self._attributes.get(attribute_id, {})
        dependency = definition.get("depends_on")
        if dependency:
            # Pregunta condicional (G1): solo aplica si su condicion se cumple.
            applies = (self._obtain(state, dependency["attribute_id"], rule, depth + 1)
                       and self._holds(state, dependency, depth + 1))
            if not applies:
                state.unanswered.add(attribute_id)
                state.log(depth, f"La pregunta '{attribute_id}' no aplica (depende de "
                                 f"{dependency['attribute_id']}).")
                return False

        question = Question(
            attribute_id=attribute_id,
            question=definition.get("question")
            or f"Ingrese el valor de '{definition.get('name', attribute_id)}':",
            type=definition.get("type", "text"),
            options=tuple(definition.get("options") or ()),
            range=tuple(definition["range"]) if definition.get("range") else None,
            rule_id=rule["id"] if rule else None,
            goal=rule["conclusion"]["attribute_id"] if rule else None,
        )
        if self.ask_fn is None:
            raise _NeedInput(question)

        state.asked.append(question)
        answer = self.ask_fn(question)
        if answer is None:
            state.unanswered.add(attribute_id)
            state.log(depth, f"El usuario no respondió '{attribute_id}'.")
            return False

        value = self.validate_answer(attribute_id, answer)
        state.memory["facts"][attribute_id] = value
        state.log(depth, f"Dato ingresado: {attribute_id} = {value!r}")
        return True

    # --- Carga y validacion ---

    def _load_knowledge_base(self, kb: dict[str, Any]) -> None:
        if not isinstance(kb, dict):
            raise InvalidKnowledgeBaseError("La base de conocimiento debe ser un objeto JSON (dict).")
        rules = kb.get("rules")
        if not isinstance(rules, list) or not rules:
            raise InvalidKnowledgeBaseError("'rules' debe ser una lista con al menos una regla.")
        attributes = kb.get("attributes", [])
        if not isinstance(attributes, list):
            raise InvalidKnowledgeBaseError("'attributes' debe ser una lista.")

        for attribute in attributes:
            if not isinstance(attribute, dict) or not attribute.get("id"):
                raise InvalidKnowledgeBaseError("Cada atributo debe ser un objeto con 'id'.")
            self._attributes[attribute["id"]] = attribute

        for rule in rules:
            self._validate_rule(rule)
            if rule["id"] in self._rules:
                raise InvalidKnowledgeBaseError(f"La regla '{rule['id']}' está repetida.")
            self._rules[rule["id"]] = rule
            self._by_conclusion.setdefault(rule["conclusion"]["attribute_id"], []).append(rule)
        for group in self._by_conclusion.values():
            group.sort(key=lambda r: (-r.get("priority", 0), r["id"]))

    @staticmethod
    def _validate_rule(rule: Any) -> None:
        if not isinstance(rule, dict) or not rule.get("id"):
            raise InvalidKnowledgeBaseError("Cada regla debe ser un objeto con 'id'.")
        rid = rule["id"]
        conditions = rule.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise InvalidKnowledgeBaseError(f"La regla '{rid}' debe tener al menos una condición.")
        for cond in conditions:
            if not isinstance(cond, dict) or not {"attribute_id", "operator", "value"} <= cond.keys():
                raise InvalidKnowledgeBaseError(
                    f"Una condición de '{rid}' necesita attribute_id, operator y value."
                )
            if cond["operator"] not in SUPPORTED_OPERATORS:
                raise InvalidKnowledgeBaseError(
                    f"La regla '{rid}' usa un operador no soportado: {cond['operator']!r}."
                )
            if cond["operator"] == "in" and not isinstance(cond["value"], list):
                raise InvalidKnowledgeBaseError(
                    f"El operador 'in' de '{rid}' requiere una lista como valor."
                )
        conclusion = rule.get("conclusion")
        if not isinstance(conclusion, dict) or not conclusion.get("attribute_id") \
                or "value" not in conclusion:
            raise InvalidKnowledgeBaseError(f"La regla '{rid}' necesita una conclusión con attribute_id y value.")
        if not isinstance(rule.get("priority", 0), int) or isinstance(rule.get("priority", 0), bool):
            raise InvalidKnowledgeBaseError(f"La prioridad de '{rid}' debe ser un entero.")

    def _require_known_goal(self, attribute_id: str) -> None:
        used = attribute_id in self._attributes or attribute_id in self._by_conclusion or any(
            c["attribute_id"] == attribute_id for r in self._rules.values() for c in r["conditions"]
        )
        if not used:
            raise BackwardEngineError(
                f"El atributo '{attribute_id}' no existe en la base de conocimiento."
            )

    def _prepare_memory(self, memory: dict[str, Any] | None, session_id: str | None) -> dict[str, Any]:
        if memory is None:
            return {
                "session_id": session_id or f"sess_{datetime.now().year}_{uuid.uuid4().hex[:6]}",
                "facts": {},
                "derived_facts": {},
                "execution_trace": [],
            }
        if not isinstance(memory, dict):
            raise InvalidWorkingMemoryError("La memoria de trabajo debe ser un objeto JSON (dict).")
        prepared = copy.deepcopy(memory)
        if session_id and not prepared.get("session_id"):
            prepared["session_id"] = session_id
        if not prepared.get("session_id") or not isinstance(prepared["session_id"], str):
            raise InvalidWorkingMemoryError("La memoria necesita un 'session_id' de texto.")
        for key, kind in (("facts", dict), ("derived_facts", dict), ("execution_trace", list)):
            prepared.setdefault(key, kind())
            if not isinstance(prepared[key], kind):
                raise InvalidWorkingMemoryError(f"'{key}' de la memoria tiene un tipo inválido.")
        for name, derived in prepared["derived_facts"].items():
            if not isinstance(derived, dict) or "value" not in derived:
                raise InvalidWorkingMemoryError(
                    f"El hecho derivado '{name}' necesita al menos el campo 'value'."
                )
        return prepared

    @staticmethod
    def _to_number(value: Any, name: str) -> float | int:
        if isinstance(value, bool):
            raise InvalidAnswerError(f"'{name}' debe ser un número; se recibió {value!r}.")
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value.strip().replace(",", "."))
            except ValueError:
                pass
        raise InvalidAnswerError(f"'{name}' debe ser un número; se recibió {value!r}.")

    @staticmethod
    def _reason(state: "_RunState", goal: str, goal_value: Any, known: bool,
                value: Any, pending: Question | None) -> str:
        if pending is not None:
            return "falta_dato"
        if not known:
            return "sin_conclusion" if goal in state.unanswered else "no_se_cumple_ninguna_regla"
        if goal_value is not None and value != goal_value:
            return "valor_distinto"
        if goal in state.memory["derived_facts"]:
            return "derivado"
        return "dato_conocido"


# --- Estado de una corrida -----------------------------------------------------


class _RunState:
    """Estado mutable de una sola llamada a ``prove`` (el motor no guarda estado)."""

    def __init__(self, memory: dict[str, Any]) -> None:
        self.memory = memory
        self.asked: list[Question] = []
        self.unanswered: set[str] = set()
        self.failed: set[str] = set()
        self.cycles = 0
        self.stack: list[str] = []
        self.proof: list[str] = []

    def known(self, attribute_id: str) -> bool:
        return attribute_id in self.memory["facts"] or attribute_id in self.memory["derived_facts"]

    def value(self, attribute_id: str) -> Any:
        if attribute_id in self.memory["facts"]:
            return self.memory["facts"][attribute_id]
        return self.memory["derived_facts"][attribute_id]["value"]

    def fire(self, rule: dict[str, Any]) -> None:
        attribute_id = rule["conclusion"]["attribute_id"]
        self.memory["derived_facts"][attribute_id] = {
            "value": copy.deepcopy(rule["conclusion"]["value"]),
            "derived_by_rule": rule["id"],
            "certainty_factor": DEFAULT_CERTAINTY,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        trace = self.memory["execution_trace"]
        trace.append({"step": len(trace) + 1, "rule_fired": rule["id"], "added_fact": attribute_id})

    def log(self, depth: int, message: str) -> None:
        self.proof.append("  " * depth + message)
