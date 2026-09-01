# -*- coding: utf-8 -*-
"""
retorno.py - processa arquivos de RETORNO (CNAB) no Smart, por HTTP.

A tela "Financeiro > CNAB > Processar Retorno" (retornoocorrencia.php) NAO
posta formulario: ela conversa com `ajax/ajaxretornocnab.php` mandando um
parametro `Acao`. Cada passo do JS vira uma chamada aqui - por isso o robo NAO
precisa abrir tela nenhuma.

Bonus: sem tela, some o "Debugger pausado em outra guia" que trava o
processamento quando o Playwright esta anexado via CDP (o Chrome trata a
conexao como depurador e qualquer `debugger;` no JS congela a pagina).

SEQUENCIA (a mesma do navegador, em ordem):
  1. VERIFICAR_ARQUIVO_EM_PROCESSAMENTO  {NomeArquivo}      -> trava anti-concorrencia
  2. VERIFICAR_ARQUIVO_PROCESSADO        {NomeArquivo}      -> ja rodou hoje?
  3. (cliente) conta linhas - limite 5000
  4. VALIDAR_BANCO_CONTA                 {Header}           -> descobre numConta
  5. INICIALIZAR_LOG_UPLOAD
  6. UPLOAD_ARQUIVO   {NomeArquivo, conteudo, origem, numConta}
                                                            -> devolve target/extensao/qtd
  7. INICIALIZAR_LOG_PROGRESSO
  8. PROCESSAR_ARQUIVO {NomeArquivo, target, origem, extensao, numContaArquivoRetorno}
                                                            <- ESTE da baixa nos titulos
  9. RETIRAR_EM_PROCESSAMENTO            {NomeArquivo}      -> solta a trava

Ate o passo 6 nada e efetivado: o upload so deixa o arquivo pronto e monta a
grade. Quem altera producao e o passo 8. Por isso `processar()` so vai ate o 6
quando dry_run=True.
"""
import base64
import hashlib
import json
import os
import re
import urllib.parse

import portao
import retorno_config as cfg
# so o `parece_deslogado` interessa aqui — e ele agora e compartilhado
from src.common.clients import smart_sessao as autenticacao

URL_AJAX = cfg.SMART_BASE + "/financeiro/ajax/ajaxretornocnab.php"
LIMITE_LINHAS = 5000          # mesmo valor do campo #limiteLinhas da tela

#: Motivo do skip por --pular-processados (mesmo conteudo ja processado com
#: SUCESSO antes). `robo_retorno.py` usa esta constante pra NAO contar o skip
#: como erro no exit code - e a prova de um sucesso anterior, nao uma pendencia.
MOTIVO_JA_PROCESSADO = "conteudo identico ja processado (--pular-processados)"


class ErroRetorno(Exception):
    """Falha esperada no fluxo (arquivo invalido, banco nao achado, etc.)."""


def nome_limpo(caminho):
    """Mesmo saneamento do JS: so letras, numeros e ponto.
        form.avatar_file.value.split("\\\\").pop().replace(/[^a-zA-Z0-9.]/g, "")
    O Smart usa ESSE nome como chave de 'ja processado' / 'em processamento',
    entao tem que bater exatamente.
    """
    return re.sub(r"[^a-zA-Z0-9.]", "", os.path.basename(caminho))


def ler_arquivo(caminho):
    """Le o .RET como ISO-8859-1 (igual ao FileReader da tela)."""
    with open(caminho, "r", encoding="iso-8859-1", errors="replace") as f:
        return f.read()


def _post(ctx, dados, timeout=180_000):
    """POST no ajax e devolve o JSON.

    ATENCAO: o corpo vai URLENCODADO na mao. Passar `data={dict}` pro Playwright
    serializa como JSON, o PHP nao acha nada em $_POST e responde
    {"message": "UNKNOW_ACTION"} - que e facil de confundir com "nao tem nada",
    porque d.get("EmProcessamento") tambem volta vazio. Por isso, alem do
    encode certo, qualquer UNKNOW_ACTION vira ERRO explicito aqui embaixo.

    A resposta as vezes traz '<!-- ping -->' no meio (keepalive do servidor);
    o proprio JS da tela limpa isso antes do parse.
    """
    corpo = urllib.parse.urlencode(dados, encoding="iso-8859-1", errors="replace")
    r = ctx.request.post(
        URL_AJAX, data=corpo,
        headers={"content-type": "application/x-www-form-urlencoded; charset=ISO-8859-1",
                 "x-requested-with": "XMLHttpRequest"},
        timeout=timeout)
    bruto = r.body().decode("iso-8859-1", errors="replace")
    if autenticacao.parece_deslogado(bruto):
        raise ErroRetorno("sessao do Smart caiu")
    limpo = bruto.strip().replace("<!-- ping -->", "").strip()
    try:
        resposta = json.loads(limpo)
    except Exception:
        raise ErroRetorno(f"resposta nao-JSON (status={r.status}): {limpo[:200]!r}")
    msg = resposta.get("message") if isinstance(resposta, dict) else None
    if msg == "UNKNOW_ACTION":
        raise ErroRetorno(f"o Smart nao reconheceu a acao {dados.get('Acao')!r} "
                          "- payload nao chegou como o PHP espera")
    if msg == "NO_NUM_FACTORING":
        raise ErroRetorno("licenca/numFactoring nao identificada na sessao")
    return resposta


# --------------------------------------------------------------------------- #
# passos
# --------------------------------------------------------------------------- #
def em_processamento(ctx, nome):
    d = _post(ctx, {"Acao": "VERIFICAR_ARQUIVO_EM_PROCESSAMENTO", "NomeArquivo": nome})
    return int(d.get("EmProcessamento") or 0) > 0


def ja_processado(ctx, nome):
    d = _post(ctx, {"Acao": "VERIFICAR_ARQUIVO_PROCESSADO", "NomeArquivo": nome})
    return int(d.get("JaProcessado") or 0) > 0


def validar_banco_conta(ctx, conteudo):
    """Manda o HEADER (1a linha) e recebe a conta correspondente no Smart."""
    header = conteudo.split("\r\n")[0] if "\r\n" in conteudo else conteudo.split("\n")[0]
    d = _post(ctx, {"Acao": "VALIDAR_BANCO_CONTA", "Header": header})
    msg = d.get("message")
    if msg == "INVALID_FILE":
        raise ErroRetorno("arquivo de retorno invalido")
    if msg == "BANK_NOT_FOUND":
        raise ErroRetorno("banco nao encontrado no arquivo")
    if msg == "ACCOUNT_NOT_FOUND":
        raise ErroRetorno("nao corresponde a nenhuma conta do sistema")
    if msg == "CONFIRM_ACCOUNT_NOT_FOUND":
        # a tela PERGUNTA se prossegue; sem gente, o robo NAO arrisca
        raise ErroRetorno("conta nao cadastrada (a tela pediria confirmacao)")
    return d.get("numConta")


def extrair_titulos(dados_upload):
    """Le o campo `titulos` da resposta do upload -> lista de dicts.

    O Smart manda a GRADE PRONTA em base64 (o mesmo HTML que aparece na tela).
    Colunas: 6 do lado do Smart (valor, vencimento, sacado, ACAO TOMADA, STATUS,
    juros/multa) + 13 do lado do arquivo de retorno.
    OBS: o HTML e ISO-8859-1, nao utf-8 (decodificar errado estraga os acentos).
    """
    bruto = (dados_upload or {}).get("titulos") or ""
    if not bruto:
        return []
    try:
        html = base64.b64decode(bruto + "=" * (-len(bruto) % 4)).decode(
            "iso-8859-1", errors="replace")
    except Exception:
        return []

    campos = ["valor_titulo", "vencimento", "sacado", "acao_tomada", "status",
              "juros_multa", "numero_titulo", "valor_titulo_arq", "valor_pago",
              "data_ocorrencia", "banco_cobrador", "agencia_cobradora", "especie",
              "tarifa", "outras_despesas", "iof", "abatimento", "desconto",
              "juros_mora"]
    linhas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        celulas = [re.sub(r"\s+", " ",
                          re.sub(r"<[^>]+>|&nbsp;", " ", c)).strip()
                   for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
        if not any(celulas):
            continue
        linhas.append({campos[i] if i < len(campos) else f"col{i}": v
                       for i, v in enumerate(celulas)})
    return linhas


# "Acao tomada" (grade do upload) -> contador devolvido pelo PROCESSAR_ARQUIVO.
# Serve p/ conferir se o que o arquivo pedia bate com o que o Smart registrou.
MAPA_ACAO_CONTADOR = {
    "entrada confirmada": "confirmacao_entrada",
    "liquidado": "refinan",
    "baixa": "baixa",
    "entrada rejeitada": "entrada_rejeitada",
    "instrucao rejeitada": "instrucao_rejeitada",
    "prorrogacao": "prorrogacao",
    "abatimento concedido": "abatimento_concedido",
}


def conferir_divergencias(acoes, ocorrencias):
    """Compara previsto (grade) x registrado (contador). Retorna lista de avisos.

    NAO e erro fatal - so registro. Visto em 31/07/2026: dois arquivos com 6
    titulos "Entrada Rejeitada" cada na grade e contador 4 e 3. Reprocessar deu
    o MESMO numero, entao nao e "so conta quem mudou de estado" - a causa segue
    desconhecida. Por decisao do usuario o robo segue e apenas registra.
    """
    avisos = []
    for acao, qtd in (acoes or {}).items():
        chave = MAPA_ACAO_CONTADOR.get(_normalizar(acao))
        if not chave:
            continue
        registrado = (ocorrencias or {}).get(chave)
        try:
            registrado = int(registrado)
        except (TypeError, ValueError):
            registrado = 0
        if registrado != qtd:
            avisos.append(f"{acao}: grade={qtd} contador={registrado}")
    return avisos


def _normalizar(texto):
    import unicodedata
    t = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in t if not unicodedata.combining(c)).strip().lower()


def resumo_acoes(titulos):
    """Conta quantos titulos por 'acao tomada' e quantos fora de status OK."""
    acoes, nao_ok = {}, []
    for t in titulos:
        acao = t.get("acao_tomada") or "(sem acao)"
        acoes[acao] = acoes.get(acao, 0) + 1
        if (t.get("status") or "").upper() != "OK":
            nao_ok.append(t)
    return acoes, nao_ok


def enviar(ctx, nome, conteudo, num_conta, origem=""):
    """UPLOAD_ARQUIVO - deixa o arquivo pronto e devolve os dados do passo final.
    NAO efetiva nada (quem efetiva e processar_arquivo)."""
    _post(ctx, {"Acao": "INICIALIZAR_LOG_UPLOAD", "NomeArquivo": nome})
    d = _post(ctx, {"Acao": "UPLOAD_ARQUIVO", "NomeArquivo": nome,
                    "conteudo": conteudo, "origem": origem,
                    "numConta": num_conta or ""})
    if d.get("message") and d.get("message") != "OK":
        raise ErroRetorno(f"upload devolveu {d.get('message')}")
    return d


def processar_arquivo(ctx, nome, dados_upload, origem=""):
    """PROCESSAR_ARQUIVO - E AQUI QUE A BAIXA ACONTECE."""
    _post(ctx, {"Acao": "INICIALIZAR_LOG_PROGRESSO", "NomeArquivo": nome})
    d = _post(ctx, {
        "Acao": "PROCESSAR_ARQUIVO",
        "NomeArquivo": dados_upload.get("nomeArquivoOriginal") or nome,
        "target": dados_upload.get("target") or "",
        "origem": origem,
        "extensao": dados_upload.get("extensaoArquivo") or ".TXT",
        "numContaArquivoRetorno": dados_upload.get("numContaArquivoRetorno") or "",
    })
    return d


def resumo_processamento(resposta):
    """Le a resposta do PROCESSAR_ARQUIVO -> {categoria: quantidade}.

    O Smart devolve um contador por TIPO DE OCORRENCIA (confirmacao_entrada,
    liquidacao, baixa, entrada_rejeitada, prorrogacao, protesto_*, ...), com
    `null` nas que nao ocorreram. Isso e a conferencia do que ele fez de fato.
    """
    ignorar = {"message", "varRetorno2", "dateMsgRetorno", "DifSistema"}
    fora = {}
    for chave, valor in (resposta or {}).items():
        if chave in ignorar or valor in (None, "", 0, "0"):
            continue
        fora[chave] = valor
    return fora


def verificar_criticas(ctx, nome, dados_upload):
    """VERIFICAR_CRITICAS - roda DEPOIS do processamento e lista pendencias."""
    d = _post(ctx, {
        "Acao": "VERIFICAR_CRITICAS",
        "target": (dados_upload or {}).get("target") or "",
        "origem": (dados_upload or {}).get("origem") or "",
        "nomeArquivoOriginal": (dados_upload or {}).get("nomeArquivoOriginal") or nome,
    })
    return d.get("criticas") or []


def soltar_trava(ctx, nome):
    try:
        _post(ctx, {"Acao": "RETIRAR_EM_PROCESSAMENTO", "NomeArquivo": nome})
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# fluxo completo de UM arquivo
# --------------------------------------------------------------------------- #
def processar(ctx, caminho, dry_run=True, pular_se_processado=False,
              aceitar_conta_desconhecida=False, hashes_ja_feitos=None,
              usar_portao=False, modo_deposito=False):
    """Roda a sequencia inteira para um .RET. Retorna dict com o resultado.

    dry_run=True para no passo 6 (upload): valida banco/conta e mostra quantos
    titulos o arquivo tem, SEM dar baixa em nada.

    pular_se_processado=False por decisao do usuario (31/07/2026): reprocessar
    o mesmo arquivo NAO e problema no fluxo dele. A tela pergunta "ja foi
    processado hoje, deseja continuar?" e o operador responde que sim.

    ATENCAO (regra do negocio, 31/07/2026): acontece de chegar arquivo com o
    MESMO NOME no mesmo dia e CONTEUDO DIFERENTE - e ele TEM que ser processado
    como novo. Como o VERIFICAR_ARQUIVO_PROCESSADO do Smart olha so o NOME, ele
    diz "ja processado" nesse caso. Por isso:
      - `ja_processado` aqui e apenas INFORMATIVO;
      - a identidade real do arquivo e o `hash` do conteudo (calculado abaixo),
        que o robo grava no controle. Quem decide pular usa o hash, nunca o nome.

    aceitar_conta_desconhecida=False: quando o retorno nao casa com conta
    cadastrada a tela PERGUNTA se prossegue. Sem gente pra decidir, o padrao e
    pular e reportar - ligar so se o usuario mandar.

    usar_portao=False: confere a grade do upload, TITULO A TITULO, contra o
    que o proprio arquivo mandou ANTES de chamar `processar_arquivo` (ver
    `portao.py` - a ultima defesa contra o BUG-548, a baixa que caiu no
    titulo de OUTRO sacado). Recusa o ARQUIVO INTEIRO quando algum titulo
    diverge - nao filtra linha, porque o Smart processa o .RET completo.

    modo_deposito=False: preserva o retorno bancario normal. Quando True, exige
    o arquivo sintetico com identificador/hash, faz o portao fechar arquivo,
    upload e grade, e so considera processado quando a resposta prova exatamente
    `liquidacao=quantidade`, sem `refinan` nem outro resultado.
    """
    nome = nome_limpo(caminho)
    conteudo = ler_arquivo(caminho)
    normalizado = conteudo.encode("iso-8859-1", "replace")
    with open(caminho, "rb") as arquivo_bruto:
        bruto = arquivo_bruto.read()
    saida = {"arquivo": os.path.basename(caminho), "nome_smart": nome,
             "titulos": 0, "conta": None, "processado": False,
             "ja_processado": False, "motivo": "",
             "passo_irreversivel_chamado": False,
             # IDENTIDADE PELO CONTEUDO, nao pelo nome (ver nota abaixo)
             "hash": hashlib.md5(normalizado).hexdigest(),
             "sha256": hashlib.sha256(bruto).hexdigest()}
    linhas = [l for l in conteudo.splitlines() if l.strip()]
    if not linhas:
        saida["motivo"] = "arquivo vazio"
        return saida
    if len(linhas) > LIMITE_LINHAS:
        saida["motivo"] = f"{len(linhas)} linhas (limite {LIMITE_LINHAS})"
        return saida

    arquivo_deposito = None
    if modo_deposito:
        arquivo_deposito = portao.avaliar_cnab_deposito(linhas)
        sufixo_hash = saida["sha256"][:16].upper()
        if (
            not re.fullmatch(r"DEP\d+[0-9A-F]{16}\.RET", saida["arquivo"])
            or not saida["arquivo"].endswith(f"{sufixo_hash}.RET")
        ):
            arquivo_deposito["liberado"] = False
            arquivo_deposito["erros"].append(
                "nome do arquivo nao carrega o prefixo do SHA-256 do conteudo"
            )
            arquivo_deposito["sumario"] = "; ".join(arquivo_deposito["erros"])
        saida["arquivo_deposito"] = arquivo_deposito
        if not arquivo_deposito["liberado"]:
            veredito = {
                "liberado": False,
                "avaliados": 0,
                "resumo": 0,
                "recusados": [],
                "erros_grade": arquivo_deposito["erros"],
                "sumario": arquivo_deposito["sumario"],
            }
            saida["portao"] = veredito
            saida["estado_final"] = "recusado_portao"
            saida["motivo"] = f"RECUSADO PELO PORTAO: {veredito['sumario']}"
            return saida

    if em_processamento(ctx, nome):
        saida["motivo"] = "ja esta em processamento no Smart"
        return saida

    # informativo: o Smart olha o NOME, entao isto NAO decide nada sozinho
    saida["ja_processado"] = ja_processado(ctx, nome)
    if pular_se_processado and saida["ja_processado"] and hashes_ja_feitos \
            and saida["hash"] in hashes_ja_feitos:
        saida["motivo"] = MOTIVO_JA_PROCESSADO
        saida["estado_final"] = "ja_processado"
        return saida

    try:
        saida["conta"] = validar_banco_conta(ctx, conteudo)
    except ErroRetorno as e:
        if "conta nao cadastrada" in str(e) and aceitar_conta_desconhecida:
            saida["conta"] = None       # a tela seguiria sem conta
            saida["motivo"] = "conta nao cadastrada (seguindo por opcao)"
        else:
            raise

    try:
        dados = enviar(ctx, nome, conteudo, saida["conta"])
        saida["titulos"] = int(dados.get("quantidadeTitulos") or 0)
        # a grade vem PRONTA na resposta do upload: da p/ conferir titulo a
        # titulo (acao tomada / status) ANTES mesmo de processar
        saida["detalhes"] = extrair_titulos(dados)
        saida["acoes"], saida["fora_ok"] = resumo_acoes(saida["detalhes"])
        saida["criticas"] = dados.get("criticas") or []
        saida["data_hora"] = dados.get("dataHora")
        saida["valor_total"] = dados.get("valorTotalTitulos")
        if usar_portao or modo_deposito:
            veredito = portao.avaliar_grade(
                saida["detalhes"],
                exigir_status_ok=modo_deposito,
                quantidade_esperada=saida["titulos"] if modo_deposito else None,
                quantidade_arquivo=(
                    arquivo_deposito["quantidade"] if modo_deposito else None
                ),
                exigir_valor_arquivo=modo_deposito,
                exigir_acao="Liquidado" if modo_deposito else None,
            )
            saida["portao"] = veredito
            if not veredito["liberado"]:
                saida["motivo"] = f"RECUSADO PELO PORTAO: {veredito['sumario']}"
                saida["portao_recusados"] = veredito["recusados"]
                saida["estado_final"] = "recusado_portao"
                return saida
        if dry_run:
            saida["estado_final"] = "dry_run"
            saida["motivo"] = "DRY_RUN (upload e portao validados, sem processar)"
            return saida

        saida["passo_irreversivel_chamado"] = True
        try:
            resultado = processar_arquivo(ctx, nome, dados)
        except Exception as exc:
            if not modo_deposito:
                raise
            saida["estado_final"] = "inconclusivo"
            saida["inconclusivo"] = True
            saida["motivo"] = (
                "RESULTADO INCONCLUSIVO APOS PROCESSAR_ARQUIVO: "
                f"{type(exc).__name__}: {str(exc)[:160]}"
            )
            return saida

        saida["resposta_processamento"] = resultado
        # conferencia do que o Smart FEZ (contador por tipo de ocorrencia)
        saida["ocorrencias"] = resumo_processamento(resultado)
        if modo_deposito:
            confirmacao = portao.avaliar_resultado_deposito(
                resultado, saida["titulos"]
            )
            saida["confirmacao_smart"] = confirmacao
            saida["processado"] = confirmacao["comprovado"]
            saida["inconclusivo"] = not confirmacao["comprovado"]
            saida["estado_final"] = (
                "processado_smart" if confirmacao["comprovado"] else "inconclusivo"
            )
            saida["motivo"] = (
                "OK" if confirmacao["comprovado"]
                else f"RESULTADO INCONCLUSIVO: {confirmacao['sumario']}"
            )
            saida["divergencias"] = confirmacao["erros"]
        else:
            saida["processado"] = (resultado.get("message") or "OK") == "OK"
            saida["motivo"] = resultado.get("message") or "OK"
            saida["divergencias"] = conferir_divergencias(
                saida.get("acoes"), saida["ocorrencias"]
            )
        try:
            saida["criticas"] = verificar_criticas(ctx, nome, dados)
        except ErroRetorno:
            pass
    finally:
        soltar_trava(ctx, nome)

    return saida
