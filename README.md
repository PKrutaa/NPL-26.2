# Oracle of Ages · ambiente PyBoy para experimentos com agentes

O projeto usa o PyBoy para rodar Oracle of Ages US, permitir controle humano e preparar experimentos de controle por agentes.

A [spec de portabilidade para Windows e Linux](docs/spec-portabilidade-windows-linux.md) detalha a migração proposta, a matriz de suporte e os critérios de aceitação.

## Estado atual

| Parte | Estado |
| --- | --- |
| Emulador | Jogável no macOS. A CLI oferece janela SDL2, controles por teclado, save de cartucho e checkpoints. |
| Build da ROM | Script com commits fixados, verificação de SHA-1 e exportação de símbolos para o PyBoy. |
| Replay | Smoke headless confirma que a mesma sequência de inputs, repetida após restaurar um checkpoint, produz o mesmo estado serializado e os mesmos pixels. |
| Adapter semântico | Lê sala, posição, direção, interações visíveis, quadrantes de colisão em salas pequenas e estado de diálogo. Executa ações curtas via PyBoy. |
| Laya local | Inferência offline validada com o checkpoint clássico. Concluiu aproximação e diálogo com texto sem histórico, e travou na saída. |
| Agente autônomo | O Laya escolhe entre opções que o emulador confirmou. Uma memória impede repetir o que já falhou. Em 150 decisões a partir do boot, recebeu a espada, falou com a Maku Tree e entrou no passado. Veja [Laya jogando sozinho](#laya-jogando-sozinho). |
| Supervisor opcional | Um LLM pequeno e local escolhe uma opção quando o agente fica sem novidade. Desligado por padrão. Ainda sem evidência de ganho. |
| Windows e Linux | Código preparado e testes unitários no CI. Ainda sem certificação em máquina real. Veja [Outras plataformas](#outras-plataformas). |

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

Para ver onde ficam ROM, save, saídas e cache nesta máquina:

```bash
.venv/bin/python -m zelda_env where
```

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

## Outras plataformas

O mesmo código Python roda em Windows e Linux. Os comandos abaixo seguem a [spec de portabilidade](docs/spec-portabilidade-windows-linux.md). Eles ainda não foram executados em máquina real. O CI roda os testes unitários nos três sistemas, sem ROM e sem janela.

| Operação | Windows (PowerShell) | Linux (Bash) |
| --- | --- | --- |
| Criar o ambiente | `py -3.12 -m venv .venv` | `python3.12 -m venv .venv` |
| Instalar | `.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt` e depois `.\.venv\Scripts\python.exe -m pip install --no-deps -e .` | `.venv/bin/python -m pip install -r requirements.lock.txt` e depois `.venv/bin/python -m pip install --no-deps -e .` |
| Verificar | `.\.venv\Scripts\python.exe -m zelda_env smoke --rom "C:\Games\Ages US.gbc"` | `.venv/bin/python -m zelda_env smoke --rom "/home/me/Games/Ages US.gbc"` |
| Jogar | `Jogar.cmd` | `./jogar.sh` |

O passo a passo completo para Windows, incluindo o agente e os testes por trecho, está em [Rodar no Windows](docs/windows.md).

No Linux, o build da ROM usa `git`, `cmake`, `gcc`, `make` e `bash`. No Windows, o script de build ainda não roda: passe uma ROM compatível com `--rom`, ou gere a ROM em Linux, macOS ou WSL2 e copie o arquivo.

Sem dados no checkout, o projeto grava em pastas do usuário:

| Sistema | Dados (ROM, saves, saídas) | Cache (build) |
| --- | --- | --- |
| Windows | `%LOCALAPPDATA%\zelda-env\data` | `%LOCALAPPDATA%\zelda-env\cache` |
| Linux | `$XDG_DATA_HOME/zelda-env` ou `~/.local/share/zelda-env` | `$XDG_CACHE_HOME/zelda-env` ou `~/.cache/zelda-env` |
| macOS | `~/Library/Application Support/zelda-env` | `~/Library/Caches/zelda-env` |

A ordem de escolha é: `--data-dir`, depois `ZELDA_ENV_DATA_DIR`, depois as pastas `roms/`, `saves/` e `output/` que já existirem no checkout, depois a pasta do usuário. O cache usa `ZELDA_ENV_CACHE_DIR`.

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

- **Save do cartucho:** `saves/<sha1>/battery.sav`. Guarda o progresso que o próprio jogo salvou; é carregado automaticamente na próxima execução e persistido ao encerrar. Encerrar à força pode perder alterações da sessão. A gravação usa um arquivo temporário e troca atômica, então uma falha mantém o save anterior. Uma segunda janela de `play` no mesmo save é recusada.
- **Checkpoint do emulador:** `roms/oracle-of-ages.gbc.state`, criado por Z e restaurado por X. Captura a execução completa, inclusive quando não seria possível salvar pelo menu do jogo. Para ROM externa, fica ao lado dela com sufixo `.state`.
- **Checkpoint explícito:** `--load-state caminho` permite abrir uma cópia de outro slot. Para conservar vários, copie o `.state` com outro nome.

Para trazer um save de outra pasta ou de outro computador, use `import-save`. O comando valida o tamanho, copia os bytes e guarda uma cópia `.bak` do save que estava ativo. A origem não é alterada.

```bash
.venv/bin/python -m zelda_env import-save --source /caminho/battery.sav
```

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

Os experimentos partem de três checkpoints locais. O comando `seed` joga do boot até o primeiro ponto controlável, em `00:8a`, posição `124,56`, só com inputs de controle. Ele grava `output/inicio.state` e um `.json` com a procedência. O comando `prepare` deriva os três cenários a partir desse ponto. Os arquivos `.state` são locais.

```bash
.venv/bin/python -m pip install -e '.[laya]'
.venv/bin/python -m zelda_env seed
.venv/bin/python -m zelda_env.model prepare
.venv/bin/python -m zelda_env.benchmark prepare
.venv/bin/python -m zelda_env.benchmark run --policy script
.venv/bin/python -m zelda_env.benchmark run --policy random --trials 10
.venv/bin/python -m zelda_env.benchmark run --policy human --scenario approach
.venv/bin/python -m zelda_env.benchmark run --policy laya
```

A política humana recebe a mesma observação no terminal e escolhe entre as mesmas ações. O comando `model prepare` baixa os pesos fixados do Hugging Face e faz uma inferência de prova. É o único comando que usa a rede. Os demais carregam o Laya em modo offline e, se o cache estiver incompleto, param com a instrução de preparo. A inferência ocorre no próprio processo Python, em CPU por padrão. A opção `--device mps` só é aceita onde o PyTorch expõe esse backend.

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

## Campanha local

O modo campanha executa uma sequência de objetivos e salva o estado entre marcos em `output/campaign/`. Ele retoma do último marco existente no diretório. A navegação busca sequências de inputs em uma cópia headless do PyBoy, e o Laya local escolhe entre A e B quando o diálogo aceita entrada. A partida principal evolui com inputs de controle e usa SRAM em memória.

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m zelda_env.campaign
```

Use `--headless --directory output/campaign-verify` para validar em uma execução separada e `--script-dialogue` para comparar com a política fixa da tecla A. O modo campanha começa no checkpoint usado para o cenário `exit`, gerado pelo comando `prepare` acima.

No benchmark, `--lookahead` mostra o efeito próximo de cada direção ao modelo e exclui ações que o teste no emulador confirmou estarem bloqueadas. No checkpoint da saída, o Laya deixou de colidir, mas ainda se desviou e esgotou as 12 decisões. A busca usada na campanha recebe objetivos de sala e de interação definidos à mão.

## Laya jogando sozinho

O modo agente não usa rotas escritas à mão. Ele parte do seed do boot e repete este ciclo:

1. **Levantamento.** Uma cópia headless do emulador testa movimentos a partir do estado atual e lista o que é possível na sala: saídas, conversas, objetos que podem ser empurrados, uso de item em obstáculo ou no chão, luta de espada contra um inimigo e pontos que disparam uma cena.
2. **Escolha.** O Laya escolhe uma dessas opções. Ele recebe um objetivo curto, como `Go north.`, e opções curtas, como `Go north to a new room` ou `Attack the enemy`. O planner converte a escolha em inputs de controle.
3. **Memória.** Uma opção já tentada na mesma área, sem progresso na história, sai da lista. Uma conversa volta para a lista quando o personagem tem uma fala nova. Sem nada novo na sala, o agente vai para a área conhecida mais próxima que ainda tem opções.
4. **Parada.** Quando não resta nada novo em lugar nenhum, o agente registra o impasse e para. Ele não fica repetindo a mesma ação.

```bash
.venv/bin/python -m zelda_env.agent                     # com janela
.venv/bin/python -m zelda_env.agent --headless --decisions 300
.venv/bin/python -m zelda_env.agent --fresh             # recomeça do seed
.venv/bin/python -m zelda_env.agent --policy random     # comparação: sorteia entre as mesmas opções
```

A sessão fica em `output/agent/`: `latest.state` e `memory.json` para retomar, `trace.jsonl` com uma linha por decisão e `summary.json` com o resumo. Cada decisão registra a origem: `laya`, `forced` (só havia uma opção nova), `frontier` (viagem até uma área com opções), `supervisor` ou `fallback`. O resumo traz `max_repeats_of_one_option_in_one_story_state`, que mede repetição.

Os objetivos em `zelda_env/agent.py` são etapas escritas à mão: uma sala de referência, o que fazer ao chegar e um teste lido da memória do jogo, como a flag da espada. O agente converte a sala de referência em uma direção. Eles não contêm rotas nem coordenadas. A lista vai até a primeira essência.

Cada decisão registra também a vida de Link. O levantamento descarta rotas que causam dano, e uma decisão que mata Link é desfeita e nunca mais oferecida naquele ponto.

### Testes por trecho

Para iterar em um trecho do jogo sem rodar desde o boot, o agente salva estado e memória a cada objetivo concluído, e `zelda_env.segments` roda de um desses pontos até o objetivo seguinte:

```bash
.venv/bin/python -m zelda_env.segments list
.venv/bin/python -m zelda_env.segments capture output/agent
.venv/bin/python -m zelda_env.segments run chave-do-cemiterio --decisions 150
```

Um trecho passa quando o objetivo é concluído sem corte de ciclo e sem impasse. Veja os [detalhes](docs/validation-agent.md#testes-por-trecho).

### Supervisor opcional

O supervisor é um LLM pequeno que roda no [Ollama](https://ollama.com) local. Ele é consultado quando o agente fica sem opção nova, ou depois de 20 decisões sem progresso na história. Ele recebe o objetivo, a sala, as últimas ações e a lista de opções, e devolve o id de uma opção ou `abstain`. O código rejeita JSON inválido, id fora da lista e resposta depois de 20 segundos. Nesses casos o agente segue com a recuperação própria. O limite é de duas consultas por impasse, com seis decisões de intervalo.

```bash
ollama pull qwen2.5:1.5b          # uma vez, com rede
ollama serve                      # se o servidor não estiver rodando
.venv/bin/python -m zelda_env.agent --supervisor qwen2.5:1.5b
```

Sem o servidor ou sem os pesos, o agente avisa e roda sem supervisor. Veja as [medições](docs/validation-agent.md).

## Testes

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Os testes não precisam de ROM, modelo ou janela. Eles cobrem caminhos por plataforma, validação de ROM, gravação atômica, lock de save, o contrato do supervisor e a memória do agente.

## Estrutura

```text
zelda_env/__main__.py       CLI play/smoke/seed/import-save/where e ciclo de vida do emulador
zelda_env/paths.py          Pastas de dados e cache, validação de ROM, gravação atômica e lock
zelda_env/adapter.py        Leitura de WRAM, telemetria e ações de controle
zelda_env/scenarios.py      Preparação e critérios de sucesso dos três cenários
zelda_env/benchmark.py      Execução de políticas e logs de avaliação
zelda_env/laya_policy.py    Inferência local de Choice
zelda_env/lookahead.py      Simulação local de ações e busca de rotas
zelda_env/campaign.py       Objetivos e checkpoints da campanha com rotas escritas à mão
zelda_env/survey.py         Levantamento das opções da sala na cópia headless
zelda_env/agent.py          Agente autônomo: memória, escolha do Laya e objetivos
zelda_env/supervisor.py     Contrato e backend do LLM supervisor
zelda_env/model.py          Preparo e verificação offline dos pesos do Laya
tests/                      Testes unitários sem ROM
scripts/build_rom.py       Build fixado e verificação da ROM
Jogar.command              Launcher do Finder no macOS
Jogar.cmd                  Launcher do Windows
jogar.sh                   Launcher do Linux
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
- **Save em uso:** outra janela de `play` está aberta com o mesmo save. Feche a outra janela.
- **Pesos do Laya ausentes:** rode `python -m zelda_env.model prepare` uma vez, com rede.
- **Hash incompatível:** verifique a versão. O programa aceita especificamente Ages US vanilla; não altere o hash esperado para contornar a verificação.
- **Erro de SDL:** confirme que a venv está ativa pelo executável usado e que as dependências do lock foram instaladas. Em macOS, execute no terminal da sessão gráfica do usuário.
- **Sem áudio ou erro do dispositivo:** use `--mute`.
- **Janela sem responder ao teclado:** clique nela; os controles são A/S, não Z/X. Z/X são checkpoints.
- **Checkpoint incompatível:** use a mesma ROM e PyBoy 2.8.1. Não passe um save de cartucho em `--load-state`.
- **Falha no build:** a saída identifica a etapa; os diretórios permanecem em `.cache/rom-build/` para inspeção. O script exige que o build termine com sucesso e que a ROM tenha o SHA-1 esperado.

## Próximo passo

O agente conclui sozinho, desde o boot, os cinco primeiros objetivos: espada, Árvore Maku, viagem ao passado, pá e salvar a Árvore Maku. O sexto, a chave do cemitério, ainda não foi concluído em execução limpa. Para a primeira dungeon faltam chefes, projéteis e recuperação de corações. A validação em máquinas Windows e Linux reais também está pendente.

O [ADR 0001](docs/adr/0001-agente-por-opcoes-com-memoria.md) explica como o agente funciona e o que ele não cobre. A [validação do agente](docs/validation-agent.md) traz os números e o estado de cada item da spec. A [proposta de arquitetura](docs/architecture-brainstorm.md) registra o desenho original. A [pesquisa sobre Oracle of Ages](docs/research-oracle-of-ages.md) reúne as referências para a leitura de memória.

Referências: [API PyBoy](https://docs.pyboy.dk/api/pyboy.html), [controles PyBoy](https://docs.pyboy.dk/wiki/development/getting-started.html), [disassembly](https://github.com/Stewmath/oracles-disasm), [WLA-DX](https://github.com/vhelin/wla-dx).
