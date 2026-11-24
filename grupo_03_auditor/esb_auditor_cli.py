"""Interfaz de línea de comandos del Auditor de Base de Conocimiento (Grupo 3).

Ejecución desde la raíz del repositorio:

    python -m grupo_03_auditor.esb_auditor_cli ruta/conocimiento_dominio.json
    python -m grupo_03_auditor.esb_auditor_cli ruta/conocimiento_dominio.json --tabla-decision
    python -m grupo_03_auditor.esb_auditor_cli ruta/conocimiento_dominio.json --output-json reporte.json --output-md reporte.md

También admite ejecución directa:

    python grupo_03_auditor/esb_auditor_cli.py ruta/conocimiento_dominio.json

Códigos de salida:
    0: Base de conocimiento sin errores críticos (ERROR = 0).
    1: Se detectaron errores críticos (o advertencias si se usa ``--estricto``).
    2: Error de uso / argumentos de línea de comandos.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

if __package__ in (None, ""):
    _raiz = str(Path(__file__).resolve().parents[1])
    if _raiz not in sys.path:
        sys.path.insert(0, _raiz)
    from grupo_03_auditor.esb_auditor import (  # type: ignore
        KBAuditor,
        ReporteAuditoria,
        SEVERIDAD_WARNING,
        formatear_tabla_decision_consola,
    )
else:
    from .esb_auditor import (
        KBAuditor,
        ReporteAuditoria,
        SEVERIDAD_WARNING,
        formatear_tabla_decision_consola,
    )


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="esb_auditor_cli",
        description=(
            "Grupo 3 — Auditor de consistencia, contradicciones, redundancias, "
            "ciclos y tablas de decisión para conocimiento_dominio.json."
        ),
    )
    parser.add_argument(
        "archivo",
        nargs="?",
        type=Path,
        help="Ruta al archivo conocimiento_dominio.json a auditar.",
    )
    parser.add_argument(
        "--archivo",
        dest="archivo_flag",
        type=Path,
        default=None,
        help="Alternativa nombrada para indicar la ruta del archivo JSON.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Ruta donde exportar el reporte de auditoría en formato JSON.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Ruta donde exportar el reporte de auditoría en formato Markdown.",
    )
    parser.add_argument(
        "--tabla-decision",
        action="store_true",
        help="Mostrar la Tabla de Decisión completa en la consola.",
    )
    parser.add_argument(
        "--sin-schema",
        action="store_true",
        help="Omitir la validación previa con SchemaManager (usar solo validación interna).",
    )
    parser.add_argument(
        "--estricto",
        action="store_true",
        help="Devolver código de salida 1 también cuando existan advertencias (WARNING).",
    )
    return parser


def imprimir_resumen_consola(
    reporte: ReporteAuditoria,
    ruta_archivo: Path,
    *,
    mostrar_tabla: bool = False,
) -> None:
    """Imprime un resumen claro y estructurado del reporte en la salida estándar."""
    titulo = reporte.meta.get("project_title") or "(sin título)"
    version = reporte.meta.get("version") or "N/A"
    res = reporte.resumen
    conteo = res["conteo_severidad"]

    print("=" * 72)
    print(" ES-Shell Suite | Grupo 3 — Auditor de Base de Conocimiento (KBAuditor)")
    print("=" * 72)
    print(f"Archivo   : {ruta_archivo}")
    print(f"Dominio   : {titulo} (v{version})")
    print(f"Estado    : {reporte.estado} (es_valida={reporte.es_valida})")
    print(
        f"Métricas  : {res['total_atributos']} atributo(s) | "
        f"{res['total_reglas']} regla(s) | "
        f"{res['total_hallazgos']} hallazgo(s) "
        f"[ERROR={conteo['ERROR']}, WARNING={conteo['WARNING']}, INFO={conteo['INFO']}]"
    )
    print("-" * 72)

    if not reporte.hallazgos:
        print("[OK] No se detectaron problemas en la base de conocimiento.")
    else:
        print("Hallazgos:")
        for idx, h in enumerate(reporte.hallazgos, 1):
            reglas_txt = f" | reglas={h.reglas}" if h.reglas else ""
            attrs_txt = f" | atributos={h.atributos}" if h.atributos else ""
            print(f"  {idx}. [{h.severidad}] ({h.categoria}){reglas_txt}{attrs_txt}")
            print(f"     {h.mensaje}")

    if mostrar_tabla:
        print("\nTabla de Decisión:")
        print(formatear_tabla_decision_consola(reporte.tabla_decision))


def main(argv: Sequence[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    ruta = args.archivo_flag or args.archivo
    if ruta is None:
        parser.error("Debe especificar la ruta al archivo conocimiento_dominio.json.")

    auditor = KBAuditor(ruta, usar_schema_manager=not args.sin_schema)
    reporte = auditor.auditar()

    imprimir_resumen_consola(
        reporte,
        ruta,
        mostrar_tabla=args.tabla_decision,
    )

    if args.output_json is not None:
        try:
            auditor.exportar_json(args.output_json, reporte=reporte)
            print(f"\n[EXPORTADO] Reporte JSON guardado en: {args.output_json}")
        except OSError as exc:
            print(f"\n[ERROR] No se pudo escribir '{args.output_json}': {exc}", file=sys.stderr)
            return 1

    if args.output_md is not None:
        try:
            auditor.exportar_markdown(args.output_md, reporte=reporte)
            print(f"[EXPORTADO] Reporte Markdown guardado en: {args.output_md}")
        except OSError as exc:
            print(f"[ERROR] No se pudo escribir '{args.output_md}': {exc}", file=sys.stderr)
            return 1

    if not reporte.es_valida:
        return 1
    if args.estricto and reporte.resumen["conteo_severidad"].get(SEVERIDAD_WARNING, 0) > 0:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
