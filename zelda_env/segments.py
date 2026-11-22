"""Run one stretch of the game at a time, from a saved checkpoint to the next objective.

A full run from boot takes about an hour to reach the later objectives. A segment starts
from the state and the agent memory saved when the previous objective was completed, so
a change can be checked on the stretch it affects in minutes.

  python -m zelda_env.segments list
  python -m zelda_env.segments capture output/agent-limpa
  python -m zelda_env.segments run chave-do-cemiterio --decisions 150
  python -m zelda_env.segments run all

Checkpoints live in output/segments. A segment passes when the objective is completed
within the budget with no loop cut and no impasse.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from . import paths
from .__main__ import add_common, resolve_common

REPEAT_MOVES = 4  # a stretch made of at most this many distinct moves counts as repetition


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
        "loop_cuts": events["loop_cut"], "impasses": events["impasse"],
        "dropped": sum(record["outcome"].startswith("failed") for record in decisions),
        "longest_repeat": longest if len(moves) > REPEAT_MOVES else 0,
        "most_repeated": [[*move, count] for move, count in Counter(moves).most_common(3)],
        "origins": dict(Counter(record["origin"] for record in decisions)),
        "survey_s": round(sum(survey) / len(survey), 1) if survey else 0.0,
    }


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


def run(directory, name, args):
    """Run the agent from the checkpoint before `name` until `name` is completed."""
    order = names()
    before = order[order.index(name) - 1] if order.index(name) else None
    command = [sys.executable, "-m", "zelda_env.agent", "--headless", "--fresh", "--until", name,
               "--decisions", str(args.decisions), "--policy", args.policy,
               "--directory", str(directory / "runs" / name), "--rom", str(args.rom)]
    if args.data_dir:
        command += ["--data-dir", str(args.data_dir)]
    if before:
        state, memory = checkpoint(directory, before)
        if not state.is_file():
            return {"segment": name, "status": "sem checkpoint", "needs": before}
        command += ["--seed-state", str(state)]
        if memory.is_file() and not args.fresh_memory:
            command += ["--seed-memory", str(memory)]
    started = time.perf_counter()
    session = directory / "runs" / name
    session.mkdir(parents=True, exist_ok=True)
    with (session / "agent.log").open("w", encoding="utf-8") as log:
        code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
    trace = session / "trace.jsonl"
    if code or not trace.is_file():
        return {"segment": name, "status": "erro", "log": str(session / "agent.log")}
    result = {"segment": name, "from": before or "boot", **metrics(trace),
              "seconds": round(time.perf_counter() - started)}
    done = name in result["reached"]
    clean = not result["loop_cuts"] and not result["impasses"]
    result["status"] = "passou" if done and clean else "concluiu com ciclo" if done else "não concluiu"
    if done:
        # The first completion becomes the start of the next segment. --update replaces it.
        capture(directory, session, replace=args.update)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common(parser)
    parser.add_argument("--directory", type=Path, help="Pasta dos checkpoints. Padrão: output/segments")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Mostra os trechos e quais têm checkpoint")
    taking = commands.add_parser("capture", help="Copia os checkpoints de uma sessão do agente")
    taking.add_argument("session", type=Path)
    taking.add_argument("--update", action="store_true", help="Substitui checkpoints existentes")
    running = commands.add_parser("run", help="Roda um trecho, ou todos com 'all'")
    running.add_argument("segment", choices=[*names(), "all"])
    running.add_argument("--decisions", type=int, default=200, help="Orçamento de decisões por trecho")
    running.add_argument("--policy", choices=("laya", "random", "shortest"), default="laya")
    running.add_argument("--fresh-memory", action="store_true", help="Começa o trecho com a memória vazia")
    running.add_argument("--update", action="store_true",
                         help="Ao concluir, substitui o checkpoint do objetivo pelo desta execução")
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
        return
    if args.command == "capture":
        copied = capture(directory, args.session, replace=args.update)
        print("Copiados: " + (", ".join(copied) if copied else "nenhum"))
        return
    failed = False
    for name in order if args.segment == "all" else [args.segment]:
        result = run(directory, name, args)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "results.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        failed |= result["status"] != "passou"
        if result["status"] in ("sem checkpoint", "erro", "não concluiu") and args.segment == "all":
            break  # the next segment starts where this one should have ended
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
