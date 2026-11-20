# Spec de portabilidade para Windows e Linux

- **Status** — proposta para implementação
- **Data** — 20 de novembro de 2026
- **Projeto** — Oracle of Ages US com PyBoy, adapter semântico e Laya local

## 1. Objetivo

Entregar um fluxo documentado e reproduzível para instalar a partir de um clone limpo, fornecer ou gerar a ROM compatível, rodar o smoke headless, abrir a janela, jogar com teclado, persistir saves e executar o Laya offline em Windows e Linux. O fluxo deve partir do mesmo código Python que roda no macOS. A portabilidade cobre o modo campanha e os cenários que já existem no checkout que será migrado. A conclusão da campanha tem sua própria trilha de evolução e critérios de aceite na seção 8.2.

A instalação mínima deve funcionar com ROM local e sem modelo. A instalação completa deve oferecer preparação do modelo, benchmark e campanha com CPU local. Um release declara cada combinação plataforma × modo somente depois de passar nos critérios da seção 10.

## 2. Base atual e diferenças entre os checkouts

A base publicada em `4362f89` no GitHub tem `play`, `smoke`, benchmark, adapter e visualização do Laya. O checkout de trabalho em `e213985` acrescenta recuperação, simulação em uma cópia headless do PyBoy e campanha com checkpoints por marco. Em 20 de novembro o último marco observado no macOS foi `19-bloco-maku`, sala `04:0a` no Maku Path do passado. Use essa base de trabalho ou sua integração posterior ao implementar os testes de campanha. O histórico de validação desta spec parte do macOS Apple Silicon. Disponibilidade de dependências em outras plataformas é evidência de viabilidade, e o suporte do projeto depende dos testes propostos abaixo.

| Área | Comportamento atual | Implicação para a migração |
| --- | --- | --- |
| Instalação | README usa Homebrew e `.venv/bin/python`. `pyproject.toml` aceita Python ≥ 3.10. O lock foi resolvido no macOS com Python 3.12. | Definir uma linha de Python certificada e ambientes reproduzíveis por alvo. |
| Janela | `play`, `benchmark --watch` e campanha gráfica usam SDL2. `Jogar.command` usa zsh e sintaxe do Finder. O título usa o foco de teclado do SDL. | Fornecer inicialização nativa para cada plataforma e testar foco, áudio, escala e fechamento em desktop real. |
| Headless | PyBoy usa `window="null"`. Benchmark, campanha e cópia para simulação usam SRAM em memória. | Testar sem servidor de vídeo. Separar importação da biblioteca SDL de criação de janela. |
| ROM | `scripts/build_rom.py` verifica `git`, `cmake`, `make`, `cc`. Faz checkout fixado, chama CMake e executa GNU Make com assemblers em `build/binaries`. | Descobrir executáveis, traduzir a fronteira shell × processo nativo e validar byte a byte antes de instalar a saída. |
| Caminhos | As CLIs derivam ROM, saves e saídas da raiz do código. `Z/X` usa o checkpoint do PyBoy junto da ROM. | Centralizar o armazenamento e preservar consulta/importação dos caminhos anteriores. |
| Laya | Extra `laya==0.5.0`, encoder clássico com revisão fixa, CPU padrão. Benchmark expõe `mps`. O lock base exclui o conjunto do modelo. | Fixar dependências de inferência por alvo, preparar cache explicitamente e habilitar `mps` só onde suportado. |
| Cenários | `prepare` depende de checkpoint jogável em `00:8a`, XY `124,56`. Campanha depende desse ponto e dos marcos locais. | Documentar criação e passagem do estado inicial. A execução de um clone limpo precisa de uma rota determinística de preparação ou de um procedimento manual que produza um ponto validado. |
| Evidência | Há smoke, verificações manuais e relatórios locais. | Criar gates automáticos, uma ficha de verificação gráfica e evidência por release. |

## 3. Matriz de suporte

| Alvo inicial | Runtime | Modos de aceitação | Observações |
| --- | --- | --- | --- |
| Windows 11 x64, sessão de desktop | CPython 3.12 x64, PowerShell ou CMD | SDL2, headless, ROM externa, build MSYS2, Laya CPU offline | PyBoy e Laya rodam no Windows nativo. MSYS2 é uma dependência da rota de build. |
| Ubuntu 24.04 LTS x86-64 | CPython 3.12, ambiente virtual | SDL2, headless, ROM externa, build GNU, Laya CPU offline | Testar Wayland e X11 ou XWayland e registrar o driver SDL utilizado. |
| macOS arm64 | Python 3.12, ambiente virtual | Fluxos atualmente funcionais como regressão | Preservar o launcher e os comandos atuais na transição. |

Certificar uma versão de patch do Python por release e registrar o patch real em todos os relatórios. Outros Linux glibc, Windows ARM64, Linux ARM64, distribuições musl, WSL como desktop, CUDA, empacotamento `.exe`/AppImage e alterações de gameplay ficam em etapas futuras. A manutenção de `requires-python` é independente da matriz testada. Restringir a faixa declarada só se a implementação ou o resolver exigir.

Há wheels CPython 3.12 do PyBoy 2.8.1 para Windows x86-64 e Linux x86-64 com tags manylinux. Validar os wheels de todas as dependências do perfil planejado com `pip download --only-binary=:all:` no alvo ou no runner correspondente. Considerar wheel publicado como artefato disponível, e instalação, importação e execução como verificações distintas. [PyBoy 2.8.1 no PyPI](https://pypi.org/project/pyboy/2.8.1/)

## 4. Experiência de instalação e comandos

### 4.1 Perfis

- **Base** inclui pacote do projeto, PyBoy, Pillow e dependências de runtime. Funciona com `--rom`, smoke, play e políticas por script, aleatória e humana.
- **Build** acrescenta PyYAML e toolchain documentada. Gera a ROM localmente no checkout ou no diretório de dados configurado.
- **Laya CPU** acrescenta o stack do modelo, com lock específico de plataforma e instalação do wheel CPU do PyTorch conforme o índice oficial. Uma instalação do perfil base precisa continuar funcionando quando esse extra estiver ausente. [Instalação do PyTorch](https://pytorch.org/get-started/locally/)

Gerar locks separados para base/build e para o extra de inferência, com nomes que incluam sistema, arquitetura e Python. Fixar também transitivas, wheel/índice do PyTorch e hashes quando o formato de lock suportar. Manter `pyproject.toml` como contrato do pacote. O lock atual do macOS é ponto de partida para resolução. Seu NumPy 2.5.4 exige Python 3.12 ou superior. PyTorch `2.15.0+cpu` é candidato ao lock x64 dos dois alvos, com wheels CPython 3.12 publicados no índice CPU. Verificar a resolução conjunta com Laya antes de promovê-lo. Obter o wheel do Torch por URL/hash ou por etapa dedicada ao índice oficial, com as demais dependências resolvidas a partir do PyPI. [Metadados do NumPy](https://pypi.org/pypi/numpy/2.5.4/json) · [Índice CPU do PyTorch](https://download.pytorch.org/whl/cpu/torch/) O conjunto de versões observado em uma máquina não substitui a resolução na matriz. A instalação automatizada deve usar o Python do ambiente virtual, rodar `pip check` e informar qual perfil ficou disponível.

### 4.2 Inicialização

Manter as CLIs existentes como entrada principal. As chamadas abaixo explicitam o executável do ambiente e funcionam a partir da raiz do checkout após instalar o perfil correspondente. A spec propõe adicionar launchers finos `Jogar.cmd` e `jogar.sh`. Os launchers devem resolver a pasta pelo próprio arquivo, preservar argumentos com aspas, propagar exit code, apresentar uma mensagem quando a venv estiver ausente e delegar ao módulo Python.

| Operação | PowerShell | Bash no Linux |
| --- | --- | --- |
| Criar venv | `py -3.12 -m venv .venv` | `python3.12 -m venv .venv` |
| Smoke | `.\.venv\Scripts\python.exe -m zelda_env smoke --rom "C:\Games\Ages US.gbc"` | `.venv/bin/python -m zelda_env smoke --rom "/home/me/Games/Ages US.gbc"` |
| Jogar com telemetria | `.\.venv\Scripts\python.exe -m zelda_env play --observe` | `.venv/bin/python -m zelda_env play --observe` |
| Gerar cenários | `.\.venv\Scripts\python.exe -m zelda_env.benchmark prepare --checkpoint ".\output\inicio.state"` | `.venv/bin/python -m zelda_env.benchmark prepare --checkpoint "./output/inicio.state"` |
| Ver o agente | `.\.venv\Scripts\python.exe -m zelda_env.benchmark run --policy laya --watch` | `.venv/bin/python -m zelda_env.benchmark run --policy laya --watch` |
| Retomar campanha | `.\.venv\Scripts\python.exe -m zelda_env.campaign` | `.venv/bin/python -m zelda_env.campaign` |

`play` sem `--rom` requer que a ROM já esteja no local padrão ou legado. O README deverá mostrar a instalação por lock antes dos comandos de execução. A preparação de um clone limpo deve documentar estas sequências de ponta a ponta:

- **Só jogar** — criar venv, instalar lock base, apontar a ROM válida, executar smoke, abrir `play` e confirmar onde o SRAM foi gravado.
- **Construir** — instalar o perfil build e a toolchain selecionada, rodar o comando de build a partir do desktop/terminal do usuário, verificar manifesto e repetir o fluxo de smoke.
- **Laya e campanha** — instalar lock CPU, preparar o snapshot online, criar e validar o seed jogável, rodar script de referência, rodar o Laya offline e retomar um marco em outra invocação.
- **Segundo computador** — fazer uma cópia explícita de SRAM e, se houver suporte comprovado para o par, do savestate. Confirmar tamanho, hash, versão do PyBoy e restore antes de promover a cópia a save ativo no destino.

O procedimento manual de seed precisa explicar como criar um save novo, chegar à sala, conferir XY com `--observe` e salvar no caminho explícito. A automação de seed, se escolhida, deve usar inputs normais desde boot/menu e validar a posição observada antes de gravar. O arquivo local do seed deve carregar metadados de proveniência para permitir selecionar outro ponto sem confundir os cenários.

A ajuda e erros devem indicar o comando e as dependências apropriados ao sistema. Também validar execução com o diretório atual fora da raiz e caminho absoluto para o Python da venv.

## 5. Pipeline da ROM

### 5.1 Contrato comum

- Validar Oracle of Ages US vanilla com tamanho de 1.048.576 bytes e SHA‑1 `880374fb978b18af4aa529e2e32f7ffb4d7dd2f4`. Para ROM fornecida pelo usuário, aceitar caminho com espaços, Unicode e extensão válida de arquivo pelo conteúdo. Uma ROM existente com bytes diferentes dá erro sem alteração. Os símbolos adjacentes podem ser importados somente com perfil coerente. O adapter usa offsets fixados para essa variante.
- Construir a partir do disassembly em `21c924afdc8a13225e849214479d5113da2ec226` e WLA-DX em `89a90a56be5c2b8cf19a9afa3e1b32384ddb1a97`. Manter as revisões em um lugar só. Exportar labels de `[labels]` para `oracle-of-ages.sym` com UTF‑8 e LF. [Disassembly fixado](https://github.com/Stewmath/oracles-disasm/tree/21c924afdc8a13225e849214479d5113da2ec226) · [WLA-DX fixado](https://github.com/vhelin/wla-dx/tree/89a90a56be5c2b8cf19a9afa3e1b32384ddb1a97)
- Documentar dois caminhos equivalentes. **ROM externa** usa `--rom` e dispensa toolchain. **Build local** faz checkout, compila ferramentas, roda `make ages`, valida a saída e a instala. O manifesto deve registrar revisões, gerador e versões da toolchain, arquitetura, tamanho, SHA‑1 da ROM e hash dos símbolos.
- Quando um checkout ou uma compilação fica incompleta, encerrar com etapa, comando e path de log. Na repetição, reutilizar cache completo e compatível. Invalidar só a chave que mudou. Separar cache por plataforma, gerador, arquitetura e pins. Preparar ROM, símbolos e manifesto em staging, publicar arquivos completos sob lock e gravar o manifesto por último. Na inicialização, conferir a consistência de saídas declaradas pelo manifesto. Manter cópia válida anterior se a preparação falhar.
- Artefatos da ROM, assets upstream, snapshots de modelo, saves e capturas do jogo ficam em armazenamento local. CI público guarda resultados de verificação em texto/JSON. Uma fixture binária de jogo só pode entrar na infraestrutura após escolha de um mecanismo de acesso e permissão adequados ao projeto.

### 5.2 Linux

Usar Git, CMake, Ninja, GCC, GNU Make e Bash. A base Ubuntu deve ter `python3.12-venv`, bibliotecas de runtime SDL2 se a rota de wheel precisar delas e `xvfb` só para validação gráfica virtual. Montar o build WLA-DX com gerador explícito `Ninja` e alvos `wla-gb` e `wlalink`. Resolver os executáveis a partir da árvore realmente produzida pelo gerador. Passar os caminhos absolutos do Python e das ferramentas ao build do disassembly. Testar também paths que contenham espaços e caracteres não ASCII. [CLI do CMake](https://cmake.org/cmake/help/latest/manual/cmake.1.html)

### 5.3 Windows

O runtime segue em CPython nativo `.venv\Scripts\python.exe`. A rota de build proposta usa **MSYS2 UCRT64**, um gerador CMake de configuração única e GCC UCRT64. GNU Make e Bash executam as receitas do disassembly. A etapa de prova deverá fixar a lista exata de pacotes e verificar `cygpath`, `bash`, `make`, `cmake`, `ninja`, `gcc` e a variante do Git realmente usada. Comandos Windows do usuário podem acionar um launcher de build que entra no ambiente UCRT64 de forma explícita. [Ambientes MSYS2](https://www.msys2.org/docs/environments/) · [CMake no MSYS2](https://www.msys2.org/docs/cmake/) · [Paths no MSYS2](https://www.msys2.org/docs/filesystem-paths/)

Pontos de implementação:

1. Separar a função que resolve a toolchain da função que compila. Descobrir `wla-gb.exe` e `wlalink.exe` com testes de existência e execução. Rejeitar a combinação ambígua de outro Make ou CMake encontrado no PATH antes de iniciar o build.
2. Rodar a parte Unix com Bash/GNU Make, evitando interpolar paths do usuário como código. Traduzir no ponto de entrada de cada ferramenta. Os valores de `PYTHON`, `CC` e `LD` atravessam expansão de receita, e nesse ponto precisam de quoting testado ou de wrappers gerados em staging. Na fronteira nativa, verificar conversão automática de argumentos MSYS2 e restringir qualquer exclusão aos argumentos afetados.
3. Provar o build em checkout Windows com CRLF configurado para o usuário. Garantir LF para scripts executados por Bash e evitar alterar a configuração Git global. Se o Makefile fixado tiver limitações de quoting, usar cache de build em raiz curta independente do checkout e ainda testar paths públicos com espaços e Unicode.
4. Registrar checksum do build Windows e do Linux/macOS. O Makefile upstream chama um verificador próprio com tratamento permissivo. O wrapper do projeto define sucesso somente depois de validar o hash esperado. Considerar uma rota WSL2 de **build auxiliar** se a prova do MSYS2 falhar, com ROM resultante importada via `--rom` no runtime nativo. Qualquer alternativa exige a mesma validação e um novo registro de decisão.

## 6. Caminhos, saves e compatibilidade

Criar um módulo compartilhado de configuração de caminhos, com descoberta central de dados, cache e saída. Definir precedência por recurso na implementação:

1. Parâmetro explícito do recurso, como `--rom`, `--load-state`, `--checkpoint`, `--states`, `--directory`, `--output` e o novo `--data-dir` quando se trata da raiz.
2. Ambiente por processo, como `ZELDA_ENV_DATA_DIR` e `ZELDA_ENV_CACHE_DIR`.
3. Dados legados existentes para o recurso, quando ainda não há dados no local novo.
4. Diretórios nativos do usuário, por exemplo uma pasta dedicada sob `%LOCALAPPDATA%` no Windows, `$XDG_DATA_HOME`/ `$XDG_CACHE_HOME` ou defaults XDG no Linux e Library no macOS. Selecionar uma implementação própria pequena ou uma biblioteca de paths nativos. Dados persistentes devem ser separados de caches apagáveis. [XDG Base Directory](https://specifications.freedesktop.org/basedir-spec/latest/) · [Windows Known Folders](https://learn.microsoft.com/windows/win32/shell/knownfolderid)

| Tipo | Contrato |
| --- | --- |
| SRAM do modo humano | 8.192 bytes, identificada pelo hash da ROM. Importação copia bytes validados e mantém a origem. Save ativo é escrito em temporário único no mesmo diretório e publicado com substituição atômica após fechar os handles. Tratar falhas de substituição no Windows e manter último save íntegro. |
| Checkpoint `Z/X` | Controlar o destino de escrita de forma independente da ROM usando os eventos do PyBoy ou deixando um modo legado explícito. Validar no código da versão fixada como o plugin resolve a extensão `.state`. Permitir carregar o arquivo já existente junto da ROM. Uma ROM em mídia somente leitura deve funcionar com save e checkpoint em caminho gravável. |
| Checkpoint de campanha | Namespace separado do modo humano. Manter nome do marco, identificador da ROM, versão do PyBoy e versão do formato da campanha. Na retomada, validar o mais recente antes de usar. Se estiver corrompido ou incompatível, informar qual é o último válido e permitir retomada explícita dele. |
| Smoke e políticas | SRAM em memória e saídas próprias. A suíte deve calcular o hash do save humano antes e depois de sessões headless, `--watch` e campanha. |
| Concorrência | Duas execuções que gravam o mesmo perfil precisam de lock por perfil ou recusa clara do segundo escritor. `play` pode coexistir com benchmark/campanha isolados. Temporários incompletos ficam fora da descoberta de saves e checkpoints válidos. |

Compatibilidade de `.sav` e de `.state` são critérios separados. Primeiro certificar restore de `.state` na mesma plataforma com PyBoy fixado. Depois fazer um teste de round-trip em que a origem exporta e o destino abre, inspeciona estado lógico, avança frames e salva. Reportar compatibilidade cruzada apenas nas combinações que passarem. Se a portabilidade do checkpoint falhar, preservar o original e documentar recomeço a partir de SRAM ou criação de um checkpoint no destino. Não exigir igualdade de bytes serializados entre plataformas como critério padrão de compatibilidade. [PyBoy API de savestates](https://docs.pyboy.dk/api/pyboy.html)

## 7. SDL, áudio e sessão gráfica

- Usar o PySDL2/SDL2 exatamente no nível requerido por PyBoy. Verificar o que `pysdl2-dll` empacota para cada alvo e registrar qual biblioteca foi carregada. No Ubuntu, documentar o pacote SDL2 do sistema caso essa rota seja escolhida. No Windows, evitar dependência de DLL casual do PATH. No macOS, manter a rota que passou na regressão. [Instalação do PyBoy](https://docs.pyboy.dk/wiki/development/getting-started.html) · [pysdl2-dll](https://pypi.org/project/pysdl2-dll/)
- Rodar `play`, `play --observe`, `benchmark --watch` e campanha gráfica em sessão de usuário. Conferir setas, A/S, Enter, Backspace, P, Z/X e Esc. Verificar foco ao abrir e ao retornar de Alt+Tab, teclado ABNT2/US, escala em 100% e HiDPI, janela de 160 × 144 escalada e fechamento pelo botão da janela. O comportamento esperado em perda de foco é ausência de tecla presa.
- Fazer fallback de telemetria no console se título SDL estiver indisponível. Garantir que a cópia headless usada pelo planner nunca mude o foco ou o título da janela real. Testar alcance do quit durante inferência, watchdog e movimentos.
- Separar volume físico de emulação de áudio. Usar `--mute` para silenciar durante testes e manter a semântica de frames que as cenas exigem. Para headless, certificar execução sem dispositivo de som e sem DISPLAY/Wayland. Driver dummy de SDL pode ser usado como parte de um teste documentado e restrito ao processo.
- Teste com Xvfb ou driver virtual garante criação básica e fechamento. Aceitação de interação e som exige Windows desktop e Ubuntu desktop real ou VM com suporte a esses recursos.

## 8. Modelo offline e resultados

1. Introduzir um comando de preparação do modelo que recebe explicitamente a rede, baixa o snapshot do encoder `convaiinnovations/laya` na revisão `fd4f9dbcf4fde222fd43174bdd4c3b08b789e4e1`, registra arquivos, revisão e integridade e faz uma inferência curta. Fixar perfis CPU e evitar que o default do pacote passe a escolher outro backend na instalação. [Projeto Laya](https://github.com/NandhaKishorM/laya) · [Snapshot do modelo](https://huggingface.co/convaiinnovations/laya/tree/fd4f9dbcf4fde222fd43174bdd4c3b08b789e4e1)
2. A execução padrão do Laya usa o snapshot local. Usar `HF_HUB_OFFLINE=1` **antes da importação** ou carregamento explícito por diretório local em modo offline. Cache parcial gera erro com instrução de preparação, sem download implícito durante uma partida. A prova offline executa com rede desabilitada e um cache previamente provisionado. Um segundo teste usa cache vazio e espera erro controlado. [Cache e variáveis do Hugging Face Hub](https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables)
3. Testar cache padrão e customizado no Windows, inclusive usuário sem privilégios para criar symlinks. Medir espaço ocupado nessa condição. Documentar como remover somente o snapshot do projeto, preservando caches de outros modelos. [Limitações do cache do Hub](https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache#limitations)
4. Desabilitar `mps` fora de máquinas que exponham esse backend. Em Windows/Linux, CPU é o critério de entrega. Registrar versões realmente instaladas, dispositivo, revisão, latência e RAM de pico por plataforma. Considerar arquivos de configuração, pesos, tokenizer e encoder necessários ao snapshot. Uma preparação bem-sucedida é o download completo mais a inferência de prova com aqueles arquivos.
5. Separar instalação e resultado da política. O teste de integração passa quando o Laya offline processa o contexto, devolve uma decisão candidata válida e o executor a aplica dentro do orçamento. Sucesso do episódio, mudança de escolha entre plataformas e performance são resultados a reportar. Não usar o sucesso do modelo como substituto do teste determinístico de replay.

### 8.1 LLM supervisor local e opcional

Testar primeiro um modelo *instruct* quantizado de **1 a 3 bilhões de parâmetros**, com inferência em CPU. Essa faixa é um ponto de partida para o experimento. Escolher o checkpoint e o runtime após medir memória, latência e qualidade no Windows, no Linux e no macOS. O supervisor tem perfil de instalação e cache próprios. Ele usa pesos locais e pode ser desligado por parâmetro ou configuração. A portabilidade do runtime base e do Laya é certificada independentemente desta opção.

**Divisão de responsabilidades.** O Laya continua no caminho rápido da decisão. O planner e o executor verificam caminhos, limites de frames e ações legais. O supervisor trabalha no nível de subobjetivos: pode priorizar uma saída conhecida, sugerir conversar com um NPC observado, propor usar um item equipado quando o adapter oferecer essa opção ou recomendar uma sondagem já disponível. Inicialmente, ele ajuda a escolher entre opções que o código já sabe executar. O conjunto de capacidades cresce conforme o adapter aprende novas mecânicas.

**Quando chamar.** Acionar em impasses que o jogo confirma, como dois movimentos bloqueados seguidos com recuperação esgotada, retorno repetido ao mesmo estado sem progresso ou fim de um plano sem atingir seu predicado. Considerar mudança de sala, aquisição de item, avanço de diálogo e mudança de terreno como sinais de progresso. Excluir do contador a espera planejada em animações, transições e cutscenes. Após uma consulta, exigir progresso ou aguardar uma janela de ações antes de consultar novamente. Como valores iniciais de teste, usar até duas consultas por impasse, 20 segundos por consulta e intervalo de seis ações executadas. A emulação permanece estável na decisão, com fechamento da janela responsivo.

**Contexto mínimo.** Enviar objetivo ativo, modo, sala, XY, direção, opções verificadas de movimento, saídas conhecidas, itens equipados, interações visíveis, resumo das últimas ações com seus efeitos e predicado pendente. Dados ausentes aparecem como desconhecidos. O contexto resulta do estado do próprio jogo e é limitado por tamanho. Captura visual, transcrição de diálogo e guias externos podem ser experimentos separados.

**Contrato da resposta.** O supervisor devolve um objeto JSON com `option_id` pertencente à lista fornecida e um `reason` curto e opcional para o log. A lista de opções inclui `abstain`. O controlador valida schema, existência da opção, modo, pré-condições e orçamento. Todo input continua passando pelo executor. Resposta inválida, timeout, falta de pesos ou abstenção usam a recuperação existente e, se ela também se esgotar, registram o impasse preservando o último checkpoint válido. O supervisor não escreve na memória do jogo, no save ou no shell.

**Avaliação.** Comparar três condições com os mesmos checkpoints e orçamento de ações/frames: Laya, Laya com recuperação, Laya com recuperação e supervisor. Incluir a parede já reproduzida, um ciclo com deslocamento e um progresso de campanha que exija escolher entre navegação e interação. Manter um cenário que já funciona para verificar regressão. Registrar sucesso, marcos novos, estados revisitados, bloqueios, chamadas, respostas rejeitadas, latência adicional e pico de RAM. Separar casos usados para ajustar prompts dos usados para avaliar generalização. Promover o supervisor só se a comparação mostrar ganho em impasses com custo aceitável nos alvos. Considerar um modelo maior apenas se o pequeno ficar aquém nos testes que o supervisor foi projetado para resolver.

### 8.2 Evolução da campanha até os créditos

**Meta de produto.** Completar Oracle of Ages US em uma partida nova e não vinculada, desde um slot vazio até os créditos, com o Laya como seletor de decisões de campanha e o LLM supervisor pequeno como ajuda opcional em impasses. A execução pode retomar checkpoints produzidos pela própria partida. O agente opera pelos controles normais. Uso de save avançado, escrita em WRAM, alteração da ROM ou correção manual de uma decisão fica fora da execução que comprova a conclusão.

**Ponto de partida.** O último marco validado é `19-bloco-maku` na sala `04:0a`. O runner atual retoma checkpoints e combina objetivos escritos à mão, busca em cópia headless e Laya em diálogos. O benchmark mostrou que a checagem de paredes evita colisões, mas por si só não faz o modelo encontrar a saída. O próximo marco é avançar pelo Maku Path do passado, resolver o primeiro combate obrigatório e demonstrar progresso em direção à primeira dungeon. [Registro de validação](validation-adapter.md)

| Frente | Melhorias no projeto atual | Verificação |
| --- | --- | --- |
| Percepção e memória | Ampliar sala para era, saídas confirmadas, portas, obstáculos, inimigos, HP, inventário/equipamento, flags relevantes e opções de diálogo. Guardar grafo de salas visitadas e efeito das ações. Versionar o schema e representar valores desconhecidos. | Fixtures distinguem parede, saída, porta trancada e transição. Um ciclo com deslocamento é reconhecido sem confundir uma cutscene com um impasse. |
| Controle e habilidades | Generalizar movimento, empurrar blocos, interação, equipar e usar itens, combate e ações que combinam direção e botão. Cada habilidade recebe pré-condições, orçamento de frames, verificador de resultado e motivo de falha. Testar candidatos prometedores no emulador sombra e aplicar apenas inputs na partida principal. | Abrir uma passagem com item, resolver um bloco e vencer um encontro obrigatório com logs de saúde, ações e resultado. |
| Decisão do Laya | Oferecer subobjetivos e habilidades legais à escolha, com efeitos imediatos, requisitos e memória recente em contexto compacto. O planner traduz a escolha em ações. Replanejar por mudança de estado ou falha de habilidade. | Comparar escolhas do Laya com script e heurística sob os mesmos orçamentos. Registrar sempre a origem da ação, inclusive escolha única, fallback e supervisor. |
| Progresso e recuperação | Trocar a sequência linear de marcos por objetivos com pré-requisitos e predicados independentes. Fazer checkpoints nos marcos. Após morte ou impasse, tentar recuperação limitada a partir de checkpoint próprio, com histórico para evitar tentar infinitamente o mesmo plano. | Interromper, reiniciar e retomar com inventário e objetivos coerentes. Uma tentativa esgotada preserva evidência de onde parou. |
| Cobertura da campanha | Manter um manifesto de segmentos obrigatórios, requisitos de item e de era, salas/puzzles, chefes e essências. Usar marcos escritos à mão para orientar a tarefa, com execução verificável. Scripts de referência servem para diagnóstico e comparação. | Cada segmento comprova entrada, conclusão e saída. A execução integrada liga os segmentos sem preparar os saves manualmente. |

**Marcos de entrega**

1. **Introdução reproduzível** — criar o slot e chegar aos primeiros checkpoints pelos controles desde boot. Reproduzir os marcos existentes e completar Maku Path no passado.
2. **Primeira dungeon ponta a ponta** — demonstrar requisitos de acesso, navegação, combate, chaves e puzzle, derrotar o chefe e confirmar a primeira Essência de Tempo. Exigir dois replays a partir de checkpoints de entrada preservados.
3. **Cobertura das oito essências** — acrescentar segmentos por dungeon e progressão entre elas. Ao final de cada segmento, validar essência e inventário relevante e rodar regressão dos segmentos já automatizados.
4. **Final e créditos** — verificar pré-requisitos do final, vencer Veran na partida não vinculada e observar a sequência de créditos. Depois rodar uma partida contínua desde slot vazio com retomadas exclusivamente de checkpoints gerados durante a execução.

**Definição de pronto.** Guardar o trace de uma partida do início aos créditos, com ROM e versões, timeline de objetivos, oito essências verificadas, resultado final do jogo, evidência dos créditos e contagem de mortes, retomadas, falhas e intervenções. Para declarar **Laya zerou com supervisão**, publicar também a contribuição de cada política e as métricas do supervisor. Para declarar **Laya zerou sem supervisor**, exigir uma execução comprovada com ele desligado. Comparar as duas condições quando viáveis. Uma passagem concluída pelo script de referência conta como teste de controle, e a atribuição ao Laya exige que suas escolhas tenham sido usadas na execução de aceite. O progresso da campanha e a portabilidade são eixos independentes. Uma vez comprovada a conclusão em uma plataforma, validar replay dos marcos difíceis e depois a execução inteira em cada alvo que for anunciar suporte à campanha completa. [Disassembly fixado e referência dos estados do jogo](https://github.com/Stewmath/oracles-disasm/tree/21c924afdc8a13225e849214479d5113da2ec226)

## 9. Plano de implementação

| Etapa | Entrega | Dependências | Gate |
| --- | --- | --- | --- |
| P0 · Prova | Confirmar wheels CPU/base, backend SDL, runtime CPython e toolchains nos dois alvos. Guardar saída de diagnóstico e escolher variante de build Windows. | Runners e desktops/VMs | Instalação limpa e importação; build WLA-DX e descoberta de executáveis corretos. |
| P1 · Runtime | Central de paths, launchers, mensagens por plataforma, smoke sem GUI, armazenamento e migração. | P0 base | `play` e `smoke` com ROM externa em ambos os alvos; operações de arquivo passam nos casos de falha. |
| P2 · Build | Build Linux e Windows, staging, locks de cache, símbolos e manifesto. | P0 toolchain | Hash oficial de projeto em build frio e quente de cada alvo; Windows com path contendo espaço e Unicode. |
| P3 · Agente | Extra CPU, preparação offline, seed de cenários, `--watch`, campanha e documentação de retomada. | P1, locks CPU | Script nos três cenários, Choice offline e campanha no último marco da base portátil. |
| P3b · Supervisor opcional | Contrato de subobjetivos, backend local pequeno, fallback e comparação isolada. | P3, fixtures de impasse | A12 e A13, sem dependência para a certificação base. |
| P4 · Integração | CI, walkthrough de aceitação desktop e README com matriz suportada. | P1–P3 | Evidência dos gates abaixo, regressão macOS e instalação por outra pessoa a partir da documentação. |

Organizar os PRs por P1/P2/P3/P4, com review de portabilidade, commits pequenos e sem binários. A primeira entrega utilizável é P1 com ROM externa. Pode ser divulgada como suporte do emulador enquanto P2 e P3 são certificados separadamente. Alterações de ABI do PyBoy, revisão do modelo ou versão do ROM build exigem nova execução da matriz.

## 10. Matriz e critérios de aceitação

| ID | Teste e entrada | Evidência esperada |
| --- | --- | --- |
| A01 | Clone limpo em Windows 11 x64 e Ubuntu 24.04 x86-64, diretório com espaço e Unicode. Instalar perfil base sem Laya. | Venv correta, `pip check` passa, help dos entry points, sem resolução local inesperada por sdist. |
| A02 | Tentar caminho de ROM ausente, arquivo com hash inválido, ROM válida só leitura e caminho relativo. | Erros com causa e recuperação. ROM e saves intactos após erro. Smoke e play funcionam com ROM válida sem gravar ao lado dela. |
| A03 | Construir ROM nos dois alvos e no macOS, repetir com cache, interromper um build e retomar. | Tamanho e SHA‑1 exatos, símbolos legíveis, manifesto coerente, cache reutilizado e ROM válida anterior preservada. |
| A04 | Smoke na mesma plataforma com 600 frames de boot e 64 de replay. | `replay_state_equal` e `replay_pixels_equal` verdadeiros, tela 160 × 144 com pixels não pretos e saída em JSON. |
| A05 | Exercitar focar, mover Link, controles A/B, pausar, gravar, mover, restaurar e fechar. | Evidência manual em cada desktop, save de 8 KiB persiste e restaura sem input preso; áudio/mute e título ou fallback conferidos. |
| A06 | Importar SRAM legado, restaurar checkpoint incompatível de propósito, simular lock e interrupção entre gravações. | Nenhum overwrite de origem ou perda do último estado válido. Segundo escritor recebe diagnóstico. Erro de checkpoint preserva arquivo e perfil. |
| A07 | Gerar os três cenários a partir de seed validado, rodar script duas vezes e comparar estado/pixels ou resultados de replay na mesma plataforma. | Script completa saída, aproximação e avanço de diálogo. Checkpoints e relatórios são vinculados à ROM. O perfil humano mantém o mesmo hash. |
| A08 | Preparar Laya CPU, desativar rede, rodar benchmark e repetir sem cache. | Decisões válidas e rastreáveis com cache. Diagnóstico claro sem cache. Nenhuma dependência do serviço de inferência remoto. |
| A09 | Rodar `--watch` e campanha local no alvo e fechar com Esc; retomar campanha em diretório de sessão separado. | Frame visível, estados e ações no título ou terminal, replay do benchmark e avanço ao marco publicado e verificável da base, com reabertura pelo último checkpoint. |
| A10 | Exportar SRAM e savestate da origem macOS e testar importação em cada alvo, testar também Windows ↔ Linux. | Relatório por par com hash de SRAM, versão do PyBoy, restauração e comparação lógica. Registrar pares que exigem criação de novo checkpoint. |
| A11 | Executar novamente o conjunto no macOS arm64, incluindo `Jogar.command`. | Instalação, play, smoke e retomada continuam disponíveis. |
| A12 | Ativar supervisor offline em impasse conhecido e em cena que já avança. | Chamada só no impasse, opção válida executada sem saltar o planner, métricas comparadas com o supervisor desligado. |
| A13 | Simular timeout, JSON inválido, opção inexistente, abstenção e ausência de pesos. | Recuperação limitada aciona, nenhum input inválido é executado, janela segue fechável e último checkpoint válido pode ser retomado. |

### Formato de evidência

Para cada run de aceitação, guardar commit do projeto, ID do teste, sistema e arquitetura, versão do Python, PyBoy e SDL carregado, hash da ROM, perfil de instalação, data e resultado. Registrar exit code e erro reduzido quando falhar. Para replay, incluir hashes do seed original e do estado final e os indicadores de igualdade. Para campanha, incluir sala, marco atingido e inventário relevante. Para inferência, incluir revisão, dispositivo e contagem de decisões válidas. Usar paths relativos ou redigidos e excluir bytes de saves, ROM, snapshots de modelo, tokens e nomes pessoais.

### Estratégia de CI

- **PR obrigatório e rápido** em Windows e Ubuntu. Instalação base, compileall, ajuda, testes de paths, parsing, validação de hash com dados sintéticos, erros previstos, escrita atômica e restrição de perfis de concorrência. Rodar job de regressão macOS na frequência acordada.
- **Integração headless** em runners dos três alvos. Separar provisão da ROM do código da suíte. Em ambientes autorizados, usar ROM de SHA‑1 esperado provisionada localmente ou gerada no runner e executar smoke e cenários. Usar inputs conhecidos e limitar timeouts. Nenhuma pipeline deve usar save ou token pessoal.
- **Build frio e quente** em execução manual/release e depois promover ao CI regular se o custo permitir. Cachear toolchain por alvo e revisão. Registrar o resultado da validação por alvo, ainda que a distribuição dos binários continue restrita à máquina de teste.
- **Offline** em execução manual/release. Provisionar os pesos numa etapa online separada, depois isolar a rede e executar um episódio curto. No Windows, caminho/cache e distribuição SDL reais precisam de verificação nativa.
- **Desktop** via checklist manual ou automação local de UI no release. Registrar sistema, sessão Wayland/X11 ou Windows, driver SDL, escala, método de áudio e resultado por ação. O pipeline virtual serve como verificação complementar. [Runners do GitHub Actions](https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners)

## 11. Riscos, decisões em aberto e saída de entrega

| Decisão / risco | Como fechar | Consequência se falhar |
| --- | --- | --- |
| Makefile e quoting no Windows | Provar com UCRT64 em path real e produzir o SHA‑1 acordado. | Entregar P1 com ROM externa. Investigar correção pequena no wrapper ou build WSL2 e reabrir o gate P2. |
| SDL wheel/DLL, som e foco | Identificar a biblioteca efetivamente carregada e executar checklist nos desktops. | Certificar headless separadamente. Manter suporte gráfico pendente para o alvo ou backend afetado. |
| Transitive deps e wheel CPU | Resolver os perfis antes de implementar a distribuição e verificar a versão escolhida em cada plataforma. | Base continua utilizável. Publicar o status do perfil Laya como pendente até resolver a incompatibilidade. |
| Seed compartilhável para campanha | Definir se será produzido a partir de inputs de boot ou criado por um walkthrough manual validado. Registrar posição e hash da ROM. | Campanha precisa de checkpoint válido local. Smoke e jogo humano seguem disponíveis. |
| Cross-platform de savestate | Validar pares de exportação/importação, formato e estado lógico. | Documentar quais pares estão comprovados. Preservar importação de SRAM e criação de novos checkpoints. |
| Tempo e memória do planner | Medir pelo menos uma execução da campanha com logs de duração por marco e pico de RAM. | Definir limites a partir da medição. Usar retomada por checkpoint quando excedidos e registrar o marco afetado. |
| Supervisor consome CPU/RAM ou repete estratégias | Medir com o perfil CPU nos três alvos e comparar checkpoints reservados. | Manter opt-in, reduzir o contexto ou o orçamento e só testar modelo maior se a falha for de decisão. |
| Canal de distribuição | Começar com clone + venv + launchers, usando fontes e logs públicos. Avaliar builds empacotados e assinatura depois da primeira matriz verde. | A entrega fonte continua funcional via comandos documentados. |

A entrega de suporte inclui comandos do zero por plataforma, toolchains ou rota alternativa certificada, localização de dados e procedimento de importação, logs sanitizados dos testes e uma tabela pública com a versão e modos comprovados. A validação do desempenho ou da qualidade do Laya permanece nos relatórios de experimento. A aprovação final exige que cada sistema satisfaça os gates que aparecem como suportados no README.
