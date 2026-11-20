"""Locate ROM, saves, caches and outputs; write files without losing the last good copy."""

import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = "zelda-env"
AGES_SHA1 = "880374fb978b18af4aa529e2e32f7ffb4d7dd2f4"
ROM_BYTES = 1_048_576
SRAM_BYTES = 8192
ROM_NAME = "oracle-of-ages.gbc"

_explicit = {}


class RomError(ValueError):
    pass


class ProfileBusy(RuntimeError):
    pass


def configure(data_dir=None, cache_dir=None):
    """Record --data-dir/--cache-dir for this process. They win over the environment."""
    for key, value in (("data", data_dir), ("cache", cache_dir)):
        if value:
            _explicit[key] = Path(value).expanduser().resolve()


def _home():
    return Path.home()


def native_dir(kind, *, platform=None, environ=None):
    """Per-user directory for persistent data or for a cache that can be deleted."""
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    if platform.startswith("win"):
        base = environ.get("LOCALAPPDATA")
        base = Path(base) if base else _home() / "AppData" / "Local"
        return base / APP / kind
    if platform == "darwin":
        folder = "Application Support" if kind == "data" else "Caches"
        return _home() / "Library" / folder / APP
    variable, fallback = (
        ("XDG_DATA_HOME", ".local/share") if kind == "data" else ("XDG_CACHE_HOME", ".cache")
    )
    base = environ.get(variable)
    # The XDG spec ignores relative values.
    base = Path(base) if base and Path(base).is_absolute() else _home() / fallback
    return base / APP


def _override(kind):
    if kind in _explicit:
        return _explicit[kind]
    value = os.environ.get(f"ZELDA_ENV_{kind.upper()}_DIR")
    return Path(value).expanduser().resolve() if value else None


def data_path(*parts):
    """Resolve one resource: explicit root, environment, legacy checkout data, native."""
    override = _override("data")
    if override:
        return override.joinpath(*parts)
    # Decide per top-level folder (roms, saves, output), so one tree never splits.
    head = parts[:1]
    native = native_dir("data")
    if head and not native.joinpath(*head).exists() and ROOT.joinpath(*head).exists():
        return ROOT.joinpath(*parts)
    return native.joinpath(*parts)


def cache_path(*parts):
    override = _override("cache")
    if override:
        return override.joinpath(*parts)
    native = native_dir("cache")
    if not native.exists() and (ROOT / ".cache").exists():
        return ROOT.joinpath(".cache", *parts)
    return native.joinpath(*parts)


def default_rom():
    return data_path("roms", ROM_NAME)


def save_path():
    return data_path("saves", AGES_SHA1, "battery.sav")


def output_path(*parts):
    return data_path("output", *parts)


def venv_python():
    """The command users should type on this system, for help and error messages."""
    if sys.platform.startswith("win"):
        return r".\.venv\Scripts\python.exe"
    return ".venv/bin/python"


def validate_rom(path):
    """Accept only Oracle of Ages US vanilla. Identify the file by content, not by name."""
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        raise RomError(
            f"ROM não encontrada: {path}. Passe --rom com o caminho de uma cópia de Oracle of Ages US "
            f"ou gere uma com: {venv_python()} scripts/build_rom.py"
        )
    size = path.stat().st_size
    if size != ROM_BYTES:
        raise RomError(f"ROM incompatível: {path} tem {size} bytes. Esperado: {ROM_BYTES}.")
    digest = hashlib.sha1(path.read_bytes()).hexdigest()
    if digest != AGES_SHA1:
        raise RomError(
            f"ROM incompatível: SHA-1 {digest}. Esperado Oracle of Ages US: {AGES_SHA1}. "
            "O arquivo não foi alterado."
        )
    return path


def atomic_write(path, data, *, attempts=5):
    """Publish complete bytes under the final name. Keep the previous file if anything fails."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(attempts):
            try:
                os.replace(temporary, path)
                return path
            except PermissionError:
                # Windows refuses the replace while another process has the target open.
                if attempt == attempts - 1:
                    raise
                time.sleep(0.1 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def read_sram(path):
    """Return the battery save, or a new cartridge if the file does not exist."""
    path = Path(path)
    if not path.exists():
        return bytes(SRAM_BYTES)
    data = path.read_bytes()
    if len(data) != SRAM_BYTES:
        raise ValueError(f"Save de cartucho inválido: {path} ({len(data)} bytes, esperado {SRAM_BYTES})")
    return data


def import_sram(source, destination=None):
    """Copy a validated save into the active profile. The source stays untouched."""
    data = read_sram(source)
    if not Path(source).exists():
        raise FileNotFoundError(f"Save não encontrado: {source}")
    destination = Path(destination) if destination else save_path()
    if destination.exists() and destination.read_bytes() != data:
        backup = destination.with_name(f"{destination.name}.{time.strftime('%Y%m%d-%H%M%S')}.bak")
        atomic_write(backup, destination.read_bytes())
    return atomic_write(destination, data)


def _alive(pid):
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class ProfileLock:
    """Allow one writer per save profile. A lock left by a dead process is replaced."""

    def __init__(self, target):
        self.path = Path(target).with_name(Path(target).name + ".lock")
        self.held = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    owner = int(self.path.read_text().strip() or 0)
                except (OSError, ValueError):
                    owner = 0
                if _alive(owner):
                    raise ProfileBusy(
                        f"Outro processo (PID {owner}) está usando este save: {self.path.parent}. "
                        "Feche a outra janela do jogo e tente de novo."
                    )
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(handle, "w") as stream:
                stream.write(str(os.getpid()))
            self.held = True
            return self
        raise ProfileBusy(f"Não foi possível obter o lock do save: {self.path}")

    def __exit__(self, *_):
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False
