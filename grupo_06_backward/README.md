# Grupo 6 · Motor de encadenamiento hacia atrás

Archivo `esb_engine_backward.py`, clase `BackwardEngine`. Coordinador: Marc Chavarría (@marcdc2020).

Documentación completa del diseño, la API, las pruebas y las decisiones: [docs/DOCUMENTACION.md](docs/DOCUMENTACION.md).

El motor parte de una meta, por ejemplo `dictamen`, y busca las reglas que la concluyen. Si una condición depende de un atributo que otra regla concluye, ese atributo se vuelve una sub-meta. Si depende de un atributo que ninguna regla concluye, el motor le pide el dato al usuario. Solo pregunta lo necesario: con los datos que ya tiene, descarta una regla antes de pedir el resto de sus condiciones.

## Estado

Trabaja sobre diccionarios con la forma de los contratos JSON y no importa código de otros grupos. Escribe solo en campos que los contratos ya tienen, así que ningún contrato cambia. Las firmas son propuestas hasta que los coordinadores las acepten.

## API pública

| Método | Lo llamaría | Devuelve |
|---|---|---|
| `BackwardEngine(knowledge_base, ask_fn=None, *, max_depth=100)` | G10, G12 | instancia; recibe `conocimiento_dominio.json` ya cargado como `dict` |
| `prove(goal_attribute, goal_value=None, memory=None, *, session_id=None)` | G10, G12 | `BackwardResult` |
| `next_question(goal_attribute, memory=None, goal_value=None)` | G12 | `Question` o `None`, sin preguntar |
| `validate_answer(attribute_id, value)` | G10 | valor normalizado, o `InvalidAnswerError` |

`ask_fn(question)` se llama cada vez que falta un dato y devuelve el valor ingresado, o `None` si el usuario no lo sabe. El motor no vuelve a preguntar ese dato y prueba otras reglas.

`Question` trae `attribute_id`, `question`, `type`, `options` y `range` (tomados de `attributes[]`), más `rule_id`, la regla que se evalúa al pedir el dato, y `goal`, el atributo que esa regla concluiría. Si el atributo no tiene `question`, se genera un texto por defecto.

`BackwardResult` trae:

| Campo | Contenido |
|---|---|
| `achieved`, `value` | si se alcanzó la meta (con `goal_value`, si coincide) y el valor del atributo |
| `reason` | `derivado`, `dato_conocido`, `valor_distinto`, `no_se_cumple_ninguna_regla`, `sin_conclusion` o `falta_dato` |
| `memory` | `memoria_trabajo.json` actualizado. La memoria que se recibe no se modifica |
| `fired_rules` | reglas probadas, en orden de derivación |
| `questions_asked` | preguntas formuladas, en orden |
| `pending_question` | con `ask_fn=None`, el primer dato que falta |
| `proof` | razonamiento paso a paso, en texto |

Los errores son subclases de `BackwardEngineError` (`ValueError`) con mensajes en español: `InvalidKnowledgeBaseError`, `InvalidWorkingMemoryError` e `InvalidAnswerError`.

## Uso

```python
import json
from grupo_06_backward import BackwardEngine, InvalidAnswerError

kb = json.load(open("grupo_06_backward/datos_ejemplo/conocimiento_encadenado.json", encoding="utf-8"))
motor = BackwardEngine(kb)

def preguntar(q):
    while True:
        texto = input(f"{q.question} ")          # q.rule_id y q.goal sirven para el WHY
        if not texto:
            return None                          # no sabe
        try:
            return motor.validate_answer(q.attribute_id, texto)
        except InvalidAnswerError as error:
            print(error)

motor.ask_fn = preguntar
res = motor.prove("dictamen")                    # o prove("dictamen", "Elegible")
print(res.value, res.fired_rules)                # Elegible ['rule_04', 'rule_01']
```

Sin `ask_fn` el motor no pregunta, y sirve para una API sin estado:

```python
pregunta = motor.next_question("dictamen", memoria_de_la_sesion)
if pregunta is None:
    memoria_final = motor.prove("dictamen", memory=memoria_de_la_sesion).memory
```

### Consola de demostración

```bash
python -m grupo_06_backward.esb_backward_cli grupo_06_backward/datos_ejemplo/conocimiento_encadenado.json
```

En cada pregunta, `?` muestra por qué se pide el dato (usa a G8 si está disponible) y Enter significa "no sé". Opciones: `--meta`, `--valor` (hipótesis), `--memoria` (memoria de partida), `--salida` (guarda la memoria resultante) y `--razonamiento`.

## Política del motor

1. Las reglas de una meta se prueban de mayor a menor `priority` (empate: `id`), igual que G5. Gana la primera que se cumple.
2. Un hecho ya presente, ingresado o derivado, no se sobrescribe.
3. Las condiciones conocidas se evalúan primero; si una es falsa, la regla se descarta sin preguntar. Después se resuelven, en orden, las que faltan.
4. Un atributo que alguna regla concluye se deriva y no se pregunta. Uno que ninguna regla concluye se pregunta.
5. Una pregunta con `depends_on` solo se formula si su condición se cumple.
6. Un ciclo entre reglas se detecta y esa vía se descarta. `max_depth` limita las cadenas muy largas.
7. Una comparación imposible, como `>` entre texto y número, cuenta como condición falsa, igual que en G5.
8. Cada regla probada agrega un hecho a `derived_facts` (con `derived_by_rule` y `certainty_factor` 1.0, que G7 puede recalcular) y un paso a `execution_trace`. La traza sigue el orden de derivación: primero las sub-metas.

## Dependencias con otros grupos

| Grupo | Qué necesita G6 | Para qué |
|---|---|---|
| G1, G2, G4 | `attributes[]` y `rules[]` como en los contratos | formular preguntas y evaluar reglas |

| Grupo | Qué recibe de G6 |
|---|---|
| G8 | `memory` con `derived_by_rule` y la traza, y `Question.rule_id` para el WHY: `explain_why(q.attribute_id, q.rule_id)` |
| G7 | `memory` con `certainty_factor` 1.0 en cada hecho derivado, que `UncertaintyEngine.evaluate()` recalcula (probado) |
| G9 | `memory` y `fired_rules` para el reporte |
| G10 | `ask_fn`, `Question` y `validate_answer` para la consulta interactiva |
| G12 | `prove` y `next_question` para el motor `atras` |

Para conectarlo en la API, siguiendo el README de G12, en `adaptadores.py`:

```python
def _cargar_g6():
    try:
        from grupo_06_backward import BackwardEngine
    except ImportError:
        return None
    return BackwardEngine

# en Integraciones
def inferir_atras(self, kb: dict, memoria: dict, meta: str) -> tuple[dict, str]:
    res = self._g6(kb).prove(meta, memory=memoria)
    return res.memory, res.reason

def siguiente_pregunta_atras(self, kb: dict, memoria: dict, meta: str):
    return self._g6(kb).next_question(meta, memoria)   # Question o None
```

## Diferencia conocida con G5

En los 27 casos de la base de ejemplo, ambos motores dan el mismo dictamen y la misma regla (`test_g5_y_g6_coinciden_...`). Pueden discrepar en un caso límite. G5 dispara siempre la regla de mayor prioridad entre todas las activables, y G6 prueba por meta. Si una regla de baja prioridad ya es activable y la de alta prioridad necesita antes un hecho derivado, G5 dispara primero la de baja y la de alta ya no puede sobrescribirla, mientras que G6 llega a la de alta. Está documentado en `test_diferencia_conocida_con_g5_...` y conviene acordarlo con G5 antes de la demostración. No ocurre cuando las reglas de una misma meta son mutuamente excluyentes.

## Pendientes para coordinar

1. `explanation_why` es una sola cadena, pero este motor puede hacer varias preguntas. Cada `Question` trae su regla; quien arma el dictamen (G9 o G12) decide cuál se explica.
2. `execution_trace` no guarda las premisas ni las preguntas. El detalle está en `BackwardResult.proof`, que no forma parte de ningún contrato.
3. `certainty_factor` queda en 1.0 hasta que G7 lo recalcule.

## Pruebas

Desde la raíz del repositorio:

```bash
python -m pytest grupo_06_backward -v
```

`test_backward.py` cubre el ejemplo de la sección 4.2, sub-metas encadenadas, preguntas solo cuando hacen falta, hipótesis, conflictos por prioridad y por `id`, ciclos, datos desconocidos, preguntas condicionales, respuestas inválidas, bases y memorias inválidas, y límites de profundidad y de rendimiento. `test_cli.py` prueba la consola. `test_integracion_g5_g8_g4.py` compara con `ForwardEngine`, pide el HOW y el WHY a `XAIExplainer` y valida con `SchemaManager.validar_conjunto`. `test_integracion_g7.py` calcula los factores de certeza con `UncertaintyEngine` sobre la memoria de G6. Las pruebas de integración se omiten si falta `jsonschema` o el módulo del otro grupo. Solo se requiere Python 3.11 o superior y `pytest`.
