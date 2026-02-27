"""User interface for ffmpeg-py-gui."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMovie, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ffmpeg_py_gui._internal.ffmpeg_api import FFmpegBackend


# Global state
# pylint: disable=too-many-instance-attributes
class UserInterface(QMainWindow):
    """Main application window (PySide6 version)."""

    # pylint: disable=too-many-statements, too-many-locals
    def __init__(self) -> None:
        super().__init__()

        self.backend = FFmpegBackend(self)

        self.codec_list = []  # type: ignore

        self.setWindowTitle("FFmpeg VA-API Converter")
        self.resize(1000, 700)

        self.added_files: list[Path] = []

        # Enable native drag & drop
        self.setAcceptDrops(True)

        # --- Main Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.loading_overlay = LoadingOverlay(self)

        main_layout = QHBoxLayout(central_widget)

        # ------------------------
        # LEFT PANEL (File List)
        # ------------------------
        left_layout = QVBoxLayout()

        left_layout.addWidget(QLabel("Input Files"))

        self.file_table = QTableWidget()
        self.file_table.setColumnCount(3)
        self.file_table.setHorizontalHeaderLabels(["Filename", "Size", ""])
        self.file_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        left_layout.addWidget(self.file_table)

        button_layout = QHBoxLayout()

        add_button = QPushButton("Add Files...")
        add_button.clicked.connect(self.open_file_dialog)  # pylint: disable=no-member

        clear_button = QPushButton("Clear List")
        clear_button.clicked.connect(self.clear_list)  # pylint: disable=no-member

        button_layout.addWidget(add_button)
        button_layout.addWidget(clear_button)

        left_layout.addLayout(button_layout)

        # ------------------------
        # RIGHT PANEL (Tabs)
        # ------------------------
        tabs = QTabWidget()

        # --- Tab 1 ---
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)

        tab1_layout.addWidget(QLabel("FFmpeg Encoding Settings"))

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(
            ["Very Fast", "Fast", "Medium", "Slow", "Very Slow"],
        )
        self.preset_combo.setCurrentText("Medium")
        tab1_layout.addWidget(QLabel("Preset"))
        tab1_layout.addWidget(self.preset_combo)

        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(23)
        tab1_layout.addWidget(QLabel("CRF"))
        tab1_layout.addWidget(self.crf_spin)
        tab1_layout.addWidget(QLabel("(lower = better quality, larger file)"))

        self.codec_combo = QComboBox()
        tab1_layout.addWidget(QLabel("Codec"))
        tab1_layout.addWidget(self.codec_combo)

        self.hw_vaapi_checkbox = QCheckBox("Use hardware acceleration (VA-API)")
        self.hw_vaapi_checkbox.setChecked(False)
        self.hw_vaapi_checkbox.stateChanged.connect(self.apply_filter_vaapi)
        tab1_layout.addWidget(self.hw_vaapi_checkbox)

        self.hw_vulkan_checkbox = QCheckBox("Use hardware acceleration (VULKAN)")
        self.hw_vulkan_checkbox.setChecked(False)
        self.hw_vulkan_checkbox.stateChanged.connect(self.apply_filter_vulkan)
        tab1_layout.addWidget(self.hw_vulkan_checkbox)

        self.audio_checkbox = QCheckBox("Copy audio")
        self.audio_checkbox.setChecked(True)
        tab1_layout.addWidget(self.audio_checkbox)

        self.sub_checkbox = QCheckBox("Copy subtitles")
        self.sub_checkbox.setChecked(True)
        tab1_layout.addWidget(self.sub_checkbox)

        self.overwrite_checkbox = QCheckBox("Overwrite file if it already exists")
        self.overwrite_checkbox.setChecked(True)
        tab1_layout.addWidget(self.overwrite_checkbox)

        # Output folder
        output_layout = QHBoxLayout()
        self.output_edit = QLineEdit(str(Path.home() / "Videos"))
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_output_folder)  # pylint: disable=no-member

        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(browse_button)

        tab1_layout.addLayout(output_layout)

        self.start_button = QPushButton("Start Conversion")
        self.start_button.clicked.connect(self.start_conversion)  # pylint: disable=no-member
        tab1_layout.addWidget(self.start_button)

        self.progress_bar = QProgressBar()
        tab1_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Status: Idle")
        tab1_layout.addWidget(self.status_label)

        self.spinner_label = QLabel()
        self.spinner_label.setFixedSize(24, 24)
        self.spinner_label.hide()

        # Load spinner GIF (you need a small loading.gif file)
        self.spinner_movie = QMovie("loading.gif")
        self.spinner_movie.setScaledSize(QSize(24, 24))
        self.spinner_label.setMovie(self.spinner_movie)

        # Add spinner next to status label
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.spinner_label)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        tab1_layout.addLayout(status_layout)

        tab1_layout.addStretch()

        # --- Tab 2 ---
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)

        tab2_layout.addWidget(QLabel("Tab 2 – Settings / Preview"))

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setValue(50)
        tab2_layout.addWidget(self.threshold_slider)

        color_button = QPushButton("Choose Color")
        color_button.clicked.connect(self.choose_color)  # pylint: disable=no-member
        tab2_layout.addWidget(color_button)

        self.get_codec_button = QPushButton("Get Supported Codecs")
        self.get_codec_button.clicked.connect(self.get_codecs)  # pylint: disable=no-member
        tab1_layout.addWidget(self.get_codec_button)

        tab2_layout.addStretch()

        # --- Tab 3 ---
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)

        tab3_layout.addWidget(QLabel("Tab 3 – Logs / Output"))

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        tab3_layout.addWidget(self.log_edit)

        clear_log_button = QPushButton("Clear Log")
        clear_log_button.clicked.connect(self.log_edit.clear)  # pylint: disable=no-member
        tab3_layout.addWidget(clear_log_button)

        # Add tabs
        tabs.addTab(tab1, "Tab 1")
        tabs.addTab(tab2, "Tab 2")
        tabs.addTab(tab3, "Tab 3")

        # Add panels to main layout
        main_layout.addLayout(left_layout, 1)
        main_layout.addWidget(tabs, 1)

    # --------------------------------------------------
    # Drag & Drop (Native Linux Support)
    # --------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter event.

        Args:
            event (QDragEnterEvent): The drag enter event.
        """
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle file drop event.

        Args:
            event (QDropEvent): The drop event.
        """
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.exists():
                self.add_files([path])

    # --------------------------------------------------
    # File Handling
    # --------------------------------------------------
    def open_file_dialog(self) -> None:
        """Open a file dialog and select video files."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files",
            str(Path.home()),
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.ts)",
        )
        self.add_files([Path(f) for f in files])

    def browse_output_folder(self) -> None:
        """Browse for an output folder."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            self.output_edit.text(),
        )
        if folder:
            self.output_edit.setText(folder)

    def add_files(self, paths: list[Path]) -> None:
        """Add files to the UI.

        Args:
            paths (list[Path]): List of paths to add.
        """
        for path in paths:
            if path.is_file() and path not in self.added_files:
                self.added_files.append(path)

        self.refresh_file_list()

    def refresh_file_list(self) -> None:
        """Refresh the file list in the UI."""
        self.file_table.setRowCount(len(self.added_files))

        for row, path in enumerate(self.added_files):
            self.file_table.setItem(row, 0, QTableWidgetItem(path.name))
            size_mb = path.stat().st_size / (1024 * 1024)
            self.file_table.setItem(row, 1, QTableWidgetItem(f"{size_mb:.1f} MB"))

            remove_button = QPushButton("X")
            remove_button.clicked.connect(  # pylint: disable=no-member
                lambda _, p=path: self.remove_file(p),
            )
            self.file_table.setCellWidget(row, 2, remove_button)

    def remove_file(self, path: Path) -> None:
        """Remove file from list

        Args:
            path (Path): Path to file
        """
        if path in self.added_files:
            self.added_files.remove(path)
            self.refresh_file_list()

    def clear_list(self) -> None:
        """Clean file list"""
        self.added_files.clear()
        self.refresh_file_list()

    # --------------------------------------------------
    # Misc
    # --------------------------------------------------
    def choose_color(self) -> None:
        """Open a color dialog and log the selected color."""
        color = QColorDialog.getColor()
        if color.isValid():
            self.log_edit.append(f"Selected color: {color.name()}")

    def start_conversion(self) -> None:
        """Starts the conversion process."""
        if not self.added_files:
            self.status_label.setText("Status: No files selected")
            return

        input_file = str(self.added_files[0])
        output_file = str(Path(self.output_edit.text()) / "output.mp4")

        extra_args = [
            "-c:v",
            "libx264",
        ]

        # Busy indicator ON
        # self.start_spinner()
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Status: Running...")

        self.backend.run_conversion(input_file, output_file, extra_args)

    def get_codecs(self) -> None:
        """Fetches the available codecs from the backend."""
        self.backend.run_get_codecs()

    def update_codec_list(self, codecs: list[dict]) -> None:

        self.codec_combo.clear()
        self.codec_list.clear()
        for codec in codecs:
            description = codec["description"] if len(codec["description"]) < 50 else f"{codec['description'][:50]}..."
            codec_list_entry = f"{codec['codec']} - {description}"
            self.codec_list.append(codec_list_entry)
            self.codec_combo.addItem(codec_list_entry)

    def update_progress(self, value: float) -> None:
        """Update progress bar with a value between 0 and 1.

        Args:
            value (float): Value between 0 and 1.
        """
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(int(value * 100))

    def append_log(self, line: str) -> None:
        """Append a line to the log edit widget.

        Args:
           line (str): Line to append.
        """
        self.log_edit.append(line)

    def command_finished(self, exit_code: int) -> None:
        """Handle command finished signal.

        Args:
            exit_code (int): Exit code of the command.
        """
        self.stop_spinner()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Finished (exit code {exit_code})")

    def show_error(self, message: str) -> None:
        """Show error message in UI.

        Args:
            message (str): Error message to display.
        """
        self.status_label.setText("Error occurred")
        self.log_edit.append(f"ERROR: {message}")
        self.stop_spinner()

    def start_spinner(self) -> None:
        """Start animated spinner indicator."""
        self.loading_overlay.start("test")

    def stop_spinner(self) -> None:
        """Stop animated spinner indicator."""
        self.loading_overlay.stop()

    def apply_filter_vaapi(self):
        self.codec_combo.clear()

        if self.hw_vaapi_checkbox.isChecked():
            # Contains "vaapi" (case insensitive)
            for codec in self.codec_list:
                if "_vaapi" in codec.split()[0].lower():
                    self.codec_combo.addItem(codec)
        else:
            # Show everything
            self.codec_combo.addItems(self.codec_list)

    def apply_filter_vulkan(self):
        self.codec_combo.clear()

        if self.hw_vulkan_checkbox.isChecked():
            # Contains "vaapi" (case insensitive)
            for codec in self.codec_list:
                if "_vulkan" in codec.split()[0].lower():
                    self.codec_combo.addItem(codec)
        else:
            # Show everything
            self.codec_combo.addItems(self.codec_list)


class LoadingOverlay(QWidget):
    """Semi-transparent full-window overlay with centered spinner.
    Blocks interaction while visible.
    """

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            background-color: rgba(0, 0, 0, 120);
        """)

        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.spinner_label = QLabel()
        self.spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.text_label = QLabel("Working...")
        self.text_label.setStyleSheet("color: white; font-size: 16px;")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.movie = QMovie("loading.gif")
        self.movie.setScaledSize(QSize(64, 64))
        self.spinner_label.setMovie(self.movie)

        layout.addWidget(self.spinner_label)
        layout.addWidget(self.text_label)

    def start(self, text: str = "Working...") -> None:
        """Start loading animation

        Args:
            text (str): Text to show under the animation
        """
        self.text_label.setText(text)
        self.setGeometry(self.parent().rect())  # type: ignore[attr-defined]
        self.show()
        self.movie.start()

    def stop(self) -> None:
        """Stop loading animation"""
        self.movie.stop()
        self.hide()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Resize the widget to fit its parent.

        Args:
            event (QResizeEvent): The resize event.
        """
        self.setGeometry(self.parent().rect())  # type: ignore[attr-defined]
        super().resizeEvent(event)
