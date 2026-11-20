# Validação local do adapter e do Laya

Executada em 20 de novembro de 2026, no macOS arm64, com PyBoy 2.8.1 e Laya 0.5.0 em CPU. A inferência usou `convaiinnovations/laya`, revisão `fd4f9dbcf4fde222fd43174bdd4c3b08b789e4e1`, com `HF_HUB_OFFLINE=1`. [Laya upstream](https://github.com/NandhaKishorM/laya)

## Leitura e replay

- Pressionar cima em `00:8a` levou Link de `124,56` a `124,44`. Em seguida, pressionar direita contra a parede mudou a direção de cima para direita sem alterar XY. O executor relatou `blocked`.
- Continuar para cima disparou a transição de `00:8a` para `00:7a`. A observação omite posição e sala enquanto as variáveis de transição estão ativas.
- Diante do macaco em `00:5a`, o botão A abriu o diálogo. O avanço da primeira página foi detectado pela saída do estado de espera por entrada do textbox.
- O smoke do emulador passou com igualdade de estado e pixels após restaurar o checkpoint. A CLI interativa de benchmark também foi exercitada com entradas conhecidas, sem coleta de dados de um participante humano.

## Ensaio por cenário

| Política | Saída | Aproximação | Avanço de diálogo |
| --- | --- | --- | --- |
| Script | 1/1 · 5 decisões, 103 frames | 1/1 · 3 decisões, 39 frames | 1/1 · 5 decisões, 32 frames |
| Aleatória, sementes 0 a 9 | 0/10 | 1/10 | 3/10 |
| Laya, texto | 0/1 · 12 decisões, 156 frames | 1/1 · 3 decisões, 39 frames | 1/1 · 6 decisões, 12 frames |
| Laya, texto e histórico | 0/1 | 1/1 · 6 decisões, 45 frames | 1/1 |
| Laya, JSON | 0/1 | 1/1 | 1/1 |
| Laya, JSON e histórico | 0/1 | 0/1 · 12 decisões, 90 frames | 1/1 |

O Laya escolheu andar para a direita e encontrou a parede nas 12 decisões da saída em todas as configurações. As chamadas registraram zero truncamentos. Cada cenário usa um único checkpoint. A aproximação começa alinhada com o NPC, e o diálogo começa a uma distância em que A pode abrir o textbox. Os resultados medem esses casos locais e são insuficientes para estabelecer generalização ou efeito de formato e histórico.

Os logs incluem hash do checkpoint, hash do estado final, ações e observações, quadro de colisão, payload do Laya, resposta, métricas de tokens e latência da escolha. As probabilidades são saídas do modelo sem calibração específica para o jogo.

## Limites da observação

XY são pixels locais. O leitor reconhece os slots de interação com sprite visível dentro da tela e identifica Impa e os macacos. Outros slots ficam com tipo desconhecido. As máscaras de colisão cobrem salas pequenas e registram geometria estática em quadrantes. Objetos, equipamento e estado podem influenciar se um movimento realmente acontece. O leitor detecta estados de texto e avanço de página sem transcrever o diálogo.

## Recuperação após bloqueios

Com o mesmo modelo, checkpoint e limite de 12 decisões, a exploração após dois movimentos bloqueados chegou à saída em 7 de 10 sementes. A semente 0 concluiu em 11 decisões e 182 frames. A política original repetiu direita nas 12 decisões e terminou sem sair. A exploração escolhe entre direções que não acabaram de falhar e mantém a direção sorteada por até cinco ações enquanto houver movimento. O modo `--watch` varia a semente a cada volta. A comparação ainda se limita ao mesmo checkpoint.

## Ensaio de campanha com checkpoints persistentes

Na janela SDL2, Link saiu do checkpoint inicial, encontrou Impa, moveu a pedra, atravessou a introdução e recebeu a espada. Usou a espada para cortar o arbusto no caminho até Lynna City, atravessou Maku Path, falou com a Maku Tree e seguiu Ralph pelo portal para o passado. A execução salvou o marco `12-passado.state` em `01:39`, XY 40,40. A campanha é uma combinação de objetivos escritos à mão, busca em cópias locais do emulador e Choice do Laya nos diálogos. Os estados da busca são descartados. Os marcos são gerados por inputs no emulador principal.

A checagem de uma jogada por direção no benchmark de saída eliminou as colisões, mas o modelo continuou sem concluir no orçamento de 12 decisões. O checkpoint da campanha comprova progresso no jogo até o portal. A execução ainda não chegou às essências ou aos créditos.
