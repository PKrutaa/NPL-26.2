"""Run a pinned Laya Choice model in the same Python process."""

import json
import os

from .adapter import ACTIONS
from .paths import venv_python

MODEL_ID = "convaiinnovations/laya"
REVISION = "fd4f9dbcf4fde222fd43174bdd4c3b08b789e4e1"


def available_devices():
    """CPU everywhere. MPS only where this PyTorch build exposes it."""
    try:
        import torch
    except ImportError:
        return ("cpu",)
    return ("cpu", "mps") if torch.backends.mps.is_available() else ("cpu",)


def load(device, *, online=False):
    """Load the pinned snapshot. Offline unless the caller is the prepare command."""
    if not online:
        # Must be set before huggingface_hub is imported: no download during a game.
        os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        import laya
    except ImportError as error:
        raise RuntimeError(f'Instale o Laya com: {venv_python()} -m pip install -e ".[laya]"') from error
    if device not in available_devices():
        raise RuntimeError(f"Dispositivo indisponível nesta máquina: {device}. Use --device cpu.")
    try:
        return laya.Agent(MODEL_ID, device=device, revision=REVISION)
    except Exception as error:
        if online:
            raise
        raise RuntimeError(
            f"Pesos do Laya ausentes ou incompletos no cache local ({type(error).__name__}). "
            f"Prepare uma vez, com rede: {venv_python()} -m zelda_env.model prepare"
        ) from error


class LayaPolicy:
    def __init__(self, device, context_format, history):
        self.agent = load(device)
        self.model = {"id": MODEL_ID, "revision": REVISION}
        self.context_format = context_format
        self.history = history

    def choose(self, context, criteria):
        """Pick one of the described options. Keys of criteria are the option ids."""
        text = "\n".join(f"{key}: {value}" for key, value in context.items())
        question = {"action": {
            "type": "choice",
            "instructions": "Which option reaches the goal?",
            "criteria": criteria,
        }}
        result = self.agent.predict(text, question)
        answer = result["answers"]["action"]
        if answer["choice"] not in criteria:
            raise RuntimeError(f"Laya retornou uma opção inválida: {answer['choice']!r}")
        return answer["choice"], {"context": text, "criteria": criteria, "answer": answer, "usage": result["usage"]}

    def __call__(self, goal, observation, candidates, trace, *, directions=None):
        if len(candidates) == 1:
            return candidates[0], {"forced_action": True}
        state = {
            "goal": goal,
            "mode": observation.mode,
            "room": observation.room,
            "player_pixels": {"x": observation.x, "y": observation.y, "facing": observation.facing},
            "visible_interactions_pixels": [
                {key: entity[key] for key in ("kind", "x", "y")}
                for entity in observation.entities
            ],
            "dialogue_ready_for_input": observation.dialogue_ready,
            "collision_rows_16px_tiles": (
                ["".join(format(value, "x") for value in row)
                 for row in observation.collision_quadrants]
                if observation.collision_quadrants is not None else None
            ),
        }
        if directions:
            state["direction_checks"] = directions
        if self.history:
            state["recent_actions"] = [
                {"action": step["action"], "event": step["event"]} for step in trace[-3:]
            ]
        if self.context_format == "json":
            context = json.dumps(state, separators=(",", ":"))
        else:
            context = "\n".join(f"{key.replace('_', ' ')}: {value}" for key, value in state.items())
        question = {
            "action": {
                "type": "choice",
                "instructions": (
                    "Which single controller action makes progress toward the stated goal now? "
                    "Coordinates increase to the right and down. A press opens dialogue in talking range "
                    "and advances it inside a textbox. Terrain rows use hexadecimal collision masks: "
                    "0 is clear and f is fully solid; other values may be partially solid."
                ),
                "criteria": {key: ACTIONS[key] for key in candidates},
            }
        }
        result = self.agent.predict(context, question)
        answer = result["answers"]["action"]
        action = answer["choice"]
        if action not in candidates:
            raise RuntimeError(f"Laya retornou uma ação inválida: {action!r}")
        return action, {"laya": {
            "context": context, "question": question, "answer": answer, "usage": result["usage"],
        }}
