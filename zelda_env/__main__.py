"""Run with python -m zelda_env --help."""

import argparse
import hashlib
import io
import json
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROM = ROOT / "roms/oracle-of-ages.gbc"
AGES_SHA1 = "880374fb978b18af4aa529e2e32f7ffb4d7dd2f4"


def rom_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(
            f"ROM não encontrada: {path}. Execute .venv/bin/python scripts/build_rom.py"
        )
    digest = hashlib.sha1(path.read_bytes()).hexdigest()
    if digest != AGES_SHA1:
        raise argparse.ArgumentTypeError(
            f"ROM incompatível: SHA-1 {digest}. Esperado Oracle of Ages US: {AGES_SHA1}"
        )
    return path


def smoke(pyboy, output: Path, frames: int) -> None:
    """Exercise the real emulator, input and deterministic state restoration."""
    output.mkdir(parents=True, exist_ok=True)
    pyboy.set_emulation_speed(0)
    pyboy.tick(frames)
    pyboy.screen.image.save(output / "boot.png")
    state = io.BytesIO()
    pyboy.save_state(state)
    (output / "boot.state").write_bytes(state.getvalue())

    def replay():
        for key in ("start", "a", "right", "down"):
            pyboy.button_press(key)
            pyboy.tick(8)
            pyboy.button_release(key)
            pyboy.tick(8)
        result = io.BytesIO()
        pyboy.save_state(result)
        return result.getvalue(), pyboy.screen.ndarray.tobytes()

    first_state, first_frame = replay()
    state.seek(0)
    pyboy.load_state(state)
    second_state, second_frame = replay()
    if first_state != second_state or first_frame != second_frame:
        raise RuntimeError("Replay divergente após restaurar checkpoint")
    image = pyboy.screen.image
    image.save(output / "replay.png")
    if image.convert("RGB").getextrema() == ((0, 0), (0, 0), (0, 0)):
        raise RuntimeError("A tela final está completamente preta")
    report = {
        "rom_sha1": AGES_SHA1,
        "pyboy": version("pyboy"),
        "boot_frames": frames,
        "replay_frames": 64,
        "replay_state_equal": first_state == second_state,
        "replay_pixels_equal": first_frame == second_frame,
        "screen_size": list(image.size),
        "cartridge_title": pyboy.cartridge_title,
        "scope": "Boot, inputs and state replay; does not validate the semantic adapter",
    }
    (output / "smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"Capturas e relatório: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Oracle of Ages US — ambiente local")
    parser.add_argument("command", choices=("play", "smoke"))
    parser.add_argument("--rom", type=rom_path, default=str(DEFAULT_ROM))
    parser.add_argument("--scale", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--mute", action="store_true")
    parser.add_argument("--load-state", type=Path, help="Checkpoint PyBoy a restaurar")
    parser.add_argument("--frames", type=int, default=600, help="Frames de boot no smoke")
    parser.add_argument("--output", type=Path, default=ROOT / "output/smoke")
    args = parser.parse_args()
    if args.frames < 1:
        parser.error("--frames precisa ser positivo")
    if args.load_state and not args.load_state.is_file():
        parser.error(f"Checkpoint não encontrado: {args.load_state}")

    # Import after argument validation, so --help works without SDL startup.
    from pyboy import PyBoy

    save_dir = ROOT / "saves" / AGES_SHA1
    save_dir.mkdir(parents=True, exist_ok=True)
    # Smoke never reads/writes the player's battery save.
    ram_path = args.output.resolve() / "smoke.sav" if args.command == "smoke" else save_dir / "battery.sav"
    ram_path.parent.mkdir(parents=True, exist_ok=True)
    # Ages US has one 8 KiB SRAM bank. An explicitly empty stream is invalid
    # in PyBoy; zero-filled SRAM matches a new cartridge in this emulator.
    ram_data = ram_path.read_bytes() if args.command == "play" and ram_path.exists() else bytes(8192)
    if len(ram_data) != 8192:
        parser.error(f"Save de cartucho inválido: {ram_path} (esperado 8192 bytes)")
    ram = io.BytesIO(ram_data)
    pyboy = PyBoy(
        str(args.rom),
        ram_file=ram,
        window="null" if args.command == "smoke" else "SDL2",
        scale=args.scale,
        sound_volume=0 if args.mute or args.command == "smoke" else 50,
    )
    try:
        if args.load_state:
            with args.load_state.open("rb") as state:
                pyboy.load_state(state)
        if args.command == "smoke":
            smoke(pyboy, args.output.resolve(), args.frames)
        else:
            print("Setas: mover | A/S: A/B | Enter: Start | Backspace: Select")
            print("P: pausa | Z/X: salvar/carregar estado | Escape: sair")
            print(f"Save do jogo: {ram_path}")
            print(f"Checkpoint Z/X: {args.rom}.state")
            while pyboy.tick():
                pass
    except KeyboardInterrupt:
        pass
    finally:
        if args.command == "play":
            battery = io.BytesIO()
            pyboy.stop(save=True, ram_file=battery)
            temporary = ram_path.with_suffix(".sav.tmp")
            temporary.write_bytes(battery.getvalue())
            temporary.replace(ram_path)
        else:
            pyboy.stop(save=False)


if __name__ == "__main__":
    main()
