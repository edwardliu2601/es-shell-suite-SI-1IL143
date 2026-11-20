# Grupo 5 — Motor de encadenamiento hacia adelante

Librería modular `ForwardEngine` para el shell experto ES-Shell Suite.
Implementa razonamiento *forward chaining* sobre reglas SI-ENTONCES
usando los contratos JSON acordados por la clase.

## Estructura

```
grupo_05_forward/
  __init__.py       # API pública
  engine.py         # ForwardEngine
  models.py         # Rule, WorkingMemory, InferenceResult, …
  operators.py      # Evaluación de == != > < >= <= in
  agenda.py         # Resolución de conflictos por prioridad
  io.py             # Carga/guardado de JSON
  exceptions.py
  tests/
    fixtures/
    test_*.py
```

## Uso rápido

```python
from grupo_05_forward import (
    ForwardEngine,
    load_knowledge_base,
    load_working_memory,
    save_working_memory,
)

kb = load_knowledge_base("contracts/conocimiento_dominio.json")
memory = load_working_memory("contracts/memoria_trabajo.json")

engine = ForwardEngine(kb)
result = engine.run(memory)

save_working_memory("contracts/memoria_trabajo.json", result.working_memory)
print(result.fired_rules, result.halted_reason)
```

## Política del motor

1. Una regla se activa solo si **todas** sus condiciones se cumplen con hechos
   ingresados o derivados.
2. Ante varias reglas activables, gana la de **mayor `priority`**
   (empate: `id` lexicográfico).
3. No se sobrescribe un hecho ya presente (primera aserción gana).
4. Cada disparo se registra en `derived_facts` y `execution_trace`.
5. Termina por quiescencia o por `max_steps`.

## Pruebas

Desde la raíz del repositorio:

```bash
PYTHONPATH=. pytest grupo_05_forward/tests -q
```
