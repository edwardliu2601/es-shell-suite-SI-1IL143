"""Interfaz de consulta del Grupo 10 (ESB_Interactive_UI).

Consola interactiva para el perfil de usuario final: elige una base de
conocimiento, responde solo las preguntas relevantes, puede pedir en cada
pregunta el WHY ("por qué") y recibe el dictamen con su traza y sus
explicaciones HOW/WHY. Al final puede guardar memoria_trabajo.json y
dictamen_salida.json, y exportar un reporte en Markdown o HTML.

La interfaz no razona por su cuenta. Toda la logica de la consulta (que
preguntar, validar, inferir, explicar) la hace ServicioESB del Grupo 12, que a
su vez usa G4 (validacion), G5 (motor), G8 (explicaciones) y G9 (reportes).
Este modulo solo pregunta, convierte la respuesta al tipo del atributo y
muestra resultados.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from grupo_12_api.servicio import (
    KB_ACADEMICO,
    KB_EJEMPLO,
    ContratoInvalido,
    EstadoInvalido,
    ServicioESB,
)

__all__ = ["ESB_Interactive_UI", "convertir_respuesta", "CARPETA_RESULTADOS"]

CARPETA_RESULTADOS = Path(__file__).parent / "resultados"
COMANDOS_WHY = {"por que", "porque", "why", "?"}
COMANDOS_SALIR = {"salir", "cancelar", "exit"}
SI = {"si", "s", "true", "verdadero", "1"}
NO = {"no", "n", "false", "falso", "0"}


class _Cancelado(Exception):
    """El usuario escribio 'salir' o cerro la entrada (Ctrl+D / Ctrl+C)."""


def _normalizar(texto: str) -> str:
    """Minusculas, sin tildes ni espacios sobrantes: 'Por Qué ' -> 'por que'."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().replace("¿", "").split())


def _corta(ruta: Path) -> Path:
    """Ruta relativa a la carpeta actual si es posible, para mostrarla corta."""
    try:
        return ruta.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return ruta


def convertir_respuesta(texto: str, pregunta: dict) -> Any:
    """Convierte lo que escribio el usuario al tipo del atributo.

    Solo revisa el formato. El rango y las opciones validas los revisa el
    SchemaManager del Grupo 4 cuando el hecho se registra en la memoria.
    Lanza ValueError con un mensaje para el usuario si no se puede convertir.
    """
    texto = texto.strip()
    if not texto:
        raise ValueError("La respuesta está vacía.")
    tipo = pregunta["type"]

    if tipo == "numeric":
        try:
            numero = float(texto.replace(",", "."))
        except ValueError:
            raise ValueError(f"'{texto}' no es un número.") from None
        return int(numero) if numero.is_integer() else numero

    if tipo == "boolean":
        if _normalizar(texto) in SI:
            return True
        if _normalizar(texto) in NO:
            return False
        raise ValueError("Responda sí o no.")

    if tipo == "categorical":
        opciones = pregunta.get("options") or []
        if texto.isdigit() and 1 <= int(texto) <= len(opciones):
            return opciones[int(texto) - 1]
        for opcion in opciones:
            if _normalizar(opcion) == _normalizar(texto):
                return opcion
        # Sin coincidencia: se devuelve tal cual y G4 informa la opcion invalida.
        return texto

    return texto  # text


class ESB_Interactive_UI:
    """Consola de consulta del shell experto.

    Parametros:
        servicio: fachada del Grupo 12. Por defecto crea una con las bases de
            ejemplo precargadas (kb_academico y kb_ejemplo).
        entrada: funcion que devuelve lo que escribe el usuario. Por defecto
            input(); en las pruebas se reemplaza por respuestas simuladas.
        consola: consola de rich donde se escribe la salida.
        carpeta_salida: donde se guardan los JSON y reportes exportados.
    """

    def __init__(self, servicio: ServicioESB | None = None,
                 entrada: Callable[[str], str] = input,
                 consola: Console | None = None,
                 carpeta_salida: Path | str = CARPETA_RESULTADOS):
        self.servicio = servicio or ServicioESB()
        self._entrada = entrada
        self.consola = consola or Console()
        self.carpeta_salida = Path(carpeta_salida)
        self.bases: list[str] = [KB_ACADEMICO, KB_EJEMPLO]

    # ------------------------------------------------------------------
    # Uso programatico (sin teclado): seccion 6, paso 2 "o programatica"
    # ------------------------------------------------------------------

    def consultar(self, kb_id: str, respuestas: dict[str, Any]) -> dict:
        """Ejecuta una consulta completa con las respuestas dadas.

        Devuelve {"session_id", "memoria", "traza", "dictamen"}; "dictamen" es
        None si ninguna regla se activo. Lanza ContratoInvalido si las
        respuestas no son validas para la base.
        """
        sesion = self.servicio.iniciar_consulta(kb_id, "adelante", respuestas)
        return self._resolver(sesion["session_id"])

    # ------------------------------------------------------------------
    # Uso interactivo
    # ------------------------------------------------------------------

    def ejecutar(self) -> None:
        """Bucle principal: elegir base, consultar, ver resultado, repetir."""
        self._bienvenida()
        try:
            while True:
                kb_id = self.elegir_base()
                if kb_id is None:
                    break
                resultado = self.consulta_interactiva(kb_id)
                self.mostrar_resultado(resultado)
                if not self._menu_final(resultado):
                    break
        except _Cancelado:
            pass
        self.consola.print("\nHasta luego.")

    def elegir_base(self) -> str | None:
        """Muestra las bases disponibles y devuelve el kb_id elegido."""
        while True:
            tabla = Table(title="Bases de conocimiento", show_header=False, box=None)
            for i, kb_id in enumerate(self.bases, start=1):
                titulo = self.servicio.obtener_conocimiento(kb_id)["meta"].get("project_title", "")
                tabla.add_row(f"[bold]{i}[/]", kb_id, titulo)
            tabla.add_row("[bold]a[/]", "Cargar una base desde un archivo JSON", "")
            tabla.add_row("[bold]s[/]", "Salir", "")
            self.consola.print(tabla)

            opcion = _normalizar(self._leer("Elija una opción:"))
            if opcion in {"s", *COMANDOS_SALIR}:
                return None
            if opcion == "a":
                kb_id = self.cargar_base(self._leer("Ruta del archivo conocimiento_dominio.json:"))
                if kb_id:
                    return kb_id
                continue
            if opcion.isdigit() and 1 <= int(opcion) <= len(self.bases):
                return self.bases[int(opcion) - 1]
            self.consola.print("[red]Opción no válida.[/]")

    def cargar_base(self, ruta: str) -> str | None:
        """Lee y valida una base de conocimiento (G4). Devuelve su kb_id o None."""
        try:
            with open(Path(ruta.strip()).expanduser(), encoding="utf-8") as f:
                base = json.load(f)
            kb_id, _ = self.servicio.cargar_conocimiento(base)
        except OSError as exc:
            self.consola.print(f"[red]No se pudo abrir el archivo:[/] {exc}")
            return None
        except json.JSONDecodeError as exc:
            self.consola.print(f"[red]El archivo no es un JSON válido:[/] {exc}")
            return None
        except ContratoInvalido as exc:
            self._mostrar_errores(str(exc), exc.errores)
            return None
        self.bases.append(kb_id)
        self.consola.print(f"[green]Base cargada como {kb_id}.[/]")
        return kb_id

    def consulta_interactiva(self, kb_id: str) -> dict:
        """Pregunta solo lo necesario, una cosa a la vez, y luego infiere."""
        base = self.servicio.obtener_conocimiento(kb_id)
        self.consola.rule(f"Consulta · {base['meta'].get('project_title', kb_id)}")
        self.consola.print("[dim]Escriba 'por qué' para saber por qué se pide un dato, "
                           "o 'salir' para terminar.[/]")
        session_id = self.servicio.iniciar_consulta(kb_id, "adelante", {})["session_id"]

        while True:
            siguiente = self.servicio.siguiente_pregunta(session_id)
            if siguiente["completa"]:
                break
            self._preguntar(session_id, siguiente["pregunta"], siguiente["explanation_why"])

        return self._resolver(session_id)

    def mostrar_resultado(self, resultado: dict) -> None:
        """Muestra hechos, traza, dictamen y explicaciones HOW/WHY."""
        memoria = resultado["memoria"]

        hechos = Table(title="Memoria de trabajo", show_lines=False)
        hechos.add_column("Atributo")
        hechos.add_column("Valor")
        hechos.add_column("Origen")
        for attr, valor in memoria["facts"].items():
            hechos.add_row(attr, str(valor), "ingresado por el usuario")
        for attr, d in memoria["derived_facts"].items():
            hechos.add_row(attr, str(d["value"]),
                           f"derivado por {d['derived_by_rule']} (CF {d.get('certainty_factor', 1.0)})")
        self.consola.print(hechos)

        self.consola.print("[bold]Traza de reglas aplicadas[/]")
        for linea in resultado["traza"] or ["Ninguna regla se activó."]:
            self.consola.print(f"  {linea}")

        dictamen = resultado["dictamen"]
        if dictamen is None:
            self.consola.print(Panel(
                "Con los datos ingresados ninguna regla de la base llegó a una conclusión.",
                title="Sin dictamen", border_style="yellow"))
            return

        cuerpo = (f"[bold]{dictamen['final_outcome']}[/]\n"
                  f"Certeza: {dictamen['certainty_score']}\n\n"
                  "[bold]¿Cómo se llegó a esta conclusión? (HOW)[/]\n"
                  + "\n".join(f"  • {l}" for l in dictamen["explanation_how"])
                  + "\n\n[bold]¿Por qué se pidió el dato? (WHY)[/]\n"
                  f"  {dictamen['explanation_why']}")
        self.consola.print(Panel(cuerpo, title=f"Dictamen · {dictamen['session_id']}",
                                 border_style="green"))

    def guardar_json(self, resultado: dict, carpeta: Path | None = None) -> list[Path]:
        """Guarda memoria_trabajo.json y, si hay, dictamen_salida.json."""
        carpeta = Path(carpeta or self.carpeta_salida) / resultado["session_id"]
        carpeta.mkdir(parents=True, exist_ok=True)
        archivos = {"memoria_trabajo.json": resultado["memoria"]}
        if resultado["dictamen"] is not None:
            archivos["dictamen_salida.json"] = resultado["dictamen"]
        rutas = []
        for nombre, datos in archivos.items():
            ruta = carpeta / nombre
            ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
            rutas.append(ruta)
        return rutas

    def exportar_reporte(self, resultado: dict, formato: str,
                         carpeta: Path | None = None) -> Path:
        """Exporta el reporte del dictamen en 'md' o 'html' (G9 o G12)."""
        contenido = self.servicio.generar_reporte(resultado["session_id"], formato)
        carpeta = Path(carpeta or self.carpeta_salida) / resultado["session_id"]
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"reporte.{formato}"
        ruta.write_text(contenido, encoding="utf-8")
        return ruta

    # ------------------------------------------------------------------
    # internos
    # ------------------------------------------------------------------

    def _resolver(self, session_id: str) -> dict:
        """Infiere y arma el resultado; el dictamen es None si nada se activo."""
        memoria, _motivo = self.servicio.inferir(session_id) if self._hay_hechos(session_id) \
            else (self.servicio.obtener_memoria(session_id), "sin_hechos")
        try:
            dictamen = self.servicio.obtener_dictamen(session_id)
        except EstadoInvalido:
            dictamen = None
        return {"session_id": session_id, "memoria": memoria,
                "traza": self.servicio.obtener_traza(session_id), "dictamen": dictamen}

    def _hay_hechos(self, session_id: str) -> bool:
        return bool(self.servicio.obtener_memoria(session_id)["facts"])

    def _preguntar(self, session_id: str, pregunta: dict, why: str) -> None:
        """Repite la pregunta hasta que la respuesta sea valida y quede registrada."""
        texto = pregunta.get("question") or pregunta["attribute_id"]
        self.consola.print(f"\n[bold cyan]{texto}[/]")
        if pregunta.get("options"):
            for i, opcion in enumerate(pregunta["options"], start=1):
                self.consola.print(f"  {i}) {opcion}")
        elif pregunta.get("range"):
            minimo, maximo = pregunta["range"]
            self.consola.print(f"  [dim]Valor entre {minimo} y {maximo}[/]")

        while True:
            respuesta = self._leer(">")
            if _normalizar(respuesta) in COMANDOS_WHY:
                self.consola.print(f"  [magenta]WHY:[/] {why}")
                continue
            try:
                valor = convertir_respuesta(respuesta, pregunta)
                self.servicio.registrar_hechos(session_id, {pregunta["attribute_id"]: valor})
                return
            except ValueError as exc:
                if isinstance(exc, ContratoInvalido):
                    self._mostrar_errores("Respuesta no válida.", exc.errores)
                else:
                    self.consola.print(f"  [red]{exc}[/]")

    def _menu_final(self, resultado: dict) -> bool:
        """Acciones tras el dictamen. Devuelve False si el usuario quiere salir."""
        opciones = {"1": "Guardar memoria_trabajo.json y dictamen_salida.json",
                    "2": "Exportar reporte en Markdown",
                    "3": "Exportar reporte en HTML",
                    "4": "Nueva consulta",
                    "5": "Salir"}
        hay_dictamen = resultado["dictamen"] is not None
        while True:
            self.consola.print()
            for clave, texto in opciones.items():
                if clave in {"2", "3"} and not hay_dictamen:
                    continue
                self.consola.print(f"  [bold]{clave}[/]) {texto}")
            opcion = _normalizar(self._leer("Elija una opción:"))
            if opcion == "1":
                for ruta in self.guardar_json(resultado):
                    self.consola.print(f"  [green]Guardado:[/] {_corta(ruta)}")
            elif opcion in {"2", "3"} and hay_dictamen:
                ruta = self.exportar_reporte(resultado, "md" if opcion == "2" else "html")
                self.consola.print(f"  [green]Reporte:[/] {_corta(ruta)}")
            elif opcion == "4":
                return True
            elif opcion in {"5", *COMANDOS_SALIR}:
                return False
            else:
                self.consola.print("[red]Opción no válida.[/]")

    def _bienvenida(self) -> None:
        estado = self.servicio.estado_modulos()
        modulos = "  ".join(f"{g}: {'[green]' if e == 'real' else '[yellow]'}{e}[/]"
                            for g, e in estado.items())
        self.consola.print(Panel(f"Sistema experto modular · UTP 1IL143\nMódulos: {modulos}",
                                 title="ES-Shell Suite · Consulta", border_style="cyan"))

    def _mostrar_errores(self, mensaje: str, errores: list[str]) -> None:
        self.consola.print(f"  [red]{mensaje}[/]")
        for error in errores:
            self.consola.print(f"   - {error}")

    def _leer(self, indicacion: str) -> str:
        self.consola.print(indicacion, end=" ")
        try:
            texto = self._entrada("")
        except (EOFError, KeyboardInterrupt):
            raise _Cancelado from None
        if _normalizar(texto) in COMANDOS_SALIR and indicacion == ">":
            raise _Cancelado
        return texto
