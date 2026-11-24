# Grupo 3 — Auditor de Base de Conocimiento (`KBAuditor`)

**Proyecto:** ES-Shell Suite en Python (UTP, FISC, 1IL143)  
**Entregable:** `KBAuditor` (`esb_auditor.py`) y CLI (`esb_auditor_cli.py`)  
**Categoría del shell:** 2 — Componente del experto (verificación estática y tablas de decisión).

Este módulo audita archivos `conocimiento_dominio.json` alineados al contrato oficial en `contracts/conocimiento_dominio.schema.json` sin ejecutar inferencias ni modificar el archivo analizado.

## 1. Estructura del módulo

```text
grupo_03_auditor/
├── __init__.py
├── esb_auditor.py                  # Lógica central pura: KBAuditor, Hallazgo, ReporteAuditoria
├── esb_auditor_cli.py              # Interfaz de línea de comandos para auditar y exportar
├── README.md                       # Documentación de uso, API y ejemplos
├── datos_ejemplo/
│   ├── conocimiento_valido.json        # Base de conocimiento limpia (0 errores, 0 advertencias)
│   ├── conocimiento_con_errores.json   # Contradicciones, duplicados, subsunción y reglas muertas
│   └── conocimiento_con_ciclos.json    # Ciclos directos/indirectos en reglas y en depends_on
└── tests/
    ├── __init__.py
    ├── test_auditor.py             # Pruebas unitarias y de compatibilidad con G1, G2 y G4
    └── test_cli.py                 # Pruebas de la interfaz de consola
```

## 2. Capacidades de auditoría

1. **Carga y validación inicial segura:**
   - Acepta un `dict` en memoria o una ruta (`str` / `Path`) a `conocimiento_dominio.json`.
   - Rechaza constantes no estándar (`NaN`, `Infinity`) y maneja archivos faltantes, JSON malformados o estructuras incompletas devolviendo hallazgos estructurados (`esquema_invalido`) sin lanzar excepciones no controladas.
   - Integración opcional automática con `SchemaManager` (**Grupo 4**) y fallback estructural independiente cuando se ejecuta de forma aislada (`usar_schema_manager=False` o `--sin-schema`).
2. **Detección de reglas contradictorias (`contradiccion`):**
   - Evalúa compatibilidad lógica exacta sobre intervalos numéricos (`>`, `>=`, `<`, `<=`), igualdades/desigualdades (`==`, `!=`) y conjuntos (`in`) considerando los dominios declarados (`range`, `options`, `boolean`).
   - Marca como `ERROR` los conflictos con **igual prioridad** (ambigüedad irresoluble) y como `WARNING` los conflictos desempatados por **prioridad distinta**.
3. **Detección de redundancias y subsunción (`redundancia`):**
   - Detecta reglas **duplicadas** (condiciones lógicamente equivalentes y misma conclusión).
   - Detecta reglas **subsumidas** (una regla general cubre todos los casos de otra más específica con igual conclusión).
4. **Detección de condiciones inalcanzables y reglas muertas (`condicion_inalcanzable`):**
   - Contradicciones internas dentro de una regla (ej. `promedio >= 2.5` y `promedio < 2.0`, o `in` con lista vacía).
   - Valores fuera de `range` (atributos `numeric`) o fuera de `options` (atributos `categorical`, soportando tanto strings como objetos `{"value", "label"}`).
   - Referencias a `attribute_id` inexistentes (no declarados en `attributes` ni derivados por otra regla).
   - Atributos usados en condiciones sin `question` y sin regla que los concluya (hechos imposibles de obtener).
   - Validación de `depends_on` (atributos inexistentes, valores imposibles y dependencias sin fuente).
5. **Detección de ciclos (`ciclo`):**
   - Construye el grafo bipartito dirigido `atributo -> [regla] -> atributo` y detecta ciclos directos (1 regla) e indirectos (2, 3+ reglas) usando componentes fuertemente conexas (Tarjan) y búsqueda de ciclos elementales.
   - Detecta ciclos directos e indirectos en `depends_on`.
6. **Generador de Tablas de Decisión y reportes:**
   - Construye la tabla de decisión estructurada resaltando reglas en conflicto, redundantes, inalcanzables o en ciclo.
   - Exporta reportes completos a `dict`, **JSON** y **Markdown**, y la tabla de decisión a **Markdown** o texto alineado para consola.

## 3. Requisitos e instalación

- **Python 3.11+** (la lógica central usa solo la biblioteca estándar).
- Opcional para validación con `SchemaManager` (Grupo 4) y pruebas:

```bash
python -m pip install jsonschema pytest
```

## 4. Uso desde línea de comandos (CLI)

Ejecutar desde la **raíz del repositorio**:

```bash
# Auditar una base de conocimiento y mostrar la tabla de decisión
python -m grupo_03_auditor.esb_auditor_cli grupo_03_auditor/datos_ejemplo/conocimiento_valido.json --tabla-decision

# Auditar una base con errores y exportar reporte en JSON y Markdown
python -m grupo_03_auditor.esb_auditor_cli grupo_03_auditor/datos_ejemplo/conocimiento_con_errores.json --tabla-decision --output-json reporte.json --output-md reporte.md

# Auditar el ejemplo oficial del Grupo 4
python -m grupo_03_auditor.esb_auditor_cli grupo_04_schema/ejemplos/conocimiento_dominio.json --tabla-decision

# Modo aislado (sin invocar SchemaManager) y modo estricto (falla también con WARNING)
python -m grupo_03_auditor.esb_auditor_cli ruta/conocimiento.json --sin-schema --estricto
```

### Códigos de salida

- `0`: La base de conocimiento no contiene errores críticos (`ERROR = 0`).
- `1`: Se detectaron uno o más `ERROR` (o `WARNING` si se especifica `--estricto`).
- `2`: Error de argumentos en la línea de comandos.

## 5. Uso desde Python (API)

```python
from grupo_03_auditor import KBAuditor

# Desde archivo JSON
auditor = KBAuditor("grupo_03_auditor/datos_ejemplo/conocimiento_valido.json")
reporte = auditor.auditar()

print(reporte.es_valida)                  # True
print(reporte.estado)                     # "VALIDA"
print(reporte.resumen)                    # Conteos de atributos, reglas y severidades

# Exportar reporte completo
reporte_dict = reporte.to_dict()          # dict serializable a JSON
json_texto = auditor.exportar_json()      # str JSON (o pasa una ruta para guardar)
md_texto = auditor.exportar_markdown()    # str Markdown (o pasa una ruta para guardar)

# Tabla de decisión en consola o Markdown
print(auditor.exportar_tabla_decision_consola())
print(auditor.exportar_tabla_decision_markdown())

# También se puede auditar directamente un diccionario Python
datos = {"meta": {...}, "attributes": [...], "rules": [...]}
reporte_dic = KBAuditor.desde_dict(datos).generar_reporte()
```

### Métodos principales de `KBAuditor`

| Método | Descripción |
|---|---|
| `KBAuditor(fuente=None, *, schema_manager=None, usar_schema_manager=True)` | Inicializa el auditor desde un `dict`, ruta JSON o vacío. |
| `auditar(fuente=None) -> ReporteAuditoria` | Ejecuta todas las comprobaciones y devuelve el reporte estructurado. |
| `generar_reporte(fuente=None) -> dict` | Devuelve el reporte completo como diccionario serializable a JSON. |
| `validar_esquema() -> list[Hallazgo]` | Ejecuta `SchemaManager` (si está disponible) o la validación estructural interna. |
| `detectar_contradicciones() -> list[Hallazgo]` | Encuentra pares de reglas con condiciones solapables/equivalentes y conclusión distinta. |
| `detectar_redundancias() -> list[Hallazgo]` | Encuentra reglas duplicadas y subsumidas. |
| `detectar_condiciones_inalcanzables() -> list[Hallazgo]` | Detecta contradicciones internas, rangos/opciones inválidas, atributos huérfanos y `depends_on` rotos. |
| `detectar_ciclos() -> list[Hallazgo]` | Detecta ciclos directos e indirectos en reglas y en `depends_on`. |
| `generar_tabla_decision() -> dict` | Construye la tabla de decisión con alertas de conflicto, redundancia, inalcanzabilidad o ciclo. |
| `exportar_json(ruta=None) -> str` | Serializa el reporte a JSON y opcionalmente lo guarda en disco. |
| `exportar_markdown(ruta=None) -> str` | Serializa el reporte a Markdown y opcionalmente lo guarda en disco. |
| `exportar_tabla_decision_markdown()` / `exportar_tabla_decision_consola()` | Renderiza la tabla de decisión en Markdown o texto alineado para consola. |

## 6. Ejecución de pruebas

Desde la raíz del repositorio:

```bash
python -m pytest grupo_03_auditor/tests -v
```
