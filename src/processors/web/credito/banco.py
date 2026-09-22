"""
banco.py - acesso ao Postgres + controle dos downloads.

Usado pelo sub-fluxo BAIXAR NF E RESUMO (subfluxos.py) para:
  1) DESCOBRIR as operacoes na etapa "FEEDBACK ANALISE ROB" consultando
     trs.operacao_desagio (coluna id_operacao = numero da operacao do Smart;
     coluna etapa = etapa ATUAL). Substitui a raspagem da tela de consulta.
  2) REGISTRAR quais operacoes ja tiveram NF + resumo baixados (e se a etapa ja
     foi movida), para nao reprocessar.

O controle mora no banco desde 22/09/2026 (Gerencia: "colocar tudo no banco ... e
eliminar a escrita no csv"): cada download e cada move sao um evento em
erp_automation.operacao_evento (`documentos_baixados`, `etapa_movida`), na execucao
que analisar_credito.py abriu. O controle_downloads.csv parou de ser lido e escrito;
o que ele sabia (desde 03/07/2026) entrou no banco pela carga
src/processors/db/controle/carregar_historico_csv.py, com o instante original.
"""

from datetime import datetime

import config


# --------------------------------------------------------------------------- #
# PostgreSQL
# --------------------------------------------------------------------------- #
def operacoes_na_etapa(etapa: str) -> list:
    """Retorna os numeros de operacao (str) que estao na 'etapa' informada,
    lendo trs.operacao_desagio. LEVANTA excecao se o banco estiver inacessivel
    (o chamador trata e cai p/ a raspagem da UI). connect_timeout curto evita
    travar o ciclo quando a VPN esta fora."""
    import psycopg2  # import tardio: so quando realmente vai falar com o banco
    conn = psycopg2.connect(connect_timeout=config.DB_CONNECT_TIMEOUT, **config.DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id_operacao FROM {config.TABELA_OPERACOES} "
            "WHERE etapa = %s ORDER BY id_operacao",
            (etapa,),
        )
        ops = [str(r[0]).strip() for r in cur.fetchall() if r[0] is not None]
        cur.close()
        return ops
    finally:
        conn.close()


def quadro_societario(op) -> dict:
    """Busca o quadro societario da operacao no Postgres (tabelas que o robo de
    analise de credito - prospercredit - popula). Usado pela conferencia V3 p/
    checar assinaturas x representantes legais.

    Retorna:
      {
        "cedente": {"cnpj","nome","socios":[...],"administracao":[...]|None,"receita_federal":{...}|None} | None,
        "sacados": [{"cnpj","nome","socio_principal","qtd_socios"}, ...]
      }
    O CEDENTE vem COMPLETO (stg.robo_analise_cedente: socios/administracao/receita_federal).
    Os SACADOS vem PARCIAIS (stg.robo_analise_sacado + int.enriquecimento_sacado:
    so socio_principal/qtd_socios - o banco nao guarda o QSA completo do sacado).
    Retorna {"cedente": None, "sacados": []} se o banco estiver inacessivel
    (best-effort: a checagem de assinaturas fica "sem dados", nao derruba o resto).
    """
    import psycopg2  # import tardio
    op = str(op)
    out = {"cedente": None, "sacados": []}
    try:
        conn = psycopg2.connect(connect_timeout=config.DB_CONNECT_TIMEOUT, **config.DB_CONFIG)
    except Exception as e:
        print(f"  [societario] banco inacessivel ({e}) -> sem dados societarios")
        return out
    try:
        cur = conn.cursor()
        # CEDENTE (completo)
        try:
            cur.execute(
                "SELECT cnpj, nome, socios, administracao, receita_federal "
                "FROM stg.robo_analise_cedente WHERE numero_operacao = %s "
                "ORDER BY data_carga DESC NULLS LAST LIMIT 1", (op,))
            r = cur.fetchone()
            if r:
                out["cedente"] = {"cnpj": r[0], "nome": r[1], "socios": r[2],
                                  "administracao": r[3], "receita_federal": r[4]}
        except Exception as e:
            print(f"  [societario] erro cedente op {op}: {e}")
        # SACADOS (cnpj+nome da analise; societario parcial via enriquecimento).
        # Dedup por CNPJ (a op tem 1 linha por titulo -> mesmo sacado repete).
        try:
            cur.execute("SELECT DISTINCT cnpj, nome FROM stg.robo_analise_sacado "
                        "WHERE numero_operacao = %s", (op,))
            vistos = set()
            for cnpj, nome in cur.fetchall():
                chave = (cnpj or "").strip()
                if chave in vistos:
                    continue
                vistos.add(chave)
                sac = {"cnpj": cnpj, "nome": nome, "socio_principal": None, "qtd_socios": None}
                try:
                    cur.execute(
                        "SELECT socio_principal_nome, qtd_socios, razao_social "
                        "FROM int.enriquecimento_sacado "
                        "WHERE regexp_replace(cpf_cnpj,'[^0-9]','','g') = "
                        "      regexp_replace(%s,'[^0-9]','','g') LIMIT 1", (cnpj or "",))
                    e = cur.fetchone()
                    if e:
                        sac["socio_principal"] = e[0]
                        sac["qtd_socios"] = e[1]
                        if not sac["nome"] and e[2]:
                            sac["nome"] = e[2]
                except Exception:
                    pass
                out["sacados"].append(sac)
        except Exception as e:
            print(f"  [societario] erro sacados op {op}: {e}")
        cur.close()
    finally:
        conn.close()
    return out


# --------------------------------------------------------------------------- #
# Controle dos downloads ja feitos: eventos no banco (erp_automation.operacao_evento)
# --------------------------------------------------------------------------- #
_EVENTOS_CONTROLE = ("documentos_baixados", "etapa_movida")


def carregar_controle(ops=None) -> dict:
    """O controle lido do banco -> {id_operacao(str): registro}, so das `ops` pedidas
    (todas, sem elas). O registro e o que o CSV tinha: data_download, arquivo_nfe,
    arquivo_resumo, nfe_ok, resumo_ok, etapa_movida — somando todos os eventos da op
    (um ok ja gravado nao se desfaz). {} sem execucao aberta ou sem banco: pode_mover
    exige o resumo, entao nenhuma op e movida neste ciclo e o proximo tenta de novo."""
    try:
        from src.common.clients import execucao_job
    except ImportError:
        return {}
    ex = execucao_job.atual()
    if ex is None:
        return {}
    eventos = execucao_job.listar_eventos_operacao(
        ex, _EVENTOS_CONTROLE, ops=None if ops is None else [str(o) for o in ops])
    if eventos is None:
        print("  [controle] banco sem resposta -> nenhuma op movida neste ciclo (retenta)")
        return {}
    return controle_dos_eventos(eventos)


def controle_dos_eventos(eventos) -> dict:
    """Eventos em ordem de ocorrencia -> o controle no formato do CSV antigo."""
    dados = {}
    for e in eventos:
        op = str(e["id_operacao"])
        reg = dados.setdefault(op, {"data_download": "", "arquivo_nfe": "",
                                    "arquivo_resumo": "", "nfe_ok": False,
                                    "resumo_ok": False, "etapa_movida": False})
        if e["tipo_evento"] == "etapa_movida":
            reg["etapa_movida"] = True
            continue
        d = e.get("detalhe") or {}
        quando = e.get("ocorrido_em")
        if isinstance(quando, datetime):
            reg["data_download"] = quando.astimezone().strftime("%d/%m/%Y %H:%M:%S")
        reg["arquivo_nfe"] = d.get("arquivo_nfe") or reg["arquivo_nfe"]
        reg["arquivo_resumo"] = d.get("arquivo_resumo") or reg["arquivo_resumo"]
        reg["nfe_ok"] = reg["nfe_ok"] or bool(d.get("nfe_ok"))
        reg["resumo_ok"] = reg["resumo_ok"] or bool(d.get("resumo_ok"))
    return dados


def registrar_download(op, arquivo_nfe, arquivo_resumo) -> None:
    """Registra o que ESTE download trouxe (ok = caminho != None) como evento
    documentos_baixados. O acumulado (um ok anterior nao se desfaz) sai da soma dos
    eventos em carregar_controle."""
    nfe_ok, resumo_ok = bool(arquivo_nfe), bool(arquivo_resumo)
    _registrar_no_banco(op, "documentos_baixados",
                        resultado="OK" if (nfe_ok and resumo_ok) else "PARCIAL",
                        detalhe={"arquivo_nfe": arquivo_nfe or "",
                                 "arquivo_resumo": arquivo_resumo or "",
                                 "nfe_ok": nfe_ok, "resumo_ok": resumo_ok})


def marcar_etapa_movida(op) -> None:
    """Registra que a etapa da op foi movida (-> Análise de crédito)."""
    _registrar_no_banco(op, "etapa_movida", resultado=config.ROTULO_ANALISE_CREDITO)


def _registrar_no_banco(op, tipo_evento, *, resultado=None, detalhe=None) -> None:
    """O fato vai para operacao_evento, na execucao que analisar_credito.py abriu
    (execucao_job.atual()). Fato consumado: falha de banco avisa no log e o download
    segue. Fora do fluxo do job (teste, uso manual de uma funcao) nao ha execucao aberta
    e nada e registrado."""
    if not str(op).isdigit():
        return
    try:
        from src.common.clients import execucao_job
    except ImportError:
        return
    ex = execucao_job.atual()
    if ex is None:
        return
    execucao_job.registrar_evento_operacao(ex, int(op), tipo_evento, resultado=resultado,
                                           detalhe=detalhe or {}, fato=True)


def ja_baixou(reg) -> bool:
    """True se o registro de controle indica NF E resumo ja baixados com sucesso."""
    return bool(reg) and bool(reg.get("nfe_ok")) and bool(reg.get("resumo_ok"))


def pode_mover(reg) -> bool:
    """True se da p/ MOVER a etapa da operacao. Exige apenas o RESUMO baixado;
    a NF e OPCIONAL: existem operacoes que legitimamente NAO tem nota fiscal, e
    nesses casos a NF nao pode bloquear o avanco (senao a op fica presa em loop
    infinito em 'Feedback ROB'). A ausencia da NF fica registrada no controle
    (nfe_ok=0) para auditoria."""
    return bool(reg) and bool(reg.get("resumo_ok"))
