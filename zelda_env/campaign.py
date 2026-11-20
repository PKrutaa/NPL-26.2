"""Advance a local, isolated playthrough with room goals and controller input."""

import argparse
from functools import partial
from io import BytesIO
from pathlib import Path

from .__main__ import DEFAULT_ROM, ROOT, rom_path
from .adapter import execute, observe, show_status
from .lookahead import Lookahead

# Ages US, as documented in the disassembly used to build the ROM.
CUTSCENE_PHASE = 0xCFD0
LISTENERS_TALKED_TO = 0xCFDE
GLOBAL_FLAGS = 0xC6D0
INTRO_DONE = 0x0A
TREASURE_FLAGS = 0xC69A
WOODEN_SWORD = 0x05
IMPA_SUBSTATE = (1, 0xD245)
TEXT_DISPLAY_STATE = (7, 0xD0C0)


class Campaign:
    def __init__(self, pyboy, navigator, policy, watch):
        self.pyboy = pyboy
        self.navigator = navigator
        self.policy = policy
        self.watch = watch

    def flag(self, base, index):
        return bool(self.pyboy.memory[base + index // 8] & (1 << index % 8))

    def act(self, action, *, hold_frames=12):
        after, event, _ = execute(self.pyboy, action, render=self.watch, hold_frames=hold_frames)
        if self.watch:
            show_status(self.pyboy, f"Campanha | {action} | {event}")
        return after

    def go(self, goal):
        route = self.navigator.path(self.pyboy, goal)
        for action in route:
            self.act(action)
        if not goal(observe(self.pyboy)):
            raise RuntimeError("A rota prevista divergiu no emulador principal")

    def room(self, room):
        self.go(lambda obs: obs.room == room)

    def scene(self, done, *, budget=320, quiet_steps=0):
        stable = 0
        for _ in range(budget):
            obs = observe(self.pyboy)
            stable = stable + 1 if done(obs) else 0
            if stable > quiet_steps:
                return
            action = "wait"
            text_state = self.pyboy.memory[TEXT_DISPLAY_STATE]
            if obs.mode == "dialogue" and (obs.dialogue_ready or text_state in (2, 4, 10)):
                action = "interact"
                if obs.dialogue_ready and self.policy:
                    action, _ = self.policy(
                        "Continue the current story dialogue. Confirm and advance the text.",
                        obs, ("interact", "cancel"), (),
                    )
            self.act(action)
        raise RuntimeError("A cena não terminou dentro do orçamento")

    def talk(self, x, y, flag):
        if self.pyboy.memory[LISTENERS_TALKED_TO] & flag:
            return

        def spoken(emulator, obs):
            if obs.room != "00:39" or abs(obs.x - x) > 20 or abs(obs.y - y) > 20:
                return False
            if obs.mode == "locked":
                obs, _, _ = execute(emulator, "wait")
            return bool(emulator.memory[LISTENERS_TALKED_TO] & flag)

        print(f"Clareira: procurando conversa em {x},{y}", flush=True)
        route = self.navigator.path(self.pyboy, lambda obs: False, interaction=spoken)
        for action in route:
            self.act(action)
        self.scene(lambda obs: obs.mode == "playing" and bool(self.pyboy.memory[LISTENERS_TALKED_TO] & flag),
                   quiet_steps=8)

    def clear_nayru_scene(self):
        # The bear moves aside after hearing from the other listeners.
        for x, y, flag in ((72, 44, 1), (104, 72, 4), (136, 80, 2), (120, 80, 8), (88, 56, 16)):
            self.talk(x, y, flag)
        self.go(lambda obs: obs.room == "00:39" and obs.x >= 96 and obs.y < 62)
        self.scene(lambda obs: obs.mode == "playing" and self.flag(GLOBAL_FLAGS, INTRO_DONE),
                   budget=1800)
        if not self.flag(TREASURE_FLAGS, WOODEN_SWORD):
            raise RuntimeError("Introdução concluída sem a espada esperada no jogo não vinculado")

    def meet_impa(self):
        self.room("00:7a")
        self.go(lambda obs: obs.room == "00:7a" and obs.mode == "playing" and obs.y <= 10)
        self.act("up")
        self.scene(lambda obs: obs.room == "00:6a" and obs.mode == "playing")

    def approach_stone(self):
        self.room("00:5a")
        self.room("00:59")
        self.go(lambda obs: obs.room == "00:59" and obs.x < 120 and obs.y < 88)
        self.scene(lambda obs: obs.mode == "playing" and self.pyboy.memory[CUTSCENE_PHASE] == 4)

    def push_stone(self):
        self.go(lambda obs: obs.room == "00:59" and 66 <= obs.x <= 75 and 32 <= obs.y <= 45)
        obs = observe(self.pyboy)
        if not 35 <= obs.y <= 41:
            self.act("down" if obs.y < 38 else "up", hold_frames=abs(38 - obs.y))
        self.act("left", hold_frames=60)
        self.scene(lambda obs: obs.mode == "playing" and self.pyboy.memory[IMPA_SUBSTATE] == 0x0D)


STAGES = (
    ("01-impa", Campaign.meet_impa),
    ("02-pedra", Campaign.approach_stone),
    ("03-pedra-movida", Campaign.push_stone),
    ("04-caminho-da-floresta", partial(Campaign.room, room="00:49")),
    ("05-clareira", partial(Campaign.room, room="00:39")),
    ("06-nayru", Campaign.clear_nayru_scene),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=rom_path, default=str(DEFAULT_ROM))
    parser.add_argument("--seed-state", type=Path, default=ROOT / "output/scenarios/exit.state")
    parser.add_argument("--directory", type=Path, default=ROOT / "output/campaign")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--script-dialogue", action="store_true")
    args = parser.parse_args()

    from pyboy import PyBoy

    pyboy = PyBoy(
        str(args.rom), window="null" if args.headless else "SDL2",
        ram_file=BytesIO(bytes(8192)), sound_volume=0,
    )
    pyboy.set_emulation_speed(0 if args.headless else 2)
    navigator = Lookahead(args.rom)
    try:
        policy = None
        if not args.script_dialogue:
            from .laya_policy import LayaPolicy

            policy = LayaPolicy("cpu", "text", False)
        campaign = Campaign(pyboy, navigator, policy, not args.headless)
        args.directory.mkdir(parents=True, exist_ok=True)
        start = args.seed_state
        pending = STAGES
        for index, (name, _) in reversed(list(enumerate(STAGES))):
            checkpoint = args.directory / f"{name}.state"
            if checkpoint.exists():
                start = checkpoint
                pending = STAGES[index + 1:]
                break
        with start.open("rb") as stream:
            pyboy.load_state(stream)
        print(f"Campanha carregada de {start}", flush=True)
        for name, stage in pending:
            print(f"Em andamento: {name}", flush=True)
            stage(campaign)
            checkpoint = args.directory / f"{name}.state"
            temporary = checkpoint.with_suffix(".tmp")
            with temporary.open("wb") as stream:
                pyboy.save_state(stream)
            temporary.replace(checkpoint)
            obs = observe(pyboy)
            print(f"Marco salvo: {name} | {obs.room} | X={obs.x} Y={obs.y}", flush=True)
        if not args.headless:
            print("Último marco implementado. A janela continua aberta.", flush=True)
            while pyboy.tick():
                if pyboy.frame_count % 16 == 0:
                    show_status(pyboy, "Campanha | checkpoint")
    except (InterruptedError, KeyboardInterrupt):
        pass
    finally:
        navigator.close()
        pyboy.stop(save=False)


if __name__ == "__main__":
    main()
