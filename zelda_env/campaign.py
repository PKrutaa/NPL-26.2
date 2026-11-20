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
MET_MAKU_TREE = 0x0C
RALPH_ENTERED_PORTAL = 0x40
ENTER_PAST_SCENE_DONE = 0x41
TREASURE_FLAGS = 0xC69A
WOODEN_SWORD = 0x05
SHOVEL = 0x15
PAST_ROOM_FLAGS = 0xC800
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

    def go(self, goal, **search_options):
        route = self.navigator.path(self.pyboy, goal, **search_options)
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

    def open_dialogue(self, x, y, accepted):
        room = observe(self.pyboy).room

        def opened(emulator, obs):
            if obs.room != room or abs(obs.x - x) > 20 or abs(obs.y - y) > 20:
                return False
            if obs.mode == "locked":
                obs, _, _ = execute(emulator, "wait")
            return obs.mode == "dialogue" and accepted(emulator)

        target = lambda obs: (abs(obs.x - x) + abs(obs.y - y)) / 12
        for action in self.navigator.path(self.pyboy, lambda obs: False,
                                          interaction=opened, toward=target):
            self.act(action)

    def talk(self, x, y, flag):
        if self.pyboy.memory[LISTENERS_TALKED_TO] & flag:
            return
        print(f"Clareira: procurando conversa em {x},{y}", flush=True)
        self.open_dialogue(x, y, lambda emulator: bool(emulator.memory[LISTENERS_TALKED_TO] & flag))
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

    def leave_forest(self):
        for room in ("00:49", "00:59", "00:69"):
            self.room(room)

    def reach_lynna_city(self):
        self.go(lambda obs: obs.room == "00:68",
                toward=lambda obs: (obs.x + abs(obs.y - 71)) / 12, terrain_tools=True)

    def head_north_in_lynna(self):
        self.go(lambda obs: obs.room == "00:58",
                toward=lambda obs: (abs(obs.x - 20) + obs.y) / 12)
        self.room("00:48")

    def enter_maku_path(self):
        self.go(lambda obs: obs.room == "04:04",
                toward=lambda obs: (abs(obs.x - 24) + abs(obs.y - 36)) / 12)
        self.go(lambda obs: obs.room == "04:04" and obs.mode == "dialogue")
        self.scene(lambda obs: obs.mode == "playing", quiet_steps=8)
        self.go(lambda obs: obs.room == "04:03", toward=lambda obs: obs.y / 12)

    def meet_maku_tree(self):
        for room in ("04:02", "04:01", "00:38"):
            self.go(lambda obs: obs.room == room,
                    toward=lambda obs: (obs.y + abs(obs.x - 120)) / 12)
        self.scene(lambda obs: obs.mode == "playing" and self.flag(GLOBAL_FLAGS, MET_MAKU_TREE),
                   quiet_steps=8)

    def enter_past(self):
        self.go(lambda obs: obs.room == "00:39",
                toward=lambda obs: (160 - obs.x + abs(obs.y - 53)) / 12)
        self.scene(lambda obs: obs.mode == "playing" and self.flag(GLOBAL_FLAGS, RALPH_ENTERED_PORTAL),
                   quiet_steps=8)
        self.go(lambda obs: obs.room == "00:39" and obs.mode == "locked"
                and abs(obs.x - 40) <= 8 and abs(obs.y - 40) <= 8,
                toward=lambda obs: (abs(obs.x - 40) + abs(obs.y - 40)) / 12)
        self.scene(lambda obs: obs.room == "01:39" and obs.mode == "playing"
                   and self.flag(GLOBAL_FLAGS, ENTER_PAST_SCENE_DONE), quiet_steps=8, budget=900)

    def cross_past_lynna(self):
        for room in ("01:49", "01:48", "01:58", "01:68", "01:67", "01:77"):
            self.room(room)

    def reach_black_tower(self):
        for action in self.navigator.overland(self.pyboy, "01:75", limit=6500):
            self.act(action)
        self.room("01:85")
        self.room("01:86")
        self.open_dialogue(72, 56, lambda emulator: True)
        self.scene(lambda obs: obs.mode == "playing"
                   and self.pyboy.memory[PAST_ROOM_FLAGS + 0x86] & 0x80, budget=900)

    def enter_black_tower(self):
        self.room("01:76")
        self.go(lambda obs: obs.room == "04:e7",
                toward=lambda obs: (abs(obs.x - 80) + abs(obs.y - 71)) / 12)
        self.go(lambda obs: obs.room == "04:e7" and obs.mode == "dialogue")
        self.scene(lambda obs: obs.mode == "playing", quiet_steps=8)
        self.go(lambda obs: obs.room == "04:e8",
                toward=lambda obs: (240 - obs.x + abs(obs.y - 96)) / 12)

    def get_shovel(self):
        self.go(lambda obs: obs.room == "04:e2",
                toward=lambda obs: (abs(obs.x - 176) + obs.y) / 12, limit=1300)
        self.go(lambda obs: obs.room == "04:e1",
                toward=lambda obs: (obs.x + abs(obs.y - 56)) / 12, limit=1200)
        self.open_dialogue(72, 152, lambda emulator: True)
        self.scene(lambda obs: obs.mode == "playing" and self.flag(TREASURE_FLAGS, SHOVEL),
                   quiet_steps=8, budget=700)

    def leave_black_tower(self):
        exits = (("04:e2", 239, 72), ("04:e8", 176, 175), ("04:e7", 0, 96))
        for room, x, y in exits:
            self.go(lambda obs: obs.room == room, limit=1200,
                    toward=lambda obs: (abs(obs.x - x) + abs(obs.y - y)) / 12)
        self.go(lambda obs: obs.room == "04:e7" and obs.mode == "locked" and obs.y >= 165,
                toward=lambda obs: (abs(obs.x - 120) + abs(obs.y - 170)) / 12, limit=1200)
        self.scene(lambda obs: obs.room == "01:76" and obs.mode == "playing", quiet_steps=8)

    def open_past_maku_path(self):
        for action in self.navigator.overland(self.pyboy, "01:48", limit=6500):
            self.act(action)
        self.go(lambda obs: obs.room == "01:48" and 20 <= obs.x <= 28 and obs.y >= 105,
                toward=lambda obs: (abs(obs.x - 24) + abs(obs.y - 118)) / 12)
        self.go(lambda obs: obs.room == "04:0d", limit=700, terrain_tools=True,
                toward=lambda obs: (abs(obs.x - 24) + abs(obs.y - 36)) / 8)

    def push_maku_block(self):
        self.go(lambda obs: obs.room == "04:0d" and obs.mode == "dialogue")
        self.scene(lambda obs: obs.mode == "playing", quiet_steps=8)
        self.go(lambda obs: obs.room == "04:0c", toward=lambda obs: obs.y / 12)
        self.go(lambda obs: obs.room == "04:0c" and obs.x == 120 and 80 <= obs.y <= 85
                and obs.facing == "up", toward=lambda obs: (abs(obs.x - 120) + abs(obs.y - 82)) / 12)
        self.act("up", hold_frames=48)
        self.act("wait", hold_frames=40)
        self.go(lambda obs: obs.room == "04:0a",
                toward=lambda obs: (obs.y + abs(obs.x - 120)) / 12)

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
    ("07-saida-da-floresta", Campaign.leave_forest),
    ("08-lynna-city", Campaign.reach_lynna_city),
    ("09-norte-da-cidade", Campaign.head_north_in_lynna),
    ("10-maku-path", Campaign.enter_maku_path),
    ("11-maku-tree", Campaign.meet_maku_tree),
    ("12-passado", Campaign.enter_past),
    ("13-lynna-village", Campaign.cross_past_lynna),
    ("14-black-tower", Campaign.reach_black_tower),
    ("15-black-tower-interior", Campaign.enter_black_tower),
    ("16-pa", Campaign.get_shovel),
    ("17-saida-da-torre", Campaign.leave_black_tower),
    ("18-maku-path-passado", Campaign.open_past_maku_path),
    ("19-bloco-maku", Campaign.push_maku_block),
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
