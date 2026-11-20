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
| CI em Windows, Ubuntu e macOS | Workflow escrito. Ainda não rodou no GitHub. |
| Supervisor: contrato, orçamento, fallback | Implementado e testado. |
| Supervisor: comparação das três condições com checkpoints reservados | Não feita. |
| Agente: percepção de inimigos, combate, HP, inventário | Não implementado. O levantamento só evita rotas que causam dano. |
| Critérios A01 a A13 em Windows e Linux | Não executados. |
