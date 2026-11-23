"""Conexion de la API con los modulos de los demas grupos.

Cada modulo se importa por separado. Si un grupo todavia no publico su codigo
(o el import falla), la API usa un respaldo propio y lo informa en /salud, de
modo que la suite siga funcionando con los modulos que si estan disponibles.

Modulos conectados:

- G3 KBAuditor: auditoria de la base (contradicciones, redundancias, ciclos).
- G4 SchemaManager: valida los contratos con los esquemas de contracts/.
- G5 ForwardEngine: encadenamiento hacia adelante.
- G7 UncertaintyEngine: factores de certeza de los hechos derivados.
- G8 XAIExplainer: explicaciones HOW, WHY y traza.
- G9 ReportGenerator: reporte en Markdown (solo si ya no es un stub).

Pendientes (sin codigo al 23 nov.): G6 BackwardEngine y G11 ESBConverter.
Cuando publiquen su clase, se agrega aqui un _cargar_gX() y su uso en
Integraciones, sin tocar servicio.py.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Iterable

RAIZ = Path(__file__).resolve().parent.parent
CONTRATOS = RAIZ / "contracts"


class ContratoInvalido(ValueError):
    """El documento no cumple el contrato JSON. Lleva la lista de errores."""

    def __init__(self, mensaje: str, errores: list[str]):
        super().__init__(mensaje)
        self.errores = errores


class ModuloNoDisponible(RuntimeError):
    """La operacion necesita un modulo que todavia no esta en el repositorio."""


# --- Carga de cada modulo ---

def _cargar_g3():
    try:
        from grupo_03_auditor import KBAuditor
    except ImportError:
        return None
    return KBAuditor


def _cargar_g4():
    try:
        from grupo_04_schema.esb_schema import SchemaManager
    except ImportError:
        return None
    carpeta = CONTRATOS if CONTRATOS.is_dir() else None
    return SchemaManager(carpeta_esquemas=carpeta)


def _cargar_g5():
    try:
        import grupo_05_forward as g5
    except ImportError:
        return None
    return g5


def _cargar_g7():
    try:
        import grupo_07_uncertainty as g7
    except ImportError:
        return None
    return g7


def _cargar_g8():
    try:
        from grupo_08_explainer import XAIExplainer
    except ImportError:
        return None
    return XAIExplainer


def _cargar_g9():
    try:
        from grupo_09_reporter import ReportGenerator
    except ImportError:
        return None
    try:
        ReportGenerator().generar_markdown()
    except NotImplementedError:
        return None  # todavia es el stub
    except Exception:
        pass  # implementado; falla solo porque no recibio archivos
    return ReportGenerator


# --- Respaldos ---

def cumple(operador: str, izquierda: Any, derecha: Any) -> bool:
    """Evalua una condicion con los operadores del contrato."""
    try:
        if operador == "==":
            return izquierda == derecha
        if operador == "!=":
            return izquierda != derecha
        if operador == ">":
            return izquierda > derecha
        if operador == "<":
            return izquierda < derecha
        if operador == ">=":
            return izquierda >= derecha
        if operador == "<=":
            return izquierda <= derecha
        if operador == "in":
            return izquierda in derecha
    except TypeError:
        return False
    return False


def _inferir_respaldo(kb: dict, memoria: dict) -> tuple[dict, str]:
    """Encadenamiento hacia adelante minimo, usado solo si falta G5."""
    reglas = sorted(kb["rules"], key=lambda r: -r.get("priority", 0))
    derivados = memoria["derived_facts"]
    traza = memoria["execution_trace"]
    while True:
        conocidos = {**memoria["facts"], **{k: v["value"] for k, v in derivados.items()}}
        regla = next((r for r in reglas
                      if r["conclusion"]["attribute_id"] not in conocidos
                      and all(c["attribute_id"] in conocidos
                              and cumple(c["operator"], conocidos[c["attribute_id"]], c["value"])
                              for c in r["conditions"])), None)
        if regla is None:
            return memoria, "quiescence"
        atributo = regla["conclusion"]["attribute_id"]
        derivados[atributo] = {"value": regla["conclusion"]["value"],
                               "derived_by_rule": regla["id"]}
        traza.append({"step": len(traza) + 1, "rule_fired": regla["id"], "added_fact": atributo})


class _ExplicadorRespaldo:
    """Textos minimos con la misma interfaz que XAIExplainer, si falta G8."""

    def __init__(self, knowledge_base: dict):
        self.rules = {r["id"]: r for r in knowledge_base.get("rules", [])}

    def explain_how(self, working_memory: dict, attribute_id: str) -> list[str]:
        derivado = working_memory.get("derived_facts", {}).get(attribute_id)
        if derivado is not None:
            return [f"Se determinó {derivado['value']!r} debido a la regla {derivado['derived_by_rule']}."]
        hechos = working_memory.get("facts", {})
        if attribute_id in hechos:
            return [f"'{attribute_id}' fue ingresado por el usuario: {hechos[attribute_id]!r}."]
        raise ValueError(f"'{attribute_id}' no tiene valor en la memoria de trabajo.")

    def explain_why(self, attribute_id: str, rule_id: str | None = None) -> str:
        if rule_id is None:
            candidatas = [r for r in self.rules.values()
                          if any(c["attribute_id"] == attribute_id for c in r["conditions"])]
            if not candidatas:
                raise ValueError(f"Ninguna regla usa el atributo '{attribute_id}'.")
            rule_id = max(candidatas, key=lambda r: r.get("priority", 0))["id"]
        if rule_id not in self.rules:
            raise ValueError(f"La regla '{rule_id}' no está en la base de conocimiento.")
        return f"Se solicitó '{attribute_id}' para evaluar la condición de la regla {rule_id}."

    def explain_trace(self, working_memory: dict) -> list[str]:
        derivados = working_memory.get("derived_facts", {})
        return [f"Paso {p['step']}: {p['rule_fired']} agregó {p['added_fact']} = "
                f"{derivados.get(p['added_fact'], {}).get('value')!r}"
                for p in working_memory.get("execution_trace", [])]


# --- Fachada ---

class Integraciones:
    """Punto unico de contacto con los modulos de los demas grupos.

    deshabilitar permite forzar el respaldo de un grupo (por ejemplo {"G5"}),
    lo que usan las pruebas para comprobar que la API sigue respondiendo.
    """

    def __init__(self, deshabilitar: Iterable[str] = ()):
        apagados = set(deshabilitar)
        self._g3 = None if "G3" in apagados else _cargar_g3()
        self._g4 = None if "G4" in apagados else _cargar_g4()
        self._g5 = None if "G5" in apagados else _cargar_g5()
        self._g7 = None if "G7" in apagados else _cargar_g7()
        self._g8 = None if "G8" in apagados else _cargar_g8()
        self._g9 = None if "G9" in apagados else _cargar_g9()

    def estado(self) -> dict[str, str]:
        def marca(modulo):
            return "real" if modulo is not None else "simulado"
        return {
            "G3 KBAuditor": marca(self._g3),
            "G4 SchemaManager": marca(self._g4),
            "G5 ForwardEngine": marca(self._g5),
            "G6 BackwardEngine": "simulado",
            "G7 UncertaintyEngine": marca(self._g7),
            "G8 XAIExplainer": marca(self._g8),
            "G9 ReportGenerator": marca(self._g9),
            "G11 ESBConverter": "simulado",
        }

    # G4
    def validar(self, datos: dict, tipo: str) -> list[str]:
        if self._g4 is None:
            return []
        return self._g4.validar_datos(datos, tipo)["errores"]

    def validar_memoria(self, memoria: dict, kb: dict) -> list[str]:
        if self._g4 is None:
            return []
        return self._g4.validar_memoria(memoria, kb)["errores"]

    # G5
    def inferir_adelante(self, kb: dict, memoria: dict) -> tuple[dict, str]:
        """Ejecuta el motor sobre una copia de la memoria; devuelve (memoria, motivo de parada)."""
        if self._g5 is None:
            return _inferir_respaldo(kb, json.loads(json.dumps(memoria)))
        g5 = self._g5
        try:
            motor = g5.ForwardEngine(g5.parse_knowledge_base(kb))
            resultado = motor.run(g5.parse_working_memory(memoria))
        except g5.ForwardEngineError as exc:
            raise ContratoInvalido("El motor rechazó la base o la memoria.", [str(exc)]) from exc
        return g5.working_memory_to_dict(resultado.working_memory), resultado.halted_reason

    # G7
    def _motor_certeza(self, kb: dict, fc_reglas: dict | None, fc_hechos: dict | None):
        try:
            return self._g7.UncertaintyEngine(kb, rule_cfs=fc_reglas or None,
                                              fact_cfs=fc_hechos or None)
        except self._g7.UncertaintyError as exc:
            raise ContratoInvalido("Los factores de certeza no son válidos.", [str(exc)]) from exc

    def validar_certezas(self, kb: dict, fc_reglas: dict | None, fc_hechos: dict | None) -> None:
        """Comprueba que los FC citen reglas y atributos de la base (G7)."""
        if self._g7 is not None:
            self._motor_certeza(kb, fc_reglas, fc_hechos)

    def evaluar_certeza(self, kb: dict, memoria: dict, fc_reglas: dict | None = None,
                        fc_hechos: dict | None = None) -> dict:
        """Memoria con certainty_factor en cada hecho derivado (G7).

        Sin G7, la memoria se devuelve igual y el dictamen usa 1.0.
        """
        if self._g7 is None:
            return memoria
        try:
            return self._motor_certeza(kb, fc_reglas, fc_hechos).evaluate(memoria)
        except self._g7.UncertaintyError as exc:
            raise ContratoInvalido("No se pudo calcular la certeza.", [str(exc)]) from exc

    # G3
    def auditar(self, kb: dict):
        """ReporteAuditoria de G3 para la base; ModuloNoDisponible si falta G3."""
        if self._g3 is None:
            raise ModuloNoDisponible("El auditor de base de conocimiento (G3) todavía no está "
                                     "integrado en el repositorio.")
        return self._g3(kb, schema_manager=self._g4, usar_schema_manager=False).auditar()

    # G8
    def explicador(self, kb: dict):
        clase = self._g8 or _ExplicadorRespaldo
        return clase(kb)

    # G9
    def reporte_markdown(self, kb: dict, memoria: dict, dictamen: dict) -> str | None:
        """Reporte de G9, o None si no esta disponible o falla."""
        if self._g9 is None:
            return None
        with tempfile.TemporaryDirectory() as carpeta:
            rutas = []
            for nombre, datos in (("conocimiento_dominio", kb), ("memoria_trabajo", memoria),
                                  ("dictamen_salida", dictamen)):
                ruta = Path(carpeta) / f"{nombre}.json"
                ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
                rutas.append(str(ruta))
            try:
                return self._g9(*rutas).generar_markdown()
            except Exception:
                return None
