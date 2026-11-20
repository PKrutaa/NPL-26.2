"""Prepare local emulator checkpoints and evaluate policies with equal budgets."""

import argparse
import hashlib
import io
import json
import random
import time
from dataclasses import asdict
from pathlib import Path

from .__main__ import DEFAULT_ROM, ROOT, rom_path
from .adapter import candidates, execute, observe
from .scenarios import SCENARIOS, achieved, prepare


def evaluate(pyboy, name, policy, seed, choose_laya=None):
    scenario = SCENARIOS[name]
    rng = random.Random(seed)
    obs = observe(pyboy)
    initial = asdict(obs)
    trace = []
    talking_to_monkey = False
    monkey_dialogue_advanced = False
    for step in range(scenario.budget):
        choices = candidates(obs)
        start = time.perf_counter()
        details = {}
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
            action, details = choose_laya(scenario.goal, obs, choices, trace)
        latency = (time.perf_counter() - start) * 1000
        before = obs
        obs, event, frames = execute(pyboy, action)
        if event == "dialogue_opened":
            talking_to_monkey = action == "interact" and achieved("approach", before)
        elif event in ("dialogue_advanced", "dialogue_closed"):
            monkey_dialogue_advanced |= talking_to_monkey and before.dialogue_ready
            if event == "dialogue_closed":
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--rom", type=rom_path, default=str(DEFAULT_ROM))
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_ROM.with_suffix(".gbc.state"))
    parser.add_argument("--states", type=Path, default=ROOT / "output/scenarios")
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--policy", choices=("script", "random", "human", "laya"), default="script")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--trials", type=int, default=1, help="Número de sementes para random")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.trials < 1 or (args.trials != 1 and args.policy != "random"):
        parser.error("--trials deve ser positivo e só pode variar para random")

    from pyboy import PyBoy

    pyboy = PyBoy(str(args.rom), window="null", ram_file=io.BytesIO(bytes(8192)), sound_volume=0)
    pyboy.set_emulation_speed(0)
    try:
        if args.command == "prepare":
            with args.checkpoint.open("rb") as file:
                pyboy.load_state(file)
            pyboy.tick(1, render=False)
            prepare(pyboy, args.states)
            print(f"Checkpoints gerados em {args.states}")
            return

        names = SCENARIOS if args.scenario == "all" else (args.scenario,)
        checkpoints = {name: (args.states / f"{name}.state").read_bytes() for name in names}
        choose_laya = None
        if args.policy == "laya":
            from .laya_policy import LayaPolicy

            choose_laya = LayaPolicy(args.device, args.format, args.history)

        runs = []
        for name, checkpoint in checkpoints.items():
            for seed in range(args.seed, args.seed + args.trials):
                pyboy.load_state(io.BytesIO(checkpoint))
                run = evaluate(pyboy, name, args.policy, seed, choose_laya)
                run["checkpoint_sha256"] = hashlib.sha256(checkpoint).hexdigest()
                runs.append(run)
                print(f"{name}/{args.policy}/{seed}: success={run['success']} "
                      f"decisions={run['decisions']} frames={run['frames']}")

        output = args.output or ROOT / f"output/benchmark/{args.policy}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "format": args.format, "history": args.history, "device": args.device,
            "model": choose_laya.model if choose_laya else None,
            "runs": runs,
        }
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"Relatório salvo em {output}")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    finally:
        pyboy.stop(save=False)


if __name__ == "__main__":
    main()
