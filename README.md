# Oracle of Ages · ambiente PyBoy para experimentos com agentes

O projeto usa o PyBoy para rodar Oracle of Ages US, permitir controle humano e preparar experimentos de controle por agentes.

## Estado atual

| Parte | Estado |
| --- | --- |
| Emulador | Jogável no macOS. A CLI oferece janela SDL2, controles por teclado, save de cartucho e checkpoints. |
| Build da ROM | Script com commits fixados, verificação de SHA-1 e exportação de símbolos para o PyBoy. |
| Replay | Smoke headless confirma que a mesma sequência de inputs, repetida após restaurar um checkpoint, produz o mesmo estado serializado e os mesmos pixels. |
| Adapter semântico | Lê sala, posição, direção, interações visíveis, quadrantes de colisão em salas pequenas e estado de diálogo. Executa ações curtas via PyBoy. |
| Laya local | Inferência offline validada com o checkpoint clássico. Concluiu aproximação e diálogo com texto sem histórico, e travou na saída. |

A [validação local](docs/validation-emulator.md) registra a sessão jogável de 28 de outubro de 2026 e a repetição do smoke em 20 de novembro de 2026.

## Jogar depois da instalação

Abra `Jogar.command` com dois cliques no Finder ou execute, na pasta do projeto:

```bash
.venv/bin/python -m zelda_env play
```

Clique na janela para ela receber o teclado. Feche com Escape ou pelo botão da janela, permitindo que o save seja gravado.

| Tecla | Função |
| --- | --- |
| Setas | Direcional |
| A | Botão A |
| S | Botão B |
| Enter | Start |
| Backspace/Delete | Select |
| P | Pausar/retomar |
| Z | Salvar checkpoint do emulador |
| X | Carregar o último checkpoint |
| Espaço segurado | Acelerar |
| Escape | Encerrar e persistir o save do cartucho |

Os atalhos de pausa/checkpoint disparam ao soltar a tecla. `Z` usa um único slot: cada gravação substitui a anterior.

Outras opções:

```bash
.venv/bin/python -m zelda_env play --mute --scale 5
.venv/bin/python -m zelda_env play --load-state roms/oracle-of-ages.gbc.state
.venv/bin/python -m zelda_env --help
```

`--scale` aceita de 1 a 8; o padrão é 4 (640 × 576). Os caminhos padrão são relativos à localização do projeto, independentemente da pasta de onde o comando for chamado.

Em uma instalação nova, comece pelo boot/menu e pressione Z durante a partida para criar o primeiro checkpoint. O exemplo com `--load-state` pressupõe que esse arquivo já existe. O perfil e o checkpoint usados na validação são locais.

## Instalação reproduzível no macOS

Pré-requisitos: Git, Command Line Tools da Apple, Homebrew e rede para baixar pacotes e fontes. Se `cc`/`make` estiverem ausentes, instale as ferramentas da Apple com `xcode-select --install`. Na raiz do projeto, execute o seguinte.

```bash
brew install python@3.12 cmake sdl2
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python scripts/build_rom.py
.venv/bin/python -m zelda_env smoke
.venv/bin/python -m zelda_env play
```

Alternativa sem o lock, para resolver dependências novamente:

```bash
.venv/bin/python -m pip install -e '.[build-rom]'
```

Não é necessário ativar a venv; os comandos acima chamam seu Python explicitamente. A aplicação exige Python >= 3.10, e a instalação validada usa 3.12. As bibliotecas Python ficam em `.venv/`. Homebrew instala as ferramentas nativas fora do projeto. PySDL2 também inclui uma distribuição de SDL para macOS como dependência do PyBoy.

## De onde vem o jogo

O script `scripts/build_rom.py` baixa o [oracles-disasm público](https://github.com/Stewmath/oracles-disasm) e o assembler [WLA-DX](https://github.com/vhelin/wla-dx), fixa os commits abaixo e compila Ages em modo vanilla. Não usa um site de download de ROMs.

| Entrada | Versão fixada |
| --- | --- |
| oracles-disasm | `21c924afdc8a13225e849214479d5113da2ec226` |
| WLA-DX 10.6 | `89a90a56be5c2b8cf19a9afa3e1b32384ddb1a97` |
| PyBoy | `2.8.1` |
| SHA-1 esperado da ROM US | `880374fb978b18af4aa529e2e32f7ffb4d7dd2f4` |

A compilação verifica o hash antes de copiar o resultado para `roms/oracle-of-ages.gbc`. Também exporta somente a seção de labels dos símbolos WLA para `roms/oracle-of-ages.sym`, formato aceito pelo PyBoy, e registra a procedência em `roms/manifest.json`. A execução rejeita uma ROM diferente, evitando usar símbolos dos EUA com outra versão do jogo. Para passar uma cópia compatível já existente, use `--rom /caminho/arquivo.gbc`.

O primeiro build pode levar alguns minutos. Builds seguintes reutilizam o cache. WLA-DX é compilado no projeto, sem substituir um assembler instalado no sistema. A opção de compatibilidade do CMake permite compilar essa versão antiga com CMake 4.

O jogo e os assets pertencem a Nintendo/Capcom, conforme o aviso do próprio disassembly. Gerar a ROM a partir desse repositório não a transforma em conteúdo livre. ROM, fontes baixadas e saves ficam ignorados no Git; o procedimento preserva a origem de cada artefato. Consulte os avisos de cada dependência antes de redistribuir binários.

## Saves e checkpoints

São mecanismos diferentes:

- **Save do cartucho:** `saves/<sha1>/battery.sav`. Guarda o progresso que o próprio jogo salvou; é carregado automaticamente na próxima execução e persistido ao encerrar. Encerrar à força pode perder alterações da sessão.
- **Checkpoint do emulador:** `roms/oracle-of-ages.gbc.state`, criado por Z e restaurado por X. Captura a execução completa, inclusive quando não seria possível salvar pelo menu do jogo. Para ROM externa, fica ao lado dela com sufixo `.state`.
- **Checkpoint explícito:** `--load-state caminho` permite abrir uma cópia de outro slot. Para conservar vários, copie o `.state` com outro nome.

Carregar checkpoint reverte a execução. Ao sair depois disso, o save do cartucho corresponde à execução restaurada. Faça backup antes de experimentar com seu progresso. Estados completos não são intercambiáveis entre PyBoy, SameBoy e mGBA; mantenha a versão do PyBoy junto dos checkpoints.

## Verificação de execução

```bash
.venv/bin/python -m zelda_env smoke
```

O comando roda sem janela, com RAM de cartucho isolada em memória. Não carrega nem altera o progresso do jogador. Ele:

1. Avança 600 frames a partir do boot da ROM validada.
2. Salva um checkpoint.
3. Executa uma sequência curta de Start, A e direções.
4. Restaura o checkpoint e repete a mesma sequência.
5. Exige igualdade dos estados serializados e dos pixels finais.
6. Grava `boot.png`, `replay.png`, `boot.state` e `smoke.json` em `output/smoke/`.

Isso verifica boot, API de inputs e replay determinístico no emulador real. Não prova que Link se moveu em gameplay: a sequência pode estar na introdução/menu. A conferência visual e uma sessão jogável complementam o teste. Também não valida percepção, NPCs, terreno ou decisões do modelo.

## Adapter e Laya local

Para ver frame, modo, sala, posição e direção no título, abra o emulador com o comando abaixo e clique na janela.

```bash
.venv/bin/python -m zelda_env play --observe --load-state roms/oracle-of-ages.gbc.state
```

Os experimentos partem de três checkpoints locais. O comando `prepare` deriva os três com inputs normais a partir do checkpoint Z/X do início do jogo em `00:8a`, posição `124,56`. Em outra máquina, use `--checkpoint /caminho/inicial.state` para indicar uma cópia desse ponto. Os arquivos `.state` são locais.

```bash
.venv/bin/python -m pip install -e '.[laya]'
.venv/bin/python -m zelda_env.benchmark prepare
.venv/bin/python -m zelda_env.benchmark run --policy script
.venv/bin/python -m zelda_env.benchmark run --policy random --trials 10
.venv/bin/python -m zelda_env.benchmark run --policy human --scenario approach
.venv/bin/python -m zelda_env.benchmark run --policy laya
```

A política humana recebe a mesma observação no terminal e escolhe entre as mesmas ações. A primeira execução com Laya baixa os pesos fixados do Hugging Face. A inferência ocorre no próprio processo Python, em CPU por padrão. Com os pesos no cache, execute offline com `HF_HUB_OFFLINE=1`.

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m zelda_env.benchmark run --policy laya --format text
HF_HUB_OFFLINE=1 .venv/bin/python -m zelda_env.benchmark run --policy laya \
  --format json --history --output output/benchmark/laya-json-history.json
```

Para assistir ao Laya jogar em loop numa janela local do PyBoy, rode o comando abaixo. Adicione `--scenario approach`, `--scenario dialogue` ou `--scenario exit` para repetir só um cenário. Após dois movimentos bloqueados, o modo ao vivo explora outra direção por até cinco ações. A semente avança a cada volta. Pressione Escape na janela para parar.

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m zelda_env.benchmark run --policy laya --watch
```

Para medir o efeito dessa exploração no cenário de saída, use `--recover` também no modo headless.

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m zelda_env.benchmark run --policy laya \
  --scenario exit --recover --trials 10 --output output/benchmark/laya-recovery.json
```

O PyBoy aguarda enquanto a política escolhe. Cada execução registra resultado, decisões, frames, bloqueios e latência em `output/benchmark/`. As execuções isolam o save de cartucho em memória. Veja os [resultados e limites da avaliação](docs/validation-adapter.md).

## Estrutura

```text
zelda_env/__main__.py       CLI play/smoke e ciclo de vida do emulador
zelda_env/adapter.py        Leitura de WRAM, telemetria e ações de controle
zelda_env/scenarios.py      Preparação e critérios de sucesso dos três cenários
zelda_env/benchmark.py      Execução de políticas e logs de avaliação
zelda_env/laya_policy.py    Inferência local de Choice
scripts/build_rom.py       Build fixado e verificação da ROM
Jogar.command              Launcher do Finder no macOS
requirements.lock.txt      Versões Python resolvidas na máquina validada
docs/                      Pesquisa, arquitetura e registro de validação
.cache/rom-build/          Fontes e build de terceiros, gerados e ignorados
roms/                      ROM, símbolos, manifesto e checkpoint Z/X, ignorados
saves/                     Progresso do jogo, ignorado
output/                    Capturas e relatórios, ignorados
```

A janela de jogo usa o teclado do PyBoy e avança um frame por `tick()`. O smoke e o benchmark usam o mesmo core no modo headless.

## Problemas comuns

- **ROM ausente:** rode o script de build e espere a mensagem de hash validado.
- **Hash incompatível:** verifique a versão. O programa aceita especificamente Ages US vanilla; não altere o hash esperado para contornar a verificação.
- **Erro de SDL:** confirme que a venv está ativa pelo executável usado e que as dependências do lock foram instaladas. Em macOS, execute no terminal da sessão gráfica do usuário.
- **Sem áudio ou erro do dispositivo:** use `--mute`.
- **Janela sem responder ao teclado:** clique nela; os controles são A/S, não Z/X. Z/X são checkpoints.
- **Checkpoint incompatível:** use a mesma ROM e PyBoy 2.8.1. Não passe um save de cartucho em `--load-state`.
- **Falha no build:** a saída identifica a etapa; os diretórios permanecem em `.cache/rom-build/` para inspeção. O script exige que o build termine com sucesso e que a ROM tenha o SHA-1 esperado.

## Próximo passo

Expandir a avaliação para outros pontos de partida e entender por que o Laya insiste em andar contra a parede no cenário de saída. A [proposta de arquitetura](docs/architecture-brainstorm.md) registra o desenho original. A [pesquisa sobre Oracle of Ages](docs/research-oracle-of-ages.md) reúne as referências para a leitura de memória.

Referências: [API PyBoy](https://docs.pyboy.dk/api/pyboy.html), [controles PyBoy](https://docs.pyboy.dk/wiki/development/getting-started.html), [disassembly](https://github.com/Stewmath/oracles-disasm), [WLA-DX](https://github.com/vhelin/wla-dx).
