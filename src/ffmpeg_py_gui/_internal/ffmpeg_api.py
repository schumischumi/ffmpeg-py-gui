import subprocess
import re
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtCore import QThread


class FFmpegWorker(QObject):
    """
    Worker that runs ffmpeg/ffprobe commands asynchronously.
    Runs inside a QThread.
    """

    finished = Signal(int)              # exit code
    progress = Signal(float)            # 0.0 - 1.0
    output_line = Signal(str)           # raw stdout/stderr line
    result = Signal(object)             # generic result (e.g. codec list)
    error = Signal(str)

    def __init__(self, command: list[str]):
        super().__init__()
        self.command = command
        self._is_running = True

    @Slot()
    def run(self):
        """Executed inside worker thread."""

        try:
            process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            duration = None

            for line in process.stdout:
                if not self._is_running:
                    process.kill()
                    break

                self.output_line.emit(line.strip())

                # Parse duration
                if "Duration:" in line:
                    duration = self._parse_duration(line)

                # Parse progress time=
                if "time=" in line and duration:
                    current = self._parse_time(line)
                    if current:
                        progress = min(current / duration, 1.0)
                        self.progress.emit(progress)

            process.wait()
            self.finished.emit(process.returncode)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False

    def _parse_duration(self, line: str):
        match = re.search(r"Duration: (\d+):(\d+):(\d+.\d+)", line)
        if match:
            h, m, s = match.groups()
            return int(h)*3600 + int(m)*60 + float(s)
        return None

    def _parse_time(self, line: str):
        match = re.search(r"time=(\d+):(\d+):(\d+.\d+)", line)
        if match:
            h, m, s = match.groups()
            return int(h)*3600 + int(m)*60 + float(s)
        return None



class FFmpegBackend:
    def __init__(self, ui):
        self.ui = ui
        self.thread = None
        self.worker = None

    def run_command(self, command: list[str]):
        self.thread = QThread()
        self.worker = FFmpegWorker(command)

        self.worker.moveToThread(self.thread)

        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.worker.progress.connect(self.ui.update_progress)
        self.worker.output_line.connect(self.ui.append_log)
        self.worker.error.connect(self.ui.show_error)
        self.worker.finished.connect(self.ui.command_finished)

        self.thread.start()