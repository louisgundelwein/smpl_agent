"""Voice transcription using a local Whisper model (lazy-loaded)."""

import logging
import shutil
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)

# pip package name → import name for all transcription dependencies.
_REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("faster-whisper", "faster_whisper"),
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
        [sys.executable, "-m", "pip", "install", "--break-system-packages"] + missing_pip,
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


def _normalize_model_name(model_name: str) -> str:
    """Map HuggingFace-style model names to faster-whisper short names.

    Examples:
        ``"openai/whisper-large-v3-turbo"`` → ``"large-v3-turbo"``
        ``"openai/whisper-small"`` → ``"small"``
        ``"large-v3"`` → ``"large-v3"`` (pass-through)
    """
    # Strip HuggingFace org/whisper- prefix if present.
    if "/" in model_name:
        model_name = model_name.split("/", 1)[1]
    if model_name.startswith("whisper-"):
        model_name = model_name[len("whisper-"):]
    return model_name


class Transcriber:
    """Lazy-loading Whisper transcription using faster-whisper.

    The model is downloaded and loaded into memory on the first call
    to transcribe(). Dependencies (faster-whisper, imageio-ffmpeg) are
    auto-installed via pip if not present.
    """

    def __init__(self, model_name: str = "openai/whisper-large-v3-turbo") -> None:
        self._model_name = model_name
        self._model: Any = None  # faster_whisper.WhisperModel, lazily created

    def _load_model(self) -> Any:
        """Ensure dependencies exist, then load the WhisperModel."""
        if self._model is not None:
            return self._model

        _ensure_dependencies()

        short_name = _normalize_model_name(self._model_name)
        print(f"  [transcription] loading model: {short_name}")
        logger.info("Loading Whisper model: %s", short_name)

        from faster_whisper import WhisperModel

        try:
            import torch
            cuda_available = torch.cuda.is_available()
        except ImportError:
            cuda_available = False

        if cuda_available:
            device, compute_type = "cuda", "float16"
        else:
            device, compute_type = "cpu", "int8"

        self._model = WhisperModel(short_name, device=device, compute_type=compute_type)

        print(f"  [transcription] model loaded (device={device})")
        logger.info("Whisper model loaded on %s", device)
        return self._model

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes (OGG/Opus, MP3, WAV, FLAC) to text.

        Decodes audio to a numpy array via ffmpeg, then runs it through
        the faster-whisper model.

        Args:
            audio_bytes: Raw audio file content.

        Returns:
            Transcribed text string.

        Raises:
            RuntimeError: If dependencies cannot be installed or model fails.
        """
        model = self._load_model()
        audio_input = _decode_audio(audio_bytes)
        segments, _info = model.transcribe(audio_input["raw"])
        text = " ".join(seg.text for seg in segments).strip()
        return text
