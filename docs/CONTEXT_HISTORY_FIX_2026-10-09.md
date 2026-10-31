# Repeticao do piloto apos corrigir historico nativo

## Plano anterior aos dados

Continua `CONTEXT_ABLATION_2026-10-09.md`. O harness executa uma tool por
ciclo, mas ecoava todas as propostas da geracao. Ajuste unico na estrategia:
ecoar somente a primeira tool executada, preservando a lista completa nas
Generation e dados brutos. Sem executar tools adicionais, sem refresh ou
feedback de erro novo. Testar o contrato com backend simulado antes da
inferencia: resposta com uma e duas propostas, uma resposta por id ecoado,
segunda tool nao executada e geracao original intacta.

Pergunta: removido o historico inconsistente, o 0.8B melhora o progresso e
a resolucao, e fonte inicial ainda difere de recuperacao sob demanda?

Manter Qwen3.5 0.8B local/llama-swap/jinja, ctx8192/threads4, thinking
desligado, patch, sem decoys, temperatura0.5/top_p0.9, 500 tokens/chamada,
4 ciclos. Tarefas001/002, seeds20/21, AB/BA por seed como antes. Baseline
de contexto = fonte inicial; variante = `seed_files=[]`. Comparar tambem
descritivamente com as seis observacoes antigas do harness inconsistente,
sem tratar isso como comparacao randomizada: ambiente/cache/tempo variam.

Dois blocos sequenciais de quatro episodios, por tarefa; warm-up separado
por bloco, limite suave de 300s (nao iniciar novos episodios depois dele),
90s por chamada HTTP. Estimativa 3-5min/bloco, episodio iniciado pode
ultrapassar limite. Sem download, instalacao ou inferencia concorrente.
Sucesso = 3/3 ou 5/5 testes, todos os dados/negativos registrados.

Criterio previo: so considerar indicio de ganho se houver mais sucessos
nos pares antigos disponiveis ou mesmo sucesso com menor custo; n=2 por
celula e insuficiente para causalidade. Novas sementes nao serao escolhidas
em funcao de resultados. Se 002 continuar falhando, registrar; nao misturar
correcao de historico com refresh do fonte/feedback pytest.

Runner aceita tarefa/identificador explicitos e grava hash da estrategia
em cada episodio. Audita em cada request real que os ids anunciados no
historico correspondem exatamente aos respondidos; nao modifica payload.
Usa o mesmo probe de RAM ollama-bench e psutil existente.
RSS amostrado e RAM global nao isolam cache/paginacao; CPU e soma de threads
do servidor, excluindo cliente/pytest. Dados novos separados dos antigos.

```powershell
$benchPath = (panda projects path ollama-bench).Trim()
panda py run-project pandaforge scripts/check_native_tool_history.py --timeout 45
panda py run-project pandaforge scripts/run_context_ablation.py --timeout 650 -- --bench-path $benchPath --experiment context-history-fixed-2026-10-09 --tasks py_debug_001 --max-elapsed 300 --output results/context-history-fixed-001-2026-10-09.jsonl
panda py run-project pandaforge scripts/run_context_ablation.py --timeout 650 -- --bench-path $benchPath --experiment context-history-fixed-2026-10-09 --tasks py_debug_002 --max-elapsed 300 --output results/context-history-fixed-002-2026-10-09.jsonl
panda py run-project pandaforge scripts/analyze_context_ablation.py --timeout 45 -- --input results/context-history-fixed-001-2026-10-09.jsonl
panda py run-project pandaforge scripts/analyze_context_ablation.py --timeout 45 -- --input results/context-history-fixed-002-2026-10-09.jsonl
```

## Resultados

O teste simulado falhou no codigo original: o eco continha `read-source`
e `done-unexecuted`, com resposta apenas para read. Apos o ajuste passou,
assim como o controle de uma tool. Todas as propostas continuam no objeto
Generation original. Sem inferencia no teste.

Oito episodios executados (4/4 por bloco), sem episodios ausentes.
Warm-up001=13.10s, warm-up002=0.37s; episodios somaram 436.48s,
aproximadamente 7.5min incluindo warm-ups. Todas as 31 requests reais
passaram na auditoria de ids anunciados/respondidos; quatro geracoes
propuseram duas tools, mas apenas a primeira foi ecoada e executada.
Hash da estrategia unico nos dois blocos (campo native_strategy_sha256).

| tarefa | contexto | sucesso | tokens gerados medios | tempo medio (s) | CPU media servidor (s) | RSS pico medio (MiB) |
|---|---|---:|---:|---:|---:|---:|
| 001 | fonte inicial | 1/2 | 344.5 | 58.4 | 190.0 | 1441.6 |
| 001 | sob demanda | 1/2 | 219.5 | 46.0 | 150.3 | 1530.3 |
| 002 | fonte inicial | 1/2 | 296.0 | 67.6 | 211.6 | 1685.1 |
| 002 | sob demanda | 1/2 | 158.5 | 46.2 | 141.1 | 1582.6 |

Prompt usage acumulado medio por episodio (inclui cache): 5717/4289.5 em
001 e 6594/4193.5 em 002, fonte inicial/sob demanda. RAM global pico menos
inicio medio: 206.7/235.0MiB em 001, 57.3/123.75MiB em 002. CPU soma user+
system dos threads do servidor; nao mede cliente/pytest. RSS variou entre
1285.0 e 1751.2MiB por episodio; todas as sondagens sem erros, mesmo PID
entre os blocos. RAM global inicial variou e estava menor que no piloto
antigo: comparar tempos antes/depois nao isola a correcao de historico.

Resultados por seed:

- 001 seed20: fonte inicial leu fonte/testes, rodou testes e patchou
  corretamente (416 tokens, 67.1s). Sob demanda repetiu testes/fonte por
  quatro ciclos, sem patch (110 tokens, 38.5s), falhou 2 passed/1 failed.
- 001 seed21: sob demanda passou (329 tokens, 53.5s); fonte inicial falhou
  (273 tokens, 49.7s), mudando a formula para multiplicar por 100 em vez
  de remover a divisao por 100. Diagnostico correto nao garantiu fix correto.
- 002 seed20: ambas aplicaram `stock[sku] += qty`, causando KeyError para
  SKU novo, 2 passed/3 failed. Fonte inicial leu/patchou/testou e terminou
  com texto sem tool_call; sob demanda leu/testou/patchou/testou e esgotou
  os ciclos. O caso de borda ainda nao foi considerado mesmo com historico
  de tools valido.
- 002 seed21: ambas resolveram com `stock.get(sku, 0) + qty`, 5/5 testes.
  Sob demanda usou tres chamadas, 165 tokens/42.2s; fonte inicial quatro
  chamadas, 416 tokens/83.8s. Mostra capacidade existente neste exemplo,
  nao frequencia confiavel nem efeito isolado da correcao do harness.

## Comparacao e resultado negativo

No piloto antigo, 001 fonte inicial 2/2 vs sob demanda 1/2; agora ambos
1/2. Nos seis pares de configuracao/seed existentes nos dois pilotos,
antigo acertou 3/6 e corrigido 2/6. O novo sucesso de 002 seed21 em ambos
os contextos nao tinha observacao anterior: nao atribuir esse ganho ao fix.
Nao juntar as amostras: protocolo e ambiente mudaram.

**Negativo:** historico consistente corrige um bug real, mas nao demonstrou
aumento de capacidade ou sucesso nos pares antigos. A vantagem de contexto
inicial observada no piloto anterior nao se repetiu. Sob demanda teve
menores custos medios nos dois blocos, porem em 001 o par seed21 custou mais
que o baseline e as sementes trocaram qual contexto acertava: nenhuma
estrategia domina por seed. Amostra de dois episodios por celula, pistas
explicitas nas fixtures/objetivos e limite de quatro ciclos nao permitem
generalizar eficiencia ou confiabilidade.

## Validacao e reproducao

Os JSONL antigos foram preservados; oito novos registros foram acrescentados
nos historicos das tarefas com hypothesis `context-history-fixed-2026-10-09`.
Resultados dedicados e summaries:
`results/context-history-fixed-001-2026-10-09.jsonl` e `.summary.json`,
`results/context-history-fixed-002-2026-10-09.jsonl` e `.summary.json`.
Cada resultado tem respostas brutas, codigo final, hashes de fixtures/probe/
estrategia e ids de historico realmente enviados. Analyzer valida contra
recorder e garante hash unico, identificador e plano consistente no bloco.
Repeticoes devem usar novos --output e --experiment para distinguir a rodada.

## Proxima pergunta

Testar se devolver automaticamente a falha do pytest ao modelo imediatamente
apos um patch malsucedido melhora recuperacao sob quatro ciclos, em vez de
precisar gastar uma chamada extra de `run_tests`. O harness ja executa esse
teste, mas a observacao enviada depois da edicao diz somente que o trecho
foi substituido, mesmo quando os testes falham. Isolar feedback (sem refresh
automatico do fonte nesta rodada).

Plano proposto: tarefa002, mesmo modelo/budgets/contexto fonte inicial,
baseline corrigido atual vs observacao pos-edicao contendo resultado real
do verificador (sem solucao), seeds20/21/22, AB/BA por seed, seis episodios
sequenciais. Medir sucesso, regressao, recuperacao apos falha, chamadas,
tokens/tempo/CPU/RSS; teto suave de cinco minutos, registrar ausencias.
Validar com backend simulado que o verificador nao roda em duplicata e que
o feedback corresponde ao codigo vigente. Estimativa 5-8 minutos para a
comparacao; nao executada nesta continuacao.
