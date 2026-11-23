"""Record a silent demo video of the agent playing, with its decisions and key presses.

The left side is the game. The right side shows the objective, the options the survey
found, which one was chosen and who chose it (Laya, the supervisor or a rule of the
agent), and the buttons being pressed.

  python scripts/demo_video.py --out output/demo/laya.mp4 \\
      --clip "Cubo, chave e porta trancada" output/segments/cases/chave-pequena/start.state 14 \\
      --clip "Mini-chefe Giant Ghini" output/segments/cases/giant-ghini/start.state 12

Each --clip is a title, a saved state and a number of decisions. The memory file next to
the state (start.memory.json or <name>.memory.json) is used when it exists. Needs ffmpeg.
"""

import argparse
import json
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from zelda_env import paths  # noqa: E402
from zelda_env.adapter import health, observe  # noqa: E402

WIDTH, HEIGHT, SCALE = 1180, 640, 4
GAME_AT = (24, 32)
PANEL_X = 24 + 160 * SCALE + 28
BACKGROUND, INK, DIM, ACCENT, CHOSEN, KEY_OFF, KEY_ON = (
    (16, 18, 24), (232, 234, 240), (132, 138, 152), (120, 196, 255), (255, 208, 96), (44, 48, 60), (120, 230, 150))
WHO = {
    "laya": "Laya (modelo de ação)", "supervisor": "Supervisor (LLM local)",
    "forced": "Regra do agente: única opção nova, item no chão ou plano conferido",
    "route": "Agente: mapa conhecido", "frontier": "Agente: ida a uma área com opções",
    "recipe": "Agente: receita de travessia", "sweep": "Agente: varredura", "fallback": "Agente: rodízio",
}


def font(size, mono=False):
    for name in (("Menlo.ttc", "SFNSMono.ttf", "DejaVuSansMono.ttf", "consola.ttf") if mono
                 else ("HelveticaNeue.ttc", "Helvetica.ttc", "DejaVuSans.ttf", "arial.ttf")):
        for folder in ("/System/Library/Fonts", "/usr/share/fonts/truetype/dejavu", "C:/Windows/Fonts"):
            try:
                return ImageFont.truetype(str(Path(folder) / name), size)
            except OSError:
                continue
    return ImageFont.load_default()


TITLE, TEXT, SMALL, MONO = font(23), font(18), font(15), font(15, mono=True)


class Recorder:
    """Stands in for the emulator. Every tick can become a video frame."""

    def __init__(self, pyboy, sink, every):
        self._pyboy, self._sink, self._every = pyboy, sink, every
        self._count = 0
        self.held = {}  # button -> frames it stays lit after release
        self.panel = {"title": "", "lines": []}

    def __getattr__(self, name):
        return getattr(self._pyboy, name)

    def button_press(self, name):
        self.held[name] = None
        return self._pyboy.button_press(name)

    def button_release(self, name):
        if name in self.held:
            self.held[name] = 5  # a one-frame press would not be seen otherwise
        return self._pyboy.button_release(name)

    def tick(self, count=1, render=True, sound=True):
        alive = True
        for _ in range(count):
            self._count += 1
            show = self._count % self._every == 0
            alive = self._pyboy.tick(1, show, False)
            if show:
                self.frame()
        return alive

    def frame(self, repeat=1):
        canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        game = self._pyboy.screen.image.convert("RGB").resize((160 * SCALE, 144 * SCALE), Image.NEAREST)
        canvas.paste(game, GAME_AT)
        draw = ImageDraw.Draw(canvas)
        y = 30
        for part in wrap(draw, self.panel["title"], TITLE, WIDTH - PANEL_X - 20):
            draw.text((PANEL_X, y), part, font=TITLE, fill=INK)
            y += TITLE.size + 6
        y += 10
        for kind, text in self.panel["lines"]:
            color = {"dim": DIM, "accent": ACCENT, "chosen": CHOSEN}.get(kind, INK)
            used = MONO if kind in ("option", "chosen") else SMALL if kind == "dim" else TEXT
            for part in wrap(draw, text, used, WIDTH - PANEL_X - 20):
                draw.text((PANEL_X, y), part, font=used, fill=color)
                y += used.size + 7
            y += 3
        self.keys(draw)
        data = canvas.tobytes()
        for _ in range(repeat):
            self._sink.write(data)
        for name, left in list(self.held.items()):
            if left is not None:
                self.held[name] = left - 1
                if left <= 1:
                    del self.held[name]

    def keys(self, draw):
        left, top, size = PANEL_X, HEIGHT - 150, 38
        draw.text((left, top - 30), "Botões que o agente aperta", font=SMALL, fill=DIM)
        pad = {"up": (1, 0), "left": (0, 1), "right": (2, 1), "down": (1, 2)}
        tip = {"up": ((0, -9), (-8, 6), (8, 6)), "down": ((0, 9), (-8, -6), (8, -6)),
               "left": ((-9, 0), (6, -8), (6, 8)), "right": ((9, 0), (-6, -8), (-6, 8))}
        for name, (column, row) in pad.items():
            box = (left + column * size, top + row * size, left + column * size + size - 4, top + row * size + size - 4)
            draw.rounded_rectangle(box, 6, fill=KEY_ON if name in self.held else KEY_OFF)
            middle = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
            draw.polygon([(middle[0] + dx, middle[1] + dy) for dx, dy in tip[name]],
                         fill=BACKGROUND if name in self.held else DIM)
        for index, (name, label) in enumerate((("b", "B"), ("a", "A"), ("start", "START"))):
            wide = 86 if name == "start" else 46
            x = left + 150 + sum(96 if n == "start" else 56 for n, _ in (("b", 0), ("a", 0), ("start", 0))[:index])
            box = (x, top + size, x + wide, top + size + 40)
            draw.rounded_rectangle(box, 8, fill=KEY_ON if name in self.held else KEY_OFF)
            draw.text((x + 14, top + size + 9), label, font=TEXT, fill=BACKGROUND if name in self.held else DIM)


def wrap(draw, text, used, width):
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=used) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return [*lines, line][:3]


def describe(agent, recorder, obs, hint, options, option, origin, details, name):
    """Fill the side panel for one decision."""
    hearts = health(agent.pyboy)
    lines = [("dim", f"decisão {agent.decisions + 1}  ·  sala {obs.room}  ·  vida {hearts[0] / 4:g} de {hearts[1] / 4:g}"),
             ("accent", f"Objetivo: {name}"), ("text", f"Meta dada ao modelo: {hint}"), ("dim", "Opções encontradas na sala:")]
    laya = details.get("laya") if isinstance(details.get("laya"), dict) else {}
    odds = (laya.get("answer") or {}).get("probabilities") or {}
    shown = laya.get("criteria") or {}
    if shown:
        chosen_text = option.short or option.description
        marked = False
        for key, text in list(shown.items())[:7]:
            mine = not marked and text == (chosen_text if text == chosen_text else None)
            mine = mine or (not marked and origin == "laya" and key == (laya.get("answer") or {}).get("choice"))
            marked |= mine
            chance = f"  {odds[key] * 100:.0f}%" if key in odds else ""
            lines.append(("chosen" if mine else "option", f"{'>' if mine else ' '} {text}{chance}"))
    else:
        seen = []
        for item in [option, *options]:
            text = item.short or item.description
            if (text, item.id == option.id) not in seen and len(seen) < 7:
                seen.append((text, item.id == option.id))
        for text, mine in seen:
            lines.append(("chosen" if mine else "option", f"{'>' if mine else ' '} {text}"))
    lines.append(("dim", "Quem decidiu:"))
    lines.append(("accent", WHO.get(origin, origin)))
    if details.get("reason") and origin == "supervisor":
        lines.append(("text", f"“{details['reason']}”"))
    elif origin == "laya" and (laya.get("answer") or {}).get("answer_confidence") is not None:
        lines.append(("text", f"confiança {laya['answer']['answer_confidence']:.2f}"))
    lines.append(("chosen", f"Ação: {option.description}"))
    recorder.panel["lines"] = lines


def play(recorder, args, title, state, decisions, policy, supervisor):
    from zelda_env.agent import Agent, Memory
    from zelda_env.survey import Surveyor

    with state.open("rb") as stream:
        recorder._pyboy.load_state(stream)
    memory = None
    for candidate in (state.with_name("start.memory.json"), state.with_suffix(".memory.json")):
        if candidate.is_file():
            memory = Memory.load(json.loads(candidate.read_text(encoding="utf-8")))
            break
    surveyor = Surveyor(args.rom)
    try:
        agent = Agent(recorder, surveyor, policy, supervisor=supervisor, memory=memory)
        agent.decisions = agent.memory.decisions
        recorder.panel = {"title": title, "lines": [("dim", "O levantamento simula a sala e lista o que dá para fazer.")]}
        recorder._pyboy.tick(1, True, False)
        recorder.frame(repeat=45)
        decide, current = agent.decide, {}

        def watched(obs, node, options, hint):
            option, origin, details = decide(obs, node, options, hint)
            if option is not None:
                describe(agent, recorder, obs, hint, options, option, origin, details, current.get("name") or "")
                recorder.frame(repeat=args.pause)  # time to read the decision before Link moves
            return option, origin, details

        objective = agent.objective

        def named(room=None):
            current["name"], hint = objective(room)
            return current["name"], hint

        agent.decide, agent.objective = watched, named
        target = agent.decisions + decisions
        while agent.decisions < target and agent.step():
            pass
        recorder.frame(repeat=30)
    finally:
        surveyor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--clip", nargs=3, action="append", required=True, metavar=("TITULO", "ESTADO", "DECISOES"))
    parser.add_argument("--every", type=int, default=3, help="Um quadro de vídeo a cada N quadros do jogo")
    parser.add_argument("--pause", type=int, default=24, help="Quadros de vídeo parados em cada decisão")
    parser.add_argument("--supervisor", default=None, help="Modelo Ollama. Padrão: o do agente")
    parser.add_argument("--no-supervisor", action="store_true")
    args = parser.parse_args()
    args.rom = paths.validate_rom(args.rom or paths.default_rom())
    if not shutil.which("ffmpeg"):
        parser.exit(1, "ffmpeg ausente. Instale com: brew install ffmpeg\n")

    from pyboy import PyBoy

    from zelda_env.agent import DEFAULT_SUPERVISOR
    from zelda_env.laya_policy import LayaPolicy
    from zelda_env.supervisor import OllamaBackend, Supervisor, SupervisorUnavailable

    supervisor = None
    if not args.no_supervisor:
        backend = OllamaBackend(args.supervisor or DEFAULT_SUPERVISOR)
        try:
            backend.check()
            backend.warm()
            supervisor = Supervisor(backend)
        except SupervisorUnavailable as error:
            print(f"Supervisor desligado: {error}", flush=True)
    policy = LayaPolicy("cpu", "text", False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    encoder = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}",
         "-r", "30", "-i", "-", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(args.out)],
        stdin=subprocess.PIPE)
    pyboy = PyBoy(str(args.rom), window="null", ram_file=BytesIO(bytes(paths.SRAM_BYTES)), sound_volume=0)
    pyboy.set_emulation_speed(0)
    recorder = Recorder(pyboy, encoder.stdin, args.every)
    try:
        for title, state, decisions in args.clip:
            play(recorder, args, title, Path(state), int(decisions), policy, supervisor)
    finally:
        encoder.stdin.close()
        encoder.wait()
        pyboy.stop(save=False)
    print(f"Vídeo: {args.out}")


if __name__ == "__main__":
    main()
