# Memoria técnica · Grupo 8 · Módulo de explicación XAI (HOW/WHY)

UNIVERSIDAD TECNOLÓGICA DE PANAMÁ · Facultad de Ingeniería de Sistemas Computacionales
1498 · Ingeniería de Sistemas Inteligentes · ES-Shell Suite (Parcial 2)

Integrantes: Christian Arce, Ashton Lasso y James Tack (coordinador)
Grupo: 1IL143 · Profesor: Ing. Nicholas Béliz Osorio · Fecha de entrega: 24 de noviembre de 2026
Repositorio: https://github.com/edwardliu2601/es-shell-suite-SI-1IL143 (carpeta `grupo_08_explainer/`)

## 1. Función del módulo

El Grupo 8 construyó `XAIExplainer`, que responde dos preguntas sobre una consulta del sistema experto. La pregunta HOW pide la cadena de reglas que llevó a una conclusión. La pregunta WHY pide la razón por la que el sistema solicita un dato, en función de la meta que persigue. Davis et al. (1977) introdujeron este reparto en MYCIN, y se conserva en los sistemas expertos basados en reglas porque permite que una persona sin formación técnica audite una decisión.

El módulo no ejecuta reglas ni razona por su cuenta. Lee lo que dejaron los motores de los grupos 5, 6 y 7 en la memoria de trabajo y lo convierte en texto. Esa decisión evita que la explicación describa algo distinto de lo que el motor hizo. El módulo es simbólico en su totalidad, usa solo la biblioteca estándar de Python y no emplea aprendizaje automático ni redes neuronales.

## 2. Interfaz y contratos

| Método | Entrada | Salida |
|---|---|---|
| `XAIExplainer(knowledge_base)` | contenido de `conocimiento_dominio.json` | instancia |
| `explain_how(working_memory, attribute_id)` | `memoria_trabajo.json` y un atributo | `list[str]`, campo `explanation_how` |
| `explain_why(attribute_id, rule_id=None)` | atributo solicitado y, si se conoce, la regla en evaluación | `str`, campo `explanation_why` |
| `explain_trace(working_memory)` | `memoria_trabajo.json` | `list[str]`, una línea por regla aplicada |

Del contrato de conocimiento lee `rules[].id`, `description`, `priority`, `conditions` y `explanation_template`. De la memoria de trabajo lee `facts`, `derived_facts[].derived_by_rule`, `certainty_factor` y `execution_trace`. No exige campos nuevos a ningún grupo.

## 3. Método de reconstrucción

La memoria de trabajo de la guía sigue el modelo de procedencia PROV-O (Lebo et al., 2013): cada disparo de regla es una actividad, `derived_by_rule` indica qué actividad generó un hecho y las condiciones de la regla señalan los hechos que usó. Con esas piezas, el HOW es un recorrido hacia atrás desde el hecho derivado hasta los datos del usuario.

1. Si el atributo es un dato ingresado, se informa que lo ingresó el usuario.
2. Si es derivado, se cita su regla, con el factor de certeza cuando difiere de 1,0.
3. Cada condición de la regla genera una línea de premisa. Si la premisa es a su vez derivada, su explicación se agrega con sangría de forma recursiva.
4. Se añade el `explanation_template` de la regla y, si otras reglas con la misma conclusión también se cumplen, se nombran.

El módulo lanza `ValueError` con mensaje en español ante tres situaciones: atributo sin valor, regla citada que no existe en la base y ciclo en la derivación. El WHY sin `rule_id` elige la regla de mayor prioridad que usa el atributo.

## 4. Integración

| Grupo | Relación |
|---|---|
| G5 `ForwardEngine` | provee `derived_by_rule` y `execution_trace`; hay una prueba sobre su salida real |
| G6 `BackwardEngine` | provee `derived_by_rule` y, con cada pregunta, el `rule_id` que se evalúa; su PR llama a `explain_why(atributo, rule_id)` |
| G7 `UncertaintyEngine` | provee `certainty_factor`; su prueba de integración verifica `(FC = 0.9)` en el HOW |
| G9 `ReportGenerator` | copia `explanation_how` y `explanation_why` del dictamen al informe |
| G10 interfaz | muestra el WHY de cada pregunta y el HOW del dictamen a través de G12 |
| G12 API | expone las tres funciones como endpoints y pasa el `rule_id` en curso al WHY |
| `integration/` | el paso 6 del escenario obligatorio ejecuta HOW y WHY y valida el dictamen con G4 |

## 5. Evaluación

La suite completa del repositorio, con las pruebas de todos los grupos, pasó 368 pruebas el 22 de noviembre de 2026. El módulo tiene 13 pruebas propias: el ejemplo de la sección 4.2 de la guía (reproduce exactamente las tres líneas de referencia), una cadena de dos reglas con factor de certeza, respaldo de varias reglas, los tres errores y una prueba contra la memoria real de G5. La integración con G7 y G12 se prueba en sus carpetas. El 23 de noviembre se repitió la corrida con el mismo resultado. El repositorio ejecuta pytest en CI con Python 3.11 y 3.12 en cada PR.

## 6. Limitaciones y trabajo futuro

1. `explanation_why` es una sola cadena. Con encadenamiento hacia atrás que pide varios datos, quien arma el dictamen guarda la explicación de una regla.
2. `execution_trace` no guarda las premisas, de modo que el explicador las toma de la base de conocimiento. Es correcto mientras la base no cambie en la sesión, y por eso G11 debería versionar la base de cada sesión guardada.
3. Sin `rule_id`, el WHY puede citar una regla distinta de la que el motor evalúa. G6 y G12 ya pasan ese `rule_id`, así que el problema queda para quien llame al WHY sin él.
4. Trabajo futuro: WHY sucesivos que suban por la pila de metas (requiere que G6 la entregue) y una pregunta WHY-NOT sobre por qué no se concluyó un valor. Clancey (1983) señaló que explicar bien exige representar la estrategia del sistema aparte de las reglas.

## Referencias

Clancey, W. J. (1983). The epistemology of a rule-based expert system: A framework for explanation. *Artificial Intelligence, 20*(3), 215-251. https://doi.org/10.1016/0004-3702(83)90008-5

Davis, R., Buchanan, B. G., y Shortliffe, E. H. (1977). Production rules as a representation for a knowledge-based consultation program. *Artificial Intelligence, 8*(1), 15-45. https://doi.org/10.1016/0004-3702(77)90003-0

Lebo, T., Sahoo, S., y McGuinness, D. (Eds.). (2013). *PROV-O: The PROV Ontology* (W3C Recommendation). W3C. https://www.w3.org/TR/2013/REC-prov-o-20130430/
