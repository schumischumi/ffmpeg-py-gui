# Why does this file exist, and why not put this in `__main__`?
#
# You might be tempted to import things from `__main__` later,
# but that will cause problems: the code will get executed twice:
#
# - When you run `python -m ffmpeg_py_gui` python will execute
#   `__main__.py` as a script. That means there won't be any
#   `ffmpeg_py_gui.__main__` in `sys.modules`.
# - When you import `__main__` it will get executed again (as a module) because
#   there's no `ffmpeg_py_gui.__main__` in `sys.modules`.

from __future__ import annotations

import click
import sys
from PySide6.QtWidgets import (
    QApplication)

from ffmpeg_py_gui._internal import debug
from ffmpeg_py_gui.gui.user_interface import UserInterface

# def get_parser() -> click.Group:
#     """Return the CLI argument parser."""
#     @click.group()
#     def cli():
#         pass

#     @cli.command()
#     @click.option("-V", "--version", is_flag=True, help="Show version.")
#     def version():
#         click.echo(f"ffmpeg-py-gui {debug._get_version()}")

#     @cli.command()
#     @click.option("--gui", is_flag=True, help="Start the GUI.")
#     def gui():
#         pass
def debug_info_callback(ctx, param, value) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(debug._get_debug_info())
    click.echo(av.library_versions)          # dict of linked lib versions
    click.echo(av.ffmpeg_version_info)       # more detailed
    click.echo(av.codecs_available)
    codec = av.Codec('h264', 'r')
    click.echo(codec.capabilities)
    codec = av.Codec('hevc', 'r')
    click.echo(codec.capabilities)
    ctx.exit()


@click.command()
@click.version_option(version=debug._get_version())
@click.option("--debug-info", is_flag=True, expose_value=False, is_eager=True, callback=debug_info_callback, help="Print debug information.")
@click.option("--gui", is_flag=True, help="Run GUI")
def main(gui) -> int:
    """Run the main program."""
    if gui:
        app = QApplication(sys.argv)
        window = UserInterface()
        window.show()
        sys.exit(app.exec())

    return 0

