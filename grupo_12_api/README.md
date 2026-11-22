# Grupo 12 · API REST (FastAPI)

Archivo `esb_api.py`, servicio FastAPI. Coordinador: Samuel Díaz (@Shazam15).

Este módulo expone el shell experto por HTTP para el perfil de integrador o desarrollador externo. Cubre tres operaciones: cargar una base de conocimiento, ejecutar una consulta y pedir el dictamen con sus explicaciones HOW/WHY. La API no razona por su cuenta. Recibe la petición, llama al módulo del grupo que corresponde y devuelve el resultado con la forma de los contratos de `contracts/`.

## Estado

Integrado con los módulos que ya están en `develop`. `GET /salud` muestra en cada momento cuáles se usan de verdad (`real`) y cuáles se reemplazan por un respaldo propio (`simulado`).

| Grupo | Módulo | Estado | Uso en la API |
|---|---|---|---|
| G4 | `SchemaManager` | real | Valida la base (`POST /conocimiento`) y los hechos (`POST /consultas`, `POST /hechos`) con los esquemas de `contracts/` |
| G5 | `ForwardEngine` | real | `POST /inferir` |
| G8 | `XAIExplainer` | real | HOW, WHY, traza y las explicaciones del dictamen |
| G9 | `ReportGenerator` | simulado | Todavía es un stub; la API genera el reporte por su cuenta |
| G6 | `BackwardEngine` | simulado | Sin código; una sesión con `motor: "atras"` usa el motor hacia adelante |
| G7 | `UncertaintyEngine` | simulado | Sin código; `certainty_score` toma el `certainty_factor` del hecho o 1.0 |
| G11 | `ESBConverter` | simulado | Sin código; bases y sesiones se guardan en memoria |

Si un módulo real deja de importarse, la API sigue funcionando con su respaldo, y `/salud` lo indica.

## Estructura

| Archivo | Contenido |
|---|---|
| `esb_api.py` | Aplicación FastAPI y rutas. Solo traduce HTTP a llamadas del servicio. |
| `servicio.py` | `ServicioESB`, la lógica de la consulta (sesiones, siguiente pregunta, dictamen). No depende de FastAPI. |
| `adaptadores.py` | `Integraciones`, el único lugar que importa los módulos de otros grupos, con su respaldo. |
| `modelos.py` | Modelos Pydantic de los tres contratos y de los cuerpos propios de la API. |
| `datos_ejemplo/` | Los tres JSON de la sección 4.2 de la guía (también los usa G4 en sus pruebas de integración). |
| `tests/test_api.py` | Pruebas por endpoint con los módulos reales. |
| `tests/test_e2e.py` | Escenario obligatorio de la sección 6 recorrido por HTTP. |

## Instalación y ejecución

Desde la raíz del repositorio, con Python 3.11 o superior:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r grupo_12_api/requirements.txt
uvicorn grupo_12_api.esb_api:app --reload
```

La documentación interactiva queda en http://127.0.0.1:8000/docs (Swagger) y http://127.0.0.1:8000/redoc. Al iniciar se precargan dos bases:

- `kb_academico`: la base de la demo (calificaciones y repetición de asignaturas), leída de `grupo_04_schema/ejemplos/conocimiento_dominio.json`.
- `kb_ejemplo`: la base de la sección 4.2 de la guía.

## Endpoints

| Método y ruta | Qué hace | Respuesta |
|---|---|---|
| `GET /salud` | Estado del servicio y de los módulos | `Salud` |
| `POST /conocimiento` | Carga y valida un `conocimiento_dominio.json` | `kb_id` y resumen |
| `GET /conocimiento/{kb_id}` | Devuelve la base cargada | `conocimiento_dominio.json` |
| `GET /conocimiento/{kb_id}/preguntas` | Atributos con su pregunta, tipo, opciones y rango | lista de `Pregunta` |
| `POST /consultas` | Inicia una sesión (`kb_id`, `motor`: `adelante` o `atras`, `hechos`) | `session_id` |
| `POST /consultas/{session_id}/hechos` | Registra datos del usuario y descarta las conclusiones anteriores | `memoria_trabajo.json` |
| `GET /consultas/{session_id}/siguiente-pregunta` | Próximo dato que conviene pedir, con su WHY | `SiguientePregunta` |
| `POST /consultas/{session_id}/inferir` | Ejecuta el motor | `memoria_trabajo.json` + `halted_reason` |
| `GET /consultas/{session_id}/memoria` | Memoria de trabajo actual | `memoria_trabajo.json` |
| `GET /consultas/{session_id}/dictamen` | Resultado final con HOW/WHY | `dictamen_salida.json` |
| `GET /consultas/{session_id}/reporte?formato=md\|html` | Reporte descargable | Markdown o HTML |
| `GET /consultas/{session_id}/explicacion/how?atributo=` | ¿Cómo se llegó a ese valor? | `explanation_how` |
| `GET /consultas/{session_id}/explicacion/why?atributo=&regla=` | ¿Por qué se pide ese dato? | `explanation_why` |
| `GET /consultas/{session_id}/traza` | Reglas aplicadas en orden | lista de pasos |

`siguiente-pregunta` recorre las reglas de mayor a menor prioridad y descarta las que ya no pueden cumplirse con los hechos conocidos. Devuelve el primer atributo que falta y que el usuario puede responder. Respeta `depends_on`, por lo que no ofrece una pregunta condicional mientras no se cumpla su condición. Por ejemplo, con `tipo_consulta = "Repeticion"` pide `nota_obtenida` y no `puntaje_final`.

El dictamen toma el hecho derivado `dictamen` o, si la base usa otro nombre, el último hecho derivado. Su `explanation_why` explica el último dato que se le preguntó al usuario dentro de la regla que produjo el resultado.

### Errores

| Código | Cuándo | Cuerpo |
|---|---|---|
| `404` | La base, la sesión, el atributo o la regla no existe, o el atributo no tiene valor | `{"detail": "..."}` |
| `409` | Se infiere sin hechos, o se pide el dictamen cuando ninguna regla se activó | `{"detail": "..."}` |
| `422` | La base o los hechos no cumplen el contrato | `{"detail": "...", "errores": [...]}` con los mensajes de G4 |

Ejemplo de un hecho fuera de rango:

```json
{"detail": "Los hechos no son válidos para la base de conocimiento.",
 "errores": ["$.facts.puntaje_final: El valor 150 está fuera del rango [0, 100]."]}
```

### Ejemplo con `curl` (caso de la demo)

```bash
curl -X POST localhost:8000/consultas -H 'Content-Type: application/json' \
     -d '{"kb_id": "kb_academico", "hechos": {"tipo_consulta": "Calificacion"}}'
# {"session_id": "sess_2026_00001", ...}
curl localhost:8000/consultas/sess_2026_00001/siguiente-pregunta
# pide "puntaje_final"
curl -X POST localhost:8000/consultas/sess_2026_00001/hechos -H 'Content-Type: application/json' \
     -d '{"hechos": {"puntaje_final": 95}}'
curl -X POST localhost:8000/consultas/sess_2026_00001/inferir
curl localhost:8000/consultas/sess_2026_00001/dictamen
# "final_outcome": "Calificación A - Sobresaliente", por la regla reg_calificacion_a
```

## Dependencias con otros grupos

| Grupo | Qué usa G12 | Firma |
|---|---|---|
| G4 | `SchemaManager(carpeta_esquemas=contracts/)` | `validar_datos(datos, tipo)`, `validar_memoria(memoria, conocimiento)` → `{"valido", "errores"}` |
| G5 | `ForwardEngine` y sus funciones de E/S | `parse_knowledge_base`, `parse_working_memory`, `ForwardEngine(kb).run(wm)`, `working_memory_to_dict` |
| G8 | `XAIExplainer(knowledge_base)` | `explain_how`, `explain_why`, `explain_trace` |
| G9 | `ReportGenerator(ruta_conocimiento, ruta_memoria, ruta_dictamen)` | `generar_markdown()`; la API le pasa archivos temporales |

### Cómo conectar G6, G7 y G11

Todo pasa por `adaptadores.py`. Cuando el grupo publique su clase en `develop`:

1. Agregar un `_cargar_gX()` que la importe con `try/except ImportError`.
2. Guardarla en `Integraciones.__init__` y cambiar su entrada de `estado()` a `marca(...)`.
3. Exponer un método pequeño: `inferir_atras` (G6), `combinar_certeza` (G7) o `guardar_sesion` / `cargar_sesion` (G11). Luego llamarlo desde el método correspondiente de `servicio.py`.
4. Agregar una prueba en `tests/test_api.py` con el módulo real y otra con `Integraciones(deshabilitar={"GX"})`.

## Observaciones de contratos

Resueltas con los contratos congelados:

- Los tipos de atributo (`numeric`, `categorical`, `boolean`, `text`) y los operadores (`==`, `!=`, `>`, `<`, `>=`, `<=`, `in`) quedaron cerrados. `modelos.py` los usa.
- `explanation_why` se mantiene como una sola cadena.
- `session_id` es una cadena libre. La API genera `sess_AAAA_NNNNN`.

Pendientes:

- Formato con que G6 informará el próximo dato y la regla que evalúa. Mientras tanto, la API calcula `siguiente-pregunta` con las reglas de la base.
- Guardar con cada sesión la `meta.version` de la base con que se ejecutó, cuando G11 publique su módulo.

## Pruebas

Desde la raíz del repositorio:

```bash
python -m pytest grupo_12_api
```

Cubren:

- Caso normal con la base académica: calificación A y F, y repetición con D. La memoria y el dictamen se validan con `SchemaManager.validar_conjunto`.
- HOW, WHY, traza, siguiente pregunta y reporte.
- Datos inválidos: bases rechazadas por G4 o por la forma del contrato, hechos fuera de rango, opciones inexistentes, tipos incorrectos y atributos no declarados.
- Reglas que no se activan: 200 sin hechos derivados al inferir, y 409 al pedir el dictamen.
- Reglas en conflicto: gana la regla de mayor prioridad.
- Funcionamiento con respaldo cuando falta G4, G5 o G8.

`tests/test_e2e.py` recorre los 8 pasos del escenario obligatorio con un caso documentado: puntaje 95 → "Calificación A - Sobresaliente".
