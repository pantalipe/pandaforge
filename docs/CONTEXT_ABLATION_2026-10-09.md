# Piloto: codigo inicial vs leitura sob demanda (2026-10-09)

## Plano registrado antes da inferencia

Pergunta: disponibilizar o codigo-fonte automaticamente no primeiro contexto
melhora sucesso/custo comparado a recupera-lo via `read_file`?
Nao testa compressao estruturada de H3 nem isola toda H6.

- Baseline: `run_native_tools`, `seed_files=None` (todos os fontes iniciais),
  igual ao mecanismo da bateria H5; repetir no ambiente atual.
- Variante: somente `seed_files=[]`; arquivos continuam disponiveis via tools.
- Modelo ja instalado: `qwen3.5:0.8b`, llama-swap, `--jinja`, thinking desligado.
- Duas tarefas existentes: `py_debug_001` e `py_debug_002`.
- Seeds novas 20/21 em cada tarefa/condicao; ordem AB/BA por seed.
- Mesmo menu sem decoys, patch, temperatura 0.5, top_p 0.9,
  500 tokens/chamada, 4 ciclos (teto de
  2000 tokens gerados/episodio), mesmos prompts e verificador.
- Sucesso: todos os testes originais passam (3/3 ou 5/5), sem julgamento LLM.
- Warm-up separado; oito episodios sequenciais, sem downloads/instalacoes.
- Piloto estimado em 3-7 minutos; nao iniciar episodios apos 420s,
  timeout HTTP de 90s/chamada. Limite de tempo e suave: o episodio em andamento
  pode terminar depois dele. Registrar bateria incompleta se acontecer.

Criterio anterior aos dados: a vantagem de fornecer o fonte exige mais
sucessos, ou mesmo sucesso com menor tempo/tokens. Se a leitura sob demanda
igualar ou superar o baseline nas duas tarefas sem custo maior, nao ha
evidencia de beneficio do seed automatico neste piloto. Comparacoes por seed
e por tarefa; n=2 por celula nao permite conclusoes estatisticas.

Medicoes: tempo de episodio inclui ferramentas/pytest, tempo por chamada,
tokens gerados e tokens de prompt reportados (nao confundir usage com prefill
sem cache), chamadas/acoes, teste final, codigo final. RAM global reutiliza
`ollama-bench/bench.py:get_ram_used_mb` resolvido no registro atual; psutil ja
instalado mede CPU user+system por PID e pico amostrado de RSS do llama-server
apos warm-up, a cada 0.5s. RSS nao e memoria privada/commit/KV; pico amostrado
pode perder picos curtos, RAM global inclui outros aplicativos. CPU nao inclui
cliente/pytest. Nao comparar RAM atual com historico que nao a media.

Reproducao (PowerShell, sem instalar dependencias):

```powershell
panda projects show pandaforge
panda projects show ollama-bench
$benchPath = (panda projects path ollama-bench).Trim()
panda py run-project pandaforge scripts/run_context_ablation.py --timeout 45 -- --bench-path $benchPath --validate-only
panda py run-project pandaforge scripts/run_context_ablation.py --timeout 850 -- --bench-path $benchPath
```

O script recusa sobrescrever o resultado dedicado existente; para repetir,
usar `--output results/<novo-nome>.jsonl`. Cada episodio tambem e acrescentado
ao JSONL historico da sua tarefa via recorder existente. Fixtures sao copiadas
para temporarios e removidas apos cada episodio; hashes e respostas brutas
ficam no resultado dedicado.
Para auditar uma repeticao, passar o mesmo caminho em
`scripts/analyze_context_ablation.py --input results/<novo-nome>.jsonl`.

## Revisao da evidencia anterior

H1 tem evidencia condicional na tarefa 001: 4B direto 0/5 vs iterative 5/5,
mas nao prova ganho sob custo total igual nem generalizacao. Em 2B, iterative
igualou sucesso direto 4/5 a custo muito maior. Patch protege contra reescrita
e seed + verificacao automatica ajudaram em 001; em 002 houve regressao e
patch repetido contra fonte desatualizado. H4: nenhum decoy em 12 episodios,
apenas para ferramentas semanticamente distintas. H5: 0.8B native_nothink
3/3 vs iterative 0/3 em 001; formato e thinking variaram juntos.
Schemas com `tool_choice=auto` nao demonstram garantia de estrutura pelo
runtime; ausencia de format_errors nao prova argumentos/acoes validos.
`cpu-llm-bench` ja documenta limites AVX1 e falhas dos runtimes low-bit;
trocar/compilar runtime aqui duplicaria pesquisa e nao responde a pergunta.

## Resultados

Seis dos oito episodios planejados foram executados. O limite suave de 420s
impediu iniciar o par seed21 da tarefa 002; nenhum desses episodios ausentes
conta como falha. Tempo de episodios: 464.9s; warm-up separado: 21.45s;
total aproximado de 8.1 minutos. Nao houve download, instalacao ou inferencia
simultanea. Modelo local: `C:/models/qwen3.5-0.8b.gguf`, 811843840 bytes;
runtime `C:/llama.cpp/llama-server.exe`, ctx8192, threads4, `--jinja`.

| tarefa | contexto | sucesso | tokens gerados medios | tempo medio (s) | CPU servidor media (s) | RSS pico medio (MiB) |
|---|---|---:|---:|---:|---:|---:|
| 001 | fonte inicial (baseline) | 2/2 | 336.5 | 87.8 | 230.6 | 1263.7 |
| 001 | sob demanda | 1/2 | 273.0 | 56.9 | 169.3 | 1260.0 |
| 002 | fonte inicial (baseline) | 0/1 | 239.0 | 77.8 | 243.6 | 1490.5 |
| 002 | sob demanda | 0/1 | 168.0 | 97.7 | 221.9 | 1559.5 |

Tokens de prompt reportados medios: 4032.5/3567.5 em 001 e 6232/5535 em
002 (baseline/sob demanda); soma de usage por chamada, nao tokens novos
processados sem cache. RAM global pico menos inicio medio: 322.8/127.7 MiB
em 001 e 113.6/306.2 MiB em 002. Sem erros de psutil, mesmo PID 25060 em
todos os episodios. RSS aumenta com a ordem ao longo da bateria: cache,
estado residente e atividade externa impedem atribuir diferencas pequenas
de RAM ao tratamento. CPU segundos somam varios threads, podendo exceder
tempo de parede. A chamada unica de warm-up excluida nao elimina efeitos
de cache/paginacao entre episodios.

Tracos da PRIMEIRA chamada de tool efetivamente executada por geracao:

- 001 baseline seed20: read fonte -> patch; passou 3/3 testes.
- 001 sob demanda seed20: read testes -> read fonte -> read testes -> read
  fonte; nenhuma edicao, falhou 2/3.
- 001 sob demanda seed21: read fonte -> run_tests -> patch; passou 3/3.
- 001 baseline seed21: read fonte -> read testes -> run_tests -> patch;
  passou 3/3.
- 002 baseline seed20: read fonte -> patch (`stock[sku] += qty`) ->
  run_tests -> repetir o mesmo patch antigo; regrediu para 2 passed/3 failed
  por KeyError em SKU novo. Confirma o modo de falha ja observado no 4B,
  agora no 0.8B nativo sem thinking (nao uma prova de frequencia).
- 002 sob demanda seed20: read fonte -> read testes -> read fonte ->
  resposta sem tool_call; fonte inalterado, 3 passed/2 failed.

**Resultado negativo:** leitura sob demanda nao trouxe melhoria geral de
capacidade ou eficiencia: perdeu um sucesso em 001, e em 002 ambos falharam,
com sob demanda mais lento apesar de gerar menos tokens. Fornecer o fonte
tambem nao resolveu 002 nem evitou regressao. Em 001, o baseline teve mais
sucessos e mais custo; dividir tempo agregado por sucessos da aproximadamente
87.8s/sucesso no baseline vs 113.7s/sucesso sob demanda, incluindo a tentativa
fracassada. Este indicador descritivo de n=2 nao estima confiabilidade futura.

**Limite do harness encontrado na auditoria:** quatro geracoes em quatro
episodios propuseram duas tools. `run_native_tools` executa somente a
primeira, mas ecoa a lista inteira no historico e responde somente ao
primeiro id. A segunda tool nao foi executada. Assim, historico pode ficar
incompleto; custo/efeito desse comportamento nao esta isolado. O problema
afeta as duas condicoes, mas nao permite concluir que recuperacao de contexto
por si so causou as falhas. Nenhuma correcao da estrategia foi misturada no
piloto. Apos a bateria, foi corrigido somente o print do novo runner para
aceitar recursos ausentes, sem mudar prompts ou inferencia.

Fixtures, objetivos e comentarios entregam pistas explicitas do bug;
duas tarefas pequenas nao representam debugging real nem contexto longo.
Ha apenas dois pares em 001 e um em 002, limites de quatro ciclos e custo
de thinking ausente. Nao testa H3 estruturada nem confirma/refuta H1/H6.

Dados e auditoria reproduzivel:
`results/context-seed-ablation-2026-10-09.jsonl`,
`results/context-seed-ablation-2026-10-09.summary.json`, e historicos
`results/py_debug_001.jsonl`/`results/py_debug_002.jsonl` com hypothesis
`context-seed-ablation-2026-10-09`. O resultado dedicado guarda respostas
brutas e codigo final, alem dos hashes de fixtures e do probe reutilizado.

```powershell
panda py run-project pandaforge scripts/analyze_context_ablation.py --timeout 45
```

## Proximo experimento proposto

Antes de expandir sementes, garantir historico valido para chamadas multiplas:
manter apenas a primeira tool no eco do assistente, coerente com a unica
executada, registrando separadamente todas as propostas. Validar esse contrato
com backend simulado (sem LLM) e respostas de uma/duas tools. Depois repetir
este mesmo piloto com seeds20/21, explicitando o novo baseline, mantendo
500 tokens/4 ciclos e demais variaveis. Planejar dois blocos separados por
tarefa de ate 5 minutos cada; pedir autorizacao se for necessario ampliar
tempo/numero de sementes. Somente apos isso testar refresh do fonte e erro
pytest apos patch malsucedido na tarefa 002 (nova variavel, sem misturar com
a correcao de historico).
