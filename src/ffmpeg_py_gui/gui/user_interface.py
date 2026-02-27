
import threading
import tkinter as tk
from pathlib import Path
import urllib.parse   # to handle file:// URIs
import os
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QFileDialog,
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget,
    QComboBox, QSpinBox, QCheckBox, QLineEdit,
    QProgressBar, QTextEdit, QSlider, QColorDialog,
    QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

# Global state
class UserInterface(QMainWindow):
    """Main application window (PySide6 version)."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("FFmpeg VA-API Converter")
        self.resize(1000, 700)

        self.added_files: list[Path] = []

        # Enable native drag & drop
        self.setAcceptDrops(True)

        # --- Main Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

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
            0, QHeaderView.Stretch
        )
        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_table.setEditTriggers(QTableWidget.NoEditTriggers)

        left_layout.addWidget(self.file_table)

        button_layout = QHBoxLayout()

        add_button = QPushButton("Add Files...")
        add_button.clicked.connect(self.open_file_dialog)

        clear_button = QPushButton("Clear List")
        clear_button.clicked.connect(self.clear_list)

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
            ["Very Fast", "Fast", "Medium", "Slow", "Very Slow"]
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
        self.codec_combo.addItems([
            "H.265 (hevc_vaapi)",
            "H.264 (h264_vaapi)",
            "AV1 (av1_vaapi)"
        ])
        tab1_layout.addWidget(QLabel("Codec"))
        tab1_layout.addWidget(self.codec_combo)

        self.hw_checkbox = QCheckBox("Use hardware acceleration (VA-API)")
        self.hw_checkbox.setChecked(True)
        tab1_layout.addWidget(self.hw_checkbox)

        self.audio_checkbox = QCheckBox("Copy audio")
        self.audio_checkbox.setChecked(True)
        tab1_layout.addWidget(self.audio_checkbox)

        self.sub_checkbox = QCheckBox("Copy subtitles")
        self.sub_checkbox.setChecked(True)
        tab1_layout.addWidget(self.sub_checkbox)

        # Output folder
        output_layout = QHBoxLayout()
        self.output_edit = QLineEdit(str(Path.home() / "Videos"))
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_output_folder)

        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(browse_button)

        tab1_layout.addLayout(output_layout)

        self.start_button = QPushButton("Start Conversion")
        tab1_layout.addWidget(self.start_button)

        self.progress_bar = QProgressBar()
        tab1_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Status: Idle")
        tab1_layout.addWidget(self.status_label)

        tab1_layout.addStretch()

        # --- Tab 2 ---
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)

        tab2_layout.addWidget(QLabel("Tab 2 – Settings / Preview"))

        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setValue(50)
        tab2_layout.addWidget(self.threshold_slider)

        color_button = QPushButton("Choose Color")
        color_button.clicked.connect(self.choose_color)
        tab2_layout.addWidget(color_button)

        tab2_layout.addStretch()

        # --- Tab 3 ---
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)

        tab3_layout.addWidget(QLabel("Tab 3 – Logs / Output"))

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        tab3_layout.addWidget(self.log_edit)

        clear_log_button = QPushButton("Clear Log")
        clear_log_button.clicked.connect(self.log_edit.clear)
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
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.exists():
                self.add_files([path])

    # --------------------------------------------------
    # File Handling
    # --------------------------------------------------
    def open_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files",
            str(Path.home()),
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.ts)"
        )
        self.add_files([Path(f) for f in files])

    def browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            self.output_edit.text()
        )
        if folder:
            self.output_edit.setText(folder)

    def add_files(self, paths: list[Path]):
        for path in paths:
            if path.is_file() and path not in self.added_files:
                self.added_files.append(path)

        self.refresh_file_list()

    def refresh_file_list(self):
        self.file_table.setRowCount(len(self.added_files))

        for row, path in enumerate(self.added_files):
            self.file_table.setItem(row, 0, QTableWidgetItem(path.name))
            size_mb = path.stat().st_size / (1024 * 1024)
            self.file_table.setItem(row, 1, QTableWidgetItem(f"{size_mb:.1f} MB"))

            remove_button = QPushButton("X")
            remove_button.clicked.connect(
                lambda _, p=path: self.remove_file(p)
            )
            self.file_table.setCellWidget(row, 2, remove_button)

    def remove_file(self, path: Path):
        if path in self.added_files:
            self.added_files.remove(path)
            self.refresh_file_list()

    def clear_list(self):
        self.added_files.clear()
        self.refresh_file_list()

    # --------------------------------------------------
    # Misc
    # --------------------------------------------------
    def choose_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.log_edit.append(f"Selected color: {color.name()}")
