# Hipoteses

Cada hipotese tem um criterio de falsificacao explicito, definido
ANTES de olhar os dados que a testam.

---

## H1 (central)

> Um modelo pequeno com reasoning limitado, estado externo e ciclos
> iterativos pode resolver tarefas que o mesmo modelo, usando
> `/no_think` ou uma unica janela de reasoning, nao consegue resolver
> dentro dos mesmos recursos computacionais.

**Criterio de falsificacao:** se, numa amostra razoavel de tarefas
(varias categorias, varios seeds), `iterative` nunca supera `think`
nem em taxa de sucesso nem em sucesso/custo, a hipotese cai nesta
forma e precisa ser revista (por exemplo: talvez o ganho so apareca
com um mecanismo de edicao mais cirurgico, ou so em tarefas mais
longas que py_debug_001).

**Status:** EM TESTE. Primeiro dado (py_debug_001, 1 tarefa, 1 seed):
`think` > `no_think` (confirma parte da motivacao -- thinking ajuda
quando ha budget suficiente). `iterative` com write_file de arquivo
inteiro ficou PIOR que `think` em sucesso e custo -- ver
`docs/NEGATIVE_RESULTS.md`. Amostra pequena demais pra decidir
qualquer coisa sobre H1 em si; o resultado ate agora fala mais sobre
o MECANISMO DE EDICAO do que sobre a hipotese central.

**Conclusao parcial, 2 tarefas testadas (dados de 1 execucao):** H1
tinha UM resultado a favor (py_debug_001, mas que vinha de "parar
cedo economiza", nao de "iterar ajuda a pensar melhor") e UM
resultado claramente contra (py_debug_002, no teste mais justo ate
entao -- budget forcado abaixo do necessario). Baseado em 1 execucao
por celula, a hipotese parecia nao se sustentar.

**Atualizacao decisiva (py_debug_001, qwen3:4b E qwen3.5:2b, 5
sementes por celula):** a comparacao de 1 execucao era enganosa por
falta de amostra. Com 5 sementes:

| modelo | no_think | iterative+patch (seed + verificacao automatica) |
|---|---|---|
| qwen3:4b | **0/5** (0%), 350 tok, 127.4s | **5/5** (100%), 674 tok, 199.2s |
| qwen3.5:2b | 4/5 (80%), 314 tok, 60.7s | 4/5 (80%), 2166 tok, 338.6s |

No `qwen3:4b`, `no_think` FALHA de forma consistente (nao e sorte --
e 0 em 5, sempre com o mesmo numero exato de tokens, sugerindo que o
modelo converge pro mesmo raciocinio raso raso independente da
semente) e `iterative` ACERTA de forma consistente (5 em 5), custando
menos do que o dobro dos tokens. **Esta e a primeira evidencia
robusta (multi-seed) a favor de H1** -- mas com uma ressalva
importante: no `qwen3.5:2b`, que ja acerta 80% via `no_think` sozinho,
`iterative` nao melhora a taxa de sucesso (mesma 4/5) e custa ~7x mais
tokens. Ou seja: **o beneficio do `iterative` parece concentrado em
modelos onde a estrategia direta falha de forma consistente** -- ele
nao e uma melhoria universal, e pode ser puro desperdicio quando
`no_think` ja funciona bem.

**Licao metodologica:** os resultados de 1 execucao anteriores
(incluindo a "conclusao parcial" acima, baseada em py_debug_002 com 1
seed) devem ser tratados como preliminares ate serem repetidos com
varias sementes -- o padrao mudou de "H1 nao se sustenta" para "H1 se
sustenta condicionalmente" so ao adicionar amostra.

**Proximo passo:** repetir py_debug_002 (a tarefa mais dificil) com 5
sementes nos mesmos 2 modelos, pra confirmar se o padrao "iterative
ajuda so quando no_think falha consistentemente" se mantem numa
tarefa onde ja vimos os dois falharem.

---

## H2 (mecanismo de edicao)

> Um protocolo de edicao cirurgico (patch/diff parcial) reduz tanto o
> custo por ciclo quanto o risco de regressao, comparado a reescrever
> o arquivo inteiro a cada ciclo.

**Criterio de falsificacao:** rodar `iterative` com um `patch_file`
(em vez de `write_file` de arquivo inteiro) na mesma tarefa e mesmos
budgets; se o resultado nao melhorar em nenhuma das duas dimensoes
(sucesso, tokens), a hipotese cai.

**Status:** H2 CONFIRMADA nesta tarefa. `patch_file` + seed automatico
corrigiu o bug real corretamente, sem regressao. A ressalva de
eficiencia (ciclos desperdicados sem checar o proprio trabalho) foi
resolvida com verificacao automatica pos-edicao no harness -- ver
atualizacao em H1 acima: resultado final 456 tokens / 126.6s /
2 chamadas, batendo `write_file` E `think` nas duas dimensoes.

---

## H3 (compressao de estado)

> Estado estruturado (objective/hypothesis/evidence/next_action) supera
> historico completo em tarefas onde o historico completo estouraria o
> orcamento de contexto -- com perda de desempenho mensuravel, mas
> aceitavel, em troca de caber no contexto.

**Status:** NAO TESTADA AINDA. `iterative` hoje usa "estado + ultimas
observacoes" (janela das ultimas 6 entradas do log), nao um dos
formatos estruturados da lista original. Falta comparar as variantes.

---

## H4 (tamanho do espaco de decisao)

> Expor tools irrelevantes a tarefa (decoys) junto das tools reais
> degrada desempenho e/ou custo do `iterative`, comparado ao mesmo
> modelo/budget/tarefa vendo so as tools relevantes -- mesmo quando as
> decoys nunca sao, de fato, a escolha certa.

**Motivacao:** originou da auditoria de arquitetura do `/pask`
(`panda-home-bot`), que expoe 12 tools de uma vez, sempre, mesmo
quando a pergunta so precisa de uma. `iterative` hoje so testa 4 tools,
todas relevantes -- nao ha espaco de decisao inflado pra observar esse
efeito.

**Criterio de falsificacao:** rodar a mesma tarefa/modelo/budget com
(a) as 4 tools reais e (b) as 4 reais + N decoys plausiveis pro
contexto de debugging (ex.: `run_lint`, `git_blame`, `search_docs`,
`format_code` -- reais o bastante pra tentar, mas que sempre retornam
"nao aplicavel a esta tarefa" se chamadas, custando um ciclo de
verdade). Se accuracy e custo (tokens, tempo, ciclos ate `done`) forem
estatisticamente indistinguiveis entre (a) e (b), a hipotese cai --
decision space nao importa nessa faixa de tamanho.

**Metrica nova (alem das ja coletadas):** taxa de escolha de decoy por
ciclo.

**Isolamento da variavel:** mesmo protocolo de saida (`<action>` de
`protocol.py`, inalterado), mesmo modelo, mesmo budget, mesma tarefa --
so o TAMANHO do menu de tools muda entre (a) e (b).

**O que precisa ser construido:** hoje `VALID_TOOLS`/
`TOOL_INSTRUCTIONS_*` em `tools/protocol.py` sao fixos (4 tools
hardcoded). Precisa parametrizar para aceitar uma lista de decoys
injetada nas instrucoes (e em `VALID_TOOLS`, senao um decoy chamado
vira erro de parsing em vez de "escolha real disponivel mas invalida
pra essa tarefa" -- o que mudaria o que esta sendo medido).

**Status:** NAO TESTADA AINDA. Prioridade: media -- depende de
parametrizar `protocol.py`, que hoje assume um conjunto fixo de tools.

---

## H5 (mecanismo de saida: tool-calling nativo vs protocolo de texto)

> Tool-calling nativo (JSON estruturado via `tools=`/`tool_choice=` no
> endpoint `/v1/chat/completions`, formatado pelo chat template real do
> modelo) produz escolha de ferramenta mais acertada e mais rapida que
> o protocolo de texto `<action>` customizado (`tools/protocol.py`), no
> mesmo modelo/budget/conjunto de tools.

**Motivacao:** essa e a pergunta central da auditoria de arquitetura
do `/pask` (Arquitetura A -- tool calling tradicional -- vs B --
structured command + harness). `/pask` ja usa tool-calling nativo em
producao; `iterative` usa o protocolo de texto proprio, escolhido
deliberadamente porque JSON estrito falhava no Qwen3-4B sob budget
curto (ver docstring de `protocol.py`). H5 testa essa escolha de design
de forma controlada, com verificacao objetiva (pytest), em vez de so
inferir de experiencia em producao.

**Criterio de falsificacao:** se a taxa de "acao valida no 1o parse" e
o custo (tokens, tempo) forem iguais ou piores no tool-calling nativo
comparado ao protocolo `<action>`, a hipotese cai -- e reforca a
decisao de design ja documentada em `protocol.py`.

**Pre-requisito de engenharia (achado em 2026-09-29, ver
`panda-home-bot/docs/pask-tool-calling-jinja-fix.md`):**

1. `LlamaServerBackend.chat()` (`backend/llama_server.py`) ainda NAO
   aceita `tools=`/`tool_choice=` nem le `message.tool_calls` do
   retorno -- so e usado hoje como baseline de `no_think`. Precisa
   estender pra isso (espelhando o que `panda-home-bot/pagent/loop.py`
   ja faz manualmente fora do PandaForge) e escrever uma nova
   estrategia (`strategies/native_tools.py`, analoga a
   `iterative.py`).
2. **`--jinja` e obrigatorio** no `llama-swap` para o modelo usado
   neste teste. Confirmado empiricamente no `/pask`: sem `--jinja`, o
   `llama-server` usa um chat template generico que NAO popula
   `message.tool_calls` -- a intencao de chamar a tool fica presa como
   texto cru em `reasoning_content`, mesmo quando o modelo decidiu
   corretamente. Testar H5 sem `--jinja` no modelo do experimento
   enviesaria o resultado contra o tool-calling nativo por um motivo
   de configuracao, nao pela hipotese em si. Hoje NENHUM modelo
   exclusivo do PandaForge (`qwen3.5:0.8b`, `qwen3.5:2b`, `qwen3:1.7b`,
   `deepseek-r1-distill-qwen:1.5b`) tem `--jinja` no
   `C:\llama.cpp\config.yaml` -- precisa habilitar no(s) modelo(s)
   escolhido(s) para este teste antes de rodar.

**Isolamento da variavel:** mesmo modelo, mesmo budget, mesmo conjunto
de tools (as 4 reais, sem decoys) -- so o MECANISMO de saida muda
entre `<action>` de texto e `tools=` nativo. Rodar H5 antes de cruzar
com H4 (protocolo x tamanho do menu), para nao confundir as duas
variaveis no mesmo resultado.

**Status:** NAO TESTADA AINDA. Prioridade: alta -- responde
diretamente a pergunta que motivou a auditoria do `/pask`, mas exige
mais trabalho de harness que H4 (novo backend + nova estrategia,
alem do `--jinja`).

**Atualizacao 2026-09-29 (engenharia + smoke test):**
`backend/llama_server.py::chat()` estendido com `tools=`/`tool_choice=`
e `Generation.tool_calls`; nova estrategia `strategies/native_tools.py`
implementada, espelhando `iterative.py` (mesmos seeds, mesmo
`edit_tool`, mesmos `decoy_tools`, mesma logica de auto-check pos-
edicao). Schemas nativos ficam em `tools/protocol.py::tool_schemas_for()`,
reaproveitando as descricoes de `DECOY_TOOLS` -- H4 e H5 usam o mesmo
"menu" de decoys por construcao.

**Achado critico durante o smoke test:** `chat()` NAO tem o truque de
"corte no orcamento + continuacao forcada" que `complete()` tem em
`iterative.py`. Primeira tentativa (thinking ligado, `max_tokens=300`,
py_debug_001, decoys=3): as duas chamadas bateram `finish_reason=
'length'` ainda pensando, sem nunca emitir `tool_calls` -- o ciclo
inteiro se perdeu (`n_format_errors=2`, tarefa nao resolvida). Isso
NAO e evidencia de que tool-calling nativo "erra mais"; e uma
assimetria de engenharia entre as duas estrategias que precisa ser
controlada antes de comparar.

Mitigacao aplicada: `run_native_tools(..., disable_thinking=True)`,
que passa `chat_template_kwargs: {"enable_thinking": False}` (mesmo
mecanismo ja usado para Qwen3.5+ no resto do projeto). Reteste
identico com essa flag: **passou de primeira**, `n_format_errors=0`,
`n_decoy_calls=0`, **84 tokens totais e ~92s** -- contra 356 tokens e
~230s da mesma tarefa/decoys/edit_tool rodada em `iterative.py` (ver
commit do smoke test de H4). Amostra de n=1 em cada lado, nao prova
nada sozinha, mas e um resultado forte o suficiente para priorizar
rodar a bateria de sementes de H5 com `disable_thinking=True` como
configuracao padrao -- e, se quiser isolar so o efeito do
tool-calling nativo (sem a variavel de desligar o pensamento),
rodar tambem `iterative.py` com thinking desligado do lado
"structured" para um comparativo mais limpo (`iterative.py` hoje
sempre deixa algum orcamento de pensamento antes da acao).

**TODO em aberto:** dar a `chat()`/`native_tools.py` um mecanismo de
continuacao equivalente ao de `complete()`, para o caso
`disable_thinking=False` nao ficar estruturalmente em desvantagem
quando alguem quiser medir native tool-calling COM thinking ligado.
