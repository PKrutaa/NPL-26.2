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

Nesse trecho o Laya segue a meta com 92% a 98% de confiança. O erro está na meta.

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
| Supervisor `qwen2.5:7b` | Pior: em 150 inputs Link não saiu da primeira tela |

## Consequências

- O agente ainda entra em ciclos e não conclui o primeiro trecho do jogo. Esse é o comportamento medido dos dois modelos.
- O gargalo medido é o supervisor: ele repete metas que o próprio estado diz que falharam e imagina coisas que não estão no mapa.
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

O rastro em `trace.jsonl` tem uma linha por input, com a meta em vigor, o botão escolhido, a confiança do Laya e o resultado, e uma linha por meta nova, com o motivo que o supervisor deu.
