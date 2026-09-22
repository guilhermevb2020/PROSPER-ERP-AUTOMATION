#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes da TRAVA DE SOBREPOSICAO do robo de pagamento (`run_agendado.sh`).

POR QUE ESTES TESTES EXISTEM
----------------------------
Este robo roda de 30 em 30 minutos — cadencia que nenhum outro robo deste
container tem. O wrapper mata o Chrome do proprio perfil na largada (e o que
destrava um perfil preso de um run anterior). Sem trava, uma rodada que passe
de 30 min seria MORTA PELA SEGUINTE, possivelmente entre o "gerar" e o "baixar":
a remessa ficaria orfa no Smart — gerada, nao baixada, e invisivel na proxima
rodada porque os itens ja sairam da fila.

O modo de falha nao e hipotese: o `retorno_cobranca` tem dois wrappers no mesmo
perfil e se defende com FOLGA DE HORARIO (`run_deposito.sh`, 10 min antes do
agendado, com o porque escrito la). Folga nao resolve para quem roda a cada
30 min.

O QUE ELES TRAVAM
-----------------
1. Sobreposicao NORMAL sai com 0. Com cron de 30 min, marcar falha a cada
   sobreposicao encheria o hub de alarme falso — e alarme falso diario ensina a
   ignorar o alerta (a mesma licao ja aprendida no `MOTIVOS_BENIGNOS` do
   `retorno_cobranca`).
2. Rodada PRESA sai com 6. E o caso que precisa de gente, e nao pode se
   esconder atras da regra 1.
3. Trava orfa (o processo dono morreu) e removida — senao um `docker kill` no
   meio de uma rodada silenciaria o robo ate alguem apagar o arquivo a mao.
4. O trecho roda em `dash` E em `sh`: o hub chama o wrapper com `sh ...`, e aqui
   `sh` e `dash`. O shebang NAO vale nessa invocacao — foi assim que o
   `${PIPESTATUS[0]}` (bashism) deixou o exit code do robo passar em branco.

COMO ELES FAZEM ISSO
--------------------
Recortam o trecho REAL do `run_agendado.sh`, entre os marcadores `>>> TRAVA` e
`<<< TRAVA`, e o executam. Nao ha copia do codigo aqui: se alguem editar o
wrapper, e o wrapper editado que roda.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
WRAPPER = RAIZ / "src" / "processors" / "web" / "robo_pagamento" / "run_agendado.sh"

INICIO, FIM = "# >>> TRAVA", "# <<< TRAVA"

# O hub chama com `sh`, que neste container e o dash. `bash` entra porque e o que
# uma pessoa usa ao testar a mao — e onde um bashism passaria despercebido.
SHELLS = [s for s in ("dash", "sh", "bash") if shutil.which(s)]


def recortar_trava() -> str:
    """O trecho da trava, tal como esta no wrapper de producao."""
    texto = WRAPPER.read_text(encoding="utf-8")
    assert INICIO in texto and FIM in texto, (
        f"marcadores {INICIO!r}/{FIM!r} sumiram de {WRAPPER} — o teste recorta "
        "por eles justamente para nao virar copia do codigo")
    return texto.split(INICIO, 1)[1].split(FIM, 1)[0]


@pytest.fixture
def roteiro(tmp_path):
    """Script executavel = trava real + um corpo que anuncia que entrou."""
    caminho = tmp_path / "trava.sh"
    caminho.write_text(
        "set -u\n" + recortar_trava()
        + '\necho "ENTREI"\nsleep "${DORME:-0}"\n', encoding="utf-8")
    return caminho


def rodar(shell, roteiro, trava, espera=None, **env):
    ambiente = {**os.environ, "TRAVA_PAG": str(trava), **env}
    return subprocess.run([shell, str(roteiro)], capture_output=True, text=True,
                          timeout=espera or 30, env=ambiente)


@pytest.fixture
def dono(roteiro, tmp_path):
    """Uma rodada VIVA segurando a trava. Encerra no teardown."""
    trava = tmp_path / "pag.lock"
    processos = []

    def abrir(shell, segundos=10):
        p = subprocess.Popen([shell, str(roteiro)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             env={**os.environ, "TRAVA_PAG": str(trava),
                                  "DORME": str(segundos)})
        processos.append(p)
        limite = time.time() + 10
        while not trava.exists() and time.time() < limite:
            time.sleep(0.02)
        assert trava.exists(), "a rodada dona nao criou a trava"
        return p

    yield abrir, trava
    for p in processos:
        p.kill()
        p.wait(timeout=5)


@pytest.mark.parametrize("shell", SHELLS)
def test_trava_livre_entra_e_limpa_ao_sair(shell, roteiro, tmp_path):
    trava = tmp_path / "pag.lock"
    r = rodar(shell, roteiro, trava)
    assert r.returncode == 0 and "ENTREI" in r.stdout
    # o `trap ... EXIT` tem de devolver a trava, senao a proxima rodada so entra
    # quando o limite de idade estourar
    assert not trava.exists(), r.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_rodada_em_curso_sai_zero_sem_entrar(shell, roteiro, dono):
    """Sobreposicao normal NAO pode virar falha no hub (seria diaria)."""
    abrir, trava = dono
    abrir(shell)
    r = rodar(shell, roteiro, trava)
    assert r.returncode == 0
    assert "ENTREI" not in r.stdout, "entrou por cima de uma rodada viva!"
    assert "ja ha uma rodada em curso" in r.stdout
    assert trava.exists(), "o intruso apagou a trava do dono"


@pytest.mark.parametrize("shell", SHELLS)
def test_rodada_presa_sai_seis(shell, roteiro, dono):
    """Presa ha mais que o limite: isso precisa de gente, e o hub tem de ver."""
    abrir, trava = dono
    abrir(shell)
    antigo = time.time() - 60 * 60          # 60 min
    os.utime(trava, (antigo, antigo))
    r = rodar(shell, roteiro, trava, IDADE_ALERTA_MIN_PAG="45")
    assert r.returncode == 6, r.stdout
    assert "TRAVADO" in r.stdout and "ENTREI" not in r.stdout
    assert trava.exists()


@pytest.mark.parametrize("shell", SHELLS)
def test_limite_de_idade_e_configuravel(shell, roteiro, dono):
    """A mesma trava velha passa quando o limite e maior — a regra e a idade."""
    abrir, trava = dono
    abrir(shell)
    antigo = time.time() - 60 * 60
    os.utime(trava, (antigo, antigo))
    r = rodar(shell, roteiro, trava, IDADE_ALERTA_MIN_PAG="90")
    assert r.returncode == 0 and "TRAVADO" not in r.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_trava_orfa_e_removida(shell, roteiro, tmp_path):
    """Processo dono morto (ex.: `docker kill` no meio) nao pode calar o robo."""
    trava = tmp_path / "pag.lock"
    trava.write_text("999999\n")            # pid que nao existe
    r = rodar(shell, roteiro, trava)
    assert r.returncode == 0
    assert "trava orfa" in r.stdout and "ENTREI" in r.stdout
    assert not trava.exists()


@pytest.mark.parametrize("shell", SHELLS)
def test_trava_vazia_e_tratada_como_orfa(shell, roteiro, tmp_path):
    """Arquivo criado sem pid (escrita interrompida) nao pode travar para sempre."""
    trava = tmp_path / "pag.lock"
    trava.write_text("")
    r = rodar(shell, roteiro, trava)
    assert r.returncode == 0 and "ENTREI" in r.stdout


def test_o_wrapper_inteiro_e_valido_nos_dois_shells():
    """`sh -n` no arquivo de producao: bashism aqui e exit code perdido no hub."""
    for shell in SHELLS:
        r = subprocess.run([shell, "-n", str(WRAPPER)], capture_output=True,
                           text=True, timeout=30)
        assert r.returncode == 0, f"{shell}: {r.stderr}"
