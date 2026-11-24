"""Modelos de datos de la API del Grupo 12.

La primera parte reproduce los tres contratos congelados en contracts/
(conocimiento_dominio, memoria_trabajo y dictamen_salida). Los nombres de
campo se dejan en ingles porque asi los fija el contrato; no se cambian sin
acuerdo de los 12 coordinadores.

La segunda parte son los cuerpos de peticion y respuesta propios de la API,
que no forman parte de los contratos comunes.

Los modelos de contrato aceptan campos adicionales (extra="allow"), igual que
los esquemas. Las comprobaciones semanticas (opciones de un categorico, valor
de "in", ids repetidos, rangos) las hace SchemaManager (G4) en servicio.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Contrato(BaseModel):
    model_config = ConfigDict(extra="allow")


# --- conocimiento_dominio.json ---

class Meta(_Contrato):
    project_title: str
    version: str
    author_group: str


Operador = Literal["==", "!=", ">", "<", ">=", "<=", "in"]
TipoAtributo = Literal["numeric", "categorical", "boolean", "text"]


class Condicion(_Contrato):
    attribute_id: str
    operator: Operador
    value: Any


class Atributo(_Contrato):
    id: str
    name: str
    type: TipoAtributo
    question: str | None = None
    range: list[float] | None = Field(default=None, min_length=2, max_length=2)
    options: list[str] = Field(default_factory=list)
    depends_on: Condicion | None = Field(
        default=None, description="Pregunta condicional: solo se hace si se cumple esta condición.")
    help_text: str | None = None


class Conclusion(_Contrato):
    attribute_id: str
    value: Any


class Regla(_Contrato):
    id: str
    description: str
    priority: int
    conditions: list[Condicion] = Field(min_length=1)
    conclusion: Conclusion
    explanation_template: str


class ConocimientoDominio(_Contrato):
    meta: Meta
    attributes: list[Atributo] = Field(min_length=1)
    rules: list[Regla] = Field(min_length=1)


# --- memoria_trabajo.json ---

class HechoDerivado(_Contrato):
    value: Any
    derived_by_rule: str
    certainty_factor: float | None = Field(default=None, ge=-1.0, le=1.0)
    timestamp: str | None = None


class PasoTraza(_Contrato):
    step: int
    rule_fired: str
    added_fact: str


class MemoriaTrabajo(_Contrato):
    session_id: str
    facts: dict[str, Any] = Field(default_factory=dict)
    derived_facts: dict[str, HechoDerivado] = Field(default_factory=dict)
    execution_trace: list[PasoTraza] = Field(default_factory=list)


# --- dictamen_salida.json ---

class DictamenSalida(_Contrato):
    session_id: str
    final_outcome: str
    certainty_score: float | None = None
    explanation_how: list[str]
    explanation_why: str


# --- Peticiones y respuestas propias de la API ---

class Motor(str, Enum):
    adelante = "adelante"
    atras = "atras"


class Salud(BaseModel):
    estado: str
    version: str
    modulos: dict[str, str] = Field(
        description="Por cada grupo integrado: 'real' si se usa su modulo o 'simulado' si se usa el stub.")


class BaseCargada(BaseModel):
    kb_id: str
    project_title: str
    version: str
    atributos: int
    reglas: int


class Pregunta(BaseModel):
    attribute_id: str
    question: str | None = None
    type: str
    options: list[Any] = Field(default_factory=list)
    range: list[float] | None = None


FactorCerteza = Annotated[float, Field(ge=-1.0, le=1.0)]


class NuevaConsulta(BaseModel):
    kb_id: str
    motor: Motor = Motor.adelante
    hechos: dict[str, Any] = Field(default_factory=dict)
    fc_reglas: dict[str, FactorCerteza] = Field(
        default_factory=dict,
        description="Factor de certeza de cada regla, {rule_id: FC}. Las que faltan valen 1.0 (G7).")
    fc_hechos: dict[str, FactorCerteza] = Field(
        default_factory=dict,
        description="Certeza del usuario en cada dato, {attribute_id: FC}. Los que faltan valen 1.0.")


class ConsultaCreada(BaseModel):
    session_id: str
    kb_id: str
    motor: Motor


class RestaurarSesion(BaseModel):
    kb_id: str = Field(description="Base con la que se validan los hechos guardados.")
    motor: Motor = Motor.adelante


class SesionGuardada(BaseModel):
    session_id: str
    ruta: str


class HechosEntrada(BaseModel):
    hechos: dict[str, Any] = Field(min_length=1)
    fc_hechos: dict[str, FactorCerteza] = Field(
        default_factory=dict, description="Certeza del usuario en estos datos (opcional).")


class SiguientePregunta(BaseModel):
    session_id: str
    completa: bool = Field(description="True cuando el motor ya no necesita mas datos.")
    pregunta: Pregunta | None = None
    explanation_why: str | None = None


class ExplicacionHow(BaseModel):
    session_id: str
    attribute_id: str
    explanation_how: list[str]


class ExplicacionWhy(BaseModel):
    session_id: str
    attribute_id: str
    rule_id: str
    explanation_why: str


class Traza(BaseModel):
    session_id: str
    pasos: list[str]
