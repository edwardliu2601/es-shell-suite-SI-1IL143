# Grupo 10 · Interfaz de consulta

Archivo `esb_ui.py`, clase `ESB_Interactive_UI`. Coordinador: @acubilla18.

Consola interactiva para el **usuario final**. Permite elegir una base de conocimiento, responder solo las preguntas relevantes (una a la vez), pedir en cualquier momento **por qué** se solicita un dato y recibir el dictamen con la traza de reglas y las explicaciones HOW/WHY. Al terminar, se pueden guardar `memoria_trabajo.json` y `dictamen_salida.json` y exportar un reporte en Markdown o HTML.

La interfaz **no razona por su cuenta**: solo pregunta, convierte la respuesta al tipo del atributo y muestra resultados. La lógica la hace `ServicioESB` del Grupo 12, que usa a su vez a G4, G5, G8 y G9. Así se cumple la regla de separar la lógica de negocio de la interfaz.

## Instalación y ejecución

Desde la raíz del repositorio, con Python 3.11 o superior:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r grupo_10_ui/requirements.txt
python -m grupo_10_ui
```

Para empezar con una base propia: `python -m grupo_10_ui --kb ruta/conocimiento_dominio.json`.

## Cómo se usa

```
Bases de conocimiento
 1  kb_academico   Consulta académica: calificaciones y repetición de asignaturas
 2  kb_ejemplo     Sistema Experto de Evaluacion Academica UTP
 a  Cargar una base desde un archivo JSON
 s  Salir
Elija una opción: 1

¿Qué desea consultar?
  1) Calificacion
  2) Repeticion
> 1
¿Cuál fue el puntaje final de la asignatura (de 0 a 100)?
> por qué
  WHY: Se solicitó 'puntaje_final' para evaluar la condición de la regla reg_calificacion_a …
> 150
  Respuesta no válida.
   - $.facts.puntaje_final: El valor 150 está fuera del rango [0, 100].
> 95
```

Después se muestran la memoria de trabajo (hechos ingresados y derivados), la traza de reglas, el dictamen con su certeza y las explicaciones HOW y WHY, y un menú para guardar o exportar.

| Comando en una pregunta | Efecto |
|---|---|
| número de opción o el texto de la opción | Responde (sin importar mayúsculas ni tildes) |
| `por qué`, `porque`, `why` o `?` | Muestra el WHY del dato que se pide |
| `salir` | Termina la consulta |

Los archivos exportados quedan en `grupo_10_ui/resultados/<session_id>/`, una carpeta que Git ignora.

## Uso programático

```python
from grupo_10_ui import ESB_Interactive_UI

ui = ESB_Interactive_UI()
r = ui.consultar("kb_academico", {"tipo_consulta": "Calificacion", "puntaje_final": 95})
r["dictamen"]["final_outcome"]   # 'Calificación A - Sobresaliente'
r["traza"]                       # ["Paso 1: reg_calificacion_a agregó dictamen = ..."]
ui.guardar_json(r)               # memoria_trabajo.json y dictamen_salida.json
ui.exportar_reporte(r, "md")     # reporte.md
```

`consultar` devuelve `{"session_id", "memoria", "traza", "dictamen"}`. `dictamen` es `None` cuando ninguna regla se activa.

## Métodos públicos

| Método | Qué hace |
|---|---|
| `ejecutar()` | Bucle interactivo completo |
| `elegir_base()` | Menú de bases; devuelve el `kb_id` o `None` |
| `cargar_base(ruta)` | Lee un `conocimiento_dominio.json` y lo valida con G4 |
| `consulta_interactiva(kb_id)` | Hace las preguntas necesarias e infiere |
| `consultar(kb_id, respuestas)` | Consulta sin teclado |
| `mostrar_resultado(resultado)` | Memoria, traza, dictamen, HOW y WHY |
| `guardar_json(resultado)` | Escribe los contratos de memoria y dictamen |
| `exportar_reporte(resultado, "md" \| "html")` | Escribe el reporte |

## Dependencias con otros grupos

| Grupo | Qué usa G10 |
|---|---|
| G12 | `ServicioESB`: `siguiente_pregunta`, `registrar_hechos`, `inferir`, `obtener_dictamen`, `obtener_traza`, `generar_reporte`, `cargar_conocimiento` |
| G4 | Validación de bases, hechos y de los JSON exportados (vía G12) |
| G5 | Motor hacia adelante (vía G12) |
| G8 | WHY de cada pregunta, HOW, WHY y traza del dictamen (vía G12) |
| G9 | Reporte en Markdown cuando está integrado; si no, G12 genera uno propio |

Al iniciar, la consola muestra qué módulos se usan de verdad (`real`) y cuáles tienen un respaldo (`simulado`). Cuando G6, G7, G9 y G11 se integren en G12, la interfaz los usará sin cambios.

## Pruebas

```bash
python -m pytest grupo_10_ui -v
```

Las respuestas del usuario se simulan con una lista y se revisa lo que muestra la consola. Cubren:

- **Caso documentado:** `tipo_consulta = Calificacion`, `puntaje_final = 95` → "Calificación A - Sobresaliente" por `reg_calificacion_a`.
- **Consulta interactiva completa:** WHY, dato fuera de rango, texto en un campo numérico y dictamen final.
- Repetición con nota D; solo se pregunta lo necesario (con "Repeticion" no se pide el puntaje).
- **Datos inválidos:** opción inexistente, formatos incorrectos, base que no cumple el contrato, archivo inexistente o JSON roto.
- **Reglas que no se activan:** aviso "Sin dictamen" sin error y sin ofrecer el reporte.
- **Reglas en conflicto:** gana la de mayor prioridad.
- Salir a mitad de la consulta o cerrar la entrada (Ctrl+D) termina sin error.
- Los JSON exportados cumplen los contratos según el `SchemaManager` de G4; el reporte se exporta en Markdown y HTML.
