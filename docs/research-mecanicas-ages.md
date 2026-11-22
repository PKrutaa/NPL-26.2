# Mecânicas necessárias para terminar Oracle of Ages

Pesquisa feita em 22 de novembro de 2026. Jogo: The Legend of Zelda: Oracle of Ages, Game Boy Color, versão US, jogo não ligado (sem senha de Oracle of Seasons).

Este documento lista, em ordem de jogo, o que o agente precisa saber fazer para chegar ao fim. A seção 5 é o catálogo de mecânicas e serve de backlog de implementação.

## Como ler

- Ids de sala usam o formato `GG:RR` em hexadecimal (grupo:sala).
- Nomes de itens, dungeons e personagens estão em inglês, como o jogo mostra.
- `[TIMING]` marca uma ação que depende de tempo de reação.
- Cada mecânica tem um id fixo (`M01`, `M02`...). As tabelas de dungeon e de overworld usam esses ids.
- A coluna "Agente" parte de três valores: `sim` (já faz, segundo a lista do pedido), `não` (está na lista do que ele não faz) e `desconhecido` (não está em nenhuma das duas listas). Algumas células têm uma observação.
- Os botões descritos no catálogo vêm das fontes quando elas dizem. Onde está escrito `não confirmado`, o gesto vem de conhecimento geral do jogo e precisa de teste no emulador.
- Cada flag global foi associada ao passo pelo nome da constante. O script que liga a flag não foi lido.

## Fontes

| Sigla | Fonte | Como foi lida |
| --- | --- | --- |
| DIS | Disassembly local em `.cache/rom-build/oracles-disasm` (Stewmath/oracles-disasm). Os caminhos abaixo são relativos a essa pasta. | Arquivos locais |
| ZD-n | Zelda Dungeon, Oracle of Ages Walkthrough, capítulo n: `https://www.zeldadungeon.net/oracle-of-ages-walkthrough/<slug>/`, com slugs `spirits-grave` (1), `wing-dungeon` (2), `moonlit-grotto` (3), `skull-dungeon` (4), `crown-dungeon` (5), `mermaids-cave` (6), `jabu-jabus-belly` (7), `ancient-tomb` (8), `the-black-tower` (9) | O site devolve 403. Lido pela cópia do Internet Archive (`web.archive.org/web/2024id_/<url>`) |
| SW | StrategyWiki, `https://strategywiki.org/wiki/The_Legend_of_Zelda:_Oracle_of_Ages/<página>` | O site devolve 403. Lido pela cópia do Internet Archive (`web.archive.org/web/2023id_/<url>`) |

Fontes que não responderam: zeldadungeon.net direto (403), strategywiki.org direto (403), zelda.fandom.com (403), gamefaqs.gamespot.com (403, e a cópia do Archive testada devolveu 404), zeldauniverse.net (403), supercheats.com (403). O zeldawiki.wiki respondeu ao `curl`, mas não foi usado: as duas fontes acima já cobriam os mesmos fatos.

Regra de confirmação usada: uma estratégia de chefe conta como confirmada quando ZD e SW concordam, ou quando uma delas concorda com o DIS. A ordem do caminho crítico segue ZD. Para as linhas 1 a 38, o SW foi usado só para conferir que os mesmos itens e missões aparecem no mesmo capítulo (Harp, Mystery Seeds, bombas, Flippers, Cheval, Tingle, Rafton, Scent Seedling, Wild Tokay, carpinteiros, Tune of Currents, Patch, Tuni Nut); a ordem tela a tela dessas linhas vem de uma fonte só. Da linha 39 em diante, as duas fontes foram comparadas passo a passo.

## Referência de memória para escrever objetivos

Endereços tirados de `ages.sym` (DIS).

| Símbolo | Endereço | Uso |
| --- | --- | --- |
| `wObtainedTreasureFlags` | `$c69a` (16 bytes) | Bit N ligado quando o tesouro de id N foi obtido. Byte `N / 8`, bit `N % 8`. |
| `wEssencesObtained` | `$c6bf` | Um bit por Essence. O comportamento de coleta é "set bit [param]" (`data/ages/treasureCollectionBehaviours.s:12` e `:356`). A relação bit = número da dungeon − 1 não foi conferida. |
| `wGlobalFlags` | `$c6d0` (16 bytes) | Flags globais de `constants/common/globalFlags.s`. |
| `wDungeonSmallKeys` | `$c672` (16 bytes) | Small Keys por dungeon. |
| `wDungeonBossKeys` | `$c682` (2 bytes) | Boss Keys, um bit por dungeon. |
| `wLinkHealth` / `wLinkMaxHealth` | `$c6aa` / `$c6ab` | Vida. |
| `wNumRupees` | `$c6ad` (2 bytes) | Rupees. |
| `wNumBombs` | `$c6b0` | Bombas. |
| `wNumEmberSeeds`, `wNumScentSeeds`, `wNumMysterySeeds` | `$c6b9`, `$c6ba`, `$c6bd` | Sementes. |
| `wAnimalCompanion` | `$c610` | `$0b` Ricky, `$0c` Dimitri, `$0d` Moosh (`include/wram.s:431`). |
| `wInventoryB` / `wInventoryA` | `$c688` / `$c689` | Itens nos botões. |
| `wActiveGroup` / `wActiveRoom` | `$cc2d` / `$cc30` | Sala atual. |
| `wDungeonIndex` | `$cc39` | Dungeon atual, `$ff` fora de dungeon. |
| `wNumTorchesLit` | `$cc8f` | Tochas acesas na sala. |
| `wActiveTriggers` | `$cca0` | Botões de chão ativos na sala (um bit por botão). |
| `wRotatingCubeColor` / `wRotatingCubePos` | `$ccad` / `$ccae` | Cor e posição do cubo colorido. |
| `wToggleBlocksState` / `wSwitchState` | `$cdd2` / `$cdd3` | Estado dos orbes e interruptores. |

Ids de tesouro usados neste documento (`constants/common/treasure.s`):

| Constante | Id | Constante | Id |
| --- | --- | --- | --- |
| `TREASURE_BOMBS` | `$03` | `TREASURE_SMALL_KEY` | `$30` |
| `TREASURE_CANE_OF_SOMARIA` | `$04` | `TREASURE_BOSS_KEY` | `$31` |
| `TREASURE_SWORD` | `$05` | `TREASURE_MAKU_SEED` | `$36` |
| `TREASURE_SWITCH_HOOK` | `$0a` | `TREASURE_ESSENCE` | `$40` |
| `TREASURE_FLUTE` | `$0e` | `TREASURE_GRAVEYARD_KEY` | `$42` |
| `TREASURE_SHOOTER` | `$0f` | `TREASURE_CROWN_KEY` | `$43` |
| `TREASURE_HARP` | `$11` | `TREASURE_MERMAID_KEY` | `$44` |
| `TREASURE_SHOVEL` | `$15` | `TREASURE_OLD_MERMAID_KEY` | `$45` |
| `TREASURE_BRACELET` | `$16` | `TREASURE_LIBRARY_KEY` | `$46` |
| `TREASURE_FEATHER` | `$17` | `TREASURE_RICKY_GLOVES` | `$48` |
| `TREASURE_SEED_SATCHEL` | `$19` | `TREASURE_BOMB_FLOWER` | `$49` |
| `TREASURE_EMBER_SEEDS` | `$20` | `TREASURE_MERMAID_SUIT` | `$4a` |
| `TREASURE_SCENT_SEEDS` | `$21` | `TREASURE_SLATE` | `$4b` |
| `TREASURE_PEGASUS_SEEDS` | `$22` | `TREASURE_TUNI_NUT` | `$4c` |
| `TREASURE_GALE_SEEDS` | `$23` | `TREASURE_SCENT_SEEDLING` | `$4d` |
| `TREASURE_MYSTERY_SEEDS` | `$24` | `TREASURE_ZORA_SCALE` | `$4e` |
| `TREASURE_TUNE_OF_ECHOES` | `$25` | `TREASURE_TOKAY_EYEBALL` | `$4f` |
| `TREASURE_TUNE_OF_CURRENTS` | `$26` | `TREASURE_FAIRY_POWDER` | `$51` |
| `TREASURE_TUNE_OF_AGES` | `$27` | `TREASURE_CHEVAL_ROPE` | `$52` |
| `TREASURE_FLIPPERS` | `$2e` | `TREASURE_ISLAND_CHART` | `$54` |
| `TREASURE_POTION` | `$2f` | `TREASURE_BOOK_OF_SEALS` | `$55` |
| `TREASURE_GORON_LETTER` | `$59` | `TREASURE_LAVA_JUICE` | `$5a` |
| `TREASURE_BROTHER_EMBLEM` | `$5b` | `TREASURE_GORON_VASE` | `$5c` |
| `TREASURE_GORONADE` | `$5d` | `TREASURE_ROCK_BRISKET` | `$5e` |

Entradas das dungeons, tiradas de `data/ages/warpSources.s` e `data/ages/warpDestinations.s`. A primeira sala de cada dungeon também aparece em `data/ages/dungeonData.s` (byte 1, sala para onde o Wallmaster leva).

| Dungeon | Índice (`wDungeonIndex`) | Tela de entrada | Primeira sala |
| --- | --- | --- | --- |
| Maku Road, presente | `$00` | `00:48` (saída no alto: `00:38`) | `04:04`, salas `04:01` a `04:04` |
| Maku Path, passado | `$0d` | `01:48` (saída no alto: `01:38`, pela `04:07`) | `04:0d`, salas `04:05` a `04:0d` |
| 1 Spirit's Grave | `$01` | `00:8d` | `04:24` |
| 2 Wing Dungeon | `$02` | `01:83` | `04:46` |
| 3 Moonlit Grotto | `$03` | `00:ba` | `04:66` |
| 4 Skull Dungeon | `$04` | `00:03` | `04:91` |
| 5 Crown Dungeon | `$05` | `00:0a` | `04:bb` |
| 6 Mermaid's Cave | `$06` e `$0c` | `01:0e` e `03:0f` | `05:26` e `05:44` |
| 7 Jabu-Jabu's Belly | `$07` | `02:90` | `05:56` |
| 8 Ancient Tomb | `$08` | `01:5c` | `05:aa` |
| Hero's Cave (só jogo ligado, segundo ZD-1) | `$0b` | `00:48` | `04:ce` |

O grupo `01` é o overworld do passado. Os grupos `02` e `03` contêm os mapas submersos. Qual das duas entradas de Mermaid's Cave é a do presente não foi conferido no DIS (veja as perguntas em aberto).

## 1. Caminho crítico em ordem

Só o que é obrigatório. "P" é presente, "A" é passado (antigo).

| # | Onde | O que fazer | Exige | Dá | Fonte |
| --- | --- | --- | --- | --- | --- |
| 1 | Forest of Time, P | Subir duas telas, encontrar Impa, empurrar a pedra com o triângulo, falar com todos os ouvintes de Nayru (o urso por último) | Empurrar, falar | Cena de Veran, `TREASURE_SWORD` | ZD-1 |
| 2 | Lynna City, P | Cortar arbusto, entrar na Maku Road (caverna à esquerda do portão), subir quatro telas | Espada | Encontro com a Maku Tree | ZD-1 |
| 3 | Ao lado da Maku Tree, P | Entrar no portal do tempo | — | Passado | ZD-1 |
| 4 | Black Tower, A | Falar com o operário que segura a planta | — | `TREASURE_SHOVEL` | ZD-1 |
| 5 | Maku Path, A (`01:48` para `04:0d`) | Cavar a entrada, resolver as salas de blocos, pisar no botão, abrir o baú da Small Key, passar a porta trancada, sair pela escada | Pá, empurrar, baú, Small Key | Acesso à Maku Tree no passado | ZD-1; DIS `scripts/ages/dungeonScripts.s:8` |
| 6 | Maku Tree, A | Derrotar dois Moblins | Luta | `GLOBALFLAG_MAKU_TREE_SAVED` (`$12`) | ZD-1 |
| 7 | Maku Tree, P | Voltar pelo portal e falar com a Maku Tree | — | `TREASURE_SEED_SATCHEL` com 20 Ember Seeds | ZD-1 |
| 8 | Yoll Graveyard, P | Queimar arbustos, descer a escada escondida, acender as duas tochas | Ember Seeds | `TREASURE_GRAVEYARD_KEY` | ZD-1, SW |
| 9 | Yoll Graveyard, P (`00:8d`) | Empurrar o portão com a chave e entrar na dungeon | Graveyard Key | Spirit's Grave | ZD-1, SW |
| 10 | **Dungeon 1, Spirit's Grave** | Veja a seção 2.1 | Ember Seeds, espada | `TREASURE_BRACELET`, Essence 1 (Eternal Spirit) | ZD-1, SW, DIS |
| 11 | Oeste de Lynna City, P | Levantar a pedra, ir até Fairies' Woods | Power Bracelet | Acesso ao bosque | ZD-2 |
| 12 | Fairies' Woods, P | Aceitar o jogo das fadas e achar as três (rota fixa de telas, uma sob pedra e duas sob arbustos) | Bracelet, espada | `GLOBALFLAG_WON_FAIRY_HIDING_GAME` (`$0e`). Ao levantar a pedra seguinte, a dungeon desaba | ZD-2 |
| 13 | Nayru's House, P | Empurrar a estátua para a esquerda, descer ao porão | Empurrar | `TREASURE_HARP` e `TREASURE_TUNE_OF_ECHOES` | ZD-2 |
| 14 | Ao lado de Nayru's House, P | Tocar Tune of Echoes sobre o portal e entrar | Harp | Passado | ZD-2 |
| 15 | Deku Forest, A | Levantar pedras, atravessar a caverna, colher Mystery Seeds da árvore com a espada | Bracelet, Satchel | `TREASURE_MYSTERY_SEEDS` | ZD-2 |
| 16 | Deku Forest, A | Passar pelo Business Scrub com as sementes: um guarda leva Link ao palácio (cena) | — | `TREASURE_BOMBS` (`GLOBALFLAG_0b`) | ZD-2; DIS `constants/common/globalFlags.s` |
| 17 | Deku Forest, A (`01:83`) | Explodir a entrada rachada | Bombas | Wing Dungeon | ZD-2 |
| 18 | **Dungeon 2, Wing Dungeon** | Seção 2.2 | Bombas, Bracelet | `TREASURE_FEATHER`, Essence 2 (Ancient Wood) | ZD-2, SW |
| 19 | South Shore, A | Pular da ponte para a plataforma e falar com Cheval | Roc's Feather | Pista do túmulo | ZD-3 |
| 20 | Yoll Graveyard, P | Derrotar três fantasmas, montar em Moosh, voar sobre os buracos até a lápide do canto e empurrá-la para cima | Luta, Moosh | Entrada do túmulo de Cheval | ZD-3 |
| 21 | Túmulo de Cheval, P | Pular a água, puxar a alavanca com o Bracelet, pegar os Flippers, nadar até a corda | Feather, Bracelet | `TREASURE_FLIPPERS`, `TREASURE_CHEVAL_ROPE` | ZD-3; DIS `scripts/ages/scripts.s:6872` e `:6878` |
| 22 | Rafton's House, A | Entregar a corda | Cheval Rope | `GLOBALFLAG_GAVE_ROPE_TO_RAFTON` (`$15`) | ZD-3 |
| 23 | Forest of Time e praia, P | Falar com Ricky, cavar as luvas na praia, devolver, montar em Ricky e subir os penhascos até Tingle | Pá, Ricky | `TREASURE_RICKY_GLOVES`, depois acesso a Tingle | ZD-3 |
| 24 | Penhasco de Tingle, P | Pular e cortar o balão, falar e aceitar | Feather, espada | `TREASURE_ISLAND_CHART` | ZD-3; DIS `scripts/ages/scripts.s:9017` |
| 25 | Rafton's House, A | Falar com Rafton e embarcar na jangada: baixo 2, direita 1, cima 2 | Island Chart | Tempestade e chegada a Crescent Island sem itens | ZD-3 |
| 26 | Crescent Island, A | Recuperar os itens (seção 3.3), vencer o Wild Tokay, plantar a muda | Vários | Todos os itens de volta, `TREASURE_SCENT_SEEDLING` plantada | ZD-3 |
| 27 | Crescent Island, P | Colher Scent Seeds da árvore crescida | Harp, espada | `TREASURE_SCENT_SEEDS` | ZD-3 |
| 28 | Crescent Island, A e P (`00:ba`) | Cavar o portal escondido, voltar ao presente, andar até a dungeon | Pá, Harp | Moonlit Grotto | ZD-3 |
| 29 | **Dungeon 3, Moonlit Grotto** | Seção 2.3 | Bombas, Harp, Scent Seeds | `TREASURE_SHOOTER`, Essence 3 (Echoing Howl) | ZD-3, SW |
| 30 | Costa norte de Crescent Island, P | Dar Ember Seeds aos Tokay, montar em Dimitri e cruzar o mar | Ember Seeds | Volta ao continente | ZD-4 |
| 31 | Oeste de Lynna City, P | Com o Seed Shooter, queimar o arbusto e acertar a alavanca da ponte | Seed Shooter, Ember Seeds | Nuun Highlands | ZD-4 |
| 32 | Nuun Highlands e Fairies' Woods, P | Falar com o chefe dos carpinteiros, aceitar o pedido da fada, achar o companheiro perdido (cima, baixo, cima), voltar e achar os três carpinteiros | Companheiro | Flauta do companheiro (`GLOBALFLAG_GOT_FLUTE`, `$23`), ponte (`GLOBALFLAG_SYMMETRY_BRIDGE_BUILT`, `$25`) | ZD-4 |
| 33 | Symmetry City, P e A | Colher Gale Seeds, descobrir os portais sob os arbustos, falar com as irmãs e os dois irmãos | Espada, Harp | Broken Tuni Nut | ZD-4 |
| 34 | Talus Peaks, A | Mergulhar no quadrado fundo, falar com Tokkey, tocar Tune of Echoes sobre o tile verde | Flippers, Harp | `TREASURE_TUNE_OF_CURRENTS` | ZD-4 |
| 35 | Talus Peaks, A e P | Alternar entre as épocas, empurrar a pirâmide vermelha e a muda de trepadeira, chegar à Restoration Wall e subir pelas trepadeiras desviando das pedras | Harp, Bracelet, empurrar | Casa de Patch | ZD-4 |
| 36 | Casa de Patch, A | Vencer a cerimônia de restauração (mini-jogo) | Feather | `TREASURE_TUNI_NUT` restaurada | ZD-4, SW Minigames |
| 37 | Symmetry Village, A | Colocar a Tuni Nut no altar da casa do meio | Tuni Nut | `GLOBALFLAG_TUNI_NUT_PLACED` (`$29`) | ZD-4 |
| 38 | Symmetry City, P (`00:03`) | Entrar pela abertura da cachoeira | — | Skull Dungeon | ZD-4 |
| 39 | **Dungeon 4, Skull Dungeon** | Seção 2.4 | Feather, Seed Shooter, bombas, Bracelet | `TREASURE_SWITCH_HOOK`, Essence 4 (Burning Flame) | ZD-4, SW |
| 40 | Rolling Ridge, A e P | Cruzar os buracos com o Switch Hook, alternar épocas, colher Pegasus Seeds (árvore só no passado) | Switch Hook, Harp, Bracelet | `TREASURE_PEGASUS_SEEDS` | ZD-5, SW |
| 41 | Great Moblin's Keep, P | Correr com Pegasus Seed antes de o piso sumir, descer, devolver as bombas grandes do Great Moblin | Pegasus Seeds, Bracelet | `GLOBALFLAG_MOBLINS_KEEP_DESTROYED` (`$1a`), `TREASURE_BOMB_FLOWER` | ZD-5, SW; DIS `scripts/ages/scripts.s:7376` |
| 42 | Rolling Ridge, A | Dar a Bomb Flower aos Gorons na pilha de pedras | Bomb Flower | `GLOBALFLAG_SAVED_GORON_ELDER` (`$2f`), `TREASURE_CROWN_KEY` | ZD-5, SW |
| 43 | Rolling Ridge, P (`00:0a`) | Caverna de ilhas: salto longo com Pegasus Seed e Feather; usar a Crown Key na fechadura | Pegasus Seeds, Feather, Crown Key | Crown Dungeon | ZD-5 |
| 44 | **Dungeon 5, Crown Dungeon** | Seção 2.5 | Seed Shooter, Switch Hook, Ember Seeds | `TREASURE_CANE_OF_SOMARIA`, Essence 5 (Sacred Soil) | ZD-5, SW |
| 45 | Rolling Ridge leste, A e P | Cadeia de trocas dos Gorons, com cinco mini-jogos obrigatórios (seção 3.6) | Rupees, Seed Shooter, Pegasus Seeds, Feather, Switch Hook | `TREASURE_BROTHER_EMBLEM`, `TREASURE_OLD_MERMAID_KEY`, `TREASURE_MERMAID_KEY` | ZD-6, SW, SW Minigames; DIS `scripts/ages/scripts.s:5442`, `:6509`, `:5453` |
| 46 | **Dungeon 6, Mermaid's Cave**, A e P | Seção 2.6. Ordem: passado, presente, passado | As duas chaves, bombas, Seed Shooter, Switch Hook, Cane, Harp | `TREASURE_MERMAID_SUIT`, Essence 6 (nome não confirmado nas fontes lidas) | ZD-6, SW; DIS `data/ages/chestData.s:111` |
| 47 | Ambi's Palace, A | Pisar em quatro botões do jardim sem ser visto pelos guardas, nadar pelo canal, vencer Nayru possuída (seção 3.7) | Mermaid Suit, Mystery Seeds, Seed Shooter, Switch Hook | `GLOBALFLAG_BEAT_POSSESSED_NAYRU` (`$19`), `GLOBALFLAG_SAVED_NAYRU` (`$11`), `TREASURE_TUNE_OF_AGES` | ZD-7, SW |
| 47a | Loja de Syrup, Yoll Graveyard, P | Comprar a Magic Potion por 300 Rupees | 300 Rupees | `TREASURE_POTION` | ZD-7 |
| 48 | Zora Village e mar, A e P | Chegar à vila alternando épocas, dar a poção a King Zora, pegar a Library Key, o Book of Seals e a Fairy Powder, curar a Fairy Queen, obter a permissão (seção 3.7) | Tune of Ages, Mermaid Suit, Switch Hook, Potion | `GLOBALFLAG_KING_ZORA_CURED` (`$27`), `TREASURE_LIBRARY_KEY`, `TREASURE_BOOK_OF_SEALS`, `TREASURE_FAIRY_POWDER`, `GLOBALFLAG_WATER_POLLUTION_FIXED` (`$30`), `GLOBALFLAG_GOT_PERMISSION_TO_ENTER_JABU` (`$31`) | ZD-7, SW; DIS `scripts/ages/scripts.s:8345` |
| 49 | **Dungeon 7, Jabu-Jabu's Belly** (`02:90`), P | Seção 2.7 | Mermaid Suit, Seed Shooter, Scent Seeds, Switch Hook | Long Hook (`TREASURE_OBJECT_SWITCH_HOOK_01`), Essence 7 (Rolling Sea) | ZD-7, SW; DIS `data/ages/chestData.s:128` |
| 50 | Zora Village, P | Nadar uma tela para baixo do santuário de Jabu-Jabu; um Zora entrega a escama | — | `TREASURE_ZORA_SCALE` | ZD-8; DIS `scripts/ages/scripts.s:8628` |
| 51 | Sea of Storms, A | Tocar Tune of Ages, nadar, mergulhar, passar pelo Zora guarda, achar o navio pirata e entregar a escama ao capitão | Tune of Ages, Mermaid Suit, Zora Scale | `TREASURE_TOKAY_EYEBALL`, `GLOBALFLAG_PIRATES_GONE` (`$34`) | ZD-8, SW |
| 52 | Sul de Crescent Island, A | Ir de Gale Seed até South Shore, nadar até a estátua-cabeça e colocar o olho | Gale Seeds, Tokay Eyeball | Entrada das três salas de teste | ZD-8 |
| 53 | Salas de teste e Sea of No Return, A (`01:5c`) | Matar cinco Gibdos, passar pelas blade traps, cruzar o piso invisível, alinhar os três Armos, atravessar o labirinto de telas | Luta, Feather, empurrar | Ancient Tomb | ZD-8, SW |
| 54 | **Dungeon 8, Ancient Tomb** | Seção 2.8 | Todos os itens | Power Glove (`TREASURE_OBJECT_BRACELET_02`), Essence 8 (Falling Star) | ZD-8, SW; DIS `data/ages/chestData.s:150` |
| 55 | Maku Tree, P | Falar com a Maku Tree | 8 Essences | `TREASURE_MAKU_SEED`, `GLOBALFLAG_GOT_MAKU_SEED` (`$35`) | ZD-9 |
| 56 | Black Tower, A | Tocar Tune of Ages, subir os três andares, o labirinto de escadas e a sala das chamas | Maku Seed | Sala de Veran | ZD-9, SW |
| 57 | Topo da Black Tower, A | Derrotar Veran em três fases (seção 2.9) | Mystery Seeds, Seed Shooter, Long Hook, bombas, espada | Créditos (`GLOBALFLAG_FINISHEDGAME`, `$14`) | ZD-9, SW |

## 2. Dungeons

### 2.1 Dungeon 1: Spirit's Grave (`wDungeonIndex` = `$01`)

**Resumo**

| Campo | Valor |
| --- | --- |
| Entrada | `00:8d` para `04:24` |
| Item | Power Bracelet (`TREASURE_BRACELET`, `$16`), solto por script na sala `04:10` (`scripts/ages/dungeonScripts.s:65`) |
| Small Keys | 3: cai na `04:1e`, baú na `04:1a`, baú na `04:16` (`data/ages/chestData.s:54` em diante, e ZD-1) |
| Portas trancadas | 3: `04:1d` para cima, `04:14` para baixo, `04:17` para baixo. A primeira vem só do SW ("open the north door"); as outras duas estão em ZD-1 e SW |
| Mini-boss | Giant Ghini (`ENEMY_GIANT_GHINI`, `$70`), sala `04:18` |
| Boss | Pumpkin Head (`ENEMY_PUMPKIN_HEAD`, `$78`), sala `04:13` |
| Essence | Sala `04:11` (`INTERAC_ESSENCE`) |

**Mapa.** Grade de `data/ages/dungeonLayouts.s:31`. Cada célula é uma sala do grupo `04`. Norte fica em cima.

```
 10  .   .   11
 .   .   12  13
 .   .   14  15  16
 .   17  18  19  1a
 .   1b  .   1c  1d  1e
 .   1f  .   .   20  21
 .   22  23  24  25
```

A sala `10` não é vizinha de nenhuma outra: é a sala lateral subterrânea do Bracelet, alcançada pela escada da `1b`.

**Salas, na ordem do caminho.** O conteúdo vem de `objects/ages/mainData.s:2648` a `:2768` e de `data/ages/chestData.s`. A solução vem de ZD-1 e SW.

| Passo | Sala | Conteúdo (DIS) | O que fazer (ZD-1, SW) | Mecânicas |
| --- | --- | --- | --- | --- |
| 1 | `04:24` | Texto de entrada, estátua-olho, ponto do portal do mini-boss | Ir para a direita | M01 |
| 2 | `04:25` | 3 Zol (`$34`), portas que abrem com a sala limpa (`$1e` subids `$08`, `$0b`), baú do Dungeon Map numa saliência | Matar os Zols (cada um vira dois Gels). Empurrar o bloco de baixo da direita. Subir | M05, M14, M03 |
| 3 | `04:20` | Cubo colorido (`INTERAC_COLORED_CUBE`), 4 chamas, portas controladas por trigger para cima e para a direita (`$1e` subids `$04`, `$05`), evento `$21` subid `$19` | Empurrar o cubo para cima até o tile preto entre as tochas, com a face azul para cima. As chamas ficam azuis e as portas abrem. O trigger 0 liga quando `wRotatingCubeColor` = `$82` (`object_code/ages/interactions/dungeonEvents.s:153`) | M15 |
| 3a | `04:20` e `04:25` | — | Opcional: subir os degraus da esquerda, descer uma tela e abrir o baú do Dungeon Map. Pular da saliência e refazer o cubo (a sala volta ao estado inicial) | M16, M17 |
| 4 | `04:21` | 2 Stalfos (`$31`) e inimigos aleatórios | Atravessar e subir | M05 |
| 5 | `04:1e` | Ghini (`$17`), portas que abrem com a sala limpa (baixo e esquerda), `INTERAC_DUNGEON_STUFF` subid `$01`, que roda `dropSmallKeyWhenNoEnemiesScript` (`object_code/common/interactions/dungeonStuff.s:92`) | Matar o Ghini. As portas abrem e uma Small Key cai no tile vermelho. Pegar a chave e ir para a esquerda | M14, M10 |
| 6 | `04:1d` | Baú do Compass | Empurrar o bloco central e subir pela porta de cima (trancada, segundo SW). O Compass é opcional | M03, M18 |
| 6a | `04:1c` | 2 Rope (`$10`), botão (`PART_BUTTON`), script "baú quando o trigger 0 liga", baú com anel | Opcional: queimar as trepadeiras da parede esquerda da `1d` com Ember Seed, matar os Ropes, pisar no botão, abrir o baú | M09, M19, M16 |
| 7 | `04:1a` | Keese (`$32`), baú com Small Key | Empurrar o bloco de baixo da direita, seguir o caminho e abrir o baú. Empurrar o bloco solto da esquerda e ir para a esquerda | M03, M16 |
| 8 | `04:19` | Keese | Empurrar o bloco da esquerda para baixo e o da direita para a esquerda, contornar e voltar para a direita | M03 |
| 9 | `04:1a` para `04:16` | `04:16`: dois botões, porta de baixo controlada por trigger (`$1e` subid `$06`), baú com Small Key, script da plataforma | Subir. A porta fecha atrás de Link. Empurrar os cinco blocos de cima (centro para cima, vizinho esquerdo para a esquerda, o de cima dele para cima, o de baixo da direita para a direita, o de cima dele para cima). Pisar no botão da esquerda: aparece o baú. Pisar no da direita: aparece a plataforma (`spiritsGraveScript_spawnMovingPlatform`, `scripts/ages/dungeonScripts.s:54`). Andar na plataforma até o baú e pegar a Small Key | M21, M03, M19, M20, M16 |
| 10 | `04:1a`, `04:19`, `04:15` | `04:15`: plataforma móvel (`INTERAC_MOVING_PLATFORM`), botão, baú com Gasha Seed | Descer, ir para a esquerda e subir. Cruzar na plataforma e sair pela esquerda. O baú é opcional | M20 |
| 11 | `04:14` | Sem objetos (arbustos no cenário) | Cortar os arbustos, abrir a porta trancada de baixo | M04, M18 |
| 12 | `04:18` | Giant Ghini antes do evento, portas que abrem com a sala limpa, script do portal | Derrotar o mini-boss. Aparecem uma fada e o portal para a entrada | M22, M23, M29 |
| 13 | `04:17` | 2 Boomerang Moblin (`$0a`) | Atravessar e abrir a porta trancada de baixo | M05, M18 |
| 14 | `04:1b` (parte esquerda) | — | Fileira de três blocos: os das pontas para baixo, o do meio para o lado. Descer | M03 |
| 15 | `04:1f` | 4 Stalfos, baú com anel | Matar os Stalfos e subir pelo caminho da direita | M05 |
| 16 | `04:1b` (parte direita) | 2 Stalfos, script "escada quando 2 tochas acesas" (`spiritsGraveScript_stairsToBraceletRoom`, `scripts/ages/dungeonScripts.s:117`) | Acender as duas tochas do alto da sala com Ember Seeds. A escada aparece. Há Ember Seeds nos arbustos ao sul (SW) | M12 |
| 17 | `04:10` | Script que solta o Bracelet | Sala lateral: descer uma escada de mão, subir a outra, pegar o Power Bracelet | M24, M10 |
| 18 | `04:1f` | — | Opcional: levantar os vasos e abrir o baú do anel | M25, M16 |
| 19 | `04:22` | Na versão US: botão e porta controlada por trigger (`mainData.s:2746`, bloco `.ifndef REGION_JP`) | Descer os degraus e empurrar o vaso solto da direita para cima do botão. A porta da direita abre | M26 |
| 20 | `04:23` | 3 Stalfos, baú com Boss Key | Levantar os vasos do caminho e os que cercam o baú. Abrir o baú | M25, M16, M27 |
| 21 | `04:24` | Portal | Ir para a direita até a entrada e usar o portal para a `04:18` | M23 |
| 22 | `04:14`, `04:12` | `04:12`: Wallmaster (`$28`) | Subir, cortar arbustos, subir pelo canto superior esquerdo. Atravessar a `04:12` sem parar: o Wallmaster cai do teto e leva Link para a `04:24`. Ele reaparece sempre | M28 |
| 23 | `04:13` | Pumpkin Head antes do evento, script de morte do boss | Abrir a porta do boss com a Boss Key e lutar | M27, M22 |
| 24 | `04:13`, `04:11` | Heart Container no centro (`dungeonScript_bossDeath`, `scripts/ages/dungeonScripts.s:85`), Essence | Pegar o Heart Container, subir uma tela e subir no altar | M30 |

**Giant Ghini.** Ele se cerca de três fantasmas pequenos. Um fantasma que gruda em Link o deixa lento e impede o golpe de espada. Um golpe mata cada fantasma pequeno. Golpear o Giant Ghini sem parar; ficar acima dele faz os fantasmas virem para a espada (ZD-1). SW concorda e fala em cerca de seis golpes.

**Pumpkin Head.** Tem três partes no código: corpo, cabeça e fantasma (`object_code/ages/enemies/pumpkinHead.s:4` a `:16`).

1. Ele anda devagar, pula para pisar em Link e cospe três projéteis em leque. Manter distância.
2. Golpear o corpo com a espada até ele sumir. Sobra a cabeça no chão.
3. Levantar a cabeça com o Power Bracelet. Embaixo está o fantasma, que é o ponto fraco.
4. Arremessar a cabeça para longe e golpear o fantasma com a espada. ZD-1 diz que também dá para jogar a cabeça em cima do fantasma.
5. Se o fantasma alcança a cabeça, o corpo volta e o ciclo recomeça.

ZD-1 e SW concordam.

**O que falta ao agente para a dungeon 1, em ordem de uso:** baú (M16), queda de chave e porta trancada (M18), botão de chão (M19), plataforma móvel (M20), mini-boss (M22), portal (M23), tochas (M12, se ainda não funcionar), sala lateral (M24), levantar e arremessar (M25), Boss Key (M27), Wallmaster (M28), luta do Pumpkin Head.

### 2.2 Dungeon 2: Wing Dungeon (`$02`, passado)

| Campo | Valor |
| --- | --- |
| Entrada | `01:83` para `04:46`, parede rachada aberta com bomba |
| Item | Roc's Feather (`TREASURE_FEATHER`, `$17`), numa sala lateral depois do mini-boss (`wingDungeonScript_spawnFeather`, `scripts/ages/dungeonScripts.s:128`) |
| Mini-boss | Swoop (`ENEMY_SWOOP`, `$71`) |
| Boss | Head Thwomp (`ENEMY_HEAD_THWOMP`, `$79`) |

**Swoop.** Ele voa e cai sobre a posição de Link. Onde ele cai no piso amarelo abre um buraco; cair no buraco leva ao andar de baixo e a luta recomeça. Ficar nos tiles azuis da borda, que não quebram, e golpear quando ele pousa. Depois de alguns golpes ele passa a quicar na direção de Link (ZD-2, SW concorda; SW fala em cerca de dez golpes).

**Head Thwomp.** Sala lateral. Ele gira mostrando quatro rostos coloridos. Subir a escada de mão até a saliência do alto e arremessar uma bomba dentro da cabeça aberta, de modo que ela entre quando o rosto vermelho aparece. Outro rosto dispara um ataque. Ele gira mais rápido a cada acerto. Quatro acertos (ZD-2 e SW concordam). `[TIMING]`

**Mecânicas das salas**

| Mecânica | Id |
| --- | --- |
| Matar todos os inimigos para abrir porta, soltar chave ou criar baú | M14 |
| Spiked Beetle: virar com escudo ou pá antes de golpear (pode ser evitado) | M05 |
| Cubo colorido por uma sequência fixa até o tile preto | M15 |
| Bomba em parede rachada | M34 |
| Sala lateral com escadas de mão, plataformas móveis e Thwomp que esmaga `[TIMING]` | M24, M43 |
| Minecart, e alavanca de trilho acertada com a espada durante o percurso `[TIMING]` | M37 |
| Buraco no piso que leva ao andar de baixo | M42 |
| Pular buracos com a Feather | M38 |
| Piso frágil que desaba se Link fica parado | M44 |
| Tile que muda de cor quando Link pula por cima (um tile, ou um grupo que deve copiar um padrão) | M39 |
| Bloco trancado aberto com Small Key | M40 |
| Vaso empurrado até um botão, com saltos para trocar de lado | M26, M38 |
| Estátuas coloridas que só se movem quando o tile de cor está na cor delas; copiar o arranjo do lado esquerdo | M41 |
| Zols invisíveis que aparecem quando Link pula o tile central | M39 |
| Arremessar bomba sobre um abismo para matar arqueiros (opcional) | M34 |

### 2.3 Dungeon 3: Moonlit Grotto (`$03`, presente)

| Campo | Valor |
| --- | --- |
| Entrada | `00:ba` para `04:66` |
| Item | Seed Shooter (`TREASURE_SHOOTER`, `$0f`), baú na `04:58` (`data/ages/chestData.s:74`), que aparece ao limpar a sala |
| Mini-boss | Subterror (`ENEMY_SUBTERROR`, `$72`) |
| Boss | Shadow Hag (`ENEMY_SHADOW_HAG`, `$7a`) |
| Flag | `GLOBALFLAG_D3_CRYSTALS` (`$0f`): os quatro cristais quebrados fazem a plataforma giratória cair para o subsolo |

**Subterror.** Ele anda debaixo da terra e ataca com a broca. Cavar com a pá quando ele chega perto, para desenterrá-lo, e golpear com a espada. Fica mais rápido a cada acerto (ZD-3 e SW concordam).

**Shadow Hag.** Ela se divide em quatro sombras que perseguem Link. Depois sai de uma sombra e corre atrás dele. Ela some se Link olha na direção dela. Ficar de costas e atirar uma semente com o Seed Shooter na parede à frente: a semente volta e acerta a boss atrás de Link. ZD-3 diz Scent Seed; SW não diz qual semente. As borboletas que ela solta dão corações e sementes. `[TIMING]`

**Mecânicas das salas**

| Mecânica | Id |
| --- | --- |
| Cristal azul quebrado com espada ou com semente; quatro no total | M52 |
| Plataforma giratória: gira Link para uma saída, e o sentido alterna a cada uso | M53 |
| Bomba arremessada por cima de uma grade para quebrar bloco rachado | M54 |
| Estátua empurrada por uma sequência fixa para soltar chave; blocos arrumados para copiar um padrão | M03, M41 |
| Harp tocada na sala mata Pols Voice | M55 |
| Cair de propósito em buraco para o subsolo | M42 |
| Interruptor azul/vermelho acionado por bomba; botão que acorda Armos | M52, M19 |
| Armos só morre com bomba (10 bombas de capacidade; reabastecer nos arbustos) | M56 |
| Sala de tiles que voam em Link: sobreviver até acabarem | M57 |
| Iron Mask só leva dano por trás; Like-Like engole o escudo; arbustos que são Beetles | M05 |
| Seed Shooter com Ember Seed para acender tocha à distância | M59 |
| Seed Shooter em cristal atrás de grade | M58 |
| Barra vermelha giratória: o interruptor muda o ângulo e a semente ricocheteia nela até a alavanca verde, que troca as pontes | M60 |
| Tiro diagonal que ricocheteia nas paredes, feito de cima de um botão | M58 |

### 2.4 Dungeon 4: Skull Dungeon (`$04`, presente)

| Campo | Valor |
| --- | --- |
| Entrada | `00:03` para `04:91` |
| Item | Switch Hook (`TREASURE_SWITCH_HOOK`, `$0a`), baú na `04:87` (`data/ages/chestData.s:81`), logo depois do mini-boss |
| Small Keys | 5 em ZD-4: 2 portas trancadas e 3 blocos trancados |
| Mini-boss | Armos Warrior (`ENEMY_ARMOS_WARRIOR`, `$73`) |
| Boss | Eyesoar (`ENEMY_EYESOAR`, `$7b`) |

**Armos Warrior.** Fase 1: ele lança uma espada teleguiada. Correr pela borda da sala deixando o mini-boss entre Link e a espada, para que a espada o acerte. Três acertos quebram a espada e o escudo. Fase 2: ele investe e bate nas paredes; golpear depois da batida e pular para sair da frente (ZD-4 e SW concordam). `[TIMING]`

**Eyesoar.** Um olho grande com quatro olhos menores em órbita. Acertar o olho central com o Switch Hook: ele troca de lugar com Link e fica tonto. Golpear com a espada até ele voltar a se mexer e repetir. SW acrescenta que o gancho precisa acertar o olho central, e que para isso é preciso abrir espaço destruindo olhos externos (que se regeneram) ou esperar eles se afastarem. `[TIMING]`

**Mecânicas das salas**

| Mecânica | Id |
| --- | --- |
| Lava: dano alto e volta à entrada da sala; pular os vãos com a Feather | M62, M38 |
| Plataformas móveis sobre lava, pulando de uma para outra `[TIMING]` | M20 |
| Cubo colorido por sequência fixa até o tile marcado | M15 |
| Porta trancada e bloco trancado | M18, M40 |
| Minecart; alavanca de trilho acertada antes de embarcar e durante o percurso | M37 |
| Tiro diagonal com ricochete em interruptor que se move `[TIMING]` | M58 |
| Tiro em interruptor de canto feito de cima de plataforma móvel `[TIMING]` | M58, M20 |
| Matar todos os inimigos com o Seed Shooter de dentro do carrinho antes do fim do trilho `[TIMING]` | M67 |
| Blade traps: provocar e passar enquanto recolhem `[TIMING]` | M65 |
| Alavanca de parede puxada com o Bracelet para parar a lava, e travessia antes de ela voltar `[TIMING]` | M46, M68 |
| Tiles que mudam de cor ao pular, até copiar um padrão | M39 |
| Zols invisíveis revelados ao pular o tile central | M39 |
| Bomba em parede rachada | M34 |
| Caminho que cobre todos os tiles da sala uma vez (os tiles passam de azul para vermelho) | M66 |
| Switch Hook: trocar de lugar com um bloco-diamante ou um vaso do outro lado de um vão | M63 |
| Levar um diamante até um botão com trocas sucessivas | M64 |
| Switch Hook de cima de plataforma móvel | M63, M20 |
| Sala lateral com plataformas que sobem, vasos para o gancho e escada | M24 |
| Vaso empurrado até botão | M26 |
| Stalfos amarelo que pula para longe do golpe: encurralar ou usar spin attack | M05 |

### 2.5 Dungeon 5: Crown Dungeon (`$05`, presente)

| Campo | Valor |
| --- | --- |
| Entrada | `00:0a` para `04:bb`, aberta com a Crown Key |
| Item | Cane of Somaria (`TREASURE_CANE_OF_SOMARIA`, `$04`), baú na `04:a5` (`data/ages/chestData.s:91`), depois das duas primeiras chaves |
| Small Keys | 5 em ZD-5 |
| Mini-boss | Smasher (`ENEMY_SMASHER`, `$74`) |
| Boss | Smog (`ENEMY_SMOG`, `$7c`) |

**Smasher.** Ele pula pela sala e tenta pegar uma bola que aparece, para jogá-la em Link. Levantar a bola antes dele com o Bracelet e arremessá-la nele. A bola some depois de alguns segundos. ZD-5 fala em cerca de seis acertos. `[TIMING]`

**Smog.** Ele se divide em pedaços que andam contornando arranjos de blocos. Criar blocos com a Cane of Somaria de modo que os pedaços se encontrem e se juntem; então golpear com a espada. São quatro arranjos. Um botão no canto superior esquerdo reinicia o arranjo. Diferenças: SW diz que também dá para empurrar os blocos da sala, que a espada atordoa um pedaço, que Smog junto solta raios, e que é preciso destruí-lo quatro vezes; ZD-5 fala em três golpes finais.

**Mecânicas das salas**

| Mecânica | Id |
| --- | --- |
| Matar todos os inimigos para a escada aparecer | M14 |
| Pilares vermelhos e azuis que sobem e descem com um cristal (espada, ou semente à distância). Inclui ficar sobre pilares baixos e atirar no cristal para subir junto, e andar por cima dos pilares altos | M71 |
| Três estátuas-olho acertadas com sementes em sequência rápida (`crownDungeonScript_spawnChestWhen3TriggersActive`) `[TIMING]` | M74 |
| Tochas acesas com Ember Seed que ricocheteia em defletores giratórios `[TIMING]` | M75, M59 |
| Botão que mostra um padrão; estátuas coloridas empurradas para copiá-lo | M41 |
| Estátuas sobre botões; um bloco da Cane serve de quarto peso | M26, M72 |
| Estátuas ligadas (empurrar uma move a outra); um bloco da Cane trava uma delas | M41, M72 |
| Bloco da Cane como degrau para alcançar saliência alta com a Feather (sala lateral) | M72, M24 |
| Bloco da Cane sobre botão estende ponte | M72, M19 |
| Piso invisível sobre buracos: observar o caminho dos Moblins, sondar com um bloco da Cane, ou trocar de lugar com um Moblin | M73 |
| Salto longo com Pegasus Seed e Feather | M69 |
| Diamante até botão com trocas | M64 |

### 2.6 Dungeon 6: Mermaid's Cave (`$06` e `$0c`, passado e presente)

| Campo | Valor |
| --- | --- |
| Entradas | Mesma caverna nas duas épocas. A Mermaid Key abre a porta do passado e a Old Mermaid Key abre a do presente (ZD-6). No DIS: `01:0e` para `05:26` e `03:0f` para `05:44` |
| Item | Mermaid Suit (`TREASURE_MERMAID_SUIT`, `$4a`), baú na `05:13` (`data/ages/chestData.s:111`), na dungeon do presente, na sala depois do mini-boss |
| Mini-boss | Vire (`ENEMY_VIRE`, `$75`), no presente |
| Boss | Octogon (`ENEMY_OCTOGON`, `$7d`), no passado. A Boss Key fica no presente |

**Relação entre as épocas** (ZD-6).

1. Passado, parte 1: acender quatro tochas numa ordem fixa (uma delas por ricochete) para abrir uma parede sobre água funda; pegar uma Small Key; explodir um ponto escondido de uma parede norte.
2. Sair e tocar Tune of Currents.
3. Presente: a passagem só existe porque a parede foi explodida no passado. Vencer Vire, pegar a Mermaid Suit e a Boss Key.
4. Sair e tocar Tune of Echoes.
5. Passado, parte 2: mergulhar na água funda com a Mermaid Suit, pegar mais duas Small Keys, enfrentar o boss.

**Vire.** Ele voa, dispara orbes azuis e investe. Golpear quando chega perto. Depois de alguns acertos ele investe menos; continuar até ele se dividir em dois Vires pequenos e golpear cada um quando investir. SW acrescenta que os orbes podem ser cortados com a espada e fala em três acertos por etapa. `[TIMING]`

**Octogon.** Link fica numa plataforma central e o boss nada em volta. As fontes divergem na superfície: ZD-6 manda atirar no rosto com o Seed Shooter quando ele vira para Link, ou ricochetear uma semente na parede atrás dele; SW manda golpear com a espada quando ele abre a boca e usar o Seed Shooter só debaixo d'água. Quando ele submerge, mergulhar e atirar nele; debaixo d'água ele persegue Link e solta bolhas que o prendem. Debaixo d'água só o item do botão A funciona. Os vasos da plataforma voltam com Scent Seeds a cada mergulho.

**Mecânicas das salas**

| Mecânica | Id |
| --- | --- |
| Ação no passado que muda a dungeon do presente | M87 |
| Quatro tochas acesas em ordem com o Seed Shooter, uma por ricochete | M59, M58 |
| Cutucar a parede com a espada para achar o ponto oco e explodir | M34 |
| Bomba por cima de grade | M54 |
| Switch Hook em diamantes, vasos e arbustos; diamantes levados a tiles marcados | M63, M64 |
| Ricochete de semente num bloco para acertar cristal atrás de barras; cristal troca pisos e pontes | M58, M52 |
| Scent Seed largada como isca para Ropes caírem em buracos | M09 |
| Cubo colorido rolado até tiles vermelho, amarelo e azul | M15 |
| Plataformas giratórias | M53 |
| Duas alavancas, com resultado aleatório | M46 |
| Candlehead aceso com Ember Seed | M59 |
| Mermaid Suit: nadar em água funda, mergulhar e emergir entre andares | M80 |
| Salas laterais submersas, com correnteza, flechas e plataforma móvel | M24, M80 |
| Blade traps gigantes `[TIMING]` | M65 |
| Vaso em botão, bloco da Cane em botão | M26, M72 |
| Portas e blocos trancados, matar todos os inimigos | M18, M40, M14 |

### 2.7 Dungeon 7: Jabu-Jabu's Belly (`$07`, presente)

| Campo | Valor |
| --- | --- |
| Entrada | `02:90` para `05:56`, depois da permissão de King Zora |
| Item | Long Hook (Switch Hook nível 2, `TREASURE_OBJECT_SWITCH_HOOK_01`), baú na `05:4e` (`data/ages/chestData.s:128`), na sala depois do mini-boss, atrás de um bloco trancado |
| Mini-boss | Angler Fish (`ENEMY_ANGLER_FISH`, `$76`) |
| Boss | Plasmarine (`ENEMY_PLASMARINE`, `$7e`) |

**Nível da água.** Três botões de chão no terceiro andar. O de tile vermelho esvazia toda a água funda. Um de tile azul, atrás de porta trancada, enche o primeiro andar. Outro de tile azul, atrás de bloco trancado e alcançável só com o Long Hook, enche até o segundo andar. Sequência de ZD-7: começa cheio, esvaziar, encher o 1F, esvaziar, encher o 1F, encher o 2F. Sem água, Link anda, abre baús expostos e cai por buracos. Com água, ele nada por cima dos buracos e troca de andar emergindo ou mergulhando.

**Angler Fish.** Sala lateral submersa. Ele quica e solta bolhas; golpear as bolhas dá Scent Seeds. Atirar uma Scent Seed com o Seed Shooter para ele murchar e golpear o orbe da cabeça (ZD-7 e SW concordam).

**Plasmarine.** Ele começa azul, dispara orbes da própria cor e vem na direção de Link. Usar o Long Hook nele: os dois trocam de lugar e ele troca de cor (azul ou vermelho), de modo que o orbe que ele mesmo soltou o acerta. Só um orbe da cor oposta o fere. SW concorda com a troca, não fala das cores e diz que a espada não serve. `[TIMING]`

**Mecânicas das salas**

| Mecânica | Id |
| --- | --- |
| Botões que sobem e descem a água | M81 |
| Mermaid Suit em todos os andares; salas laterais submersas | M80, M24 |
| Cair por buraco para o andar de baixo | M42 |
| Switch Hook e Long Hook em diamantes, inclusive atirando para outra saliência | M63, M83 |
| Diamantes levados para a frente de estátuas ou para botões | M64 |
| Switch Hook como arma debaixo d'água | M63 |
| Lâminas giratórias `[TIMING]` | M65 |
| Portas e blocos trancados, matar todos os inimigos, botões | M18, M40, M14, M19 |

### 2.8 Dungeon 8: Ancient Tomb (`$08`, passado)

| Campo | Valor |
| --- | --- |
| Entrada | `01:5c` para `05:aa` |
| Item | Power Glove (`TREASURE_OBJECT_BRACELET_02`), baú na `05:a6` (`data/ages/chestData.s:150`), prêmio do puzzle de caminho no B1F, antes do mini-boss. Levanta as estátuas azuis grandes |
| Slates | 4 baús no B2F: `05:7c`, `05:7e`, `05:92`, `05:94` (`data/ages/chestData.s:140` a `:144`). Colocar as quatro nas paredes do altar abre a escada para o B3F |
| Mini-boss | Blue Stalfos (`ENEMY_BLUE_STALFOS`, `$77`); SW chama de Big Stalfos |
| Boss | Ramrock (`ENEMY_RAMROCK`, `$07`) |

**Blue Stalfos.** Ele dispara dois tipos de orbe. O orbe inteiro deve ser rebatido com a espada. O orbe em cacho estoura ao ser golpeado: pular por cima com a Feather. Quando um orbe rebatido o acerta, ele vira uma forma pequena que voa; golpear essa forma (ZD-8; SW concorda no mecanismo e não cita os dois tipos). `[TIMING]`

**Ramrock.** Quatro formas. SW diz três acertos por forma.

| Forma | Como vencer |
| --- | --- |
| 1 | Ele anda de um lado para o outro no alto e lança os punhos. Rebater os punhos com a espada para que acertem a cabeça |
| 2 | Ele persegue Link com garras. Arremessar uma bomba no rosto, de modo que ele feche as garras sobre a bomba antes de ela explodir `[TIMING]` |
| 3 | Dois escudos, orbes que não podem ser rebatidos e lasers que varrem a sala. Atirar sementes na parede atrás dele para que ricocheteiem na nuca. ZD-8 diz Scent Seeds; SW não diz o tipo |
| 4 | Braços de corrente com bolas. Quando ele lança uma mão, puxar a outra para baixo três vezes com a Power Glove e soltar nele `[TIMING]`. SW sugere travar a bola lançada com um bloco da Cane |

**Mecânicas das salas**

| Mecânica | Id |
| --- | --- |
| Tochas com Ember Seed, incluindo tiro diagonal com ricochete | M12, M59, M58 |
| Bomba em parede atrás de estátua empurrada, blocos rachados | M34, M03 |
| Sala de quatro botões: diamante com o Long Hook, bloco da Cane, Link num botão, e tiro na tocha | M64, M72, M19, M83 |
| Plataformas giratórias | M53 |
| Pilares vermelhos e azuis, incluindo subir junto com eles | M71 |
| Puzzle de caminho que cobre todos os tiles (rota longa; ZD-8 lista os passos) | M66 |
| Power Glove: levantar e arremessar estátuas azuis | M84 |
| Minecarts, com portão de trilho aberto por puzzle de bloco e troca rápida de carrinho `[TIMING]` | M37 |
| Tiles voadores | M57 |
| Piso de gelo: lutar escorregando | M85 |
| Candlehead: acender com Ember Seed e depois matar | M05, M09 |
| Água corrente com buracos: nadar de lado para não ser sugado `[TIMING]` | M86, M80 |
| Salas laterais submersas e com escada de mão | M24, M80 |
| Alavanca de lava puxada até o fim, e travessia enquanto o piso está sólido `[TIMING]` | M46, M68 |
| Blade traps e lâminas giratórias `[TIMING]` | M65 |
| Colocar as quatro Slates no altar | M76 |
| Small Keys, blocos trancados, Boss Key | M18, M40, M27 |

### 2.9 Maku Path, Black Tower e Veran

**Maku Path** (`wDungeonIndex` = `$0d`, passado, salas `04:05` a `04:0d`, layout `dungeon0dLayout` em `data/ages/dungeonLayouts.s`). A Maku Road do presente é o índice `$00`, salas `04:01` a `04:04`, e é só um corredor. Mini-dungeon obrigatória antes da dungeon 1. O agente já passou por ela. Mecânicas: blocos (M03), botão que cria baú quando `wActiveTriggers` = `$01` (`scripts/ages/dungeonScripts.s:8`), baú com Small Key na `04:08` (`data/ages/chestData.s`), porta trancada, salas que abrem ao matar todos os inimigos. O mesmo arquivo tem scripts de tochas para esta área (`makuPathScript_keyFallsFromCeilingWhen1TorchLit`, `:35`), ligados à parte opcional.

**Hero's Cave.** ZD-1 trata como conteúdo de jogo ligado. Não entra no caminho crítico.

**Black Tower** (passado).

1. Três andares de salas com inimigos, que podem ser ignorados. No alto, a Maku Seed e as oito Essences abrem a passagem (ZD-9).
2. Turret: labirinto de escadas em dois níveis. ZD-9 dá uma rota de sete escadas; SW descreve de outro jeito ("manter o centro").
3. Sala das chamas: quatro chamas cercam Link e se espalham; só uma leva adiante. ZD-9: a penúltima da fileira de baixo. SW: a que começa atrás de Link.

**Veran.** O jogo não ligado termina na fase 3. ZD-9 e SW concordam: depois dela vêm os créditos. Twinrova aparece só em cena. O DIS tem `ENEMY_TWINROVA` e `ENEMY_GANON`, usados no jogo ligado.

| Fase | Como vencer |
| --- | --- |
| 1, Veran em Queen Ambi (`object_code/ages/enemies/veranPossessionBoss.s`) | Igual à luta de Nayru possuída. Acertar uma Mystery Seed com o Seed Shooter quando ela para para atacar. O espírito de Veran sai do corpo: puxá-lo com o Switch Hook e golpear com a espada. Três acertos. Ela solta uma aranha que persegue Link `[TIMING]` |
| 2, forma alada (`veranFairy.s`) | Quatro cópias escuras de Link andam no sentido contrário ao dele e só ferem por contato; morrem com alguns golpes e soltam corações. Golpear Veran quando ela se aproxima |
| 3, forma final (`veranFinalForm.s`) | Alterna três formas. Tartaruga: ela pula sobre Link e deixa ácido; fugir (ZD-9 usa Pegasus Seeds) e golpear quando a cabeça sai do casco. Aranha: arremessar uma bomba que exploda nela e golpear enquanto está fraca. Abelha: golpear a qualquer momento, desviando dos orbes e das abelhas pequenas `[TIMING]` |

## 3. Overworld entre as dungeons

### 3.1 Do início à dungeon 1

Passos 1 a 9 do caminho crítico. O agente já fez este trecho. Mecânicas: M01 a M13.

### 3.2 Da dungeon 1 à dungeon 2

| Missão | Mecânica | Id |
| --- | --- | --- |
| Levantar pedras do overworld | Power Bracelet | M25 |
| Jogo das fadas em Fairies' Woods: o bosque vira labirinto. Rota de ZD-2 a partir da clareira: cima, baixo, cima (fada sob a pedra solta); direita, esquerda 2 (arbusto mais à esquerda dos três de baixo); direita, esquerda, baixo (arbusto de baixo dos dois da esquerda) | Labirinto de telas, levantar, cortar | M31, M25, M04 |
| Harp of Ages no porão de Nayru's House, atrás da estátua | Empurrar | M03 |
| Portais inativos: tocar Tune of Echoes em cima do portal | Usar a Harp | M32 |
| Mystery Seeds na árvore de Deku Forest | Colher sementes com a espada | M33 |
| Captura pelo guarda e cena no palácio | Esperar cena | M06 |
| Entrada rachada da Wing Dungeon | Bomba | M34 |

### 3.3 Da dungeon 2 à dungeon 3

| Missão | Mecânica | Id |
| --- | --- | --- |
| Casa de Cheval: pular da ponte sobre a água | Feather | M38 |
| Moosh: montar andando até ele; segurar e apertar A várias vezes para voar sobre buracos | Companheiro | M45 |
| Túmulo de Cheval: pular trechos de água, puxar a alavanca até o fim com o Bracelet para separar dois blocos | Alavanca | M46 |
| Nadar com os Flippers (A acelera, B mergulha) | Nadar | M47 |
| Ricky: cavar as luvas, devolver, montar; pular penhascos e buracos | Pá, companheiro | M07, M45 |
| Tingle: pular e golpear o balão no ar | Feather e espada juntas | M38 |
| Jangada de Rafton: navegar por telas de mar | Jangada | M48 |
| Crescent Island: os Tokay levam todos os itens | Perda e recuperação de itens | M49 |
| Wild Tokay (obrigatório, dá a Scent Seedling) | Mini-jogo | M50 |
| Plantar a muda (falar com o Tokay), voltar no presente e colher Scent Seeds | Falar, colher | M02, M33 |
| Mergulhar num quadrado fundo para chegar a uma passagem submersa | Mergulho | M47 |
| Portal escondido sob terra: cavar e tocar a Harp | Pá, Harp | M07, M32 |

**Ordem de recuperação em Crescent Island** (ZD-3). O agente perde espada, pá, Bracelet, Feather, Flippers, Satchel e Harp.

1. Pá: falar com o Tokay ao sul.
2. Espada: caverna; empurrar a pedra verde e cavar a terra.
3. Empurrar a muda de trepadeira duas vezes para a direita (serve de escada depois).
4. Cabana de trocas: a Feather e o Bracelet estão lá, mas só um por vez. Trocar a pá pelo Bracelet.
5. Com o Bracelet: levantar a pedra, descer, explodir a entrada da sala do Wild Tokay e vencer o jogo. (As bombas não são levadas, segundo o texto, que as usa neste ponto; não confirmado em outra fonte.)
6. Entregar a muda ao Tokay do viveiro.
7. Cabana: trocar de volta para a Feather. Explodir a parede da caverna norte, pular e recuperar os Flippers.
8. Cabana: trocar de volta para o Bracelet. Nadar, levantar pedras, mergulhar, sair na saliência central e recuperar a Satchel.
9. Cabana: com a Satchel, comprar a Feather por 10 Mystery Seeds.
10. Caverna da lagoa: nadar, pular de plataforma em plataforma, recuperar a Harp.
11. No presente, colher Scent Seeds. No passado, trocar o Bracelet pela pá e comprar o Bracelet por 10 Scent Seeds.

As flags `GLOBALFLAG_BOUGHT_FEATHER_FROM_TOKAY` (`$36`) e `GLOBALFLAG_BOUGHT_BRACELET_FROM_TOKAY` (`$37`) marcam as duas compras.

### 3.4 Da dungeon 3 à dungeon 4

| Missão | Mecânica | Id |
| --- | --- | --- |
| Dar Ember Seeds aos Tokay e montar em Dimitri para cruzar o mar | Falar, companheiro | M02, M45 |
| Ponte para Nuun Highlands: queimar o arbusto e acertar a alavanca com o Seed Shooter | Seed Shooter | M58 |
| Escolha do companheiro | Veja abaixo | M45 |
| Achar o companheiro perdido em Fairies' Woods (cima, baixo, cima) | Labirinto de telas | M31 |
| Achar três carpinteiros em Nuun Highlands | Companheiro | M45 |
| Gale Seeds e portais sob arbustos em Symmetry City | Colher, cortar, Harp | M33, M04, M32 |
| Casa de Tokkey: mergulhar, tocar Tune of Echoes no tile verde | Mergulho, Harp | M47, M32 |
| Tune of Currents: vai do passado ao presente em qualquer lugar e deixa um portal de volta | Harp | M35 |
| Empurrar a pirâmide vermelha (muda a água) e a muda de trepadeira cinco vezes | Empurrar | M03 |
| Subir a Restoration Wall pelas trepadeiras desviando de pedras que caem; só o centro dá acesso ao topo `[TIMING]` | Escalada com obstáculos | M01 |
| Cerimônia de Patch (obrigatória) | Mini-jogo | M77 |
| Colocar a Tuni Nut no altar | Entregar item | M76 |

Flags deste trecho e do anterior, úteis para objetivos (associadas pelo nome): `GLOBALFLAG_TALKED_TO_CHEVAL` (`$43`), `GLOBALFLAG_MET_TINGLE` (`$1b`), `GLOBALFLAG_TALKED_TO_HEAD_CARPENTER` (`$22`), `GLOBALFLAG_COMPANION_LOST_IN_FOREST` (`$42`), `GLOBALFLAG_SAVED_COMPANION_FROM_FOREST` (`$24`), `GLOBALFLAG_FOREST_UNSCRAMBLED` (`$2b`), `GLOBALFLAG_TALKED_TO_SYMMETRY_BROTHER` (`$2a`).

**Escolha do companheiro** (ZD-4). O terreno de Nuun Highlands muda conforme o companheiro.

| Companheiro | Como é escolhido | Terreno | O que o jogador faz |
| --- | --- | --- | --- |
| Moosh | Padrão: não obter nenhuma Strange Flute | Grupos de buracos | Voar sobre buracos apertando A várias vezes |
| Dimitri | Comprar a Strange Flute na loja de Lynna City por 150 Rupees | Água e correntezas | Nadar e subir cachoeiras montado |
| Ricky | Ganhar a Strange Flute no Shooting Gallery de Lynna Village (50 pontos ou mais) | Mato e penhascos | Pular penhascos; soco para abrir arbustos |

Para o agente, o caminho sem compra e sem mini-jogo é o de Moosh. `wAnimalCompanion` (`$c610`) guarda a escolha.

### 3.5 Da dungeon 4 à dungeon 5

| Missão | Mecânica | Id |
| --- | --- | --- |
| Cruzar buracos com o Switch Hook num diamante | Switch Hook | M63 |
| Alternar épocas com Tune of Echoes e Tune of Currents; portal sob pedra | Harp, Bracelet | M32, M35, M25 |
| Colher Pegasus Seeds (árvore só no passado) | Colher | M33 |
| Great Moblin's Keep: piso que some; correr com Pegasus Seed `[TIMING]` | Pegasus Seed | M69 |
| Great Moblin: levantar as bombas grandes que ele joga e devolvê-las; cerca de seis acertos (ZD-5) `[TIMING]` | Devolver bombas | M70 |
| Dar a Bomb Flower aos Gorons (resposta "sim") | Falar | M02 |
| Caverna de ilhas: salto longo com Pegasus Seed e Feather | Salto longo | M69 |
| Usar a Crown Key na fechadura | Chave do overworld | M13 |

A dança dos Gorons e o Brother Emblem não aparecem em ZD-5 nem na página do SW para este trecho. Eles pertencem ao trecho seguinte.

### 3.6 Da dungeon 5 à dungeon 6

Rolling Ridge leste. É o trecho com mais mini-jogos obrigatórios. Ordem de ZD-6 (SW pega o Lava Juice depois da Old Mermaid Key).

| # | Onde | O que fazer | Dá | Id |
| --- | --- | --- | --- | --- |
| 1 | Caverna ao lado da Crown Dungeon, P | Empurrar quatro pedras para dentro de buracos; pisar no botão que estende a ponte | Acesso a Rolling Ridge Base | M03, M19 |
| 2 | Goron Dance Hall, P | Pagar 10 Rupees e vencer a dança | `TREASURE_BROTHER_EMBLEM` (`$5b`) | M78 |
| 3 | Ao lado do Dance Hall, P | Cortar o arbusto, tocar Tune of Echoes no portal | Passado | M04, M32 |
| 4 | Caverna, A | Mostrar o emblema ao Goron da escada. Cruzar os vãos com Pegasus Seed e Feather (ZD-6) ou com o Switch Hook (SW). Fora, puxar a muda de trepadeira com o Switch Hook até o ponto de terra. Tocar Tune of Currents e subir pela trepadeira crescida | Parte alta, P | M69, M63, M35 |
| 5 | Target Carts, P | Pontuação perfeita | `TREASURE_ROCK_BRISKET` (`$5e`) | M79 |
| 6 | Galeria de tiro dos Gorons, A (portal sob a pedra ao lado do Target Carts) | Mais de 100 pontos. Colher Mystery Seeds da árvore ao lado (necessárias para Nayru e Veran) | `TREASURE_LAVA_JUICE` (`$5a`) | M88, M33 |
| 7 | Dance Hall, P | Dar o Rock Brisket ao Goron com fome | `TREASURE_GORON_VASE` (`$5c`) | M76 |
| 8 | Dance Hall, A | Dar o Goron Vase ao Goron da escada | `TREASURE_GORONADE` (`$5d`) | M76 |
| 9 | Caverna do Big Bang Game, P | Dar a Goronade ao dono e vencer o jogo | `TREASURE_OLD_MERMAID_KEY` (`$45`) | M89 |
| 10 | Caverna ao norte da galeria, A | Dar o Lava Juice. SW diz que a troca só funciona com a Old Mermaid Key | `TREASURE_GORON_LETTER` (`$59`), que o jogo chama de Letter of Introduction | M76 |
| 11 | Dance Hall, A | Dar a carta ao Graceful Goron e vencer a dança | `TREASURE_MERMAID_KEY` (`$44`) | M78 |
| 12 | Cachoeira, A | Nadar para dentro da cachoeira e abrir a porta | Mermaid's Cave | M47, M13 |

Evitar o Old Man sob o arbusto solitário no presente: ele tira 100 Rupees (ZD-6). O Boomerang é opcional.

### 3.7 Da dungeon 6 à dungeon 7

| # | Onde | O que fazer | Dá | Id |
| --- | --- | --- | --- | --- |
| 1 | Jardim de Ambi's Palace, A | Pisar em quatro botões, um em cada canto, fora da linha de visão dos guardas. Ser visto expulsa Link, mas os botões já pisados continuam valendo. Cada botão move uma estátua `[TIMING]` | Caminho aberto | M90, M19 |
| 2 | Lado leste do jardim, A | Cortar arbustos, descer a escada, mergulhar e nadar duas telas para a esquerda desviando de redemoinhos | Interior do palácio | M80 |
| 3 | Palácio, A | Os guardas de dentro atacam; lutar. Empurrar um bloco para sair da sala de entrada | Sala de Nayru | M05, M03 |
| 4 | Sala do trono, A | Nayru possuída: ela se teleporta para junto de uma estátua e dispara orbes em círculo. Quando para, acertar uma Mystery Seed com o Seed Shooter. O espírito de Veran sobe: puxá-lo com o Switch Hook e golpear com a espada. ZD-7: três acertos. SW: repetir os passos duas vezes `[TIMING]` | `GLOBALFLAG_SAVED_NAYRU`, Tune of Ages | M22 |
| 5 | Loja de Syrup, P | Comprar a Magic Potion por 300 Rupees. Também pode vir de Maple ou de uma árvore Gasha | `TREASURE_POTION` | M51 |
| 6 | Zora Seas, A e P | Alternar épocas com Tune of Ages em ilhotas, mergulhar e usar o Switch Hook em dois diamantes submersos para cruzar a água envenenada. Num dos pontos a música tem de ser tocada bem em frente aos degraus | Zora Village | M36, M80, M63 |
| 7 | Palácio de King Zora, A | Dar a poção | `GLOBALFLAG_KING_ZORA_CURED` | M76 |
| 8 | King Zora, P | Falar | `TREASURE_LIBRARY_KEY` | M02 |
| 9 | Zora Village, A | Switch Hook num diamante para chegar à Fairy Queen. Abrir a Eyeglass Library com a chave | Biblioteca | M63, M13 |
| 10 | Biblioteca, P | Falar com o velho da sala dos fundos | `TREASURE_BOOK_OF_SEALS` | M02 |
| 11 | Biblioteca, A | Colocar o livro no pedestal verde e andar por um caminho invisível sobre buracos, um trecho por livro. Cair recomeça do início. Rotas (ZD-7 e SW iguais): D4 C2 D2; C2 E1 C2 D1 C1; E2 C1 E3; B1 E3 C1 E3; B1 D1 B2 E2 B3; D1 B1 D2 C1 D1 C1 D2 (D direita, E esquerda, C cima, B baixo) | `TREASURE_FAIRY_POWDER` | M73 |
| 12 | Zora Village, A | Dar o pó à Fairy Queen | `GLOBALFLAG_WATER_POLLUTION_FIXED` | M76 |
| 13 | King Zora, P | Falar; ir ao santuário de Jabu-Jabu | `GLOBALFLAG_GOT_PERMISSION_TO_ENTER_JABU` | M02 |

### 3.8 Da dungeon 7 à dungeon 8

| Missão | Mecânica | Id |
| --- | --- | --- |
| Receber a Zora Scale | Falar | M02 |
| Ir ao passado com Tune of Ages | Harp | M36 |
| Nadar e mergulhar até o Zora que guarda o Sea of Storms | Mermaid Suit | M80 |
| Achar o navio pirata, que anda pela região, e nadar até ele. A posição não é dada por nenhuma fonte | Busca em área aberta | M01 |
| Entregar a escama ao capitão | Entregar item | M76 |
| Viajar de Gale Seed para South Shore | Gale Seed | M82 |
| Colocar o Tokay Eyeball na estátua | Entregar item | M76 |
| Sala da força: matar cinco Gibdos | Luta | M14 |
| Sala da coragem: passar por blade traps `[TIMING]` | Blade traps | M65 |
| Sala da sabedoria: piso invisível com rota fixa (ZD-8) | Piso invisível | M73 |
| Empurrar o Armos que está fora de linha | Empurrar | M03 |
| Labirinto de telas do Sea of No Return, com Darknuts e Lynels | Labirinto de telas, luta | M31, M05 |

### 3.9 Da dungeon 8 ao fim

Falar com a Maku Tree no presente, tocar Tune of Ages perto da Black Tower e seguir a seção 2.9.

## 4. Chefes: resumo

| Onde | Chefe | Item-chave | Técnica | Confirmação |
| --- | --- | --- | --- | --- |
| D1 mini | Giant Ghini | Espada | Matar os fantasmas pequenos e golpear | ZD + SW |
| D1 | Pumpkin Head | Espada, Bracelet | Destruir o corpo, levantar a cabeça, golpear o fantasma | ZD + SW + DIS |
| D2 mini | Swoop | Espada | Esperar a queda nos tiles azuis e golpear | ZD + SW |
| D2 | Head Thwomp | Bombas | Bomba dentro da cabeça no rosto vermelho | ZD + SW |
| D3 mini | Subterror | Pá, espada | Desenterrar e golpear | ZD + SW |
| D3 | Shadow Hag | Seed Shooter | Tiro com ricochete, de costas | ZD + SW (tipo de semente só em ZD) |
| D4 mini | Armos Warrior | Espada, Feather | Fazer a espada dele acertá-lo; golpear após a investida | ZD + SW |
| D4 | Eyesoar | Switch Hook, espada | Gancho no olho central e golpes | ZD + SW |
| Overworld | Great Moblin | Bracelet | Devolver as bombas | ZD + SW |
| D5 mini | Smasher | Bracelet | Arremessar a bola nele | ZD + SW |
| D5 | Smog | Cane of Somaria, espada | Juntar os pedaços com blocos e golpear | ZD + SW, com diferenças |
| D6 mini | Vire | Espada | Golpear nas investidas; depois os dois Vires pequenos | ZD + SW |
| D6 | Octogon | Seed Shooter (e espada, segundo SW) | Atirar no rosto; mergulhar e atirar quando ele submerge | ZD e SW divergem na superfície |
| Palácio | Nayru possuída | Mystery Seeds, Seed Shooter, Switch Hook, espada | Semente, gancho no espírito, espada | ZD + SW (contagem diverge) |
| D7 mini | Angler Fish | Seed Shooter, Scent Seeds, espada | Semente para murchar, golpe no orbe | ZD + SW |
| D7 | Plasmarine | Long Hook | Trocar de lugar para o orbe dele acertá-lo | ZD + SW (cores só em ZD) |
| D8 mini | Blue Stalfos | Espada, Feather | Rebater o orbe; golpear a forma pequena | ZD + SW |
| D8 | Ramrock | Espada, bombas, Seed Shooter, Power Glove | Quatro formas | ZD + SW, com diferenças |
| Final | Veran | Seed Shooter, Mystery Seeds, Switch Hook, bombas, espada | Três fases | ZD + SW |

## 5. Catálogo de mecânicas

Ordenado pela primeira vez em que a mecânica é obrigatória. A coluna "Onde aparece" lista os trechos em que as fontes a citam no caminho obrigatório; "D" é dungeon e "OW n" é o trecho de overworld antes da dungeon n. A contagem é por trecho, não por sala.

| Id | Mecânica | O que o jogador faz | Primeira vez obrigatória | Onde aparece | Agente |
| --- | --- | --- | --- | --- | --- |
| M01 | Andar até saída, porta ou escada | Direcional | Início | Todos | sim |
| M02 | Falar, ler placa, avançar diálogo, responder sim/não | A de frente para o alvo; A ou B para avançar; direcional para escolher | Início | Todos | sim |
| M03 | Empurrar bloco ou objeto | Segurar o direcional contra o objeto | Forest of Time | Todos | sim |
| M04 | Cortar arbusto | Espada de frente para o arbusto | Lynna City | Todos | sim |
| M05 | Luta de espada com inimigo comum | Golpear; alguns inimigos pedem um detalhe (Zol divide, Iron Mask só por trás, Stalfos amarelo foge, Spiked Beetle precisa ser virado) | Maku Path | Todos | sim, sem os detalhes por inimigo |
| M06 | Entrar em tile de gatilho, esperar cena | Andar até o ponto; não apertar nada | Início | Todos | sim |
| M07 | Cavar com a pá | Item de frente para a terra | Lynna Village, A | OW 1, OW 3, D3 (Subterror) | sim |
| M08 | Equipar item pelo menu | Start, cursor, A ou B | OW 1 | Todos | sim |
| M09 | Largar semente pela Satchel | Item de frente para o alvo. Ember queima arbusto, muda e trepadeira; Scent serve de isca | OW 1 | OW 1, D1 (opcional), D6, D8 | sim |
| M10 | Pegar item no chão | Andar sobre o item | OW 1 | Todos | sim |
| M11 | Portal do tempo ativo | Andar para dentro do portal | OW 1 | Todos | sim |
| M12 | Acender tocha com Ember Seed pela Satchel | Ficar ao lado da tocha, de frente, e usar a semente | OW 1 (caverna da Graveyard Key) | OW 1, D1, D5, D8 | desconhecido. O agente obteve a Graveyard Key, que exige isso, mas a lista do pedido diz que ele não acende tochas |
| M13 | Fechadura do overworld | Andar contra o portão ou a fechadura com a chave no inventário | OW 1 (Graveyard Key) | OW 1, OW 5, OW 6, OW 7 | sim na prática (chegou à entrada da D1) |
| M14 | Matar todos os inimigos da sala | Limpar a sala. Efeitos: porta abre, chave cai, baú ou escada aparece | Maku Path | Todas as dungeons, OW 8 | parcial: a luta existe; ligar "sala limpa" ao efeito é novo |
| M15 | Cubo colorido no tile marcado | Empurrar o cubo por uma sequência que termina com a cor certa para cima | D1 `04:20` | D1, D2, D4, D6, D8 | sim para empurrar; escolher a sequência pela cor é desconhecido |
| M16 | Abrir baú | A de frente para o baú, vindo de baixo (`não confirmado`) | Maku Path (`04:08`) | Todas as dungeons | não, segundo o pedido. Mas o agente passou pela Maku Path, que exige baú, chave e porta trancada (ZD-1) |
| M17 | Descer de saliência | Andar contra a borda; é caminho só de ida | D1 | D1 a D8, overworld | desconhecido |
| M18 | Small Key e porta trancada | Pegar a chave (baú ou queda) e andar contra a porta | Maku Path | Todas as dungeons | não, segundo o pedido. Mesma observação de M16 |
| M19 | Botão de chão | Pisar. Efeitos: baú, plataforma, ponte, porta, estátua | Maku Path | Todas as dungeons, OW 6, OW 7 | desconhecido. Mesma observação de M16 |
| M20 | Plataforma móvel sobre buraco ou lava | Subir quando ela encosta e descer no outro lado `[TIMING]` | D1 `04:16` | D1, D2, D4, D5, D6 | não |
| M21 | Porta que fecha atrás de Link | Resolver a sala para sair | D1 `04:16` | Todas as dungeons | sim (o ADR já trata a comparação local) |
| M22 | Luta de chefe com roteiro | Um roteiro por chefe (seção 4) | D1 `04:18` | 8 mini-bosses, 8 bosses, Great Moblin, Nayru, Veran | não |
| M23 | Portal de mini-boss | Pisar no portal: liga a entrada à sala do mini-boss | D1 | D1 a D8 | desconhecido |
| M24 | Sala lateral | Vista de lado, com gravidade: escada de mão, plataformas, pulo depois da Feather | D1 `04:10` | D1, D2, D4, D5, D6, D7, D8 | desconhecido |
| M25 | Levantar e arremessar | SW: segurar o botão do Bracelet de frente para o objeto e puxar o direcional para trás para levantar. Arremessar: apertar o botão de novo (`não confirmado`) | D1 `04:1f`/`04:23` | D1 em diante, todo o overworld | não |
| M26 | Objeto pesado em botão | Empurrar um vaso ou uma estátua até o botão | D1 `04:22` | D1, D2, D4, D5, D6 | sim (empurrar) |
| M27 | Boss Key e porta do boss | Abrir o baú da chave e andar contra a porta | D1 | D1 a D8 | não |
| M28 | Wallmaster | Atravessar a sala sem parar; se for pego, volta à entrada | D1 `04:12` | D1; outras dungeons não conferidas | não |
| M29 | Recuperar vida | Pegar corações que caem, fada do mini-boss, cama de Nayru | D1 | Todos | não |
| M30 | Heart Container e Essence | Andar sobre o item; subir no altar | D1 | D1 a D8 | sim (pegar item) |
| M31 | Labirinto de telas | Seguir uma ordem fixa de saídas | OW 2 (Fairies' Woods) | OW 2, OW 4, OW 8, Black Tower | desconhecido |
| M32 | Tune of Echoes | Usar a Harp em cima de um portal inativo e entrar | OW 2 | OW 2 em diante | não |
| M33 | Colher sementes de árvore | Golpear a árvore com a espada e pegar as sementes | OW 2 (Mystery Seeds) | OW 2, OW 3, OW 4, OW 5, OW 6 | desconhecido |
| M34 | Bombas | Colocar ao lado de parede ou bloco rachado; levantar e arremessar | OW 2 (entrada da D2) | D2 a D8, OW 3 | não |
| M37 | Minecart | Andar para dentro do carrinho; golpear a alavanca de trilho ao passar `[TIMING]` | D2 | D2, D4, D8 | não |
| M43 | Thwomp em sala lateral | Provocar a queda e passar por baixo enquanto ele sobe `[TIMING]` | D2 | D2 | não |
| M42 | Cair para o andar de baixo | Andar para dentro de um buraco de propósito | D2 (por acidente), D3 | D2, D3, D7 | desconhecido. Hoje o levantamento descarta rotas com dano; cair num buraco comum dá dano |
| M38 | Roc's Feather | Apertar o botão do item andando, para pular um tile | D2 | D2 em diante, todo o overworld | não |
| M44 | Piso frágil | Não ficar parado sobre o piso | D2 | D2 | não |
| M39 | Tile que muda de cor ao ser pulado | Pular por cima do tile até a cor certa | D2 | D2, D4, D6 (opcional) | não |
| M40 | Bloco trancado | Andar contra o bloco com uma Small Key | D2 | D2, D4, D5, D6, D7, D8 | não |
| M41 | Estátuas e blocos em padrão | Empurrar peças para copiar um arranjo mostrado na sala | D2 | D2, D3, D5 | sim para empurrar; ler o padrão é novo |
| M45 | Companheiro animal | Andar até o animal para montar. Moosh: apertar A várias vezes para voar. Ricky: pular penhascos, soco. Dimitri: nadar | OW 3 (Moosh) | OW 3, OW 4 | não |
| M46 | Alavanca puxada com o Bracelet | Segurar o botão do Bracelet de frente para a alavanca e andar para trás até o fim (`não confirmado`; as fontes só dizem "puxar até o fim") | OW 3 (túmulo de Cheval) | OW 3, D4, D6, D8 | não |
| M47 | Nadar e mergulhar com os Flippers | Direcional na água; A acelera; B mergulha | OW 3 | OW 3, OW 4, OW 6 | não |
| M48 | Jangada | Andar para a jangada e navegar com o direcional | OW 3 | OW 3 | não |
| M49 | Perda de itens em Crescent Island | Recuperar item por item, numa ordem em que cada um libera o seguinte | OW 3 | OW 3 | não |
| M51 | Comprar e trocar | Falar com o vendedor; pagar com Rupees ou sementes | OW 3 (cabana dos Tokay) | OW 3, OW 6 (entradas dos jogos), OW 7 (poção de 300 Rupees) | não |
| M50 | Wild Tokay | Mini-jogo (seção 6) | OW 3 | OW 3 | não |
| M52 | Cristal ou interruptor | Golpear com espada, semente ou bomba | D3 | D3, D5, D6, D8 | não |
| M53 | Plataforma giratória | Pisar; ela vira Link para uma saída e alterna o sentido a cada uso | D3 | D3, D6, D8 | não |
| M54 | Bomba por cima de grade | Arremessar a bomba para que exploda do outro lado `[TIMING]` | D3 | D3, D6 | não |
| M55 | Harp contra Pols Voice | Usar a Harp na sala | D3 | D3 | não |
| M56 | Armos | Acordar com botão ou interruptor e matar com bombas | D3 | D3 | não |
| M57 | Tiles voadores | Sobreviver até o fim (desviar, bloquear ou golpear) `[TIMING]` | D3 | D3, D8 | não |
| M58 | Seed Shooter | Mirar em 8 direções e atirar; a semente ricocheteia em paredes (fontes). Gesto de mira: segurar o botão e girar com o direcional (`não confirmado`) | D3 | D3 a D8, OW 4, Veran | não |
| M59 | Tocha ou Candlehead à distância | Seed Shooter com Ember Seed | D3 | D3, D5, D6, D8 | não |
| M60 | Barra giratória e alavanca de ponte | Mudar o ângulo da barra com o interruptor e atirar para a semente ricochetear até a alavanca | D3 | D3 | não |
| M35 | Tune of Currents | Usar a Harp em qualquer lugar do passado para ir ao presente | OW 4 | OW 4, OW 5, OW 6, D6 | não |
| M77 | Cerimônia de Patch | Mini-jogo (seção 6) | OW 4 | OW 4 | não |
| M76 | Entregar ou encaixar item | Falar com o personagem, ou apertar A de frente para o altar, com o item no inventário | OW 3 (corda de Rafton) | OW 3 a OW 8, D8 (Slates) | sim (falar), se o diálogo bastar |
| M62 | Lava | Não tocar; cair dá dano alto e volta à entrada da sala | D4 | D4, D8 | não |
| M65 | Blade trap | Provocar e passar enquanto recolhe, ou pular `[TIMING]` | D4 | D4, D6, D7, D8, OW 8 | não |
| M66 | Caminho que cobre todos os tiles | Andar uma rota exata, sem repetir tile | D4 | D4, D8 | não |
| M67 | Tiro de dentro do carrinho | Seed Shooter enquanto o carrinho anda `[TIMING]` | D4 | D4, OW 6 (Target Carts) | não |
| M68 | Travessia cronometrada depois de alavanca | Puxar a alavanca e cruzar antes de a lava voltar `[TIMING]` | D4 | D4, D8 | não |
| M63 | Switch Hook | Atirar o gancho num diamante, vaso ou arbusto; Link troca de lugar com o alvo | D4 | D4 a D8, OW 5, OW 6, OW 7, Nayru, Veran | não |
| M64 | Diamante até botão | Várias trocas seguidas para levar o diamante ao botão | D4 | D4, D5, D6, D7, D8 | não |
| M69 | Pegasus Seed | Usar a semente para correr; com a Feather, salto longo `[TIMING]` | OW 5 | OW 5, D5, OW 6, Veran (opcional) | não |
| M70 | Devolver bombas | Levantar a bomba do inimigo e arremessar de volta `[TIMING]` | OW 5 (Great Moblin) | OW 5 | não |
| M71 | Pilares vermelhos e azuis | Acertar o cristal para trocar quais estão altos; subir junto atirando de cima de pilares baixos | D5 | D5, D8 | não |
| M74 | Três estátuas-olho | Acertar as três com sementes em pouco tempo `[TIMING]` | D5 | D5 | não |
| M75 | Defletores giratórios | Atirar quando o defletor aponta para a tocha `[TIMING]` | D5 | D5 | não |
| M72 | Cane of Somaria | Criar um bloco à frente; empurrar; serve de peso, degrau, trava e sonda. Só existe um bloco por vez | D5 | D5, D6, D8, OW 7 (opcional) | não |
| M73 | Piso invisível | Seguir uma rota fixa, ou sondar com um bloco da Cane | D5 | D5, OW 7 (biblioteca), OW 8 | não |
| M78 | Goron Dance | Mini-jogo (seção 6) | OW 6 | OW 6 (duas vezes) | não |
| M79 | Target Carts | Mini-jogo (seção 6) | OW 6 | OW 6 | não |
| M88 | Galeria de tiro dos Gorons | Mini-jogo (seção 6) | OW 6 | OW 6 | não |
| M89 | Big Bang Game | Mini-jogo (seção 6) | OW 6 | OW 6 | não |
| M87 | Ação no passado muda o presente | Fazer algo numa época e conferir na outra | OW 3 (Scent Seedling) | OW 3, OW 4, D6 | não |
| M80 | Mermaid Suit | Em água funda, apertar o direcional várias vezes para nadar; B emerge (SW); o botão de mergulho não é dito pelas fontes; debaixo d'água só o item do botão A funciona (ZD-6) | D6 | D6, D7, D8, OW 7, OW 8 | não |
| M90 | Passar sem ser visto | Andar fora da linha de visão dos guardas `[TIMING]` | OW 7 | OW 7 | não |
| M36 | Tune of Ages | Usar a Harp em qualquer lugar para trocar de época nos dois sentidos | OW 7 | OW 7, OW 8, final | não |
| M81 | Nível da água | Pisar nos botões que enchem ou esvaziam os andares, na ordem certa | D7 | D7 | não |
| M83 | Long Hook | Switch Hook com alcance maior | D7 | D7, D8, Veran | não |
| M82 | Viagem por Gale Seed | Usar a semente pela Satchel e escolher a árvore de destino no mapa (`não confirmado`) | OW 8 | OW 8 | não |
| M84 | Power Glove | Levantar estátuas grandes; puxar as mãos de Ramrock | D8 | D8 | não |
| M85 | Piso de gelo | Andar e lutar escorregando | D8 | D8 | não |
| M86 | Correnteza com buracos | Nadar contra a corrente para não ser sugado `[TIMING]` | D8 | D8 | não |

O id M61 não é usado. O roteiro de cada chefe, incluindo Nayru possuída, está dentro de M22.

A tabela segue a ordem de primeira necessidade por trecho; dentro do mesmo trecho a ordem das linhas é aproximada.

**Prioridade para a dungeon 1:** M16, M18, M19, M20, M22 (Giant Ghini e Pumpkin Head), M23, M12, M24, M25, M27, M28, M29.

**Prioridade seguinte (até a dungeon 2):** M31, M32, M33, M34, M37, M38, M43, M39, M40, M41, M42.

## 6. Mini-jogos e trechos que dependem de tempo

### 6.1 Mini-jogos obrigatórios

| Id | Jogo | Onde | Regras | Custo | Prêmio obrigatório | Fonte |
| --- | --- | --- | --- | --- | --- | --- |
| — | Jogo das fadas | Fairies' Woods, P | Não tem tempo. Achar três fadas escondidas seguindo uma rota de telas | Grátis | Acesso à área da D2; `GLOBALFLAG_WON_FAIRY_HIDING_GAME` | ZD-2 |
| M50 | Wild Tokay | Crescent Island, A (parede explodida com bomba) | A carne cai no centro da sala. Levantar e arremessar para cada Tokay que passa pelas laterais. Deixar um passar perde `[TIMING]` | 10 Rupees por tentativa | Scent Seedling na primeira vitória | ZD-3, SW Minigames |
| M77 | Cerimônia de Patch | Restoration Wall, A | Pisar no botão faz aparecer quatro Hardhat Beetles. Derrubar todos nos buracos antes de o carrinho bater na Tuni Nut. ZD-4: atrair os besouros para perto de um buraco, pular por cima deles com a Feather e empurrá-los. SW: o carrinho não bate enquanto Link está no botão `[TIMING]` | Não informado | Tuni Nut restaurada | ZD-4, SW Minigames |
| M78 | Goron Dance | Rolling Ridge Base, P e A | Ouvir o ritmo e repetir: B move, A segura a pose. 8 rodadas; vence com 6 certas; três erros eliminam `[TIMING]` | 10 Rupees (P), 20 (A) | Brother Emblem (P); Mermaid Key (A, com a carta) | SW Minigames, ZD-6 |
| M79 | Target Carts | Rolling Ridge, P | Seed Shooter de dentro de um carrinho em movimento; 12 alvos; só a pontuação perfeita dá o prêmio `[TIMING]` | 10 Rupees | Rock Brisket | SW Minigames, ZD-6 |
| M88 | Galeria de tiro dos Gorons | Rolling Ridge, A | Golpear com a espada bolas lançadas para acertar alvos; 10 lançamentos. Fada +100, azul +30, vermelho −10, diabrete −50, erro −50. Mais de 100 pontos `[TIMING]` | 20 Rupees | Lava Juice | SW Minigames, ZD-6 |
| M89 | Big Bang Game | Rolling Ridge, P | Piso que se move em várias direções; bombas caem e explodem rápido, em número crescente. Desviar até o tempo acabar; uma explosão perde. Pegasus Seed e Feather ajudam `[TIMING]` | Primeira vez grátis, depois 10 Rupees | Old Mermaid Key | SW Minigames, ZD-6 |

O Shooting Gallery de Lynna Village só é obrigatório para quem quer Ricky. O Treasure Chest da loja é opcional.

### 6.2 Trechos obrigatórios que dependem de tempo, fora dos mini-jogos

| Trecho | O que exige | Id |
| --- | --- | --- |
| D1 `04:16`, `04:15` | Subir e descer de plataforma móvel | M20 |
| D1 `04:12` | Atravessar antes de o Wallmaster cair | M28 |
| D2 | Thwomp em sala lateral; alavanca de trilho durante o percurso; bomba no rosto vermelho do Head Thwomp | M43, M37, M22 |
| D3 | Tiros com ricochete; Shadow Hag de costas | M58, M60, M22 |
| OW 4 | Pedras que caem na Restoration Wall | M01 |
| D4 | Plataformas sobre lava; interruptor móvel; tiro de dentro do carrinho; blade traps; alavanca de lava; Armos Warrior e Eyesoar | M20, M58, M67, M65, M68, M22 |
| OW 5 | Piso que some no Keep; bombas do Great Moblin; salto longo | M69, M70 |
| D5 | Três estátuas-olho; defletores; bola do Smasher | M74, M75, M22 |
| OW 7 | Guardas do jardim; Nayru possuída | M90, M22 |
| D7 | Lâminas giratórias; Plasmarine | M65, M22 |
| OW 8 | Blade traps da sala da coragem | M65 |
| D8 | Troca de carrinho; correnteza; alavanca de lava; orbes do Blue Stalfos; formas 2 e 4 de Ramrock | M37, M86, M68, M22 |
| Final | Semente no momento em que Veran para; forma final | M22 |

Para um agente de decisões discretas, a cópia headless ajuda: uma rota de inputs que funciona na cópia funciona igual no emulador principal (ADR 0001). Isso cobre os trechos de tempo fixo. Os mini-jogos de ritmo (Goron Dance) e de reação a eventos aleatórios (Wild Tokay, Big Bang) pedem um controlador próprio.

## 7. Perguntas em aberto

**Fontes que divergem**

1. **Octogon, na superfície.** ZD-6 usa o Seed Shooter no rosto. SW diz que só a espada na boca aberta funciona. Conferir em `object_code/ages/enemies/octogon.s`.
2. **Nayru possuída e Veran fase 1.** ZD-7 fala em três acertos; SW fala em repetir duas vezes.
3. **Smog.** ZD-5 usa só a Cane; SW também empurra blocos e fala em quatro destruições.
4. **Ramrock forma 3.** ZD-8 diz Scent Seeds; SW não diz o tipo. Forma 4: SW usa a Cane para travar a bola.
5. **Ordem das Slates e uso da alavanca de lava na D8.** ZD-8 e SW dão ordens diferentes para os mesmos quatro lugares.
6. **Sala das chamas e Turret da Black Tower.** As duas fontes descrevem a rota de modos diferentes.
7. **Lava Juice.** ZD-6 pega antes da Old Mermaid Key; SW pega depois. SW diz que a troca do Lava Juice pela carta exige a Old Mermaid Key.
8. **Nomes.** O DIS usa `TREASURE_ROCK_BRISKET` e `TREASURE_GORON_LETTER`; SW escreve "Rock Sirloin"; as duas fontes chamam a carta de "Letter of Introduction". O texto da ROM não foi conferido.
9. **Segundo puzzle de caminho da D4 e sequência do cubo da D6.** As rotas das duas fontes não batem.

**Não confirmado**

10. **O que o agente já faz em dungeon.** O pedido diz que ele não abre baús nem usa Small Keys, mas ele atravessou a Maku Path do passado, que segundo ZD-1 exige botão, baú, Small Key e porta trancada. Vale conferir no log como ele passou antes de implementar M16, M18 e M19 do zero. O mesmo vale para M12 (tochas da caverna da Graveyard Key).

11. **Terceira porta trancada da D1.** A porta de cima da `04:1d` aparece como trancada só no SW. A conta fecha com três chaves e três portas, mas os tiles de porta não foram lidos no DIS (`data/ages/tile_properties/keydoorTiles.s` e os layouts de sala).
12. **Entradas de Mermaid's Cave.** O DIS dá `01:0e` para `05:26` (índice `$06`, script só de mini-boss) e `03:0f` para `05:44` (índice `$0c`, script de boss). As fontes dizem que o mini-boss fica no presente e o boss no passado. Falta conferir qual grupo é qual época e como o grupo `03` entra nisso.
13. **Bits de `wEssencesObtained`.** Não foi conferido se o bit é o número da dungeon menos um.
14. **Wallmaster fora da D1.** Só a D1 foi lida sala por sala.
15. **Itens levados em Crescent Island.** A lista vem do passo a passo de ZD-3. O DIS não foi lido para confirmar quais tesouros são removidos e se as bombas ficam.
16. **Hero's Cave.** ZD-1 a trata como conteúdo de jogo ligado. A entrada `00:48` para `04:ce` existe no DIS; não foi conferido o que a bloqueia no jogo não ligado.
17. **Fim do jogo não ligado.** ZD-9 e SW dizem que os créditos vêm depois de Veran. O DIS não foi lido para confirmar.
18. **Posição do navio pirata** no Sea of Storms: nenhuma fonte dá.
19. **Regras exatas** não informadas pelas fontes: duração do Big Bang Game, janela de tempo das três estátuas-olho, vida dos chefes, custo da cerimônia de Patch, botões da galeria de tiro.
20. **Rupees.** O caminho obrigatório gasta pelo menos 300 (poção), mais as entradas dos mini-jogos dos Gorons e do Wild Tokay. Nenhuma fonte soma o total nem indica a melhor forma de juntar.
21. **Salas das dungeons 2 a 8.** Só a D1 tem ids de sala. As outras têm só entrada, baú do item e mecânicas.

**Fontes não alcançadas:** zelda.fandom.com, GameFAQs, Zelda Universe, ZeldaXtreme (respondeu, mas não foi lido) e Zelda Wiki (respondeu ao `curl`, mas não foi lido). As estratégias de chefe foram cruzadas só entre Zelda Dungeon e StrategyWiki, as duas pelo Internet Archive.
