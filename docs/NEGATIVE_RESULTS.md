# Resultados negativos

Resultados negativos sao resultados validos (regra do projeto). Cada
entrada aqui documenta uma hipotese/tecnica que NAO funcionou como
esperado, com dados, para nao repetir a mesma tentativa sem saber.

---

## 2026-09 -- Reescrita de arquivo inteiro por ciclo causa regressao

**Tarefa:** `py_debug_001` (bug silencioso de escala em `apply_discount`,
3 testes, 1 falhando na fixture original).

**Configuracao:** Qwen3-4B via llama-swap, `iterative` com
`think_budget=400`, `continue_budget=150`, `max_cycles=5`. Protocolo de
acao: `write_file` sempre recebe o conteudo **completo** do arquivo
(sem diff/patch parcial).

**O que aconteceu:** o agente reescreveu `src/orders.py` inteiro em 2
ciclos diferentes (ciclos 2 e 3). O resultado final tinha **2 testes
falhando** (antes eram so 1) -- `format_price` passou a devolver
`"19.90"` em vez de `"$19.90"`, e `total_price` tambem quebrou.
Custou 2025 tokens e 547s (9 chamadas ao modelo).

**Comparacao no mesmo experimento:**

| estrategia | passou | tokens | tempo | chamadas |
|---|---|---|---|---|
| no_think | nao | 347 | 193.6s | 1 |
| think (budget 800) | **sim** | 758 | 452.5s | 1 |
| iterative (400/150, 5 ciclos) | nao (regrediu) | 2025 | 547.3s | 9 |

**Hipotese descartada (nesta configuracao):** que ciclos curtos +
estado externo compensam a janela de contexto pequena. Aqui, o
mecanismo de edicao (reescrita total por ciclo, sob orcamento curto
de 400 tokens) foi a causa provavel da regressao -- cada reescrita e
uma nova chance de "esquecer" uma funcao que ja estava correta. A
chamada unica com orcamento generoso (`think`) nao tem esse problema
porque so escreve o arquivo uma vez.

**Nao concluir ainda:** que a hipotese central do projeto esta errada.
So testamos 1 tarefa, 1 seed, 1 combinacao de budgets, e com um
mecanismo de edicao ingenuo (write_file de arquivo inteiro). O proximo
teste obrigatorio antes de descartar qualquer coisa: um `patch_file`
que edita so o trecho necessario, comparado de novo.

**Dados brutos:** `results/py_debug_001.jsonl` (registro retroativo,
`recorded_retroactively: true`).

---

## 2026-09 -- patch_file evita a regressao, mas o modelo nunca le o arquivo antes de "corrigir"

**Tarefa/config:** mesma acima, trocando so `write_file` por `patch_file`
(mesmos budgets: 400/150, 5 ciclos).

**O que aconteceu:** o modelo NUNCA chamou `read_file src/orders.py` em
nenhum dos 5 ciclos. A partir da mensagem de falha do pytest sozinha,
ele **alucinou** a assinatura da funcao (`def apply_discount(price,
discount):` -- nomes e indentacao errados) e uma formula que nem
contém o bug real. Tentou o mesmo `OLD`/`NEW` errado nos ciclos 2, 3,
4 e 5, **identico byte a byte todas as vezes**, apesar de receber o
mesmo erro "OLD nao encontrado" toda vez -- nunca tentou `read_file`
para conferir o texto exato.

**Resultado:** `patch_file` rejeitou as 4 tentativas (`OLD` nunca bateu
no arquivo real) -- **zero alteracoes aplicadas**. O estado final
ficou identico ao inicial (1 teste falhando, o mesmo de sempre). Sem
regressao (diferente do `write_file`), mas tambem sem progresso.
Custou 2272 tokens e 692s (10 chamadas) -- mais caro que a versao
`write_file`.

**Leitura:** `patch_file` funcionou como trava de seguranca (evitou
que uma edicao as cegas quebrasse algo), mas isso NAO testa H2 de
forma limpa ainda -- o modelo nunca teve a chance de patchar
corretamente porque nunca olhou o arquivo. O framing atual (estado
compacto = so a saida do pytest, sem o conteudo do arquivo) nao
instrui nem pressiona o modelo a fazer `read_file` antes de editar.

**Proximo passo (nao e H2 ainda -- e um pre-requisito pra testar H2
de verdade):** ou (a) instruir explicitamente no prompt "leia o
arquivo antes de tentar corrigi-lo", ou (b) incluir o conteudo do
arquivo relevante por padrao no estado do primeiro ciclo, e so ai
comparar write_file vs patch_file de novo.

**Dados brutos:** `results/py_debug_001.jsonl`, ultima linha
(`strategy: iterative_patch`) -- esta com `generations` completo,
nao retroativo.

