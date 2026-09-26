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

Atualizacao (py_debug_002, teste calibrado de verdade): usamos a
calibracao do proprio `think` (precisou de 903 tokens pra ter sucesso
com budget generoso) pra escolher `think_budget=400` -- ABAIXO do
necessario -- como primeiro teste genuinamente justo: sera que
`iterative`, com o MESMO orcamento por ciclo, resolve onde o
single-shot e forcado a cortar? `think` cortou de fato (SyntaxError,
arquivo truncado). `iterative` (patch, seed, verificacao automatica)
TAMBEM falhou -- pior ainda, REGREDIU (3 testes falhando em vez de
2), porque o ciclo 1 diagnosticou a causa raiz certa mas implementou
um fix incompleto (`+=` sem tratar SKU novo) sob pressao do orcamento
curto, e os ciclos seguintes nunca corrigiram isso. Custou 2499 tokens
e 840s contra 400 tokens e 132s do `think` que so falhou (nao
regrediu). Ver `docs/NEGATIVE_RESULTS.md` para o detalhe completo.

**Conclusao parcial, 2 tarefas testadas:** H1 tem UM resultado a favor
(py_debug_001, mas que veio de "parar cedo economiza", nao de
"iterar ajuda a pensar melhor") e UM resultado claramente contra
(py_debug_002, no teste mais justo ate agora -- budget forcado abaixo
do necessario). A hipotese, na forma atual, NAO esta se sustentando:
quando o orcamento por ciclo e curto o bastante pra realmente cortar
o raciocinio do single-shot, o MESMO orcamento curto tambem nao da
pro `iterative` raciocinar bem o suficiente por ciclo -- ele so
acumula erros ao longo de varios ciclos em vez de um so. Precisa de
mais tarefas/seeds antes de declarar H1 falsificada, mas o padrao ate
agora aponta nessa direcao.

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
