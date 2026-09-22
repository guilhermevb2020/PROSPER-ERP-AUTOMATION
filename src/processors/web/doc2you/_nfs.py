# -*- coding: utf-8 -*-
"""NF (DANFEs) de uma operação do Smart — versão ASYNC p/ o robô do doc2you.

Espelha `credito/subfluxos.baixar_nf`, HTTP puro (mais simples que os anexos —
não tem a indireção do iframe): o endpoint devolve o PDF direto.

  GET /smart/operacaoajax/web/gerardanfes.php?NumOperacao=<op>  → application/pdf
      (todas as DANFEs da operação num PDF só)

Destino: CADASTRO/LASTRO DAS OPERACOES/nf operacao/NFE<op>.pdf  (flat, 1 por operação
— mesmo padrão do robô de crédito). Skip-existing: não re-baixa o que já está lá.
"""
import os

SMART = os.getenv("DOC2YOU_SMART_HOST", "https://wvw.smartsecurities.com.br").rstrip("/")
URL_NF = SMART + "/smart/operacaoajax/web/gerardanfes.php?NumOperacao={op}"
NC_SUBPASTA = os.getenv("DOC2YOU_NF_SUBPASTA", "nf operacao")


async def obter_nf(ctx, op: str):
    """(bytes, None) da NF da operação, ou (None, motivo). Best-effort."""
    r = await ctx.request.get(URL_NF.format(op=op), timeout=120000)
    b = await r.body()
    if r.status == 200 and b[:4] == b"%PDF":
        return b, None
    ct = (r.headers or {}).get("content-type", "")
    return None, f"status={r.status} ct={ct} ({len(b)}B)"


async def baixar_op(ctx, op: str, uploader, existentes: set) -> tuple:
    """Baixa a NF da operação (se ainda não estiver no Nextcloud) e sobe.

    `existentes` = nomes já presentes em `nf operacao/` (pré-carregados 1× pelo
    chamador, pois a pasta é flat/compartilhada). Retorna (novo, pulado, sem_nf, erro),
    cada um 0/1. Nunca levanta exceção (é rede de segurança, não pode derrubar o run)."""
    op = str(op).strip()
    if not op.isdigit():
        return 0, 0, 0, 0
    nome = f"NFE{op}.pdf"
    if nome in existentes:
        return 0, 1, 0, 0
    try:
        b, motivo = await obter_nf(ctx, op)
    except Exception as e:
        print(f"  [nf op{op}] erro ao baixar: {type(e).__name__}: {e}", flush=True)
        return 0, 0, 0, 1
    if b is None:
        # Operação pode não ter NF (ex.: lastro que não é duplicata) — não é erro fatal.
        print(f"  [nf op{op}] sem NF ({motivo})", flush=True)
        return 0, 0, 1, 0
    try:
        st = uploader.enviar(b, NC_SUBPASTA, nome)
    except Exception as e:
        print(f"  [nf op{op}] upload erro: {type(e).__name__}: {e}", flush=True)
        return 0, 0, 0, 1
    if st in (201, 204):
        print(f"  nf -> {NC_SUBPASTA}/{nome} ({len(b)}B)", flush=True)
        return 1, 0, 0, 0
    print(f"  [nf op{op}] Nextcloud http {st}", flush=True)
    return 0, 0, 0, 1
