# ADR 0002: o Laya aperta um botão por vez e o supervisor escreve a meta

- Estado: aceito
- Data: 2026-11-23

## Contexto

O projeto quer saber até onde dois modelos pequenos, rodando localmente, conseguem jogar The Legend of Zelda: Oracle of Ages sem ajuda.

- O **Laya** é um modelo de ação: recebe um contexto curto e escolhe uma entre poucas alternativas.
- O **supervisor** é um LLM local de cerca de 4 bilhões de parâmetros (`gemma3:4b`, no Ollama).

Para o resultado dizer algo sobre os modelos, a decisão precisa ser deles. Se o código descobre o que dá para fazer em cada sala e entrega a resposta pronta, o que se mede é o código.

## Decisão

O Laya decide no nível do controle e o supervisor decide o que fazer. O código só percebe e executa.

| Papel | O que faz |
| --- | --- |
| Supervisor | Lê o estado do jogo em texto e escreve a meta do momento, em poucas palavras |
| Laya | Lê a meta e escolhe um botão por input: cima, baixo, esquerda, direita, A ou B |
| Código | Lê a memória do jogo, monta o texto, espera enquanto o jogo está no controle e aperta o botão escolhido |

A implementação está em `zelda_env/player.py`.

### O que o supervisor recebe

Só texto, lido da memória do jogo naquele instante:

- o que o objetivo atual pede, em uma frase, sem salas e sem rotas;
- a sala, a posição de Link e para onde ele olha;
- um mapa da tela em caracteres: `@` Link, `#` parede, `.` chão, `o` buraco, `s` escada, `B` bloco, `C` baú, `b` botão, `E` inimigo, `N` personagem ou objeto;
- o que está ao lado de Link em cada direção;
- os lados por onde a tela pode ser deixada;
- a vida;
- os oito últimos inputs e o resultado de cada um;
- quantos inputs seguidos não tiveram efeito;
- as metas que não mudaram nada naquela tela.

Ele devolve uma meta de até doze palavras, que começa por `Walk up`, `Walk down`, `Walk left`, `Walk right`, `Press A` ou `Press B`, e o motivo. Uma meta nova é pedida a cada oito inputs, quando a tela muda e a cada quatro inputs sem efeito.

### Memória do supervisor

Por padrão o supervisor só vê o instante: os oito últimos inputs, a última meta e as metas que não mudaram nada na tela atual. Os acréscimos abaixo existem como opção, desligados porque não melhoraram a medição:

- `--memory`: um diário das seis últimas metas com o que cada uma fez, o mesmo registro guardado por tela (continua lá quando Link sai e volta) e uma nota de até vinte palavras que o supervisor escreve para si mesmo e recebe de volta na chamada seguinte.
- `--texts`: as falas que o jogo mostrou, lidas da tabela de textos do disassembly quando ele está no cache local.
- `--history`: as telas visitadas e por onde Link saiu de cada uma.
- `--reach`: o supervisor diz por quantos inputs a meta vale, de 1 a 8, em vez de oito fixos.
- `--guide`: um parágrafo de guia sobre o objetivo atual, que o supervisor pode seguir ou não. Só o trecho `espada` tem guia escrito.
- `--followers`: o personagem que continua ao lado de Link depois de ele andar três vezes aparece no mapa como `f`.
- `--walk-to`: o supervisor escolhe uma casa do mapa e o que fazer ao chegar (parar, apertar A ou B, sair por um lado). O código calcula o caminho sobre o mapa em caracteres e dá ao Laya a direção do próximo passo. É a única opção em que o código decide a direção, por isso fica fora do padrão.
- `--repeats`: quantas vezes o último texto do jogo foi mostrado.
- `--paths`: os lados da tela a que dá para chegar andando de onde Link está, por um preenchimento sobre o mapa em caracteres.

### O que o Laya recebe

A meta do supervisor, para onde Link olha e o que está ao lado dele. Com isso escolhe um dos seis botões. Durante um texto do jogo, as escolhas são A e B.

### O que o código não faz

- Não simula nada à frente.
- Não lista ações possíveis.
- Não resolve salas de blocos nem lutas.
- Não guarda o que já foi tentado e não corta ciclos.
- Não desfaz decisões: se Link morre, o jogo segue como seguiria para uma pessoa.

### Linha de base

`zelda_env/agent.py` é a linha de base de comparação. Nela o código simula cada sala em uma cópia do emulador, lista o que dá para fazer e o Laya escolhe entre opções prontas. Ela mostra até onde se chega quando o código faz a maior parte do trabalho, e está descrita no [ADR 0001](0001-agente-por-opcoes-com-memoria.md).

## Medições

Trecho `espada`, do início do jogo até Link receber a espada. Orçamento de 600 inputs, supervisor `gemma3:4b`.

| Medida | Agente | Linha de base com opções |
| --- | --- | --- |
| Resultado | Não concluiu | Concluiu |
| Orçamento usado | 600 inputs | 23 decisões |
| Telas visitadas | 4 | 14 |
| Maior trecho repetitivo | 32 | 4 |
| Inputs contra uma parede | 232 de 600 | não se aplica |
| Tempo | 7 minutos | 5 minutos |

O agente sobe três telas, que é o caminho certo, e passa pelo primeiro diálogo apertando A. Depois fica indo e voltando entre as telas `00:6a` e `00:5a`. A personagem Impa passa a acompanhar Link depois do diálogo; o supervisor vê um personagem ao lado dele e manda ir até o personagem, que anda junto.

Nesse trecho o Laya segue a meta com 92% a 98% de confiança. O erro está na meta. Na rodada com o supervisor de 35B, o botão que o Laya apertou foi o que a meta pedia em 300 de 300 inputs.

O que cada ajuste mudou, sempre no mesmo trecho:

| Ajuste | Efeito |
| --- | --- |
| Prompt com exemplos de meta | O supervisor copiou um exemplo e repetiu `Press A to read the text` 28 vezes seguidas |
| Sem exemplos, com início obrigatório da meta | Link passou a andar e chegou a 4 telas. É a versão em uso |
| Árvores do mundo aberto deixaram de aparecer como blocos no mapa | As metas "empurre o bloco" sumiram |
| Esperar o texto ser escrito sem contar como input | O diálogo deixou de consumir o orçamento |
| Histórico de telas visitadas no texto do supervisor | Piorou: Link andou para a esquerda e para a direita na mesma tela por 440 inputs. Ficou como opção (`--history`) |
| Legenda só com os símbolos presentes e marca de quem segue Link | Piorou: 380 inputs contra a parede na primeira tela. Não foi adotado |
| Resposta do supervisor como botão mais finalidade, em formato fixo | Piorou: 200 de 200 inputs contra a parede. Não foi adotado |
| Memória do supervisor: diário das últimas metas, o que foi tentado em cada tela e uma nota que ele escreve para si mesmo (`--memory`) | Não melhorou: as mesmas 4 telas, 332 inputs contra a parede e mais idas e voltas (107 trocas de tela). Ficou como opção |
| Falas do jogo no texto do supervisor (`--texts`) | Piorou: 68 metas iguais seguidas e maior trecho repetitivo de 544. Ficou como opção |
| Meta com alcance: o supervisor diz por quantos inputs a meta vale (`--reach`) | Piorou nos dois modelos. Com `gemma3:4b`, 527 metas iguais ("ande para a direita até o personagem"). Com o de 35B, 114 metas para a esquerda alternadas com 109 para a direita, sempre atrás da personagem que acompanha Link. Ficou como opção |
| Marcar no mapa o personagem que acompanha Link (`--followers`) | Não melhorou: as mesmas 4 telas, maior trecho repetitivo de 128 |
| Dizer a que lados da tela dá para chegar andando (`--paths`) | Piorou: 69 metas iguais seguidas, maior trecho repetitivo de 548 |
| As duas juntas | Igual à versão em uso: 4 telas, maior trecho repetitivo de 32, a mesma ida e volta |
| Texto de um guia sobre o objetivo no estado do supervisor (`--guide`), com `gemma3:4b` | Piorou: ele copiou a primeira frase do guia e deu a meta "Walk north three screens" 150 vezes |
| O mesmo guia com `qwen3.6:35b-a3b`, 400 inputs | Melhorou para esse modelo, de 2 para 4 telas, e parou no mesmo ponto das outras variações: não vai para o oeste na quarta tela |
| Destino em vez de direção (`--walk-to`): o supervisor escolhe uma casa do mapa e o que fazer lá, e o código anda um passo por input até ela, com `gemma3:4b` | Piorou: ele escolheu a casa ao lado de Link com "aperte A" 595 vezes e Link não saiu da primeira tela |
| O mesmo, com `qwen3.6:35b-a3b` e o guia | Chegou à quarta tela em 47 inputs, o trecho mais rápido medido. Depois escolheu "aperte A" ao lado da Impa 110 vezes: ela acompanha Link e cada A reabre a fala. Maior trecho repetitivo de 553 |
| Dizer ao supervisor quantas vezes o último texto do jogo foi mostrado (`--repeats`), com `--walk-to`, o guia e `qwen3.6:35b-a3b` | Sem efeito: os mesmos 546 "aperte A" na quarta tela. A causa era do código: a meta dada com o texto aberto continuava valendo depois de ele fechar, e o A seguinte reabria o texto |
| A meta termina quando o texto fecha, mesma configuração | Melhorou: Link chegou à quinta tela (`00:59`, a oeste, que é o caminho certo) no input 380. É a primeira variação a passar da quarta tela. Depois escolheu "aperte A" em uma casa ao lado da Impa 217 vezes sem efeito |
| A meta termina quando o texto fecha, `gemma3:4b` padrão | 3 telas, maior trecho repetitivo de 7: Link anda para a esquerda e para a direita atrás da personagem que o acompanha (455 dos 600 inputs) |
| O mesmo, `gemma3:4b` com `--walk-to --repeats` | Igual a antes: "aperte A" na casa ao lado 588 vezes, na primeira tela |
| Com `--walk-to`, Link vira para o destino antes de apertar o botão, `qwen3.6:35b-a3b` com guia e `--repeats` | Não melhorou: 4 telas. O ciclo da quinta tela sumiu e apareceu outro: o supervisor escolhe como destino a personagem que acompanha Link, ela troca de lado a cada passo, e ele alterna "vire para cima" e "vire para baixo" por cerca de 540 inputs |
| O mesmo, somando `--followers` | Não melhorou: 4 telas, 83 trocas entre `00:6a` e `00:5a`. Na quarta tela ele tenta sair pelo norte, que está fechado, em vez de ir para o oeste como o guia diz |
| O mesmo, `gemma3:4b` com `--walk-to --repeats` | Igual: "aperte A" na casa ao lado 588 vezes, na primeira tela |
| Correções do `--walk-to`: o destino é descartado ao trocar de tela, a saída por um lado fechado é recusada e a resposta do supervisor pede o motivo por último, `qwen3.6:35b-a3b` com guia, `--repeats` e `--followers` | As consultas que falhavam sumiram: de 43 em 134 para 0 em 260. Antes o modelo se estendia no motivo, a resposta era cortada antes da casa de destino e o agente seguia com a meta antiga. O resultado não mudou: 4 telas. Na quarta tela ele alterna "vá até o personagem da linha 1" e "da linha 2" por 421 inputs, atrás da personagem que acompanha Link |
| Supervisor `qwen2.5:7b` | Pior: em 150 inputs Link não saiu da primeira tela |
| Supervisor `qwen3.6:35b-a3b`, sem a fase de raciocínio (`--no-think`), 300 inputs | Não saiu do ciclo: 2 telas, com 18 metas "ande para a direita" alternadas com 17 "ande para a esquerda". Os motivos são mais articulados, mas ele conclui que a saída norte está fechada depois de já ter passado por ela |

## Consequências

- O agente ainda entra em ciclos e não conclui o primeiro trecho do jogo. Esse é o comportamento medido dos dois modelos.
- O gargalo medido é o supervisor: ele repete metas que o próprio estado diz que falharam e imagina coisas que não estão no mapa.
- O ciclo mais frequente tem a mesma origem em todas as variações: depois do primeiro diálogo a personagem Impa acompanha Link, o mapa a mostra como um personagem ao lado dele, e o supervisor manda ir até ela.
- Trocar o supervisor por um modelo quase nove vezes maior não tirou o agente do ciclo. Isso aponta para o que o supervisor recebe e para o formato da meta, mais do que para o tamanho do modelo: uma meta vale por oito inputs e não diz até onde andar, e o mapa em caracteres não diz por onde há caminho.
- Vinte e três variações de percepção, memória, conhecimento do jogo, formato da meta e modelo foram medidas no mesmo trecho. Nenhuma concluiu o trecho. A que foi mais longe usa o supervisor de 35B com destino, guia e contagem de textos repetidos: cinco telas em uma rodada, quatro nas seguintes.
- O que cabe melhorar sem tirar a decisão dos modelos é a percepção em texto, o prompt e o modelo do supervisor. Vários ajustes de prompt pioraram o resultado, então cada um precisa ser medido no mesmo trecho antes de ser adotado.
- Cada input custa uma chamada ao Laya e, em média, uma chamada ao supervisor a cada cinco inputs. Um trecho de 600 inputs leva cerca de 7 minutos.

## Como rodar

```
python -m zelda_env.player                                   # com janela
python -m zelda_env.player --headless --steps 600 --until espada
python -m zelda_env.player --headless --steps 600 --supervisor qwen2.5:7b
python -m zelda_env.segments run espada --decisions 600
python -m zelda_env.segments run espada --mode options       # o mesmo trecho na linha de base
python scripts/demo_video.py --out output/demo/laya.mp4 --play "Do início do jogo" output/inicio.state 280
```

Quando uma consulta ao supervisor falha, a linha da meta traz o erro e a resposta como chegou.

O rastro em `trace.jsonl` tem uma linha por input, com a meta em vigor, o botão escolhido, a confiança do Laya e o resultado, e uma linha por meta nova, com o motivo que o supervisor deu.
