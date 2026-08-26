# -*- coding: utf-8 -*-
"""Robo que INSERE o retorno CNAB 240 de pagamento no Smart (da baixa).

Tela: Financeiro > Sistemas de pagamento > Pagamento BMP Money Plus > Processar
Retorno (`financeiro/pagtobmp/retornopagtobmp.php`). NAO e a mesma coisa que o
`robo_retorno`, que trata do retorno de COBRANCA (`financeiro/retornoocorrencia.php`)
— outra arvore de menu, outro form, outro risco.

Le o `.RET` que o `baixar_retorno_pagamento.py` (process-automation) ja baixou do
Money Plus e publicou no Nextcloud; sobe esse arquivo nesta tela.

Entrypoint agendado: `run_agendado.sh` (display :93).
"""
