from pathlib import Path

from app.media import _filter_filename


def test_ffmpeg_filter_filename_escapes_windows_drive_colon():
    value = _filter_filename(Path(r"C:\PostalAutoClip\data\cache\abc\energy.txt"))
    assert value == r"C\:/PostalAutoClip/data/cache/abc/energy.txt"


def test_ffmpeg_filter_filename_escapes_single_quote():
    value = _filter_filename(Path("/tmp/postal's/energy.txt"))
    assert value == r"/tmp/postal\'s/energy.txt"
