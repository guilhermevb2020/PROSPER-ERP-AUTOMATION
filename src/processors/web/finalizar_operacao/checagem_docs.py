# -*- coding: utf-8 -*-
"""
checagem_docs.py - CHECAGEM 1 do job finalizar_operacao: os documentos que compoem a operacao
foram devidamente ASSINADOS?

REUSA o endpoint do doc2you ja mapeado no verificar_docs.py (pacote de origem) e aperta a
regra em tres pontos, todos descobertos ao vivo em 28/08/2026 (ops 64887/64882):

1. ASSINADO, nao so EMITIDO. La o criterio e "o documento existe"; aqui e
   "existe E esta assinado" (status Concluido no doc2you).

2. A COLUNA "Tipo" DO DOC2YOU NAO SERVE p/ identificar o documento: ela chama de
   "Contrato" TRES coisas diferentes - o Aditivo, a Letra de Cambio e a Carta de
   Cessao. Quem identifica de verdade e o PREFIXO DO ARQUIVO PDF:
       ReciboCliente*          -> Aditivo
       ModeloNotaPromissoria*  -> Nota promissoria
       DUPLICATA*              -> Duplicata
       LCB*                    -> Letra de cambio
       CartadeCessaoCreditos*  -> Carta de cessao
   Confiar na coluna "Tipo" fazia a op 64882 (que TEM letra de cambio) ser
   reprovada por "letra de cambio nao emitida", e contava 14 "Aditivos" onde
   havia 1 Aditivo + 12 cartas de cessao + 1 LCB.

3. O ADITIVO nunca fica "Concluido", porque a assinatura da Prosper e feita
   depois. Entao o criterio dele e assinante a assinante: se todos os que NAO
   sao a Prosper ja assinaram, libera.

Custo: o prefixo do PDF so aparece no DETALHE de cada documento (1 request por
documento). Por isso a resolucao e PREGUICOSA - o Aditivo/NPP/Duplicata saem de
graca (tipo + descricao) e so os "Contrato sem descricao" (LCB vs Carta de
Cessao) sao abertos, e mesmo assim so quando a operacao tem titulo LCB.

Uso isolado (read-only, precisa da sessao deste job no ar):
  python finalizar_operacao/checagem_docs.py --op 64887
"""
import argparse
import os
import re
import sys
import time
import unicodedata

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)
for _p in (_AQUI, os.path.join(_RAIZ, "operacoes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import r7_config as cfg          # noqa: E402
import verificar_docs as vd      # noqa: E402  (endpoint doc2you)


def _norm(s):
    """minusculas, sem acento, espacos colapsados."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def _assinado(doc):
    """True se o documento esta ASSINADO no doc2you.

    Usa o `status_code` (atributo data-statusdocumento da linha), que e o campo
    confiavel: C=Concluido, P=Pendente, I=Ignorado. O status TEXTUAL vem VAZIO
    nos ignorados, e tratar vazio como "nao assinado" fazia o job barrar
    operacao boa (descoberto em 31/08/2026 auditando ops ja finalizadas: 35 de
    104 documentos eram 'I'). O texto fica so como reserva se o code faltar.
    """
    code = (doc.get("status_code") or "").strip().upper()
    if code:
        return code == "C"
    return _norm(doc.get("status")) in tuple(_norm(x) for x in cfg.STATUS_ASSINADO)


def _ignorado(doc):
    """True se o documento foi IGNORADO no doc2you (regerado/substituido).

    Ignorado NAO faz mais parte da operacao: nao conta como pendente nem como
    assinado - sai da conta inteira. Se sobrar so ignorado de um tipo exigido,
    o documento e tratado como NAO EMITIDO, que e o certo.
    """
    return (doc.get("status_code") or "").strip().upper() == "I"


_ROTULO = {"aditivo": "Aditivo", "nota_promissoria": "Nota promissoria",
           "duplicata": "Duplicata", "letra_cambio": "Letra de cambio",
           "carta_cessao": "Carta de cessao"}


# --------------------------------------------------------------------------- #
# Sessao no doc2you
# --------------------------------------------------------------------------- #
def _autenticado(corpo):
    """True se a resposta do doc2you veio da sessao AUTENTICADA.

    Deslogado, o doc2you devolve HTTP 200 com uma landing estatica de ~37KB
    (identica p/ qualquer operacao) que contem 'login' e NAO tem o menu. Logado,
    a pagina de resultados traz o menu com 'Sair'. Sem esta checagem, "0
    documentos" por sessao caida seria confundido com "a op nao tem documentos".
    """
    return "Sair" in corpo and "acessarLicenca" not in corpo


def sso_doc2you(ctx, esperar_ms=8000, tentativas=3):
    """Estabelece a sessao no doc2you via SSO do Smart (smart/doc2you.php).

    ATENCAO: NAO usar wait_until='domcontentloaded' (o que o verificar_docs faz) - o
    doc2you.php e um redirect JS que nao dispara esse evento, o goto estoura os
    60s de timeout e o SSO nunca acontece. 'commit' + espera funciona.

    Mesmo com 'commit' a navegacao as vezes pendura (Chrome carregado / sessao
    ocupada), entao TENTA DE NOVO: um SSO que falha derruba a checagem de
    documentos da op inteira.
    """
    for i in range(1, tentativas + 1):
        pg = ctx.new_page()
        pg.on("dialog", lambda d: d.accept())
        try:
            pg.goto(vd.SSO_URL, wait_until="commit", timeout=30_000)
            pg.wait_for_timeout(esperar_ms)
            return True
        except Exception as e:
            print(f"  [doc2you] SSO tentativa {i}/{tentativas} falhou: {str(e)[:80]}")
        finally:
            try:
                pg.close()
            except Exception:
                pass
        time.sleep(4)
    return False


def _post_doc2you(ctx, op, tentativas=3):
    """POST no doc2you com retentativa de REDE.

    Duas falhas diferentes derrubam essa consulta e precisam de tratamento
    diferente: sessao caida (resolve com SSO) e conexao caida ('socket hang up',
    visto em 01/09/2026 na op 65030). Sem retentar a segunda, um soluco de rede
    reprovava a checagem de documentos da op inteira.
    """
    ultimo = None
    for i in range(1, tentativas + 1):
        try:
            r = ctx.request.post(vd.URL, form=vd._body(op), timeout=60_000)
            return r.body().decode("utf-8", errors="replace")
        except Exception as e:
            ultimo = e
            print(f"  [doc2you] consulta tentativa {i}/{tentativas} falhou: {str(e)[:80]}")
            if i < tentativas:
                time.sleep(3 * i)
    raise ultimo


def _consultar(ctx, op, tentar_sso=True):
    """POST no doc2you + parse dos documentos, guardando tambem o LINK de cada
    linha (e por ele que se chega ao detalhe). Se a sessao estiver caida, faz o
    SSO e tenta UMA vez mais."""
    html = _post_doc2you(ctx, op)
    if not _autenticado(html) and tentar_sso:
        print("  [doc2you] sessao nao autenticada -> fazendo SSO e repetindo")
        sso_doc2you(ctx)
        html = _post_doc2you(ctx, op)
    if not _autenticado(html):
        raise RuntimeError(
            "doc2you continua DESLOGADO apos o SSO - nao da p/ confiar no "
            "resultado (0 documentos aqui nao significa 'op sem documentos')")
    docs = vd.parse_documentos(html)
    links = {}
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", html, re.I | re.S):
        m = re.search(r"name='chk'[^>]*value='(\d+)'", tr, re.I)
        if not m:
            continue
        achados = re.findall(r"href=[\"']([^\"']+)[\"']", tr, re.I)
        links[m.group(1)] = [a for a in achados
                             if a and a.strip() not in ("#", "javascript:;")]
    for d in docs:
        d["links"] = links.get(d["idDoc"], [])
    return docs, html


# --------------------------------------------------------------------------- #
# Detalhe do documento (assinantes + nome do PDF) - com cache por idDoc
# --------------------------------------------------------------------------- #
def _url_detalhe(doc):
    for link in doc.get("links") or []:
        if link.startswith("/documento/visualizar"):
            return "https://www.doc2you.com.br" + link
        if "doc2you.com.br/documento/visualizar" in link:
            return link
    return None


def detalhe(ctx, doc, cache=None):
    """HTML da tela de detalhe do documento (ou None). Usa cache por idDoc."""
    if cache is not None and doc["idDoc"] in cache:
        return cache[doc["idDoc"]]
    url = _url_detalhe(doc)
    html = None
    if url:
        try:
            r = ctx.request.get(url, timeout=45_000)
            if r.status == 200:
                html = r.body().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  [docs] falha ao abrir o detalhe do idDoc {doc['idDoc']}: {e}")
    if cache is not None:
        cache[doc["idDoc"]] = html
    return html


# prefixo do arquivo PDF -> documento. E o unico identificador confiavel.
_PREFIXO_PDF = [
    ("aditivo",          r"^recibocliente"),
    ("nota_promissoria", r"^modelonotapromissoria"),
    ("duplicata",        r"^duplicata"),
    ("letra_cambio",     r"^lcb"),
    ("carta_cessao",     r"^cartadecessao"),
]


def prefixo_pdf(html):
    """Prefixo alfabetico do nome do arquivo PDF do documento (minusculo)."""
    for m in re.finditer(r"([A-Za-z0-9_.-]+\.pdf)", html or ""):
        base = m.group(1)
        if "pdfviewer" in base.lower():
            continue
        p = re.match(r"([A-Za-z]+)", base)
        return (p.group(1) if p else "").lower()
    return ""


def _classificar(doc):
    """Classificacao BARATA (so tipo + descricao da lista), sem request extra.
    Devolve o nome canonico ou None quando e ambiguo (tipo 'Contrato' sem
    descricao: pode ser Letra de cambio OU Carta de cessao)."""
    tipo = _norm(doc.get("tipo"))
    desc = _norm(doc.get("descricao"))
    if tipo.startswith("nota promiss"):
        return "nota_promissoria"
    if tipo == "duplicata":
        return "duplicata"
    if tipo == "contrato":
        if "aditivo de securit" in desc:
            return "aditivo"
        return None          # ambiguo -> so o PDF resolve
    return None


def classificar_com_detalhe(ctx, doc, cache=None):
    """Classificacao EXATA pelo prefixo do PDF (1 request, com cache)."""
    barato = _classificar(doc)
    if barato:
        return barato
    html = detalhe(ctx, doc, cache)
    if not html:
        return None
    pre = prefixo_pdf(html)
    for canonico, padrao in _PREFIXO_PDF:
        if re.search(padrao, pre):
            return canonico
    return None


# --------------------------------------------------------------------------- #
# EXCECAO DO ADITIVO: "falta so a Prosper assinar" nao reprova
# --------------------------------------------------------------------------- #
_ASSINOU = re.compile(r"assinad|conclu|finalizad", re.I)
_NAO_ASSINOU = re.compile(r"pendent|aguardand|nao assinad|não assinad", re.I)


def _so_digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def _e_prosper(assinante, nome_cedente=None):
    """True se o assinante e a PROSPER (a unica cuja assinatura pode faltar).

    Aceita o dict de parse_assinantes ou uma string (nome), p/ compatibilidade.

    A identificacao boa e pelo PAPEL: na tabela do doc2you a Prosper e a
    'Contratada'; o cedente e seus representantes sao 'Contratante' e os
    avalistas 'Avalista'. O CNPJ e a segunda prova. O nome so entra como ultimo
    recurso, porque e o criterio mais fragil.

    TRAVA: se o nome bate com o CEDENTE da operacao, e terceiro - mesmo que
    contenha "prosper" (ex.: cedente "PROSPERIDADE COMERCIO").
    """
    if isinstance(assinante, dict):
        papel = _norm(assinante.get("papel"))
        nome = assinante.get("nome") or ""
        doc = _so_digitos(assinante.get("documento"))
        if papel and papel in [_norm(x) for x in cfg.PAPEIS_PROSPER]:
            return True
        if papel and papel in [_norm(x) for x in cfg.PAPEIS_TERCEIRO]:
            return False          # Contratante/Avalista NUNCA e a Prosper
        if doc and doc in [_so_digitos(c) for c in cfg.CNPJ_PROSPER]:
            return True
    else:
        nome = assinante

    t = _norm(nome)
    if nome_cedente:
        c = _norm(nome_cedente)
        if c and (c in t or t in c):
            return False
    return any(_norm(marca) in t for marca in cfg.ASSINANTES_PROSPER)


def _limpar(s):
    """Tira lixo de borda (o doc2you envolve os nomes em caracteres estranhos)."""
    return re.sub(r"^[^0-9A-Za-zÀ-ÿ]+|[^0-9A-Za-zÀ-ÿ.]+$", "", str(s or "")).strip()


def parse_assinantes(html):
    """Assinantes do documento, como dicts:
        {nome, documento, email, papel, situacao}

    A tabela do doc2you tem as colunas:
        Nome | CPF/CNPJ | E-mail | (2 vazias) | Papel | Situacao
    onde Papel e 'Contratante' (o cedente e seus representantes), 'Avalista'
    ou 'Contratada' (a PROSPERE SECURITIZADORA).

    NAO adivinhar o nome pegando "a celula mais longa": o e-mail costuma ser
    mais longo que o nome, e ai um cedente com e-mail tipo
    contato@prosperplasticos.com.br seria lido como "Prosper" e sua assinatura
    faltante seria ignorada - a operacao sairia sem a assinatura do cedente.
    """
    assinantes = []
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", html or "", re.I | re.S):
        tds = vd._td_textos(tr)
        if len(tds) < 3:
            continue
        # a situacao e a ULTIMA celula que casa assinado/pendente
        idx = None
        for i, t in enumerate(tds):
            if _ASSINOU.search(t) or _NAO_ASSINOU.search(t):
                idx = i
        if idx is None:
            continue
        assinantes.append({
            "nome": _limpar(tds[0])[:80],
            "documento": _limpar(tds[1])[:24] if len(tds) > 1 else "",
            "email": next((t for t in tds if "@" in t), ""),
            "papel": _limpar(tds[idx - 1])[:24] if idx >= 1 else "",
            "situacao": _limpar(tds[idx])[:24],
        })
    return assinantes


def avaliar_excecao_prosper(ctx, rotulo, docs_pendentes, nome_cedente=None, cache=None):
    """Aplica a excecao "falta so a Prosper". Retorna (ok: bool, detalhe: str)."""
    if cfg.MODO_ADITIVO == "so_existe":
        return True, f"{rotulo}: modo so_existe - basta o documento existir"

    faltando = []
    for doc in docs_pendentes:
        html = detalhe(ctx, doc, cache)
        assinantes = parse_assinantes(html) if html else None
        if not assinantes:
            print(f"  [docs] {rotulo} idDoc={doc['idDoc']}: nao li os assinantes "
                  "-> caindo p/ 'so_existe' nesta op (VERIFICAR na mao)")
            return True, f"{rotulo}: assinantes ilegiveis - aceito por existir (VERIFICAR)"
        faltando += [
            f"{a['nome']} [{a['papel'] or 'sem papel'}] {a['situacao']}"
            for a in assinantes
            if _NAO_ASSINOU.search(a["situacao"]) and not _e_prosper(a, nome_cedente)]

    if faltando:
        return False, (f"{rotulo}: falta assinatura de terceiro(s) -> "
                       + "; ".join(faltando[:4]))
    return True, f"{rotulo}: so a Prosper pendente - liberado"


# --------------------------------------------------------------------------- #
# Regra: quais documentos a operacao precisa ter
# --------------------------------------------------------------------------- #
def documentos_exigidos(tipos_titulos):
    tipos = {str(t or "").strip().upper() for t in (tipos_titulos or [])}
    exigidos = ["aditivo", "nota_promissoria"]
    if tipos & set(cfg.TIPOS_COM_DUPLICATA):
        exigidos.append("duplicata")
    if tipos & set(cfg.TIPOS_COM_LETRA_CAMBIO):
        exigidos.append("letra_cambio")
    return exigidos


def conferir(ctx, op, tipos_titulos=None, fazer_sso=True, nome_cedente=None):
    """Confere os documentos da op no doc2you.

    nome_cedente: TRAVA na excecao do Aditivo - um assinante com o nome do
    cedente e sempre terceiro, mesmo que o nome contenha "prosper".

    Retorna {"ok", "pendencias", "observacoes", "exigidos", "encontrados",
             "tipos_brutos", "total_docs"}.
    """
    op = str(op)
    docs, _html = _consultar(ctx, op, tentar_sso=fazer_sso)
    cache = {}
    exigidos = documentos_exigidos(tipos_titulos)

    # 1) classificacao BARATA (sem request extra)
    for d in docs:
        d["canonico"] = _classificar(d)

    # 2) resolve os AMBIGUOS (Contrato sem descricao: LCB vs Carta de cessao)
    #    so quando algum documento exigido ainda nao apareceu. Para assim que
    #    encontrar - normalmente 1 request, nao um por documento.
    ambiguos = [d for d in docs if d["canonico"] is None and not _ignorado(d)]
    faltantes = [c for c in exigidos if not any(d["canonico"] == c for d in docs)]
    if ambiguos and faltantes:
        print(f"  [docs] {len(ambiguos)} documento(s) ambiguo(s); procurando "
              f"{', '.join(_ROTULO[f] for f in faltantes)} pelo nome do PDF...")
        for i, d in enumerate(ambiguos, 1):
            d["canonico"] = classificar_com_detalhe(ctx, d, cache)
            faltantes = [c for c in exigidos if not any(x["canonico"] == c for x in docs)]
            if not faltantes:
                print(f"  [docs] resolvido apos abrir {i} de {len(ambiguos)}")
                break

    # 3) agrega por documento canonico. Documento IGNORADO sai da conta.
    encontrados = {}
    ignorados = 0
    for d in docs:
        canonico = d.get("canonico")
        if not canonico:
            continue
        if _ignorado(d):
            ignorados += 1
            continue
        alvo = encontrados.setdefault(
            canonico, {"total": 0, "assinados": 0, "pendentes": [], "docs_pendentes": []})
        alvo["total"] += 1
        if _assinado(d):
            alvo["assinados"] += 1
        else:
            alvo["pendentes"].append(f"{d.get('status') or 'sem status'}"
                                     f" ({d.get('descricao') or d['idDoc']})")
            alvo["docs_pendentes"].append(d)

    # 4) veredito
    pendencias, observacoes = [], []
    for canonico in exigidos:
        rot = _ROTULO[canonico]
        info = encontrados.get(canonico)
        if not info or info["total"] == 0:
            pendencias.append(f"{rot}: NAO foi emitido (nao existe no doc2you)")
            continue
        if info["assinados"] >= info["total"]:
            continue
        faltam = info["total"] - info["assinados"]
        if canonico in cfg.ASSINATURA_PROSPER_OPCIONAL:
            ok, det = avaliar_excecao_prosper(ctx, rot, info["docs_pendentes"],
                                              nome_cedente, cache)
            observacoes.append(det)
            if not ok:
                pendencias.append(det)
            continue
        pendencias.append(f"{rot}: {faltam} de {info['total']} SEM assinatura -> "
                          + "; ".join(info["pendentes"][:3]))

    return {
        "ok": not pendencias,
        "pendencias": pendencias,
        "observacoes": observacoes,
        "exigidos": exigidos,
        "encontrados": encontrados,
        "tipos_brutos": sorted({d.get("tipo", "") for d in docs if d.get("tipo")}),
        "ignorados": ignorados,
        "total_docs": len(docs),
        "nao_classificados": sum(1 for d in docs if not d.get("canonico")),
    }


def main():
    ap = argparse.ArgumentParser(description="Checa se os documentos da op estao assinados (doc2you).")
    ap.add_argument("--op", required=True)
    ap.add_argument("--cdp", default=str(cfg.CDP_PORT))
    ap.add_argument("--tipos", default="",
                    help="tipos dos titulos separados por virgula (ex.: LCB,DUR). "
                         "Vazio = le da tela da operacao.")
    ap.add_argument("--cedente", default="", help="nome do cedente (trava da excecao do Aditivo)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp}")
        except Exception as e:
            print(f"[ERRO] CDP {args.cdp} nao responde: {e}\n"
                  "       Sem Chrome deste job no ar: a sessao so existe durante uma rodada (smart_sessao.sessao)")
            return 2
        ctx = browser.contexts[0]

        tipos = [t.strip() for t in args.tipos.split(",") if t.strip()]
        if not tipos:
            import classe_risco_tool as crt
            from smart_session import Smart
            dados = crt.carregar_operacao(Smart.attach(ctx), args.op)
            tipos = [t.get("tipoTitulo", "") for t in dados["titulos"]]
            print(f"  tipos dos titulos (da tela): {sorted(set(tipos))}")

        r = conferir(ctx, args.op, tipos, nome_cedente=args.cedente or None)

    print(f"\n=== DOCUMENTOS op {args.op} | {r['total_docs']} no doc2you ===")
    print(f"  exigidos: {[_ROTULO[e] for e in r['exigidos']]}")
    for canonico, info in r["encontrados"].items():
        print(f"  - {_ROTULO[canonico]:<18} {info['assinados']}/{info['total']} assinado(s)")
    if r["nao_classificados"]:
        print(f"  ({r['nao_classificados']} documento(s) nao classificado(s) - nao exigidos)")
    for obs in r.get("observacoes", []):
        print(f"  * {obs}")
    if r["ok"]:
        print("\n  >> OK: todos os documentos exigidos estao ASSINADOS.")
    else:
        print("\n  >> PENDENCIAS:")
        for pnd in r["pendencias"]:
            print(f"     - {pnd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
