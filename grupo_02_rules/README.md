# Grupo 2 — Editor de reglas SI–ENTONCES y prioridades

**Proyecto:** ES-Shell Suite en Python (UTP, 1IL143)  
**Entregable:** `RuleEditor` (`esb_rules.py`)  
**Alcance:** crear, modificar, validar, eliminar y guardar reglas de `conocimiento_dominio.json` sin ejecutar inferencias.

## 1. Archivos entregados

```text
grupo_02_rules/
├── __init__.py
├── esb_rules.py                  # Clase RuleEditor, lógica y persistencia
├── esb_rules_cli.py              # Menú interactivo opcional de prueba
├── README.md                     # Este documento
├── PENDIENTES_INTEGRACION.md     # Acuerdos y límites de la integración
├── datos_ejemplo/
│   └── conocimiento_dominio.json # Datos de demostración (basados en G1)
└── tests/
    ├── __init__.py
    ├── test_esb_rules.py         # Pruebas unitarias del editor
    └── test_integracion_g1_g4.py # Integración real G1 -> G2 -> G4
```

**Importante:** toda la implementación está dentro de `grupo_02_rules/` para seguir las reglas de `CONTRIBUTING.md`. No se editaron los archivos de los demás grupos ni los esquemas de `contracts/`.

## 2. Contratos y relación con otros grupos

El editor lee el archivo `conocimiento_dominio.json` con secciones:

- `meta`: metadatos definidos por el documento.
- `attributes`: atributos administrados por el **Grupo 1** (`QuestionEditor`).
- `rules`: reglas administradas por el **Grupo 2** (`RuleEditor`).

La estructura y las restricciones son las de `contracts/conocimiento_dominio.schema.json`, publicado en el ZIP revisado y validado mediante `SchemaManager` (**Grupo 4**).

Cada regla contiene `id`, `description`, `priority`, `conditions`, `conclusion` y `explanation_template`. Cada condición es `{ "attribute_id": "...", "operator": "...", "value": ... }`. Las condiciones de una misma regla se combinan mediante **AND**. Se admiten los operadores `==`, `!=`, `>`, `<`, `>=`, `<=` e **`in`**. Para `in`, el valor debe ser una lista no vacía y sus elementos deben respetar el tipo del atributo; los operadores de orden solo se aplican a atributos numéricos.

La prioridad es un entero; **su resolución efectiva durante la inferencia corresponde a los Grupos 5/6**. El editor conserva el número indicado pero no ejecuta reglas ni resuelve empates.

La implementación acepta conclusiones sobre atributos derivados no declarados, con una advertencia (el esquema actual del G4 permite ese caso). Se recomienda declarar el atributo de conclusión en `attributes` si otras reglas van a consumirlo.

## 3. Requisitos

- Python **3.11+**, según `CONTRIBUTING.md`.
- `esb_rules.py` y las pruebas unitarias básicas usan solo la biblioteca estándar.
- Para validar el documento completo con el módulo real del Grupo 4, instalar `jsonschema`.

Desde la **raíz del repositorio**:

```bash
python -m pip install jsonschema pytest
```

## 4. Ejecución por consola

Desde la raíz, ejecutar el menú del Grupo 2:

```bash
python -m grupo_02_rules.esb_rules_cli --archivo grupo_02_rules/datos_ejemplo/conocimiento_dominio.json
```

El menú permite **listar, crear, editar, eliminar, validar, guardar y recargar** reglas. La edición cubre descripción, prioridad, condiciones, conclusión y explicación. Para valores del operador `in`, introducir un arreglo JSON, por ejemplo:

```json
["Electiva", "Obligatoria"]
```

Los cambios no se guardan automáticamente: elegir la opción **6) Guardar reglas**. La opción **7) Recargar** descarta las ediciones no guardadas.

Para trabajar sobre otro archivo, cambiar `--archivo` a una copia de su `conocimiento_dominio.json`. **No usar el archivo original del Grupo 1 como archivo de pruebas**, salvo que el equipo lo haya acordado: primero crear una copia.

El CLI conecta `SchemaManager` del Grupo 4 en el guardado. Puede ejecutarse temporalmente con `--sin-schema` si se necesita aislar la validación del editor durante desarrollo, pero **no utilizar esta opción como evidencia final de integración**.

## 5. Uso desde Python

```python
from grupo_02_rules.esb_rules import RuleEditor
from grupo_04_schema.esb_schema import SchemaManager

editor = RuleEditor(
    "grupo_02_rules/datos_ejemplo/conocimiento_dominio.json",
    schema_manager=SchemaManager(),
)

nueva_regla = {
    "id": "regla_materias_comunes",
    "description": "Admite una materia electiva u obligatoria",
    "priority": 20,
    "conditions": [
        {
            "attribute_id": "materia",
            "operator": "in",
            "value": ["Electiva", "Obligatoria"],
        }
    ],
    "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
    "explanation_template": "La materia está permitida por esta regla.",
}

editor.create_rule(nueva_regla)               # Agrega EN MEMORIA
editor.set_priority("regla_materias_comunes", 30)
print(editor.validate_rules())                 # {'valido': True, ...}
editor.save_rules()                           # Persiste solo la sección rules
```

> **Nota:** el ejemplo anterior modifica `datos_ejemplo/conocimiento_dominio.json` cuando se ejecuta. Para repetir la demostración sin alterar el ejemplo, trabajar sobre una copia temporal.

### API pública disponible

| Método | Función |
|---|---|
| `RuleEditor(json_path, schema_manager=None)` | Abre un documento existente. Acepta el validador G4 como dependencia opcional. |
| `create_rule(rule)` / `add_rule(rule)` | Agrega una regla válida (diccionario). |
| `edit_rule(rule_id, changes)` | Modifica los campos de una regla; el identificador no cambia. |
| `set_priority(rule_id, priority)` | Modifica la prioridad de una regla. |
| `delete_rule(rule_id)` | Elimina una regla en memoria. |
| `get_rule(rule_id)` | Obtiene copia independiente de una regla. |
| `list_rules()` | Devuelve copia de todas las reglas. |
| `validate_rule(rule)` | Devuelve `valido`, `errores` y `advertencias` para una regla. |
| `validate_rules()` | Comprueba el conjunto actual de reglas sin guardar. |
| `save_rules()` | Valida y guarda únicamente `rules` en el JSON. |
| `load_rules()` | Relee el JSON y descarta ediciones sin guardar. |

Las operaciones reportan problemas mediante `RuleEditorError`; la búsqueda de un ID inexistente puede lanzar `KeyError`. Las **firmas todavía deben ser ratificadas** por los coordinadores del proyecto.

### Protección de cambios de los otros grupos

1. Al abrir, se leen `meta`, `attributes` y `rules`.
2. Las operaciones del G2 cambian únicamente `rules` en memoria.
3. Al guardar, se vuelve a leer el archivo y se preservan los `meta` y `attributes` **más recientes**.
4. Si otro equipo cambió las reglas en disco, se interrumpe el guardado y se solicita recargar para evitar sobrescribirlas.
5. Las reglas se revalidan con los atributos vigentes; si falla `SchemaManager`, no se reemplaza el archivo.
6. El guardado crea un archivo temporal y utiliza reemplazo atómico para reducir el riesgo de escritura parcial (no es un sistema de bloqueo entre procesos).

## 6. Pruebas

Desde la raíz del repositorio:

```bash
python -m unittest discover -s grupo_02_rules/tests -v
```

O con `pytest`:

```bash
python -m pytest grupo_02_rules/tests -q
```

Las pruebas cubren operaciones normales, duplicados, valores inválidos, condiciones numéricas, categóricas, booleanas y de texto, operadores `in`, cambios externos al JSON, escritura sin destruir otras secciones, validación real del Grupo 4 y uso real de `QuestionEditor` del Grupo 1.

Las pruebas de integración no ejecutan un motor de inferencia: **validan el intercambio entre editores y validador**.

## 7. Qué debe acordarse antes de la entrega final

Ver [PENDIENTES_INTEGRACION.md](PENDIENTES_INTEGRACION.md). Los principales puntos son la ratificación de las firmas del G2 y la conexión con motores de inferencia y auditoría. El contrato real del ZIP ya reconoce `in` y la validación G4 comprueba su estructura.
