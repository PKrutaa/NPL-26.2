# Validação do agente autônomo e do supervisor

Executada em 20 de novembro de 2026, no macOS arm64 (Apple M3 Pro), com Python 3.12.13, PyBoy 2.8.1, Laya 0.5.0 em CPU e PyTorch 2.15.0. O Laya usou `convaiinnovations/laya` na revisão `fd4f9dbcf4fde222fd43174bdd4c3b08b789e4e1`, carregado em modo offline. A ROM foi gerada pelo `scripts/build_rom.py` e tem o SHA-1 esperado.

## Ponto de partida

O comando `seed` joga do boot até `00:8a`, XY `124,56`, só com inputs de controle. Duas execuções geraram o mesmo arquivo. Todo o resto parte desse seed. Nenhum checkpoint manual foi usado.

Com esse seed, o Laya sozinho no cenário de saída repetiu o resultado já documentado: escolheu direita 12 vezes contra a parede e não saiu. A probabilidade da opção escolhida foi 0,31, com as outras cinco entre 0,09 e 0,21.

A campanha com rotas escritas à mão (`zelda_env.campaign --script-dialogue`) parou no marco `06-nayru` a partir desse seed. Ela não achou o quinto personagem na coordenada fixa `88,56`. Os marcos `01` a `05` foram reproduzidos.

## Como o agente evita loops

| Mecanismo | O que faz |
| --- | --- |
| Levantamento por simulação | Lista só o que o emulador confirmou ser possível na sala. O Laya não escolhe direções. |
| Memória por área e por estado da história | Uma opção já tentada sai da lista de candidatas. |
| Identidade pelo resultado | Uma conversa é identificada pelo texto que o personagem diria agora. Fala nova é opção nova. |
| Áreas separadas | Uma sala com partes sem ligação vira mais de uma área, identificada pelas saídas. |
| Viagem até a fronteira | Sem nada novo na sala, o agente segue o caminho conhecido mais curto até uma área com opções. |
| Parada declarada | Sem nada novo em lugar nenhum, o agente registra `impasse` e para depois de seis tentativas em rodízio. |

Um teste unitário explora 30 mundos aleatórios de 12 salas só com essas regras. Em todos a exploração termina, conversa com cada personagem uma vez e usa menos de 200 passos.

Três regras do jogo exigiram ajuste no levantamento:

- **Fala que depende de estado oculto.** O urso da clareira só libera o caminho quando é o último a ser ouvido. Por isso a conversa é identificada pelo resultado.
- **Cena com atraso.** Ao entrar na zona de Impa, o jogo trava os controles e abre o diálogo cerca de um segundo depois. O levantamento testa ficar parado uma vez por região da tela e sempre que os controles param de responder.
- **Cena que esconde a sala.** Durante algumas cenas a leitura da sala fica indisponível. O levantamento espera a sala voltar antes de classificar o resultado.

## Supervisor em casos isolados

Dois modelos foram medidos no Ollama 0.30.10 local, em três casos com resposta conhecida, duas repetições cada. O Ollama usou a GPU do Mac. Não há medição em CPU.

| Modelo | Acertos | Latência por consulta | Memória carregada |
| --- | --- | --- | --- |
| `qwen2.5:1.5b` | 3 de 3 | 0,42 a 0,50 s | 2,1 GB |
| `llama3.2:1b` | 1 de 3 | 0,40 a 0,63 s | 2,6 GB |

A primeira consulta depois de carregar o modelo levou 2,4 s no `qwen2.5:1.5b` e 13,6 s no `llama3.2:1b`. Os três casos foram escritos para esta medição e são poucos. Eles serviram para escolher o modelo padrão, não para medir generalização.

Os casos de falha do contrato rodam nos testes unitários com um backend falso: timeout, JSON inválido, schema inválido, opção inexistente, abstenção e pesos ausentes. Em todos o supervisor devolve nenhuma opção e o agente segue com a recuperação própria.

## Execução a partir do boot

Comando: `python -m zelda_env.agent --headless --fresh --decisions 150`, sem supervisor. A sessão partiu do seed do boot e parou no orçamento de decisões.

| Medida | Valor |
| --- | --- |
| Decisões | 150 |
| Objetivos concluídos | `espada` na decisão 29, `maku-tree` na 96, `passado` na 98 |
| Salas visitadas | 56 |
| Sala final | `01:86`, no passado, junto da Black Tower |
| Origem das decisões | Laya 113, forçada 25, viagem até a fronteira 12, fallback 0 |
| Resultado das decisões | 90 mudaram de sala, 9 avançaram a história, 51 sem novidade |
| Maior repetição de uma opção no mesmo estado da história | 2 |
| Mortes ou retomadas | 0 |
| Essências | 0 |
| Tempo total | 1.524 s, cerca de 10 s por decisão |
| Levantamento por decisão | 9,3 s em média |
| Escolha do Laya | 281 ms em média, nenhum contexto truncado |

As 12 opções com duas tentativas são as viagens até a fronteira, que repetem uma saída já conhecida para chegar a uma área com opções. Nenhuma conversa, empurrão ou evento foi repetido.

No caminho o agente encontrou Impa, empurrou a pedra, falou com os cinco ouvintes da clareira e voltou ao urso depois dos outros, recebeu a espada, cortou o arbusto no caminho para Lynna City, atravessou o Maku Path, falou com a Maku Tree e entrou no portal para o passado. A campanha escrita à mão registra esses pontos como os marcos 01 a 12.

O que esta execução não mostra:

- É uma execução única. Não há repetição com outras condições iniciais.
- As 25 decisões forçadas e as 12 viagens não são escolhas do Laya. O Laya escolheu em 113 de 150.
- Em Lynna City o Laya foi para o sul com o objetivo dizendo norte. A memória evitou a repetição, e a exploração chegou ao norte depois.
- Não houve combate. O agente ainda não chegou à primeira dungeon.

## Supervisor no jogo

Uma sessão de 60 decisões rodou com `--supervisor qwen2.5:1.5b --stall 3`, para forçar consultas. Ela concluiu `espada` e visitou 23 salas.

| Medida | Valor |
| --- | --- |
| Consultas | 4 |
| Aceitas | 0 |
| Abstenções | 4 |
| Bloqueadas pelo orçamento | 38 |
| Tempo somado das consultas | 3,4 s |

O supervisor absteve nas quatro consultas, inclusive em duas com uma saída na direção do objetivo. O agente seguiu com a escolha do Laya em todas. O prompt foi reescrito depois disso. Em três desses contextos reais, o prompt novo escolheu uma opção em dois e absteve em um. Esses contextos passaram a ser casos de ajuste de prompt. O prompt novo ainda não foi avaliado em uma sessão completa.

Com isso, o supervisor está integrado e seguro, mas ainda não há evidência de que ele melhora o resultado.

## Segunda rodada: comparação, contexto curto, luta e itens

As medições abaixo são do mesmo dia e da mesma máquina, depois da execução de 150 decisões descrita acima.

### Comparação com outras políticas

Mesmo seed, mesmo orçamento de 150 decisões e as mesmas opções candidatas. Só muda quem escolhe entre as opções novas. Uma execução de cada.

| Política | Objetivos | Como terminou |
| --- | --- | --- |
| Laya, contexto longo | `espada` na 29, `maku-tree` na 96, `passado` na 98 | Orçamento esgotado, 56 salas |
| `shortest`, a opção de rota mais curta | `espada` na 22 | Impasse na decisão 83, 13 salas |
| `random`, semente 0 | `espada` na 55 | Impasse na decisão 110, 13 salas |

As duas políticas de comparação pararam na floresta. O Laya saiu dela. Com uma execução de cada, isso é um indício e não uma prova: a diferença pode vir da ordem em que as salas foram visitadas.

### Contexto curto para o Laya

Foram reunidas as 23 decisões da execução acima em que havia uma saída na direção citada pelo objetivo e outra em direção diferente. A pergunta foi qual saída cada modelo escolhe.

| Quem escolhe e com qual contexto | Escolheu a saída na direção do objetivo |
| --- | --- |
| Acaso | 6,5 de 23, esperado |
| Laya, contexto longo: objetivo em frase, sala, posição e histórico | 9 de 23 |
| Laya, contexto longo com "leva para perto" e "leva para longe" nas opções | 9 de 23 |
| `qwen2.5:1.5b`, contexto longo | 10 de 23, com 8 abstenções |
| Laya, objetivo `Go north.` e opções `Go north`, `Go south` | 23 de 23, confiança média 0,87 |

Com isso o agente passou a enviar ao Laya só um objetivo curto e opções curtas. Em 13 casos escritos à mão com objetivos de outros tipos (`Go to a new room.`, `Talk to the character.`, `Attack the enemy.`, `Use the item on the ground.`), o Laya escolheu a opção esperada nos 11 que tinham resposta certa. Esses casos serviram para desenhar o texto e não medem generalização.

### Execução do boot com contexto curto e objetivos em etapas

| Objetivo | Decisão em que foi concluído | Antes, com contexto longo |
| --- | --- | --- |
| `espada` | 21 | 29 |
| `maku-tree` | 34 | 96 |
| `passado` | 36 | 98 |
| `pa`, a pá na Black Tower | 120 | não alcançado em 150 |

Depois da pá, na mesma execução, o agente foi até o portão do Maku Path, cavou os montes de terra, entrou e venceu as lutas das duas primeiras salas. Ele parou na sala dos blocos, com a versão do código anterior às correções de empurrar descritas abaixo. O levantamento por decisão ficou entre 3 e 5 segundos.

### Capacidades verificadas em estados de teste

Os estados de teste abaixo foram produzidos pela campanha escrita à mão a partir do checkpoint do agente no passado. Em cada um, o levantamento e a execução usaram só as opções genéricas. Nenhuma rota foi escrita.

| Situação | Resultado |
| --- | --- |
| Três morcegos na primeira sala do Maku Path do passado | Três lutas vencidas sem perder vida, uma por decisão. |
| Três inimigos na sala seguinte | Vencidos sem perder vida. A porta norte abre depois da última luta e o agente a encontra. |
| Portão do Maku Path com montes de terra | A pá abre os montes um a um e a entrada aparece. |
| Sala com três blocos sobre buracos | As três empurradas saem na ordem certa, o baú aparece e a chave pequena é obtida. Funciona também com Link começando desalinhado. |
| Pá guardada no inventário em vez de equipada | A opção de cavar continua disponível. A rota abre o menu, equipa com botões reais e cava. |
| Inimigo atrás de obstáculo, sem caminho | Nenhuma luta é oferecida. |

Na sala do Octorok (`00:64`), o estado de teste foi montado movendo Link por escrita em memória. Esse estado serviu só para desenvolver a luta e não entra em nenhuma execução do agente.

### Vida

Nas primeiras execuções Link terminava com meio coração de três, sem nenhuma morte registrada. A causa era o teste de empurrar, que segura a direção por 60 frames e podia jogar Link num buraco ou na água. Os testes de interagir, empurrar e esperar passaram a conferir a vida, inclusive o dano que chega com atraso. Depois disso, uma sessão de 70 decisões no mesmo trecho terminou com a vida cheia. Cada decisão agora registra a vida.

### CI

O workflow rodou no GitHub nos três sistemas e passou: instalação do perfil base, compilação, ajuda de todas as CLIs, testes unitários e a checagem de erro com ROM ausente. Isso cobre Windows e Ubuntu só nesses pontos. ROM, janela, save e Laya não foram executados nessas plataformas.

## Terceira rodada: sessão contínua até a Maku Tree salva

Uma única sessão, iniciada no boot e retomada várias vezes do próprio estado salvo, concluiu cinco objetivos: `espada`, `maku-tree`, `passado`, `pa` e `maku-tree-salva`. O último exige atravessar o Maku Path do passado inteiro.

| Trecho do Maku Path do passado | O que o agente fez |
| --- | --- |
| Portão em `01:48` | Cavou os montes de terra com a pá e entrou. |
| `04:0c` | Empurrou o bloco que fecha a passagem. |
| `04:0a` | Saiu do cercado de blocos e venceu três morcegos. |
| `04:0b` | Venceu três inimigos. A porta norte abre depois da última luta. |
| `04:08` | Empurrou três blocos sobre buracos, abriu o baú e pegou a chave pequena. |
| `04:0a`, porta oeste | Abriu a porta trancada com a chave. |
| `04:09` | Empurrou cinco blocos e subiu a escada para a sala lateral `06:05`, onde pegou um item. |
| `04:06` e `04:07` | Venceu dois inimigos e tomou a saída para `01:38`. |
| `01:38` | Venceu os dois inimigos que atacavam a Maku Tree. A flag do jogo de árvore salva ficou ligada. |

Link terminou com 3 de 3 corações.

Esta sessão não serve como medida de custo nem como prova de ausência de ciclos. Ela somou 1.497 decisões porque o código foi corrigido ao longo dela, e várias centenas de decisões foram gastas em ciclos que as correções depois eliminaram. Os ciclos observados e o que os resolveu:

| Ciclo observado | Causa | Correção |
| --- | --- | --- |
| Vai e volta entre `04:0d` e `04:0c` empurrando o mesmo bloco | A saída para fora da dungeon contava como pendência na sala da entrada e atraía viagens de volta. | A saída não conta como pendência dentro da dungeon do objetivo. Detector de ciclo curto. |
| Refazer as onze empurradas de `04:09` a cada visita | Regra que tornava novas todas as ações de uma sala revisitada. | Regra removida. Receitas de travessia. Detector de ciclo longo. |
| Vai e volta de varredura entre as duas salas da entrada | A varredura só considerava salas com registro de última visita. | A varredura considera todas as salas conhecidas. |
| "Sem opções" em `04:09` com empurradas disponíveis | Cache de área examinada pulava a camada do levantamento que encontra empurrões. | Cada cache vale só para a própria camada e é descartado ao carregar a sessão. |
| Saída para a Maku Tree nunca tomada | Regra que proibia sair da dungeon do objetivo. | A regra barra só saídas para salas já visitadas. |

Uma execução do boot com o código final, sem correções no meio, é necessária para medir decisões por objetivo e contar ciclos. A seção seguinte descreve essas execuções.

## Quarta rodada: execuções limpas desde o boot

Cada execução parte de `output/inicio.state`, com memória vazia (`--fresh`), sem janela e sem supervisor. Nenhum código muda durante a execução. Quando uma execução para ou corta um ciclo, a causa é corrigida e a execução seguinte recomeça do boot.

Comando:

```
python -m zelda_env.agent --headless --fresh --decisions 900 --directory output/agent-limpa
```

A métrica de ciclo é o maior trecho de decisões seguidas formado por no máximo quatro movimentos distintos, além dos eventos `loop_cut` e `impasse` do rastro.

| Execução | Resultado | Causa | Correção |
| --- | --- | --- | --- |
| 1 | Impasse na decisão 143, na floresta. | Duas passagens para a mesma sala vizinha contavam como uma saída. | A saída de borda leva no nome o trecho onde Link pousa do outro lado. |
| 2 | 2 objetivos. Cerca de 200 idas e voltas entre `00:39` e `00:49`, 42 cortes de ciclo. | A rota conhecida levava à parte da sala do marco que não tem o evento. | Uma entrada ainda não usada para a sala do marco vem antes da rota conhecida. A parte da sala onde nada resta deixa de ser destino. |
| 3 | 21 conversas seguidas com o mesmo personagem, 3 cortes em 40 decisões. | Refazer a tarefa do marco reoferecia a mesma conversa sem limite. | Três repetições por ação ao refazer a tarefa. |
| 4 | 1 objetivo. Impasse na decisão 290. | Dez cortes de arbusto ao acaso esgotaram o limite de uso do item sem abrir o caminho. | A opção de obstáculo diz o lado da sala em que ele fica quando nenhuma saída aponta para o objetivo. |
| 5 | 3 objetivos em 41 decisões. Impasse na decisão 124. | Depois de ir a uma área pendente, Laya voltava pela saída conhecida. O corte de ciclo apagava todas as pendências. | Após a ida a uma área pendente, só o que falta nela é oferecido. O corte remove só os movimentos do ciclo. |
| 6 | 5 objetivos em 268 decisões. 2 cortes de ciclo na sala `01:48`. | A opção genérica de cavar era reoferecida a cada decisão. | O limite de três repetições vale para qualquer ação. |
| 7 | 5 objetivos em 265 decisões, sem corte de ciclo e sem impasse até ali. Primeiro corte na decisão 377, no sexto objetivo. | O marco do sexto objetivo apontava para a sala errada. A etapa avançava ao entrar de novo na dungeon já percorrida. A lista de doze opções cortava a que o objetivo pedia. | Marco corrigido para a sala do portal. A etapa só avança em mapa novo ou no mapa da etapa seguinte. As opções que o objetivo pede ficam na lista. |
| 8 | 5 objetivos em 262 decisões, sem corte de ciclo e sem impasse até ali. Primeiro corte na decisão 365, no sexto objetivo. | A conversa com a Árvore Maku termina numa pergunta. Confirmar a primeira resposta repete a explicação sem fim, e a opção era descartada. Em `00:7a`, saídas achadas por uma varredura mais detalhada foram registradas como abertas pela última interação, que passou a ser refeita a cada visita. | Uma pergunta que volta recebe a resposta seguinte. Só conta como abertura a saída que surge com mudança de terreno ou depois de uma conversa. |
| 9 | 5 objetivos em 262 decisões, sem corte de ciclo e sem impasse. Encerrada ali para gerar o ponto de partida do trecho da chave do cemitério. | Não se aplica. | Não se aplica. |
| 10 | 8 objetivos em 293 decisões, do boot até entrar na dungeon 1. Nenhum corte de ciclo, nenhum impasse, nenhuma opção descartada e nenhuma morte. | Não se aplica. | Não se aplica. |

Decisões por objetivo na execução 7:

| Objetivo | Decisão |
| --- | --- |
| `espada` | 28 |
| `maku-tree` | 39 |
| `passado` | 41 |
| `pa` | 120 |
| `maku-tree-salva` | 265 |

Até a decisão 265 da execução 7, o maior trecho com no máximo quatro movimentos distintos tem 13 decisões. A origem das 379 decisões da execução: 209 do Laya, 75 forçadas (uma só opção nova), 54 de fronteira, 15 de rota, 12 de varredura, 10 de receita e 4 de rodízio. O levantamento levou em média 15 s por decisão.

### Execução 10: do boot à dungeon 1

A execução 10 rodou com `--until dungeon-1`, a partir do seed do boot, com memória vazia, sem janela e sem supervisor. Parou sozinha ao entrar na dungeon 1, depois de 92 minutos.

| Objetivo | Decisão |
| --- | --- |
| `espada` | 23 |
| `maku-tree` | 34 |
| `passado` | 36 |
| `pa` | 84 |
| `maku-tree-salva` | 206 |
| `sacola-de-sementes` | 219 |
| `chave-do-cemiterio` | 244 |
| `dungeon-1` | 293 |

| Medida | Valor |
| --- | --- |
| Cortes de ciclo | 0 |
| Impasses | 0 |
| Opções descartadas por morte ou perda de controle | 0 |
| Maior trecho com no máximo quatro movimentos distintos | 7 decisões |
| Movimento mais repetido | 4 vezes |
| Origem das decisões | 165 do Laya, 61 forçadas, 31 de rota, 21 de fronteira, 14 de varredura, 1 de rodízio |
| Tempo médio de levantamento | 18,3 s por decisão |

Esta execução usou o código de um commit antes da última mudança, que só reduz o tempo de espera no teste de obstáculo. Os objetivos seguintes (`essencia-1` em diante) ainda não foram alcançados.

As correções que levaram do quinto ao oitavo objetivo foram feitas no teste por trecho, descrito abaixo.

### Sexto, sétimo e oitavo objetivos no teste por trecho

Os trechos partem do ponto salvo pela execução 9 ao salvar a Árvore Maku, com a memória do agente daquele momento.

| Trecho | Resultado | Decisões | Cortes de ciclo | Impasses | Maior trecho repetitivo |
| --- | --- | --- | --- | --- | --- |
| `sacola-de-sementes` | Passou | 6 | 0 | 0 | 4 |
| `chave-do-cemiterio` | Passou | 64 | 0 | 0 | 6 |
| `dungeon-1` | Concluiu com ciclo na primeira rodada (88 decisões, 1 corte). Passou depois das correções. | 37 | 0 | 0 | 5 |

O que impedia o trecho da chave, na ordem em que apareceu:

| Causa | Correção |
| --- | --- |
| A Árvore Maku solta a Sacola de Sementes depois da conversa, e a Laya ia embora sem pegar. | Novo objetivo `sacola-de-sementes`. |
| O caminho para o cemitério é fechado por um broto que só queima com semente de brasa. O levantamento esperava 20 quadros pelo efeito do item, e a semente leva cerca de um segundo. | O teste de obstáculo espera mais quando o item não mostra efeito na hora, e um bloco sólido deixa de ser tratado como chão livre. |
| Depois de queimar o broto, a etapa não avançava e o agente voltava para `00:6a`. | Uma etapa de conversa ou de obstáculo avança quando a história anda. |
| A sala de referência da chave era `00:7c`. A caverna fica em `00:8d`. | Sala de referência corrigida a partir dos dados de warp do disassembly. |
| Depois de abrir o portão do cemitério com a chave, o agente seguia a rota conhecida e só usava a saída nova 50 decisões depois. | Uma saída que a última ação abriu é tomada antes de qualquer rota conhecida. |
| Abrir o portão mudava o estado da história e apagava a marca de parte esgotada da sala de referência. A rota voltava a apontar para a parte da caverna. | A marca de parte esgotada vale por etapa do objetivo. |
| Com o objetivo em duas direções, o agente nomeava a primeira que tivesse qualquer saída, mesmo já usada. | A direção com saída ainda não usada vem primeiro. |
| Um arbusto que volta a crescer era cortado a cada visita para reabrir um caminho que ninguém ia usar. | Limite de duas repetições por estado da história. |

### Dentro da dungeon 1

O trecho `essencia-1` ainda não passa. O caso `chave-pequena` passa: a partir da sala antes do cubo colorido, o agente resolve o cubo, derrota o Ghini, pega a chave pequena e abre a porta trancada de `04:1d`, em 12 decisões e sem corte de ciclo.

| Mecânica da dungeon 1 | Estado |
| --- | --- |
| Derrotar todos os inimigos para abrir a porta | Funciona |
| Cubo colorido até o encaixe | Funciona |
| Pegar a chave pequena que cai | Funciona. Um item no chão é pego antes de qualquer outra coisa. |
| Porta trancada com chave pequena | Funciona. Andar contra a porta já é uma opção do levantamento. |
| Baú | Visto uma vez no trecho (`04:1a`), sem caso próprio |
| Queimar trepadeira com semente de brasa | Visto uma vez no trecho (`04:1d`), sem caso próprio |
| Sequência de blocos de `04:19` e `04:16` | Não resolve. O agente tenta empurrões ao acaso e a sala volta ao início quando ele sai. |
| Botão de chão, plataforma móvel, mini-chefe, tochas, Power Bracelet, Wallmaster, chefe | Não alcançados |

A lista completa de passos da dungeon está em [research-mecanicas-ages.md](research-mecanicas-ages.md).

## Testes por trecho e por caso

Uma execução desde o boot leva cerca de uma hora até os objetivos mais distantes. Para iterar mais rápido, o agente salva o estado do jogo e a própria memória em dois momentos, e `zelda_env/segments.py` roda a partir desses pontos.

| Teste | Parte de | Vai até | Duração típica |
| --- | --- | --- | --- |
| Trecho | Objetivo anterior concluído (`objetivo-<nome>.state`) | Objetivo seguinte | 3 a 30 minutos |
| Caso | Qualquer ponto salvo, como o `falha-<decisão>.state` | Um objetivo ou uma sala | 1 a 5 minutos |

Quando o agente corta um ciclo ou para em impasse, ele grava `falha-<decisão>.state` e `falha-<decisão>.memory.json` com o estado de até 25 decisões antes. Esse ponto reproduz o problema sem rodar o jogo desde o início.

```
python -m zelda_env.segments list
python -m zelda_env.segments capture output/agent-limpa
python -m zelda_env.segments run chave-do-cemiterio --decisions 150
python -m zelda_env.segments run all --jobs 4
python -m zelda_env.segments case-add ciclo-7a --state output/agent-limpa/falha-340.state --until-room 00:7b --decisions 30 --note "ida e volta em 00:7a"
python -m zelda_env.segments case-run all --jobs 4
python -m zelda_env.segments report
```

- `list` mostra cada trecho, de onde ele parte e se o ponto de partida existe, e os casos guardados.
- `capture` copia para `output/segments` os pontos salvos por uma sessão do agente.
- `run` roda um trecho. Com `all`, roda todos em sequência, cada um partindo do fim do anterior. Com `--jobs`, roda em paralelo os trechos que já têm ponto de partida.
- `case-add` guarda um ponto salvo como caso, com o alvo e o orçamento de decisões. `--no-drops` faz o caso falhar também quando uma opção é descartada por morte ou perda de controle.
- `case-run` roda um caso ou todos.
- `report` mostra o último resultado de cada teste ao lado do anterior, com o commit.
- `inspect` mostra o que o agente vê em um estado salvo: sala, itens, blocos com colisão, objetos e as opções do levantamento. Salva também a imagem da tela.

O agente grava um ponto a cada 10 decisões em `pontos/` dentro da sessão. `case-add --run <sessão> --decision N` cria um caso a partir do último ponto até a decisão N. `run` aceita vários trechos de uma vez, e `--jobs` roda um emulador por núcleo.

Cada execução imprime uma linha JSON com decisões, cortes de ciclo, impasses, opções descartadas, maior trecho repetitivo e tempo. O histórico fica em `output/segments/results.jsonl`.

Um teste passa quando chega ao alvo dentro do orçamento, sem corte de ciclo e sem impasse. O comando sai com código 1 quando algum teste não passa. Ao concluir um trecho pela primeira vez, o ponto final vira a partida do trecho seguinte. `--update` substitui um ponto existente e `--fresh-memory` começa o trecho com a memória vazia.

Fluxo de trabalho:

1. Uma execução longa encontra um ciclo e grava o ponto de reprodução.
2. O ponto vira um caso com `case-add`.
3. A correção é testada no caso, em minutos.
4. `case-run all` e `run all --jobs 4` confirmam que os outros casos e trechos continuam passando.
5. A execução limpa desde o boot dá a evidência final.

Os pontos salvos ficam em `output/`, fora do repositório, porque derivam da ROM.

## Estado em relação à spec

| Item da spec | Estado |
| --- | --- |
| Central de caminhos, `--data-dir`, variáveis de ambiente, pastas nativas | Implementado e testado no macOS. Lógica de Windows e Linux coberta por teste unitário. |
| Gravação atômica do save, lock por perfil, importação de SRAM | Implementado e testado. `play` encerra com Ctrl+C ou SIGTERM e grava o save. |
| Launchers `Jogar.cmd` e `jogar.sh` | Escritos. `jogar.sh` testado no macOS. `Jogar.cmd` não foi executado. |
| Seed a partir do boot com procedência | Implementado e testado. |
| Preparo offline do modelo, erro sem cache, `mps` só onde existe | Implementado e testado. |
| Build da ROM: toolchain resolvida antes, log por etapa, manifesto por último | Implementado. Build quente testado no macOS. Linux não testado. |
| Build da ROM no Windows (MSYS2) | Não implementado. O script informa e orienta a usar `--rom`. |
| Destino do checkpoint Z/X independente da ROM | Não implementado. Continua ao lado da ROM. |
| Locks de dependência por plataforma com hashes | Não implementado. O lock atual é o do macOS. |
| CI em Windows, Ubuntu e macOS | Rodou e passou nos três sistemas, sem ROM e sem janela. |
| Supervisor: contrato, orçamento, fallback | Implementado e testado. |
| Supervisor: comparação das três condições com checkpoints reservados | Não feita. |
| Agente: percepção de inimigos, combate, HP, inventário | Luta de espada, leitura de vida, itens em chão livre e itens guardados via menu implementados e testados nos estados acima. Chefes, projéteis e recuperação de vida não. |
| Critérios A01 a A13 em Windows e Linux | Não executados. |
