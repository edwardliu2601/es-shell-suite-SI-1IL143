# Reporte de Auditoría — Base de conocimiento con inconsistencias intencionales (ejemplo)

## Resumen general

- **Estado:** `INVALIDA` (`es_valida=False`)
- **Versión del dominio:** 1.0
- **Grupo autor:** Grupo 3 - KBAuditor
- **Total de atributos:** 4
- **Total de reglas:** 10
- **Hallazgos totales:** 15 (ERROR: 9, WARNING: 6, INFO: 0)

## Hallazgos detectados

### 1. [ERROR] `esquema_invalido`

- **Descripción:** Validación de esquema (SchemaManager): $.rules[7].conditions[0].value: El valor 'Doctorado' no está entre las opciones permitidas.
- **Reglas implicadas:** —
- **Atributos implicados:** —

### 2. [ERROR] `esquema_invalido`

- **Descripción:** Validación de esquema (SchemaManager): $.rules[9].conditions[0].attribute_id: El atributo 'atributo_fantasma' no existe.
- **Reglas implicadas:** —
- **Atributos implicados:** —

### 3. [ERROR] `contradiccion`

- **Descripción:** Conflicto entre 'regla_conflicto_1' y 'regla_conflicto_2': sus condiciones son solapables, pero concluyen valores distintos para 'dictamen' ('Aprobado' vs 'Revision'). Ambas tienen la misma prioridad (20), lo que produce una ambigüedad irresoluble.
- **Reglas implicadas:** `regla_conflicto_1`, `regla_conflicto_2`
- **Atributos implicados:** `dictamen`, `modalidad`, `promedio`

### 4. [WARNING] `contradiccion`

- **Descripción:** Conflicto entre 'regla_conflicto_1' y 'regla_conflicto_desempatado': sus condiciones son solapables, pero concluyen valores distintos para 'dictamen' ('Aprobado' vs 'Rechazado'). Prioridades distintas (regla_conflicto_1=20, regla_conflicto_desempatado=10); la regla 'regla_conflicto_1' desempata por mayor prioridad, pero conviene revisar el solapamiento.
- **Reglas implicadas:** `regla_conflicto_1`, `regla_conflicto_desempatado`
- **Atributos implicados:** `dictamen`, `modalidad`, `promedio`

### 5. [ERROR] `contradiccion`

- **Descripción:** Conflicto entre 'regla_conflicto_2' y 'regla_duplicada': sus condiciones son solapables, pero concluyen valores distintos para 'dictamen' ('Revision' vs 'Aprobado'). Ambas tienen la misma prioridad (20), lo que produce una ambigüedad irresoluble.
- **Reglas implicadas:** `regla_conflicto_2`, `regla_duplicada`
- **Atributos implicados:** `dictamen`, `modalidad`, `promedio`

### 6. [WARNING] `contradiccion`

- **Descripción:** Conflicto entre 'regla_conflicto_desempatado' y 'regla_duplicada': sus condiciones son solapables, pero concluyen valores distintos para 'dictamen' ('Rechazado' vs 'Aprobado'). Prioridades distintas (regla_conflicto_desempatado=10, regla_duplicada=20); la regla 'regla_duplicada' desempata por mayor prioridad, pero conviene revisar el solapamiento.
- **Reglas implicadas:** `regla_conflicto_desempatado`, `regla_duplicada`
- **Atributos implicados:** `dictamen`, `modalidad`, `promedio`

### 7. [WARNING] `contradiccion`

- **Descripción:** Conflicto entre 'regla_conflicto_desempatado' y 'regla_subsumida': sus condiciones son solapables, pero concluyen valores distintos para 'dictamen' ('Rechazado' vs 'Aprobado'). Prioridades distintas (regla_conflicto_desempatado=10, regla_subsumida=15); la regla 'regla_subsumida' desempata por mayor prioridad, pero conviene revisar el solapamiento.
- **Reglas implicadas:** `regla_conflicto_desempatado`, `regla_subsumida`
- **Atributos implicados:** `dictamen`, `modalidad`, `promedio`

### 8. [WARNING] `redundancia`

- **Descripción:** Reglas duplicadas 'regla_conflicto_1' y 'regla_duplicada': tienen condiciones lógicamente equivalentes y concluyen lo mismo ('dictamen' = 'Aprobado').
- **Reglas implicadas:** `regla_conflicto_1`, `regla_duplicada`
- **Atributos implicados:** `dictamen`, `modalidad`, `promedio`

### 9. [WARNING] `redundancia`

- **Descripción:** Subsunción detectada: la regla 'regla_conflicto_1' (más general) subsume a 'regla_subsumida' con la misma conclusión ('dictamen' = 'Aprobado'), haciendo a 'regla_subsumida' redundante.
- **Reglas implicadas:** `regla_conflicto_1`, `regla_subsumida`
- **Atributos implicados:** `dictamen`, `modalidad`, `promedio`

### 10. [WARNING] `redundancia`

- **Descripción:** Subsunción detectada: la regla 'regla_duplicada' (más general) subsume a 'regla_subsumida' con la misma conclusión ('dictamen' = 'Aprobado'), haciendo a 'regla_subsumida' redundante.
- **Reglas implicadas:** `regla_duplicada`, `regla_subsumida`
- **Atributos implicados:** `dictamen`, `modalidad`, `promedio`

### 11. [ERROR] `condicion_inalcanzable`

- **Descripción:** Regla 'regla_contradiccion_interna' muerta por contradicción interna sobre 'promedio': ningún valor puede satisfacer simultáneamente (promedio >= 2.5 Y promedio < 2.0).
- **Reglas implicadas:** `regla_contradiccion_interna`
- **Atributos implicados:** `promedio`

### 12. [ERROR] `condicion_inalcanzable`

- **Descripción:** Regla 'regla_fuera_de_rango': la condición 'promedio > 4.0' es imposible de satisfacer dentro del rango declarado [0.0, 3.0].
- **Reglas implicadas:** `regla_fuera_de_rango`
- **Atributos implicados:** `promedio`

### 13. [ERROR] `condicion_inalcanzable`

- **Descripción:** Regla 'regla_opcion_invalida': el valor 'Doctorado' en 'modalidad' no existe en las opciones permitidas ['Presencial', 'Virtual', 'Semipresencial'].
- **Reglas implicadas:** `regla_opcion_invalida`
- **Atributos implicados:** `modalidad`

### 14. [ERROR] `condicion_inalcanzable`

- **Descripción:** Regla 'regla_atributo_huerfano': el atributo 'beca_interna' se usa en una condición, pero no tiene 'question' para preguntarse al usuario ni es concluido por ninguna regla (hecho imposible de obtener).
- **Reglas implicadas:** `regla_atributo_huerfano`
- **Atributos implicados:** `beca_interna`

### 15. [ERROR] `condicion_inalcanzable`

- **Descripción:** Regla 'regla_atributo_inexistente': la condición referencia al atributo inexistente 'atributo_fantasma' (no está declarado en 'attributes' ni es derivado por ninguna regla).
- **Reglas implicadas:** `regla_atributo_inexistente`
- **Atributos implicados:** `atributo_fantasma`

## Tabla de Decisión

| Regla | Prioridad | modalidad | promedio | beca_interna | atributo_fantasma | Conclusión | Estado |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| `regla_conflicto_1` | 20 | `== 'Presencial'` | `>= 2.0` | — | — | `dictamen = 'Aprobado'` | CONFLICTO(ERROR), CONFLICTO(WARNING), REDUNDANTE(WARNING) [con regla_conflicto_2, regla_conflicto_desempatado, regla_duplicada, regla_subsumida] |
| `regla_conflicto_2` | 20 | `== 'Presencial'` | `<= 2.3` | — | — | `dictamen = 'Revision'` | CONFLICTO(ERROR) [con regla_conflicto_1, regla_duplicada] |
| `regla_conflicto_desempatado` | 10 | `in ['Presencial', 'Virtual']` | `>= 2.8` | — | — | `dictamen = 'Rechazado'` | CONFLICTO(WARNING) [con regla_conflicto_1, regla_duplicada, regla_subsumida] |
| `regla_duplicada` | 20 | `== 'Presencial'` | `>= 2.0` | — | — | `dictamen = 'Aprobado'` | CONFLICTO(ERROR), CONFLICTO(WARNING), REDUNDANTE(WARNING) [con regla_conflicto_2, regla_conflicto_desempatado, regla_conflicto_1, regla_subsumida] |
| `regla_subsumida` | 15 | `== 'Presencial'` | `>= 2.5` | — | — | `dictamen = 'Aprobado'` | CONFLICTO(WARNING), REDUNDANTE(WARNING) [con regla_conflicto_desempatado, regla_conflicto_1, regla_duplicada] |
| `regla_contradiccion_interna` | 10 | — | `>= 2.5 Y < 2.0` | — | — | `dictamen = 'Aprobado'` | INALCANZABLE(ERROR) |
| `regla_fuera_de_rango` | 10 | — | `> 4.0` | — | — | `dictamen = 'Aprobado'` | INALCANZABLE(ERROR) |
| `regla_opcion_invalida` | 10 | `== 'Doctorado'` | — | — | — | `dictamen = 'Revision'` | INALCANZABLE(ERROR) |
| `regla_atributo_huerfano` | 10 | — | — | `== true` | — | `dictamen = 'Aprobado'` | INALCANZABLE(ERROR) |
| `regla_atributo_inexistente` | 10 | — | — | — | `== 'X'` | `dictamen = 'Rechazado'` | INALCANZABLE(ERROR) |
