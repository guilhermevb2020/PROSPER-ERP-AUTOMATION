import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "processors" / "web" / "robo_retorno"))

from artefatos import (  # noqa: E402
    SCHEMA_RECIBO,
    categoria_do_resultado,
    gravar_recibo_atomico,
    mover_sem_sobrescrever,
)


def test_categoria_separa_processado_rejeitado_inconclusivo_e_retry():
    assert categoria_do_resultado({
        "processado": True, "estado_final": "processado_smart",
    }) == "_PROCESSADOS"
    assert categoria_do_resultado({
        "processado": False, "portao": {"liberado": False},
    }) == "_REJEITADOS"
    assert categoria_do_resultado({
        "processado": False, "passo_irreversivel_chamado": True,
    }) == "_INCONCLUSIVOS"
    assert categoria_do_resultado({
        "processado": False, "estado_final": "ja_processado",
    }) == "_PROCESSADOS"
    assert categoria_do_resultado({
        "processado": False, "passo_irreversivel_chamado": False,
    }) is None


def test_movimento_individual_nunca_sobrescreve_homonimo(tmp_path):
    primeira_origem = tmp_path / "origem1"
    segunda_origem = tmp_path / "origem2"
    primeira_origem.mkdir()
    segunda_origem.mkdir()
    primeira = primeira_origem / "DEP.RET"
    segunda = segunda_origem / "DEP.RET"
    primeira.write_bytes(b"primeiro")
    segunda.write_bytes(b"segundo")

    destino1 = Path(mover_sem_sobrescrever(
        primeira, tmp_path / "fila", "_PROCESSADOS"
    ))
    destino2 = Path(mover_sem_sobrescrever(
        segunda, tmp_path / "fila", "_PROCESSADOS"
    ))

    assert destino1 != destino2
    assert destino1.read_bytes() == b"primeiro"
    assert destino2.read_bytes() == b"segundo"
    assert not primeira.exists()
    assert not segunda.exists()


def test_recibo_e_json_atomico_com_provas_do_smart(tmp_path):
    resultado = {
        "arquivo": "DEP010926123ABC.RET",
        "nome_smart": "DEP010926123ABC.RET",
        "hash": "a" * 32,
        "sha256": "b" * 64,
        "titulos": 1,
        "processado": True,
        "estado_final": "processado_smart",
        "passo_irreversivel_chamado": True,
        "portao": {"liberado": True, "avaliados": 1},
        "confirmacao_smart": {"comprovado": True},
        "resposta_processamento": {
            "message": "OK", "liquidacao": 1, "refinan": None,
        },
        "ocorrencias": {"liquidacao": 1},
        "destino_relativo": "_PROCESSADOS/2026-09/DEP010926123ABC.RET",
        "motivo": "OK",
    }

    caminho = Path(gravar_recibo_atomico(tmp_path / "_RESULTADOS", resultado))
    recibo = json.loads(caminho.read_text(encoding="utf-8"))

    assert recibo["schema"] == SCHEMA_RECIBO
    assert recibo["sha256"] == "b" * 64
    assert recibo["portao"] == {"avaliados": 1, "liberado": True}
    assert recibo["resposta_processamento"]["liquidacao"] == 1
    assert recibo["destino_relativo"].startswith("_PROCESSADOS/")
    assert list((tmp_path / "_RESULTADOS").rglob("*.tmp")) == []


def test_duas_tentativas_geram_dois_recibos_sem_sobrescrever(tmp_path):
    resultado = {
        "arquivo": "DEP.RET", "sha256": "c" * 64,
        "processado": False, "estado_final": "recusado_portao",
    }

    primeiro = gravar_recibo_atomico(tmp_path, resultado)
    segundo = gravar_recibo_atomico(tmp_path, resultado)

    assert primeiro != segundo
    assert Path(primeiro).is_file()
    assert Path(segundo).is_file()
