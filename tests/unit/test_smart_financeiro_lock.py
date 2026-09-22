"""Exclusao entre wrappers reais, sem navegador, rede ou credenciais."""
import fcntl
import os
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'src/common/smart_financeiro_lock.sh'


@pytest.mark.parametrize('shell', ['sh', 'dash', 'bash'])
def test_duas_rotinas_esperam_e_preservam_argumentos_e_exit_code(tmp_path, shell):
    roteiro = tmp_path / 'wrapper.sh'
    roteiro.write_text(f'. {shlex.quote(str(LOCK))}\nprintf "EXECUTOU:%s\\n" "$1"\nexit 7\n')
    env = dict(os.environ, TRAVA_SMART_FINANCEIRO=str(tmp_path / 'financeiro.lock'))
    with open(env['TRAVA_SMART_FINANCEIRO'], 'w') as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        proc = subprocess.Popen([shell, str(roteiro), 'argumento com espacos'],
                                env=env, stdout=subprocess.PIPE, text=True)
        try:
            assert 'aguardando exclusividade' in proc.stdout.readline()
            # Enquanto outra rotina usa a conta, nem o corpo do wrapper comeca.
            with pytest.raises(subprocess.TimeoutExpired):
                proc.wait(timeout=0.1)
            fcntl.flock(holder, fcntl.LOCK_UN)
            output = proc.communicate(timeout=5)[0]
            assert 'EXECUTOU:argumento com espacos' in output
            assert proc.returncode == 7
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)


def test_daemon_nao_herda_trava_apos_wrapper_sair(tmp_path):
    roteiro = tmp_path / 'wrapper.sh'
    roteiro.write_text(f'. {shlex.quote(str(LOCK))}\nsleep 2 >/dev/null 2>&1 &\n')
    lock = tmp_path / 'financeiro.lock'
    subprocess.run(['sh', str(roteiro)], check=True, timeout=5,
                   env=dict(os.environ, TRAVA_SMART_FINANCEIRO=str(lock)),
                   stdout=subprocess.DEVNULL)
    with lock.open('w') as holder:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize('robo', ['remessa_pagamento', 'retorno_pagamento'])
def test_wrapper_trava_antes_de_tocar_no_chrome(robo):
    wrapper = ROOT / 'src/processors/web' / robo / 'run_agendado.sh'
    text = wrapper.read_text()
    assert text.index('smart_financeiro_lock.sh') < text.index('pkill -f')
    subprocess.run(['sh', '-n', str(wrapper)], check=True)
