"""Grupo 3 — Auditor de Base de Conocimiento (KBAuditor) de ES-Shell Suite.

Módulo de análisis estático y auditoría lógica para archivos
``conocimiento_dominio.json``. Opera sobre el contrato oficial definido en
``contracts/conocimiento_dominio.schema.json`` sin ejecutar inferencias ni
modificar la base de conocimiento.

Capacidades principales:
- Carga segura desde diccionario Python o archivo JSON (con validación opcional
  previa mediante ``SchemaManager`` del Grupo 4 y fallback independiente).
- Detección de reglas contradictorias (conflictos de condiciones equivalentes o
  solapables con distinta conclusión, diferenciando empates de prioridad).
- Detección de reglas redundantes (duplicadas) y subsumidas.
- Detección de condiciones inalcanzables, contradicciones internas, valores
  fuera de ``range`` u ``options``, atributos inexistentes o imposibles de
  obtener y validación completa de ``depends_on``.
- Detección de ciclos directos e indirectos en el grafo de reglas y en
  ``depends_on``.
- Generación de Tablas de Decisión y reportes estructurados en dict, JSON y
  Markdown.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TIPOS_VALIDOS: tuple[str, ...] = ("numeric", "categorical", "boolean", "text")
OPERADORES_VALIDOS: tuple[str, ...] = ("==", "!=", ">", "<", ">=", "<=", "in")
OPERADORES_ORDEN: frozenset[str] = frozenset({">", "<", ">=", "<="})
CAMPOS_REGLA: frozenset[str] = frozenset(
    {"id", "description", "priority", "conditions", "conclusion", "explanation_template"}
)

SEVERIDAD_ERROR = "ERROR"
SEVERIDAD_WARNING = "WARNING"
SEVERIDAD_INFO = "INFO"

CAT_ESQUEMA = "esquema_invalido"
CAT_CONTRADICCION = "contradiccion"
CAT_REDUNDANCIA = "redundancia"
CAT_INALCANZABLE = "condicion_inalcanzable"
CAT_CICLO = "ciclo"


# ---------------------------------------------------------------------------
# Utilidades de tipos y comparación segura
# ---------------------------------------------------------------------------


def _es_numero(valor: Any) -> bool:
    """True si ``valor`` es int/float finito y NO booleano."""
    return (
        not isinstance(valor, bool)
        and isinstance(valor, (int, float))
        and math.isfinite(valor)
    )


def _valor_clave(valor: Any) -> tuple[str, Any]:
    """Genera una clave hashable y sensible al tipo (evita ``True == 1``)."""
    if isinstance(valor, bool):
        return ("bool", valor)
    if _es_numero(valor):
        return ("num", float(valor))
    if isinstance(valor, str):
        return ("str", valor)
    if valor is None:
        return ("null", None)
    try:
        return ("json", json.dumps(valor, sort_keys=True, ensure_ascii=False))
    except (TypeError, ValueError):
        return ("repr", repr(valor))


def _valores_iguales(a: Any, b: Any) -> bool:
    return _valor_clave(a) == _valor_clave(b)


def _formatear_valor(valor: Any) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, str):
        return f"'{valor}'"
    if isinstance(valor, list):
        return "[" + ", ".join(_formatear_valor(v) for v in valor) + "]"
    return str(valor)


def _extraer_opciones_atributo(atributo: dict[str, Any]) -> list[Any] | None:
    """Extrae los valores permitidos de ``options`` (soporta str y {value, label})."""
    opciones = atributo.get("options")
    if not isinstance(opciones, list) or not opciones:
        return None
    valores: list[Any] = []
    for item in opciones:
        if isinstance(item, dict) and "value" in item:
            valores.append(item["value"])
        else:
            valores.append(item)
    return valores if valores else None


def _rango_valido(atributo: dict[str, Any]) -> tuple[float, float] | None:
    rango = atributo.get("range")
    if (
        isinstance(rango, list)
        and len(rango) == 2
        and _es_numero(rango[0])
        and _es_numero(rango[1])
        and float(rango[0]) <= float(rango[1])
    ):
        return (float(rango[0]), float(rango[1]))
    return None


def _rechazar_constante_json(constante: str) -> None:
    raise ValueError(f"Constante numérica no válida en JSON estándar: {constante}")


# ---------------------------------------------------------------------------
# Álgebra de dominios para análisis lógico exacto de condiciones
# ---------------------------------------------------------------------------


class _Dominio:
    """Interfaz base de un dominio lógico de valores posibles para un atributo."""

    def es_vacio(self) -> bool:
        raise NotImplementedError

    def intersectar(self, otro: "_Dominio") -> "_Dominio":
        raise NotImplementedError

    def es_subconjunto_de(self, otro: "_Dominio") -> bool:
        raise NotImplementedError

    def equivale_a(self, otro: "_Dominio") -> bool:
        return self.es_subconjunto_de(otro) and otro.es_subconjunto_de(self)


class _DominioNumerico(_Dominio):
    """Subconjunto exacto de R: intervalo (con inclusiones), exclusiones y conjunto finito opcional."""

    def __init__(
        self,
        low: float = -math.inf,
        low_inc: bool = False,
        high: float = math.inf,
        high_inc: bool = False,
        excluded: frozenset[float] = frozenset(),
        allowed: frozenset[float] | None = None,
    ) -> None:
        self.low = float(low)
        self.low_inc = bool(low_inc) and math.isfinite(self.low)
        self.high = float(high)
        self.high_inc = bool(high_inc) and math.isfinite(self.high)
        self.excluded = frozenset(excluded)
        self.allowed = allowed
        self._normalizar()

    def _en_intervalo(self, x: float) -> bool:
        if x < self.low or (x == self.low and not self.low_inc):
            return False
        if x > self.high or (x == self.high and not self.high_inc):
            return False
        return True

    def _normalizar(self) -> None:
        if self.allowed is not None:
            filtrados = frozenset(
                x for x in self.allowed if self._en_intervalo(x) and x not in self.excluded
            )
            self.allowed = filtrados
            if filtrados:
                self.low = min(filtrados)
                self.low_inc = True
                self.high = max(filtrados)
                self.high_inc = True
            else:
                self.low = 1.0
                self.high = -1.0
                self.low_inc = False
                self.high_inc = False
            self.excluded = frozenset()
            return

        # Ajustar extremos si están excluidos
        excl = set(self.excluded)
        if self.low_inc and self.low in excl:
            self.low_inc = False
            excl.discard(self.low)
        if self.high_inc and self.high in excl:
            self.high_inc = False
            excl.discard(self.high)

        # Filtrar exclusiones que ya están fuera del intervalo
        excl = {x for x in excl if self._en_intervalo(x)}

        if self.low > self.high:
            self.allowed = frozenset()
            self.excluded = frozenset()
            return

        if self.low == self.high:
            if self.low_inc and self.high_inc and self.low not in excl:
                self.allowed = frozenset({self.low})
                self.excluded = frozenset()
            else:
                self.allowed = frozenset()
                self.excluded = frozenset()
            return

        self.excluded = frozenset(excl)

    def contiene(self, x: float) -> bool:
        if self.allowed is not None:
            return x in self.allowed
        return self._en_intervalo(x) and x not in self.excluded

    def aplicar(self, operador: str, valor: Any) -> "_DominioNumerico":
        if operador == "==":
            if not _es_numero(valor):
                return _DominioNumerico(allowed=frozenset())
            v = float(valor)
            nuevo_allowed = (
                frozenset({v}) if self.allowed is None else self.allowed & {v}
            )
            return _DominioNumerico(
                self.low, self.low_inc, self.high, self.high_inc, self.excluded, nuevo_allowed
            )
        if operador == "!=":
            if not _es_numero(valor):
                return self
            v = float(valor)
            return _DominioNumerico(
                self.low,
                self.low_inc,
                self.high,
                self.high_inc,
                self.excluded | {v},
                self.allowed,
            )
        if operador == ">":
            if not _es_numero(valor):
                return _DominioNumerico(allowed=frozenset())
            v = float(valor)
            low, low_inc = self.low, self.low_inc
            if v > low or (v == low and low_inc):
                low, low_inc = v, False
            return _DominioNumerico(
                low, low_inc, self.high, self.high_inc, self.excluded, self.allowed
            )
        if operador == ">=":
            if not _es_numero(valor):
                return _DominioNumerico(allowed=frozenset())
            v = float(valor)
            low, low_inc = self.low, self.low_inc
            if v > low:
                low, low_inc = v, True
            return _DominioNumerico(
                low, low_inc, self.high, self.high_inc, self.excluded, self.allowed
            )
        if operador == "<":
            if not _es_numero(valor):
                return _DominioNumerico(allowed=frozenset())
            v = float(valor)
            high, high_inc = self.high, self.high_inc
            if v < high or (v == high and high_inc):
                high, high_inc = v, False
            return _DominioNumerico(
                self.low, self.low_inc, high, high_inc, self.excluded, self.allowed
            )
        if operador == "<=":
            if not _es_numero(valor):
                return _DominioNumerico(allowed=frozenset())
            v = float(valor)
            high, high_inc = self.high, self.high_inc
            if v < high:
                high, high_inc = v, True
            return _DominioNumerico(
                self.low, self.low_inc, high, high_inc, self.excluded, self.allowed
            )
        if operador == "in":
            if not isinstance(valor, list):
                return _DominioNumerico(allowed=frozenset())
            vals = frozenset(float(x) for x in valor if _es_numero(x))
            nuevo_allowed = vals if self.allowed is None else self.allowed & vals
            return _DominioNumerico(
                self.low, self.low_inc, self.high, self.high_inc, self.excluded, nuevo_allowed
            )
        return _DominioNumerico(allowed=frozenset())

    def es_vacio(self) -> bool:
        return self.allowed is not None and len(self.allowed) == 0

    def intersectar(self, otro: _Dominio) -> _Dominio:
        if not isinstance(otro, _DominioNumerico):
            return _DominioNumerico(allowed=frozenset())
        if self.es_vacio() or otro.es_vacio():
            return _DominioNumerico(allowed=frozenset())

        if self.low > otro.low:
            low, low_inc = self.low, self.low_inc
        elif otro.low > self.low:
            low, low_inc = otro.low, otro.low_inc
        else:
            low, low_inc = self.low, (self.low_inc and otro.low_inc)

        if self.high < otro.high:
            high, high_inc = self.high, self.high_inc
        elif otro.high < self.high:
            high, high_inc = otro.high, otro.high_inc
        else:
            high, high_inc = self.high, (self.high_inc and otro.high_inc)

        if self.allowed is not None and otro.allowed is not None:
            allowed: frozenset[float] | None = self.allowed & otro.allowed
        elif self.allowed is not None:
            allowed = self.allowed
        else:
            allowed = otro.allowed

        return _DominioNumerico(
            low, low_inc, high, high_inc, self.excluded | otro.excluded, allowed
        )

    def es_subconjunto_de(self, otro: _Dominio) -> bool:
        if self.es_vacio():
            return True
        if not isinstance(otro, _DominioNumerico) or otro.es_vacio():
            return False

        if self.allowed is not None:
            return all(otro.contiene(x) for x in self.allowed)

        # self es un intervalo infinito (no degenerado)
        if otro.allowed is not None:
            return False

        if self.low < otro.low or (self.low == otro.low and self.low_inc and not otro.low_inc):
            return False
        if self.high > otro.high or (self.high == otro.high and self.high_inc and not otro.high_inc):
            return False

        # Ningún punto excluido en 'otro' puede pertenecer a 'self'
        for e in otro.excluded:
            if self.contiene(e):
                return False
        return True


class _DominioFinito(_Dominio):
    """Dominio discreto finito (``categorical`` con opciones o ``boolean``)."""

    def __init__(self, claves: frozenset[tuple[str, Any]]) -> None:
        self.claves = claves

    @classmethod
    def desde_valores(cls, valores: list[Any]) -> "_DominioFinito":
        return cls(frozenset(_valor_clave(v) for v in valores))

    def aplicar(self, operador: str, valor: Any) -> "_DominioFinito":
        if operador == "==":
            k = _valor_clave(valor)
            return _DominioFinito(self.claves & {k})
        if operador == "!=":
            k = _valor_clave(valor)
            return _DominioFinito(self.claves - {k})
        if operador == "in":
            if not isinstance(valor, list):
                return _DominioFinito(frozenset())
            ks = frozenset(_valor_clave(v) for v in valor)
            return _DominioFinito(self.claves & ks)
        return _DominioFinito(frozenset())

    def es_vacio(self) -> bool:
        return len(self.claves) == 0

    def intersectar(self, otro: _Dominio) -> _Dominio:
        if isinstance(otro, _DominioFinito):
            return _DominioFinito(self.claves & otro.claves)
        if isinstance(otro, _DominioAbierto):
            if otro.allowed is not None:
                return _DominioFinito(self.claves & otro.allowed)
            return _DominioFinito(self.claves - otro.excluded)
        return _DominioFinito(frozenset())

    def es_subconjunto_de(self, otro: _Dominio) -> bool:
        if self.es_vacio():
            return True
        if isinstance(otro, _DominioFinito):
            return self.claves <= otro.claves
        if isinstance(otro, _DominioAbierto):
            if otro.allowed is not None:
                return self.claves <= otro.allowed
            return self.claves.isdisjoint(otro.excluded)
        return False


class _DominioAbierto(_Dominio):
    """Dominio discreto sobre universo infinito (``text`` o atributo sin opciones fijas)."""

    def __init__(
        self,
        allowed: frozenset[tuple[str, Any]] | None = None,
        excluded: frozenset[tuple[str, Any]] = frozenset(),
    ) -> None:
        if allowed is not None:
            self.allowed: frozenset[tuple[str, Any]] | None = allowed - excluded
            self.excluded: frozenset[tuple[str, Any]] = frozenset()
        else:
            self.allowed = None
            self.excluded = excluded

    def aplicar(self, operador: str, valor: Any) -> "_DominioAbierto":
        if operador == "==":
            k = _valor_clave(valor)
            if self.allowed is None:
                return _DominioAbierto(allowed=frozenset({k}) - self.excluded)
            return _DominioAbierto(allowed=self.allowed & {k})
        if operador == "!=":
            k = _valor_clave(valor)
            if self.allowed is None:
                return _DominioAbierto(allowed=None, excluded=self.excluded | {k})
            return _DominioAbierto(allowed=self.allowed - {k})
        if operador == "in":
            if not isinstance(valor, list):
                return _DominioAbierto(allowed=frozenset())
            ks = frozenset(_valor_clave(v) for v in valor)
            if self.allowed is None:
                return _DominioAbierto(allowed=ks - self.excluded)
            return _DominioAbierto(allowed=self.allowed & ks)
        return _DominioAbierto(allowed=frozenset())

    def es_vacio(self) -> bool:
        return self.allowed is not None and len(self.allowed) == 0

    def intersectar(self, otro: _Dominio) -> _Dominio:
        if isinstance(otro, _DominioFinito):
            return otro.intersectar(self)
        if not isinstance(otro, _DominioAbierto):
            return _DominioAbierto(allowed=frozenset())
        if self.allowed is not None and otro.allowed is not None:
            return _DominioAbierto(allowed=self.allowed & otro.allowed)
        if self.allowed is not None:
            return _DominioAbierto(allowed=self.allowed - otro.excluded)
        if otro.allowed is not None:
            return _DominioAbierto(allowed=otro.allowed - self.excluded)
        return _DominioAbierto(allowed=None, excluded=self.excluded | otro.excluded)

    def es_subconjunto_de(self, otro: _Dominio) -> bool:
        if self.es_vacio():
            return True
        if isinstance(otro, _DominioFinito):
            if self.allowed is None:
                return False
            return self.allowed <= otro.claves
        if not isinstance(otro, _DominioAbierto):
            return False
        if self.allowed is not None:
            if otro.allowed is not None:
                return self.allowed <= otro.allowed
            return self.allowed.isdisjoint(otro.excluded)
        if otro.allowed is not None:
            return False
        return otro.excluded <= self.excluded


# ---------------------------------------------------------------------------
# Modelos de hallazgo y reporte
# ---------------------------------------------------------------------------


@dataclass
class Hallazgo:
    """Representa un hallazgo individual de la auditoría."""

    categoria: str
    severidad: str
    mensaje: str
    reglas: list[str] = field(default_factory=list)
    atributos: list[str] = field(default_factory=list)
    detalles: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "categoria": self.categoria,
            "severidad": self.severidad,
            "mensaje": self.mensaje,
            "reglas": list(self.reglas),
            "atributos": list(self.atributos),
            "detalles": copy.deepcopy(self.detalles),
        }


@dataclass
class ReporteAuditoria:
    """Reporte estructurado completo de una auditoría de base de conocimiento."""

    es_valida: bool
    estado: str
    meta: dict[str, Any]
    resumen: dict[str, Any]
    hallazgos: list[Hallazgo]
    tabla_decision: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "es_valida": self.es_valida,
            "estado": self.estado,
            "meta": copy.deepcopy(self.meta),
            "resumen": copy.deepcopy(self.resumen),
            "hallazgos": [h.to_dict() for h in self.hallazgos],
            "tabla_decision": copy.deepcopy(self.tabla_decision),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent) + "\n"

    def to_markdown(self) -> str:
        return formatear_reporte_markdown(self)


# ---------------------------------------------------------------------------
# Formateadores de Tabla de Decisión y Reporte (Markdown / Consola)
# ---------------------------------------------------------------------------


def _escapar_celda_md(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def formatear_tabla_decision_markdown(tabla: dict[str, Any]) -> str:
    """Convierte la estructura ``tabla_decision`` en una tabla Markdown legible."""
    filas = tabla.get("filas", [])
    atributos_cond = tabla.get("atributos_condicion", [])

    if not filas:
        return "_No existen reglas válidas para construir la tabla de decisión._\n"

    encabezados = ["Regla", "Prioridad", *atributos_cond, "Conclusión", "Estado"]
    separadores = ["---", "---:", *(["---"] * len(atributos_cond)), "---", "---"]

    lineas = [
        "| " + " | ".join(_escapar_celda_md(h) for h in encabezados) + " |",
        "| " + " | ".join(separadores) + " |",
    ]

    for fila in filas:
        celdas = [
            f"`{fila['regla_id']}`",
            str(fila["prioridad"]),
        ]
        conds = fila.get("condiciones", {})
        for aid in atributos_cond:
            val = conds.get(aid, "—")
            celdas.append(f"`{val}`" if val != "—" else "—")
        celdas.append(f"`{fila['conclusion']}`")
        celdas.append(fila["estado"])
        lineas.append("| " + " | ".join(_escapar_celda_md(c) for c in celdas) + " |")

    return "\n".join(lineas) + "\n"


def formatear_tabla_decision_consola(tabla: dict[str, Any]) -> str:
    """Renderiza la tabla de decisión en texto plano alineado para consola."""
    filas = tabla.get("filas", [])
    atributos_cond = tabla.get("atributos_condicion", [])

    if not filas:
        return "(No existen reglas válidas para construir la tabla de decisión.)"

    encabezados = ["Regla", "Prio", *atributos_cond, "Conclusión", "Estado"]
    matriz: list[list[str]] = [encabezados]

    for fila in filas:
        conds = fila.get("condiciones", {})
        row = [
            str(fila["regla_id"]),
            str(fila["prioridad"]),
            *(str(conds.get(aid, "-")) for aid in atributos_cond),
            str(fila["conclusion"]),
            str(fila["estado"]),
        ]
        matriz.append(row)

    anchos = [max(len(fila[col]) for fila in matriz) for col in range(len(encabezados))]

    def _linea_sep(char: str = "-") -> str:
        return "+" + "+".join(char * (w + 2) for w in anchos) + "+"

    def _linea_datos(valores: list[str]) -> str:
        return "| " + " | ".join(v.ljust(anchos[i]) for i, v in enumerate(valores)) + " |"

    salida = [_linea_sep("-"), _linea_datos(matriz[0]), _linea_sep("=")]
    for fila in matriz[1:]:
        salida.append(_linea_datos(fila))
        salida.append(_linea_sep("-"))
    return "\n".join(salida)


def formatear_reporte_markdown(reporte: ReporteAuditoria) -> str:
    """Genera un informe completo de auditoría en formato Markdown."""
    titulo = reporte.meta.get("project_title") or "Base de conocimiento sin título"
    version = reporte.meta.get("version") or "N/A"
    autor = reporte.meta.get("author_group") or "N/A"
    res = reporte.resumen
    conteo = res["conteo_severidad"]

    lineas: list[str] = [
        f"# Reporte de Auditoría — {titulo}",
        "",
        "## Resumen general",
        "",
        f"- **Estado:** `{reporte.estado}` (`es_valida={reporte.es_valida}`)",
        f"- **Versión del dominio:** {version}",
        f"- **Grupo autor:** {autor}",
        f"- **Total de atributos:** {res['total_atributos']}",
        f"- **Total de reglas:** {res['total_reglas']}",
        f"- **Hallazgos totales:** {res['total_hallazgos']} "
        f"(ERROR: {conteo['ERROR']}, WARNING: {conteo['WARNING']}, INFO: {conteo['INFO']})",
        "",
        "## Hallazgos detectados",
        "",
    ]

    if not reporte.hallazgos:
        lineas.append("No se encontraron inconsistencias, redundancias ni ciclos en la base de conocimiento.")
        lineas.append("")
    else:
        for idx, h in enumerate(reporte.hallazgos, 1):
            reglas_txt = ", ".join(f"`{r}`" for r in h.reglas) if h.reglas else "—"
            attrs_txt = ", ".join(f"`{a}`" for a in h.atributos) if h.atributos else "—"
            lineas.append(f"### {idx}. [{h.severidad}] `{h.categoria}`")
            lineas.append("")
            lineas.append(f"- **Descripción:** {h.mensaje}")
            lineas.append(f"- **Reglas implicadas:** {reglas_txt}")
            lineas.append(f"- **Atributos implicados:** {attrs_txt}")
            lineas.append("")

    lineas.append("## Tabla de Decisión")
    lineas.append("")
    lineas.append(formatear_tabla_decision_markdown(reporte.tabla_decision).rstrip())
    lineas.append("")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Clase principal: KBAuditor
# ---------------------------------------------------------------------------


class KBAuditor:
    """Auditor estático de consistencia y generador de tablas de decisión (Grupo 3).

    Puede recibir un diccionario Python o una ruta a ``conocimiento_dominio.json``
    en el constructor o directamente en :meth:`auditar`.

    Parámetros:
        fuente: ``dict``, ``str``, ``Path`` o ``None``.
        schema_manager: instancia opcional de ``SchemaManager`` (Grupo 4) que
            exponga ``validar_datos(datos, tipo)``.
        usar_schema_manager: si es ``True`` y no se suministra ``schema_manager``,
            intenta cargar automáticamente ``SchemaManager`` del Grupo 4 con
            fallback seguro si el módulo o ``jsonschema`` no están disponibles.
    """

    def __init__(
        self,
        fuente: dict[str, Any] | str | Path | None = None,
        *,
        schema_manager: Any = None,
        usar_schema_manager: bool = True,
    ) -> None:
        self.schema_manager = (
            schema_manager
            if schema_manager is not None
            else (self._cargar_schema_manager_opcional() if usar_schema_manager else None)
        )
        self._datos: dict[str, Any] | None = None
        self._errores_carga: list[Hallazgo] = []
        self._ultimo_reporte: ReporteAuditoria | None = None

        if fuente is not None:
            self._cargar_fuente(fuente)

    @staticmethod
    def _cargar_schema_manager_opcional() -> Any:
        """Intenta instanciar SchemaManager del Grupo 4 sin acoplamiento rígido."""
        try:
            from grupo_04_schema.esb_schema import SchemaManager  # type: ignore

            return SchemaManager()
        except Exception:
            return None

    @classmethod
    def desde_archivo(
        cls,
        ruta: str | Path,
        *,
        schema_manager: Any = None,
        usar_schema_manager: bool = True,
    ) -> "KBAuditor":
        return cls(
            Path(ruta),
            schema_manager=schema_manager,
            usar_schema_manager=usar_schema_manager,
        )

    @classmethod
    def desde_dict(
        cls,
        datos: dict[str, Any],
        *,
        schema_manager: Any = None,
        usar_schema_manager: bool = True,
    ) -> "KBAuditor":
        return cls(
            datos,
            schema_manager=schema_manager,
            usar_schema_manager=usar_schema_manager,
        )

    # ------------------------------------------------------------------
    # Carga segura de fuentes
    # ------------------------------------------------------------------

    def cargar_archivo(self, ruta: str | Path) -> None:
        """Carga una base de conocimiento desde un archivo JSON sin lanzar errores no controlados."""
        self._datos = None
        self._errores_carga = []
        self._ultimo_reporte = None
        camino = Path(ruta)
        try:
            with camino.open("r", encoding="utf-8-sig") as f:
                contenido = json.load(f, parse_constant=_rechazar_constante_json)
        except FileNotFoundError:
            self._errores_carga.append(
                Hallazgo(
                    categoria=CAT_ESQUEMA,
                    severidad=SEVERIDAD_ERROR,
                    mensaje=f"No se encontró el archivo de base de conocimiento: '{camino}'.",
                    detalles={"ruta": str(camino)},
                )
            )
            return
        except json.JSONDecodeError as exc:
            self._errores_carga.append(
                Hallazgo(
                    categoria=CAT_ESQUEMA,
                    severidad=SEVERIDAD_ERROR,
                    mensaje=(
                        f"El archivo JSON está mal formado en la línea {exc.lineno}, "
                        f"columna {exc.colno}: {exc.msg}."
                    ),
                    detalles={"ruta": str(camino), "linea": exc.lineno, "columna": exc.colno},
                )
            )
            return
        except (ValueError, UnicodeError, OSError) as exc:
            self._errores_carga.append(
                Hallazgo(
                    categoria=CAT_ESQUEMA,
                    severidad=SEVERIDAD_ERROR,
                    mensaje=f"No se pudo leer el archivo JSON '{camino}': {exc}.",
                    detalles={"ruta": str(camino)},
                )
            )
            return

        self.cargar_datos(contenido)

    def cargar_datos(self, datos: Any) -> None:
        """Carga una base de conocimiento desde un objeto Python en memoria."""
        self._datos = None
        self._errores_carga = []
        self._ultimo_reporte = None

        if not isinstance(datos, dict):
            self._errores_carga.append(
                Hallazgo(
                    categoria=CAT_ESQUEMA,
                    severidad=SEVERIDAD_ERROR,
                    mensaje=(
                        "La base de conocimiento debe ser un objeto JSON (dict), "
                        f"pero se recibió '{type(datos).__name__}'."
                    ),
                )
            )
            return

        try:
            json.dumps(datos, allow_nan=False)
        except (TypeError, ValueError) as exc:
            self._errores_carga.append(
                Hallazgo(
                    categoria=CAT_ESQUEMA,
                    severidad=SEVERIDAD_ERROR,
                    mensaje=f"La base de conocimiento contiene valores no serializables en JSON estándar: {exc}.",
                )
            )

        self._datos = copy.deepcopy(datos)

    def _cargar_fuente(self, fuente: Any) -> None:
        if isinstance(fuente, (str, Path)):
            self.cargar_archivo(fuente)
        else:
            self.cargar_datos(fuente)

    # ------------------------------------------------------------------
    # Extracción segura de atributos y reglas
    # ------------------------------------------------------------------

    def _obtener_atributos_lista(self) -> list[dict[str, Any]]:
        if not isinstance(self._datos, dict):
            return []
        raw = self._datos.get("attributes")
        if not isinstance(raw, list):
            return []
        return [a for a in raw if isinstance(a, dict)]

    def _obtener_atributos_mapa(self) -> dict[str, dict[str, Any]]:
        mapa: dict[str, dict[str, Any]] = {}
        for attr in self._obtener_atributos_lista():
            aid = attr.get("id")
            if isinstance(aid, str) and aid.strip() and aid not in mapa:
                mapa[aid] = attr
        return mapa

    def _obtener_reglas_lista(self) -> list[dict[str, Any]]:
        if not isinstance(self._datos, dict):
            return []
        raw = self._datos.get("rules")
        if not isinstance(raw, list):
            return []
        return [r for r in raw if isinstance(r, dict)]

    def _atributos_derivados(self, reglas: list[dict[str, Any]]) -> set[str]:
        derivados: set[str] = set()
        for regla in reglas:
            conc = regla.get("conclusion")
            if isinstance(conc, dict):
                aid = conc.get("attribute_id")
                if isinstance(aid, str) and aid.strip():
                    derivados.add(aid)
        return derivados

    # ------------------------------------------------------------------
    # 1. Validación estructural / SchemaManager
    # ------------------------------------------------------------------

    def validar_esquema(self) -> list[Hallazgo]:
        """Valida estructura básica y, si está disponible, ejecuta SchemaManager (G4)."""
        hallazgos: list[Hallazgo] = list(self._errores_carga)
        if self._datos is None:
            if not hallazgos:
                hallazgos.append(
                    Hallazgo(
                        categoria=CAT_ESQUEMA,
                        severidad=SEVERIDAD_ERROR,
                        mensaje="No se ha cargado ninguna base de conocimiento para auditar.",
                    )
                )
            return hallazgos

        datos = self._datos
        valido_por_schema_manager = False

        if self.schema_manager is not None:
            fn = getattr(self.schema_manager, "validar_datos", None)
            if callable(fn):
                try:
                    resultado = fn(datos, "conocimiento_dominio")
                    valido_por_schema_manager = True
                    if isinstance(resultado, dict) and not resultado.get("valido", False):
                        for err in resultado.get("errores", []):
                            hallazgos.append(
                                Hallazgo(
                                    categoria=CAT_ESQUEMA,
                                    severidad=SEVERIDAD_ERROR,
                                    mensaje=f"Validación de esquema (SchemaManager): {err}",
                                    detalles={"origen": "SchemaManager", "error_bruto": str(err)},
                                )
                            )
                except Exception as exc:
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_WARNING,
                            mensaje=(
                                "No se pudo ejecutar SchemaManager; se aplicará la validación "
                                f"estructural interna ({exc})."
                            ),
                            detalles={"origen": "SchemaManager"},
                        )
                    )

        if not valido_por_schema_manager:
            hallazgos.extend(self._validar_estructura_interna(datos))

        return hallazgos

    def _validar_estructura_interna(self, datos: dict[str, Any]) -> list[Hallazgo]:
        """Fallback de validación estructural alineado a contracts/conocimiento_dominio.schema.json."""
        hallazgos: list[Hallazgo] = []

        # meta
        meta = datos.get("meta")
        if not isinstance(meta, dict):
            hallazgos.append(
                Hallazgo(
                    categoria=CAT_ESQUEMA,
                    severidad=SEVERIDAD_ERROR,
                    mensaje="Falta el bloque obligatorio 'meta' o no es un objeto JSON.",
                )
            )
        else:
            for campo in ("project_title", "version", "author_group"):
                val = meta.get(campo)
                if not isinstance(val, str) or not val.strip():
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=f"El campo obligatorio 'meta.{campo}' falta o está vacío.",
                        )
                    )

        # attributes
        attrs_raw = datos.get("attributes")
        if not isinstance(attrs_raw, list) or not attrs_raw:
            hallazgos.append(
                Hallazgo(
                    categoria=CAT_ESQUEMA,
                    severidad=SEVERIDAD_ERROR,
                    mensaje="El campo 'attributes' debe ser una lista no vacía de atributos.",
                )
            )
        else:
            ids_vistos: set[str] = set()
            for idx, attr in enumerate(attrs_raw):
                if not isinstance(attr, dict):
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=f"El elemento attributes[{idx}] debe ser un objeto JSON.",
                        )
                    )
                    continue
                aid = attr.get("id")
                if not isinstance(aid, str) or not aid.strip():
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=f"El atributo en posición {idx} no tiene un 'id' válido.",
                        )
                    )
                else:
                    if aid in ids_vistos:
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_ESQUEMA,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=f"El atributo '{aid}' está duplicado en 'attributes'.",
                                atributos=[aid],
                            )
                        )
                    ids_vistos.add(aid)

                nombre = attr.get("name")
                if not isinstance(nombre, str) or not nombre.strip():
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=f"El atributo '{aid or idx}' carece de un campo 'name' válido.",
                            atributos=[aid] if isinstance(aid, str) and aid else [],
                        )
                    )

                tipo = attr.get("type")
                if tipo not in TIPOS_VALIDOS:
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=(
                                f"El atributo '{aid or idx}' tiene tipo inválido '{tipo}'. "
                                f"Tipos permitidos: {', '.join(TIPOS_VALIDOS)}."
                            ),
                            atributos=[aid] if isinstance(aid, str) and aid else [],
                        )
                    )
                elif tipo == "categorical":
                    opciones = _extraer_opciones_atributo(attr)
                    if not opciones:
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_ESQUEMA,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=(
                                    f"El atributo categórico '{aid or idx}' debe declarar "
                                    "al menos una opción en 'options'."
                                ),
                                atributos=[aid] if isinstance(aid, str) and aid else [],
                            )
                        )
                elif tipo == "numeric" and "range" in attr and attr["range"] is not None:
                    rango = attr["range"]
                    if (
                        not isinstance(rango, list)
                        or len(rango) != 2
                        or not all(_es_numero(x) for x in rango)
                        or float(rango[0]) >= float(rango[1])
                    ):
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_ESQUEMA,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=(
                                    f"El atributo numérico '{aid or idx}' tiene un 'range' inválido "
                                    f"({rango!r}); se requiere [min, max] con min < max."
                                ),
                                atributos=[aid] if isinstance(aid, str) and aid else [],
                            )
                        )

        # rules
        rules_raw = datos.get("rules")
        if not isinstance(rules_raw, list) or not rules_raw:
            hallazgos.append(
                Hallazgo(
                    categoria=CAT_ESQUEMA,
                    severidad=SEVERIDAD_ERROR,
                    mensaje="El campo 'rules' debe ser una lista no vacía de reglas.",
                )
            )
        else:
            rids_vistos: set[str] = set()
            for idx, regla in enumerate(rules_raw):
                if not isinstance(regla, dict):
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=f"El elemento rules[{idx}] debe ser un objeto JSON.",
                        )
                    )
                    continue
                rid = regla.get("id")
                rid_label = rid if isinstance(rid, str) and rid.strip() else f"rules[{idx}]"
                faltantes = sorted(CAMPOS_REGLA - set(regla.keys()))
                if faltantes:
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=(
                                f"La regla '{rid_label}' omite campos obligatorios: "
                                f"{', '.join(faltantes)}."
                            ),
                            reglas=[rid_label],
                        )
                    )
                if not isinstance(rid, str) or not rid.strip():
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=f"La regla en posición {idx} no tiene un 'id' válido.",
                        )
                    )
                else:
                    if rid in rids_vistos:
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_ESQUEMA,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=f"El identificador de regla '{rid}' está duplicado.",
                                reglas=[rid],
                            )
                        )
                    rids_vistos.add(rid)

                prio = regla.get("priority")
                if "priority" in regla and (not isinstance(prio, int) or isinstance(prio, bool)):
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=f"La regla '{rid_label}' debe tener una prioridad entera.",
                            reglas=[rid_label],
                        )
                    )

                conds = regla.get("conditions")
                if "conditions" in regla and (not isinstance(conds, list) or not conds):
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_ESQUEMA,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=f"La regla '{rid_label}' debe contener al menos una condición.",
                            reglas=[rid_label],
                        )
                    )
                elif isinstance(conds, list):
                    for cidx, cond in enumerate(conds):
                        if not isinstance(cond, dict):
                            hallazgos.append(
                                Hallazgo(
                                    categoria=CAT_ESQUEMA,
                                    severidad=SEVERIDAD_ERROR,
                                    mensaje=(
                                        f"En la regla '{rid_label}', la condición #{cidx + 1} "
                                        "debe ser un objeto JSON."
                                    ),
                                    reglas=[rid_label],
                                )
                            )
                            continue
                        op = cond.get("operator")
                        if op not in OPERADORES_VALIDOS:
                            hallazgos.append(
                                Hallazgo(
                                    categoria=CAT_ESQUEMA,
                                    severidad=SEVERIDAD_ERROR,
                                    mensaje=(
                                        f"En la regla '{rid_label}', la condición #{cidx + 1} "
                                        f"usa un operador no soportado: {op!r}."
                                    ),
                                    reglas=[rid_label],
                                )
                            )
                        elif op == "in" and (
                            not isinstance(cond.get("value"), list) or not cond.get("value")
                        ):
                            hallazgos.append(
                                Hallazgo(
                                    categoria=CAT_ESQUEMA,
                                    severidad=SEVERIDAD_ERROR,
                                    mensaje=(
                                        f"En la regla '{rid_label}', el operador 'in' requiere "
                                        "una lista no vacía de valores."
                                    ),
                                    reglas=[rid_label],
                                )
                            )
                        elif op != "in" and isinstance(cond.get("value"), list):
                            hallazgos.append(
                                Hallazgo(
                                    categoria=CAT_ESQUEMA,
                                    severidad=SEVERIDAD_ERROR,
                                    mensaje=(
                                        f"En la regla '{rid_label}', el operador '{op}' "
                                        "no admite una lista como valor."
                                    ),
                                    reglas=[rid_label],
                                )
                            )

                conc = regla.get("conclusion")
                if "conclusion" in regla:
                    if (
                        not isinstance(conc, dict)
                        or not isinstance(conc.get("attribute_id"), str)
                        or not conc["attribute_id"].strip()
                        or "value" not in conc
                    ):
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_ESQUEMA,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=(
                                    f"La regla '{rid_label}' tiene una 'conclusion' incompleta "
                                    "(requiere 'attribute_id' y 'value')."
                                ),
                                reglas=[rid_label],
                            )
                        )

        return hallazgos

    # ------------------------------------------------------------------
    # Construcción de dominios por atributo y por regla
    # ------------------------------------------------------------------

    def _dominio_base_atributo(
        self,
        attr_id: str,
        atributos: dict[str, dict[str, Any]],
        condiciones_referencia: list[dict[str, Any]] | None = None,
        *,
        incluir_limites: bool = True,
    ) -> _Dominio:
        attr = atributos.get(attr_id)
        if attr is not None:
            tipo = attr.get("type")
            if tipo == "numeric":
                if incluir_limites:
                    rango = _rango_valido(attr)
                    if rango is not None:
                        return _DominioNumerico(rango[0], True, rango[1], True)
                return _DominioNumerico()
            if tipo == "categorical":
                if incluir_limites:
                    opciones = _extraer_opciones_atributo(attr)
                    if opciones:
                        return _DominioFinito.desde_valores(opciones)
                return _DominioAbierto()
            if tipo == "boolean":
                return _DominioFinito.desde_valores([True, False])
            return _DominioAbierto()

        # Atributo derivado no declarado en attributes: inferir dominio según operadores/valores
        conds = condiciones_referencia or []
        if any(c.get("operator") in OPERADORES_ORDEN for c in conds):
            return _DominioNumerico()
        valores_vistos: list[Any] = []
        for c in conds:
            v = c.get("value")
            if c.get("operator") == "in" and isinstance(v, list):
                valores_vistos.extend(v)
            elif "value" in c:
                valores_vistos.append(v)
        if valores_vistos and all(_es_numero(v) for v in valores_vistos):
            return _DominioNumerico()
        if valores_vistos and all(isinstance(v, bool) for v in valores_vistos):
            return _DominioFinito.desde_valores([True, False])
        return _DominioAbierto()

    def _construir_dominios_regla(
        self,
        regla: dict[str, Any],
        atributos: dict[str, dict[str, Any]],
        *,
        incluir_limites: bool = True,
    ) -> tuple[dict[str, _Dominio], bool]:
        """Devuelve ``(dominios_por_atributo, es_satisfacible)`` para una regla."""
        conds = regla.get("conditions")
        if not isinstance(conds, list) or not conds:
            return ({}, False)

        agrupadas: dict[str, list[dict[str, Any]]] = {}
        for cond in conds:
            if not isinstance(cond, dict):
                return ({}, False)
            aid = cond.get("attribute_id")
            op = cond.get("operator")
            if not isinstance(aid, str) or not aid.strip() or op not in OPERADORES_VALIDOS:
                return ({}, False)
            if "value" not in cond:
                return ({}, False)
            if op == "in" and (not isinstance(cond["value"], list) or not cond["value"]):
                return ({}, False)
            if op != "in" and isinstance(cond["value"], list):
                return ({}, False)
            agrupadas.setdefault(aid, []).append(cond)

        dominios: dict[str, _Dominio] = {}
        satisfacible = True
        for aid, lista_conds in agrupadas.items():
            dom = self._dominio_base_atributo(
                aid, atributos, lista_conds, incluir_limites=incluir_limites
            )
            for cond in lista_conds:
                dom = dom.aplicar(cond["operator"], cond["value"])
            dominios[aid] = dom
            if dom.es_vacio():
                satisfacible = False

        return (dominios, satisfacible)

    # ------------------------------------------------------------------
    # 2 y 3. Detección de contradicciones, redundancias y subsunción
    # ------------------------------------------------------------------

    def _analizar_pares_reglas(
        self,
    ) -> tuple[list[Hallazgo], list[Hallazgo]]:
        """Analiza todos los pares de reglas satisfacibles con igual atributo de conclusión."""
        contradicciones: list[Hallazgo] = []
        redundancias: list[Hallazgo] = []

        atributos = self._obtener_atributos_mapa()
        reglas = self._obtener_reglas_lista()
        derivados = self._atributos_derivados(reglas)

        # Precomputar dominios por regla y lista de condiciones por atributo (para derivados sin declarar)
        conds_por_attr: dict[str, list[dict[str, Any]]] = {}
        for r in reglas:
            for c in r.get("conditions", []) if isinstance(r.get("conditions"), list) else []:
                if isinstance(c, dict) and isinstance(c.get("attribute_id"), str):
                    conds_por_attr.setdefault(c["attribute_id"], []).append(c)

        def _regla_tiene_atributo_inalcanzable(regla: dict[str, Any]) -> bool:
            conds = regla.get("conditions")
            if not isinstance(conds, list):
                return True
            for cond in conds:
                if not isinstance(cond, dict):
                    return True
                aid = cond.get("attribute_id")
                if not isinstance(aid, str) or not aid.strip():
                    return True
                if aid not in atributos and aid not in derivados:
                    return True
                if aid in atributos:
                    attr = atributos[aid]
                    tiene_pregunta = (
                        isinstance(attr.get("question"), str)
                        and bool(attr["question"].strip())
                    )
                    if not tiene_pregunta and aid not in derivados:
                        return True
            return False

        evaluadas: list[tuple[dict[str, Any], dict[str, _Dominio], str, Any, int]] = []
        for idx, regla in enumerate(reglas):
            conc = regla.get("conclusion")
            if not isinstance(conc, dict):
                continue
            conc_attr = conc.get("attribute_id")
            if not isinstance(conc_attr, str) or not conc_attr.strip() or "value" not in conc:
                continue
            if _regla_tiene_atributo_inalcanzable(regla):
                continue
            doms, satisfacible = self._construir_dominios_regla(
                regla, atributos, incluir_limites=True
            )
            if not satisfacible:
                # Las reglas muertas ya se reportan en detectar_condiciones_inalcanzables().
                continue
            prio = regla.get("priority", 0)
            prio_int = prio if isinstance(prio, int) and not isinstance(prio, bool) else 0
            evaluadas.append((regla, doms, conc_attr, conc["value"], prio_int))

        n = len(evaluadas)
        for i in range(n):
            r_a, doms_a, attr_a, val_a, prio_a = evaluadas[i]
            id_a = str(r_a.get("id", f"rules[{i}]"))
            for j in range(i + 1, n):
                r_b, doms_b, attr_b, val_b, prio_b = evaluadas[j]
                if attr_a != attr_b:
                    continue
                id_b = str(r_b.get("id", f"rules[{j}]"))

                todos_attrs = sorted(set(doms_a.keys()) | set(doms_b.keys()))
                compatibles = True
                b_en_a = True  # S(B) <= S(A) -> A subsume a B
                a_en_b = True  # S(A) <= S(B) -> B subsume a A

                for aid in todos_attrs:
                    base = self._dominio_base_atributo(
                        aid, atributos, conds_por_attr.get(aid), incluir_limites=True
                    )
                    da = doms_a.get(aid, base)
                    db = doms_b.get(aid, base)

                    if da.intersectar(db).es_vacio():
                        compatibles = False
                        b_en_a = False
                        a_en_b = False
                        break
                    if b_en_a and not db.es_subconjunto_de(da):
                        b_en_a = False
                    if a_en_b and not da.es_subconjunto_de(db):
                        a_en_b = False

                if not compatibles:
                    continue

                equivalentes = a_en_b and b_en_a
                misma_conclusion = _valores_iguales(val_a, val_b)

                if not misma_conclusion:
                    empate = prio_a == prio_b
                    severidad = SEVERIDAD_ERROR if empate else SEVERIDAD_WARNING
                    relacion = "equivalentes" if equivalentes else "solapables"
                    if empate:
                        detalle_prio = (
                            f"Ambas tienen la misma prioridad ({prio_a}), lo que produce "
                            "una ambigüedad irresoluble."
                        )
                    else:
                        ganadora = id_a if prio_a > prio_b else id_b
                        detalle_prio = (
                            f"Prioridades distintas ({id_a}={prio_a}, {id_b}={prio_b}); "
                            f"la regla '{ganadora}' desempata por mayor prioridad, pero "
                            "conviene revisar el solapamiento."
                        )
                    contradicciones.append(
                        Hallazgo(
                            categoria=CAT_CONTRADICCION,
                            severidad=severidad,
                            mensaje=(
                                f"Conflicto entre '{id_a}' y '{id_b}': sus condiciones son "
                                f"{relacion}, pero concluyen valores distintos para '{attr_a}' "
                                f"({_formatear_valor(val_a)} vs {_formatear_valor(val_b)}). "
                                f"{detalle_prio}"
                            ),
                            reglas=[id_a, id_b],
                            atributos=[attr_a, *todos_attrs],
                            detalles={
                                "tipo": relacion,
                                "atributo_conclusion": attr_a,
                                "valores_conflicto": {id_a: val_a, id_b: val_b},
                                "prioridades": {id_a: prio_a, id_b: prio_b},
                                "empate_prioridad": empate,
                            },
                        )
                    )
                else:
                    if equivalentes:
                        redundancias.append(
                            Hallazgo(
                                categoria=CAT_REDUNDANCIA,
                                severidad=SEVERIDAD_WARNING,
                                mensaje=(
                                    f"Reglas duplicadas '{id_a}' y '{id_b}': tienen condiciones "
                                    f"lógicamente equivalentes y concluyen lo mismo "
                                    f"('{attr_a}' = {_formatear_valor(val_a)})."
                                ),
                                reglas=[id_a, id_b],
                                atributos=[attr_a, *todos_attrs],
                                detalles={
                                    "tipo": "duplicada",
                                    "atributo_conclusion": attr_a,
                                    "valor_conclusion": val_a,
                                    "prioridades": {id_a: prio_a, id_b: prio_b},
                                },
                            )
                        )
                    elif b_en_a:
                        redundancias.append(
                            Hallazgo(
                                categoria=CAT_REDUNDANCIA,
                                severidad=SEVERIDAD_WARNING,
                                mensaje=(
                                    f"Subsunción detectada: la regla '{id_a}' (más general) "
                                    f"subsume a '{id_b}' con la misma conclusión "
                                    f"('{attr_a}' = {_formatear_valor(val_a)}), haciendo a "
                                    f"'{id_b}' redundante."
                                ),
                                reglas=[id_a, id_b],
                                atributos=[attr_a, *todos_attrs],
                                detalles={
                                    "tipo": "subsumida",
                                    "regla_general": id_a,
                                    "regla_redundante": id_b,
                                    "atributo_conclusion": attr_a,
                                    "valor_conclusion": val_a,
                                    "prioridades": {id_a: prio_a, id_b: prio_b},
                                },
                            )
                        )
                    elif a_en_b:
                        redundancias.append(
                            Hallazgo(
                                categoria=CAT_REDUNDANCIA,
                                severidad=SEVERIDAD_WARNING,
                                mensaje=(
                                    f"Subsunción detectada: la regla '{id_b}' (más general) "
                                    f"subsume a '{id_a}' con la misma conclusión "
                                    f"('{attr_a}' = {_formatear_valor(val_a)}), haciendo a "
                                    f"'{id_a}' redundante."
                                ),
                                reglas=[id_b, id_a],
                                atributos=[attr_a, *todos_attrs],
                                detalles={
                                    "tipo": "subsumida",
                                    "regla_general": id_b,
                                    "regla_redundante": id_a,
                                    "atributo_conclusion": attr_a,
                                    "valor_conclusion": val_a,
                                    "prioridades": {id_a: prio_a, id_b: prio_b},
                                },
                            )
                        )

        return contradicciones, redundancias

    def detectar_contradicciones(self) -> list[Hallazgo]:
        """Detecta pares de reglas contradictorias (conflictos)."""
        contradicciones, _ = self._analizar_pares_reglas()
        return contradicciones

    def detectar_redundancias(self) -> list[Hallazgo]:
        """Detecta reglas duplicadas y reglas subsumidas."""
        _, redundancias = self._analizar_pares_reglas()
        return redundancias

    # ------------------------------------------------------------------
    # 4. Detección de condiciones inalcanzables, reglas muertas y depends_on
    # ------------------------------------------------------------------

    def _validar_condicion_contra_atributo(
        self,
        condicion: dict[str, Any],
        atributo: dict[str, Any],
        contexto: str,
        regla_id: str | None = None,
    ) -> list[Hallazgo]:
        """Comprueba si una condición individual es alcanzable según el tipo/rango/opciones."""
        hallazgos: list[Hallazgo] = []
        aid = str(atributo.get("id", condicion.get("attribute_id", "")))
        tipo = atributo.get("type")
        op = condicion.get("operator")
        reglas_ref = [regla_id] if regla_id else []

        if op not in OPERADORES_VALIDOS:
            hallazgos.append(
                Hallazgo(
                    categoria=CAT_INALCANZABLE,
                    severidad=SEVERIDAD_ERROR,
                    mensaje=f"{contexto}: operador inválido {op!r} sobre el atributo '{aid}'.",
                    reglas=reglas_ref,
                    atributos=[aid],
                    detalles={"motivo": "operador_invalido", "operador": op},
                )
            )
            return hallazgos

        if "value" not in condicion:
            hallazgos.append(
                Hallazgo(
                    categoria=CAT_INALCANZABLE,
                    severidad=SEVERIDAD_ERROR,
                    mensaje=f"{contexto}: la condición sobre '{aid}' no especifica 'value'.",
                    reglas=reglas_ref,
                    atributos=[aid],
                    detalles={"motivo": "valor_faltante"},
                )
            )
            return hallazgos

        valor = condicion["value"]

        if op == "in":
            if not isinstance(valor, list) or len(valor) == 0:
                hallazgos.append(
                    Hallazgo(
                        categoria=CAT_INALCANZABLE,
                        severidad=SEVERIDAD_ERROR,
                        mensaje=(
                            f"{contexto}: el operador 'in' sobre '{aid}' tiene una lista vacía "
                            "o no es una lista, por lo que nunca puede cumplirse."
                        ),
                        reglas=reglas_ref,
                        atributos=[aid],
                        detalles={"motivo": "in_lista_vacia"},
                    )
                )
                return hallazgos
        elif isinstance(valor, list):
            hallazgos.append(
                Hallazgo(
                    categoria=CAT_INALCANZABLE,
                    severidad=SEVERIDAD_ERROR,
                    mensaje=(
                        f"{contexto}: el operador '{op}' sobre '{aid}' no admite listas "
                        "como valor de comparación."
                    ),
                    reglas=reglas_ref,
                    atributos=[aid],
                    detalles={"motivo": "lista_en_operador_escalar"},
                )
            )
            return hallazgos

        if op in OPERADORES_ORDEN and tipo != "numeric":
            hallazgos.append(
                Hallazgo(
                    categoria=CAT_INALCANZABLE,
                    severidad=SEVERIDAD_ERROR,
                    mensaje=(
                        f"{contexto}: el operador de orden '{op}' no es aplicable al "
                        f"atributo '{aid}' de tipo '{tipo}'."
                    ),
                    reglas=reglas_ref,
                    atributos=[aid],
                    detalles={"motivo": "operador_incompatible", "tipo": tipo, "operador": op},
                )
            )
            return hallazgos

        valores_lista = valor if op == "in" else [valor]

        if tipo == "numeric":
            no_numericos = [v for v in valores_lista if not _es_numero(v)]
            if no_numericos:
                hallazgos.append(
                    Hallazgo(
                        categoria=CAT_INALCANZABLE,
                        severidad=SEVERIDAD_ERROR,
                        mensaje=(
                            f"{contexto}: el atributo numérico '{aid}' se compara con valores "
                            f"no numéricos ({no_numericos!r})."
                        ),
                        reglas=reglas_ref,
                        atributos=[aid],
                        detalles={"motivo": "tipo_incompatible", "valores": no_numericos},
                    )
                )
                return hallazgos

            rango = _rango_valido(atributo)
            if rango is not None:
                lo, hi = rango
                if op == "in":
                    fuera = [v for v in valores_lista if not (lo <= float(v) <= hi)]
                    dentro = [v for v in valores_lista if lo <= float(v) <= hi]
                    if not dentro:
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_INALCANZABLE,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=(
                                    f"{contexto}: todos los valores de '{aid} in {valor}' están "
                                    f"fuera del rango declarado [{lo}, {hi}]."
                                ),
                                reglas=reglas_ref,
                                atributos=[aid],
                                detalles={"motivo": "fuera_de_rango", "rango": [lo, hi], "valores": fuera},
                            )
                        )
                    elif fuera:
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_INALCANZABLE,
                                severidad=SEVERIDAD_WARNING,
                                mensaje=(
                                    f"{contexto}: la condición '{aid} in {valor}' incluye valores "
                                    f"fuera del rango declarado [{lo}, {hi}]: {fuera}."
                                ),
                                reglas=reglas_ref,
                                atributos=[aid],
                                detalles={"motivo": "parcialmente_fuera_de_rango", "rango": [lo, hi], "valores": fuera},
                            )
                        )
                else:
                    v = float(valor)
                    dom_rango = _DominioNumerico(lo, True, hi, True)
                    dom_res = dom_rango.aplicar(op, v)
                    if dom_res.es_vacio():
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_INALCANZABLE,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=(
                                    f"{contexto}: la condición '{aid} {op} {valor}' es imposible "
                                    f"de satisfacer dentro del rango declarado [{lo}, {hi}]."
                                ),
                                reglas=reglas_ref,
                                atributos=[aid],
                                detalles={"motivo": "fuera_de_rango", "rango": [lo, hi], "valor": valor},
                            )
                        )
                    elif not (lo <= v <= hi):
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_INALCANZABLE,
                                severidad=SEVERIDAD_WARNING,
                                mensaje=(
                                    f"{contexto}: el valor {valor} en '{aid} {op} {valor}' está "
                                    f"fuera del rango declarado [{lo}, {hi}]."
                                ),
                                reglas=reglas_ref,
                                atributos=[aid],
                                detalles={"motivo": "umbral_fuera_de_rango", "rango": [lo, hi], "valor": valor},
                            )
                        )

        elif tipo == "categorical":
            opciones = _extraer_opciones_atributo(atributo)
            if opciones is not None:
                claves_validas = {_valor_clave(o) for o in opciones}
                invalidos = [v for v in valores_lista if _valor_clave(v) not in claves_validas]
                validos = [v for v in valores_lista if _valor_clave(v) in claves_validas]
                if op == "==" and invalidos:
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_INALCANZABLE,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=(
                                f"{contexto}: el valor {_formatear_valor(valor)} en '{aid}' "
                                f"no existe en las opciones permitidas {opciones}."
                            ),
                            reglas=reglas_ref,
                            atributos=[aid],
                            detalles={"motivo": "opcion_invalida", "opciones": opciones, "valor": valor},
                        )
                    )
                elif op == "in":
                    if not validos:
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_INALCANZABLE,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=(
                                    f"{contexto}: ninguno de los valores de '{aid} in {valor}' "
                                    f"pertenece a las opciones permitidas {opciones}."
                                ),
                                reglas=reglas_ref,
                                atributos=[aid],
                                detalles={"motivo": "opcion_invalida", "opciones": opciones, "valores": invalidos},
                            )
                        )
                    elif invalidos:
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_INALCANZABLE,
                                severidad=SEVERIDAD_WARNING,
                                mensaje=(
                                    f"{contexto}: la condición '{aid} in {valor}' contiene opciones "
                                    f"no declaradas ({invalidos}); opciones válidas: {opciones}."
                                ),
                                reglas=reglas_ref,
                                atributos=[aid],
                                detalles={"motivo": "opcion_parcialmente_invalida", "opciones": opciones, "valores": invalidos},
                            )
                        )
                elif op == "!=" and invalidos:
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_INALCANZABLE,
                            severidad=SEVERIDAD_WARNING,
                            mensaje=(
                                f"{contexto}: el valor {_formatear_valor(valor)} en '{aid} != ...' "
                                f"no pertenece a las opciones permitidas {opciones} (condición siempre verdadera)."
                            ),
                            reglas=reglas_ref,
                            atributos=[aid],
                            detalles={"motivo": "opcion_invalida", "opciones": opciones, "valor": valor},
                        )
                    )

        elif tipo == "boolean":
            no_bool = [v for v in valores_lista if not isinstance(v, bool)]
            if no_bool:
                hallazgos.append(
                    Hallazgo(
                        categoria=CAT_INALCANZABLE,
                        severidad=SEVERIDAD_ERROR,
                        mensaje=(
                            f"{contexto}: el atributo booleano '{aid}' se compara con valores "
                            f"no booleanos ({no_bool!r})."
                        ),
                        reglas=reglas_ref,
                        atributos=[aid],
                        detalles={"motivo": "tipo_incompatible", "valores": no_bool},
                    )
                )

        elif tipo == "text":
            no_str = [v for v in valores_lista if not isinstance(v, str)]
            if no_str:
                hallazgos.append(
                    Hallazgo(
                        categoria=CAT_INALCANZABLE,
                        severidad=SEVERIDAD_ERROR,
                        mensaje=(
                            f"{contexto}: el atributo de texto '{aid}' se compara con valores "
                            f"que no son cadenas ({no_str!r})."
                        ),
                        reglas=reglas_ref,
                        atributos=[aid],
                        detalles={"motivo": "tipo_incompatible", "valores": no_str},
                    )
                )

        return hallazgos

    def detectar_condiciones_inalcanzables(self) -> list[Hallazgo]:
        """Detecta contradicciones internas, valores inválidos, atributos huérfanos y depends_on inválidos."""
        hallazgos: list[Hallazgo] = []
        atributos = self._obtener_atributos_mapa()
        reglas = self._obtener_reglas_lista()
        derivados = self._atributos_derivados(reglas)

        # 1. Revisar cada regla
        for idx, regla in enumerate(reglas):
            rid = str(regla.get("id", f"rules[{idx}]"))
            conds = regla.get("conditions")
            if not isinstance(conds, list):
                continue

            attrs_con_error_individual: set[str] = set()
            conds_por_attr: dict[str, list[dict[str, Any]]] = {}

            for cond in conds:
                if not isinstance(cond, dict):
                    continue
                aid = cond.get("attribute_id")
                op = cond.get("operator")
                if not isinstance(aid, str) or not aid.strip():
                    continue

                conds_por_attr.setdefault(aid, []).append(cond)

                # a) Referencia a atributo inexistente (ni declarado ni derivado)
                if aid not in atributos and aid not in derivados:
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_INALCANZABLE,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=(
                                f"Regla '{rid}': la condición referencia al atributo inexistente "
                                f"'{aid}' (no está declarado en 'attributes' ni es derivado por ninguna regla)."
                            ),
                            reglas=[rid],
                            atributos=[aid],
                            detalles={"motivo": "atributo_inexistente"},
                        )
                    )
                    attrs_con_error_individual.add(aid)
                    continue

                # b) Atributo declarado sin question y sin regla que lo derive
                if aid in atributos:
                    attr = atributos[aid]
                    tiene_pregunta = (
                        isinstance(attr.get("question"), str)
                        and bool(attr["question"].strip())
                    )
                    if not tiene_pregunta and aid not in derivados:
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_INALCANZABLE,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=(
                                    f"Regla '{rid}': el atributo '{aid}' se usa en una condición, "
                                    "pero no tiene 'question' para preguntarse al usuario ni es "
                                    "concluido por ninguna regla (hecho imposible de obtener)."
                                ),
                                reglas=[rid],
                                atributos=[aid],
                                detalles={"motivo": "atributo_sin_fuente"},
                            )
                        )

                    errs = self._validar_condicion_contra_atributo(
                        cond, attr, contexto=f"Regla '{rid}'", regla_id=rid
                    )
                    if any(e.severidad == SEVERIDAD_ERROR for e in errs):
                        attrs_con_error_individual.add(aid)
                    hallazgos.extend(errs)
                else:
                    # Atributo derivado no declarado en attributes: validar operadores básicos
                    if op == "in" and (
                        not isinstance(cond.get("value"), list) or not cond.get("value")
                    ):
                        hallazgos.append(
                            Hallazgo(
                                categoria=CAT_INALCANZABLE,
                                severidad=SEVERIDAD_ERROR,
                                mensaje=(
                                    f"Regla '{rid}': el operador 'in' sobre '{aid}' tiene lista vacía."
                                ),
                                reglas=[rid],
                                atributos=[aid],
                                detalles={"motivo": "in_lista_vacia"},
                            )
                        )
                        attrs_con_error_individual.add(aid)

            # c) Contradicciones internas entre múltiples condiciones sobre el mismo atributo
            for aid, lista_conds in conds_por_attr.items():
                if aid in attrs_con_error_individual:
                    continue
                if len(lista_conds) < 2:
                    continue
                dom_sin_limites = self._dominio_base_atributo(
                    aid, atributos, lista_conds, incluir_limites=False
                )
                dom_con_limites = self._dominio_base_atributo(
                    aid, atributos, lista_conds, incluir_limites=True
                )
                for cond in lista_conds:
                    if cond.get("operator") in OPERADORES_VALIDOS and "value" in cond:
                        dom_sin_limites = dom_sin_limites.aplicar(cond["operator"], cond["value"])
                        dom_con_limites = dom_con_limites.aplicar(cond["operator"], cond["value"])

                if dom_sin_limites.es_vacio() or dom_con_limites.es_vacio():
                    exprs = " Y ".join(
                        f"{aid} {c.get('operator')} {_formatear_valor(c.get('value'))}"
                        for c in lista_conds
                    )
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_INALCANZABLE,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=(
                                f"Regla '{rid}' muerta por contradicción interna sobre '{aid}': "
                                f"ningún valor puede satisfacer simultáneamente ({exprs})."
                            ),
                            reglas=[rid],
                            atributos=[aid],
                            detalles={"motivo": "contradiccion_interna", "expresion": exprs},
                        )
                    )

            # d) Validar conclusión si el atributo está declarado en attributes
            conc = regla.get("conclusion")
            if isinstance(conc, dict):
                c_aid = conc.get("attribute_id")
                if isinstance(c_aid, str) and c_aid in atributos and "value" in conc:
                    cond_simulada = {
                        "attribute_id": c_aid,
                        "operator": "==",
                        "value": conc["value"],
                    }
                    errs_conc = self._validar_condicion_contra_atributo(
                        cond_simulada,
                        atributos[c_aid],
                        contexto=f"Conclusión de regla '{rid}'",
                        regla_id=rid,
                    )
                    hallazgos.extend(errs_conc)

        # 2. Validar depends_on de todos los atributos
        for aid, attr in atributos.items():
            dep = attr.get("depends_on")
            if dep is None:
                continue
            if not isinstance(dep, dict):
                hallazgos.append(
                    Hallazgo(
                        categoria=CAT_INALCANZABLE,
                        severidad=SEVERIDAD_ERROR,
                        mensaje=f"El atributo '{aid}' tiene un campo 'depends_on' inválido (debe ser un objeto).",
                        atributos=[aid],
                        detalles={"motivo": "depends_on_invalido"},
                    )
                )
                continue

            dep_aid = dep.get("attribute_id")
            if not isinstance(dep_aid, str) or not dep_aid.strip():
                hallazgos.append(
                    Hallazgo(
                        categoria=CAT_INALCANZABLE,
                        severidad=SEVERIDAD_ERROR,
                        mensaje=f"El atributo '{aid}' tiene 'depends_on' sin 'attribute_id' válido.",
                        atributos=[aid],
                        detalles={"motivo": "depends_on_sin_atributo"},
                    )
                )
                continue

            if dep_aid == aid:
                # El ciclo directo en depends_on se reporta en detectar_ciclos()
                continue

            if dep_aid not in atributos:
                hallazgos.append(
                    Hallazgo(
                        categoria=CAT_INALCANZABLE,
                        severidad=SEVERIDAD_ERROR,
                        mensaje=(
                            f"El atributo '{aid}' tiene 'depends_on' hacia el atributo "
                            f"inexistente '{dep_aid}'."
                        ),
                        atributos=[aid, dep_aid],
                        detalles={"motivo": "depends_on_atributo_inexistente"},
                    )
                )
                continue

            dep_attr = atributos[dep_aid]
            dep_tiene_pregunta = (
                isinstance(dep_attr.get("question"), str)
                and bool(dep_attr["question"].strip())
            )
            if not dep_tiene_pregunta and dep_aid not in derivados:
                hallazgos.append(
                    Hallazgo(
                        categoria=CAT_INALCANZABLE,
                        severidad=SEVERIDAD_ERROR,
                        mensaje=(
                            f"El atributo '{aid}' depende mediante 'depends_on' de '{dep_aid}', "
                            f"pero '{dep_aid}' no tiene 'question' ni es derivado por ninguna regla."
                        ),
                        atributos=[aid, dep_aid],
                        detalles={"motivo": "depends_on_atributo_sin_fuente"},
                    )
                )

            errs_dep = self._validar_condicion_contra_atributo(
                dep, dep_attr, contexto=f"Dependencia 'depends_on' del atributo '{aid}'"
            )
            for err in errs_dep:
                if aid not in err.atributos:
                    err.atributos = [aid, *err.atributos]
                err.detalles["origen"] = "depends_on"
            hallazgos.extend(errs_dep)

        return hallazgos

    # ------------------------------------------------------------------
    # 5. Detección de ciclos en reglas y en depends_on
    # ------------------------------------------------------------------

    def detectar_ciclos(self) -> list[Hallazgo]:
        """Detecta ciclos directos e indirectos en reglas y en ``depends_on``."""
        hallazgos: list[Hallazgo] = []
        hallazgos.extend(self._detectar_ciclos_reglas())
        hallazgos.extend(self._detectar_ciclos_depends_on())
        return hallazgos

    def _detectar_ciclos_reglas(self) -> list[Hallazgo]:
        """Construye el grafo bipartito (atributo -> regla -> atributo) y detecta ciclos elementales."""
        reglas = self._obtener_reglas_lista()
        ady: dict[tuple[str, str], list[tuple[str, str]]] = {}

        for idx, regla in enumerate(reglas):
            rid = str(regla.get("id", f"rules[{idx}]"))
            conds = regla.get("conditions")
            conc = regla.get("conclusion")
            if not isinstance(conds, list) or not isinstance(conc, dict):
                continue
            conc_aid = conc.get("attribute_id")
            if not isinstance(conc_aid, str) or not conc_aid.strip():
                continue

            nodo_regla = ("rule", rid)
            nodo_conc = ("attr", conc_aid)
            ady.setdefault(nodo_regla, [])
            if nodo_conc not in ady[nodo_regla]:
                ady[nodo_regla].append(nodo_conc)
            ady.setdefault(nodo_conc, [])

            for cond in conds:
                if not isinstance(cond, dict):
                    continue
                c_aid = cond.get("attribute_id")
                if not isinstance(c_aid, str) or not c_aid.strip():
                    continue
                nodo_cond = ("attr", c_aid)
                ady.setdefault(nodo_cond, [])
                if nodo_regla not in ady[nodo_cond]:
                    ady[nodo_cond].append(nodo_regla)

        # Algoritmo de Tarjan para Componentes Fuertemente Conexas (SCC)
        indice_actual = 0
        indices: dict[tuple[str, str], int] = {}
        lowlink: dict[tuple[str, str], int] = {}
        pila: list[tuple[str, str]] = []
        en_pila: set[tuple[str, str]] = set()
        sccs: list[set[tuple[str, str]]] = []

        def tarjan(nodo: tuple[str, str]) -> None:
            nonlocal indice_actual
            indices[nodo] = indice_actual
            lowlink[nodo] = indice_actual
            indice_actual += 1
            pila.append(nodo)
            en_pila.add(nodo)

            for vecino in ady.get(nodo, []):
                if vecino not in indices:
                    tarjan(vecino)
                    lowlink[nodo] = min(lowlink[nodo], lowlink[vecino])
                elif vecino in en_pila:
                    lowlink[nodo] = min(lowlink[nodo], indices[vecino])

            if lowlink[nodo] == indices[nodo]:
                comp: set[tuple[str, str]] = set()
                while True:
                    w = pila.pop()
                    en_pila.remove(w)
                    comp.add(w)
                    if w == nodo:
                        break
                if len(comp) >= 2:
                    sccs.append(comp)

        for nodo in sorted(ady.keys()):
            if nodo not in indices:
                tarjan(nodo)

        # Extraer ciclos elementales únicos por SCC empezando por el atributo mínimo
        hallazgos: list[Hallazgo] = []
        max_ciclos = 50
        ciclos_encontrados = 0

        for comp in sccs:
            atributos_scc = sorted(n[1] for n in comp if n[0] == "attr")
            for inicio_attr in atributos_scc:
                if ciclos_encontrados >= max_ciclos:
                    break
                nodo_inicio = ("attr", inicio_attr)
                camino: list[tuple[str, str]] = [nodo_inicio]
                visitados: set[tuple[str, str]] = {nodo_inicio}

                def dfs(actual: tuple[str, str]) -> None:
                    nonlocal ciclos_encontrados
                    if ciclos_encontrados >= max_ciclos:
                        return
                    for sig in sorted(ady.get(actual, [])):
                        if sig not in comp:
                            continue
                        if sig == nodo_inicio:
                            ciclo_completo = [*camino, nodo_inicio]
                            reglas_ciclo = [n[1] for n in ciclo_completo if n[0] == "rule"]
                            attrs_ciclo = [n[1] for n in camino if n[0] == "attr"]
                            cadena = " -> ".join(
                                f"[{n[1]}]" if n[0] == "rule" else n[1]
                                for n in ciclo_completo
                            )
                            tipo_ciclo = "directo" if len(reglas_ciclo) == 1 else "indirecto"
                            hallazgos.append(
                                Hallazgo(
                                    categoria=CAT_CICLO,
                                    severidad=SEVERIDAD_ERROR,
                                    mensaje=(
                                        f"Ciclo {tipo_ciclo} detectado en reglas: {cadena}."
                                    ),
                                    reglas=reglas_ciclo,
                                    atributos=attrs_ciclo,
                                    detalles={
                                        "origen": "reglas",
                                        "tipo": tipo_ciclo,
                                        "cadena": cadena,
                                        "longitud_reglas": len(reglas_ciclo),
                                    },
                                )
                            )
                            ciclos_encontrados += 1
                            continue

                        if sig in visitados:
                            continue
                        if sig[0] == "attr" and sig[1] < inicio_attr:
                            continue

                        visitados.add(sig)
                        camino.append(sig)
                        dfs(sig)
                        camino.pop()
                        visitados.remove(sig)

                dfs(nodo_inicio)

        return hallazgos

    def _detectar_ciclos_depends_on(self) -> list[Hallazgo]:
        """Detecta ciclos directos e indirectos en las dependencias ``depends_on``."""
        atributos = self._obtener_atributos_mapa()
        deps: dict[str, str] = {}
        hallazgos: list[Hallazgo] = []

        for aid, attr in atributos.items():
            dep = attr.get("depends_on")
            if isinstance(dep, dict) and isinstance(dep.get("attribute_id"), str):
                destino = dep["attribute_id"]
                if destino == aid:
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_CICLO,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=(
                                f"Ciclo directo en 'depends_on': el atributo '{aid}' "
                                f"depende de sí mismo ({aid} -> {aid})."
                            ),
                            atributos=[aid],
                            detalles={
                                "origen": "depends_on",
                                "tipo": "directo",
                                "cadena": f"{aid} -> {aid}",
                            },
                        )
                    )
                elif destino in atributos:
                    deps[aid] = destino

        revisados: set[str] = set()
        for inicio in sorted(deps.keys()):
            if inicio in revisados:
                continue
            camino: list[str] = []
            posiciones: dict[str, int] = {}
            actual = inicio
            while actual in deps and actual not in revisados:
                if actual in posiciones:
                    ciclo = camino[posiciones[actual]:] + [actual]
                    cadena = " -> ".join(ciclo)
                    hallazgos.append(
                        Hallazgo(
                            categoria=CAT_CICLO,
                            severidad=SEVERIDAD_ERROR,
                            mensaje=f"Ciclo en 'depends_on' de atributos: {cadena}.",
                            atributos=ciclo[:-1],
                            detalles={
                                "origen": "depends_on",
                                "tipo": "indirecto",
                                "cadena": cadena,
                            },
                        )
                    )
                    break
                posiciones[actual] = len(camino)
                camino.append(actual)
                actual = deps[actual]
            revisados.update(camino)

        return hallazgos

    # ------------------------------------------------------------------
    # 6. Generador de Tablas de Decisión
    # ------------------------------------------------------------------

    def generar_tabla_decision(
        self, hallazgos: list[Hallazgo] | None = None
    ) -> dict[str, Any]:
        """Construye la Tabla de Decisión cruzando atributos, reglas, prioridades y conclusiones."""
        reglas = self._obtener_reglas_lista()

        # Recolectar atributos de condición en orden de aparición
        attrs_cond: list[str] = []
        attrs_conc: list[str] = []
        for regla in reglas:
            conds = regla.get("conditions")
            if isinstance(conds, list):
                for cond in conds:
                    if isinstance(cond, dict):
                        aid = cond.get("attribute_id")
                        if isinstance(aid, str) and aid.strip() and aid not in attrs_cond:
                            attrs_cond.append(aid)
            conc = regla.get("conclusion")
            if isinstance(conc, dict):
                c_aid = conc.get("attribute_id")
                if isinstance(c_aid, str) and c_aid.strip() and c_aid not in attrs_conc:
                    attrs_conc.append(c_aid)

        # Indexar alertas por regla a partir de los hallazgos
        if hallazgos is None:
            hallazgos = (
                self.detectar_contradicciones()
                + self.detectar_redundancias()
                + self.detectar_condiciones_inalcanzables()
                + self.detectar_ciclos()
            )

        alertas_por_regla: dict[str, list[str]] = {}
        relacionadas_por_regla: dict[str, list[str]] = {}
        etiqueta_cat = {
            CAT_CONTRADICCION: "CONFLICTO",
            CAT_REDUNDANCIA: "REDUNDANTE",
            CAT_INALCANZABLE: "INALCANZABLE",
            CAT_CICLO: "CICLO",
            CAT_ESQUEMA: "ESQUEMA",
        }

        for h in hallazgos:
            tag_base = etiqueta_cat.get(h.categoria, h.categoria.upper())
            for rid in h.reglas:
                tag = f"{tag_base}({h.severidad})"
                lista = alertas_por_regla.setdefault(rid, [])
                if tag not in lista:
                    lista.append(tag)
                rels = relacionadas_por_regla.setdefault(rid, [])
                for otra in h.reglas:
                    if otra != rid and otra not in rels:
                        rels.append(otra)

        filas: list[dict[str, Any]] = []
        for idx, regla in enumerate(reglas):
            rid = str(regla.get("id", f"rules[{idx}]"))
            desc = str(regla.get("description", ""))
            prio = regla.get("priority", 0)

            celdas_cond: dict[str, str] = {aid: "—" for aid in attrs_cond}
            conds = regla.get("conditions")
            if isinstance(conds, list):
                por_attr: dict[str, list[str]] = {}
                for cond in conds:
                    if not isinstance(cond, dict):
                        continue
                    aid = cond.get("attribute_id")
                    op = cond.get("operator")
                    if isinstance(aid, str) and aid in celdas_cond:
                        val_txt = _formatear_valor(cond.get("value")) if "value" in cond else "?"
                        por_attr.setdefault(aid, []).append(f"{op} {val_txt}")
                for aid, partes in por_attr.items():
                    celdas_cond[aid] = " Y ".join(partes)

            conc = regla.get("conclusion")
            if isinstance(conc, dict) and isinstance(conc.get("attribute_id"), str):
                c_aid = conc["attribute_id"]
                c_val = conc.get("value")
                conc_txt = f"{c_aid} = {_formatear_valor(c_val)}"
            else:
                c_aid = ""
                c_val = None
                conc_txt = "(incompleta)"

            alertas = alertas_por_regla.get(rid, [])
            rels = relacionadas_por_regla.get(rid, [])
            if alertas:
                estado_txt = ", ".join(alertas)
                if rels:
                    estado_txt += f" [con {', '.join(rels)}]"
            else:
                estado_txt = "OK"

            filas.append(
                {
                    "regla_id": rid,
                    "descripcion": desc,
                    "prioridad": prio,
                    "condiciones": celdas_cond,
                    "conclusion_atributo": c_aid,
                    "conclusion_valor": c_val,
                    "conclusion": conc_txt,
                    "estado": estado_txt,
                    "alertas": alertas,
                    "reglas_relacionadas": rels,
                }
            )

        return {
            "atributos_condicion": attrs_cond,
            "atributos_conclusion": attrs_conc,
            "filas": filas,
        }

    def exportar_tabla_decision_markdown(
        self, tabla: dict[str, Any] | None = None
    ) -> str:
        """Exporta la tabla de decisión en formato Markdown."""
        t = tabla if tabla is not None else self.generar_tabla_decision()
        return formatear_tabla_decision_markdown(t)

    def exportar_tabla_decision_consola(
        self, tabla: dict[str, Any] | None = None
    ) -> str:
        """Exporta la tabla de decisión en formato de tabla ASCII para consola."""
        t = tabla if tabla is not None else self.generar_tabla_decision()
        return formatear_tabla_decision_consola(t)

    # ------------------------------------------------------------------
    # 7. Auditoría integral y exportación de reportes
    # ------------------------------------------------------------------

    def auditar(
        self, fuente: dict[str, Any] | str | Path | None = None
    ) -> ReporteAuditoria:
        """Ejecuta la auditoría completa y devuelve un :class:`ReporteAuditoria`."""
        if fuente is not None:
            self._cargar_fuente(fuente)

        hallazgos: list[Hallazgo] = []
        hallazgos.extend(self.validar_esquema())

        if self._datos is not None:
            contradicciones, redundancias = self._analizar_pares_reglas()
            hallazgos.extend(contradicciones)
            hallazgos.extend(redundancias)
            hallazgos.extend(self.detectar_condiciones_inalcanzables())
            hallazgos.extend(self.detectar_ciclos())

        tabla = self.generar_tabla_decision(hallazgos=hallazgos)

        conteo_sev = {
            SEVERIDAD_ERROR: 0,
            SEVERIDAD_WARNING: 0,
            SEVERIDAD_INFO: 0,
        }
        conteo_cat: dict[str, int] = {}
        for h in hallazgos:
            conteo_sev[h.severidad] = conteo_sev.get(h.severidad, 0) + 1
            conteo_cat[h.categoria] = conteo_cat.get(h.categoria, 0) + 1

        es_valida = conteo_sev[SEVERIDAD_ERROR] == 0
        if not es_valida:
            estado = "INVALIDA"
        elif conteo_sev[SEVERIDAD_WARNING] > 0:
            estado = "CON_ADVERTENCIAS"
        else:
            estado = "VALIDA"

        meta = (
            copy.deepcopy(self._datos["meta"])
            if isinstance(self._datos, dict) and isinstance(self._datos.get("meta"), dict)
            else {}
        )
        total_atributos = len(self._obtener_atributos_lista())
        total_reglas = len(self._obtener_reglas_lista())

        resumen = {
            "es_valida": es_valida,
            "estado": estado,
            "total_atributos": total_atributos,
            "total_reglas": total_reglas,
            "total_hallazgos": len(hallazgos),
            "conteo_severidad": conteo_sev,
            "conteo_categoria": conteo_cat,
        }

        reporte = ReporteAuditoria(
            es_valida=es_valida,
            estado=estado,
            meta=meta,
            resumen=resumen,
            hallazgos=hallazgos,
            tabla_decision=tabla,
        )
        self._ultimo_reporte = reporte
        return reporte

    def generar_reporte(
        self, fuente: dict[str, Any] | str | Path | None = None
    ) -> dict[str, Any]:
        """Ejecuta la auditoría y devuelve el reporte como ``dict`` serializable a JSON."""
        return self.auditar(fuente).to_dict()

    def exportar_json(
        self,
        ruta: str | Path | None = None,
        reporte: ReporteAuditoria | None = None,
        *,
        indent: int = 2,
    ) -> str:
        """Serializa el reporte a JSON y, si se indica ``ruta``, lo guarda en disco."""
        rep = reporte or self._ultimo_reporte or self.auditar()
        contenido = rep.to_json(indent=indent)
        if ruta is not None:
            destino = Path(ruta)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(contenido, encoding="utf-8")
        return contenido

    def exportar_markdown(
        self,
        ruta: str | Path | None = None,
        reporte: ReporteAuditoria | None = None,
    ) -> str:
        """Serializa el reporte a Markdown y, si se indica ``ruta``, lo guarda en disco."""
        rep = reporte or self._ultimo_reporte or self.auditar()
        contenido = rep.to_markdown()
        if ruta is not None:
            destino = Path(ruta)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(contenido, encoding="utf-8")
        return contenido
