#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print "Ambiente ausente. Siga a instalação no README.md."
  read "?Pressione Enter para fechar."
  exit 1
fi
.venv/bin/python -m zelda_env play
if [[ $? -ne 0 ]]; then
  read "?O jogo encerrou com erro. Pressione Enter para fechar."
fi
