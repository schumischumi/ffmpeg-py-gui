"""Main application GUI for ffmpeg-py-gui."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click
from PySide6.QtCore import (
    QObject,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from PySide6.QtCore import Qt


# =============================================================================
# CONSTANTS
# =============================================================================

APP_TITLE = "ffmpeg-py-gui"

# Input/Output widgets
INPUT_LABEL = "Input file:"
OUTPUT_LABEL = "Output file:"

CODECLABEL = "Codec:"
FILTER_LABEL = "Filter:"

# Default values
DEFAULT_CODECS: list[dict[str, str]] = [
    # (display_text, internal_value)
    ("Copy", "copy"),
]

DEFAULT_OUTPUT_PATH: str = "output"


# =============================================================================
# UI STYLES
# =============================================================================

UI_STYLES = """
QLabel {
    font: 20pt;
}

QLineEdit {
    font: 16pt;
    padding: 5px;
    border-radius: 4px;
}

QPushButton {
    font: 16pt;
    color: white;
    background-color: #1976d2;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
}

QPushButton:hover {
    background-color: #1565c0;
}

QComboBox {
    font: 14pt;
    padding: 5px;
}

QListWidget {
    font: 12pt;
    row-spacing: 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
}

QMessageBox QLabel {
    color: black;
}
"""

# =============================================================================
# MODEL / STATE
# =============================================================================


class ConversionSettings:
    """Holds conversion parameters and parsed file info."""

    def __init__(self) -> None:
        self.input_file: str | None = None
        self.output_file: str | None = None
        self.codec: str = "copy"
        self.filter: str = ""
        self.hw_accel_enabled: bool = False

        # Parsed input file info
        self.duration: float | None = None
        self.width: int | None = None
        self.height: int | None = None


# =============================================================================
# COMPONENTS / SUBSYSTEMS
# =============================================================================


class LoadingOverlay(QMainWindow):
    """Full-window blocking overlay with loading animation."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent=parent.window())  # type: ignore[argument-type]
        self.ui_main = parent  # type: ignore[attr-defined]

        self.setAttribute(Qt.WidgetAttribute.WA_Translucent, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        self.setVisible(False)

        overlay = QWidget(self)
        layout = QVBoxLayout(overlay)
        layout.setContentsMargins(20, 50, 20, 50)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.spinner_label = QLabel()
        self.spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.text_label = QLabel("Working...")
        self.text_label.setStyleSheet("color: white; font-size: 18px;")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.spinner_label)
        layout.addWidget(self.text_label, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        from PySide6.QtWidgets import QMovie
        self.movie = QTimer()
        self.spinner_label.installEventFilter(self)  # type: ignore[attr-defined]

        overlay.setWindowFlags(Qt.WindowType.Tool)
        overlay.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    @Slot(str)
    def show(self, text: str = "Working...") -> None:
        """Start loading state."""
        self.text_label.setText(text)
        from PySide6.QtCore import QRect
        self.setGeometry(QRect.fromPointAndSize(0, 0, self.ui_main.width(), self.ui_main.height()))  # type: ignore[attr-defined]
        self.show()
        self.timer_start(self movie.start())

    def stop(self) -> None:
        """Stop and hide loading state."""
        self.movie.stop()
        self.hide()

    def resizeEvent(self, event) -> None:
        """Resize to fit parent."""
        from PySide6.QtCore import QRect
        self.setGeometry(QRect.fromPointAndSize(0, 0, self.ui_main.width(), self.ui_main.height()))  # type: ignore[attr-defined]
        super().resizeEvent(event)


# =============================================================================
# SERVICES / BACKENDS
# =============================================================================


class FFmpegManager(QObject):
    """Manages all ffmpeg/ffprobe worker threads and command execution."""

    _instances: dict[Path, "FFmpegManager"] = {}

    @classmethod
    def get_instance(cls, parent_widget: QWidget) -> "FFmpegManager":
        """Get singleton instance for this QApplication's main window."""
        key = Path.home() / "ffmpeg_manager"
        if key not in cls._instances:
            cls._instances[key] = FFmpegManager(parent_widget.window())  # type: ignore[argument-type,attr-defined]
        return cls._instances[key]

    def run_conversion(
        self,
        input_file: str,
        output_file: str,
        hw_accel_args: list[str] | None = None,
        extra_args: list[str] | None = None,
    ) -> None:
        """Run ffmpeg conversion with live progress."""
        command = ["ffmpeg"] + (hw_accel_args or []) + [
            "-i",
            input_file,
        ] + (extra_args or []) + [output_file]

        def line_parser(line: str) -> None:
            if "Duration:" in line:
                self._duration = self._parse_duration(line)
            if "time=" in line and self._duration is not None:
                current = self._parse_time(line)
                if current is not None:
                    progress = min(current / self._duration, 1.0)
                    self.ui_main.loading_overlay.show("Converting...")

        from ffmpeg_py_gui._internal.ffmpeg_api import FFmpegWorker
        worker = FFmpegWorker(command, line_parser=line_parser)
        self._start_worker(worker)

    def run_get_codecs(self) -> None:
        """Run get codecs."""
        from ffmpeg_py_gui._internal.ffmpeg_api import FFmpegWorker

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
                flags = parts[0]
                codec_name = parts[1]
                description = " ".join(parts[2:]).strip()
                codecs.append(
                    {
                        "codec": codec_name,
                        "flags": flags,
                        "description": description,
                    }  # type: ignore[typeddict-item]
                )
            return codecs

        command = ["ffmpeg", "-encoders"]

        from PySide6.QtWidgets import QComboBox
        worker_result_worker: FFmpegWorker | None = None
        for i in range(self.ui_main.codec_combo.count()):
            self.item_data = (self.ui_main.codec_combo.itemText(i), self.ui_main.codec_combo.itemData(i))

        worker_result_worker = FFmpegWorker(command, final_parser=final_parser)
        worker.result.connect(self.update_codec_list)
        self._start_worker(worker_result_worker)

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
        self._connect_worker_signals(worker)
        self._start_worker(worker)

    @Slot(list[dict])
    def update_codec_list(self, codecs: list[dict]) -> None:
        """Update codec dropdown with parsed results."""
        self.ui_main.codec_combo.clear()
        for item in codecs:
            text = f"{item['codec']} ({item['description']})"  # type: ignore[index]
            self.ui_main.codec_combo.addItem(text, item["codec"])

    def _start_worker(self, worker: "FFmpegWorker") -> None:
        """Start a worker in a new QThread."""
        from ffmpeg_py_gui._internal.ffmpeg_api import FFmpegWorker

        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # UI signals from worker
        worker.progress.connect(self.ui_main.update_progress)
        worker.output_line.connect(self.ui_main.append_log)
        worker.error.connect(self.ui_main.show_error)
        worker.finished.connect(self.ui_main.command_finished)

        self.ui_main.loading_overlay.start("Preparing...")
        thread.start()

    def _connect_worker_signals(self, worker: "FFmpegWorker") -> None:
        """Connect common worker signals to UI."""
        from ffmpeg_py_gui._internal.ffmpeg_api import FFmpegWorker

        worker.progress.connect(self.ui_main.update_progress)
        worker.output_line.connect(self.ui_main.append_log)
        worker.error.connect(self.ui_main.show_error)
        worker.finished.connect(self.ui_main.command_finished)

    def _parse_duration(self, line: str) -> float | None:
        import re as _re

        match = _re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", line)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        return None

    def _parse_time(self, line: str) -> float | None:
        import re as _re

        match = _re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        return None

    def stop(self) -> None:
        """Stop all workers."""
        self._is_running = False


# =============================================================================
# MAIN APPLICATION UI
# =============================================================================


class ApplicationUI(QWidget):
    """Main application window with GUI and event handling."""

    input_file_changed = Signal(str)
    output_file_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        # Attributes
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(800, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title_label = QLabel(APP_TITLE + " - Video Converter")
        title_font = QFont()
        title_font.setPointSizeF(24.0 / 96.0 * 1.1875)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Grid for inputs/outputs
        grid_layout = QGridLayout(self._create_input_output_widgets())
        grid_layout.setColumnStretch(1, 2)
        grid_layout.setRowStretch(4, 1)
        layout.addLayout(grid_layout, alignment=Qt.AlignmentFlag.AlignTop)

        # Filter dropdown button (simulated with QLabel + custom button in real impl)
        filter_label = QLabel(FILTER_LABEL)
        filter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(filter_label, alignment=Qt.AlignmentFlag.AlignTop)

        # Codec dropdown
        self.codeclist_widget = QScrollArea()
        self.codeclist_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        codeclist_inner = QWidget()
        self.codeclist_layout = QVBoxLayout(codeclist_inner)
        self.codeclist_layout.setContentsMargins(0, 0, 0, 0)
        self.codeclist_widget.setWidget(codeclist_inner)
        layout.addWidget(self.codeclist_widget, alignment=Qt.AlignmentFlag.AlignTop)

        # Convert button + spacer
        grid_convert = QHBoxLayout()
        convert_btn = QPushButton("Convert")
        grid_convert.addWidget(convert_btn)
        convert_btn.clicked.connect(self.run_conversion)
        grid_convert.addStretch()
        layout.addLayout(grid_convert, alignment=Qt.AlignmentFlag.AlignJustify)

        # Status line
        status_label = QLabel("")
        status_label.setStyleSheet("color: gray;")
        self.status_label = status_label  # Expose via attribute for backward compat
        layout.addWidget(status_label, alignment=Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignHCenter)

        # Log area with scroll
        log_area = QScrollArea()
        log_area.setWidgetResizable(True)
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        self.log_edit = None  # Will be set after layout
        log_layout.addWidget(self.log_edit, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(log_area, alignment=Qt.AlignmentFlag.AlignJustify | Qt.AlignmentFlag.AlignHCenter)

    def _create_input_output_widgets(
        self,
    ) -> dict[str, QHBoxLayout]:
        """Create all input/output widgets and return their layouts."""
        result = {}

        row = 0

        # Input file
        input_row = QHBoxLayout()
        input_label = QLabel(INPUT_LABEL)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("e.g. /path/to/input.mp4")
        input_row.addWidget(input_label)
        input_row.addWidget(self.input_field, stretch=2)
        result["input"] = input_row

        # Output file
        output_row = QHBoxLayout()
        output_label = QLabel(OUTPUT_LABEL)
        self.output_field = QLineEdit()
        self.output_field.setPlaceholderText("e.g. /path/to/output.mp4")
        output_row.addWidget(output_label)
        output_row.addWidget(self.output_field, stretch=2)
        result["output"] = output_row

        # Codec dropdown - create it after init in _connect_ui_signals()
        codec_row = QHBoxLayout()
        codec_label = QLabel(CODECLABEL)
        self.codec_combo = QComboBox()
        for text, value in DEFAULT_CODECS:
            self.codec_combo.addItem(text, value)
        codec_row.addWidget(codec_label)
        codec_row.addWidget(self.codec_combo, stretch=2)
        result["codec"] = codec_row

        # Filter row (placeholder)
        filter_row = QHBoxLayout()
        filter_label = QLabel(FILTER_LABEL)
        self.filter_field = QLineEdit()
        filter_row.addWidget(filter_label)
        filter_row.addWidget(self.filter_field, stretch=2)
        result["filter"] = filter_row

        # Progress row
        progress_row = QHBoxLayout()
        progress_label = QLabel("Progress:")
        self.progress_label = QLabel("0%")
        progress_bar = QProgressBar()
        progress_row.addWidget(progress_label)
        progress_row.addWidget(self.progress_label, stretch=2)
        progress_row.addWidget(progress_bar)
        result["progress"] = progress_row

        # Log row (will be added later)
        log_row = QHBoxLayout()
        log_label = QLabel("Log:")
        self.scroll_log_area = QScrollArea()
        log_widget_inner = QWidget()
        log_layout_inner = QVBoxLayout(log_widget_inner)
        self.log_edit = QPlainTextEdit()
        log_layout_inner.addWidget(self.log_edit)
        self.scroll_log_area.setWidget(log_widget_inner)
        log_row.addWidget(log_label)
        log_row.addWidget(self.scroll_log_area, stretch=2)
        result["log"] = log_row

        # Checkbox rows for hw accel (simulated)
        checkbox_rows: list[QHBoxLayout] = []
        for idx in range(3):  # Simulate 3 HW accel options
            row = QHBoxLayout()
            label_text = f"HW Acceleration Option {idx + 1}"
            lbl = QLabel(label_text)
            chk = QCheckBox()
            row.addWidget(lbl)
            row.addWidget(chk, stretch=2)
            checkbox_rows.append(row)

        # Add them all to result so _connect_ui_signals can wire them
        for i, row in enumerate(checkbox_rows):
            row_index = f"hw_accel_{i}"
            result[row_index] = row

        return result

    def _connect_ui_signals(self) -> None:
        """Connect widget signals to event handlers."""
        self.input_field.textChanged.connect(lambda t: self._on_input_file_changed())
        self.input_field.returnPressed.connect(self.run_get_file_info)

    @Slot()
    def _on_input_file_changed(self) -> None:
        """Handle input file change."""
        self.input_file_changed.emit(self.input_field.text())

    def _handle_codec_selection(self) -> None:
        """Apply filter-based codec selection (Vaapi/Vulkan)."""
        # Placeholder for Vaapi/Vulkan UI logic
        pass


# =============================================================================
# ENTRY POINTS / PUBLIC API
# =============================================================================


def run_conversion(
    ui_window: ApplicationUI,
    input_file: str,
    output_file: str,
    extra_args: list[str] = None,
) -> None:
    """Start conversion for an already-created UI window.

    Args:
        ui_window: The main ApplicationUI instance
        input_file: Path to input file
        output_file: Path to desired output
        extra_args: Optional ffmpeg arguments to append
    """
    from ffmpeg_py_gui.main import FFmpegManager
    manager = FFmpegManager.get_instance(ui_window)
    manager.run_conversion(input_file, output_file, extra_args=extra_args)


def display_file_info(ui_window: ApplicationUI, input_file: str) -> None:
    """Fetch and display info for an input file."""
    from ffmpeg_py_gui.main import FFmpegManager
    manager = FFmpegManager.get_instance(ui_window)
    manager.run_get_file_info(input_file)


@click.command()
@click.option(
    "--gui/",
    is_flag=True,
    help="Run GUI",
)
def main(gui: bool) -> None:
    """Entry point for ffmpeg-py-gui."""
    app = QApplication(sys.argv)
    window = ApplicationUI()
    # Wire up codec selection to filter (Vaapi/Vulkan) - done in _connect_ui_signals
    window._handle_codec_selection()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
