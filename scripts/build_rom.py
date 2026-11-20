"""Build the pinned public disassembly; verify vanilla US output before copying."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache/rom-build"
DISASM_COMMIT = "21c924afdc8a13225e849214479d5113da2ec226"
WLA_COMMIT = "89a90a56be5c2b8cf19a9afa3e1b32384ddb1a97"
EXPECTED_SHA1 = "880374fb978b18af4aa529e2e32f7ffb4d7dd2f4"


def run(*args, cwd=None):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def checkout(url, commit, directory):
    if not directory.exists():
        directory.mkdir(parents=True)
        run("git", "init", directory)
        run("git", "remote", "add", "origin", url, cwd=directory)
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=directory, capture_output=True, text=True
    )
    if actual.returncode or actual.stdout.strip() != commit:
        run("git", "fetch", "--depth", "1", "origin", commit, cwd=directory)
        run("git", "checkout", "--detach", commit, cwd=directory)


def main():
    for command in ("git", "cmake", "make", "cc"):
        if not shutil.which(command):
            raise SystemExit(f"Dependência ausente: {command}. Consulte README.md")
    try:
        import yaml  # noqa: F401; required by upstream build scripts
    except ImportError:
        raise SystemExit('Instale: .venv/bin/python -m pip install -e ".[build-rom]"')
    CACHE.mkdir(parents=True, exist_ok=True)
    wla = CACHE / "wla-dx"
    disasm = CACHE / "oracles-disasm"
    checkout("https://github.com/vhelin/wla-dx.git", WLA_COMMIT, wla)
    checkout("https://github.com/Stewmath/oracles-disasm.git", DISASM_COMMIT, disasm)
    build = wla / "build"
    run("cmake", "-S", wla, "-B", build, "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_POLICY_VERSION_MINIMUM=3.5")
    jobs = str(min(os.cpu_count() or 2, 8))
    run("cmake", "--build", build, "--target", "wla-gb", "wlalink", "-j", jobs)
    run("make", "-j", jobs, "ages", f"CPUS={jobs}", f"PYTHON={sys.executable}",
        f"CC={build / 'binaries/wla-gb'}", f"LD={build / 'binaries/wlalink'}", cwd=disasm)
    rom = disasm / "ages.gbc"
    data = rom.read_bytes()
    digest = hashlib.sha1(data).hexdigest()
    if digest != EXPECTED_SHA1:
        raise SystemExit(f"Build incompatível; nada copiado. SHA-1: {digest}")
    destination = ROOT / "roms"
    destination.mkdir(exist_ok=True)
    target = destination / "oracle-of-ages.gbc"
    if target.exists() and target.read_bytes() != data:
        raise SystemExit(f"Não vou sobrescrever um arquivo diferente: {target}")
    shutil.copy2(rom, target)
    # PyBoy auto-loads the adjacent .sym, but WLA's metadata/section records
    # aren't BGB symbol records. Export only the [labels] section.
    labels = []
    section = ""
    for line in (disasm / "ages.sym").read_text().splitlines():
        if line.startswith("["):
            section = line
        elif section == "[labels]" and line.strip() and not line.startswith(";"):
            labels.append(line)
    (destination / "oracle-of-ages.sym").write_text("\n".join(labels) + "\n")
    manifest = {
        "source": "https://github.com/Stewmath/oracles-disasm",
        "disasm_commit": DISASM_COMMIT,
        "wla_dx_commit": WLA_COMMIT,
        "rom_sha1": digest,
        "rom_bytes": len(data),
        "variant": "Oracle of Ages US, vanilla",
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"ROM gerada e verificada: {target}\nSHA-1: {digest}")


if __name__ == "__main__":
    main()
