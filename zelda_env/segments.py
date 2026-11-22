"""Test the agent on one stretch of the game at a time.

A full run from boot takes about an hour to reach the later objectives. Two kinds of
shorter test start from a saved game state plus the agent memory saved with it:

- A segment goes from one completed objective to the next.
- A case goes from any saved point (for example the one the agent writes when it cuts a
  loop) to an objective or a room.

  python -m zelda_env.segments list
  python -m zelda_env.segments capture output/agent-limpa
  python -m zelda_env.segments run chave-do-cemiterio --decisions 150
  python -m zelda_env.segments run all --jobs 5
  python -m zelda_env.segments run pa maku-tree-salva --jobs 2
  python -m zelda_env.segments case-add pergunta-maku --state output/agent/falha-260.state \\
      --until-room 00:48 --decisions 30
  python -m zelda_env.segments case-add portao --run output/agent --decision 361 \\
      --until dungeon-1 --decisions 40
  python -m zelda_env.segments case-run all --jobs 4
  python -m zelda_env.segments inspect output/agent/pontos/00360.state
  python -m zelda_env.segments report

Everything lives in output/segments. A test passes when it reaches its target within the
budget with no loop cut and no impasse. The exit code is 1 when any test does not pass.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import paths
from .__main__ import add_common, resolve_common

REPEAT_MOVES = 4  # a stretch made of at most this many distinct moves counts as repetition
PASSED = "passou"


def names():
    from .agent import OBJECTIVES

    return [item[0] for item in OBJECTIVES]


def metrics(trace):
    """Loop figures of one trace: events, origins and the longest repetitive stretch."""
    decisions, events = [], Counter()
    for line in Path(trace).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if "decision" in record:
            decisions.append(record)
        elif record.get("event"):
            events[record["event"]] += 1
    moves = [(record["node"], record["choice"]) for record in decisions]
    longest = start = 0
    for end in range(len(moves)):
        while len(set(moves[start:end + 1])) > REPEAT_MOVES:
            start += 1
        longest = max(longest, end - start + 1)
    survey = [record["survey_s"] for record in decisions]
    return {
        "decisions": len(decisions),
        "reached": [name for record in decisions for name in record["reached"]],
        "rooms": list(dict.fromkeys(record["after_room"] for record in decisions if record.get("after_room"))),
        "loop_cuts": events["loop_cut"], "impasses": events["impasse"],
        "dropped": sum(record["outcome"].startswith("failed") for record in decisions),
        "longest_repeat": longest if len(moves) > REPEAT_MOVES else 0,
        "most_repeated": [[*move, count] for move, count in Counter(moves).most_common(3)],
        "origins": dict(Counter(record["origin"] for record in decisions)),
        "survey_s": round(sum(survey) / len(survey), 1) if survey else 0.0,
    }


def verdict(result, until=None, until_room=None, no_drops=False):
    """Passing needs the target reached and nothing that signals a loop.

    With `no_drops`, an option dropped because Link died or lost control also fails it.
    """
    done = until in result["reached"] if until else until_room in result["rooms"]
    clean = not result["loop_cuts"] and not result["impasses"] and not (no_drops and result["dropped"])
    return PASSED if done and clean else "concluiu com ciclo" if done else "não concluiu"


def revision():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=paths.ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def checkpoint(directory, name):
    return directory / f"{name}.state", directory / f"{name}.memory.json"


def capture(directory, session, replace=False):
    """Copy the checkpoints a session saved at each objective. Returns the names copied."""
    copied = []
    for name in names():
        state = session / f"objetivo-{name}.state"
        memory = session / f"objetivo-{name}.memory.json"
        target_state, target_memory = checkpoint(directory, name)
        if state.is_file() and memory.is_file() and (replace or not target_memory.is_file()):
            directory.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(state, target_state)
            shutil.copyfile(memory, target_memory)
            copied.append(name)
    return copied


def play(label, session, args, *, state=None, memory=None, until=None, until_room=None, decisions=200,
         no_drops=False):
    """Run the agent once from a saved point to a target and return what happened."""
    command = [sys.executable, "-m", "zelda_env.agent", "--headless", "--fresh",
               "--decisions", str(decisions), "--policy", args.policy,
               "--directory", str(session), "--rom", str(args.rom)]
    if args.data_dir:
        command += ["--data-dir", str(args.data_dir)]
    if until:
        command += ["--until", until]
    if until_room:
        command += ["--until-room", until_room]
    if state:
        command += ["--seed-state", str(state)]
    if memory:
        command += ["--seed-memory", str(memory)]
    started = time.perf_counter()
    if session.exists():
        shutil.rmtree(session)  # failure snapshots of an older run must not be mistaken for new ones
    session.mkdir(parents=True)
    # One emulator uses one core. Keeping the model to one thread too lets several tests
    # run side by side without fighting for the same cores.
    environment = {**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"}
    with (session / "agent.log").open("w", encoding="utf-8") as log:
        code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=environment).returncode
    trace = session / "trace.jsonl"
    if code or not trace.is_file():
        return {"test": label, "status": "erro", "log": str(session / "agent.log")}
    result = {"test": label, **metrics(trace), "seconds": round(time.perf_counter() - started),
              "target": until or until_room, "budget": decisions, "policy": args.policy,
              "commit": revision(), "when": datetime.now().isoformat(timespec="seconds")}
    result["status"] = verdict(result, until, until_room, no_drops)
    del result["rooms"]
    return result


def run_segment(directory, name, args):
    """From the checkpoint before `name` until `name` is completed."""
    order = names()
    before = order[order.index(name) - 1] if order.index(name) else None
    state = memory = None
    if before:
        state, memory = checkpoint(directory, before)
        if not state.is_file():
            return {"test": name, "status": "sem checkpoint", "needs": before}
        if not memory.is_file() or args.fresh_memory:
            memory = None
    session = directory / "runs" / name
    result = play(name, session, args, state=state, memory=memory, until=name, decisions=args.decisions)
    if name in result.get("reached", ()):
        # The first completion becomes the start of the next segment. --update replaces it.
        capture(directory, session, replace=args.update)
    return result


def load_cases(directory):
    cases = {}
    for file in sorted((directory / "cases").glob("*/case.json")):
        cases[file.parent.name] = json.loads(file.read_text(encoding="utf-8"))
    return cases


def snapshot_before(run, decision):
    """The latest snapshot a session kept at or before a decision."""
    points = sorted(point for point in (run / "pontos").glob("*.state") if int(point.stem) <= decision)
    if not points:
        raise SystemExit(f"Nenhum ponto salvo em {run / 'pontos'} até a decisão {decision}")
    return points[-1]


def add_case(directory, args):
    if args.state is None:
        if args.run is None or args.decision is None:
            raise SystemExit("Informe --state, ou --run com --decision")
        args.state = snapshot_before(args.run, args.decision)
    folder = directory / "cases" / args.name
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.state, folder / "start.state")
    memory = args.memory or args.state.with_name(args.state.name.replace(".state", ".memory.json"))
    has_memory = memory.is_file()
    if has_memory:
        shutil.copyfile(memory, folder / "start.memory.json")
    case = {"until": args.until, "until_room": args.until_room, "decisions": args.decisions,
            "note": args.note, "memory": has_memory, "no_drops": args.no_drops}
    (folder / "case.json").write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return case


def run_case(directory, name, case, args):
    folder = directory / "cases" / name
    memory = folder / "start.memory.json" if case.get("memory") else None
    return play(f"case:{name}", folder / "run", args, state=folder / "start.state", memory=memory,
                until=case.get("until"), until_room=case.get("until_room"), decisions=case["decisions"],
                no_drops=case.get("no_drops", False))


def inspect(args):
    """Print what the agent would see at a saved state, and save a picture of the screen."""
    from io import BytesIO

    from pyboy import PyBoy

    from .adapter import enemies, health, observe
    from .agent import SURVEY_LEVELS
    from .survey import Surveyor

    pyboy = PyBoy(str(args.rom), window="null", ram_file=BytesIO(bytes(paths.SRAM_BYTES)), sound_volume=0)
    surveyor = Surveyor(args.rom)
    try:
        with args.state.open("rb") as stream:
            pyboy.load_state(stream)
        memory, seen = pyboy.memory, observe(pyboy)
        print(f"sala {seen.room}  modo {seen.mode}  xy {seen.x},{seen.y}  vida {health(pyboy)}")
        print(f"botões B/A {memory[0xC688]:02x}/{memory[0xC689]:02x}  guardados "
              f"{' '.join(f'{item:02x}' for item in memory[0xC68A:0xC69A] if item) or '-'}")
        large = memory[0xCD01] != 1
        width, height = (15, 11) if large else (10, 8)
        print("blocos (colisão marcada com *):")
        for row in range(height):
            print(" ".join(f"{memory[0xCF00 + row * 16 + column]:02x}"
                           f"{'*' if memory[0xCE00 + row * 16 + column] else ' '}" for column in range(width)))
        for kind, offset in (("interação", 0x40), ("inimigo", 0x80), ("parte", 0xC0)):
            for high in range(0xD0, 0xE0):
                address = high * 256 + offset
                if memory[1, address]:
                    print(f"{kind} id {memory[1, address + 1]:02x} subid {memory[1, address + 2]:02x} "
                          f"xy {memory[1, address + 0x0D]},{memory[1, address + 0x0B]}")
        print(f"inimigos vivos: {enemies(pyboy)}")
        started = time.perf_counter()
        options = surveyor.options(pyboy, **SURVEY_LEVELS[args.level])
        print(f"opções no nível {args.level} ({time.perf_counter() - started:.1f} s):")
        for option in options:
            print(f"  {option.id:36} {option.short or option.description}  ({len(option.route)} passos)")
        pyboy.tick(1, render=True)
        picture = args.picture or args.state.with_suffix(".png")
        pyboy.screen.image.resize((480, 432)).save(picture)
        print(f"imagem: {picture}")
    finally:
        surveyor.close()
        pyboy.stop(save=False)


def report(directory):
    """Latest result of each test next to the one before it."""
    history = {}
    log = directory / "results.jsonl"
    for line in log.read_text(encoding="utf-8").splitlines() if log.is_file() else ():
        record = json.loads(line)
        history.setdefault(record.get("test") or record.get("segment"), []).append(record)
    rows = [("teste", "status", "decisões", "antes", "ciclos", "repetição", "s", "commit")]
    for name, records in history.items():
        last, before = records[-1], records[-2] if len(records) > 1 else {}
        rows.append((name, last["status"], last.get("decisions", "-"), before.get("decisions", "-"),
                     last.get("loop_cuts", "-"), last.get("longest_repeat", "-"), last.get("seconds", "-"),
                     last.get("commit") or "-"))
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]
    return "\n".join("  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common(parser)
    parser.add_argument("--directory", type=Path, help="Pasta dos checkpoints. Padrão: output/segments")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Mostra os trechos e os casos")
    commands.add_parser("report", help="Último resultado de cada teste e o anterior")
    looking = commands.add_parser("inspect", help="Mostra sala, blocos, objetos e opções de um estado salvo")
    looking.add_argument("state", type=Path)
    looking.add_argument("--level", type=int, choices=(0, 1, 2), default=1, help="Nível do levantamento")
    looking.add_argument("--picture", type=Path, help="Onde salvar a imagem. Padrão: ao lado do estado")
    taking = commands.add_parser("capture", help="Copia os checkpoints de uma sessão do agente")
    taking.add_argument("session", type=Path)
    taking.add_argument("--update", action="store_true", help="Substitui checkpoints existentes")
    running = commands.add_parser("run", help="Roda um trecho, ou todos com 'all'")
    running.add_argument("segment", nargs="+", choices=[*names(), "all"],
                         help="Um ou mais trechos, ou 'all'")
    running.add_argument("--decisions", type=int, default=200, help="Orçamento de decisões por trecho")
    running.add_argument("--fresh-memory", action="store_true", help="Começa o trecho com a memória vazia")
    running.add_argument("--update", action="store_true",
                         help="Ao concluir, substitui o checkpoint do objetivo pelo desta execução")
    adding = commands.add_parser("case-add", help="Guarda um ponto salvo como caso de teste")
    adding.add_argument("name")
    adding.add_argument("--state", type=Path, help="Estado salvo de onde o caso parte")
    adding.add_argument("--run", type=Path, help="Pasta de uma sessão do agente, usada com --decision")
    adding.add_argument("--decision", type=int,
                        help="Parte do último ponto salvo pela sessão até esta decisão")
    adding.add_argument("--memory", type=Path, help="Padrão: o .memory.json ao lado do estado, se existir")
    target = adding.add_mutually_exclusive_group(required=True)
    target.add_argument("--until", choices=names(), help="Objetivo que o caso precisa concluir")
    target.add_argument("--until-room", help="Sala a que o caso precisa chegar")
    adding.add_argument("--decisions", type=int, default=40)
    adding.add_argument("--no-drops", action="store_true",
                        help="Falha também se uma opção for descartada por morte ou perda de controle")
    adding.add_argument("--note", default="", help="O que o caso reproduz")
    casing = commands.add_parser("case-run", help="Roda um caso, ou todos com 'all'")
    casing.add_argument("case")
    for sub in (running, casing):
        sub.add_argument("--policy", choices=("laya", "random", "shortest"), default="laya")
        sub.add_argument("--jobs", type=int, default=1,
                         help="Testes em paralelo. Com mais de um, os trechos não são encadeados")
    args = resolve_common(parser, parser.parse_args())
    directory = args.directory or paths.output_path("segments")
    order = names()
    if args.command == "list":
        for index, name in enumerate(order):
            start = order[index - 1] if index else None
            ready = not start or checkpoint(directory, start)[0].is_file()
            memory = bool(start) and checkpoint(directory, start)[1].is_file()
            print(f"{name:22} parte de {start or 'boot':18} "
                  f"{'pronto' if ready else 'sem checkpoint'}{'' if memory or not ready or not start else ' (sem memória)'}")
        for name, case in load_cases(directory).items():
            print(f"case:{name:17} até {case.get('until') or case.get('until_room'):22} "
                  f"{case['decisions']} decisões  {case.get('note', '')}")
        return
    if args.command == "inspect":
        inspect(args)
        return
    if args.command == "report":
        print(report(directory))
        return
    if args.command == "capture":
        copied = capture(directory, args.session, replace=args.update)
        print("Copiados: " + (", ".join(copied) if copied else "nenhum"))
        return
    if args.command == "case-add":
        print(json.dumps(add_case(directory, args), ensure_ascii=False))
        return
    if args.command == "case-run":
        cases = load_cases(directory)
        if args.case != "all" and args.case not in cases:
            parser.exit(2, f"Caso desconhecido: {args.case}. Existentes: {', '.join(cases) or 'nenhum'}\n")
        chosen = cases if args.case == "all" else {args.case: cases[args.case]}
        jobs = [lambda name=name, case=case: run_case(directory, name, case, args) for name, case in chosen.items()]
        chained = False
    else:
        chosen = order if "all" in args.segment else [name for name in order if name in args.segment]
        if args.jobs > 1:
            # In parallel each segment starts from its stored checkpoint, so only those that have one run.
            chosen = [name for name in chosen
                      if not order.index(name) or checkpoint(directory, order[order.index(name) - 1])[0].is_file()]
        jobs = [lambda name=name: run_segment(directory, name, args) for name in chosen]
        chained = "all" in args.segment and args.jobs == 1
    failed = False
    directory.mkdir(parents=True, exist_ok=True)

    def finish(result):
        nonlocal failed
        with (directory / "results.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        failed |= result["status"] != PASSED

    if args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for result in pool.map(lambda job: job(), jobs):
                finish(result)
    else:
        for job in jobs:
            result = job()
            finish(result)
            if chained and result["status"] in ("sem checkpoint", "erro", "não concluiu"):
                break  # the next segment starts where this one should have ended
    print(report(directory))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
