# Grupo 8 · Explicador XAI (HOW/WHY)

Archivo `esb_explainer.py`, clase `XAIExplainer`. Coordinador: James Tack (@endlessconflict).

Este módulo es el componente explicativo del shell. Responde dos preguntas, HOW y WHY. La pregunta HOW (¿cómo?) se contesta con la cadena de reglas que llevó a una conclusión, reconstruida desde el hecho derivado hasta los datos que ingresó el usuario. La pregunta WHY (¿por qué?) aparece cuando el motor pide un dato y el usuario quiere saber para qué sirve, y en ese caso la respuesta es la regla que necesita ese atributo y la conclusión a la que llevaría. Es el mismo reparto de funciones que introdujo MYCIN (Davis et al., 1977). Por tanto, el módulo no razona por su cuenta, sino que lee lo que los motores dejaron en la memoria de trabajo y lo convierte en texto que una persona sin formación técnica puede revisar.

## Estado

El módulo está integrado en `develop` y se ejecuta con memorias reales. G12 lo expone en la API REST (`grupo_12_api`), G7 comprueba el `(FC = x)` en `grupo_07_uncertainty/tests/test_integracion_g5_g8_g4.py`, y la prueba end-to-end de `integration/` lo usa en el paso 6 del escenario obligatorio. `grupo_08_explainer/tests/test_integracion_g5.py` verifica el HOW recursivo y la traza sobre la salida de `ForwardEngine` (G5). Las firmas quedaron congeladas el 16 de noviembre.

## API pública

| Método | Lo llama | Devuelve |
|---|---|---|
| `XAIExplainer(knowledge_base)` | G9, G10, G12 | instancia; recibe `conocimiento_dominio.json` ya cargado como `dict` |
| `explain_how(working_memory, attribute_id)` | G9, G10, G12 | `list[str]`, el campo `explanation_how` de `dictamen_salida.json` |
| `explain_why(attribute_id, rule_id=None)` | G10 (cuando G6 pide un dato), G12 | `str`, el campo `explanation_why` |
| `explain_trace(working_memory)` | G9, G10 | `list[str]`, una línea por regla aplicada |

Uso con los ejemplos de la sección 4.2:

```python
from grupo_08_explainer import XAIExplainer

ex = XAIExplainer(conocimiento_dominio)
ex.explain_how(memoria_trabajo, "dictamen")
# ["Se determinó 'Elegible' debido a la regla rule_01.",
#  "Premisa 1: materia == 'Trabajo de Graduacion' (Verificado)",
#  "Premisa 2: promedio >= 2.0 (Valor ingresado: 2.25)",
#  "El promedio cumple el mínimo requerido."]
ex.explain_why("promedio", "rule_01")
# "Se solicitó 'promedio' para evaluar la condición de la regla rule_01
#  (Elegibilidad para un trámite), que permitiría concluir dictamen = 'Elegible'."
```

Las tres primeras líneas coinciden con el `explanation_how` del ejemplo de `dictamen_salida.json`, y la cuarta es el `explanation_template` de la regla. Cuando una premisa es a su vez un hecho derivado, debajo de ella se agrega, con sangría, la explicación de ese hecho, hasta llegar a datos del usuario. Si el factor de certeza que registró G7 es distinto de 1.0, aparece en la primera línea como `(FC = 0.8)`. Si otras reglas con la misma conclusión también se cumplen con los datos de la sesión (G5 registra una sola por hecho, y G7 puede combinarlas en el FC), la última línea las nombra: `También respaldan esta conclusión: rule_02.` Un atributo sin valor, una regla citada que no existe en la base o un ciclo en la derivación producen `ValueError` con un mensaje en español.

## Dependencias con otros grupos

| Grupo | Qué necesita G8 | Para qué |
|---|---|---|
| G5, G6, G7 | Llenar `derived_facts[atributo].derived_by_rule` en cada hecho que deriven y `certainty_factor` cuando aplique | Reconstruir la cadena HOW |
| G6 | Pasar a G10 el `rule_id` que está evaluando cuando pide un dato | Que el WHY cite la regla correcta |
| G2, G4 | `conditions`, `priority`, `description` y `explanation_template` en cada regla, como en la sección 4.2 | Texto de cada premisa y de cada paso |
| G10 | Opción "¿por qué?" en cada pregunta y "¿cómo?" sobre el dictamen | Mostrar las explicaciones al usuario |

| Grupo | Qué recibe de G8 |
|---|---|
| G9 | `explain_how()` y `explain_why()` para llenar el dictamen, y `explain_trace()` para el reporte |
| G10 | `explain_why()` durante la consulta, y `explain_how()` y `explain_trace()` al final |
| G12 | Las cuatro funciones, para exponerlas como endpoints |

La memoria de trabajo de la sección 4.2 sigue en esencia el modelo de procedencia de PROV-O (Lebo et al., 2013), en el que cada disparo de regla es una actividad que usa unos hechos y genera otro. El campo `derived_by_rule` registra qué actividad generó cada hecho, y las condiciones de esa regla en `conocimiento_dominio.json` dicen qué hechos usó. Con esas dos piezas el HOW es un recorrido hacia atrás, sin volver a ejecutar ningún motor, y por eso G8 no necesita campos nuevos en los contratos.

## Limitaciones conocidas

1. `explanation_why` es una sola cadena. Con encadenamiento hacia atrás que pide varios datos, quien arma el dictamen (G12) guarda la explicación de la regla meta.
2. `execution_trace` no guarda las premisas. El explicador las toma de la base de conocimiento, lo cual es correcto mientras la base no cambie durante la sesión.
3. `explain_why` sin `rule_id` elige la regla de mayor prioridad que usa el atributo. G12 pasa el `rule_id` que está evaluando, y con él la explicación cita la regla correcta.

Clancey (1983) mostró que las reglas de MYCIN no bastaban para justificar el razonamiento, porque la estrategia del sistema quedaba implícita dentro de ellas. La limitación 3 apunta al mismo problema a escala pequeña, ya que solo el motor sabe qué meta persigue cuando pregunta.

## Pruebas

Las pruebas se ejecutan desde la raíz del repositorio con el comando siguiente.

```bash
python -m pytest grupo_08_explainer
```

Cubren el caso normal de la sección 4.2, una cadena de dos reglas con factor de certeza, reglas que respaldan la misma conclusión, datos inválidos (regla inexistente, atributo que ninguna regla usa), una regla que no se activó, un ciclo en la derivación y la integración con la memoria real de G5. Se requiere Python 3.11 o superior y `pytest`; la prueba de integración se omite si G5 no está presente.

## Referencias

Clancey, W. J. (1983). The epistemology of a rule-based expert system: A framework for explanation. *Artificial Intelligence, 20*(3), 215-251. https://doi.org/10.1016/0004-3702(83)90008-5

Davis, R., Buchanan, B. G., & Shortliffe, E. H. (1977). Production rules as a representation for a knowledge-based consultation program. *Artificial Intelligence, 8*(1), 15-45. https://doi.org/10.1016/0004-3702(77)90003-0

Lebo, T., Sahoo, S., & McGuinness, D. (Eds.). (2013). *PROV-O: The PROV Ontology* (W3C Recommendation). W3C. https://www.w3.org/TR/2013/REC-prov-o-20130430/
