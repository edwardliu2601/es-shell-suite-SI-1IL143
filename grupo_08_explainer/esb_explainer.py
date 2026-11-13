"""Grupo 8 - Explicador XAI (HOW/WHY) del ES-Shell Suite.

Reconstruye, a partir de la memoria de trabajo, como se obtuvo un resultado
(HOW) y explica por que el motor solicita un dato (WHY). Lee los contratos de
la seccion 4.2 de la guia:

- conocimiento_dominio.json: rules[].id, conditions, conclusion,
  explanation_template, priority, description.
- memoria_trabajo.json: facts, derived_facts[attr].derived_by_rule,
  derived_facts[attr].certainty_factor, execution_trace.

Produce los campos explanation_how (lista de cadenas) y explanation_why
(cadena) de dictamen_salida.json. No ejecuta reglas: solo explica lo que los
motores (G5, G6, G7) dejaron registrado.
"""

from __future__ import annotations


class XAIExplainer:
    """Componente explicativo: responde HOW y WHY sobre una consulta."""

    def __init__(self, knowledge_base: dict):
        """Recibe el contenido de conocimiento_dominio.json ya cargado."""
        self.rules = {r["id"]: r for r in knowledge_base.get("rules", [])}

    def explain_how(self, working_memory: dict, attribute_id: str) -> list[str]:
        """Explica como se obtuvo el valor de attribute_id.

        Devuelve las lineas de explanation_how. Si una premisa es a su vez un
        hecho derivado, se agrega debajo, con sangria, la explicacion de ese
        hecho, hasta llegar a los datos ingresados por el usuario.
        Lanza ValueError si el atributo no tiene valor o si la memoria cita
        una regla que no existe en la base de conocimiento.
        """
        return self._how(working_memory, attribute_id, set())

    def explain_why(self, attribute_id: str, rule_id: str | None = None) -> str:
        """Explica por que se solicita attribute_id al usuario.

        rule_id es la regla que el motor esta evaluando cuando pide el dato
        (lo conoce G6). Si no se indica, se toma la regla de mayor prioridad
        que tiene una condicion sobre ese atributo.
        """
        if rule_id is None:
            candidatas = [r for r in self.rules.values()
                          if any(c["attribute_id"] == attribute_id for c in r["conditions"])]
            if not candidatas:
                raise ValueError(f"Ninguna regla usa el atributo '{attribute_id}'.")
            rule_id = max(candidatas, key=lambda r: r.get("priority", 0))["id"]
        regla = self._regla(rule_id)
        meta = regla["conclusion"]
        texto = (f"Se solicitó '{attribute_id}' para evaluar la condición de la regla "
                 f"{rule_id} ({regla.get('description', '')}), que permitiría concluir "
                 f"{meta['attribute_id']} = {meta['value']!r}.")
        return texto.replace(" ()", "")

    def explain_trace(self, working_memory: dict) -> list[str]:
        """Traza legible de las reglas aplicadas, en orden de ejecucion."""
        derivados = working_memory.get("derived_facts", {})
        lineas = []
        for paso in working_memory.get("execution_trace", []):
            attr = paso["added_fact"]
            valor = derivados.get(attr, {}).get("value")
            lineas.append(f"Paso {paso['step']}: {paso['rule_fired']} agregó {attr} = {valor!r}")
        return lineas

    # --- internos ---

    def _regla(self, rule_id: str) -> dict:
        if rule_id not in self.rules:
            raise ValueError(f"La regla '{rule_id}' no está en la base de conocimiento.")
        return self.rules[rule_id]

    def _how(self, wm: dict, attribute_id: str, en_curso: set) -> list[str]:
        hechos = wm.get("facts", {})
        derivados = wm.get("derived_facts", {})
        if attribute_id in hechos and attribute_id not in derivados:
            return [f"'{attribute_id}' fue ingresado por el usuario: {hechos[attribute_id]!r}."]
        if attribute_id not in derivados:
            raise ValueError(f"'{attribute_id}' no tiene valor en la memoria de trabajo.")
        if attribute_id in en_curso:
            raise ValueError(f"Ciclo en la derivación de '{attribute_id}'.")
        en_curso = en_curso | {attribute_id}

        derivado = derivados[attribute_id]
        rule_id = derivado["derived_by_rule"]
        regla = self._regla(rule_id)
        cabecera = f"Se determinó {derivado['value']!r} debido a la regla {rule_id}."
        fc = derivado.get("certainty_factor")
        if fc is not None and fc != 1.0:
            cabecera = cabecera[:-1] + f" (FC = {fc})."
        lineas = [cabecera]

        for i, cond in enumerate(regla["conditions"], 1):
            attr, op, esperado = cond["attribute_id"], cond["operator"], cond["value"]
            premisa = f"Premisa {i}: {attr} {op} {esperado!r}"
            if attr in derivados:
                lineas.append(f"{premisa} (Derivado por la regla {derivados[attr]['derived_by_rule']})")
                lineas += ["  " + l for l in self._how(wm, attr, en_curso)]
            elif attr not in hechos:
                lineas.append(f"{premisa} (Sin dato en la memoria de trabajo)")
            elif op == "==":
                lineas.append(f"{premisa} (Verificado)")
            else:
                lineas.append(f"{premisa} (Valor ingresado: {hechos[attr]!r})")

        if regla.get("explanation_template"):
            lineas.append(regla["explanation_template"])
        return lineas
