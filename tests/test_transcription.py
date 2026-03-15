"""Tests for src.transcription."""

import builtins
import struct
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.transcription import (
    Transcriber,
    _decode_audio,
    _ensure_dependencies,
    _get_ffmpeg_exe,
    _normalize_model_name,
)


class TestEnsureDependencies:
    """Tests for _ensure_dependencies()."""

    def test_all_present_no_pip(self, mocker):
        """When all packages are importable, no pip install runs."""
        original_import = builtins.__import__

        def allow_all(name, *args, **kwargs):
            if name in ("faster_whisper", "imageio_ffmpeg"):
                return MagicMock()
            return original_import(name, *args, **kwargs)

        mocker.patch("builtins.__import__", side_effect=allow_all)
        mock_run = mocker.patch("src.transcription.subprocess.run")

        _ensure_dependencies()

        mock_run.assert_not_called()

    def test_missing_triggers_pip(self, mocker):
        """When packages are missing, pip install is called."""
        original_import = builtins.__import__
        installed = set()

        def fake_import(name, *args, **kwargs):
            if name in ("faster_whisper", "imageio_ffmpeg"):
                if name not in installed:
                    installed.add(name)
                    raise ImportError(f"No module named '{name}'")
                return MagicMock()
            return original_import(name, *args, **kwargs)

        mocker.patch("builtins.__import__", side_effect=fake_import)
        mock_run = mocker.patch("src.transcription.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0)

        _ensure_dependencies()

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "pip" in cmd
        assert "install" in cmd
        assert "faster-whisper" in cmd
        assert "imageio-ffmpeg" in cmd

    def test_pip_failure_raises(self, mocker):
        """When pip install fails, RuntimeError is raised."""
        original_import = builtins.__import__

        def fail_import(name, *args, **kwargs):
            if name in ("faster_whisper", "imageio_ffmpeg"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        mocker.patch("builtins.__import__", side_effect=fail_import)
        mock_run = mocker.patch("src.transcription.subprocess.run")
        mock_run.return_value = MagicMock(returncode=1, stderr="error msg")

        with pytest.raises(RuntimeError, match="Failed to install"):
            _ensure_dependencies()


class TestGetFfmpegExe:
    """Tests for _get_ffmpeg_exe()."""

    def test_system_ffmpeg_preferred(self, mocker):
        """When system ffmpeg exists, it is returned."""
        mocker.patch("src.transcription.shutil.which", return_value="/usr/bin/ffmpeg")

        assert _get_ffmpeg_exe() == "/usr/bin/ffmpeg"

    def test_falls_back_to_imageio(self, mocker):
        """When no system ffmpeg, imageio-ffmpeg binary is returned."""
        mocker.patch("src.transcription.shutil.which", return_value=None)

        mock_imageio = MagicMock()
        mock_imageio.get_ffmpeg_exe.return_value = "/pkg/ffmpeg/ffmpeg.exe"
        mocker.patch.dict("sys.modules", {"imageio_ffmpeg": mock_imageio})

        assert _get_ffmpeg_exe() == "/pkg/ffmpeg/ffmpeg.exe"

    def test_raises_when_nothing_available(self, mocker):
        """When neither system nor imageio ffmpeg found, raises."""
        import sys as _sys

        mocker.patch("src.transcription.shutil.which", return_value=None)

        saved = _sys.modules.pop("imageio_ffmpeg", None)
        original_import = builtins.__import__

        def fail_import(name, *args, **kwargs):
            if name == "imageio_ffmpeg":
                raise ImportError("no imageio_ffmpeg")
            return original_import(name, *args, **kwargs)

        mocker.patch("builtins.__import__", side_effect=fail_import)

        try:
            with pytest.raises(RuntimeError, match="ffmpeg is required"):
                _get_ffmpeg_exe()
        finally:
            if saved is not None:
                _sys.modules["imageio_ffmpeg"] = saved


class TestDecodeAudio:
    """Tests for _decode_audio()."""

    def test_calls_ffmpeg_and_returns_numpy(self, mocker):
        """Decodes audio bytes via ffmpeg subprocess and returns numpy dict."""
        mocker.patch(
            "src.transcription._get_ffmpeg_exe",
            return_value="/usr/bin/ffmpeg",
        )

        # Simulate ffmpeg output: 4 samples of signed 16-bit PCM.
        pcm_data = struct.pack("<4h", 0, 16384, -16384, 32767)

        mock_run = mocker.patch("src.transcription.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0, stdout=pcm_data, stderr=b"")

        result = _decode_audio(b"fake-ogg-bytes")

        assert result["sampling_rate"] == 16000
        assert isinstance(result["raw"], np.ndarray)
        assert result["raw"].dtype == np.float32
        assert len(result["raw"]) == 4

        # Check subprocess was called with pipe args.
        cmd = mock_run.call_args[0][0]
        assert "pipe:0" in cmd
        assert "16000" in cmd

    def test_ffmpeg_failure_raises(self, mocker):
        """When ffmpeg returns non-zero, RuntimeError is raised."""
        mocker.patch(
            "src.transcription._get_ffmpeg_exe",
            return_value="/usr/bin/ffmpeg",
        )

        mock_run = mocker.patch("src.transcription.subprocess.run")
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"Unknown format",
        )

        with pytest.raises(RuntimeError, match="ffmpeg audio decoding failed"):
            _decode_audio(b"bad-audio")


class TestNormalizeModelName:
    """Tests for _normalize_model_name()."""

    def test_huggingface_format(self):
        assert _normalize_model_name("openai/whisper-large-v3-turbo") == "large-v3-turbo"

    def test_huggingface_small(self):
        assert _normalize_model_name("openai/whisper-small") == "small"

    def test_short_name_passthrough(self):
        assert _normalize_model_name("large-v3") == "large-v3"

    def test_bare_whisper_prefix(self):
        assert _normalize_model_name("whisper-tiny") == "tiny"


class TestTranscriber:
    """Tests for the Transcriber class."""

    def test_transcribe_decodes_and_calls_model(self, mocker):
        """transcribe() decodes audio, then passes result to model."""
        mocker.patch("src.transcription._ensure_dependencies")

        mock_segment = MagicMock()
        mock_segment.text = "hello world"
        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], MagicMock())

        mock_whisper_model = MagicMock(return_value=mock_model_instance)
        mock_faster_whisper = MagicMock()
        mock_faster_whisper.WhisperModel = mock_whisper_model
        mocker.patch.dict("sys.modules", {"faster_whisper": mock_faster_whisper})

        # Ensure torch is not available so we get cpu/int8.
        original_import = builtins.__import__
        def no_torch(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("no torch")
            return original_import(name, *args, **kwargs)
        mocker.patch("builtins.__import__", side_effect=no_torch)

        fake_decoded = {"raw": np.zeros(16000, dtype=np.float32), "sampling_rate": 16000}
        mocker.patch("src.transcription._decode_audio", return_value=fake_decoded)

        t = Transcriber(model_name="openai/whisper-large-v3-turbo")
        result = t.transcribe(b"fake-audio-bytes")

        assert result == "hello world"
        mock_whisper_model.assert_called_once_with("large-v3-turbo", device="cpu", compute_type="int8")
        mock_model_instance.transcribe.assert_called_once_with(fake_decoded["raw"])

    def test_model_loaded_once(self, mocker):
        """Multiple transcribe() calls reuse the same model."""
        mocker.patch("src.transcription._ensure_dependencies")

        mock_segment = MagicMock()
        mock_segment.text = "hello"
        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], MagicMock())

        mock_whisper_model = MagicMock(return_value=mock_model_instance)
        mock_faster_whisper = MagicMock()
        mock_faster_whisper.WhisperModel = mock_whisper_model
        mocker.patch.dict("sys.modules", {"faster_whisper": mock_faster_whisper})

        original_import = builtins.__import__
        def no_torch(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("no torch")
            return original_import(name, *args, **kwargs)
        mocker.patch("builtins.__import__", side_effect=no_torch)

        mocker.patch("src.transcription._decode_audio", return_value={"raw": np.zeros(1), "sampling_rate": 16000})

        t = Transcriber()
        t.transcribe(b"audio1")
        t.transcribe(b"audio2")

        # WhisperModel constructor called only once.
        mock_whisper_model.assert_called_once()
        # But model.transcribe called twice.
        assert mock_model_instance.transcribe.call_count == 2

    def test_custom_model_name_passed(self, mocker):
        """Custom model name is normalized and forwarded to WhisperModel."""
        mocker.patch("src.transcription._ensure_dependencies")

        mock_segment = MagicMock()
        mock_segment.text = "test"
        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], MagicMock())

        mock_whisper_model = MagicMock(return_value=mock_model_instance)
        mock_faster_whisper = MagicMock()
        mock_faster_whisper.WhisperModel = mock_whisper_model
        mocker.patch.dict("sys.modules", {"faster_whisper": mock_faster_whisper})

        original_import = builtins.__import__
        def no_torch(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("no torch")
            return original_import(name, *args, **kwargs)
        mocker.patch("builtins.__import__", side_effect=no_torch)

        mocker.patch("src.transcription._decode_audio", return_value={"raw": np.zeros(1), "sampling_rate": 16000})

        t = Transcriber(model_name="openai/whisper-small")
        t.transcribe(b"audio")

        mock_whisper_model.assert_called_once_with("small", device="cpu", compute_type="int8")
