"""Exercita a descoberta real do wrapper, sem iniciar Chrome ou acessar o Smart.

O Banco do Brasil entrega .ret; o MoneyPlus entrega .RET. Ambos precisam
chegar ao mesmo consumidor, preservando janela, nomes e deduplicacao.
"""

import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "src/processors/web/retorno_cobranca/run_agendado.sh"
SHELLS = [shell for shell in ("sh", "dash", "bash") if shutil.which(shell)]


def descobrir(tmp_path, shell, *args):
    texto = WRAPPER.read_text(encoding="utf-8")
    trecho = texto[texto.index('ARVORE_RET='):texto.index('# 8) roda o robo')]
    script = tmp_path / "descobrir.sh"
    script.write_text(
        "set -u\n" + trecho
        + '\ntrap \'rm -f "$PASTAS_RET"\' EXIT\ncat "$PASTAS_RET"\n',
        encoding="utf-8",
    )
    resultado = subprocess.run(
        [shell, str(script), *args],
        env={
            "PATH": os.defpath,
            "ARVORE_RETORNO_RET": str(tmp_path / "Retornos"),
            "PASTA_ENTRADA_RET": str(tmp_path / "entrada"),
            "ARQ_CONTROLE_RET": str(tmp_path / "controle.csv"),
            "DIAS_RETORNO_RET": "3",
        },
        capture_output=True, text=True, timeout=10, check=True,
    )
    return set(resultado.stdout.splitlines())


def arquivo(tmp_path, relativo, conteudo=b"retorno\r\n"):
    caminho = tmp_path / relativo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


@pytest.mark.parametrize("shell", SHELLS)
def test_descobre_bb_e_money_sem_renomear(tmp_path, shell):
    bb = arquivo(tmp_path, "Retornos/09/Banco do Brasil/PROSPERE - CBR643.ret")
    mp = arquivo(tmp_path, "Retornos/09/MoneyPlus/CAST - CP0909.RET")
    arquivo(tmp_path, "Retornos/09/Banco do Brasil/OUTRA - CBR644.ReT")
    arquivo(tmp_path, "Retornos/09/Outro/arquivo.REM")
    assert descobrir(tmp_path, shell) == {str(bb.parent), str(mp.parent)}
    assert bb.exists() and mp.exists()


@pytest.mark.parametrize("shell", SHELLS)
def test_entrada_classica_aceita_minusculo_sem_descer_subpasta(tmp_path, shell):
    entrada = arquivo(tmp_path, "entrada/CBR.ret")
    arquivo(tmp_path, "entrada/_PROCESSADOS/velho.RET")
    assert descobrir(tmp_path, shell) == {str(entrada.parent)}


@pytest.mark.parametrize("shell", SHELLS)
def test_preserva_janela_e_hash_com_quebras_normalizadas(tmp_path, shell):
    conhecido = arquivo(tmp_path, "Retornos/09/Banco do Brasil/CBR.ret")
    digest = hashlib.md5(conhecido.read_bytes().replace(b"\r", b"")).hexdigest()
    (tmp_path / "controle.csv").write_text(f"hash,processado\n{digest},True\n")
    velho = arquivo(tmp_path, "Retornos/01/MoneyPlus/antigo.RET", b"antigo\n")
    antes = time.time() - 7 * 86400
    os.utime(velho, (antes, antes))
    assert descobrir(tmp_path, shell) == set()
    novo = arquivo(tmp_path, "Retornos/09/Banco do Brasil/novo.ret", b"novo\n")
    assert descobrir(tmp_path, shell) == {str(novo.parent)}


@pytest.mark.parametrize("shell", SHELLS)
def test_pasta_explicita_preserva_escolha_do_operador(tmp_path, shell):
    arquivo(tmp_path, "Retornos/09/MoneyPlus/CP0909.RET")
    assert descobrir(tmp_path, shell, "--pasta", "/pasta/escolhida") == set()
