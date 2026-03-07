from typing import Optional


class ConversionSettings:
    """Holds input/output and conversion options."""

    def __init__(self) -> None:
        self.input_files: list[str] = []
        self.output_file: str = ""
        self.audio_codec: str = ""
        self.video_codec: str = ""
        self.filter_type: str = "hwfilter"
        self.hw_filter: bool = False
        self.duration: float = 0.0
