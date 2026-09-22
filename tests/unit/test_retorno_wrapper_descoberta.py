# -*- coding: utf-8 -*-
"""A descoberta do wrapper do retorno com a memoria do BANCO (CONTROLE_FONTE_RET=banco).

Roda o bloco DESCOBERTA_RET do run_agendado.sh em `sh` (dash, como o hub), com um
`python` falso no lugar da consulta ao banco: quando ele responde, a lista de md5 e a
memoria; quando falha (exit 1), o wrapper volta ao CSV e diz. O md5 e o de modo texto
(\\r removido), igual ao que o job grava no banco.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

WRAPPER = Path(__file__).resolve().parents[2] / "src/processors/web/retorno_cobranca/run_agendado.sh"


def _md5_texto(dados: bytes) -> str:
    return hashlib.md5(dados.replace(b"\r", b"")).hexdigest()


def _preparar(tmp_path):
    arvore = tmp_path / "Retornos" / "22" / "MoneyPlus"
    arvore.mkdir(parents=True)
    velho = b"0" * 400 + b"\r\n" + b"1" * 400 + b"\r\n"
    novo = b"0" * 400 + b"\r\n" + b"2" * 400 + b"\r\n"
    (arvore / "VELHO.RET").write_bytes(velho)
    (arvore / "NOVO.RET").write_bytes(novo)
    (tmp_path / "entrada").mkdir()
    controle = tmp_path / "controle.csv"
    controle.write_text("arquivo,hash\nVELHO.RET," + _md5_texto(velho) + "\n", encoding="utf-8")
    return arvore, controle, _md5_texto(velho), _md5_texto(novo)


def _rodar(tmp_path, fonte, python_falso, arvore, controle):
    s = WRAPPER.read_text()
    bloco = s.split("# BEGIN DESCOBERTA_RET\n", 1)[1].split("# END DESCOBERTA_RET\n", 1)[0]
    script = (python_falso + "\n"
              f'ARVORE_RET="{tmp_path / "Retornos"}"; DIAS_RET=3; ENTRADA_RET="{tmp_path / "entrada"}"; '
              f'CONTROLE_RET="{controle}"; TEM_PASTA=0; CONTROLE_FONTE_RET="{fonte}"\n'
              + bloco + 'cat "$PASTAS_RET"; rm -f "$PASTAS_RET"\n')
    r = subprocess.run(["sh", "-c", script], env={**os.environ, "TMPDIR": str(tmp_path)},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_csv_padrao_acha_so_o_arquivo_novo(tmp_path):
    arvore, controle, _, _ = _preparar(tmp_path)
    saida = _rodar(tmp_path, "csv", "python() { echo NAO-DEVIA-CHAMAR >&2; return 1; }", arvore, controle)
    assert "fonte BANCO" not in saida
    assert saida.strip().splitlines()[-1] == str(arvore), "uma pasta com novidade (NOVO.RET)"


def test_banco_responde_e_a_lista_dele_mais_o_csv_e_a_memoria(tmp_path):
    arvore, controle, md5_velho, md5_novo = _preparar(tmp_path)
    # o banco conhece os DOIS: nada e novidade
    falso = f"python() {{ echo {md5_velho}; echo {md5_novo}; return 0; }}"
    saida = _rodar(tmp_path, "banco", falso, arvore, controle)
    assert "controle: fonte BANCO (2 md5 registrados) + historico do CSV" in saida
    assert str(arvore) not in saida


def test_banco_sem_historico_ainda_respeita_o_csv(tmp_path):
    """O banco so conhece o que entrou desde 21/09/2026: o VELHO (so no CSV) nao pode virar
    novidade — e o NOVO, que nao esta em lugar nenhum, tem de aparecer."""
    arvore, controle, md5_velho, md5_novo = _preparar(tmp_path)
    saida = _rodar(tmp_path, "banco", "python() { return 0; }", arvore, controle)   # banco vazio
    assert "controle: fonte BANCO (0 md5 registrados) + historico do CSV" in saida
    assert saida.strip().splitlines()[-1] == str(arvore), "so o NOVO.RET e novidade"


def test_banco_indisponivel_volta_ao_csv_e_diz(tmp_path):
    arvore, controle, _, _ = _preparar(tmp_path)
    saida = _rodar(tmp_path, "banco", "python() { return 1; }", arvore, controle)
    assert "fonte BANCO indisponivel" in saida and "CSV de reserva" in saida
    assert saida.strip().splitlines()[-1] == str(arvore)
