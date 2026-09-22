"""O Hub deve receber o codigo do job, mesmo com stdout passando por tee."""
import os
from pathlib import Path
import subprocess

import pytest

WRAPPER = Path(__file__).resolve().parents[2] / 'src/processors/web/credito/run_agendado.sh'


@pytest.mark.parametrize('codigo', [0, 1, 2, 3, 137, 143])
def test_tee_nao_esconde_falha_do_job(tmp_path, codigo):
    s=WRAPPER.read_text()
    trecho=s[s.index('python /app/src/processors/web/credito/analisar_credito.py'):]
    # Usa o bloco inteiro quando ha preservacao explicita do codigo.
    if '# BEGIN EXECUCAO_CREDITO' in s:
        trecho=s.split('# BEGIN EXECUCAO_CREDITO\n',1)[1]
    script='python() { echo "ciclo sintetico"; return "$TEST_EXIT_CODE"; };\n'+trecho
    env={**os.environ,'TEST_EXIT_CODE':str(codigo),'LOG_JOB':str(tmp_path/'credito.log'),'TMPDIR':str(tmp_path)}
    r=subprocess.run(['sh','-c',script],env=env,capture_output=True,text=True)
    assert r.returncode==codigo
    assert 'ciclo sintetico' in (tmp_path/'credito.log').read_text()
