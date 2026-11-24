# Rodar no Windows

Este guia cobre a instalação e o uso no Windows 10 ou 11, pelo PowerShell.

O código trata caminhos, pastas de dados e travas de arquivo do Windows, e o CI roda os testes unitários no Windows. Os comandos abaixo ainda não foram executados em uma máquina Windows real. Se algum passo falhar, registre a mensagem de erro em uma issue.

## Requisitos

- Windows 10 ou 11, 64 bits.
- [Python 3.12](https://www.python.org/downloads/windows/), instalado com o launcher `py`.
- [Git para Windows](https://git-scm.com/download/win).
- Uma ROM de Oracle of Ages US, sem modificações. Veja [Obter a ROM](#obter-a-rom).

Não é preciso instalar SDL: o pacote `pysdl2-dll` do lock traz as bibliotecas.

## Instalar

```powershell
git clone https://github.com/PKrutaa/NPL-26.2.git
cd NPL-26.2
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Não é preciso ativar a venv. Todos os comandos chamam `.\.venv\Scripts\python.exe` diretamente.

## Obter a ROM

O script `scripts/build_rom.py` ainda não roda no Windows. Use uma destas opções:

- **ROM própria.** Passe o arquivo com `--rom` em cada comando, ou copie para `roms\oracle-of-ages.gbc` na pasta do projeto.
- **Build no WSL2.** Dentro de uma distribuição Linux no WSL2, siga a instalação de Linux do [README](../README.md#outras-plataformas) e rode `scripts/build_rom.py`. Depois copie `roms/oracle-of-ages.gbc` e `roms/oracle-of-ages.sym` para a pasta `roms\` do checkout no Windows.

O programa confere o SHA-1 da ROM e recusa qualquer outra versão.

## Verificar

```powershell
.\.venv\Scripts\python.exe -m zelda_env where
.\.venv\Scripts\python.exe -m zelda_env smoke
```

`where` mostra as pastas em uso. `smoke` abre a ROM sem janela e confirma que o emulador responde. Com a ROM em outro lugar:

```powershell
.\.venv\Scripts\python.exe -m zelda_env smoke --rom "C:\Games\Ages US.gbc"
```

## Jogar

Dê dois cliques em `Jogar.cmd`, ou rode:

```powershell
.\.venv\Scripts\python.exe -m zelda_env play
.\.venv\Scripts\python.exe -m zelda_env play --mute --scale 5
```

Os controles são os mesmos do [README](../README.md#jogar-depois-da-instalação).

## Laya jogando sozinho

Instale o Laya e baixe os pesos uma vez, com rede. Depois disso o agente roda offline.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[laya]"
.\.venv\Scripts\python.exe -m zelda_env seed
.\.venv\Scripts\python.exe -m zelda_env.model prepare
```

Rodar o agente:

```powershell
.\.venv\Scripts\python.exe -m zelda_env.player                       # com janela
.\.venv\Scripts\python.exe -m zelda_env.player --headless --steps 600
.\.venv\Scripts\python.exe -m zelda_env.agent --headless --decisions 300   # linha de base com opções
```

No Windows o Laya roda em CPU (`--device cpu`, o padrão). A opção `mps` existe só no macOS.

A sessão do agente fica em `output\player\`, com `trace.jsonl` de uma linha por input e `summary.json` com o resumo. A linha de base grava em `output\agent\`.

## Testes por trecho

```powershell
.\.venv\Scripts\python.exe -m zelda_env.segments list
.\.venv\Scripts\python.exe -m zelda_env.segments capture output\agent
.\.venv\Scripts\python.exe -m zelda_env.segments run espada --decisions 600
```

Veja [Testes por trecho e por caso](validation-agent.md#testes-por-trecho-e-por-caso) para o que cada comando faz.

## Supervisor

O supervisor fica ligado por padrão. Instale o [Ollama para Windows](https://ollama.com/download/windows); o instalador deixa o servidor rodando em segundo plano.

```powershell
ollama pull gemma3:4b
.\.venv\Scripts\python.exe -m zelda_env.player
.\.venv\Scripts\python.exe -m zelda_env.player --no-supervisor
```

Sem o Ollama ou sem os pesos, o agente avisa e roda sem supervisor.

## Testes unitários

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Os testes não precisam de ROM, modelo ou janela.

## Onde ficam os dados

Se o checkout já tem as pastas `roms\`, `saves\` e `output\`, o projeto usa essas pastas. Sem elas, grava na pasta do usuário:

| Conteúdo | Pasta |
| --- | --- |
| ROM, saves e saídas | `%LOCALAPPDATA%\zelda-env\data` |
| Cache | `%LOCALAPPDATA%\zelda-env\cache` |

Para escolher outra pasta, use `--data-dir` ou a variável de ambiente:

```powershell
$env:ZELDA_ENV_DATA_DIR = "D:\zelda-env"
.\.venv\Scripts\python.exe -m zelda_env where
```

## Diferenças em relação ao macOS e ao Linux

| Tema | macOS e Linux | Windows |
| --- | --- | --- |
| Python da venv | `.venv/bin/python` | `.\.venv\Scripts\python.exe` |
| Extras do pip | `'.[laya]'` | `".[laya]"` |
| Variável de ambiente | `HF_HUB_OFFLINE=1 comando` | `$env:HF_HUB_OFFLINE = "1"` e depois o comando |
| Launcher | `Jogar.command` ou `./jogar.sh` | `Jogar.cmd` |
| Build da ROM | `scripts/build_rom.py` | Não disponível. Use WSL2 ou uma ROM própria. |

## Problemas comuns

- **`py` não é reconhecido:** reinstale o Python marcando a opção do launcher, ou use o caminho completo de `python.exe`.
- **Execução de scripts bloqueada:** o guia não usa `Activate.ps1`, então a política de execução do PowerShell não interfere. Chame sempre `.\.venv\Scripts\python.exe`.
- **Caminho com espaços:** coloque o caminho entre aspas duplas, como em `--rom "C:\Games\Ages US.gbc"`.
- **Save em uso:** outra janela do jogo ou outra sessão do agente usa o mesmo arquivo. Feche a outra, ou use `--directory` com outra pasta.
- **Sem áudio ou erro do dispositivo:** use `--mute`.
- **Hash incompatível:** a ROM não é a Ages US sem modificações.
