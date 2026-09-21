"""A metade do ROBO no ensaio ponta a ponta: cancelamentos.json -> corpo do POST.

⛔ POR QUE EXISTE. O process-automation decide e escreve o arquivo; quem executa e este
robo. Entre os dois nao ha tipo compartilhado nem repositorio comum - so um JSON. Foi
nessa costura que nasceu o defeito de 21/09/2026: o robo mandava o `numero_cedente` do
CNAB (1026716) no campo `contaSelected`, que a tela espera receber a conta do ERP (298).
O POST montava a grade de uma conta inexistente, o id nao aparecia nela e o cancelamento
falhava calado - com exit 0.

A outra metade e `process-automation::tests/test_cancelamentos_ponta_a_ponta.py`, que
prova que o arquivo sai no formato lido aqui. Quem roda as duas de uma vez e
`process-automation::setores/financeiro/moneyplus/cnab_boleto_400/_dev_tools/ensaio_cancelamento.sh`.

Sem navegador, sem Smart, sem rede.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROBO = Path(__file__).resolve().parents[2] / "src/processors/web/robo_remessa"
sys.path.insert(0, str(ROBO))

import cancelar

AGORA = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)

#: O de-para real do `contas_carteiras.json`, com os nomes como o Smart os escreve.
CONTAS = {"291": "mp cast", "298": "mp tapayuna", "404": "mp prospere", "371": "mp fr&c"}


def lista(tmp_path, **troca):
    """Um `cancelamentos.json` no formato REAL - o de 21/09/2026, com uma remessa."""
    dados = {
        "versao": 1,
        "gerado_em": (AGORA - timedelta(minutes=5)).isoformat(),
        "validade_horas": 12,
        "regra": "remessa recusada cujos titulos o banco confirmou NAO ter",
        "remessas": {
            "26383": {
                "arquivo": "CB15090000961.REM",
                "numero_cedente": 1026716,
                "smart_id": 26383,
                "motivo": "2 titulo(s) sem boleto no banco voltam a fila",
                "titulos_que_voltam": 2,
                "valor": 1079.3,
                "excluir_da_geracao": [],
            }
        },
    }
    dados.update(troca)
    destino = tmp_path / "cancelamentos.json"
    destino.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return destino


# ---------------------------------------------------------------------------
# ler_lista - a lista velha NAO executa
# ---------------------------------------------------------------------------


def test_lista_fresca_e_lida(tmp_path):
    remessas, erro = cancelar.ler_lista(lista(tmp_path), agora=AGORA)

    assert erro == ""
    assert list(remessas) == ["26383"]
    assert remessas["26383"]["arquivo"] == "CB15090000961.REM"


def test_lista_VENCIDA_nao_executa(tmp_path):
    """A prova de que o boleto nao esta no banco tem prazo.

    Entre a resposta do banco e agora o boleto pode ter sido registrado - e aquele titulo
    passaria a ser uma duplicata esperando acontecer.
    """
    velha = lista(tmp_path, gerado_em=(AGORA - timedelta(hours=13)).isoformat())

    remessas, erro = cancelar.ler_lista(velha, agora=AGORA)

    assert remessas == {}
    assert "VENCIDA" in erro and "caducou" in erro


def test_lista_na_BORDA_da_validade_ainda_vale(tmp_path):
    quase = lista(tmp_path, gerado_em=(AGORA - timedelta(hours=11, minutes=59)).isoformat())

    remessas, _ = cancelar.ler_lista(quase, agora=AGORA)

    assert list(remessas) == ["26383"]


def test_lista_ausente_ou_ilegivel_nao_derruba_e_diz_o_que_falta(tmp_path):
    remessas, erro = cancelar.ler_lista(tmp_path / "nao_existe.json", agora=AGORA)
    assert remessas == {} and "nao existe" in erro

    quebrada = tmp_path / "quebrada.json"
    quebrada.write_text("{isto nao e json", encoding="utf-8")
    remessas, erro = cancelar.ler_lista(quebrada, agora=AGORA)
    assert remessas == {} and "ilegivel" in erro


def test_remessas_em_formato_inesperado_e_recusado(tmp_path):
    torta = lista(tmp_path, remessas=["26383"])

    remessas, erro = cancelar.ler_lista(torta, agora=AGORA)

    assert remessas == {} and "formato inesperado" in erro


# ---------------------------------------------------------------------------
# conta_do_smart - o defeito de 21/09/2026, virado gate
# ---------------------------------------------------------------------------


def test_o_tipo_do_controle_vira_a_conta_do_ERP(tmp_path):
    """⛔ Sao DOIS numeros e ambos parecem "o cedente".

    numero_cedente  1026716   o cedente NO BANCO, que vem no header do .REM
    conta do Smart  298       a conta no ERP, que e o que `contaSelected` espera

    O `tipo` do `remessas_geradas.json` traz o nome da conta; o `contas_carteiras.json`
    mapeia nome -> numero. Mandar o primeiro numero derruba o cancelamento em silencio.
    """
    assert cancelar.conta_do_smart("mp tapayuna Envio de cobranca registrado", CONTAS) == "298"
    assert cancelar.conta_do_smart("mp cast Quitacao ou cancelamento", CONTAS) == "291"
    assert cancelar.conta_do_smart("mp fr&c Envio de cobranca registrado", CONTAS) == "371"


def test_tipo_desconhecido_NAO_inventa_conta():
    """Sem conta nao ha POST - e adivinhar cancelaria a remessa de outro cedente."""
    assert cancelar.conta_do_smart("mp inexistente Envio", CONTAS) is None
    assert cancelar.conta_do_smart("", CONTAS) is None
    assert cancelar.conta_do_smart(None, CONTAS) is None
    assert cancelar.conta_do_smart("mp tapayuna Envio", {}) is None


def test_o_casamento_e_por_PREFIXO_e_nao_por_substring():
    """"mp cast" nao pode casar com um tipo que so CONTENHA o nome no meio."""
    assert cancelar.conta_do_smart("Envio de cobranca da mp cast", CONTAS) is None


# ---------------------------------------------------------------------------
# montar_post - o corpo exato que a tela do Smart espera
# ---------------------------------------------------------------------------


def test_o_corpo_do_post_reproduz_o_que_o_JS_da_tela_faz():
    """Lido do JS de `downloadremessa.php`:

        form.checks.value = radioSel;   // o ID da remessa
        form.cancelamento.value = 1;    // liga o cancelamento
        form.submit();                  // POST na MESMA url da listagem
    """
    corpo = cancelar.montar_post(26383, "298", "2026-09-14", "2026-09-21")

    campos = dict(par.split("=", 1) for par in corpo.split("&"))
    assert campos["checks"] == "26383"
    assert campos["cancelamento"] == "1"
    assert campos["radioSel"] == "26383"
    assert campos["contaSelected"] == "298"
    assert campos["contaCorrente"] == "298"
    assert campos["periodo_inicial"] == "2026-09-14"
    assert campos["periodo_final"] == "2026-09-21"
    assert campos["form_submit"] == "1"


def test_o_post_carrega_o_PERIODO_porque_sem_ele_a_grade_nao_tem_o_id():
    """A tela e a mesma da listagem: sem periodo e conta, o id nao existe na grade."""
    corpo = cancelar.montar_post(1, "298", "", "")

    assert "periodo_inicial=&" in corpo or corpo.endswith("periodo_final=")


# ---------------------------------------------------------------------------
# cancelar_uma - o dry e o padrao, e o timeout NAO e falha
# ---------------------------------------------------------------------------


def test_dry_run_e_o_PADRAO_e_nao_toca_no_smart():
    class ContextoQueNaoDeveSerUsado:
        @property
        def request(self):
            raise AssertionError("dry_run nao pode chamar o Smart")

    saida = cancelar.cancelar_uma(ContextoQueNaoDeveSerUsado(), 26383, "298", "a", "b")

    assert saida["ok"] is None and saida["enviado"] is False
    assert "DRY_RUN" in saida["motivo"]
    assert "checks=26383" in saida["corpo"]


def test_TIMEOUT_devolve_enviado_true_porque_pode_ter_cancelado():
    """⛔ Conexao cortada NAO diz se o Smart processou - e e o pior caso.

    `enviado=False` faria a rodada seguinte tentar de novo uma remessa que ja pode ter
    sido cancelada. Mesma regra que o `gerar.py` adotou depois do BUG-681.
    """
    class ContextoQueEstoura:
        class request:
            @staticmethod
            def post(*_, **__):
                raise TimeoutError("Timeout 180000ms exceeded")

    saida = cancelar.cancelar_uma(ContextoQueEstoura(), 26383, "298", "a", "b", dry_run=False)

    assert saida["ok"] is False
    assert saida["enviado"] is True, "quem chamou TEM de reconferir pela listagem"
    assert "reconferir" in saida["motivo"]


def test_resposta_sem_utilidade_tambem_manda_reconferir():
    class ContextoDeslogado:
        class request:
            @staticmethod
            def post(*_, **__):
                class R:
                    status = 302

                    @staticmethod
                    def body():
                        return b""
                return R()

    saida = cancelar.cancelar_uma(ContextoDeslogado(), 26383, "298", "a", "b", dry_run=False)

    assert saida["ok"] is False and saida["enviado"] is True
    assert "reconferir" in saida["motivo"]


# ---------------------------------------------------------------------------
# sumiu_da_grade - quem CONFIRMA o cancelamento e a grade, nao o status 200
# ---------------------------------------------------------------------------


def test_a_confirmacao_e_a_remessa_SUMIR_da_grade():
    """`ok=True` do POST diz que o Smart respondeu 200, nao que cancelou."""
    sumiu, motivo = cancelar.sumiu_da_grade(
        None, 26383, "298", "a", "b", listar=lambda *_: [{"id": 26461}, {"id": 26438}])

    assert sumiu is True and "sumiu" in motivo


def test_remessa_que_AINDA_aparece_nao_foi_cancelada():
    sumiu, motivo = cancelar.sumiu_da_grade(
        None, 26383, "298", "a", "b", listar=lambda *_: [{"id": "26383"}])

    assert sumiu is False and "AINDA aparece" in motivo


def test_grade_ilegivel_devolve_NAO_SEI_e_nao_um_falso_sumiu():
    """⛔ Falhar a leitura nao pode virar "cancelou" - e a direcao que custa caro."""
    def explode(*_):
        raise RuntimeError("sessao caiu")

    sumiu, motivo = cancelar.sumiu_da_grade(None, 26383, "298", "a", "b", listar=explode)

    assert sumiu is None, "nao sei != sumiu"
    assert "nao deu para reconferir" in motivo


# ---------------------------------------------------------------------------
# A cadeia inteira desta metade, num teste so
# ---------------------------------------------------------------------------


def test_do_ARQUIVO_ate_o_POST_sem_pular_nenhum_elo(tmp_path):
    """O ensaio desta metade: le a lista, traduz a conta, monta o POST, confere a grade."""
    remessas, erro = cancelar.ler_lista(lista(tmp_path), agora=AGORA)
    assert erro == ""

    (smart_id, remessa), = remessas.items()
    conta = cancelar.conta_do_smart("mp tapayuna Envio de cobranca registrado", CONTAS)
    assert conta == "298" and conta != str(remessa["numero_cedente"])

    saida = cancelar.cancelar_uma(object(), smart_id, conta, "2026-09-14", "2026-09-21")
    assert saida["enviado"] is False, "o ensaio nao cancela"
    campos = dict(par.split("=", 1) for par in saida["corpo"].split("&"))
    assert campos == {
        "form_submit": "1", "checks": "26383", "cancelamento": "1", "radioSel": "26383",
        "contaSelected": "298", "contaCorrente": "298",
        "periodo_inicial": "2026-09-14", "periodo_final": "2026-09-21",
    }

    sumiu, _ = cancelar.sumiu_da_grade(None, smart_id, conta, "a", "b", listar=lambda *_: [])
    assert sumiu is True


@pytest.mark.parametrize("campo", ["arquivo", "smart_id", "numero_cedente", "excluir_da_geracao"])
def test_o_contrato_com_o_process_automation_esta_declarado(tmp_path, campo):
    """Campo que some do arquivo tem de quebrar AQUI, nao em producao as 18h."""
    remessas, _ = cancelar.ler_lista(lista(tmp_path), agora=AGORA)

    assert campo in remessas["26383"]


# ---------------------------------------------------------------------------
# A janela e a entrada do controle — os dois gaps de 21/09/2026 a tarde
# ---------------------------------------------------------------------------


CONTROLE = {
    "CB08090000011.REM": [
        {"id": 111, "md5": "aaaa", "tipo": "mp prospere", "baixado_em": "2026-09-08 21:03:00"},
        {"id": 222, "md5": "bbbb", "tipo": "wj moreira", "baixado_em": "2026-09-08 21:04:00"},
    ],
    "CB20080000367.REM": [{"id": 25908, "tipo": "mp hydronorte", "baixado_em": "2026-08-20 21:13:25"}],
    "SEM_DATA.REM": [{"id": 9, "tipo": "mp cast"}],
}


def test_a_entrada_do_controle_e_a_DAQUELE_id_e_nao_a_primeira_do_nome():
    """⛔ O nome se repete entre contas: `entrada[0]` casa o tipo de uma com o id de outra.

    Em 18/09/2026 o `CB08090000011` era da MP PROSPERE e da WJ MOREIRA ao mesmo tempo.
    Pegar a primeira manda o POST para a grade errada, onde o id nao existe.
    """
    assert cancelar.entrada_do_controle(CONTROLE, "CB08090000011.REM", 222)["tipo"] == "wj moreira"
    assert cancelar.entrada_do_controle(CONTROLE, "CB08090000011.REM", 111)["tipo"] == "mp prospere"
    assert cancelar.entrada_do_controle(CONTROLE, "CB08090000011.REM", 999) == {}
    assert cancelar.entrada_do_controle({}, "X.REM", 1) == {}


def test_a_janela_segue_a_remessa_e_nao_os_7_dias_do_robo():
    """⛔ O gap que produzia falso sucesso em 18 das 21 remessas, medido em 21/09/2026.

    O job olha 45 dias para tras; o padrao do robo e 7. Uma remessa de 20/08 nunca
    aparece na grade de 14 a 21/09 — o POST nao acha o id, nao cancela, e o
    `sumiu_da_grade`, que lista a MESMA janela curta, confirma que sumiu.
    """
    de, ate = cancelar.janela_da_remessa(CONTROLE["CB20080000367.REM"][0])

    assert (de, ate) == ("2026-08-19", "2026-08-21"), "a grade tem de conter 20/08"
    assert cancelar.FOLGA_DA_GRADE_DIAS == 1


def test_sem_data_no_controle_a_janela_sai_LARGA_e_nao_curta():
    """⭐ Janela larga so deixa a grade maior; janela curta esconde a remessa."""
    de, ate = cancelar.janela_da_remessa(CONTROLE["SEM_DATA.REM"][0])

    assert cancelar.DIAS_SEM_DATA_NO_CONTROLE == 60
    assert (datetime.fromisoformat(ate) - datetime.fromisoformat(de)).days == 60


def test_de_e_ate_explicitos_mandam():
    """O operador que quer a janela dele tem a dele."""
    assert cancelar.janela_da_remessa({}, de="2026-01-01", ate="2026-12-31") == ("2026-01-01", "2026-12-31")


@pytest.mark.parametrize("tipo, esperada", [
    ("mp pradzia papeis Envio de cobranca registrado", "343"),
    ("mp pradzia Envio de cobranca registrado", "293"),
])
def test_o_nome_MAIS_LONGO_vence_a_colisao_de_prefixo(tipo, esperada):
    """⛔ 4 das 57 contas reais tem nome que e prefixo de outra.

    Varrendo na ordem do dicionario, `"mp pradzia papeis ..."` devolvia 293 — conta
    errada, grade errada, id ausente, e o `sumiu_da_grade` confirmando o falso sucesso.
    """
    contas = {"293": "mp pradzia", "343": "mp pradzia papeis", "298": "mp tapayuna"}

    assert cancelar.conta_do_smart(tipo, contas) == esperada
