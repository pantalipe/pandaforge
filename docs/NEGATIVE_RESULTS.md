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

---

## 2026-09 -- Bug no proprio harness: parser exigia crases que o prompt nao pedia

**Tarefa:** `py_debug_002` (nova -- bug silencioso de sobrescrita em
`apply_transactions`, requer rastrear varias transacoes em sequencia
para perceber; 5 testes, 2 falhando na fixture original).

**O que aconteceu:** ao generalizar `single_shot.py` para tarefas
multi-arquivo, a instrucao do prompt passou a pedir "um bloco de
codigo comecando com `# file: <caminho>`" sem exigir explicitamente
as crases (` ``` `) ao redor. O regex de extracao exigia as crases.
Tanto `no_think` quanto `think` **diagnosticaram e corrigiram o bug
corretamente** na resposta (confirmado lendo o campo `content` bruto
no JSONL), mas nao envolveram a resposta em crases -- entao nada foi
extraido, nada foi aplicado, e o resultado registrado foi FALHA, ainda
que o modelo tivesse acertado.

**Correcao:** prompt agora mostra o formato exato com um exemplo
completo (crases incluidas); o regex de extracao ficou tolerante a
crases ausentes (ancora em `# file:` e para no proximo `# file:`, na
crase de fechamento, ou no fim do texto -- o que vier primeiro).

**Licao:** um resultado "FALHOU" no JSONL pode ser falha do harness,
nao do modelo -- antes de registrar qualquer coisa como evidencia
contra uma hipotese, vale conferir o `content` bruto da geracao, nao
so o veredito do pytest.

---

## 2026-09 -- Teste calibrado de H1: nem think nem iterative resolvem sob orcamento apertado

**Tarefa:** `py_debug_002`. Calibracao previa (budget generoso, 1200):
`think` precisou de 903 tokens pra ter sucesso -- entao usamos
`think_budget=400` (abaixo do necessario) como o primeiro teste
genuinamente justo de H1: sera que `iterative`, com o MESMO orcamento
por ciclo, consegue terminar onde o single-shot e forcado a cortar?

**think (budget=400):** cortou no meio de um docstring (`stop_type=
'limit'`), gerando um arquivo com string nao fechada -- `SyntaxError`
na coleta dos testes. FALHA real por esgotamento de orcamento, nao
um artefato do harness. 400 tokens, 132.1s.

**iterative+patch (budget=400, continue=200, 5 ciclos, com seed e
verificacao automatica):** no ciclo 1, o modelo diagnosticou o
problema certo (sobrescrita em vez de soma) mas implementou o fix
ERRADO -- trocou `stock[sku] = qty` por `stock[sku] += qty`, que
lanca `KeyError` na primeira vez que um SKU aparece (`+=` exige que a
chave ja exista; faltou o `.get(sku, 0)`). Isso **regrediu** de 2
testes falhando para 3. A verificacao automatica detectou
corretamente que nao passou e continuou o loop; nos ciclos 2-5 o
modelo tentou reaplicar patches com um `OLD` que ja nao batia mais
(mesmo padrao de nao reler o arquivo apos uma mudanca, ja visto
antes) e nunca corrigiu o proprio erro. FALHOU, pior que o estado
inicial. 2499 tokens, 840.0s, 10 chamadas.

**Comparacao:**

| estrategia | passou | tokens | tempo |
|---|---|---|---|
| think (budget 400, forcado a cortar) | nao (SyntaxError) | 400 | 132.1s |
| iterative+patch (budget 400/ciclo) | nao (regrediu) | 2499 | 840.0s |

**Leitura para H1:** este e o primeiro teste onde `think` genuinamente
falha por orcamento (nao por preguica de formato ou tarefa facil
demais) -- e `iterative` TAMBEM falhou, custando 6x mais tokens e
tempo, e piorando o estado em vez de so nao progredir. Diferente do
resultado anterior "iterative bate think" (`py_debug_001`), que veio
de parar cedo numa tarefa facil, aqui nao ha vantagem nenhuma de
iterative -- ate agora, H1 nao tem evidencia a favor em NENHUM teste
onde a comparacao foi genuinamente justa (budget forcado abaixo do
necessario). O ciclo curto (400 tokens) parece insuficiente para o
modelo considerar o caso de borda (SKU novo) mesmo tendo diagnosticado
a causa raiz certa -- sugere que o problema pode nao ser so "quantos
tokens de thinking cabem", mas a qualidade do raciocinio dentro de um
orcamento tao curto.

**Dados brutos:** `results/py_debug_002.jsonl`.

---

## 2026-09 -- Em 0.8B, o gargalo do iterative deixa de ser raciocinio e vira formato

**Modelo:** `qwen3.5:0.8b` (novo -- integrado ao llama-swap para
comparar capacidade entre tamanhos de modelo). **Tarefa:**
`py_debug_001`, mesmos budgets usados no 4B (400/200, ate 6 ciclos,
patch_file).

**Comparacao com o 4B na mesma tarefa:**

| estrategia | 4B | 0.8B |
|---|---|---|
| no_think | passou | falhou (diagnostico errado) |
| think (800) | passou | falhou (cortou no limite, 800/800 tokens, sem convergir) |
| iterative+patch | passou | falhou (protocolo de acao quebrado) |

**O que aconteceu no iterative:** dos 6 ciclos, so 1 (ciclo 3) produziu
um bloco `<action>` valido -- e foi um `run_tests`, nunca uma edicao.
Os outros 5: ciclo 1 (400 tok, cortado) sem bloco `<action>` nenhum;
ciclo 2 (so 24 tokens, terminou sozinho) tambem sem bloco; ciclos 4 e 5
tentaram `patch_file` mas sem os campos `OLD`/`NEW` completos; ciclo 6
(17 tokens) sem bloco de novo. Nenhuma edicao foi sequer TENTADA de
forma valida -- o arquivo nunca mudou, entao tambem nao houve
regressao (diferente do 4B com write_file).

**Leitura:** no 4B, o gargalo do iterative era qualidade do raciocinio
dentro do orcamento (diagnostico certo, fix incompleto). Em 0.8B, o
gargalo e mais basico -- o modelo nao consegue seguir de forma
confiavel um protocolo estruturado (tags, campos obrigatorios) sob
pressao de orcamento curto. Isso sugere que H1 (ciclos curtos +
estado externo) tem um piso de capacidade do modelo abaixo do qual
nao faz sentido testar -- a estrategia certa muda de "como estruturar
o raciocinio" para "o modelo consegue nem seguir instrucoes de
formato". Para modelos deste porte, um protocolo mais tolerante (ou
ainda mais simples que `<action>`/`TOOL:`/`PATH:`) provavelmente
precisa vir antes de testar H1 de verdade.

**Bug de harness corrigido no caminho:** o `no_think`/`think` desse
modelo tambem expos um bug real -- o exemplo de formato no prompt
usava um placeholder generico (`caminho/exato/mostrado/acima.py`), e
o modelo pequeno **copiou o placeholder ao pe da letra** como se fosse
um caminho real, derrubando o script inteiro (`FileNotFoundError`
nao tratado). Corrigido: o exemplo agora usa um caminho REAL da
propria tarefa, e `_finish()` ignora (em vez de travar em) qualquer
caminho extraido que nao exista entre os arquivos-fonte da tarefa.

**Dados brutos:** `results/py_debug_001.jsonl` (linhas com
`model: qwen3.5:0.8b`).

---

## 2026-09 -- Protocolo mais simples NAO ajudou o 0.8B (piorou, levemente)

**Hipotese testada:** um protocolo de acao com menos campos (comandos
de uma linha "ACAO: ferramenta arg") e sintaxe mais familiar
(marcadores de conflito estilo git em vez de OLD:/NEW: inventados)
ajudaria um modelo de 0.8B a seguir o formato de forma mais confiavel
que o protocolo `<action>`/`TOOL:`/`PATH:` original.

**Resultado:** NAO ajudou -- piorou levemente. Mesma tarefa
(`py_debug_001`), mesmo modelo (`qwen3.5:0.8b`), mesmos budgets
(400/200, 6 ciclos):

| protocolo | passou | tokens | tempo | acoes validas |
|---|---|---|---|---|
| structured (`<action>`/TOOL:/PATH:) | nao | 1233 | 189.8s | 1 de 6 |
| simple (`ACAO:` + `<<<<<<<`/`=======`/`>>>>>>>`) | nao | 1836 | 221.6s | 0 de 6 |

**Modo de falha diferente e interessante:** no protocolo simples, o
modelo emitiu corretamente a linha `ACAO: patch src/orders.py` em
varios ciclos (confirmando que a sintaxe reduzida FOI seguida
parcialmente), mas parou logo em seguida (12 tokens, `stop_type=
'eos'`) sem escrever o bloco `<<<<<<<`/`=======`/`>>>>>>>` que
deveria vir a seguir -- como se o modelo "achasse" que a linha de
comando sozinha ja fosse uma acao completa, sem perceber que precisa
continuar escrevendo o conteudo do patch logo abaixo. Nos ciclos que
usaram o orcamento inteiro (400+200), o modelo as vezes nem emitiu a
linha `ACAO:` nenhuma.

**Leitura:** reduzir o numero de campos obrigatorios NAO resolve o
problema de fundo neste tamanho de modelo -- o gargalo nao parece ser
"campos demais para lembrar", e sim uma dificuldade mais basica de
manter uma estrutura de varias partes (comando + bloco de conteudo)
coerente dentro de uma unica resposta curta. Precisa de mais
evidencia antes de generalizar, mas o resultado aponta para um teto
de capacidade que um protocolo mais simples, sozinho, nao resolve --
talvez precise de few-shot no proprio prompt (um exemplo completo
preenchido, nao so a descricao do formato) ou de um budget maior por
ciclo especificamente para este modelo.

**Dados brutos:** `results/py_debug_001.jsonl` (linha
`strategy: iterative_simple_patch`).

---

## 2026-09 -- Padrao do 0.8B se confirma na py_debug_002

Repeti as 3 estrategias com `qwen3.5:0.8b` na `py_debug_002` (tarefa
diferente, mais dificil) para checar se a falha generalizada era
especifica da `py_debug_001`. NAO era -- o padrao se repete:

| estrategia | py_debug_001 | py_debug_002 |
|---|---|---|
| no_think | falhou (diagnostico errado) | falhou (`SyntaxError`: `return` fora de funcao -- indentacao quebrada ao reescrever o arquivo inteiro) |
| think (800) | falhou (cortou, 800/800) | falhou (cortou, 800/800, nao convergiu) |
| iterative+patch (400/200, 6 ciclos) | falhou (1 de 6 acoes validas) | falhou (**0 de 6** acoes validas -- todos os 6 ciclos deram erro de formato) |

**Leitura:** em nenhuma das 2 tarefas o `qwen3.5:0.8b` teve sucesso em
nenhuma das 3 estrategias. O padrao "iterative piora com tarefa mais
complexa" tambem se confirma: 1/6 acoes validas na tarefa mais facil
vira 0/6 na mais dificil (prompt de estado maior, mais texto pra
processar por ciclo). Isso reforca a leitura anterior: existe um piso
de capacidade do modelo abaixo do qual a pergunta de pesquisa central
do projeto (contexto/budget/iteracao) nao se aplica ainda -- o gargalo
e mais basico que isso.

**Dados brutos:** `results/py_debug_002.jsonl` (linhas com
`model: qwen3.5:0.8b`).


