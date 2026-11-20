# Pesquisa: ambiente e adaptador de Oracle of Ages

Consulta: 28/10/2026. Levantamento de fontes primárias e inspeção estática; nenhum jogo, ROM, modelo ou candidato foi executado. As capacidades abaixo são documentadas pelos respectivos projetos, não uma certificação de funcionamento local.

## Conclusão para decisão

Recomendo iniciar com **PyBoy + ROM original + decoder específico de Ages**, usando oracles-disasm como documentação verificável. Um resultado novo relevante é **The Oracles Project**, que já observa o mesmo jogo e oferece código de acesso a dados e documentação de sincronização. Vale estudar esse código antes de escrever o decoder. A existência de reimplementações não exige assumir a manutenção de outra engine para estudar representação textual.

Essa é uma recomendação de arquitetura, não um resultado experimental. Precisamos validar leitura e sincronização em execução antes de escolher campos como confiáveis.

## Jev e Laya: escolha fechada e contexto

- Jev aceita `state` como string, objeto ou array. Separar fatos da observação e pergunta de decisão é a orientação oficial. Inglês é a língua de melhor desempenho documentado. Fonte: [State](https://docs.typesafe.ai/concepts/state).
- `Choice` recebe `criteria` como mapa de identificador para descrição e devolve `choice`, `probabilities` e `confidence`. Isso encaixa diretamente na seleção de uma ação enumerada pelo programa. Fonte: [Choice](https://docs.typesafe.ai/primitives/choice).
- A documentação consultada lista Jev 1.14 e 1.13, endpoint `/v1/systemone`, versões fixas e aliases móveis. Para experimentos, fixar a versão e registrar o modelo efetivo da resposta evita misturar alterações do provedor com alterações do adapter. Fonte: [Models](https://docs.typesafe.ai/models).
- Laya é outro projeto, com código e pesos Apache-2.0, não um modelo publicado pela TypeSafe. Suporta execução local em Python com CPU/MPS/CUDA; o servidor upstream `laya[serve]` implementa `/v1/systemone`. Fonte: [repositório upstream](https://github.com/NandhaKishorM/laya) e [model card](https://huggingface.co/convaiinnovations/laya).
- Os limites de contexto e a definição de confiança diferem. O README upstream documenta 512 tokens por padrão no checkpoint inglês e 1.024 nos outros; multilingual aceita até 8.192 mediante configuração. Não transportar thresholds de confiança entre provedores. Fonte: [README upstream, self-hosting e honest limits](https://github.com/NandhaKishorM/laya#self-hosting-http-server-jev-compatible).

**Implicação proposta:** uma interface própria `Policy.choose(observation, actions)` deve esconder SDK/provedor. Estado compacto e poucas ações descritas são uma base comparável. Jev e Laya precisam ser avaliados nos nossos cenários; benchmarks de tickets não demonstram capacidade de jogar Zelda.

## Candidatos reaproveitáveis

| Projeto | Jogo e papel | Reaproveitamento sugerido | Limite |
|---|---|---|---|
| [PyBoy](https://github.com/Baekalfen/PyBoy) | Emulação GB/GBC em Python | Controle, frames, screenshots, memória e checkpoints | Não entrega sozinho a semântica de Ages; conferir licença própria |
| [oracles-disasm](https://github.com/Stewmath/oracles-disasm) | Disassembly de Ages/Seasons | Símbolos, estruturas, colisões, texto, constantes | Endereços dependem de jogo/versão/banco; não é ambiente Python |
| [The Oracles Project](https://github.com/thibautbus/top) | Ages/Seasons originais em SameBoy/mGBA | Leitores, símbolos gerados e conhecimento de hooks | Núcleo C; não é adapter textual/HTTP de agente pronto |
| [ooa-godot](https://github.com/SHOEGAZEssb/ooa-godot) | Reconstrução de Ages em C#/Godot | Acesso potencial a objetos nativos e prototipagem | Paridade deve ser verificada; dependências e engine adicionais |
| [gameboy-zelda-agent](https://github.com/SASUKE40/gameboy-zelda-agent) | Link’s Awakening DX em PyBoy | Forma de API local e checkpoints | Decoder de outro jogo; licença não identificada na consulta |
| [zelda-rl](https://github.com/I2obiN/zelda-rl) | Link’s Awakening em PyBoy/Gymnasium | Ideias para ambiente, macros e avaliação | RAM e recompensas não transferem diretamente para Ages |
| [Triforce](https://github.com/DarkAutumn/triforce) | Zelda de NES em stable-retro | Modelo de domínio, cenários, fim de episódio e espera por controle | Outro console/jogo e foco em RL; GPL-3.0 |

PyBoy tem [documentação oficial de API](https://docs.pyboy.dk/) para as operações genéricas. Aqui a tarefa específica é transformar bytes em observações e ações de Ages.

### The Oracles Project merece inspeção prioritária

O projeto mantém o jogo original no emulador e acrescenta um host que observa estado. Seu host é MIT; cores e dependências têm licenças próprias. Documenta builds macOS Intel/Apple Silicon, Linux, Windows e Android. Fontes: [README](https://github.com/thibautbus/top), [LICENSE](https://github.com/thibautbus/top/blob/main/LICENSE).

A [arquitetura](https://github.com/thibautbus/top/blob/main/docs/ARCHITECTURE.md) separa core, guest bus e leitores de dados. [core.h](https://github.com/thibautbus/top/blob/main/engine/core/core.h) oferece funções C para aplicar botões, avançar um frame, ler pixels e salvar/restaurar estado. Isso permite conceber outro backend, mas não equivale a um serviço de agente pronto. A [API Lua](https://github.com/thibautbus/top/blob/main/docs/MODDING.md) é voltada a mods, casas e conversas; não assumir que ela já exporte uma observação completa.

Seu [GAME_HOOKS.md](https://github.com/thibautbus/top/blob/main/docs/GAME_HOOKS.md) descreve ordem de atualização e transições. Durante carregamento, o buffer de colisão pode ainda conter a sala anterior ou dados parciais. O host lê em pontos consistentes do frame. Sua documentação de [formatos de dados](https://github.com/thibautbus/top/blob/main/docs/ROM_DATA_FORMATS.md) também deve ser consultada antes de converter mapas. **Inferência:** observar a cada N frames sem checar modo de jogo e transição pode produzir contexto incoerente.

### Agent de Link’s Awakening DX

O [server.py](https://github.com/SASUKE40/gameboy-zelda-agent/blob/main/emulator/server.py) tem `/frame`, `/press`, `/tick` e checkpoints, PyBoy headless e lock para serializar acesso. O mundo avança quando chamado. O decoder de RAM e parte do viewer são específicos de Link’s Awakening. Serve como referência pequena de desenho; a ausência de licença identificável impede tratar cópia como automaticamente autorizada.

### Reimplementação Godot

O [README de ooa-godot](https://github.com/SHOEGAZEssb/ooa-godot/blob/main/README.md) anuncia Ages jogável e Seasons como preview, com Godot/.NET e disassembly fixado. Lançar diretamente em uma sala pula progressão normal e não demonstra equivalência com a versão comercial. **Inferência:** seria útil para cenários controlados, mas usar como ambiente principal adiciona à pesquisa o risco de avaliar comportamento da reconstrução.

## Evidência concreta do disassembly

Inspeção compartilhada do commit `21c924afdc8a13225e849214479d5113da2ec226`:

- [include/wram.s](https://github.com/Stewmath/oracles-disasm/blob/21c924afdc8a13225e849214479d5113da2ec226/include/wram.s): em Ages, grupo em `cc2d`, sala em `cc30`; texto ativo em `cba0`, modo em `cba1`, índice em `cba2` (little-endian, representação incrementada de `0x400`).
- No mesmo arquivo: `wRoomCollisions` em `ce00` e `wRoomLayout` em `cf00`, buffers de `0xc0` bytes com padding; não interpretar como uma grade densa ingênua. `w1Link` está em WRAM banco 1 e usa uma estrutura, não uma posição deduzida de pixels.
- [text/info.txt](https://github.com/Stewmath/oracles-disasm/blob/21c924afdc8a13225e849214479d5113da2ec226/text/info.txt): formato de texto, códigos de controle e substituições. Índice de diálogo não é, por si só, o texto visível completo.
- `Notes/agesCollisions` trata modos de colisão de inimigos; não usar como tabela de passabilidade do terreno. Fonte geral: [árvore do commit](https://github.com/Stewmath/oracles-disasm/tree/21c924afdc8a13225e849214479d5113da2ec226).

São achados estáticos. Validar endereço, banco, versão da ROM, significado dos bits e momento de amostragem durante execução antes de registrar esses campos como ground truth.

## Artigos e referências de método

[Keep CALM and Explore](https://arxiv.org/abs/2010.02903) propõe gerar candidatos compactos de ações em jogos textuais e selecionar entre eles. A ideia de candidatos é relevante; o artigo não fornece decoder para Ages e usa outro arranjo de aprendizagem.

[A Survey on Large Language Model-Based Game Agents](https://arxiv.org/abs/2404.02039) organiza arquiteturas e desafios de agentes em jogos. É leitura de contexto para discutir percepção/memória/ação; não substitui implementação nem validação específica.

Não foi encontrado neste levantamento um adapter textual semântico pronto de Oracle of Ages integrado a Jev/Laya. Isso não prova inexistência. Há infraestrutura exata do jogo e exemplos próximos suficientes para evitar construir um simulador do zero.

## Validação que ainda falta

1. ROM identificada por hash e versão compatível com os símbolos; PyBoy instalado com versão fixa.
2. Jogar manualmente e gravar um checkpoint por cenário: saída, aproximação de NPC, avanço de diálogo.
3. Conferir observação lado a lado com tela em jogo normal, transição e diálogo.
4. Reexecutar a mesma sequência de ações a partir do mesmo checkpoint e comparar estado final.
5. Testar executor com política humana e roteiro fixo antes de atribuir falhas ao modelo.
6. Medir separadamente fidelidade de observação, sucesso de execução, sucesso da decisão, número de decisões e latência. Registrar versão/modelo, representação e histórico.

Não iniciar com planejamento automático de rota até o objetivo: se o executor já escolhe o caminho, o experimento deixa de medir parte da decisão espacial que pretendemos estudar. É possível adicionar esse nível depois, como condição experimental explicitamente diferente.
