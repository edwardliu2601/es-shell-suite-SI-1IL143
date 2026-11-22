"""esb_reporter.py, Grupo 9: generador de reportes y dictámenes del ES-Shell Suite.

Lee los tres contratos JSON de la sección 4.2 de la guía y arma un informe
legible en Markdown:

- dictamen_salida.json (obligatorio): resultado final, certeza y explicaciones.
- memoria_trabajo.json (opcional): datos ingresados, hechos derivados y traza.
- conocimiento_dominio.json (opcional): nombres de atributos y descripción de reglas.

El lector es flexible: los campos opcionales pueden faltar y el informe
simplemente no los muestra. Este módulo no ejecuta reglas, solo reporta.
"""

from __future__ import annotations

import json
from pathlib import Path


class ReportGenerator:
    """Genera el informe final de una consulta del sistema experto."""

    def __init__(self, ruta_conocimiento=None, ruta_memoria=None, ruta_dictamen=None):
        self.ruta_conocimiento = ruta_conocimiento  # conocimiento_dominio.json
        self.ruta_memoria = ruta_memoria            # memoria_trabajo.json
        self.ruta_dictamen = ruta_dictamen          # dictamen_salida.json

    # --- carga de datos ---

    def cargar_json(self, ruta):
        """Lee un archivo JSON y devuelve su contenido.

        Lanza FileNotFoundError si el archivo no existe y ValueError si el
        contenido no es un JSON válido o no es un objeto.
        """
        ruta = Path(ruta)
        if not ruta.is_file():
            raise FileNotFoundError(f"No se encontró el archivo '{ruta}'.")
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"El archivo '{ruta.name}' no es un JSON válido: {error}") from error
        if not isinstance(datos, dict):
            raise ValueError(f"El archivo '{ruta.name}' debe contener un objeto JSON.")
        return datos

    def _cargar_opcional(self, ruta):
        return self.cargar_json(ruta) if ruta else {}

    # --- informe ---

    def generar_markdown(self):
        """Devuelve el informe completo como texto en Markdown."""
        if not self.ruta_dictamen:
            raise ValueError("Falta la ruta de dictamen_salida.json.")
        dictamen = self.cargar_json(self.ruta_dictamen)
        memoria = self._cargar_opcional(self.ruta_memoria)
        conocimiento = self._cargar_opcional(self.ruta_conocimiento)

        atributos = {a.get("id"): a for a in conocimiento.get("attributes", [])}
        reglas = {r.get("id"): r for r in conocimiento.get("rules", [])}
        advertencias = self._advertencias(dictamen, memoria, reglas, bool(conocimiento))

        titulo = conocimiento.get("meta", {}).get("project_title", "Sistema experto")
        sesion = dictamen.get("session_id") or memoria.get("session_id") or "sin identificador"

        lineas = [f"# Informe de consulta: {titulo}", "", f"**Sesión:** {sesion}", ""]
        lineas += self._seccion_conclusion(dictamen)
        lineas += self._seccion_datos(memoria, atributos)
        lineas += self._seccion_derivados(memoria, atributos)
        lineas += self._seccion_reglas(memoria, reglas)
        lineas += self._seccion_how(dictamen)
        lineas += self._seccion_why(dictamen)
        if advertencias:
            lineas += ["## Advertencias", ""] + [f"- {a}" for a in advertencias] + [""]
        return "\n".join(lineas).rstrip() + "\n"

    def guardar_reporte(self, ruta_salida):
        """Guarda el informe en un archivo y devuelve la ruta."""
        ruta_salida = Path(ruta_salida)
        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        ruta_salida.write_text(self.generar_markdown(), encoding="utf-8")
        return ruta_salida

    # --- secciones ---

    def _seccion_conclusion(self, dictamen):
        lineas = ["## 1. Conclusión", ""]
        lineas.append(f"- **Resultado:** {dictamen.get('final_outcome', 'No disponible')}")
        if dictamen.get("certainty_score") is not None:
            lineas.append(f"- **Nivel de certeza:** {dictamen['certainty_score']}")
        return lineas + [""]

    def _seccion_datos(self, memoria, atributos):
        lineas = ["## 2. Datos ingresados", ""]
        hechos = memoria.get("facts", {})
        if not hechos:
            return lineas + ["_No hay datos ingresados registrados._", ""]
        for attr_id, valor in hechos.items():
            lineas.append(f"- {self._nombre(attr_id, atributos)}: {valor}")
        return lineas + [""]

    def _seccion_derivados(self, memoria, atributos):
        lineas = ["## 3. Hechos derivados", ""]
        derivados = memoria.get("derived_facts", {})
        if not derivados:
            return lineas + ["_No se derivó ningún hecho._", ""]
        for attr_id, info in derivados.items():
            info = info if isinstance(info, dict) else {"value": info}
            partes = [f"{self._nombre(attr_id, atributos)}: {info.get('value')}"]
            if info.get("derived_by_rule"):
                partes.append(f"regla {info['derived_by_rule']}")
            if info.get("certainty_factor") is not None:
                partes.append(f"certeza {info['certainty_factor']}")
            if info.get("timestamp"):
                partes.append(f"hora {info['timestamp']}")
            lineas.append("- " + ", ".join(partes))
        return lineas + [""]

    def _seccion_reglas(self, memoria, reglas):
        lineas = ["## 4. Reglas aplicadas", ""]
        traza = memoria.get("execution_trace", [])
        if not traza:
            return lineas + ["_No se activó ninguna regla._", ""]
        for paso in traza:
            rule_id = paso.get("rule_fired", "regla desconocida")
            lineas.append(f"### Paso {paso.get('step', '?')}: {rule_id}")
            lineas.append("")
            regla = reglas.get(rule_id, {})
            if regla.get("description"):
                lineas.append(f"- **Descripción:** {regla['description']}")
            if regla.get("conditions"):
                condiciones = "; ".join(
                    f"{c.get('attribute_id')} {c.get('operator')} {c.get('value')}"
                    for c in regla["conditions"])
                lineas.append(f"- **Condiciones (todas deben cumplirse):** {condiciones}")
            if paso.get("added_fact"):
                lineas.append(f"- **Hecho agregado:** {paso['added_fact']}")
            if regla.get("explanation_template"):
                lineas.append(f"- **Explicación:** {regla['explanation_template']}")
            lineas.append("")
        return lineas

    def _seccion_how(self, dictamen):
        lineas = ["## 5. Cómo se llegó a la conclusión (HOW)", ""]
        how = dictamen.get("explanation_how")
        if isinstance(how, str):
            how = [how]
        if not how:
            return lineas + ["_No hay explicación disponible._", ""]
        return lineas + ["```text"] + [str(linea) for linea in how] + ["```", ""]

    def _seccion_why(self, dictamen):
        lineas = ["## 6. Por qué se solicitó el dato (WHY)", ""]
        why = dictamen.get("explanation_why")
        if isinstance(why, list):
            why = " ".join(str(x) for x in why)
        return lineas + [why or "_No hay explicación disponible._", ""]

    # --- internos ---

    @staticmethod
    def _nombre(attr_id, atributos):
        nombre = atributos.get(attr_id, {}).get("name")
        return f"{nombre} ({attr_id})" if nombre else str(attr_id)

    @staticmethod
    def _advertencias(dictamen, memoria, reglas, hay_conocimiento):
        avisos = []
        if memoria and dictamen.get("session_id") and memoria.get("session_id") \
                and dictamen["session_id"] != memoria["session_id"]:
            avisos.append("El session_id del dictamen no coincide con el de la memoria de trabajo.")
        if hay_conocimiento:
            for paso in memoria.get("execution_trace", []):
                if paso.get("rule_fired") not in reglas:
                    avisos.append(f"La regla '{paso.get('rule_fired')}' de la traza no está "
                                  "en la base de conocimiento.")
        return avisos
