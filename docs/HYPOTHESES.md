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

Atualizacao: com `patch_file` + seed automatico de `read_file` +
verificacao automatica pos-edicao (o harness roda pytest sozinho
apos qualquer edicao bem-sucedida e encerra o loop se passar, em vez
de depender do modelo lembrar de chamar run_tests), `iterative` PASSOU
com 456 tokens / 126.6s / 2 chamadas -- MENOS que `think` (758 tokens
/ 452.5s / 1 chamada) nas duas dimensoes. Primeira evidencia real a
favor de H1 nesta tarefa. Ressalva importante: o ganho aqui veio de
engenharia do HARNESS (parar assim que o objetivo real e atingido),
nao de o modelo "raciocinar melhor" em ciclos -- ainda nao isolamos
se a vantagem persiste numa tarefa onde o modelo realmente precisa
de mais de 1 ciclo de edicao pra chegar la (aqui, o patch correto saiu
de primeira, no ciclo 1). H1 continua precisando de uma tarefa mais
dificil pra ser testada de forma que realmente distinga "iterar
ajuda a pensar" de "parar cedo economiza".

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
