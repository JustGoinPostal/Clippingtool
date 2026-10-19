from __future__ import annotations

import subprocess

import pytest

from app.media import run_ffmpeg


def test_run_ffmpeg_ignores_successful_udta_warning(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="[mov,mp4] UDTA parsing failed retrying raw\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_ffmpeg(["ffmpeg", "-i", "input.mp4"], label="Render short")
    assert result.returncode == 0


def test_run_ffmpeg_surfaces_real_error_and_filters_udta_noise(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr=(
                "[mov,mp4] UDTA parsing failed retrying raw\n"
                "[Parsed_ass_0] Could not create a libass track\n"
                "Error while processing the decoded data\n"
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        run_ffmpeg(["ffmpeg", "-i", "input.mp4"], label="Render short")
    message = str(exc.value)
    assert "UDTA parsing failed" not in message
    assert "Could not create a libass track" in message
    assert "exit code 1" in message
