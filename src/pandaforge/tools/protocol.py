"""
Protocolo textual de acao para a estrategia iterativa.

Deliberadamente NAO e JSON estrito: um Qwen3-4B erra formatacao JSON
com frequencia sob pressao de orcamento curto. Em vez disso, um bloco
<action>...</action> com campos CAMPO: valor, faceis de extrair por
regex mesmo com pequenas variacoes de espacamento.

Uma falha de parsing aqui NAO derruba o experimento -- vira uma
observacao ("erro de formato") que volta pro proximo ciclo, e tambem
uma metrica (quantidade de erros de formato do estado, como previsto
desde o inicio do projeto).

Duas ferramentas de edicao, para testar H2 (docs/HYPOTHESES.md):
  - write_file  -- reescreve o arquivo INTEIRO (mecanismo original,
                   que causou a regressao documentada em NEGATIVE_RESULTS.md)
  - patch_file  -- substitui um trecho (OLD -> NEW), exigindo que OLD
                   apareca exatamente uma vez -- mesmo criterio do
                   memory_str_replace/str_replace usados neste proprio
                   projeto de desenvolvimento.

Cada execucao da estrategia iterative usa UMA das duas (edit_tool),
nunca as duas ao mesmo tempo -- isolar a variavel e o ponto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ACTION_RE = re.compile(r"<action>(.*?)</action>", re.DOTALL | re.IGNORECASE)
_TOOL_RE = re.compile(r"^\s*TOOL:\s*(\w+)\s*$", re.MULTILINE | re.IGNORECASE)
_PATH_RE = re.compile(r"^\s*PATH:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_CONTENT_RE = re.compile(r"^\s*CONTENT:\s*\n(.*)", re.DOTALL | re.MULTILINE | re.IGNORECASE)
_OLD_NEW_RE = re.compile(r"OLD:\s*\n(.*?)\nNEW:\s*\n(.*)", re.DOTALL | re.IGNORECASE)

VALID_TOOLS = {"read_file", "run_tests", "write_file", "patch_file", "done"}

TOOL_INSTRUCTIONS_WRITE = """\
Ferramentas disponiveis (escolha exatamente UMA por resposta):

  read_file  -- le um arquivo. Requer PATH.
  run_tests  -- roda a suite de testes do projeto. Nao requer PATH nem CONTENT.
  write_file -- sobrescreve um arquivo POR COMPLETO. Requer PATH e CONTENT
                (o conteudo INTEIRO do arquivo, nunca um diff/patch parcial).
  done       -- declara que voce terminou. Nao requer PATH nem CONTENT.

Termine sua resposta com EXATAMENTE um bloco de acao, neste formato
exato (sem blocos de markdown, sem crases):

<action>
TOOL: nome_da_ferramenta
PATH: caminho/relativo (omita se a ferramenta nao usa)
CONTENT:
conteudo completo do arquivo aqui (omita se a ferramenta nao usa; se
presente, deve ser a ULTIMA coisa dentro do bloco <action>)
</action>
"""

TOOL_INSTRUCTIONS_PATCH = """\
Ferramentas disponiveis (escolha exatamente UMA por resposta):

  read_file  -- le um arquivo. Requer PATH.
  run_tests  -- roda a suite de testes do projeto. Nao requer PATH nem CONTENT.
  patch_file -- substitui um TRECHO do arquivo (nunca o arquivo inteiro).
                Requer PATH, OLD e NEW. OLD precisa ser uma copia EXATA
                (mesma indentacao, mesmas quebras de linha) de um trecho
                que aparece UMA UNICA VEZ no arquivo -- inclua linhas de
                contexto suficientes para isso. NEW e o texto que substitui
                OLD. NUNCA copie o arquivo inteiro em OLD/NEW -- so o
                trecho que precisa mudar.
  done       -- declara que voce terminou. Nao requer PATH nem CONTENT.

Termine sua resposta com EXATAMENTE um bloco de acao, neste formato
exato (sem blocos de markdown, sem crases):

<action>
TOOL: nome_da_ferramenta
PATH: caminho/relativo (omita se a ferramenta nao usa)
OLD:
trecho exato a ser substituido (so para patch_file)
NEW:
texto que substitui o trecho acima (so para patch_file; deve ser a
ULTIMA coisa dentro do bloco <action>)
</action>
"""

# mantido por compatibilidade com codigo/scripts anteriores
TOOL_INSTRUCTIONS = TOOL_INSTRUCTIONS_WRITE


class ActionParseError(Exception):
    pass


@dataclass
class Action:
    tool: str
    path: str | None = None
    content: str | None = None   # write_file: conteudo inteiro; patch_file: NEW
    old: str | None = None       # so patch_file: OLD


def parse_action(text: str) -> Action:
    m = _ACTION_RE.search(text)
    if not m:
        raise ActionParseError("nenhum bloco <action>...</action> encontrado na resposta")
    block = m.group(1)

    tool_m = _TOOL_RE.search(block)
    if not tool_m:
        raise ActionParseError("campo TOOL: ausente dentro do bloco <action>")
    tool = tool_m.group(1).strip().lower()
    if tool not in VALID_TOOLS:
        raise ActionParseError(f"ferramenta desconhecida: {tool!r} (validas: {sorted(VALID_TOOLS)})")

    path_m = _PATH_RE.search(block)
    path = path_m.group(1).strip() if path_m else None

    content = None
    old = None

    if tool == "patch_file":
        on_m = _OLD_NEW_RE.search(block)
        if on_m:
            old = on_m.group(1).rstrip("\n")
            content = on_m.group(2).rstrip("\n")
    else:
        content_m = _CONTENT_RE.search(block)
        content = content_m.group(1).rstrip("\n") if content_m else None

    if tool == "read_file" and not path:
        raise ActionParseError("read_file requer PATH")
    if tool == "write_file" and (not path or content is None):
        raise ActionParseError("write_file requer PATH e CONTENT")
    if tool == "patch_file" and (not path or old is None or content is None):
        raise ActionParseError("patch_file requer PATH, OLD e NEW (nesta ordem)")

    return Action(tool=tool, path=path, content=content, old=old)


# ---------------------------------------------------------------------
# Protocolo "simple" -- calibrado para modelos pequenos (ex.: 0.8B).
#
# Motivacao (ver docs/NEGATIVE_RESULTS.md): no qwen3.5:0.8b, o protocolo
# <action>/TOOL:/PATH:/CONTENT: acima quebrou quase sempre -- o modelo
# nao conseguia fechar a tag, nem preencher todos os campos. Duas
# apostas de design aqui:
#   1) menos campos: comandos de UMA linha ("ACAO: ferramenta arg"),
#      sem tag de abertura/fechamento para read_file/run_tests/done;
#   2) sintaxe mais familiar: para editar, marcadores de conflito estilo
#      git (<<<<<<< / ======= / >>>>>>>) em vez de OLD:/NEW: inventados
#      -- aposta de que aparecem MUITO mais em dados de treino (merges
#      de git) do que qualquer esquema de tags proprio deste projeto.
#
# So oferece patch (nao write_file inteiro) -- reescrever o arquivo
# todo em uma linha de comando nao faz sentido neste formato.
# ---------------------------------------------------------------------

_SIMPLE_ACAO_RE = re.compile(r"^\s*ACAO:\s*(\w+)(?:\s+(\S+))?\s*$", re.MULTILINE | re.IGNORECASE)
_SIMPLE_PATCH_RE = re.compile(r"<{3,}\s*\n(.*?)\n={3,}\s*\n(.*?)\n>{3,}", re.DOTALL)

SIMPLE_VALID_TOOLS = {"read_file", "run_tests", "patch", "done"}

SIMPLE_TOOL_INSTRUCTIONS = """\
Ferramentas disponiveis (escolha exatamente UMA por resposta):

  ACAO: read_file <caminho>   -- le um arquivo
  ACAO: run_tests             -- roda a suite de testes do projeto
  ACAO: patch <caminho>       -- troca um trecho de um arquivo (formato abaixo)
  ACAO: done                  -- declara que voce terminou

Para read_file, run_tests e done, escreva SO a linha "ACAO: ...".

Para patch, escreva a linha "ACAO: patch <caminho>" e, logo abaixo, o
trecho antigo e o novo, separados por marcadores de conflito (como um
conflito de merge do git):

ACAO: patch src/exemplo.py
<<<<<<<
texto exato que existe hoje no arquivo, so o trecho que muda
=======
texto novo que substitui o texto acima
>>>>>>>

So UMA acao por resposta.
"""


def parse_action_simple(text: str) -> Action:
    m = _SIMPLE_ACAO_RE.search(text)
    if not m:
        raise ActionParseError("nenhuma linha 'ACAO: <ferramenta>' encontrada na resposta")
    tool = m.group(1).strip().lower()
    arg = m.group(2).strip() if m.group(2) else None

    if tool not in SIMPLE_VALID_TOOLS:
        raise ActionParseError(
            f"ferramenta desconhecida: {tool!r} (validas: {sorted(SIMPLE_VALID_TOOLS)})"
        )

    if tool == "read_file":
        if not arg:
            raise ActionParseError("read_file requer um caminho na mesma linha")
        return Action(tool="read_file", path=arg)

    if tool in ("run_tests", "done"):
        return Action(tool=tool)

    # tool == "patch"
    if not arg:
        raise ActionParseError("patch requer um caminho na mesma linha")
    pm = _SIMPLE_PATCH_RE.search(text[m.end():])
    if not pm:
        raise ActionParseError(
            "bloco <<<<<<< / ======= / >>>>>>> nao encontrado apos 'ACAO: patch'"
        )
    old = pm.group(1).rstrip("\n")
    new = pm.group(2).rstrip("\n")
    return Action(tool="patch_file", path=arg, old=old, content=new)
