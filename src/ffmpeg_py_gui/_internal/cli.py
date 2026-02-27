"""CLI entry point for ffmpeg-py-gui."""

from __future__ import annotations

import sys

import click
from PySide6.QtWidgets import QApplication

from ffmpeg_py_gui._internal import debug
from ffmpeg_py_gui.gui.user_interface import UserInterface


def debug_info_callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Callback for printing debug info.

    Args:
       ctx (click.Context): The context of the command.
       value (bool): The value of the parameter.
    """
    if not value or ctx.resilient_parsing:
        return
    click.echo(debug._get_debug_info())  # pylint: disable=protected-access
    click.echo(param)
    ctx.exit()


@click.command()
@click.version_option(version=debug._get_version())  # pylint: disable=protected-access
@click.option(
    "--debug-info",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=debug_info_callback,
    help="Print debug information.",
)
@click.option("--gui", is_flag=True, help="Run GUI")
def main(gui: bool) -> None:
    """Run the main program.

    Args:
        gui (bool): Whether to run the GUI. Defaults to False.
    """
    if gui:
        app = QApplication(sys.argv)
        window = UserInterface()
        window.show()
        sys.exit(app.exec())
