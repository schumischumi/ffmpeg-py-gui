"""Module for interacting with ffmpeg/ffprobe commands."""

import re
import subprocess
import json  # Import inside method if needed
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot


class FFmpegWorker(QObject):
    """Worker that runs ffmpeg/ffprobe commands asynchronously.
    Runs inside a QThread.
    """

    finished = Signal(int)  # exit code
    output_line = Signal(str)  # raw stdout/stderr line
    progress = Signal(float)  # 0.0 - 1.0 (for live progress cases)
    result = Signal(object)  # generic result (e.g. codec list)
    error = Signal(str)

    def __init__(
        self,
        command: list[str],
        line_parser: Callable[[str], None] | None = None,
        final_parser: Callable[[list[str], int], Any] | None = None,
    ) -> None:
        super().__init__()
        self.command = command
        self.line_parser = line_parser or (lambda line: None)  # default: do nothing
        self.final_parser = final_parser
        self._collected_lines: list[str] = []
        self._is_running = True

    @Slot()
    def run(self) -> None:
        """Executed inside worker thread."""
        try:
            process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            assert process.stdout is not None

            for line in process.stdout:
                if not self._is_running:
                    process.kill()
                    break

                line = line.rstrip("\r\n")
                self._collected_lines.append(line)
                self.output_line.emit(line)

                # Let the custom line parser do its job (progress, partial results, etc.)
                self.line_parser(line)

            process.wait()
            exit_code = process.returncode
            self.finished.emit(exit_code)

            # Final parsing if provided
            if self.final_parser is not None:
                parsed_result = self.final_parser(self._collected_lines, exit_code)
                self.result.emit(parsed_result)

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.error.emit(str(e))

    def stop(self) -> None:
        """Stop the process."""
        self._is_running = False


# pylint: disable=too-few-public-methods
class FFmpegBackend:
    """Backend for ffmpeg-py-gui."""

    def __init__(self, ui: Any) -> None:
        self.ui = ui
        self.thread: QThread | None = None
        self.worker: FFmpegWorker | None = None
        self._duration: float | None = None  # Temp storage for progress across lines

    def _start_worker(self, worker: FFmpegWorker) -> None:
        """Common setup for starting a worker in a thread."""
        self.thread = QThread()

        self.worker = worker  # ← Critical line: assign FIRST
        self.worker.moveToThread(self.thread)

        # Now self.worker exists and has signals
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.worker.progress.connect(self.ui.update_progress)
        self.worker.output_line.connect(self.ui.append_log)
        self.worker.error.connect(self.ui.show_error)
        self.worker.finished.connect(self.ui.command_finished)

        # If using result signal for codecs / ffprobe etc.
        # self.worker.result.connect(self.ui.handle_result)  # or specific handler

        self.thread.start()

    # Example: Run a conversion command with live progress parsing
    def run_conversion(self, input_file: str, output_file: str, hw_accel_args: list[str] = None,  extra_args: list[str] = None) -> None:
        """Run ffmpeg conversion with live progress."""
        command = ["ffmpeg"]  + (hw_accel_args or []) + ["-i", input_file] + (extra_args or []) + [output_file]
        print(command)

        def line_parser(line: str) -> None:
            if "Duration:" in line:
                self._duration = self._parse_duration(line)
            if "time=" in line and self._duration is not None:
                current = self._parse_time(line)
                if current is not None:
                    progress = min(current / self._duration, 1.0)
                    self.worker.progress.emit(progress)  # Emit via worker's signal

        worker = FFmpegWorker(command, line_parser=line_parser)
        self._start_worker(worker)

    # Example: Run to get codecs with end-parsing
    def run_get_codecs(self) -> None:
        """Run ffmpeg -codecs and parse the full output at the end."""
        command = ["ffmpeg", "-encoders"]

        def final_parser(lines: list[str], exit_code: int) -> list[dict] | None:
            if exit_code != 0:
                return None
            codecs = []
            start_reading = False
            for line in lines:
                clean_line = line.strip()
                if clean_line.strip() == "------":
                    start_reading = True
                    continue
                if not start_reading:
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue

                flags = parts[0]  # "V....D" or " DEV.L." etc
                codec_name = parts[1]  # "h264", "libx264", "aac", "a64multi"
                # everything else is description
                description = " ".join(parts[2:]).strip()
                codecs.append({"codec": codec_name, "flags": flags, "description": description})
            return codecs

        worker = FFmpegWorker(command, final_parser=final_parser)
        worker.result.connect(self.ui.update_codec_list)  # Assuming you add a UI method to handle the list
        self._start_worker(worker)

    # Future example: Run ffprobe for file info, parse JSON at end
    def run_get_file_info(self, input_file: str) -> None:
        """Run ffprobe and parse JSON at end."""
        

        command = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            input_file,
        ]

        def final_parser(lines: list[str], exit_code: int) -> dict | None:
            if exit_code != 0:
                return None
            try:
                return json.loads("\n".join(lines))
            except json.JSONDecodeError:
                return None

        worker = FFmpegWorker(command, final_parser=final_parser)
        worker.result.connect(self.ui.display_file_info)  # Add your UI handler
        self._start_worker(worker)

    # Helper parsers (can be shared or overridden)
    def _parse_duration(self, line: str) -> float | None:
        match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", line)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        return None

    def _parse_time(self, line: str) -> float | None:
        match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        return None
