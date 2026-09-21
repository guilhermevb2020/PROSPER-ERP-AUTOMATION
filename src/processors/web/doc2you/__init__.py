"""Lógica do robô de download de documentos do Doc2You (Smart Securities).

Portado do robô standalone (Windows). Mantém o parsing/classificação puro
(`classificar`) e os dias úteis (`dias_uteis`); o login/browser/CapSolver vem do
framework do erp-automation (não do `comum.py`/`msvcrt` originais).
"""
