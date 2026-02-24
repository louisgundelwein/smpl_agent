"""Voice transcription using a local Whisper model (lazy-loaded)."""

import logging
import shutil
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)

# pip package name → import name for all transcription dependencies.
_REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("torch", "torch"),
    ("transformers", "transformers"),
    ("accelerate", "accelerate"),
    ("imageio-ffmpeg", "imageio_ffmpeg"),
]


def _ensure_dependencies() -> None:
    """Check all transcription deps are importable; pip-install any missing.

    Raises:
        RuntimeError: If pip install fails.
    """
    missing_pip: list[str] = []
    for pip_name, import_name in _REQUIRED_PACKAGES:
        try:
            __import__(import_name)
        except ImportError:
            missing_pip.append(pip_name)

    if not missing_pip:
        return

    logger.info("Installing transcription dependencies: %s", missing_pip)
    print(f"  [transcription] installing dependencies: {', '.join(missing_pip)}")

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + missing_pip,
        capture_output=True,
        text=True,
        timeout=600,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to install transcription dependencies: {result.stderr}"
        )

    # Verify they are now importable.
    for _, import_name in _REQUIRED_PACKAGES:
        __import__(import_name)

    print("  [transcription] dependencies installed successfully")


def _get_ffmpeg_exe() -> str:
    """Return the path to an ffmpeg binary.

    Prefers the system ffmpeg if available, otherwise falls back to
    the bundled binary from ``imageio-ffmpeg``.

    Raises:
        RuntimeError: If no ffmpeg binary can be found.
    """
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError(
            "ffmpeg is required for audio decoding but was not found. "
            "Install it with: pip install imageio-ffmpeg"
        )


def _decode_audio(audio_bytes: bytes) -> dict[str, Any]:
    """Decode audio bytes to a numpy array using ffmpeg.

    Pipes audio through ffmpeg to produce 16 kHz mono float32 PCM —
    the exact format Whisper expects.  Uses stdin/stdout pipes so no
    temporary files are needed.

    Returns:
        ``{"raw": np.ndarray, "sampling_rate": 16000}``
    """
    import numpy as np

    ffmpeg_exe = _get_ffmpeg_exe()

    result = subprocess.run(
        [
            ffmpeg_exe,
            "-i", "pipe:0",       # read from stdin
            "-ar", "16000",       # resample to 16 kHz
            "-ac", "1",           # mono
            "-f", "s16le",        # signed 16-bit little-endian PCM
            "pipe:1",             # write to stdout
        ],
        input=audio_bytes,
        capture_output=True,
        timeout=60,
    )

    if result.returncode != 0:
        stderr_text = result.stderr.decode(errors="replace")
        raise RuntimeError(f"ffmpeg audio decoding failed: {stderr_text}")

    # Convert raw PCM to float32 numpy array in [-1, 1] range.
    audio = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0

    return {"raw": audio, "sampling_rate": 16000}


class Transcriber:
    """Lazy-loading Whisper transcription.

    The model is downloaded from HuggingFace Hub and loaded into memory
    on the first call to transcribe(). Dependencies (torch, transformers,
    accelerate, imageio-ffmpeg) are auto-installed via pip if not present.
    """

    def __init__(self, model_name: str = "openai/whisper-large-v3-turbo") -> None:
        self._model_name = model_name
        self._pipeline: Any = None  # transformers.Pipeline, lazily created

    def _load_pipeline(self) -> Any:
        """Ensure dependencies exist, then load the ASR pipeline."""
        if self._pipeline is not None:
            return self._pipeline

        _ensure_dependencies()

        print(f"  [transcription] loading model: {self._model_name}")
        logger.info("Loading Whisper model: %s", self._model_name)

        import torch
        from transformers import pipeline

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        self._pipeline = pipeline(
            "automatic-speech-recognition",
            model=self._model_name,
            device=device,
            dtype=dtype,
        )

        print(f"  [transcription] model loaded (device={device})")
        logger.info("Whisper model loaded on %s", device)
        return self._pipeline

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes (OGG/Opus, MP3, WAV, FLAC) to text.

        Decodes audio to a numpy array via ffmpeg, then runs it through
        the Whisper pipeline.

        Args:
            audio_bytes: Raw audio file content.

        Returns:
            Transcribed text string.

        Raises:
            RuntimeError: If dependencies cannot be installed or model fails.
        """
        pipe = self._load_pipeline()
        audio_input = _decode_audio(audio_bytes)
        result = pipe(audio_input, return_timestamps=True)
        text = result.get("text", "").strip() if isinstance(result, dict) else str(result).strip()
        return text
