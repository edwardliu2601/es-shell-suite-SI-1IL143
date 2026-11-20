# Grupo 2 — Observaciones y pendientes de integración

Revisión basada en el ZIP `es-shell-suite-SI-1IL143-develop.zip` compartido en esta conversación. No es una confirmación de que los coordinadores hayan ratificado las firmas ni de que se haya hecho merge de este módulo.

## Ya comprobado

- **Grupo 1:** `QuestionEditor` implementa la creación, edición, lectura y escritura de `attributes`. Sus archivos de ejemplo incluyen `depends_on` y `help_text`. Se probó que G2 agrega reglas y preserva ambos campos; también que G1 guarda atributos sin borrar reglas existentes de G2.
- **Grupo 2:** `RuleEditor` crea, edita, consulta, elimina, valida y guarda reglas. `esb_rules_cli.py` permite probar esas operaciones manualmente.
- **Grupo 4:** los contratos versionados en `contracts/` incluyen `in` con lista no vacía; la clase `SchemaManager` acepta documentos generados por el editor. Se ensayó sobre el ejemplo del Grupo 4 y sobre atributos generados con el código real del Grupo 1.
- **No se ejecutan inferencias** ni se generan dictámenes en las pruebas de integración G1–G2–G4.

## Pendiente para representantes

1. **Ratificar la API de `RuleEditor`:** constructor con ruta, operaciones `create_rule`, `edit_rule`, `delete_rule`, `set_priority`, `load_rules`, `save_rules`, validadores y tipo de errores. Está publicada en README, pero sigue siendo una propuesta implementada en esta carpeta.
2. **Prioridades:** G1 propone que un número mayor tenga preferencia. Los **Grupos 5/6** deben confirmar resolución de conflictos, empates y casos de reglas con igual prioridad. `RuleEditor` solo almacena el valor.
3. **Operador `in`:** ya se encuentra en el esquema y funciona en G2; falta la ejecución de dicho operador en los motores **G5/6** y las pruebas de inferencia.
4. **Grupo 3:** verificar que el auditor reciba correctamente reglas con `in`, prioridades y conclusiones derivadas. El ZIP revisado conserva su carpeta como marcador vacío.
5. **Grupo 1:** su ejemplo `conocimiento_dominio.sample.json` tiene `rules: []`; el esquema **G4 exige al menos una regla** (`minItems: 1`), por lo que el archivo de atributos es un borrador intermedio. G2 puede abrir ese archivo, añadir una regla y producir un documento final validable. **No borrar esa etapa transitoria sin coordinar**.
6. **Grupo 1 y Grupo 4:** en el comentario de `Attribute` del G1 se menciona que `options` puede incluir objetos `{value, label}`, pero el esquema G4 actualmente acepta **solo strings** en `options`. No usar objetos sin acordar y actualizar el contrato.
7. **Contratos y versionado:** todos los cambios futuros en `contracts/` requieren coordinación y PR, según `CONTRIBUTING.md`.
8. **Integración global:** probar con los demás grupos la secuencia completa `QuestionEditor → RuleEditor → auditor → motores → explicación → dictamen`; no se puede acreditar hasta que esos módulos estén disponibles.

## Propuesta de reparto del Grupo 2

- **Integrante A:** clase `RuleEditor`, creación/edición, condiciones, operadores y prioridades.
- **Integrante B:** persistencia JSON, validación de tipos/atributos, integración con `SchemaManager`.
- **Integrante C:** consola de demostración, pruebas, documentación, coordinación y Pull Request.

El reparto es **sugerido**: puede adaptarse a los integrantes reales. Todos deben conocer la API y sus pruebas.

## Subida al repositorio

Desde la raíz de un clon Git actualizado, siguiendo `CONTRIBUTING.md`:

```bash
git checkout develop
git pull
git checkout -b grupo-02/editor-reglas
git add grupo_02_rules/
git commit -m "Agrega editor de reglas y pruebas de integración del Grupo 2"
git push origin grupo-02/editor-reglas
```

Luego abrir el Pull Request correspondiente. **No hacer push directo a `develop` o `main` ni modificar archivos de otros grupos.**
