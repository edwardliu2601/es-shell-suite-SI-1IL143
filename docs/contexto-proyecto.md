# Contexto del proyecto (para apoyo con IA)

Este archivo resume el proyecto para que puedas pegárselo a una IA
(ChatGPT, Claude, Copilot) cuando te trabes. Copia desde `## Proyecto`
hasta el final y pégalo antes de tu pregunta.

## Proyecto

- **Nombre:** ES-Shell Suite
- **Universidad:** Universidad Tecnológica de Panamá (UTP), FISC
- **Curso:** grupo 1IL143, 8vo semestre
- **Repo central:** https://github.com/edwardliu2601/es-shell-suite-SI-1IL143
- **Lenguaje:** Python 3.11+
- **Pruebas:** pytest

## Qué es

Sistema experto modular basado en conocimiento. Entre los 12 grupos
de la clase (36 estudiantes) construimos un entorno completo donde
un experto del dominio puede:

1. Cargar una base de conocimiento (reglas SI-ENTONCES y atributos).
2. Hacer consultas que activan razonamiento automático.
3. Obtener dictámenes con explicaciones HOW/WHY.

## Arquitectura

**Categoría 1 — Componentes del shell (motor):**

- Grupo 5: encadenamiento hacia adelante (ForwardEngine).
- Grupo 6: encadenamiento hacia atrás (BackwardEngine).
- Grupo 7: factores de certeza (UncertaintyEngine).
- Grupo 8: explicador XAI HOW/WHY (XAIExplainer).
- Grupo 9: generador de reportes (ReportGenerator).
- Grupo 10: interfaz de usuario, consola o web (ESB_Interactive_UI).
- Grupo 12: API REST con FastAPI (esb_api.py).

**Categoría 2 — Componentes del experto:**

- Grupo 1: editor de preguntas y atributos (QuestionEditor).
- Grupo 2: editor de reglas IF-THEN y prioridades (RuleEditor).
- Grupo 3: auditor de base de conocimiento (KBAuditor).
- Grupo 4: esquema y validación JSON (SchemaManager).
- Grupo 11: persistencia y compatibilidad (ESBConverter).

**Categoría 3 — Memoria de trabajo:**

Administrada dinámicamente por los motores (grupos 5, 6, 7)
y la interfaz (grupo 10). Mantiene hechos ingresados, hechos
derivados, reglas que los produjeron y traza de ejecución.

## Contratos JSON (acordados por toda la clase)

Tres archivos comunes que todos los módulos consumen o producen:

- `conocimiento_dominio.json`: atributos, reglas, condiciones,
  conclusiones, prioridades, plantillas de explicación.
- `memoria_trabajo.json`: hechos ingresados, hechos derivados,
  reglas que dispararon, traza de ejecución.
- `dictamen_salida.json`: resultado final, nivel de certeza,
  explicaciones HOW/WHY.

## Ejemplo mínimo de regla

```json
{
  "id": "rule_01",
  "description": "Elegibilidad para un trámite",
  "priority": 10,
  "conditions": [
    {"attribute_id": "materia", "operator": "==", "value": "Trabajo de Graduacion"},
    {"attribute_id": "promedio", "operator": ">=", "value": 2.0}
  ],
  "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
  "explanation_template": "El promedio cumple el mínimo requerido."
}
```

## Flujo de trabajo en Git

**Ramas:**

- `main`: rama estable, solo integraciones finales.
- `develop`: integración continua de todos los grupos.
- `grupo-XX`: rama viva de cada grupo.
- `grupo-XX/descripcion`: ramas de trabajo específico.

**Protección:** `main` y `develop` requieren Pull Request con
1 aprobación. Nadie hace push directo.

**Integrantes del grupo (no coordinador):**
Trabajan en un fork personal → abren PR hacia la rama `grupo-XX`
del repo central → el coordinador aprueba y mergea.

**Coordinador del grupo:**
Trabaja en una rama del repo central → abre PR hacia `develop` →
otro coordinador revisa.

## Hitos

- **Semana 10:** congelamiento de contratos JSON.
- **Semana 11:** stubs ejecutables por grupo.
- **Semana 13:** Sprint 1 (modular) + Sprint 2 (integración de bloques).
- **Semana 14:** demo end-to-end.
- **Semana 15:** defensa pública.

## Reglas importantes

- Solo Python para la lógica central.
- Separar lógica de negocio de interfaz de usuario.
- Pruebas unitarias para casos normales, datos inválidos y reglas
  que no se activan o entran en conflicto.
- No usar datos personales reales.
- Nombres de archivos, campos y contratos JSON no se cambian
  unilateralmente — requiere acuerdo de los 12 coordinadores.
