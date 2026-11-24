"""Punto de entrada: python -m grupo_10_ui [--kb ruta.json]"""

import argparse

from .esb_ui import ESB_Interactive_UI


def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta interactiva del ES-Shell Suite (Grupo 10).")
    parser.add_argument("--kb", help="Ruta de un conocimiento_dominio.json para cargar al iniciar.")
    args = parser.parse_args()

    ui = ESB_Interactive_UI()
    if args.kb:
        ui.cargar_base(args.kb)
    ui.ejecutar()


if __name__ == "__main__":
    main()
