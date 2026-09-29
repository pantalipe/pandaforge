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
