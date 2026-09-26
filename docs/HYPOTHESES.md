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

Atualizacao: com `patch_file` + seed automatico de `read_file`,
`iterative` tambem PASSOU nesta tarefa -- entao agora `think` e
`iterative` (bem configurado) empatam em sucesso, mas `iterative`
custou ~3x mais tokens e tempo. ATE AGORA, nenhuma configuracao de
`iterative` testada supera `think` em sucesso/custo -- ainda nao ha
evidencia PRO H1 nesta tarefa, so evidencia de que e possivel igualar
`think` com mais engenharia (seed, patch cirurgico). H1 precisa de
uma tarefa onde `think` genuinamente falhe (estoura o budget antes de
concluir) para ter chance de mostrar vantagem.

---

## H2 (mecanismo de edicao)

> Um protocolo de edicao cirurgico (patch/diff parcial) reduz tanto o
> custo por ciclo quanto o risco de regressao, comparado a reescrever
> o arquivo inteiro a cada ciclo.

**Criterio de falsificacao:** rodar `iterative` com um `patch_file`
(em vez de `write_file` de arquivo inteiro) na mesma tarefa e mesmos
budgets; se o resultado nao melhorar em nenhuma das duas dimensoes
(sucesso, tokens), a hipotese cai.

**Status:** H2 CONFIRMADA nesta tarefa, com ressalva de eficiencia.
Adicionando um "seed" automatico (`read_file` do arquivo relevante
ANTES do ciclo 1, sem depender do modelo escolher isso) eliminou a
alucinacao: `patch_file` corrigiu o bug real corretamente no ciclo 1
e o resultado final passou em todos os testes, sem regressao --
diferente de `write_file`, que passou (nesta forma) a nao regredir
tambem, mas custou mais caro. Ressalva: os ciclos 2-5 desperdicaram
chamadas tentando reaplicar o MESMO patch (ja aplicado, `OLD` nao
batia mais) porque o agente nunca chamou `run_tests` para perceber
que ja tinha terminado -- custou 2282 tokens / 716s / 10 chamadas
para um resultado que, com um `done`/`run_tests` mais oportuno,
poderia ter custado a fracao do ciclo 1 sozinho (~230 tokens, ~175s).
Ver `docs/NEGATIVE_RESULTS.md` para o historico completo (regressao
sem seed -> patch seguro mas hesitante sem seed -> sucesso com seed).

---

## H3 (compressao de estado)

> Estado estruturado (objective/hypothesis/evidence/next_action) supera
> historico completo em tarefas onde o historico completo estouraria o
> orcamento de contexto -- com perda de desempenho mensuravel, mas
> aceitavel, em troca de caber no contexto.

**Status:** NAO TESTADA AINDA. `iterative` hoje usa "estado + ultimas
observacoes" (janela das ultimas 6 entradas do log), nao um dos
formatos estruturados da lista original. Falta comparar as variantes.
