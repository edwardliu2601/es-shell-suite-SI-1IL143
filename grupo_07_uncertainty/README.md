# Grupo 7 · Incertidumbre y factores de certeza

Archivo `esb_engine_uncertainty.py`, clase `UncertaintyEngine`.

Este módulo calcula cuánta confianza merece cada hecho que deriva el motor de inferencia. Usa factores de certeza (FC) entre -1.0 y 1.0 y la estrategia de MYCIN. El FC de una conclusión sale del FC de la regla multiplicado por el FC más bajo de sus premisas, y cuando varias reglas llegan a la misma conclusión sus aportes se combinan. Los resultados van a campos que los contratos ya tienen: `derived_facts[atributo].certainty_factor` en `memoria_trabajo.json` y `certainty_score` en `dictamen_salida.json`. Ningún contrato cambia.

## Estado

El módulo trabaja sobre diccionarios con la forma de los contratos JSON y no importa código de otros grupos. Se puede probar con los ejemplos de la sección 4.2 de la guía. También se probó el recorrido completo con la memoria que produce G5, la explicación de G8 y la validación de G4 (ver Pruebas). Si no se entrega ningún FC, todo vale 1.0 y la salida coincide con los ejemplos de la guía. Las firmas son propuestas hasta que los coordinadores las acepten.

## API pública

| Método | Lo llamaría | Devuelve |
|---|---|---|
| `UncertaintyEngine(knowledge_base, rule_cfs=None, fact_cfs=None, *, default_cf=1.0, threshold=0.2, combine_equivalent_rules=True)` | G10, G12 | instancia; recibe `conocimiento_dominio.json` ya cargado como `dict` |
| `evaluate(working_memory)` | G10, G12 | copia de la memoria con `certainty_factor` en cada hecho derivado |
| `certainty_score(working_memory, attribute_id)` | G9, G12 | `float`, el FC del atributo indicado |
| `complete_verdict(verdict, working_memory, attribute_id)` | G9, G12 | copia del dictamen con el campo `certainty_score` |

Parámetros del constructor:

- `rule_cfs` es un diccionario `{id_de_regla: FC}`. Una regla sin entrada usa `default_cf`.
- `fact_cfs` es un diccionario `{id_de_atributo: FC}` para datos que ingresa el usuario. Un dato sin entrada usa `default_cf`.
- `threshold` es el FC mínimo de las premisas para que una regla aporte.
- `combine_equivalent_rules` activa la suma de reglas que G5 no registró (ver más abajo).

El módulo también expone las funciones del cálculo, por si G6 o G10 las necesitan por separado: `validate_cf`, `combine_premises`, `propagate`, `combine_evidence` y `combine_all`.

Cualquier dato inválido produce `UncertaintyError` (subclase de `ValueError`) con un mensaje en español. Eso incluye un FC fuera de rango, un FC para una regla o atributo que la base no tiene, una regla citada que no existe, un hecho derivado sin registro en la traza y un ciclo en la derivación.

Uso con el ejemplo de la sección 4.2:

```python
from grupo_07_uncertainty import UncertaintyEngine

motor = UncertaintyEngine(
    conocimiento_dominio,
    rule_cfs={"rule_01": 0.8},
    fact_cfs={"promedio": 0.9},
)
memoria = motor.evaluate(memoria_trabajo)
memoria["derived_facts"]["dictamen"]["certainty_factor"]   # 0.72

dictamen = motor.complete_verdict(dictamen_salida, memoria_trabajo, "dictamen")
dictamen["certainty_score"]                                 # 0.72
```

Aquí el FC de las premisas es 0.9, el menor entre `materia` (1.0 por defecto) y `promedio` (0.9), y 0.8 por 0.9 da 0.72.

## Cómo se calcula

1. Las premisas de una regla se combinan con el mínimo de sus FC. Un hecho derivado que sirve de premisa aporta el FC que se calculó para él.
2. La regla aporta `FC_regla × FC_premisas`. Si el FC de las premisas no supera el umbral (0.2, el valor de MYCIN), la regla no aporta nada.
3. Los aportes a la misma conclusión se combinan de dos en dos con `combine_evidence(a, b)`:
   - si ambos son mayores o iguales que 0: `a + b × (1 - a)`
   - si ambos son menores o iguales que 0: `a + b × (1 + a)`
   - si tienen signo distinto: `(a + b) / (1 - min(|a|, |b|))`
4. Sin ningún aporte, el hecho queda con FC 0.0. Es el caso de una regla que disparó con premisas por debajo del umbral.

Dos evidencias de 0.6 y 0.5 dan 0.8. Una de 0.8 y otra de -0.6 dan 0.5. El caso de 1.0 contra -1.0 divide entre cero y se define como 0.0. Los resultados se redondean a 6 decimales. La combinación no depende del orden de las reglas, salvo por el último decimal que deja el redondeo.

## Reglas que G5 no registró

G5 deja que una sola regla afirme cada atributo. Si dos reglas llevan al mismo valor, solo queda registrada la de mayor prioridad, y la combinación de evidencias no tendría nada que combinar. Por eso `evaluate` revisa la base de nuevo y suma al cálculo cada regla que cumple estas cuatro condiciones:

- concluye el mismo atributo con el mismo valor,
- no es la que figura en `derived_by_rule`,
- sus condiciones se cumplen con los valores finales de la memoria,
- cada premisa es un dato del usuario o un hecho derivado antes que este en `execution_trace`.

La última condición deja fuera reglas que el motor no podía haber disparado en ese momento y evita ciclos. Con `combine_equivalent_rules=False` solo cuenta la regla registrada.

## Dependencias con otros grupos

| Grupo | Qué necesita G7 | Para qué |
|---|---|---|
| G5, G6 | `derived_by_rule` en cada hecho derivado y `execution_trace` completo, como ya hace G5 | Saber qué regla produjo cada hecho y en qué orden |
| G2, G4 | `conditions` y `conclusion` en cada regla, según los esquemas actuales | Releer las reglas al calcular |

| Grupo | Qué recibe de G7 |
|---|---|
| G8 | `certainty_factor` en cada hecho derivado. Su explicador ya lo muestra como `(FC = 0.8)` cuando es distinto de 1.0 |
| G9 | `certainty_score` para el reporte |
| G12 | `evaluate()` y `complete_verdict()` para llenar `memoria_trabajo.json` y `dictamen_salida.json` en lugar del valor simulado |

## Pendientes para coordinar

1. Hoy G5 no escribe `certainty_factor`. Mientras no se acuerde otra cosa, quien arma la consulta (G10 o G12) puede llamar a `evaluate` después de la inferencia, y G5 y G6 no tienen que cambiar.
2. Los contratos no tienen campo para el FC de una regla ni para el de un dato del usuario. Por eso entran como parámetros. Si los coordinadores aprueban un campo en el futuro, solo cambia la forma de armar `rule_cfs` y `fact_cfs`.
3. `dictamen_salida.json` no indica cuál es el atributo del resultado final. `complete_verdict` pide ese atributo (en los ejemplos, `dictamen`) y le copia su FC a `certainty_score`.

## Pruebas

Las pruebas se ejecutan desde la raíz del repositorio con el comando siguiente.

```bash
python -m pytest grupo_07_uncertainty
```

`test_uncertainty.py` cubre las fórmulas (rango, conmutatividad, asociatividad, casos límite), el ejemplo de la sección 4.2, el umbral, cadenas de reglas, reglas que llegan a la misma conclusión (suma, FC negativo, otro valor, condiciones falsas, premisa derivada después) y datos inválidos. `test_integracion_g5_g8_g4.py` toma la memoria que produce `ForwardEngine`, le calcula los FC, comprueba que G8 los muestre en el HOW y que G4 valide la memoria y el dictamen. Esas pruebas se omiten si falta `jsonschema` o alguno de esos módulos. El módulo solo requiere Python 3.11 o superior y `pytest`.

## Referencias

Buchanan, B. G., & Shortliffe, E. H. (Eds.). (1984). *Rule-based expert systems: The MYCIN experiments of the Stanford Heuristic Programming Project*. Addison-Wesley.

Shortliffe, E. H., & Buchanan, B. G. (1975). A model of inexact reasoning in medicine. *Mathematical Biosciences, 23*(3-4), 351-379. https://doi.org/10.1016/0025-5564(75)90047-4
