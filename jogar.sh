#!/usr/bin/env bash
# Linux launcher. Extra arguments go to "zelda_env play", for example: ./jogar.sh --mute
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python="$here/.venv/bin/python"
if [ ! -x "$python" ]; then
  echo "Ambiente ausente em $here/.venv. Siga a instalação no README.md." >&2
  exit 1
fi
cd "$here" || exit 1
exec "$python" -m zelda_env play "$@"
