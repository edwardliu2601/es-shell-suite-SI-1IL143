"""Grupo 12 - API REST del ES-Shell Suite (FastAPI).

Expone la carga de conocimiento, la consulta y la explicacion para que un
integrador o una aplicacion externa use el shell experto sin pasar por la
interfaz de G10. Esta capa solo traduce HTTP a llamadas de ServicioESB; la
logica vive en servicio.py.

Ejecucion, desde la raiz del repositorio:

    uvicorn grupo_12_api.esb_api:app --reload

La documentacion interactiva queda en /docs (Swagger) y /redoc.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from .modelos import (BaseCargada, ConocimientoDominio, ConsultaCreada, DictamenSalida,
                      ExplicacionHow, ExplicacionWhy, HechosEntrada, MemoriaTrabajo,
                      NuevaConsulta, Pregunta, Salud, SiguientePregunta, Traza)
from .servicio import (ContratoInvalido, EstadoInvalido, ModuloNoDisponible, NoEncontrado,
                       ServicioESB)

VERSION = "0.3.0"

app = FastAPI(
    title="ES-Shell Suite · API REST",
    version=VERSION,
    description=(
        "Servicio del Grupo 12. Permite cargar una base de conocimiento "
        "(`conocimiento_dominio.json`), ejecutar una consulta sobre su memoria de "
        "trabajo (`memoria_trabajo.json`) y obtener el dictamen con sus "
        "explicaciones HOW/WHY (`dictamen_salida.json`).\n\n"
        "Valida con SchemaManager (G4), infiere con ForwardEngine (G5), calcula la "
        "certeza con UncertaintyEngine (G7), explica con XAIExplainer (G8) y audita "
        "bases con KBAuditor (G3). `GET /salud` indica qué módulos están conectados.\n\n"
        "Bases precargadas: `kb_academico` (base de la demo, de G4) y `kb_ejemplo` "
        "(sección 4.2 de la guía)."
    ),
    openapi_tags=[
        {"name": "Servicio", "description": "Estado del servicio."},
        {"name": "Conocimiento", "description": "Carga y consulta de bases de conocimiento."},
        {"name": "Consultas", "description": "Sesiones, memoria de trabajo, inferencia y dictamen."},
        {"name": "Explicación", "description": "Respuestas HOW, WHY y traza de ejecución."},
    ],
)

_servicio = ServicioESB()


def obtener_servicio() -> ServicioESB:
    """Dependencia que entrega el servicio; las pruebas la sustituyen."""
    return _servicio


@app.exception_handler(NoEncontrado)
async def _no_encontrado(_: Request, exc: NoEncontrado) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ContratoInvalido)
async def _contrato_invalido(_: Request, exc: ContratoInvalido) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc), "errores": exc.errores})


@app.exception_handler(ModuloNoDisponible)
async def _modulo_no_disponible(_: Request, exc: ModuloNoDisponible) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(EstadoInvalido)
async def _estado_invalido(_: Request, exc: EstadoInvalido) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


Servicio = Depends(obtener_servicio)
ERRORES_SESION = {404: {"description": "La sesión no existe."}}
ERROR_CONTRATO = {422: {"description": "No cumple el contrato; `errores` trae el detalle de G4."}}


# --- Servicio ---

@app.get("/salud", response_model=Salud, tags=["Servicio"], summary="Estado del servicio")
def salud(servicio: ServicioESB = Servicio) -> dict:
    """Indica si el servicio responde y qué módulos de otros grupos están integrados."""
    return {"estado": "ok", "version": VERSION, "modulos": servicio.estado_modulos()}


# --- Conocimiento ---

@app.post("/conocimiento", response_model=BaseCargada, status_code=201, tags=["Conocimiento"],
          summary="Cargar una base de conocimiento", responses=ERROR_CONTRATO)
def cargar_conocimiento(base: ConocimientoDominio, servicio: ServicioESB = Servicio) -> dict:
    """Recibe un `conocimiento_dominio.json`, lo valida contra el contrato (G4) y devuelve su `kb_id`."""
    kb_id, kb = servicio.cargar_conocimiento(base.model_dump(exclude_unset=True))
    return {"kb_id": kb_id, "project_title": kb["meta"]["project_title"],
            "version": kb["meta"]["version"], "atributos": len(kb["attributes"]),
            "reglas": len(kb["rules"])}


@app.get("/conocimiento/{kb_id}", response_model=ConocimientoDominio,
         response_model_exclude_unset=True, tags=["Conocimiento"],
         summary="Obtener una base de conocimiento",
         responses={404: {"description": "La base no existe."}})
def obtener_conocimiento(kb_id: str, servicio: ServicioESB = Servicio) -> dict:
    return servicio.obtener_conocimiento(kb_id)


@app.get("/conocimiento/{kb_id}/auditoria", tags=["Conocimiento"],
         summary="Auditar una base de conocimiento",
         responses={404: {"description": "La base no existe."},
                    503: {"description": "El auditor (G3) todavía no está en el repositorio."}})
def auditar_conocimiento(kb_id: str, formato: Literal["json", "md"] = "json",
                         servicio: ServicioESB = Servicio) -> Any:
    """Reporte de G3: contradicciones, redundancias, condiciones inalcanzables, ciclos y
    tabla de decisión. `md` devuelve el mismo reporte en Markdown."""
    reporte = servicio.auditar_conocimiento(kb_id)
    if formato == "md":
        return PlainTextResponse(reporte.to_markdown(), media_type="text/markdown; charset=utf-8")
    return reporte.to_dict()


@app.get("/conocimiento/{kb_id}/preguntas", response_model=list[Pregunta], tags=["Conocimiento"],
         summary="Listar las preguntas de una base",
         responses={404: {"description": "La base no existe."}})
def listar_preguntas(kb_id: str, servicio: ServicioESB = Servicio) -> list[dict]:
    """Atributos de la base con su pregunta, tipo, opciones y rango."""
    return servicio.listar_preguntas(kb_id)


# --- Consultas ---

@app.post("/consultas", response_model=ConsultaCreada, status_code=201, tags=["Consultas"],
          summary="Iniciar una consulta",
          responses={404: {"description": "La base no existe."}, **ERROR_CONTRATO})
def iniciar_consulta(datos: NuevaConsulta, servicio: ServicioESB = Servicio) -> dict:
    """Crea una sesión sobre `kb_id` con el motor indicado y los hechos iniciales.

    Los hechos se validan contra la base (tipo, opciones y rango). `fc_reglas` y
    `fc_hechos` son opcionales y los usa G7 para la certeza del resultado. Mientras
    G6 no publique su motor, `atras` usa el encadenamiento hacia adelante.
    """
    return servicio.iniciar_consulta(datos.kb_id, datos.motor, datos.hechos,
                                     datos.fc_reglas, datos.fc_hechos)


@app.post("/consultas/{session_id}/hechos", response_model=MemoriaTrabajo,
          response_model_exclude_unset=True, tags=["Consultas"],
          summary="Registrar hechos", responses={**ERRORES_SESION, **ERROR_CONTRATO})
def registrar_hechos(session_id: str, datos: HechosEntrada,
                     servicio: ServicioESB = Servicio) -> dict:
    """Agrega a la memoria de trabajo los datos que ingresó el usuario.

    Se descartan las conclusiones anteriores; se recalculan al volver a inferir.
    """
    return servicio.registrar_hechos(session_id, datos.hechos, datos.fc_hechos)


@app.get("/consultas/{session_id}/siguiente-pregunta", response_model=SiguientePregunta,
         tags=["Consultas"], summary="Siguiente dato que pide el motor", responses=ERRORES_SESION)
def siguiente_pregunta(session_id: str, servicio: ServicioESB = Servicio) -> dict:
    """Próximo atributo que necesita el motor, con la explicación WHY de por qué se pide."""
    return servicio.siguiente_pregunta(session_id)


@app.post("/consultas/{session_id}/inferir", response_model=MemoriaTrabajo,
          response_model_exclude_unset=True, tags=["Consultas"],
          summary="Ejecutar la inferencia",
          responses={**ERRORES_SESION, 409: {"description": "La sesión no tiene hechos."}})
def inferir(session_id: str, servicio: ServicioESB = Servicio) -> dict:
    """Ejecuta el motor (G5), calcula la certeza (G7) y devuelve la memoria actualizada.

    Incluye `halted_reason`: `quiescence` cuando no quedan reglas por activar.
    Si ninguna regla se activó, `derived_facts` queda vacío.
    """
    memoria, motivo = servicio.inferir(session_id)
    return {**memoria, "halted_reason": motivo}


@app.get("/consultas/{session_id}/memoria", response_model=MemoriaTrabajo,
         response_model_exclude_unset=True, tags=["Consultas"],
         summary="Obtener la memoria de trabajo", responses=ERRORES_SESION)
def obtener_memoria(session_id: str, servicio: ServicioESB = Servicio) -> dict:
    return servicio.obtener_memoria(session_id)


@app.get("/consultas/{session_id}/dictamen", response_model=DictamenSalida,
         response_model_exclude_unset=True, tags=["Consultas"],
         summary="Obtener el dictamen",
         responses={**ERRORES_SESION, 409: {"description": "Ninguna regla se ha activado."}})
def obtener_dictamen(session_id: str, servicio: ServicioESB = Servicio) -> dict:
    """Resultado final, certeza y explicaciones HOW/WHY (`dictamen_salida.json`)."""
    return servicio.obtener_dictamen(session_id)


@app.get("/consultas/{session_id}/reporte", tags=["Consultas"], summary="Descargar el reporte",
         response_class=PlainTextResponse,
         responses={**ERRORES_SESION, 409: {"description": "Todavía no se ha inferido."}})
def generar_reporte(session_id: str, formato: Literal["md", "html"] = "md",
                    servicio: ServicioESB = Servicio):
    """Reporte del dictamen en Markdown (`md`) o HTML (`html`)."""
    contenido = servicio.generar_reporte(session_id, formato)
    if formato == "html":
        return HTMLResponse(contenido)
    return PlainTextResponse(contenido, media_type="text/markdown; charset=utf-8")


# --- Explicacion ---

@app.get("/consultas/{session_id}/explicacion/how", response_model=ExplicacionHow,
         tags=["Explicación"], summary="¿Cómo se llegó a este valor?",
         responses={404: {"description": "La sesión no existe o el atributo no tiene valor."}})
def explicar_how(session_id: str,
                 atributo: str = Query("dictamen", description="Atributo a explicar."),
                 servicio: ServicioESB = Servicio) -> dict:
    return {"session_id": session_id, "attribute_id": atributo,
            "explanation_how": servicio.explicar_how(session_id, atributo)}


@app.get("/consultas/{session_id}/explicacion/why", response_model=ExplicacionWhy,
         tags=["Explicación"], summary="¿Por qué se solicita este dato?",
         responses={404: {"description": "La sesión, el atributo o la regla no existe."}})
def explicar_why(session_id: str,
                 atributo: str = Query(..., description="Atributo que se le pide al usuario."),
                 regla: str | None = Query(None, description="Regla que el motor está evaluando."),
                 servicio: ServicioESB = Servicio) -> dict:
    rule_id, texto = servicio.explicar_why(session_id, atributo, regla)
    return {"session_id": session_id, "attribute_id": atributo, "rule_id": rule_id,
            "explanation_why": texto}


@app.get("/consultas/{session_id}/traza", response_model=Traza, tags=["Explicación"],
         summary="Traza de reglas aplicadas", responses=ERRORES_SESION)
def obtener_traza(session_id: str, servicio: ServicioESB = Servicio) -> dict:
    return {"session_id": session_id, "pasos": servicio.obtener_traza(session_id)}
