"""Build the pinned public disassembly; verify vanilla US output before publishing it."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zelda_env import paths  # noqa: E402

DISASM_COMMIT = "21c924afdc8a13225e849214479d5113da2ec226"
WLA_COMMIT = "89a90a56be5c2b8cf19a9afa3e1b32384ddb1a97"
EXPECTED_SHA1 = paths.AGES_SHA1


class BuildError(SystemExit):
    pass


def resolve_toolchain():
    """Find every tool before compiling anything. Report all that are missing at once."""
    if sys.platform.startswith("win"):
        raise BuildError(
            "O build no Windows ainda não foi certificado. Use uma ROM compatível com --rom, "
            "ou gere a ROM em Linux, macOS ou WSL2 e copie o arquivo. "
            "A rota MSYS2 UCRT64 está descrita em docs/spec-portabilidade-windows-linux.md."
        )
    names = ["git", "cmake", "make", "cc", "bash"]
    tools = {name: shutil.which(name) for name in names}
    missing = [name for name, found in tools.items() if not found]
    if missing:
        hint = ("sudo apt install git cmake ninja-build gcc make" if sys.platform.startswith("linux")
                else "brew install cmake && xcode-select --install")
        raise BuildError(f"Dependência ausente: {', '.join(missing)}. Instale com: {hint}")
    tools["ninja"] = shutil.which("ninja")
    try:
        import yaml  # noqa: F401; required by upstream build scripts
    except ImportError:
        raise BuildError(f'Instale: {paths.venv_python()} -m pip install -e ".[build-rom]"')
    return tools


def tool_version(command):
    try:
        output = subprocess.run([command, "--version"], capture_output=True, text=True, timeout=10)
        return (output.stdout or output.stderr).splitlines()[0].strip()
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return None


def run(step, log, *args, cwd=None):
    """Run one build step. On failure, name the step, the command and the log."""
    command = [str(item) for item in args]
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"\n== {step}: {' '.join(command)}\n")
        stream.flush()
        result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise BuildError(f"Falha na etapa '{step}' (código {result.returncode}).\n"
                         f"Comando: {' '.join(command)}\nLog: {log}")


def checkout(tools, log, url, commit, directory):
    if not (directory / ".git").exists():
        directory.mkdir(parents=True, exist_ok=True)
        run("git init", log, tools["git"], "init", directory)
        run("git remote", log, tools["git"], "remote", "add", "origin", url, cwd=directory)
    actual = subprocess.run([tools["git"], "rev-parse", "HEAD"], cwd=directory, capture_output=True, text=True)
    if actual.returncode or actual.stdout.strip() != commit:
        run(f"fetch {directory.name}", log, tools["git"], "fetch", "--depth", "1", "origin", commit, cwd=directory)
        run(f"checkout {directory.name}", log, tools["git"], "checkout", "--detach", commit, cwd=directory)


def find_binary(build, name):
    """Use the binary the generator really produced, wherever it put it."""
    suffix = ".exe" if sys.platform.startswith("win") else ""
    for candidate in (build / "binaries" / f"{name}{suffix}", *build.rglob(f"{name}{suffix}")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise BuildError(f"O build do WLA-DX não produziu {name}{suffix} em {build}")


def export_labels(source):
    """PyBoy loads the adjacent .sym, but only understands the [labels] section."""
    labels, section = [], ""
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("["):
            section = line
        elif section == "[labels]" and line.strip() and not line.startswith(";"):
            labels.append(line)
    return ("\n".join(labels) + "\n").encode("utf-8")


def main():
    tools = resolve_toolchain()
    generator = "Ninja" if tools["ninja"] else "Unix Makefiles"
    # One cache per platform, architecture, generator and pins: a changed key rebuilds only itself.
    key = f"{platform.system()}-{platform.machine()}-{generator.split()[0]}".lower()
    cache = paths.cache_path("rom-build")
    legacy_layout = (cache / "wla-dx" / "build").exists()
    work = cache if legacy_layout else cache / key
    work.mkdir(parents=True, exist_ok=True)
    log = work / "build.log"
    log.write_text(f"build_rom {platform.platform()} python {platform.python_version()}\n", encoding="utf-8")
    wla, disasm = work / "wla-dx", work / "oracles-disasm"
    checkout(tools, log, "https://github.com/vhelin/wla-dx.git", WLA_COMMIT, wla)
    checkout(tools, log, "https://github.com/Stewmath/oracles-disasm.git", DISASM_COMMIT, disasm)
    build = wla / "build"
    configure = [tools["cmake"], "-S", wla, "-B", build, "-DCMAKE_BUILD_TYPE=Release",
                 "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"]
    if not (build / "CMakeCache.txt").exists():
        configure += ["-G", generator]  # an existing build tree keeps its generator
    run("cmake configure", log, *configure)
    jobs = str(min(os.cpu_count() or 2, 8))
    run("cmake build", log, tools["cmake"], "--build", build, "--target", "wla-gb", "wlalink", "-j", jobs)
    assembler, linker = find_binary(build, "wla-gb"), find_binary(build, "wlalink")
    for binary in (assembler, linker, Path(sys.executable)):
        if " " in str(binary):
            raise BuildError(
                f"O Makefile do disassembly não aceita espaços neste caminho: {binary}\n"
                "Defina ZELDA_ENV_CACHE_DIR para uma pasta sem espaços e rode de novo."
            )
    run("make ages", log, tools["make"], "-j", jobs, "ages", f"CPUS={jobs}", f"PYTHON={sys.executable}",
        f"CC={assembler}", f"LD={linker}", cwd=disasm)
    # The upstream Makefile checks the hash permissively. Success is defined here.
    data = (disasm / "ages.gbc").read_bytes()
    digest = hashlib.sha1(data).hexdigest()
    if digest != EXPECTED_SHA1 or len(data) != paths.ROM_BYTES:
        raise BuildError(f"Build incompatível; nada publicado. SHA-1: {digest}, {len(data)} bytes. Log: {log}")
    target = paths.default_rom()
    if target.exists() and target.read_bytes() != data:
        raise BuildError(f"Não vou sobrescrever um arquivo diferente: {target}")
    symbols = export_labels(disasm / "ages.sym")
    manifest = {
        "source": "https://github.com/Stewmath/oracles-disasm",
        "disasm_commit": DISASM_COMMIT,
        "wla_dx_commit": WLA_COMMIT,
        "rom_sha1": digest,
        "rom_bytes": len(data),
        "symbols_sha256": hashlib.sha256(symbols).hexdigest(),
        "variant": "Oracle of Ages US, vanilla",
        "system": platform.system(),
        "architecture": platform.machine(),
        "generator": generator,
        "python": platform.python_version(),
        "toolchain": {name: tool_version(found) for name, found in tools.items()
                      if found and name in ("git", "cmake", "make", "cc", "ninja")},
    }
    # Publish complete files under a lock. The manifest goes last and marks a finished set.
    with paths.ProfileLock(target):
        paths.atomic_write(target, data)
        paths.atomic_write(target.with_suffix(".sym"), symbols)
        paths.atomic_write(target.with_name("manifest.json"), (json.dumps(manifest, indent=2) + "\n").encode())
    print(f"ROM gerada e verificada: {target}\nSHA-1: {digest}")


if __name__ == "__main__":
    main()
