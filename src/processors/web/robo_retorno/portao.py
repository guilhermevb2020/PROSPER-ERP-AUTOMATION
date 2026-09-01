# -*- coding: utf-8 -*-
"""
portao.py - decide, TITULO A TITULO, se a grade do upload pode virar baixa.

POR QUE ELE EXISTE
------------------
O `PROCESSAR_ARQUIVO` e o ultimo passo e o unico irreversivel: depois dele o
titulo esta baixado no Smart. O BUG-548 mostrou o modo de falha caro — a baixa
entrou no titulo de OUTRO sacado. A grade mostrava
`12594-003 / R$ 4.033,33 / CONSORCIO DCDC` para um pagamento que era
`123410C / R$ 6.108,23 / RALTTEK`, e a operacao teve de ser revertida a mao.

O que NAO serve como oraculo (medido, nao suposto):

- **o contador do `dwh`**: com o layout ja corrigido, a verificacao de
  13/08/2026 deu 12 OK e 3 erradas em 15 liquidacoes, e nenhum contador previa
  QUAL erraria (as 3 falhas tinham `nosso numero + documento` = 1 par, e 6 das
  12 corretas tambem);
- **o `status` da grade sozinho**: medido sobre 804 titulos reais de banco
  (`titulos_prod_0408.csv`), `status != OK` aparece em 6 linhas cujo valor
  BATE — sao `DATA DE VENCIMENTO DIFERENTE`, liquidacao legitima. Recusar por
  status barraria 4 dos 79 arquivos reais sem nenhum erro de casamento.

O QUE SERVE
-----------
A grade do upload poe LADO A LADO os dois lados do casamento:

    valor_titulo / vencimento / sacado ....... o titulo que o SMART resolveu
    numero_titulo / valor_titulo_arq / ....... a linha que o ARQUIVO mandou
    valor_pago / data_ocorrencia / ...

Quando o Smart casa a linha no titulo errado, os dois lados DISCORDAM — foi
exatamente o que se viu no BUG-548 (4.033,33 do lado do Smart contra 6.108,23
do lado do arquivo). Nao precisamos reproduzir o criterio de casamento do Smart
(a causa remanescente do BUG-548 e justamente que a nossa base nao o reproduz):
basta LER o que ele decidiu e conferir contra o que mandamos.

Medido sobre 1.242 titulos reais de tres capturas (`titulos_prod_0408.csv`,
`titulos_0508.csv`, `titulos_teste.csv`): `valor_titulo` divergiu de
`valor_titulo_arq` em ZERO linhas legiveis. Como discriminador, o par nao
produz recusa falsa no arquivo que o banco manda.

O QUE ELE NAO FAZ
-----------------
Nao reescreve arquivo. O Smart processa o arquivo INTEIRO, entao o veredito e
por arquivo: se um titulo e recusado, o arquivo nao sobe, e o relato diz QUAL
titulo e POR QUE. Filtrar as linhas boas e recomputar o trailer do CNAB-400
seria fabricar um arquivo terceiro — a mesma classe de defeito do BUG-548 — e,
no arquivo que NOS geramos, e mais barato regerar sem a linha ruim. No arquivo
do banco, apagar linha apaga ocorrencia que ele reportou.

Modulo PURO de proposito: so stdlib, sem playwright e sem `src.common`. E o que
permite testa-lo no host, onde o pytest existe (o container nao o tem).
"""
import re
import unicodedata

# Vereditos
APROVADO = "aprovado"
RECUSADO = "recusado"
RESUMO = "resumo"          # linha do rodape da grade, nao e titulo

# Motivos de recusa (texto estavel: o relato da automação de retorno e o teste citam)
POR_VALOR = "valor no Smart diverge do valor no arquivo"
POR_SEM_CASAMENTO = "o Smart nao resolveu titulo para esta linha"
POR_STATUS = "status diferente de OK"
POR_VALOR_ARQUIVO_ILEGIVEL = "valor do arquivo vazio ou ilegivel"
POR_ACAO = "acao diferente de Liquidado"
POR_GRADE_VAZIA = "grade do upload sem titulo avaliavel"
POR_QUANTIDADE = "quantidade do arquivo, upload e grade divergem"


def _num(texto):
    """'1.234,56' -> 1234.56. Devolve None quando nao da para ler.

    O valor vem da grade em HTML no formato do Brasil. `None` NAO e zero:
    quem chama tem de tratar 'nao consegui ler' como caso proprio, senao um
    campo vazio viraria 'R$ 0,00' e passaria por divergencia.
    """
    if texto is None:
        return None
    limpo = re.sub(r"[^\d,.-]", "", str(texto)).strip()
    if not limpo:
        return None
    # separador decimal do BR: a ULTIMA virgula. Ponto e milhar.
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return round(float(limpo), 2)
    except ValueError:
        return None


def _sem_acento(texto):
    """'Visualizar Titulos' e 'Visualizar Titulos' com acento viram a MESMA coisa.

    O Smart escreve o rotulo do rodape COM acento (`Visualizar Titulos`), e
    comparar contra a forma sem acento deixava o ramo do rotulo inerte: as
    linhas de rodape so eram pegas pelo outro ramo, o do par vazio. Funcionava
    por acaso — o rodape real vem sempre sem `numero_titulo` e sem `status` —
    mas ramo morto dentro de um portao e armadilha para quem mexer depois.
    """
    t = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in t if not unicodedata.combining(c)).strip().lower()


def e_linha_de_resumo(linha):
    """A linha e do bloco de RODAPE da grade, nao um titulo?

    O Smart fecha a grade com um bloco por acao ("Entrada Confirmada 324
    R$ 1.621.341,89 [Visualizar Titulos]"). O `extrair_titulos` le esse bloco
    como se fosse titulo, e as colunas saem TROCADAS: `valor_titulo` fica com o
    nome da acao, `vencimento` com a contagem e `sacado` com o total.

    Medido: 4 linhas assim em `titulos_prod_0408.csv`, todas do
    `CBR643228308202620800.ret`. Sem este filtro elas entram como titulo sem
    status e o portao recusaria o arquivo inteiro por um rodape.

    Dois ramos, e os dois precisam existir: o rotulo (que o Smart escreve COM
    acento — dai o `_sem_acento`) e o par `numero_titulo`/`status` vazios. Nas
    capturas reais quem pega as 4 e o segundo; o primeiro cobre o rodape que
    venha com algum campo preenchido.
    """
    if _sem_acento(linha.get("acao_tomada")) == "visualizar titulos":
        return True
    # o bloco de rodape nao tem numero de titulo nem status
    sem_titulo = not (linha.get("numero_titulo") or "").strip()
    sem_status = not (linha.get("status") or "").strip()
    return sem_titulo and sem_status


def avaliar_titulo(linha, exigir_status_ok=False, exigir_valor_arquivo=False,
                   exigir_acao=None):
    """Um titulo da grade -> (veredito, motivo, detalhe).

    `detalhe` traz os numeros que sustentam a recusa, para o relato nao obrigar
    ninguem a reabrir o CSV.
    """
    if e_linha_de_resumo(linha):
        return RESUMO, "", ""

    smart = _num(linha.get("valor_titulo"))
    arquivo = _num(linha.get("valor_titulo_arq"))

    # o Smart nao achou titulo: o lado dele vem vazio
    if smart is None:
        return (RECUSADO, POR_SEM_CASAMENTO,
                (f"arquivo={linha.get('valor_titulo_arq') or '-'} "
                 f"smart={linha.get('valor_titulo') or '(vazio)'}"))

    if exigir_valor_arquivo and arquivo is None:
        return (RECUSADO, POR_VALOR_ARQUIVO_ILEGIVEL,
                f"arquivo={linha.get('valor_titulo_arq') or '(vazio)'!r}")

    # o par que discrimina o BUG-548
    if arquivo is not None and smart != arquivo:
        return (RECUSADO, POR_VALOR,
                (f"smart={smart:.2f} arquivo={arquivo:.2f} "
                 f"sacado={(linha.get('sacado') or '?')[:28]}"))

    if exigir_status_ok and (linha.get("status") or "").strip().upper() != "OK":
        return (RECUSADO, POR_STATUS,
                f"status={(linha.get('status') or '(vazio)')!r}")

    if exigir_acao and _sem_acento(linha.get("acao_tomada")) != _sem_acento(exigir_acao):
        return (RECUSADO, POR_ACAO,
                f"acao={(linha.get('acao_tomada') or '(vazio)')!r}")

    return APROVADO, "", ""


def avaliar_grade(detalhes, exigir_status_ok=False, quantidade_esperada=None,
                  quantidade_arquivo=None, exigir_valor_arquivo=False,
                  exigir_acao=None):
    """A grade inteira -> veredito do ARQUIVO.

    Args:
        detalhes: `saida["detalhes"]` do upload — a grade titulo a titulo.
        exigir_status_ok: tambem recusa quem tem `status != OK`. Padrao False
            porque, medido em 804 titulos reais, `status != OK` aparece em
            liquidacao legitima (`DATA DE VENCIMENTO DIFERENTE`).

    Returns:
        dict com `liberado` (bool), `avaliados`, `resumo`, `recusados`
        (lista de dicts com titulo/motivo/detalhe) e `sumario` (uma linha).
    """
    recusados, avaliados, resumo = [], 0, 0
    for linha in (detalhes or []):
        veredito, motivo, detalhe = avaliar_titulo(
            linha,
            exigir_status_ok=exigir_status_ok,
            exigir_valor_arquivo=exigir_valor_arquivo,
            exigir_acao=exigir_acao,
        )
        if veredito == RESUMO:
            resumo += 1
            continue
        avaliados += 1
        if veredito == RECUSADO:
            recusados.append({
                "numero_titulo": (linha.get("numero_titulo") or "?").strip(),
                "motivo": motivo,
                "detalhe": detalhe,
                "acao_tomada": (linha.get("acao_tomada") or "").strip(),
            })

    erros_grade = []
    if quantidade_esperada is not None:
        try:
            esperada = int(quantidade_esperada)
        except (TypeError, ValueError):
            esperada = -1
        if esperada <= 0:
            erros_grade.append(
                f"{POR_QUANTIDADE}: upload={quantidade_esperada!r}"
            )
        if avaliados == 0:
            erros_grade.append(POR_GRADE_VAZIA)
        if esperada >= 0 and avaliados != esperada:
            erros_grade.append(
                f"{POR_QUANTIDADE}: upload={esperada} grade={avaliados}"
            )
        if quantidade_arquivo is not None:
            try:
                no_arquivo = int(quantidade_arquivo)
            except (TypeError, ValueError):
                no_arquivo = -1
            if no_arquivo <= 0 or no_arquivo != esperada:
                erros_grade.append(
                    f"{POR_QUANTIDADE}: arquivo={quantidade_arquivo!r} "
                    f"upload={esperada} grade={avaliados}"
                )

    liberado = not recusados and not erros_grade
    if liberado:
        sumario = f"{avaliados} titulo(s) conferido(s), nenhuma divergencia"
    else:
        porque = {}
        for r in recusados:
            porque[r["motivo"]] = porque.get(r["motivo"], 0) + 1
        partes = []
        if recusados:
            partes.append(
                f"{len(recusados)} de {avaliados} titulo(s) recusado(s): "
                + ", ".join(f"{m} ({q})" for m, q in sorted(porque.items()))
            )
        partes.extend(erros_grade)
        sumario = "; ".join(partes)
    return {"liberado": liberado, "avaliados": avaliados, "resumo": resumo,
            "recusados": recusados, "erros_grade": erros_grade,
            "sumario": sumario}


def avaliar_cnab_deposito(linhas):
    """Valida o envelope CNAB-400 fabricado para a baixa por deposito.

    O identificador de 25 digitos em ``[37:62]`` e a chave exata do boleto no
    Smart. Sem ele o Smart cai no nosso numero reciclado entre cedentes.
    """
    registros = list(linhas or [])
    erros = []
    for numero, linha in enumerate(registros, 1):
        if len(linha) != 400:
            erros.append(f"linha {numero} tem {len(linha)} posicoes, esperado 400")

    if len(registros) < 3:
        erros.append("arquivo precisa de cabecalho, detalhe e trailer")
        detalhes = []
    else:
        if not registros[0].startswith("0"):
            erros.append("cabecalho CNAB nao inicia com registro 0")
        if not registros[-1].startswith("9"):
            erros.append("trailer CNAB nao inicia com registro 9")
        detalhes = registros[1:-1]

    if not detalhes:
        erros.append("arquivo sem detalhe CNAB")
    for numero, linha in enumerate(detalhes, 2):
        if not linha.startswith("1"):
            erros.append(f"linha {numero} nao e detalhe tipo 1")
            continue
        identificador = linha[37:62] if len(linha) >= 62 else ""
        if not re.fullmatch(r"\d{25}", identificador):
            erros.append(
                f"linha {numero} sem identificador CNAB de 25 digitos em [37:62]"
            )

    return {
        "liberado": not erros,
        "quantidade": len(detalhes),
        "erros": erros,
        "sumario": (
            f"{len(detalhes)} detalhe(s) CNAB valido(s)"
            if not erros else "; ".join(erros)
        ),
    }


def _contador_inteiro(valor):
    """Contador do Smart como inteiro; ausente e zero, ilegivel e inconclusivo."""
    if valor in (None, "", False):
        return 0
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def avaliar_resultado_deposito(resposta, quantidade_esperada):
    """A resposta pos-passo irreversivel prova exatamente as baixas pedidas?"""
    erros = []
    if not isinstance(resposta, dict):
        return {
            "comprovado": False,
            "erros": ["resposta do PROCESSAR_ARQUIVO nao e objeto JSON"],
            "sumario": "resposta do PROCESSAR_ARQUIVO nao e objeto JSON",
        }

    if resposta.get("message") != "OK":
        erros.append(f"message={resposta.get('message')!r}, esperado 'OK'")

    try:
        esperada = int(quantidade_esperada)
    except (TypeError, ValueError):
        esperada = -1
    liquidacao = _contador_inteiro(resposta.get("liquidacao"))
    refinan = _contador_inteiro(resposta.get("refinan"))
    if esperada <= 0 or liquidacao != esperada:
        erros.append(f"liquidacao={liquidacao!r}, esperado {esperada}")
    if refinan != 0:
        erros.append(f"refinan={refinan!r}, esperado 0")

    ignorar = {
        "message", "varRetorno2", "dateMsgRetorno", "DifSistema",
        "liquidacao", "refinan",
    }
    outros = []
    for chave, valor in resposta.items():
        if chave in ignorar:
            continue
        contador = _contador_inteiro(valor)
        if contador is None or contador != 0:
            outros.append(f"{chave}={valor!r}")
    if outros:
        erros.append("outros resultados: " + ", ".join(sorted(outros)))

    return {
        "comprovado": not erros,
        "erros": erros,
        "sumario": "baixa comprovada pelo Smart" if not erros else "; ".join(erros),
    }
