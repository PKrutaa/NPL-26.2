"""Ask a small local LLM to pick one already-legal option when the agent is stuck.

The supervisor never produces controller input. It returns an option id from the list
it was given, or abstains. Every other outcome is rejected and the caller falls back.
"""

import json
import time
import urllib.error
import urllib.request

ABSTAIN = "abstain"
MAX_CONTEXT_CHARS = 2400
SYSTEM = (
    "You guide an agent playing The Legend of Zelda: Oracle of Ages, screen by screen. "
    "Pick the option that best follows the goal. North is up, south is down, west is left, east is right. "
    "Prefer options not tried yet. When unsure, pick an exit in the direction the goal mentions. "
    'Answer with JSON only: {"option_id": "<id>", "reason": "<short reason>"}.'
)


class SupervisorUnavailable(RuntimeError):
    pass


class OllamaBackend:
    """Local Ollama server. Weights stay on this machine; no remote inference."""

    def __init__(self, model, host="http://127.0.0.1:11434"):
        self.model = model
        self.host = host.rstrip("/")
        self.name = f"ollama:{model}"

    def _post(self, path, payload, timeout):
        request = urllib.request.Request(
            self.host + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())

    def check(self, timeout=5):
        """Fail early, with the fix, if the server or the weights are missing."""
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=timeout) as response:
                models = [item["name"] for item in json.loads(response.read()).get("models", [])]
        except (OSError, ValueError) as error:
            raise SupervisorUnavailable(
                f"Servidor Ollama indisponível em {self.host}. Inicie com: ollama serve"
            ) from error
        if self.model not in models and f"{self.model}:latest" not in models:
            raise SupervisorUnavailable(
                f"Pesos ausentes para {self.model}. Baixe uma vez, com rede: ollama pull {self.model}"
            )

    def complete(self, system, user, option_ids, timeout):
        schema = {
            "type": "object",
            "properties": {"option_id": {"type": "string", "enum": [*option_ids]},
                           "reason": {"type": "string"}},
            "required": ["option_id"],
        }
        try:
            reply = self._post("/api/chat", {
                "model": self.model, "stream": False, "format": schema,
                "options": {"temperature": 0, "num_predict": 80},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            }, timeout)
        except TimeoutError:
            raise
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise TimeoutError(str(error)) from error
            raise SupervisorUnavailable(str(error)) from error
        except OSError as error:
            raise SupervisorUnavailable(str(error)) from error
        return reply.get("message", {}).get("content", "")


def build_prompt(context, options):
    """Compact, size-limited text built only from game state. Unknown values say so."""
    lines = []
    for key, value in context.items():
        lines.append(f"{key}: {'unknown' if value is None else value}")
    text = "\n".join(lines)[:MAX_CONTEXT_CHARS]
    listing = "\n".join(f"- {option_id}: {description}" for option_id, description in options)
    return f"{text}\n\nOptions:\n{listing}\n- {ABSTAIN}: choose this only if every option above was already tried"


def parse(raw, option_ids):
    """Return (option_id, reason, rejection). Exactly one of option_id/rejection is set."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None, None, "invalid_json"
    if not isinstance(data, dict) or not isinstance(data.get("option_id"), str):
        return None, None, "invalid_schema"
    reason = data.get("reason")
    reason = reason[:200] if isinstance(reason, str) else None
    choice = data["option_id"]
    if choice == ABSTAIN:
        return None, reason, "abstain"
    if choice not in option_ids:
        return None, reason, "unknown_option"
    return choice, reason, None


class Supervisor:
    def __init__(self, backend, *, timeout=20.0, per_impasse=2, interval=6):
        self.backend = backend
        self.timeout = timeout
        self.per_impasse = per_impasse
        self.interval = interval
        self.used = 0  # consultations in the current impasse
        self.last_decision = None
        self.stats = {"calls": 0, "accepted": 0, "rejected": {}, "seconds": 0.0}

    def progressed(self):
        """The game confirmed progress, so the next impasse gets a fresh budget."""
        self.used = 0

    def allowed(self, decision):
        if self.used >= self.per_impasse:
            return False
        return self.last_decision is None or decision - self.last_decision >= self.interval

    def consult(self, context, options, decision):
        """Return (option_id or None, record). Never raises; rejection means fall back."""
        if not self.allowed(decision):
            return None, {"supervisor": "skipped_budget"}
        ids = [option_id for option_id, _ in options]
        self.used += 1
        self.last_decision = decision
        self.stats["calls"] += 1
        started = time.perf_counter()
        choice, reason, rejection, raw = None, None, None, None
        try:
            raw = self.backend.complete(SYSTEM, build_prompt(context, options), [*ids, ABSTAIN], self.timeout)
            choice, reason, rejection = parse(raw, ids)
        except TimeoutError:
            rejection = "timeout"
        except SupervisorUnavailable as error:
            rejection, reason = "unavailable", str(error)[:200]
        elapsed = time.perf_counter() - started
        if rejection is None and elapsed > self.timeout:
            choice, rejection = None, "timeout"
        self.stats["seconds"] += elapsed
        if rejection:
            self.stats["rejected"][rejection] = self.stats["rejected"].get(rejection, 0) + 1
        else:
            self.stats["accepted"] += 1
        return choice, {"supervisor": rejection or "accepted", "option_id": choice, "reason": reason,
                        "seconds": round(elapsed, 3), "backend": getattr(self.backend, "name", "custom")}
