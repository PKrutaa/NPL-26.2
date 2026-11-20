"""Download and verify the pinned Laya snapshot once, so games run offline.

    python -m zelda_env.model prepare     needs network
    python -m zelda_env.model check       offline; fails with instructions if incomplete
"""

import argparse
import json
import platform
import time
from importlib.metadata import PackageNotFoundError, version


def report(agent_factory, device):
    from .laya_policy import MODEL_ID, REVISION

    started = time.perf_counter()
    agent = agent_factory()
    loaded = time.perf_counter() - started
    question = {"action": {"type": "choice", "instructions": "Which option reaches the goal?",
                           "criteria": {"north": "Walk north", "south": "Walk south"}}}
    started = time.perf_counter()
    answer = agent.predict("goal: leave through the north exit", question)["answers"]["action"]
    info = {
        "model": MODEL_ID, "revision": REVISION, "device": device,
        "load_seconds": round(loaded, 2), "inference_ms": round((time.perf_counter() - started) * 1000, 1),
        "probe_choice": answer["choice"], "system": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
    }
    for package in ("laya", "torch", "transformers", "huggingface_hub"):
        try:
            info[package] = version(package)
        except PackageNotFoundError:
            info[package] = None
    try:
        from huggingface_hub import scan_cache_dir

        repo = next((item for item in scan_cache_dir().repos if item.repo_id == MODEL_ID), None)
        if repo:
            info["cache_path"] = str(repo.repo_path)
            info["cache_bytes"] = repo.size_on_disk
            info["files"] = sorted(file.file_name for revision in repo.revisions
                                   if revision.commit_hash == REVISION for file in revision.files)
    except Exception as error:  # the scan is diagnostic only
        info["cache_scan_error"] = str(error)
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("prepare", "check"))
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    args = parser.parse_args()
    from .laya_policy import load

    try:
        info = report(lambda: load(args.device, online=args.command == "prepare"), args.device)
    except Exception as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(info, indent=2))
    print("Modelo pronto para uso offline.")


if __name__ == "__main__":
    main()
