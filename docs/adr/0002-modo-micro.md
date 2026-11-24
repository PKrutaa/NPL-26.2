# ADR 0002: no modo micro o Laya aperta um botão por vez e o supervisor escreve a meta

- Estado: aceito
- Data: 2026-11-23
- Substitui em parte o [ADR 0001](0001-agente-por-opcoes-com-memoria.md), que continua valendo para o modo opções.

## Contexto

O agente do ADR 0001 chegou longe: do boot até a entrada da dungeon 1 sem ciclos, e dentro dela até depois do mini-chefe. Mas quem decidia era, em boa parte, o código.

- O levantamento simula a sala em uma cópia do emulador e lista tudo o que dá para fazer.
- A memória tira da lista o que já foi tentado.
- Regras escolhem sozinhas em muitos casos: item no chão, botão de chão, sequência de blocos, luta simulada, rota conhecida.
- O Laya só escolhe entre opções prontas, como `Go north` ou `Push the object`.

Em uma rodada da dungeon 1, de 64 decisões, 41 foram regra do agente, 9 foram rota e 7 foram do Laya. O resultado media o código, não os modelos.

O que se quer medir é outra coisa: até onde os modelos vão quando a decisão é deles.

## Decisão

Existe um segundo modo, o modo micro, em `zelda_env/micro.py`.

| Papel | Modo opções (ADR 0001) | Modo micro |
| --- | --- | --- |
| Laya | Escolhe uma opção pronta | Escolhe um botão por input: cima, baixo, esquerda, direita, A ou B |
| Supervisor | Desempata escolhas incertas | Lê o estado em texto e escreve a meta do momento |
| Código | Descobre as opções, lembra, resolve, corta ciclos | Lê o jogo, monta o texto e aperta o botão escolhido |

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

Ele devolve uma meta de até doze palavras, que precisa começar por `Walk up`, `Walk down`, `Walk left`, `Walk right`, `Press A` ou `Press B`. Uma meta nova é pedida a cada oito inputs, quando a tela muda e a cada quatro inputs sem efeito.

### O que o Laya recebe

A meta do supervisor, para onde Link olha e o que está ao lado dele. Com isso escolhe um dos seis botões. Durante um texto do jogo, as escolhas são A e B.

### O que o código não faz neste modo

- Não simula nada à frente.
- Não lista ações possíveis.
- Não resolve salas de blocos nem simula lutas.
- Não guarda o que já foi tentado e não corta ciclos.
- Não desfaz decisões: se Link morre, o jogo segue como seguiria para uma pessoa.

Ele faz três coisas: lê o estado, espera enquanto o jogo está no controle (transição de tela, cena, texto sendo escrito) e aperta o botão escolhido.

## Medições

Trecho `espada`, do boot até Link receber a espada, 600 inputs de orçamento no modo micro, supervisor `gemma3:4b`.

| Medida | Modo opções | Modo micro |
| --- | --- | --- |
| Resultado | Passou | Não concluiu |
| Orçamento usado | 23 decisões | 600 inputs |
| Telas visitadas | 14 | 4 |
| Maior trecho repetitivo | 4 | 32 |
| Inputs contra uma parede | não se aplica | 232 de 600 |
| Tempo | 5 minutos | 7 minutos |

No modo micro Link sobe três telas, que é o caminho certo, e passa pelo primeiro diálogo. Depois fica indo e voltando entre as telas `00:6a` e `00:5a`: o supervisor manda ir até "o personagem" de uma tela e, chegando lá, manda voltar para o da outra.

O que cada ajuste mudou, sempre no mesmo trecho:

| Ajuste | Efeito |
| --- | --- |
| Prompt com exemplos de meta | O supervisor copiou um exemplo e repetiu `Press A to read the text` 28 vezes seguidas |
| Sem exemplos, com formato obrigatório | Link passou a andar e chegou a 4 telas |
| Árvores do mundo aberto deixaram de aparecer como blocos no mapa | As metas "empurre o bloco" sumiram |
| Esperar o texto ser escrito sem contar como input | O diálogo deixou de consumir o orçamento |
| Histórico de telas visitadas no texto do supervisor | Piorou: Link ficou andando para a esquerda e para a direita na mesma tela por 440 inputs. Ficou desligado por padrão (`--history`) |
| Supervisor `qwen2.5:7b` no lugar de `gemma3:4b` | Pior: em 150 inputs Link não saiu da primeira tela |

## Consequências

- O modo micro tem ciclos. Eles são o comportamento dos dois modelos sem o código por trás, e passam a ser a coisa a medir.
- O objetivo "jogar sem entrar em loops" está atendido no modo opções até a dungeon 1 e não está atendido no modo micro.
- O que ainda cabe melhorar sem voltar a mapear a sala é a percepção em texto e o prompt do supervisor.
- Cada input custa uma chamada ao Laya e, em média, uma chamada ao supervisor a cada cinco inputs. Um trecho de 600 inputs leva cerca de 7 minutos.
- O modo opções continua no repositório, para comparação. Os mesmos trechos, casos e relatórios servem para os dois modos.

## Como rodar

```
python -m zelda_env.micro --headless --steps 600 --until espada
python -m zelda_env.micro --headless --steps 600 --supervisor qwen2.5:7b
python -m zelda_env.segments run espada --mode micro --decisions 600
python -m zelda_env.segments run espada                       # o mesmo trecho no modo opções
python scripts/demo_video.py --out output/demo/laya-micro.mp4 --micro "Modo micro" output/inicio.state 280
```

O rastro em `trace.jsonl` tem uma linha por input, com a meta em vigor, o botão escolhido, a confiança do Laya e o resultado, e uma linha por meta nova, com o motivo que o supervisor deu.
