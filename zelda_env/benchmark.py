"""Prepare local emulator checkpoints and evaluate policies with equal budgets."""

import argparse
import hashlib
import io
import json
import random
import time
from dataclasses import asdict
from pathlib import Path

from . import paths
from .__main__ import add_common, resolve_common
from .adapter import DIRECTIONS, candidates, execute, observe, show_status
from .scenarios import SCENARIOS, achieved, prepare


def evaluate(pyboy, name, policy, seed, choose_laya=None, *, watch=False, recover=False, lookahead=None):
    scenario = SCENARIOS[name]
    rng = random.Random(seed)
    obs = observe(pyboy)
    initial = asdict(obs)
    trace = []
    recovery_action = None
    recovery_steps = 0
    talking_to_monkey = False
    monkey_dialogue_advanced = False
    for step in range(scenario.budget):
        choices = candidates(obs)
        start = time.perf_counter()
        details = {}
        directions = lookahead.directions(pyboy, obs, choices) if lookahead else {}
        allowed = tuple(key for key in choices if directions.get(key, {}).get("event") != "blocked")
        if policy == "script":
            action = scenario.script[step] if step < len(scenario.script) else "wait"
        elif policy == "random":
            action = rng.choice(choices)
        elif policy == "human":
            print(json.dumps({"goal": scenario.goal, **asdict(obs)}, ensure_ascii=False))
            while True:
                action = input(f"{', '.join(choices)} > ").strip()
                if action in choices:
                    break
        else:
            legal_moves = [key for key in DIRECTIONS if key in allowed]
            recent_blocks = {
                item["action"] for item in trace[-3:] if item["event"] == "blocked"
            }
            alternatives = [key for key in legal_moves if key not in recent_blocks]
            if recover and recovery_steps and recovery_action in allowed:
                action, details = recovery_action, {"recovery": "continue"}
                recovery_steps -= 1
            elif recover and alternatives and obs.mode == "playing" and len(trace) >= 2 and all(
                item["event"] == "blocked" for item in trace[-2:]
            ):
                action = rng.choice(alternatives)
                details = {"recovery": "explore"}
                recovery_action, recovery_steps = action, 4
            else:
                action, details = choose_laya(scenario.goal, obs, allowed, trace, directions=directions)
                recovery_steps = 0
        if directions:
            details["direction_checks"] = directions
        latency = (time.perf_counter() - start) * 1000
        before = obs
        if watch:
            show_status(pyboy, f"Laya | {name} | {action}")
        obs, event, frames = execute(pyboy, action, render=watch)
        if event != "moved":
            recovery_steps = 0
        if watch:
            source = " [exploração]" if "recovery" in details else ""
            print(f"{name} {step + 1}/{scenario.budget}: {action} → {event}{source}", flush=True)
            show_status(pyboy, f"Laya | {name} | {action}: {event}")
            time.sleep(0.35)
        if event == "dialogue_opened":
            talking_to_monkey = action == "interact" and achieved("approach", before)
        elif event == "dialogue_advanced":
            monkey_dialogue_advanced |= talking_to_monkey
        elif event == "dialogue_closed":
            talking_to_monkey = False
        trace.append({
            "action": action, "event": event, "frames": frames, "choice_ms": round(latency, 3),
            "after": asdict(obs), **details,
        })
        if achieved(name, obs, monkey_dialogue_advanced):
            break

    state = io.BytesIO()
    pyboy.save_state(state)
    return {
        "scenario": name, "policy": policy, "seed": seed, "success": achieved(name, obs, monkey_dialogue_advanced),
        "decisions": len(trace), "frames": sum(step["frames"] for step in trace),
        "blocked": sum(step["event"] == "blocked" for step in trace),
        "timeouts": sum(step["event"] == "timeout" for step in trace),
        "initial": initial, "final_state_sha256": hashlib.sha256(state.getvalue()).hexdigest(),
        "trace": trace,
    }


def watch_scenarios(pyboy, checkpoints, policy, seed, lookahead):
    # Display successful tasks first when looping over the three scenarios.
    while True:
        for name in ("approach", "dialogue", "exit"):
            if name not in checkpoints:
                continue
            pyboy.load_state(io.BytesIO(checkpoints[name]))
            run = evaluate(pyboy, name, "laya", seed, policy, watch=True, recover=True, lookahead=lookahead)
            result = "concluído" if run["success"] else "limite de decisões"
            print(f"{name}: {result}", flush=True)
            # Keep showing the final frame briefly. SDL events are handled by
            # the next tick and the next episode restores its own checkpoint.
            show_status(pyboy, f"Laya | {name} | {result}")
            time.sleep(1.4)
        seed += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    add_common(parser)
    parser.add_argument("--checkpoint", type=Path, help="Seed em 00:8a, XY 124,56. Padrão: output/inicio.state")
    parser.add_argument("--states", type=Path, help="Pasta dos checkpoints de cenário")
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--policy", choices=("script", "random", "human", "laya"), default="script")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--trials", type=int, default=1, help="Número de sementes para random")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--watch", action="store_true", help="Exibe e repete os episódios do Laya na janela SDL2")
    parser.add_argument("--recover", action="store_true", help="Exploração após bloqueios do Laya")
    parser.add_argument("--lookahead", action="store_true", help="Consulta colisões em uma cópia headless")
    args = resolve_common(parser, parser.parse_args())
    args.states = args.states or paths.output_path("scenarios")
    if args.checkpoint is None:
        legacy = Path(f"{args.rom}.state")
        seed = paths.output_path("inicio.state")
        args.checkpoint = legacy if legacy.exists() and not seed.exists() else seed
    if args.trials < 1 or (args.trials != 1 and args.policy != "random" and not args.recover):
        parser.error("--trials deve ser positivo e só pode variar para random ou --recover")

    if (args.recover or args.lookahead) and (args.command != "run" or args.policy != "laya"):
        parser.error("--recover e --lookahead requerem run --policy laya")

    if args.watch and (args.command != "run" or args.policy != "laya"):
        parser.error("--watch requer run --policy laya")

    from pyboy import PyBoy

    pyboy = PyBoy(
        str(args.rom), window="SDL2" if args.watch else "null",
        ram_file=io.BytesIO(bytes(8192)), sound_volume=0,
    )
    pyboy.set_emulation_speed(1 if args.watch else 0)
    lookahead = None
    try:
        if args.command == "prepare":
            if not args.checkpoint.is_file():
                raise ValueError(f"Seed ausente: {args.checkpoint}. Gere com: {paths.venv_python()} -m zelda_env seed")
            with args.checkpoint.open("rb") as file:
                pyboy.load_state(file)
            pyboy.tick(1, render=False)
            prepare(pyboy, args.states)
            print(f"Checkpoints gerados em {args.states}")
            return

        names = SCENARIOS if args.scenario == "all" else (args.scenario,)
        missing = [name for name in names if not (args.states / f"{name}.state").is_file()]
        if missing:
            raise ValueError(f"Cenários ausentes em {args.states}: {', '.join(missing)}. "
                             f"Gere com: {paths.venv_python()} -m zelda_env.benchmark prepare")
        checkpoints = {name: (args.states / f"{name}.state").read_bytes() for name in names}
        choose_laya = None
        if args.policy == "laya":
            from .laya_policy import LayaPolicy

            choose_laya = LayaPolicy(args.device, args.format, args.history)

        if args.lookahead:
            from .lookahead import Lookahead

            lookahead = Lookahead(args.rom)

        if args.watch:
            print("Laya jogando em loop. Escape fecha a janela.", flush=True)
            watch_scenarios(pyboy, checkpoints, choose_laya, args.seed, lookahead)
            return

        runs = []
        for name, checkpoint in checkpoints.items():
            for seed in range(args.seed, args.seed + args.trials):
                pyboy.load_state(io.BytesIO(checkpoint))
                run = evaluate(pyboy, name, args.policy, seed, choose_laya, recover=args.recover, lookahead=lookahead)
                run["checkpoint_sha256"] = hashlib.sha256(checkpoint).hexdigest()
                runs.append(run)
                print(f"{name}/{args.policy}/{seed}: success={run['success']} "
                      f"decisions={run['decisions']} frames={run['frames']}")

        output = args.output or paths.output_path("benchmark", f"{args.policy}.json")
        report = {
            "format": args.format, "history": args.history, "device": args.device, "recover": args.recover, "lookahead": args.lookahead,
            "model": choose_laya.model if choose_laya else None,
            "runs": runs,
        }
        paths.atomic_write(output, (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        print(f"Relatório salvo em {output}")
    except (InterruptedError, KeyboardInterrupt):
        if not args.watch:
            raise
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    finally:
        if lookahead:
            lookahead.close()
        pyboy.stop(save=False)


if __name__ == "__main__":
    main()
