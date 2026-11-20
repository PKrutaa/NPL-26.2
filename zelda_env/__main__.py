"""Run with python -m zelda_env --help."""

import argparse
import hashlib
import io
import json
import platform
import signal
import sys
from importlib.metadata import version
from pathlib import Path

from . import paths
from .paths import AGES_SHA1, ROOT

SEED_ROOM, SEED_XY = "00:8a", (124, 56)


def add_common(parser):
    """Options shared by every CLI. Defaults are resolved after --data-dir is known."""
    parser.add_argument("--rom", type=Path, help="Cópia de Oracle of Ages US. Padrão: roms/ no diretório de dados")
    parser.add_argument("--data-dir", type=Path, help="Raiz de ROM, saves e saídas (ou ZELDA_ENV_DATA_DIR)")


def resolve_common(parser, args):
    paths.configure(data_dir=args.data_dir)
    try:
        args.rom = paths.validate_rom(args.rom or paths.default_rom())
    except paths.RomError as error:
        parser.exit(2, f"{error}\n")
    return args


def make_seed(pyboy, *, render=False):
    """Play from power-on to the first controllable position with normal inputs."""
    from .adapter import execute, observe

    for index in range(1500):
        if observe(pyboy).room == SEED_ROOM:
            break
        key = ("start", "a")[index % 2]
        pyboy.button_press(key)
        pyboy.tick(4, render)
        pyboy.button_release(key)
        pyboy.tick(8, render)
    else:
        raise RuntimeError("O boot não chegou à primeira sala no orçamento de frames")
    previous, stable = None, 0
    for _ in range(4000):
        pyboy.tick(4, render)
        obs = observe(pyboy)
        current = (obs.mode, obs.x, obs.y)
        stable = stable + 1 if current == previous else 0
        previous = current
        if obs.mode == "playing" and obs.y is not None and obs.y < 128 and stable > 40:
            break
        if obs.mode == "dialogue" and obs.dialogue_ready:
            pyboy.button_press("a")
            pyboy.tick(2, render)
            pyboy.button_release("a")
    else:
        raise RuntimeError("Link não ficou controlável depois da introdução")
    while obs.x < SEED_XY[0]:
        obs, event, _ = execute(pyboy, "right", render=render, hold_frames=min(12, SEED_XY[0] - obs.x))
        if event != "moved":
            break
    if (obs.mode, obs.room, obs.x, obs.y) != ("playing", SEED_ROOM, *SEED_XY):
        raise RuntimeError(f"Seed em posição inesperada: {obs.mode} {obs.room} XY {obs.x},{obs.y}")
    state = io.BytesIO()
    pyboy.save_state(state)
    return state.getvalue()


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
        "python": platform.python_version(),
        "system": f"{platform.system()} {platform.machine()}",
        "boot_frames": frames,
        "replay_frames": 64,
        "replay_state_equal": first_state == second_state,
        "replay_pixels_equal": first_frame == second_frame,
        "screen_size": list(image.size),
        "cartridge_title": pyboy.cartridge_title,
        "scope": "Boot, inputs and state replay; does not validate the semantic adapter",
    }
    (output / "smoke.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Capturas e relatório: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Oracle of Ages US — ambiente local")
    parser.add_argument("command", choices=("play", "smoke", "seed", "import-save", "where"))
    add_common(parser)
    parser.add_argument("--source", type=Path, help="Save de cartucho a copiar em import-save")
    parser.add_argument("--observe", action="store_true", help="Telemetria no título da janela em play")
    parser.add_argument("--scale", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--mute", action="store_true")
    parser.add_argument("--load-state", type=Path, help="Checkpoint PyBoy a restaurar")
    parser.add_argument("--frames", type=int, default=600, help="Frames de boot no smoke")
    parser.add_argument("--output", type=Path, help="Pasta do smoke ou arquivo .state do seed")
    args = parser.parse_args()
    paths.configure(data_dir=args.data_dir)
    if args.command == "where":
        for label, value in (("ROM", paths.default_rom()), ("Save", paths.save_path()),
                             ("Saídas", paths.output_path()), ("Cache", paths.cache_path())):
            print(f"{label}: {value}")
        return
    if args.command == "import-save":
        if not args.source:
            parser.error("import-save requer --source")
        try:
            with paths.ProfileLock(paths.save_path()):
                print(f"Save importado: {paths.import_sram(args.source)}")
        except (OSError, ValueError, paths.ProfileBusy) as error:
            parser.exit(1, f"{error}\n")
        return
    resolve_common(parser, args)
    if args.output is None:
        args.output = paths.output_path("inicio.state" if args.command == "seed" else "smoke")
    if args.frames < 1:
        parser.error("--frames precisa ser positivo")
    if args.load_state and not args.load_state.is_file():
        parser.error(f"Checkpoint não encontrado: {args.load_state}")

    # Import after argument validation, so --help works without SDL startup.
    from pyboy import PyBoy

    play = args.command == "play"
    ram_path = paths.save_path()
    lock = paths.ProfileLock(ram_path) if play else None
    try:
        # Only play reads or writes the player's battery save. Ages US has one
        # 8 KiB SRAM bank; zero-filled SRAM matches a new cartridge.
        if play:
            lock.__enter__()
        ram_data = paths.read_sram(ram_path) if play else bytes(paths.SRAM_BYTES)
    except (ValueError, paths.ProfileBusy) as error:
        parser.exit(1, f"{error}\n")
    pyboy = PyBoy(
        str(args.rom),
        ram_file=io.BytesIO(ram_data),
        window="SDL2" if play else "null",
        scale=args.scale,
        sound_volume=50 if play and not args.mute else 0,
    )
    try:
        if args.load_state:
            with args.load_state.open("rb") as state:
                pyboy.load_state(state)
        if args.command == "smoke":
            smoke(pyboy, args.output.resolve(), args.frames)
        elif args.command == "seed":
            pyboy.set_emulation_speed(0)
            state = make_seed(pyboy)
            paths.atomic_write(args.output, state)
            provenance = {
                "rom_sha1": AGES_SHA1, "pyboy": version("pyboy"), "room": SEED_ROOM, "xy": list(SEED_XY),
                "frames": pyboy.frame_count, "state_sha256": hashlib.sha256(state).hexdigest(),
                "method": "inputs from power-on: alternate Start/A, wait for control, walk right",
                "system": f"{platform.system()} {platform.machine()}", "python": platform.python_version(),
            }
            paths.atomic_write(args.output.with_suffix(".json"), (json.dumps(provenance, indent=2) + "\n").encode())
            print(f"Seed validado em {SEED_ROOM}, XY {SEED_XY[0]},{SEED_XY[1]}: {args.output}")
        else:
            print("Setas: mover | A/S: A/B | Enter: Start | Backspace: Select")
            print("P: pausa | Z/X: salvar/carregar estado | Escape: sair")
            print(f"Save do jogo: {ram_path}")
            print(f"Checkpoint Z/X: {args.rom}.state")
            if args.observe:
                from .adapter import show_status

            # PyBoy discards a KeyboardInterrupt raised inside its frame limiter, so
            # Ctrl+C and SIGTERM set a flag instead. The save is written either way.
            stop = []
            for name in ("SIGINT", "SIGTERM"):
                signal.signal(getattr(signal, name), lambda *_: stop.append(1))
            while not stop and pyboy.tick():
                if args.observe and (pyboy.paused or pyboy.frame_count % 8 == 0):
                    show_status(pyboy)
    except KeyboardInterrupt:
        pass
    except RuntimeError as error:
        print(error, file=sys.stderr)
        sys.exitcode = 1
    finally:
        if play:
            battery = io.BytesIO()
            pyboy.stop(save=True, ram_file=battery)
            try:
                if len(battery.getvalue()) == paths.SRAM_BYTES:
                    paths.atomic_write(ram_path, battery.getvalue())
            finally:
                lock.__exit__()
        else:
            pyboy.stop(save=False)
    if getattr(sys, "exitcode", 0):
        raise SystemExit(sys.exitcode)

if __name__ == "__main__":
    main()
