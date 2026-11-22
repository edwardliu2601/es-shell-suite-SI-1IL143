# Pruebas de integración end-to-end

Esta carpeta contiene pruebas que validan que los módulos de **varios grupos** funcionan correctamente juntos. A diferencia de las pruebas unitarias de cada grupo (en `grupo_XX_*/tests/`), las de aquí **cruzan fronteras** entre módulos.

## Objetivo

Evitar regresiones cuando un grupo hace un cambio que, aunque pasa sus propias pruebas, rompe la integración con otros módulos.

## Escenario obligatorio (sección 6 de la guía)

El archivo `test_escenario_obligatorio.py` reproduce el escenario de demostración que exige el PDF del profesor:

1. Cargar la base de conocimiento desde `conocimiento_dominio.json`.
2. Iniciar una consulta y registrar los hechos en la memoria de trabajo.
3. Activar las reglas y generar al menos un hecho derivado.
4. Mostrar la traza de las reglas aplicadas.
5. Responder una pregunta HOW y una pregunta WHY.
6. Presentar el dictamen final.

Se usa el ejemplo mínimo de la sección 4.2 de la guía: regla de elegibilidad para trabajo de graduación.

## Correr las pruebas

Desde la raíz del repositorio:

```bash
python -m pytest integration -v
```

## Módulos que ejercita

- **G1** `QuestionEditor`: definición de atributos.
- **G4** `SchemaManager`: validación de contratos JSON.
- **G5** `ForwardEngine`: encadenamiento hacia adelante.
- **G8** `XAIExplainer`: explicaciones HOW/WHY.

Cuando se integren G6 (backward), G7 (incertidumbre), G9 (reportes), G10 (interfaz), G11 (storage) y G12 (API), se irán agregando pruebas E2E que los ejerciten juntos.

## Añadir nuevas pruebas

Cualquier coordinador puede agregar pruebas aquí. Convención:

- Un archivo por escenario: `test_<escenario>.py`.
- Nombres de función descriptivos en español: `test_consulta_completa_con_certeza()`, `test_la_api_rechaza_contrato_invalido()`.
- Usar las APIs públicas de cada grupo, no detalles internos.
