# -*- coding: utf-8 -*-
"""
Entrypoint: sobe Chrome com perfil persistente e mantem a sessao viva.

Uso:
    docker exec -e DISPLAY=:99 erp-automation \\
        python -m src.processors.web.boletos.manter_sessao

Ou (em background):
    docker exec -d -e DISPLAY=:99 erp-automation \\
        python -m src.processors.web.boletos.manter_sessao

Este script NAO envia boletos — so mantem o navegador logado e o CDP exposto
para que enviar_lote.py conecte e use os cookies da sessao viva.
"""

from src.processors.web.boletos._sessao import manter_sessao_viva


if __name__ == "__main__":
    manter_sessao_viva()
