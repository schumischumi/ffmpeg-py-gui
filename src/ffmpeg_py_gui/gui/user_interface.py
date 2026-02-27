
from tkinterdnd2 import DND_FILES, TkinterDnD
import threading
import tkinter as tk
from pathlib import Path
import urllib.parse   # to handle file:// URIs
import os
import dearpygui.dearpygui as dpg

# Global state

FILE_DIALOG_TAG = "file_dialog_multi"
class UserInterface:
    """Class to manage the user interface."""
    def __init__(self):
        dpg.create_context()
        self.added_files: list[Path] = []

        dpg.add_file_dialog(
            directory_selector=False,
            show=False,
            callback=lambda sender, app_data, user_data: self.add_files(app_data["file_path_name"]),
            cancel_callback=lambda s, a: print("File dialog cancelled"),
            tag=FILE_DIALOG_TAG,
            width=750,
            height=500,
            modal=True,
        )

        # Optional: better scaling on high-DPI
        #dpg.set_global_font_scale(1.1)  # or detect DPI and adjust

        with dpg.window(tag="MainWindow", label="Converter", no_title_bar=True, no_resize=True, no_move=True):
            dpg.add_text("Two side-by-side panels (resizable)")
            dpg.add_separator()

            # Horizontal group to place children next to each other
            with dpg.group(horizontal=True):
                # Left child window
                with dpg.child_window(tag="LeftPanel", border=True, horizontal_scrollbar=True):
                    dpg.add_text("Input Files", bullet=True)
                    dpg.add_separator()

                    with dpg.table(
                        header_row=True,
                        borders_outerH=True,
                        borders_outerV=True,
                        borders_innerH=True,
                        borders_innerV=True,
                        policy=dpg.mvTable_SizingStretchProp,
                        tag="file_list_table",
                        resizable=True,
                        reorderable=False,
                        # Optional: makes it nicer
                        row_background=True,
                        height=400,
                    ):
                        # Filename – takes most space, user can resize/reorder
                        dpg.add_table_column(
                            label="Filename"
                        )

                        # Size – fixed-ish, no real need to sort or hide
                        dpg.add_table_column(
                            label="Size"
                        )

                        # Remove button column – narrow, fixed, no interaction except button
                        dpg.add_table_column(
                            label=""
                        )

                        # Initial empty table body
                        with dpg.table_row(tag="file_list"):
                            pass  # will be filled dynamically
                    #dpg.set_item_drop_callback("file_list_table", self.drop_callback)
                    dpg.add_spacer(height=8)

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Add Files...", callback=self.open_file_dialog)
                        dpg.add_button(label="Clear List", callback=lambda: (globals().update(added_files=[]), self.refresh_file_list()))


                # Right child window
                with dpg.child_window(tag="RightPanel", border=True):
                    with dpg.tab_bar(tag="RightTabs"):
                        with dpg.tab(label="Tab 1", tag="Tab1"):
                            dpg.add_text("FFmpeg Encoding Settings", bullet=True)
                            dpg.add_separator()

                            # Preset selector
                            dpg.add_combo(
                                label="Preset",
                                items=["Very Fast", "Fast", "Medium", "Slow", "Very Slow"],
                                default_value="Medium",
                                width=200,
                            )

                            dpg.add_input_int(label="CRF", default_value=23, min_value=0, max_value=51, width=120)
                            dpg.add_text("(lower = better quality, larger file)")

                            dpg.add_combo(
                                label="Codec",
                                items=["H.265 (hevc_vaapi)", "H.264 (h264_vaapi)", "AV1 (av1_vaapi)"],
                                default_value="H.265 (hevc_vaapi)",
                                width=220,
                            )

                            dpg.add_checkbox(label="Use hardware acceleration (VA-API)", default_value=True)
                            dpg.add_checkbox(label="Copy audio", default_value=True)
                            dpg.add_checkbox(label="Copy subtitles", default_value=True)

                            dpg.add_spacer(height=12)

                            dpg.add_input_text(label="Output folder", default_value=str(Path.home() / "Videos"), width=300)
                            dpg.add_button(label="Browse...", width=80)

                            dpg.add_spacer(height=20)
                            dpg.add_button(label="Start Conversion", width=180, height=40)

                            dpg.add_progress_bar(width=300, height=20, default_value=0.0, tag="progress_bar")
                            dpg.add_text("Status: Idle", tag="status_text")

                        with dpg.tab(label="Tab 2", tag="Tab2"):
                            dpg.add_text("Tab 2 – Settings / Preview")
                            dpg.add_slider_float(label="Threshold", default_value=0.5, min_value=0.0, max_value=1.0)
                            dpg.add_color_edit(label="Color", default_value=[1.0, 0.5, 0.2, 1.0])
                            dpg.add_text("Some preview area could go here...")

                        with dpg.tab(label="Tab 3", tag="Tab3"):
                            dpg.add_text("Tab 3 – Logs / Output")
                            dpg.add_input_text(label="Log", multiline=True, height=180, readonly=True)
                            dpg.add_button(label="Clear Log")
        dpg.create_viewport(title="FFmpeg VA-API Converter", width=600, height=200)
        dpg.setup_dearpygui()
        dpg.set_primary_window("MainWindow", True)
        # Register resize handler (most reliable way to react to size changes)
        with dpg.item_handler_registry(tag="resize_handler"):          # ← give it a tag here
            dpg.add_item_resize_handler(callback=self.resize_windows)

        # ... later, after creating the window ...
        dpg.bind_item_handler_registry("MainWindow", "resize_handler")
        dpg.show_viewport()

        # Initial refresh (empty list)
        self.refresh_file_list()

        dpg.start_dearpygui()
        dpg.destroy_context()

    def resize_windows(self, sender, app_data, user_data):
        """Called whenever the primary window resizes"""
        # Get current size of the parent container (primary window)
        parent_width = dpg.get_item_width("MainWindow")
        parent_height = dpg.get_item_height("MainWindow")

        # Subtract a little padding/margin if you want (optional)
        margin = 8          # small padding on sides + between children
        half_width = (parent_width - margin * 3) // 2   # roughly 50/50 split

        # Apply to both child windows (height = almost full parent height)
        dpg.configure_item("LeftPanel", width=half_width, height=parent_height - 10)
        dpg.configure_item("RightPanel", width=half_width, height=parent_height - 10)

    def add_files(self, paths: list[str]) -> None:
        """Add files to the list (called from drag & drop or file dialog)."""

        new_paths = []
        for p in paths:
            path = Path(p)
            if path.is_file() and path not in self.added_files:
                # You can add more filtering here (video extensions, size, etc.)
                if path.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts"}:
                    new_paths.append(path)

        if new_paths:
            self.added_files.extend(new_paths)
            self.refresh_file_list()


    def refresh_file_list(self) -> None:
        """Update the file list widget."""
        if not dpg.does_item_exist("file_list"):
            return

        dpg.delete_item("file_list", children_only=True)

        for path in self.added_files:
            with dpg.table_row(parent="file_list"):
                dpg.add_text(str(path.name))
                dpg.add_text(f"{path.stat().st_size / (1024*1024):.1f} MB")
                # You can add remove button later
                # dpg.add_button(label="×", callback=remove_file, user_data=path)


    def open_file_dialog(self) -> None:
        """Open system file chooser."""
        dpg.show_item(FILE_DIALOG_TAG)

    def format_size(bytes_size: int) -> str:
        """Convert bytes to human-readable size (KB/MB/GB)."""
        for unit in ['', 'K', 'M', 'G', 'T']:
            if bytes_size < 1024:
                return f"{bytes_size:.1f} {unit}B" if unit else f"{bytes_size} B"
            bytes_size /= 1024
        return f"{bytes_size:.1f} PB"


    def drop_callback(self, sender, app_data, user_data):
        """
        Handles external file/folder drops on Linux.
        app_data is typically a string: path or file:///path or newline-separated paths.
        """
        print(f"Drop received on {sender} | Raw payload: {app_data!r}")
        print(f"DROP TRIGGERED! Sender: {sender}")
        print(f"Payload type: {type(app_data)}")
        print(f"Raw payload: {app_data!r}")

        paths = []

        if isinstance(app_data, str):
            # Split by newlines (some desktop environments send multiple this way)
            raw_paths = [p.strip() for p in app_data.splitlines() if p.strip()]

            for raw in raw_paths:
                path = raw
                # Handle file:// URI (very common on GNOME/Nautilus)
                if path.startswith("file://"):
                    # Convert to local path and decode %20 → space etc.
                    path = urllib.parse.unquote(urllib.parse.urlparse(path).path)
                # Skip if not exists or invalid
                if os.path.exists(path):
                    paths.append(path)
                else:
                    print(f"Ignored invalid path: {path}")

        elif isinstance(self,app_data, (list, tuple)):
            # Rare, but in case DPG or DE sends a list
            paths = [p for p in app_data if isinstance(p, str) and os.path.exists(p)]

        else:
            print(f"Unexpected payload type: {type(app_data)}")
            return

        if not paths:
            print("No valid paths dropped")
            return

        # Now add each file/folder to the table
        for path in paths:
            try:
                size_bytes = os.path.getsize(path) if os.path.isfile(path) else 0
                display_size = self.format_size(size_bytes)
                filename = os.path.basename(path) or path  # fallback for folders/root
            except Exception as e:
                print(f"Error getting info for {path}: {e}")
                continue

            # Add a new row dynamically
            with dpg.table_row(parent="file_list_table"):
                dpg.add_text(filename)                           # Column 1: Filename
                dpg.add_text(display_size)                       # Column 2: Size
                with dpg.group(horizontal=True):                 # Column 3: Remove button placeholder
                    dpg.add_button(label="X", width=50,
                                callback=lambda s, a, u: self.remove_row(u),
                                user_data=path)  # pass path or row tag if you want to remove later

        # Optional: force table redraw / update layout if needed
        dpg.configure_item("file_list_table", show=True)


    def remove_row(self, path_or_tag):
        """Example remove callback – delete the row containing this path."""
        # For simplicity: you'd normally store row tags in a dict
        # Here just print (extend to delete_item(row_tag))
        print(f"Remove requested for: {path_or_tag}")
        # dpg.delete_item(row_tag)  # if you saved the row tag


    def start_dnd_listener(self, drop_callback):
        """
        Creates invisible Tkinter window that listens for file drops
        and forwards them to DearPyGui.
        """
        def tk_thread():
            root = TkinterDnD.Tk()
            root.withdraw()  # Hide window

            def handle_drop(event):
                files = root.tk.splitlist(event.data)
                drop_callback(files)

            root.drop_target_register(DND_FILES)
            root.dnd_bind('<<Drop>>', handle_drop)

            root.mainloop()

        thread = threading.Thread(target=tk_thread, daemon=True)
        thread.start()

    def on_external_drop(self, files):
        for path in files:
            if os.path.isdir(path):
                # optionally walk folder
                for root, dirs, filenames in os.walk(path):
                    for f in filenames:
                        self.add_file(os.path.join(root, f))
            else:
                self.add_file(path)

        self.refresh_file_list()

    def refresh_file_list(self):
        dpg.delete_item("file_list_table", children_only=True)

        # Recreate columns
        dpg.add_table_column(label="Filename", parent="file_list_table")
        dpg.add_table_column(label="Size", parent="file_list_table")
        dpg.add_table_column(label="", parent="file_list_table")

        for file in self.added_files:
            size = os.path.getsize(file)

            with dpg.table_row(parent="file_list_table"):
                dpg.add_text(os.path.basename(file))
                dpg.add_text(f"{size/1024:.1f} KB")
                dpg.add_button(label="X", callback=lambda s, a, u=file: self.remove_file(u))

    def add_file(self, path):
        if path not in self.added_files:
            self.added_files.append(path)


