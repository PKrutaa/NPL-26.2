import hashlib
import os
from pathlib import Path

import pytest

from zelda_env import paths


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(paths, "_explicit", {})
    monkeypatch.delenv("ZELDA_ENV_DATA_DIR", raising=False)
    monkeypatch.delenv("ZELDA_ENV_CACHE_DIR", raising=False)


def test_native_dirs_per_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "_home", lambda: tmp_path)
    windows = paths.native_dir("data", platform="win32", environ={"LOCALAPPDATA": str(tmp_path / "Local")})
    assert windows == tmp_path / "Local" / "zelda-env" / "data"
    assert paths.native_dir("cache", platform="win32", environ={}) == tmp_path / "AppData/Local/zelda-env/cache"
    assert paths.native_dir("data", platform="linux", environ={}) == tmp_path / ".local/share/zelda-env"
    xdg = paths.native_dir("cache", platform="linux", environ={"XDG_CACHE_HOME": str(tmp_path / "x")})
    assert xdg == tmp_path / "x" / "zelda-env"
    # The XDG spec says relative values are ignored.
    assert paths.native_dir("data", platform="linux", environ={"XDG_DATA_HOME": "rel"}) == tmp_path / ".local/share/zelda-env"
    assert paths.native_dir("data", platform="darwin", environ={}) == tmp_path / "Library/Application Support/zelda-env"
    assert paths.native_dir("data", platform="darwin") != paths.native_dir("cache", platform="darwin")


def test_precedence_explicit_env_legacy_native(monkeypatch, tmp_path):
    native, legacy = tmp_path / "native", tmp_path / "checkout"
    monkeypatch.setattr(paths, "native_dir", lambda kind, **_: native / kind)
    monkeypatch.setattr(paths, "ROOT", legacy)
    assert paths.data_path("roms", "a.gbc") == native / "data/roms/a.gbc"
    (legacy / "roms").mkdir(parents=True)
    assert paths.data_path("roms", "a.gbc") == legacy / "roms/a.gbc"
    # One tree never splits: a new file under an existing legacy folder stays there.
    assert paths.data_path("roms", "new.sym") == legacy / "roms/new.sym"
    (native / "data/roms").mkdir(parents=True)
    assert paths.data_path("roms", "a.gbc") == native / "data/roms/a.gbc"
    monkeypatch.setenv("ZELDA_ENV_DATA_DIR", str(tmp_path / "env dir ç"))
    assert paths.data_path("roms", "a.gbc") == (tmp_path / "env dir ç").resolve() / "roms/a.gbc"
    paths.configure(data_dir=tmp_path / "explicit")
    assert paths.data_path("roms", "a.gbc") == (tmp_path / "explicit").resolve() / "roms/a.gbc"


def test_rom_validation_reports_cause_and_keeps_file(monkeypatch, tmp_path):
    with pytest.raises(paths.RomError, match="não encontrada"):
        paths.validate_rom(tmp_path / "missing.gbc")
    short = tmp_path / "short.gbc"
    short.write_bytes(b"x" * 10)
    with pytest.raises(paths.RomError, match="10 bytes"):
        paths.validate_rom(short)
    wrong = tmp_path / "pasta com espaço é" / "wrong.bin"
    wrong.parent.mkdir()
    wrong.write_bytes(bytes(paths.ROM_BYTES))
    with pytest.raises(paths.RomError, match="SHA-1"):
        paths.validate_rom(wrong)
    assert wrong.read_bytes() == bytes(paths.ROM_BYTES)
    # Identified by content: any name or extension, read-only, relative path.
    data = bytes(paths.ROM_BYTES)
    monkeypatch.setattr(paths, "AGES_SHA1", hashlib.sha1(data).hexdigest())
    wrong.chmod(0o444)
    monkeypatch.chdir(wrong.parent)
    assert paths.validate_rom("wrong.bin") == wrong
    assert sorted(item.name for item in wrong.parent.iterdir()) == ["wrong.bin"]


def test_atomic_write_keeps_last_good_file(monkeypatch, tmp_path):
    target = tmp_path / "battery.sav"
    paths.atomic_write(target, b"one")
    assert target.read_bytes() == b"one"

    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        paths.atomic_write(target, b"two")
    assert target.read_bytes() == b"one"
    assert [item.name for item in tmp_path.iterdir()] == ["battery.sav"]


def test_atomic_write_retries_windows_sharing_violation(monkeypatch, tmp_path):
    target = tmp_path / "battery.sav"
    real, calls = os.replace, []

    def flaky(source, destination):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("in use")
        real(source, destination)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr(paths.time, "sleep", lambda _: None)
    paths.atomic_write(target, b"data")
    assert target.read_bytes() == b"data" and len(calls) == 3


def test_sram_size_and_import(tmp_path):
    assert paths.read_sram(tmp_path / "none.sav") == bytes(paths.SRAM_BYTES)
    bad = tmp_path / "bad.sav"
    bad.write_bytes(b"123")
    with pytest.raises(ValueError, match="8192"):
        paths.read_sram(bad)
    source, active = tmp_path / "old.sav", tmp_path / "profile" / "battery.sav"
    source.write_bytes(b"\x01" * paths.SRAM_BYTES)
    paths.atomic_write(active, b"\x02" * paths.SRAM_BYTES)
    paths.import_sram(source, active)
    assert active.read_bytes() == source.read_bytes() == b"\x01" * paths.SRAM_BYTES
    backups = list(active.parent.glob("battery.sav.*.bak"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"\x02" * paths.SRAM_BYTES
    with pytest.raises(ValueError):
        paths.import_sram(bad, active)
    assert active.read_bytes() == b"\x01" * paths.SRAM_BYTES


def test_second_writer_is_refused_and_stale_lock_is_replaced(tmp_path):
    target = tmp_path / "battery.sav"
    with paths.ProfileLock(target):
        with pytest.raises(paths.ProfileBusy, match="PID"):
            paths.ProfileLock(target).__enter__()
    assert not Path(str(target) + ".lock").exists()
    Path(str(target) + ".lock").write_text("999999999")  # no such process
    with paths.ProfileLock(target):
        assert Path(str(target) + ".lock").read_text() == str(os.getpid())
