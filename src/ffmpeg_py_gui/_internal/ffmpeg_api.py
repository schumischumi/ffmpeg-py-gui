"""Module for interacting with ffmpeg/ffprobe commands."""

import re
import subprocess
from typing import Any, Callable, List, Optional
import sys

from PySide6.QtCore import QObject, QThread, Signal, Slot


class FFmpegWorker(QObject):
    """Worker that runs ffmpeg/ffprobe commands asynchronously.
    Runs inside a QThread.
    """

    finished = Signal(int)  # exit code
    output_line = Signal(str)  # raw stdout/stderr line
    result = Signal(object)  # generic result (e.g. codec list)
    error = Signal(str)

    def __init__(self, command: list[str], line_parser: Optional[Callable[[str], None]] = None,
        final_parser: Optional[Callable[[List[str], int], Any]] = None,) -> None:
        super().__init__()
        self.command = command
        self.line_parser = line_parser or (lambda line: None)   # default: do nothing
        self.final_parser = final_parser
        self._collected_lines: List[str] = []
        self._is_running = True

    @Slot()
    def run(self) -> None:
        """Executed inside worker thread."""
        try:
            # pylint: disable=consider-using-with
            process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            duration = None

            for line in process.stdout:  # type: ignore[union-attr]
                if not self._is_running:
                    process.kill()
                    break

                # self.output_line.emit(line.strip())

                line = line.rstrip("\r\n")
                self._collected_lines.append(line)
                self.output_line.emit(line)

                # Let the custom line parser do its job (progress, partial results, etc.)
                self.line_parser(line)

            process.wait()

            exit_code = process.returncode
            self.finished.emit(exit_code)
            if self.final_parser is not None:
                parsed_result = self.final_parser(self._collected_lines, exit_code)
                self.result.emit(parsed_result)

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.error.emit(str(e))

    def stop(self) -> None:
        """Stop the process."""
        self._is_running = False
        
    def _parse_duration(self, line: str) -> float | None:
        """Parse the duration from a ffmpeg output line."""
        match = re.search(r"Duration: (\d+):(\d+):(\d+.\d+)", line)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        return None

    def _parse_time(self, line: str) -> float | None:
        """Parse the current time from a ffmpeg output line."""
        match = re.search(r"time=(\d+):(\d+):(\d+.\d+)", line)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        return None

# pylint: disable=too-few-public-methods
class FFmpegBackend:
    """Backend for ffmpeg-py-gui."""

    progress = Signal(float)  # 0.0 - 1.0

    def __init__(self, ui: Any) -> None:
        self.ui = ui
        self.thread: QThread
        self.worker: QThread

    def run_command(self, command: list[str]) -> None:
        """Run a ffmpeg command in a separate thread."""
        self.thread = QThread()
        self.worker = FFmpegWorker(command, self.parse_progress)  # type: ignore[assignment]

        self.worker.moveToThread(self.thread)

        # Connect signals
        self.thread.started.connect(self.worker.run)  # pylint: disable=no-member
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)  # pylint: disable=no-member

        self.worker.progress.connect(self.ui.update_progress)  # type: ignore[attr-defined]
        self.worker.output_line.connect(self.ui.append_log)  # type: ignore[attr-defined]
        self.worker.error.connect(self.ui.show_error)  # type: ignore[attr-defined]
        self.worker.finished.connect(self.ui.command_finished)

        self.thread.start()


    def parse_progress(self, line):
        # Parse duration
        if "Duration:" in line:
            duration = self._parse_duration(line)

        # Parse progress time=
        if "time=" in line and duration:
            current = self._parse_time(line)
            if current:
                progress = min(current / duration, 1.0)
                self.progress.emit(progress)

