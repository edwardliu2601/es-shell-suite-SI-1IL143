# ES-Shell Suite

Proyecto Integrado de Clase — Shell experto modular en Python.
Universidad Tecnológica de Panamá, FISC, grupo 1IL143.

## Arquitectura

12 módulos independientes que se integran mediante contratos JSON.
Ver `docs/arquitectura.md` para el detalle.

## Grupos

| Grupo | Módulo | Carpeta |
|-------|--------|---------|
| 1 | Editor de preguntas y atributos | `grupo_01_questions/` |
| 2 | Editor de reglas IF-THEN | `grupo_02_rules/` |
| 3 | Auditor de base de conocimiento | `grupo_03_auditor/` |
| 4 | Esquema y estructura del dominio | `grupo_04_schema/` |
| 5 | Motor - Encadenamiento adelante | `grupo_05_forward/` |
| 6 | Motor - Encadenamiento atrás | `grupo_06_backward/` |
| 7 | Motor - Incertidumbre | `grupo_07_uncertainty/` |
| 8 | Explicador XAI HOW/WHY | `grupo_08_explainer/` |
| 9 | Generador de reportes | `grupo_09_reporter/` |
| 10 | Interfaz de consulta | `grupo_10_ui/` |
| 11 | Persistencia y compatibilidad | `grupo_11_storage/` |
| 12 | API REST (FastAPI) | `grupo_12_api/` |

## Contratos JSON

Los contratos viven en `contracts/`. **No se modifican unilateralmente** —
cualquier cambio requiere acuerdo de los 12 coordinadores.

## Cómo contribuir

Ver `CONTRIBUTING.md`.
