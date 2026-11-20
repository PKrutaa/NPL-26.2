"""Run a pinned Laya Choice model in the same Python process."""

import json

from .adapter import ACTIONS

MODEL_ID = "convaiinnovations/laya"
REVISION = "fd4f9dbcf4fde222fd43174bdd4c3b08b789e4e1"


class LayaPolicy:
    def __init__(self, device, context_format, history):
        try:
            import laya
        except ImportError as error:
            raise RuntimeError("Instale o Laya com: python -m pip install -e '.[laya]'") from error
        self.agent = laya.Agent(MODEL_ID, device=device, revision=REVISION)
        self.model = {"id": MODEL_ID, "revision": REVISION}
        self.context_format = context_format
        self.history = history

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
