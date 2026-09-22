# -*- coding: utf-8 -*-
"""
emissao_evidencia.py - guarda o que a emissao produziu, para dar para conferir.

POR QUE EXISTE
--------------
Ate 21/08/2026 a emissao respondia "quantos titulos sumiram da lista de
pendentes" e nada mais: o `boleto_emissao_log` gravava CONTAGEM, os IDs nunca
eram persistidos (o core devolve `ids`, o log nao recebia), e o PDF devolvido
pelo POST de impressao era descartado depois de olhar o content-type.

Resultado pratico, medido num caso real: chegou um boleto do Banco do Brasil
impresso em nome do CEDENTE (conta BB e grupo convencional, que a nossa
configuracao manda imprimir em nome da SECURITIZADORA) e nao havia como
responder "foi a nossa automacao que emitiu isto?" — nem qual titulo, nem com
que parametro, nem o documento.

Este modulo fecha esse buraco: grava o PDF e um manifesto ao lado dele.

DESENHO
-------
- **Stdlib pura.** Nenhum import do projeto, nenhuma dependencia externa. E o
  que permite testar no HOST (`tests/unit/test_emissao_evidencia.py`), onde
  playwright/psycopg2 nao existem. Mesmo motivo do `retorno_cobranca/portao.py`.
- **Best-effort, sempre.** Nada aqui pode derrubar uma emissao: quem chama
  envolve em try/except e o `salvar()` ja engole o proprio erro devolvendo
  None. Perder a evidencia e ruim; perder a emissao e pior.
- **Nao decide nada.** Nao valida, nao recusa, nao muda o que e enviado ao
  Smart. So registra. A conferencia e humana, olhando o PDF.

CONTEUDO SENSIVEL
-----------------
O PDF tem nome, CNPJ e valor do sacado. Fica em `data/boletos/emitidos/`, que
e volume do projeto (nao vai para o git: `data/` nao e versionado). Guardar por
tempo indeterminado e decisao do dono — ha `limpar_antigos()` para quando essa
decisao existir.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

# Extensao pelo content-type do que o Smart devolveu. Nao e cosmetico: um
# `.html` na pasta e o sinal visivel de que a impressao NAO produziu boleto —
# o Smart responde HTTP 200 com pagina de erro, e antes disso ninguem via.
_EXTENSAO = {"pdf": "pdf", "html": "html", "text": "html"}


def extensao_de(content_type: str) -> str:
    """'application/pdf' -> 'pdf'; qualquer outra coisa -> 'html' (ou 'bin')."""
    ct = (content_type or "").lower()
    for chave, ext in _EXTENSAO.items():
        if chave in ct:
            return ext
    return "bin"


def eh_pdf(content_type: str) -> bool:
    """A resposta da impressao e mesmo um PDF?

    O `emitir_lote` gravava `status='ok'` sem nunca olhar isto. Uma pagina de
    erro do Smart (HTTP 200, text/html) entrava no log como sucesso.
    """
    return "pdf" in (content_type or "").lower()


def nome_base(*, conta_id: str, grupo: str, quando: datetime | None = None) -> str:
    """Nome do arquivo, legivel e ordenavel: HHMMSS_<conta>_<grupo>."""
    q = quando or datetime.now()
    conta = "".join(c for c in str(conta_id) if c.isalnum()) or "sem-conta"
    return f"{q.strftime('%H%M%S')}_{conta}_{grupo}"


def pasta_do_dia(base_dir: str, quando: datetime | None = None) -> str:
    """<base>/AAAA-MM-DD — um diretorio por dia, que e como se procura depois."""
    q = quando or datetime.now()
    return os.path.join(base_dir, q.strftime("%Y-%m-%d"))


def montar_manifesto(
    *,
    conta_id: str,
    conta_label: str,
    grupo: str,
    radio: str,
    classes: list[str],
    ids: list[str],
    content_type: str,
    corpo_enviado: str = "",
    run_id: str = "",
    quando: datetime | None = None,
) -> dict:
    """O que a gente precisa saber depois, olhando so a pasta.

    `radio` e `corpo_enviado` sao o coracao disto: registram o parametro que
    DECIDE o nome impresso no boleto (`ImprimirBoletoEmNome`) e o corpo exato
    do POST. Com o PDF ao lado, da para dizer se o que pedimos foi o que saiu.
    """
    return {
        "quando": (quando or datetime.now()).isoformat(timespec="seconds"),
        "run_id": run_id,
        "conta_id": str(conta_id),
        "conta_label": conta_label,
        "grupo": grupo,
        "radio_em_nome": radio,
        "classes_risco": list(classes),
        "ids_titulos": list(ids),
        "qtd_titulos": len(ids),
        "content_type": content_type,
        "resposta_eh_pdf": eh_pdf(content_type),
        "corpo_enviado": corpo_enviado,
    }


def salvar(
    conteudo: bytes,
    manifesto: dict,
    *,
    base_dir: str,
    conta_id: str,
    grupo: str,
    quando: datetime | None = None,
) -> str | None:
    """Grava resposta + manifesto. Devolve o caminho do documento, ou None.

    NUNCA levanta: falhar em gravar evidencia nao pode derrubar a emissao.
    """
    try:
        q = quando or datetime.now()
        pasta = pasta_do_dia(base_dir, q)
        os.makedirs(pasta, exist_ok=True)
        base = nome_base(conta_id=conta_id, grupo=grupo, quando=q)
        ext = extensao_de(manifesto.get("content_type", ""))
        caminho = os.path.join(pasta, f"{base}.{ext}")
        with open(caminho, "wb") as fh:
            fh.write(conteudo or b"")
        manifesto = dict(manifesto)
        manifesto["arquivo"] = caminho
        manifesto["bytes"] = len(conteudo or b"")
        with open(os.path.join(pasta, f"{base}.json"), "w", encoding="utf-8") as fh:
            json.dump(manifesto, fh, ensure_ascii=False, indent=2)
        return caminho
    except Exception:                                               # noqa: BLE001
        return None


def limpar_antigos(base_dir: str, dias: int, hoje: datetime | None = None) -> int:
    """Apaga pastas de dia com mais de `dias`. Devolve quantas apagou.

    Existe para quando houver decisao de retencao — nao e chamado por ninguem
    ainda, de proposito: apagar boleto de cliente e ato do dono, nao efeito
    colateral de uma rodada.
    """
    import shutil

    if dias <= 0:
        return 0
    ref = (hoje or datetime.now()).date()
    apagadas = 0
    try:
        for nome in sorted(os.listdir(base_dir)):
            caminho = os.path.join(base_dir, nome)
            if not os.path.isdir(caminho):
                continue
            try:
                dia = datetime.strptime(nome, "%Y-%m-%d").date()
            except ValueError:
                continue
            if (ref - dia).days > dias:
                shutil.rmtree(caminho, ignore_errors=True)
                apagadas += 1
    except FileNotFoundError:
        return 0
    return apagadas
