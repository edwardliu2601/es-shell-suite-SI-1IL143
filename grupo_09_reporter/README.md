# Grupo 9 · Generador de reportes y dictámenes

Archivo `esb_reporter.py`, clase `ReportGenerator`. Coordinador: Brayant Chirú.

Este módulo toma el resultado de una consulta del sistema experto y lo convierte en un informe en Markdown: conclusión, datos ingresados, hechos derivados, reglas aplicadas, explicación HOW y explicación WHY. No ejecuta reglas, solo reporta lo que dejaron los otros módulos.

## Uso

```python
from grupo_09_reporter import ReportGenerator

gen = ReportGenerator(
    ruta_conocimiento="conocimiento_dominio.json",
    ruta_memoria="memoria_trabajo.json",
    ruta_dictamen="dictamen_salida.json",
)
print(gen.generar_markdown())
gen.guardar_reporte("informe.md")
```

Solo `dictamen_salida.json` es obligatorio. Si faltan los otros dos, el informe omite esas secciones. Los campos opcionales (`certainty_score`, `certainty_factor`, `timestamp`) no hacen fallar el módulo cuando no vienen.

## API pública

| Método | Devuelve |
|---|---|
| `ReportGenerator(ruta_conocimiento, ruta_memoria, ruta_dictamen)` | instancia con las rutas de los tres JSON |
| `cargar_json(ruta)` | `dict` con el contenido; lanza `FileNotFoundError` o `ValueError` |
| `generar_markdown()` | `str` con el informe completo |
| `guardar_reporte(ruta_salida)` | `Path` del archivo guardado |

## Dependencias con otros grupos

Lee los contratos JSON de la sección 4.2 de la guía. Usa `explanation_how` y `explanation_why` tal como los produce el explicador del Grupo 8, y la traza que dejan los motores (G5, G6, G7). Si el `session_id` no coincide entre archivos, o una regla de la traza no existe en la base de conocimiento, el informe agrega una sección de advertencias.

## Pruebas

Desde la raíz del repositorio:

```bash
python -m pytest grupo_09_reporter
```

Cubren el caso normal, campos opcionales ausentes, archivos inexistentes o inválidos, consultas sin reglas activadas y advertencias por datos inconsistentes. Requiere Python 3.11 o superior y `pytest`.
