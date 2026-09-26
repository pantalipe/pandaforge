"""
Framing comum da tarefa py_debug_001 para as 3 estrategias. O texto do
OBJETIVO e o mesmo nos 3 casos -- o que muda entre elas e SO quanto
contexto/mecanismo cada uma tem disponivel para trabalhar nele. Isso
e o que isola o efeito de "ter thinking" e "ter estado externo/loop"
um do outro.
"""

TASK_OBJECTIVE = """\
O projeto Python em src/orders.py tem 3 funcoes: total_price, \
apply_discount e format_price. A suite de testes em \
tests/test_orders.py tem 3 testes; exatamente 1 deles esta falhando.

Objetivo: descubra por que esse teste falha, corrija SOMENTE o bug \
real (nao reescreva as funcoes que ja funcionam), e garanta que os \
3 testes passem.
"""
