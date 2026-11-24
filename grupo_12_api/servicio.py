"""Logica de servicio de la API del Grupo 12.

ServicioESB orquesta las operaciones que expone la API (cargar conocimiento,
consultar y explicar) sin depender de FastAPI, para mantener separada la
logica de negocio de la capa HTTP. No razona por su cuenta: delega en los
modulos de los demas grupos a traves de Integraciones (adaptadores.py).

- cargar_conocimiento, iniciar_consulta, registrar_hechos: validan con G4.
- auditar_conocimiento: KBAuditor (G3), cuando esta en el repositorio.
- inferir: ForwardEngine (G5) si la sesion usa motor "adelante" o
  BackwardEngine (G6) si usa "atras"; luego UncertaintyEngine (G7) calcula el
  factor de certeza de cada hecho derivado.
- siguiente_pregunta: BackwardEngine (G6) en sesiones "atras"; en sesiones
  "adelante", las reglas de la base. El WHY lo da XAIExplainer (G8).
- explicar_how, explicar_why, obtener_traza: XAIExplainer (G8).
- obtener_dictamen: arma dictamen_salida.json desde la memoria de trabajo.
- generar_reporte: ReportGenerator (G9) si esta implementado, o uno propio.
- guardar_sesion, listar_sesiones_guardadas, restaurar_sesion: ESBConverter
  (G11), en la carpeta ESB_CARPETA_SESIONES (por defecto
  grupo_12_api/sesiones_guardadas/).

Las sesiones abiertas viven en memoria; G11 las guarda en disco cuando se pide.
"""

from __future__ import annotations

import copy
import html
import json
import os
from datetime import datetime
from itertools import count
from pathlib import Path
from typing import Any

from .adaptadores import RAIZ, ContratoInvalido, Integraciones, ModuloNoDisponible, cumple
from .modelos import Motor

DATOS_EJEMPLO = Path(__file__).parent / "datos_ejemplo"
KB_EJEMPLO = "kb_ejemplo"
KB_ACADEMICO = "kb_academico"
RUTA_KB_ACADEMICO = RAIZ / "grupo_04_schema" / "ejemplos" / "conocimiento_dominio.json"
ATRIBUTO_META = "dictamen"
CARPETA_SESIONES = Path(os.environ.get("ESB_CARPETA_SESIONES",
                                       Path(__file__).parent / "sesiones_guardadas"))

__all__ = ["ServicioESB", "NoEncontrado", "EstadoInvalido", "ContratoInvalido",
           "ModuloNoDisponible", "KB_EJEMPLO", "KB_ACADEMICO", "cargar_ejemplo"]


class NoEncontrado(LookupError):
    """La base de conocimiento, la sesion, el atributo o la regla no existe."""


class EstadoInvalido(RuntimeError):
    """La operacion no se puede hacer en el estado actual de la sesion."""


def cargar_ejemplo(nombre: str) -> dict:
    """Lee uno de los JSON de ejemplo de la seccion 4.2."""
    with open(DATOS_EJEMPLO / f"{nombre}.json", encoding="utf-8") as f:
        return json.load(f)


class ServicioESB:
    """Fachada de la suite que usa la API REST."""

    def __init__(self, integraciones: Integraciones | None = None,
                 precargar_ejemplos: bool = True,
                 carpeta_sesiones: Path | str | None = None):
        self.integraciones = integraciones or Integraciones()
        self.carpeta_sesiones = Path(carpeta_sesiones or CARPETA_SESIONES)
        self._bases: dict[str, dict] = {}
        self._sesiones: dict[str, dict] = {}
        self._kb_ids = count(1)
        self._session_ids = count(1)
        if precargar_ejemplos:
            self._bases[KB_EJEMPLO] = cargar_ejemplo("conocimiento_dominio")
            if RUTA_KB_ACADEMICO.is_file():
                with open(RUTA_KB_ACADEMICO, encoding="utf-8") as f:
                    self._bases[KB_ACADEMICO] = json.load(f)

    def estado_modulos(self) -> dict[str, str]:
        return self.integraciones.estado()

    # --- Conocimiento ---

    def cargar_conocimiento(self, base: dict) -> tuple[str, dict]:
        """Valida la base contra el contrato (G4) y devuelve su kb_id."""
        errores = self.integraciones.validar(base, "conocimiento_dominio")
        if errores:
            raise ContratoInvalido("La base de conocimiento no cumple el contrato.", errores)
        kb_id = f"kb_{next(self._kb_ids):03d}"
        self._bases[kb_id] = copy.deepcopy(base)
        return kb_id, self._bases[kb_id]

    def obtener_conocimiento(self, kb_id: str) -> dict:
        if kb_id not in self._bases:
            raise NoEncontrado(f"No existe la base de conocimiento '{kb_id}'.")
        return self._bases[kb_id]

    def auditar_conocimiento(self, kb_id: str):
        """Auditoria de G3: contradicciones, redundancias, condiciones inalcanzables y ciclos.

        Devuelve el ReporteAuditoria de G3 (to_dict() / to_markdown()).
        """
        return self.integraciones.auditar(self.obtener_conocimiento(kb_id))

    def listar_preguntas(self, kb_id: str) -> list[dict]:
        """Atributos que se le pueden preguntar al usuario, en el orden de la base."""
        return [self._pregunta(a) for a in self.obtener_conocimiento(kb_id)["attributes"]]

    # --- Consultas ---

    def iniciar_consulta(self, kb_id: str, motor: Motor, hechos: dict[str, Any],
                         fc_reglas: dict[str, float] | None = None,
                         fc_hechos: dict[str, float] | None = None) -> dict:
        """Crea una sesion con los hechos iniciales, si son validos para la base.

        fc_reglas y fc_hechos son opcionales: el factor de certeza de cada regla
        y de cada dato del usuario (G7). Lo que no se indica vale 1.0.
        """
        kb = self.obtener_conocimiento(kb_id)
        session_id = self._nuevo_session_id()
        memoria = {"session_id": session_id, "facts": dict(hechos),
                   "derived_facts": {}, "execution_trace": []}
        self._exigir_memoria_valida(memoria, kb)
        self.integraciones.validar_certezas(kb, fc_reglas, fc_hechos)
        self._abrir_sesion(session_id, kb_id, motor, memoria, fc_reglas, fc_hechos)
        return {"session_id": session_id, "kb_id": kb_id, "motor": motor}

    def registrar_hechos(self, session_id: str, hechos: dict[str, Any],
                         fc_hechos: dict[str, float] | None = None) -> dict:
        """Agrega o reemplaza hechos del usuario (y, si se indica, su certeza).

        Como los hechos cambian, se descartan las conclusiones anteriores; se
        recalculan en la siguiente llamada a inferir.
        """
        sesion = self._sesion(session_id)
        memoria = sesion["memoria"]
        kb = self._kb_de(session_id)
        nueva = {**memoria, "facts": {**memoria["facts"], **hechos},
                 "derived_facts": {}, "execution_trace": []}
        nuevos_fc = {**sesion["fc_hechos"], **(fc_hechos or {})}
        self._exigir_memoria_valida(nueva, kb)
        self.integraciones.validar_certezas(kb, sesion["fc_reglas"], nuevos_fc)
        memoria.update(nueva)
        sesion["fc_hechos"] = nuevos_fc
        return memoria

    def siguiente_pregunta(self, session_id: str) -> dict:
        """Proximo dato que conviene pedir, con su explicacion WHY.

        En una sesion "atras" lo decide BackwardEngine (G6) a partir de la meta.
        En una sesion "adelante" se recorren las reglas de mayor a menor
        prioridad, se descartan las que ya no pueden cumplirse con los hechos
        conocidos y se devuelve el primer atributo que falta y que el usuario
        puede responder (no lo concluye ninguna regla y, si tiene depends_on,
        su condicion se cumple).
        """
        memoria = self.obtener_memoria(session_id)
        kb = self._kb_de(session_id)
        if self._usa_motor_atras(session_id):
            return self._siguiente_pregunta_atras(session_id, kb, memoria)
        conocidos = self._conocidos(memoria)
        atributos = {a["id"]: a for a in kb["attributes"]}
        concluidos = {r["conclusion"]["attribute_id"] for r in kb["rules"]}

        for regla in sorted(kb["rules"], key=lambda r: -r.get("priority", 0)):
            if regla["conclusion"]["attribute_id"] in conocidos:
                continue
            if any(c["attribute_id"] in conocidos
                   and not cumple(c["operator"], conocidos[c["attribute_id"]], c["value"])
                   for c in regla["conditions"]):
                continue
            for cond in regla["conditions"]:
                attr = cond["attribute_id"]
                if attr in conocidos or attr in concluidos or attr not in atributos:
                    continue
                dep = atributos[attr].get("depends_on")
                if dep and not (dep["attribute_id"] in conocidos and
                                cumple(dep["operator"], conocidos[dep["attribute_id"]], dep["value"])):
                    continue
                why = self.integraciones.explicador(kb).explain_why(attr, regla["id"])
                self._sesion(session_id)["ultima_pregunta"] = (attr, regla["id"])
                return {"session_id": session_id, "completa": False,
                        "pregunta": self._pregunta(atributos[attr]), "explanation_why": why}
        return {"session_id": session_id, "completa": True, "pregunta": None,
                "explanation_why": None}

    def inferir(self, session_id: str) -> tuple[dict, str]:
        """Ejecuta el motor; devuelve (memoria actualizada, motivo de parada).

        Si ninguna regla se activa, la memoria queda sin hechos derivados; eso
        es un resultado valido, no un error.
        """
        sesion = self._sesion(session_id)
        memoria = sesion["memoria"]
        if not memoria["facts"]:
            raise EstadoInvalido("La sesión no tiene hechos ingresados; registre datos antes de inferir.")
        kb = self._kb_de(session_id)
        if self._usa_motor_atras(session_id):
            nueva, motivo = self.integraciones.inferir_atras(kb, self._meta_de(kb), memoria)
        else:
            nueva, motivo = self.integraciones.inferir_adelante(kb, memoria)
        nueva = self.integraciones.evaluar_certeza(kb, nueva, sesion["fc_reglas"],
                                                   sesion["fc_hechos"])
        memoria.update(nueva)
        return memoria, motivo

    def obtener_memoria(self, session_id: str) -> dict:
        return self._sesion(session_id)["memoria"]

    # --- Persistencia (G11) ---

    def guardar_sesion(self, session_id: str) -> dict:
        """Guarda la memoria de la sesion en disco con ESBConverter (G11)."""
        memoria = self.obtener_memoria(session_id)
        ruta = self.integraciones.guardar_sesion(memoria, self._kb_de(session_id),
                                                 self.carpeta_sesiones)
        return {"session_id": session_id, "ruta": str(ruta)}

    def listar_sesiones_guardadas(self) -> list[str]:
        return self.integraciones.listar_sesiones(self.carpeta_sesiones)

    def restaurar_sesion(self, session_id: str, kb_id: str, motor: Motor = Motor.adelante) -> dict:
        """Abre de nuevo una sesion guardada, validada contra la base kb_id."""
        kb = self.obtener_conocimiento(kb_id)
        if session_id in self._sesiones:
            raise EstadoInvalido(f"La sesión '{session_id}' ya está abierta.")
        try:
            memoria = self.integraciones.cargar_sesion(self.carpeta_sesiones, session_id, kb)
        except FileNotFoundError as exc:
            raise NoEncontrado(f"No hay una sesión guardada con el id '{session_id}'.") from exc
        self._abrir_sesion(session_id, kb_id, motor, memoria)
        return {"session_id": session_id, "kb_id": kb_id, "motor": motor}

    def obtener_dictamen(self, session_id: str) -> dict:
        """Construye dictamen_salida.json a partir de la memoria de la sesion."""
        memoria = self.obtener_memoria(session_id)
        meta = self._atributo_meta(memoria)
        derivado = memoria["derived_facts"][meta]
        explicador = self.integraciones.explicador(self._kb_de(session_id))
        return {
            "session_id": session_id,
            "final_outcome": str(derivado["value"]),
            "certainty_score": derivado.get("certainty_factor", 1.0),
            "explanation_how": self._traducir(explicador.explain_how, memoria, meta),
            "explanation_why": self._why_del_dictamen(session_id, derivado["derived_by_rule"]),
        }

    # --- Explicacion ---

    def explicar_how(self, session_id: str, attribute_id: str) -> list[str]:
        """Como se obtuvo el valor de attribute_id (G8)."""
        explicador = self.integraciones.explicador(self._kb_de(session_id))
        return self._traducir(explicador.explain_how, self.obtener_memoria(session_id), attribute_id)

    def explicar_why(self, session_id: str, attribute_id: str,
                     rule_id: str | None = None) -> tuple[str, str]:
        """Por que se solicita attribute_id (G8). Devuelve (rule_id, explicacion)."""
        kb = self._kb_de(session_id)
        if rule_id is None:
            candidatas = [r for r in kb["rules"]
                          if any(c["attribute_id"] == attribute_id for c in r["conditions"])]
            if not candidatas:
                raise NoEncontrado(f"Ninguna regla usa el atributo '{attribute_id}'.")
            rule_id = max(candidatas, key=lambda r: r.get("priority", 0))["id"]
        explicador = self.integraciones.explicador(kb)
        return rule_id, self._traducir(explicador.explain_why, attribute_id, rule_id)

    def obtener_traza(self, session_id: str) -> list[str]:
        """Una linea por regla aplicada, en orden de ejecucion (G8)."""
        explicador = self.integraciones.explicador(self._kb_de(session_id))
        return explicador.explain_trace(self.obtener_memoria(session_id))

    def generar_reporte(self, session_id: str, formato: str) -> str:
        """Reporte del dictamen en Markdown (G9 si esta disponible) o HTML."""
        d = self.obtener_dictamen(session_id)
        if formato == "md":
            reporte = self.integraciones.reporte_markdown(
                self._kb_de(session_id), self.obtener_memoria(session_id), d)
            if reporte:
                return reporte
        traza = self.obtener_traza(session_id)
        if formato == "html":
            how = "".join(f"<li>{html.escape(l)}</li>" for l in d["explanation_how"])
            pasos = "".join(f"<li>{html.escape(l)}</li>" for l in traza)
            return (f"<h1>Dictamen {html.escape(session_id)}</h1>"
                    f"<p><strong>Resultado:</strong> {html.escape(d['final_outcome'])}</p>"
                    f"<p><strong>Certeza:</strong> {d['certainty_score']}</p>"
                    f"<h2>Reglas aplicadas</h2><ol>{pasos}</ol>"
                    f"<h2>¿Cómo?</h2><ul>{how}</ul>"
                    f"<h2>¿Por qué?</h2><p>{html.escape(d['explanation_why'])}</p>")
        how = "\n".join(f"- {l}" for l in d["explanation_how"])
        pasos = "\n".join(f"1. {l}" for l in traza)
        return (f"# Dictamen {session_id}\n\n"
                f"**Resultado:** {d['final_outcome']}\n\n"
                f"**Certeza:** {d['certainty_score']}\n\n"
                f"## Reglas aplicadas\n\n{pasos}\n\n"
                f"## ¿Cómo?\n\n{how}\n\n"
                f"## ¿Por qué?\n\n{d['explanation_why']}\n")

    # --- internos ---

    def _nuevo_session_id(self) -> str:
        while True:
            session_id = f"sess_{datetime.now().year}_{next(self._session_ids):05d}"
            if session_id not in self._sesiones:
                return session_id

    def _abrir_sesion(self, session_id: str, kb_id: str, motor: Motor, memoria: dict,
                      fc_reglas: dict | None = None, fc_hechos: dict | None = None) -> None:
        self._sesiones[session_id] = {"kb_id": kb_id, "motor": motor, "memoria": memoria,
                                      "ultima_pregunta": None,
                                      "fc_reglas": dict(fc_reglas or {}),
                                      "fc_hechos": dict(fc_hechos or {})}

    def _usa_motor_atras(self, session_id: str) -> bool:
        return (self._sesion(session_id)["motor"] == Motor.atras
                and self.integraciones.hay_motor_atras)

    @staticmethod
    def _meta_de(kb: dict) -> str:
        """Meta del motor hacia atras: 'dictamen' o la conclusion de mayor prioridad."""
        conclusiones = [r["conclusion"]["attribute_id"] for r in kb["rules"]]
        if ATRIBUTO_META in conclusiones:
            return ATRIBUTO_META
        return max(kb["rules"], key=lambda r: r.get("priority", 0))["conclusion"]["attribute_id"]

    def _siguiente_pregunta_atras(self, session_id: str, kb: dict, memoria: dict) -> dict:
        pregunta = self.integraciones.siguiente_atras(kb, self._meta_de(kb), memoria)
        if pregunta is None:
            return {"session_id": session_id, "completa": True, "pregunta": None,
                    "explanation_why": None}
        attr, rule_id = pregunta.pop("attribute_id"), pregunta.pop("rule_id")
        why = self._traducir(self.integraciones.explicador(kb).explain_why, attr, rule_id)
        self._sesion(session_id)["ultima_pregunta"] = (attr, rule_id)
        return {"session_id": session_id, "completa": False,
                "pregunta": {"attribute_id": attr, **pregunta}, "explanation_why": why}

    def _sesion(self, session_id: str) -> dict:
        if session_id not in self._sesiones:
            raise NoEncontrado(f"No existe la sesión '{session_id}'.")
        return self._sesiones[session_id]

    def _kb_de(self, session_id: str) -> dict:
        return self.obtener_conocimiento(self._sesion(session_id)["kb_id"])

    def _exigir_memoria_valida(self, memoria: dict, kb: dict) -> None:
        errores = self.integraciones.validar_memoria(memoria, kb)
        if errores:
            raise ContratoInvalido("Los hechos no son válidos para la base de conocimiento.", errores)

    @staticmethod
    def _conocidos(memoria: dict) -> dict[str, Any]:
        return {**memoria["facts"],
                **{k: v["value"] for k, v in memoria["derived_facts"].items()}}

    @staticmethod
    def _atributo_meta(memoria: dict) -> str:
        """Atributo del dictamen: 'dictamen' o, si no existe, el ultimo derivado."""
        if ATRIBUTO_META in memoria["derived_facts"]:
            return ATRIBUTO_META
        if memoria["execution_trace"]:
            return memoria["execution_trace"][-1]["added_fact"]
        raise EstadoInvalido("Ninguna regla se activó todavía; no hay dictamen. "
                             "Registre los datos que faltan y ejecute la inferencia.")

    def _why_del_dictamen(self, session_id: str, regla_meta: str) -> str:
        """WHY referido a la regla que concluyo el dictamen.

        Explica el ultimo dato que se le pregunto al usuario si es premisa de esa
        regla; si no, la primera premisa de la regla.
        """
        kb = self._kb_de(session_id)
        regla = next(r for r in kb["rules"] if r["id"] == regla_meta)
        premisas = [c["attribute_id"] for c in regla["conditions"]]
        pregunta = self._sesion(session_id)["ultima_pregunta"]
        atributo = pregunta[0] if pregunta and pregunta[0] in premisas else premisas[0]
        explicador = self.integraciones.explicador(kb)
        return self._traducir(explicador.explain_why, atributo, regla_meta)

    @staticmethod
    def _traducir(funcion, *args):
        """Convierte los ValueError del explicador en NoEncontrado (404)."""
        try:
            return funcion(*args)
        except ValueError as exc:
            raise NoEncontrado(str(exc)) from exc

    @staticmethod
    def _pregunta(atributo: dict) -> dict:
        return {
            "attribute_id": atributo["id"],
            "question": atributo.get("question"),
            "type": atributo["type"],
            "options": copy.deepcopy(atributo.get("options", [])),
            "range": atributo.get("range"),
        }
