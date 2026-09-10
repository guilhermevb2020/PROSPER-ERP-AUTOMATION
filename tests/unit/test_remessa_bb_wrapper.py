"""Executa o wrapper BB com Python substituído; sem navegador ou rede."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "src/processors/web/robo_remessa/run_bb.sh"


@pytest.fixture
def ambiente(tmp_path):
    raiz = tmp_path / "erp com espacos"
    comum = raiz / "src/common"
    comum.mkdir(parents=True)
    shutil.copyfile(ROOT / "src/common/smart_financeiro_lock.sh", comum / "smart_financeiro_lock.sh")
    config = raiz / "config"
    config.mkdir()
    (config / "robo_remessa.env").write_text("DRY_RUN_REM=false\nHEADLESS_REM=false\n")
    (config / "robo_retorno.env").write_text("DRY_RUN_RET=false\nHEADLESS_RET=false\n")
    binario = tmp_path / "bin"
    binario.mkdir()
    python = binario / "python"
    python.write_text(f"#!{sys.executable}\n" + '''import fcntl, json, os, sys
with open(os.environ["TRAVA_SMART_FINANCEIRO"], "a") as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        pass
    else:
        raise RuntimeError("wrapper executou sem exclusividade financeira")
sufixo = "RET" if sys.argv[1].endswith("robo_retorno.py") else "REM"
print(json.dumps({"argv": sys.argv[1:], "dry": os.environ["DRY_RUN_" + sufixo],
                  "headless": os.environ["HEADLESS_" + sufixo]}))
sys.exit(int(os.environ.get("TESTE_EXIT", "0")))
''')
    python.chmod(0o755)
    return dict(os.environ, PATH=f"{binario}:{os.environ['PATH']}",
                RAIZ_BB_REMESSA=str(raiz), RAIZ_BB_RETORNO=str(raiz),
                TRAVA_SMART_FINANCEIRO=str(tmp_path / "financeiro.lock"),
                BB_REMESSA_CARTEIRA="17")


@pytest.mark.parametrize("shell", ["sh", "dash", "bash"])
@pytest.mark.parametrize("args,modo", [([], "--simular"), (["--simular"], "--simular"),
                                       (["--pra-valer"], "--pra-valer")])
def test_escopo_exato_trava_e_modo_explicito(ambiente, shell, args, modo):
    resultado = subprocess.run([shell, str(WRAPPER), *args], env=ambiente,
                               capture_output=True, text=True, timeout=5, check=True)
    dados = json.loads(resultado.stdout.splitlines()[-1])
    raiz = ambiente["RAIZ_BB_REMESSA"]
    assert dados == {"argv": [f"{raiz}/src/processors/web/robo_remessa/robo_remessa.py",
                              "--gerar", "--conta", "395", "--carteira", "17",
                              "--bb-api-convenio", "3770013", "--bb-api-ambiente", "producao",
                              "--bb-api-origem", f"{raiz}/data/retornos_a_processar/bb_api/origens", modo],
                     "dry": "True", "headless": "true"}


@pytest.mark.parametrize("args,carteira", [(["--todas-contas"], "17"),
                                         (["--pra-valer", "--simular"], "17"), ([], "9")])
def test_escopo_invalido_nao_chama_processador(ambiente, args, carteira):
    resultado = subprocess.run(["sh", str(WRAPPER), *args],
                               env=dict(ambiente, BB_REMESSA_CARTEIRA=carteira),
                               capture_output=True, text=True, timeout=5)
    assert resultado.returncode == 2
    assert '"argv"' not in resultado.stdout


def test_status_do_processador_chega_ao_agendador(ambiente):
    resultado = subprocess.run(["sh", str(WRAPPER)], env=dict(ambiente, TESTE_EXIT="6"),
                               capture_output=True, text=True, timeout=5)
    assert resultado.returncode == 6


@pytest.mark.parametrize("caminho", ["robo_remessa/run_agendado.sh", "robo_retorno/run_agendado.sh",
                                    "robo_retorno/run_deposito.sh"])
def test_wrapper_money_compartilha_trava_antes_do_chrome(caminho):
    wrapper = ROOT / "src/processors/web" / caminho
    texto = wrapper.read_text()
    assert texto.index("smart_financeiro_lock.sh") < texto.index("pkill -f")
    subprocess.run(["sh", "-n", str(wrapper)], check=True)


@pytest.mark.parametrize("shell", ["sh", "dash", "bash"])
@pytest.mark.parametrize("args", [[], ["--simular"], ["--pra-valer"]])
def test_retorno_bb_usa_pasta_conta_e_recibos_exatos(ambiente, shell, args):
    wrapper = ROOT / "src/processors/web/robo_retorno/run_bb.sh"
    resultado = subprocess.run([shell, str(wrapper), *args], env=ambiente,
                               capture_output=True, text=True, timeout=5, check=True)
    dados = json.loads(resultado.stdout.splitlines()[-1])
    raiz = ambiente["RAIZ_BB_RETORNO"]
    pasta = f"{raiz}/data/retornos_a_processar/bb_api/retornos/producao/3770013/395"
    assert dados == {"argv": [f"{raiz}/src/processors/web/robo_retorno/robo_retorno.py",
                              "--pasta", pasta, "--conta-bb-api", "395", "--portao",
                              "--pular-processados", "--recibos-dir", f"{pasta}/_RESULTADOS",
                              *(["--pra-valer"] if args == ["--pra-valer"] else [])],
                     "dry": "True", "headless": "true"}
