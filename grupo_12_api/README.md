# Grupo 12 · API REST (FastAPI)

Archivo `esb_api.py`, servicio FastAPI. Coordinador: Samuel Díaz (@Shazam15).

Este módulo expone el shell experto por HTTP para el perfil de integrador o desarrollador externo. Cubre tres operaciones: cargar una base de conocimiento, ejecutar una consulta y pedir el dictamen con sus explicaciones HOW/WHY. La API no razona por su cuenta. Recibe la petición, llama al módulo del grupo que corresponde y devuelve el resultado con la forma de los contratos de `contracts/`.

## Estado

Integrada con todos los módulos del shell. `GET /salud` muestra en cada momento cuáles se usan de verdad (`real`) y cuáles se reemplazan por un respaldo propio (`simulado`).

| Grupo | Módulo | Estado | Uso en la API |
|---|---|---|---|
| G3 | `KBAuditor` | real | `GET /conocimiento/{kb_id}/auditoria` |
| G4 | `SchemaManager` | real | Valida la base (`POST /conocimiento`) y los hechos (`POST /consultas`, `POST /hechos`) con los esquemas de `contracts/` |
| G5 | `ForwardEngine` | real | `POST /inferir` en sesiones con `motor: "adelante"` |
| G6 | `BackwardEngine` | real | `GET /siguiente-pregunta` y `POST /inferir` en sesiones con `motor: "atras"` |
| G7 | `UncertaintyEngine` | real | Después de inferir calcula el `certainty_factor` de cada hecho derivado; el dictamen toma ese valor como `certainty_score` |
| G8 | `XAIExplainer` | real | HOW, WHY, traza y las explicaciones del dictamen |
| G9 | `ReportGenerator` | real | Reporte Markdown (`GET /reporte?formato=md`) |
| G11 | `ESBConverter` | real cuando se mergee la rama `grupo-11/esb-converter` | Guardar, listar y restaurar sesiones; responde 503 mientras no esté en `develop` |

G11 se activa solo cuando su rama se mergea, porque la API ya usa su interfaz publicada. Se comprobó con su rama actual: con G11 encima de esta versión pasan todas las pruebas del repositorio, incluida la de guardar y restaurar con `ESBConverter` real. Si un módulo real deja de importarse, la API sigue funcionando con su respaldo, y `/salud` lo indica.

G10 (`ESB_Interactive_UI`) usa `ServicioESB` directamente. Por eso las firmas públicas de `servicio.py` solo se amplían con parámetros opcionales.

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
| `GET /conocimiento/{kb_id}/auditoria?formato=json\|md` | Auditoría de G3: contradicciones, redundancias, condiciones inalcanzables, ciclos y tabla de decisión | reporte de G3 |
| `GET /conocimiento/{kb_id}/preguntas` | Atributos con su pregunta, tipo, opciones y rango | lista de `Pregunta` |
| `POST /consultas` | Inicia una sesión (`kb_id`, `motor`: `adelante` o `atras`, `hechos`, y opcionalmente `fc_reglas` y `fc_hechos`) | `session_id` |
| `POST /consultas/{session_id}/hechos` | Registra datos del usuario (y opcionalmente `fc_hechos`) y descarta las conclusiones anteriores | `memoria_trabajo.json` |
| `GET /consultas/{session_id}/siguiente-pregunta` | Próximo dato que conviene pedir, con su WHY | `SiguientePregunta` |
| `POST /consultas/{session_id}/inferir` | Ejecuta el motor de la sesión (G5 o G6) y luego G7 | `memoria_trabajo.json` + `halted_reason` |
| `GET /consultas/{session_id}/memoria` | Memoria de trabajo actual | `memoria_trabajo.json` |
| `GET /consultas/{session_id}/dictamen` | Resultado final con HOW/WHY | `dictamen_salida.json` |
| `GET /consultas/{session_id}/reporte?formato=md\|html` | Reporte descargable | Markdown o HTML |
| `GET /consultas/{session_id}/explicacion/how?atributo=` | ¿Cómo se llegó a ese valor? | `explanation_how` |
| `GET /consultas/{session_id}/explicacion/why?atributo=&regla=` | ¿Por qué se pide ese dato? | `explanation_why` |
| `GET /consultas/{session_id}/traza` | Reglas aplicadas en orden | lista de pasos |
| `POST /consultas/{session_id}/guardar` | Guarda la memoria de la sesión en disco (G11) | `session_id` y `ruta` |
| `GET /sesiones-guardadas` | Ids de las sesiones guardadas | lista de `session_id` |
| `POST /sesiones-guardadas/{session_id}/restaurar` | Vuelve a abrir una sesión guardada (`kb_id`, `motor`) | `session_id` |

### Motor hacia adelante y hacia atrás

Con `motor: "atras"`, G6 parte de la meta (`dictamen`, o la conclusión de mayor prioridad si la base no la tiene) y pide solo los datos necesarios para probarla. `siguiente-pregunta` devuelve el dato que pide G6 junto con la regla que lo motivó, y el WHY de G8 cita esa regla. `inferir` responde con el `halted_reason` de G6: `derivado` cuando se probó la meta y `falta_dato` cuando todavía falta información (en ese caso `dictamen` responde 409). Con los mismos hechos, los dos motores llegan al mismo dictamen.

Con `motor: "adelante"`, `siguiente-pregunta` recorre las reglas de mayor a menor prioridad y descarta las que ya no pueden cumplirse con los hechos conocidos. Devuelve el primer atributo que falta y que el usuario puede responder. Respeta `depends_on`, por lo que no ofrece una pregunta condicional mientras no se cumpla su condición. Por ejemplo, con `tipo_consulta = "Repeticion"` pide `nota_obtenida` y no `puntaje_final`.

El dictamen toma el hecho derivado `dictamen` o, si la base usa otro nombre, el último hecho derivado. Su `explanation_why` explica el último dato que se le preguntó al usuario dentro de la regla que produjo el resultado.

### Factores de certeza

Los contratos no tienen campo para el FC de una regla ni para el de un dato del usuario, así que la API los recibe en el cuerpo de `POST /consultas`. Son opcionales; lo que no se indica vale 1.0.

```json
{"kb_id": "kb_ejemplo",
 "hechos": {"materia": "Trabajo de Graduacion", "promedio": 2.25},
 "fc_reglas": {"rule_01": 0.8},
 "fc_hechos": {"promedio": 0.9}}
```

Después de inferir, G7 aplica la estrategia de MYCIN: 0.8 × min(1.0, 0.9) = 0.72. Ese valor queda en `derived_facts.dictamen.certainty_factor` y en el `certainty_score` del dictamen, y G8 lo muestra en el HOW como `(FC = 0.72)`. Si las premisas no superan el umbral de 0.2, la regla no aporta certeza y el FC queda en 0.0. Un FC fuera de [-1, 1], o uno que cite una regla o un atributo que la base no tiene, responde 422.

### Errores

| Código | Cuándo | Cuerpo |
|---|---|---|
| `404` | La base, la sesión, el atributo o la regla no existe, o el atributo no tiene valor | `{"detail": "..."}` |
| `409` | Se infiere sin hechos, o se pide el dictamen cuando ninguna regla se activó | `{"detail": "..."}` |
| `422` | La base, los hechos o los factores de certeza no son válidos | `{"detail": "...", "errores": [...]}` con los mensajes de G4 o G7 |
| `503` | La operación necesita un módulo que todavía no está en el repositorio (hoy, la persistencia de G11) | `{"detail": "..."}` |

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
| G3 | `KBAuditor(kb, schema_manager=..., usar_schema_manager=False)` | `auditar()` → `ReporteAuditoria` (`to_dict()`, `to_markdown()`) |
| G5 | `ForwardEngine` y sus funciones de E/S | `parse_knowledge_base`, `parse_working_memory`, `ForwardEngine(kb).run(wm)`, `working_memory_to_dict` |
| G6 | `BackwardEngine(kb)` sin `ask_fn` | `next_question(meta, memoria)` → `Question`; `prove(meta, memory=memoria)` → `BackwardResult` |
| G7 | `UncertaintyEngine(kb, rule_cfs, fact_cfs)` | `evaluate(memoria)`; sus `UncertaintyError` se responden como 422 |
| G8 | `XAIExplainer(knowledge_base)` | `explain_how`, `explain_why`, `explain_trace` |
| G9 | `ReportGenerator(ruta_conocimiento, ruta_memoria, ruta_dictamen)` | `generar_markdown()`; la API le pasa archivos temporales |
| G11 | `ESBConverter(schema_manager=...)` | `save_session_to_dir`, `load_session_from_dir`, `list_sessions` |

Las sesiones se guardan en `grupo_12_api/sesiones_guardadas/` (ignorada por git). Se puede usar otra carpeta con la variable de entorno `ESB_CARPETA_SESIONES`.

## Observaciones de contratos

Resueltas con los contratos congelados:

- Los tipos de atributo (`numeric`, `categorical`, `boolean`, `text`) y los operadores (`==`, `!=`, `>`, `<`, `>=`, `<=`, `in`) quedaron cerrados. `modelos.py` los usa.
- `explanation_why` se mantiene como una sola cadena.
- `session_id` es una cadena libre. La API genera `sess_AAAA_NNNNN`.

- G6 informa el próximo dato con su `rule_id` (`Question`), que es lo que el WHY necesitaba.

Pendiente: guardar con cada sesión la `meta.version` de la base con que se ejecutó. El contrato de memoria no tiene ese campo; al restaurar, la API pide el `kb_id` y G11 valida los hechos contra esa base.

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
- Factores de certeza con G7: valor por defecto, ejemplo 0.72, umbral de MYCIN, certeza enviada junto con los hechos y FC inválidos.
- Auditoría: 503 sin G3, delegación con un doble de G3 y, cuando `KBAuditor` está disponible, el reporte real.
- Motor hacia atrás (G6): solo pide los datos necesarios, `falta_dato`, mismo resultado que el motor hacia adelante y certeza con G7.
- Persistencia (G11): 503 sin G11, guardar y restaurar con un doble de G11, ids que no chocan y, cuando `ESBConverter` está disponible, el flujo real en una carpeta temporal.
- Funcionamiento con respaldo cuando falta G4, G5, G6, G7 u G8.

`tests/test_e2e.py` recorre los 8 pasos del escenario obligatorio con un caso documentado: puntaje 95 → "Calificación A - Sobresaliente".
