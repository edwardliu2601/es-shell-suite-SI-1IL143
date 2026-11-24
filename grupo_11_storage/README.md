# Grupo 11: Persistencia y compatibilidad

Módulo `grupo_11_storage/` de ES-Shell Suite. Su entregable es la clase
`ESBConverter` (`esb_storage.py`), que **guarda y vuelve a cargar** los JSON
comunes del proyecto sin cambiar nombres de campo ni significado.

> Estado: implementación y pruebas completas dentro del alcance base
> (conocimiento y sesiones). Las firmas son la orientación del enunciado y
> siguen **pendientes de acuerdo** con los Grupos 4, 10 y 12 (ver
> [Pendientes por acordar](#pendientes-por-acordar)). La compatibilidad con
> formatos externos **no está definida**: solo existe el punto de enganche.

## Contenido

```
grupo_11_storage/
├── __init__.py            # exporta ESBConverter y las excepciones
├── esb_storage.py         # ESBConverter
├── ejemplos/              # JSON ficticios y consistentes entre sí
│   ├── conocimiento_ejemplo.json
│   ├── sesion_ejemplo.json
│   └── dictamen_ejemplo.json
├── tests/test_esb_storage.py
└── README.md              # este archivo
```

## Alcance

| Documento (contrato en `contracts/`) | Guardar / cargar | Estado |
|---|---|---|
| `conocimiento_dominio` | `save_knowledge` / `load_knowledge` | En alcance |
| `memoria_trabajo` (sesión) | `save_session` / `load_session` | En alcance |
| `dictamen_salida` | `save_verdict` / `load_verdict` | Propuesta: el enunciado pide confirmar si se persiste |
| Formatos externos | `import_knowledge` / `export_knowledge` | No definido; solo registro de convertidores |

El módulo **no modifica `contracts/`**. Los esquemas de `contracts/` y los de
`grupo_04_schema/schemas/` son idénticos en esta versión del repositorio.

## Decisiones de formato

- JSON en UTF-8, indentado con 2 espacios, sin escapar caracteres no ASCII
  (`ensure_ascii=False`), con salto de línea final. Se acepta BOM al leer.
- El orden de las claves y de las listas se conserva. Los campos adicionales
  que permiten los esquemas (`additionalProperties: true`) se guardan y se
  recargan sin cambios.
- Se rechaza en lugar de transformar en silencio: claves que no son texto
  (JSON las convertiría), `NaN`/`Infinity`, tipos que JSON no representa
  (`set`, `bytes`, `datetime`, objetos propios) y claves repetidas dentro de
  un objeto al leer. Las tuplas se guardan como listas (no hay pérdida).
- Escritura **atómica**: se escribe un archivo temporal en la misma carpeta y
  se reemplaza el destino. Si algo falla no queda un archivo a medias y la
  versión anterior sigue intacta. Guardar sobre un archivo existente lo
  sobrescribe y conserva sus permisos.
- Rutas: las elige quien usa el módulo (`str` o `Path`). Por defecto se crean
  las carpetas que falten (`create_dirs=True`).
- Sesiones por `session_id` (convención **propuesta**): archivo
  `sesion_<session_id>.json` dentro de una carpeta. El `session_id` solo puede
  tener letras, dígitos, `.`, `-` y `_` (máximo 128, sin empezar por signo),
  de modo que el nombre nunca contiene separadores de ruta.

## Validación

Se valida **antes de guardar y después de cargar**, delegando en
`SchemaManager.validar_datos` del Grupo 4 con los esquemas de `contracts/`
(la misma carpeta que usa el Grupo 12). Eso incluye las reglas semánticas de G4
para el conocimiento (ids repetidos, referencias, tipos, ciclos en `depends_on`).

- `ESBConverter(schema_manager=..., schemas_dir=..., validate=True)`: se puede
  inyectar otro `SchemaManager` o apuntar a otra carpeta de esquemas.
- Cada operación acepta `validate=True/False` para esa llamada.
- `save_session(..., knowledge=kb)` y `load_session(..., knowledge=kb)` además
  comprueban los hechos contra la base (atributo declarado, tipo, opciones y
  rango) con `SchemaManager.validar_memoria`.
- Dependencias de validación: `jsonschema` (lo usa G4). Si falta, o faltan los
  esquemas, se lanza `ValidationUnavailableError` con un mensaje claro. Con
  `validate=False` el módulo funciona solo con la biblioteca estándar.

**Borradores sin reglas.** El contrato exige al menos un atributo y una regla,
pero los borradores de G1 pueden traer `rules: []`. Para guardar un borrador:
`save_knowledge(kb, ruta, validate=False)`. Al cargarlo con validación activa
se rechazará hasta que G2 aporte reglas.

## Uso

```python
from grupo_11_storage import ESBConverter

converter = ESBConverter()

# Conocimiento
converter.save_knowledge(knowledge, "bases/elegibilidad.json")
knowledge = converter.load_knowledge("bases/elegibilidad.json")

# Sesión en una ruta elegida
converter.save_session(session, "sesiones/mi_sesion.json", knowledge=knowledge)
session = converter.load_session("sesiones/mi_sesion.json", knowledge=knowledge)

# Sesión por session_id dentro de una carpeta
converter.save_session_to_dir(session, "sesiones/")          # sesiones/sesion_<id>.json
session = converter.load_session_from_dir("sesiones/", "sess_ejemplo_001")
converter.list_sessions("sesiones/")                          # ['sess_ejemplo_001', ...]

# Dictamen (propuesta)
converter.save_verdict(verdict, "dictamenes/sess_ejemplo_001.json")
verdict = converter.load_verdict("dictamenes/sess_ejemplo_001.json")
```

Los métodos `save_*` devuelven la `Path` escrita y los `load_*` devuelven un
`dict`. Ninguno modifica el objeto recibido.

## Interfaz pública

| Método | Descripción |
|---|---|
| `save_knowledge(knowledge, path, *, validate=None)` | Guarda `conocimiento_dominio` |
| `load_knowledge(path, *, validate=None)` | Carga y valida `conocimiento_dominio` |
| `save_session(session, path, *, knowledge=None, validate=None)` | Guarda `memoria_trabajo` |
| `load_session(path, *, knowledge=None, validate=None)` | Carga y valida `memoria_trabajo` |
| `session_filename(session_id)` / `session_path(directory, session_id)` | Nombre y ruta según la convención |
| `save_session_to_dir(session, directory, *, knowledge=None, validate=None)` | Guarda nombrando por `session_id` |
| `load_session_from_dir(directory, session_id, *, knowledge=None, validate=None)` | Carga por `session_id`; verifica que el id interno coincida |
| `list_sessions(directory)` | Ids de sesión guardados (solo mira nombres de archivo) |
| `save_verdict(verdict, path, *, validate=None)` / `load_verdict(path, *, validate=None)` | Dictamen (propuesta) |
| `register_format(name, *, importer=None, exporter=None)` | Registra un formato externo |
| `registered_formats()` | Formatos externos registrados (vacío por defecto) |
| `import_knowledge(path, format, *, validate=None)` | Formato externo a JSON interno, validado |
| `export_knowledge(knowledge, path, format, *, validate=None)` | JSON interno a formato externo; valida antes de convertir |

La lectura/escritura (`_leer_json`, `_escribir_json`) está separada de la
conversión de formatos (`register_format`, `import_*`, `export_*`).

## Errores

Todos heredan de `StorageError`. Los que corresponden a un error estándar de
Python también heredan de él, así un `except FileNotFoundError` sigue sirviendo.

| Excepción | Hereda también de | Cuándo |
|---|---|---|
| `StorageFileNotFoundError` | `FileNotFoundError` | El archivo (o carpeta en `list_sessions`) no existe |
| `StorageAccessError` | `OSError` | Sin permisos, la ruta es una carpeta, no se puede crear la carpeta o escribir |
| `InvalidJSONError` | `ValueError` | JSON mal formado (con línea y columna), vacío, no UTF-8, `NaN`/`Infinity`, claves repetidas |
| `IncompatibleStructureError` | `ValueError` | Es JSON pero no cumple el contrato, la raíz no es un objeto, no es serializable, o el convertidor falló. Trae `.errores` (lista `"$.ruta: mensaje"`) |
| `UnsupportedFormatError` | `ValueError` | Se pide un formato externo sin convertidor registrado |
| `ValidationUnavailableError` | (solo `StorageError`) | No se puede validar: falta `SchemaManager`/`jsonschema` o el esquema |

Un `session_id` inadecuado para nombre de archivo lanza `ValueError`.

```python
from grupo_11_storage import IncompatibleStructureError, StorageFileNotFoundError

try:
    kb = converter.load_knowledge("bases/otra.json")
except StorageFileNotFoundError:
    ...  # no existe
except IncompatibleStructureError as error:
    print(error.errores)  # qué parte del contrato no se cumple
```

## Compatibilidad externa: no definida / pendiente

No hay ningún formato externo acordado, así que **no se implementó ninguno**.
`ESBConverter` solo ofrece el enganche, para cuando el curso lo defina:

```python
converter.register_format(
    "mi_formato",
    importer=lambda ruta: {...},          # devuelve un conocimiento_dominio (dict)
    exporter=lambda kb, ruta: ...,        # escribe el formato externo
)
kb = converter.import_knowledge("origen.ext", "mi_formato")   # validado
converter.export_knowledge(kb, "destino.ext", "mi_formato")
```

Quien escriba un convertidor debe documentar aquí qué campos transforma y qué
hace con los que no tienen correspondencia (no descartarlos en silencio). El
JSON común sigue siendo el formato interno. No se admite registrar `json`.

## Ejemplos ficticios

En `ejemplos/`: una base mínima de elegibilidad, una sesión y un dictamen
consistentes entre sí (validan con `SchemaManager.validar_conjunto`). No
contienen datos personales reales.

## Pruebas

Desde la raíz del repositorio (Python 3.11+):

```bash
pip install pytest jsonschema
python -m pytest grupo_11_storage -v
```

La suite completa y la de integración se corren igual que en el CI:

```bash
python -m pytest -v --tb=short
python -m pytest integration -v --tb=short
```

Cobertura de `tests/test_esb_storage.py`: ida y vuelta de conocimiento, sesión
y dictamen (incluidos los ejemplos de G4), campos adicionales, orden y Unicode,
archivo inexistente, JSON mal formado/vacío/no UTF-8/`NaN`/claves repetidas,
estructura incompatible al guardar y al cargar (sin escribir ni dañar la
versión anterior), permisos y rutas inválidas, sesión contra conocimiento,
validación opcional, convención de nombres de sesión y el enganche de
conversión externa con un formato ficticio de prueba.

## Pendientes por acordar

Estos puntos requieren a los otros grupos; no se resolvieron unilateralmente:

1. **Firmas** de `save_*`/`load_*` con G10 (interfaz) y G12 (API). Hoy G12
   guarda bases y sesiones en memoria (`grupo_12_api/servicio.py`) y lista a G11
   como simulado en `adaptadores.py`; se conectaría con un `_cargar_g11()`.
2. **Versión vigente del esquema de conocimiento** con G4. La descripción en
   `contracts/conocimiento_dominio.schema.json` lo marca como propuesta
   pendiente de aprobación.
3. **Nombres de archivo de sesión** (`sesion_<session_id>.json`) y si se
   persisten dictámenes.
4. **Formatos externos** de origen/destino, con un ejemplo válido de cada uno.
5. **Borradores con `rules: []`**: confirmar con G1/G2 si se guardan con
   `validate=False` o se acuerda otro mecanismo.

## Flujo de trabajo (Git)

Según `CONTRIBUTING.md`: rama `grupo-11/esb-converter`, commits en español en
imperativo, Pull Request hacia `develop` (o hacia `grupo-11` si se trabaja
desde un fork). No se hace push directo a `main` ni a `develop`.

## Lista de verificación para la entrega

- [x] `ESBConverter` guarda y carga conocimiento y sesiones conforme a los contratos vigentes en `contracts/`.
- [x] Rutas, errores y validaciones tienen un comportamiento documentado.
- [x] Conversión externa: señalada como no definida/pendiente; solo existe el enganche.
- [x] Las pruebas cubren persistencia, recarga y errores relevantes.
- [x] Documentación y ejemplos guardados en el repositorio.
- [ ] Interfaces confirmadas con G4, G10 y G12.
- [ ] Cambio entregado por Pull Request siguiendo `CONTRIBUTING.md`.
