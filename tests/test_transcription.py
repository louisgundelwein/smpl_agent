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
)


class TestEnsureDependencies:
    """Tests for _ensure_dependencies()."""

    def test_all_present_no_pip(self, mocker):
        """When all packages are importable, no pip install runs."""
        original_import = builtins.__import__

        def allow_all(name, *args, **kwargs):
            if name in ("torch", "transformers", "accelerate", "imageio_ffmpeg"):
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
            if name in ("torch", "transformers", "accelerate", "imageio_ffmpeg"):
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
        # Should install pip package names, not import names.
        assert "imageio-ffmpeg" in cmd

    def test_pip_failure_raises(self, mocker):
        """When pip install fails, RuntimeError is raised."""
        original_import = builtins.__import__

        def fail_import(name, *args, **kwargs):
            if name in ("torch", "transformers", "accelerate", "imageio_ffmpeg"):
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


class TestTranscriber:
    """Tests for the Transcriber class."""

    def test_transcribe_decodes_and_calls_pipeline(self, mocker):
        """transcribe() decodes audio, then passes result to pipeline."""
        mocker.patch("src.transcription._ensure_dependencies")

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.float32 = "float32"
        mocker.patch.dict("sys.modules", {"torch": mock_torch})

        mock_pipe_instance = MagicMock(return_value={"text": "hello world"})
        mock_pipeline_fn = MagicMock(return_value=mock_pipe_instance)
        mock_transformers = MagicMock()
        mock_transformers.pipeline = mock_pipeline_fn
        mocker.patch.dict("sys.modules", {"transformers": mock_transformers})

        fake_decoded = {"raw": np.zeros(16000, dtype=np.float32), "sampling_rate": 16000}
        mocker.patch("src.transcription._decode_audio", return_value=fake_decoded)

        t = Transcriber(model_name="test-model")
        result = t.transcribe(b"fake-audio-bytes")

        assert result == "hello world"
        mock_pipeline_fn.assert_called_once()
        mock_pipe_instance.assert_called_once_with(fake_decoded, return_timestamps=True)

    def test_pipeline_loaded_once(self, mocker):
        """Multiple transcribe() calls reuse the same pipeline."""
        mocker.patch("src.transcription._ensure_dependencies")

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.float32 = "float32"
        mocker.patch.dict("sys.modules", {"torch": mock_torch})

        mock_pipe_instance = MagicMock(return_value={"text": "hello"})
        mock_pipeline_fn = MagicMock(return_value=mock_pipe_instance)
        mock_transformers = MagicMock()
        mock_transformers.pipeline = mock_pipeline_fn
        mocker.patch.dict("sys.modules", {"transformers": mock_transformers})

        mocker.patch("src.transcription._decode_audio", return_value={"raw": np.zeros(1), "sampling_rate": 16000})

        t = Transcriber()
        t.transcribe(b"audio1")
        t.transcribe(b"audio2")

        # pipeline() constructor called only once.
        mock_pipeline_fn.assert_called_once()
        # But the pipeline instance called twice.
        assert mock_pipe_instance.call_count == 2

    def test_custom_model_name_passed(self, mocker):
        """Custom model name is forwarded to pipeline()."""
        mocker.patch("src.transcription._ensure_dependencies")

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.float32 = "float32"
        mocker.patch.dict("sys.modules", {"torch": mock_torch})

        mock_pipe_instance = MagicMock(return_value={"text": "test"})
        mock_pipeline_fn = MagicMock(return_value=mock_pipe_instance)
        mock_transformers = MagicMock()
        mock_transformers.pipeline = mock_pipeline_fn
        mocker.patch.dict("sys.modules", {"transformers": mock_transformers})

        mocker.patch("src.transcription._decode_audio", return_value={"raw": np.zeros(1), "sampling_rate": 16000})

        t = Transcriber(model_name="openai/whisper-small")
        t.transcribe(b"audio")

        _, kwargs = mock_pipeline_fn.call_args
        assert kwargs["model"] == "openai/whisper-small"
