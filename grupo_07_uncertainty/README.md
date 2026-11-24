# Grupo 7 · Incertidumbre y factores de certeza

Archivo `esb_engine_uncertainty.py`, clase `UncertaintyEngine`.

El módulo calcula el factor de certeza (FC) de cada hecho que deriva el motor de inferencia, con valores entre -1.0 y 1.0 y las reglas de MYCIN. El resultado se guarda en `derived_facts[atributo].certainty_factor` de `memoria_trabajo.json` y en `certainty_score` de `dictamen_salida.json`. No se cambió ningún contrato.

## API

| Método | Lo llamaría | Devuelve |
|---|---|---|
| `UncertaintyEngine(knowledge_base, rule_cfs=None, fact_cfs=None, *, default_cf=1.0, threshold=0.2, combine_equivalent_rules=True)` | G10, G12 | instancia; recibe `conocimiento_dominio.json` ya cargado como `dict` |
| `evaluate(working_memory)` | G10, G12 | copia de la memoria con `certainty_factor` en cada hecho derivado |
| `certainty_score(working_memory, attribute_id)` | G9, G12 | `float`, el FC del atributo indicado |
| `complete_verdict(verdict, working_memory, attribute_id)` | G9, G12 | copia del dictamen con el campo `certainty_score` |

Parámetros del constructor:

- `rule_cfs`: diccionario `{id_de_regla: FC}`. Las reglas que no aparecen usan `default_cf`.
- `fact_cfs`: diccionario `{id_de_atributo: FC}` para los datos que ingresa el usuario. Los que no aparecen usan `default_cf`.
- `threshold`: FC mínimo de las premisas para que una regla cuente.
- `combine_equivalent_rules`: suma las reglas equivalentes que G5 no dejó registradas (ver abajo).

Si no se pasa ningún FC, todo vale 1.0.

También se pueden usar por separado las funciones del cálculo: `validate_cf`, `combine_premises`, `propagate`, `combine_evidence` y `combine_all`.

Los datos inválidos lanzan `UncertaintyError`, que hereda de `ValueError`, con el mensaje en español. Pasa con un FC fuera de rango, un FC para una regla o atributo que no está en la base, una regla citada que no existe, un hecho derivado que no aparece en la traza o un ciclo en la derivación.

Ejemplo:

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

Las premisas valen 0.9 porque es el menor entre `materia` (1.0) y `promedio` (0.9). Por eso el resultado es 0.8 × 0.9 = 0.72.

## Cálculo

1. El FC de las premisas de una regla es el menor de sus FC. Si una premisa es un hecho derivado, se usa el FC que ya se calculó para ese hecho.
2. Cada regla aporta `FC_regla × FC_premisas`, siempre que el FC de las premisas sea mayor que el umbral (0.2 por defecto, como en MYCIN).
3. Si varias reglas llegan a la misma conclusión, sus aportes se combinan de dos en dos con `combine_evidence(a, b)`:
   - si ambos son mayores o iguales que 0: `a + b × (1 - a)`
   - si ambos son menores o iguales que 0: `a + b × (1 + a)`
   - si tienen signo distinto: `(a + b) / (1 - min(|a|, |b|))`
4. Si ninguna regla aporta, el hecho queda en 0.0.

Por ejemplo, 0.6 y 0.5 dan 0.8, y 0.8 con -0.6 da 0.5. El caso de 1.0 con -1.0 daría división entre cero, así que se toma como 0.0. Los resultados se redondean a 6 decimales.

## Reglas equivalentes

G5 registra una sola regla por atributo. Si dos reglas llevan al mismo valor, solo queda la de mayor prioridad, y entonces no habría nada que combinar. Por eso `evaluate` vuelve a recorrer la base y también cuenta las reglas que:

- concluyen el mismo atributo con el mismo valor,
- no son la que aparece en `derived_by_rule`,
- cumplen sus condiciones con los valores finales de la memoria, y
- solo usan datos del usuario o hechos que aparecen antes en `execution_trace`.

Con la última condición no se cuentan reglas que el motor todavía no podía disparar, y tampoco se forman ciclos. Para contar solo la regla registrada, se usa `combine_equivalent_rules=False`.

## Dependencias

| Grupo | Qué usa G7 |
|---|---|
| G5, G6 | `derived_by_rule` en cada hecho derivado y `execution_trace` |
| G2, G4 | `conditions` y `conclusion` de cada regla |

| Grupo | Qué recibe de G7 |
|---|---|
| G8 | `certainty_factor` en cada hecho derivado; el explicador lo muestra como `(FC = 0.8)` cuando no es 1.0 |
| G9 | `certainty_score` para el reporte |
| G12 | `evaluate()` y `complete_verdict()` para llenar `memoria_trabajo.json` y `dictamen_salida.json` |

## Pruebas

Desde la raíz del repositorio:

```bash
python -m pytest grupo_07_uncertainty
```

`test_uncertainty.py` prueba las fórmulas, el umbral, las cadenas de reglas, las reglas equivalentes y los datos inválidos. `test_integracion_g5_g8_g4.py` toma la memoria que genera `ForwardEngine`, le calcula los FC y revisa que G8 los muestre y que G4 valide la memoria y el dictamen. Si falta `jsonschema` o alguno de esos módulos, esas pruebas se omiten. Se necesita Python 3.11 o superior y `pytest`.
