# Validação local do emulador

Data: 2026-10-28. Máquina: macOS, Apple Silicon arm64.

## Resultado

Oracle of Ages US foi compilado do disassembly público, abriu no PyBoy e chegou ao primeiro cenário jogável. Os inputs de teclado moveram Link. Salvar com Z, mover e restaurar com X devolveu Link à posição salva. P pausou a execução e Escape encerrou normalmente. A partida foi reaberta a partir do checkpoint pelo argumento `--load-state`, com o save de cartucho existente.

Na sessão de 28 de outubro, o emulador foi deixado pausado no primeiro cenário jogável. O perfil de teste do slot 1 e o checkpoint Z/X foram gerados localmente durante a validação manual.

## Ambiente e procedência

- Python Homebrew 3.12.16 em `.venv`.
- PyBoy 2.8.1, PySDL2 0.9.17, pysdl2-dll 2.32.10; demais versões em `requirements.lock.txt`.
- ROM de 1.048.576 bytes gerada por `scripts/build_rom.py`.
- SHA-1: `880374fb978b18af4aa529e2e32f7ffb4d7dd2f4`.
- O make upstream também informou correspondência do MD5 vanilla.
- Commits de disassembly e assembler registrados em `roms/manifest.json` e README.
- Build repetido com cache manteve o mesmo hash.

## Verificações automáticas

`python -m zelda_env smoke` terminou com código 0. Após 600 frames de boot, a sequência de 64 frames de inputs foi executada duas vezes, com restauração do mesmo checkpoint entre execuções. O estado serializado completo e os pixels finais foram idênticos.

O relatório está em `output/smoke/smoke.json`; as capturas estão em `output/smoke/`. Uma verificação complementar comparou SHA-256 do save de cartucho antes/depois do smoke e confirmou que o progresso do jogador foi preservado. `output/gameplay.png` mostra o checkpoint jogável.

`pip check` não encontrou dependências quebradas. Os módulos passaram por `compileall`. A ajuda da CLI foi conferida. A validação de SRAM foi ajustada ao header real da ROM: 8 KiB (header `0x149 = 0x02`), e a reabertura com o save existente confirmou a compatibilidade.

## Limites

Somente o boot, menu e começo da aventura foram exercitados. Áudio foi habilitado sem erro na segunda abertura, mas não foi avaliado auditivamente. Não foram testados outros sistemas operacionais, ROMs regionais, controles físicos, campanha completa ou versões distintas do PyBoy. Não existe ainda extração semântica XY/entidades/terreno nem integração com Jev/Laya.

## Revalidação em 2026-11-20

O smoke foi executado em um diretório temporário com Python 3.12.16 e PyBoy 2.8.1. O replay de 64 frames após 600 frames de boot produziu estados serializados e pixels finais idênticos, com resolução de 160 × 144. O SHA-256 do save de cartucho permaneceu idêntico antes e depois. `pip check` passou. A sessão gráfica descrita acima é a validação de outubro.
