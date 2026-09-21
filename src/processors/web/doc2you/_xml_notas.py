# -*- coding: utf-8 -*-
"""XMLs das notas operadas no dia (Smart → Financeiro → Monitoramento de Notas).

HTTP puro (sem tela), na sessão já logada do robô doc2you. Fluxo mapeado 03/08/2026
(ver process-automation `tmp/docs/DOWNLOAD_XML_MONITORAMENTO_NOTAS.md`):

  1. LISTAR (paginado, 50/pág):
     GET financeiro/gridmonitoramentonota.php?page=N&datainicioOPFinalizada=..&datafimOPFinalizada=..&...
     → cada checkbox: value=idNfe, data-tiponota=NFe.
     ⚠️ ARMADILHA: página ALÉM da última repete a última (HTTP 200) → parar quando
       nenhum id novo aparece (não confiar em "página vazia" nem em "<50 linhas").
  2. PEDIR ZIP:
     POST financeiro/gridmonitoramentonotaajax.php  acao=GET_LINK_FILE_ZIP&idNotas=<id@tipo,...>
     → {"status":"OK","link":"temp\\/3912_..zip"}
  3. BAIXAR: GET financeiro/<link> → application/zip; dentro AAAA-MM/nota<n>_op<op>.xml

Destino: CADASTRO/LASTRO DAS OPERACOES/xml operacao/nota<n>_op<op>.xml (flat, skip-existing).

⚠️ Sessão caída: o Smart responde HTTP 200 com `top.location.href='...expira.php'` (93B) —
não é erro HTTP e não tem "expirou". Checar antes de interpretar como "sem nota".
"""
import io
import json
import os
import re
import zipfile

SMART = os.getenv("DOC2YOU_SMART_HOST", "https://wvw.smartsecurities.com.br").rstrip("/")
BASE = SMART + "/smart/financeiro"
URL_GRID = BASE + "/gridmonitoramentonota.php"
URL_AJAX = BASE + "/gridmonitoramentonotaajax.php"
NC_SUBPASTA = os.getenv("DOC2YOU_XML_SUBPASTA", "xml operacao")
_LOTE = int(os.getenv("DOC2YOU_XML_LOTE", "300") or 300)  # ids por ZIP (fatiar lotes grandes)

_RE_CHK = re.compile(r"<input[^>]*name=['\"]baixar\[\]['\"][^>]*>", re.I)
_RE_VAL = re.compile(r"value=['\"](\d+)['\"]", re.I)
_RE_TIPO = re.compile(r"data-tiponota=['\"]([^'\"]+)['\"]", re.I)


def _sessao_caiu(html: str) -> bool:
    low = html.lower()
    return "expira.php" in low or "top.location.href" in low


async def _get_texto(ctx, url):
    r = await ctx.request.get(url, timeout=60000)
    return (await r.body()).decode("iso-8859-1", errors="replace")


async def listar_notas(ctx, data_ini: str, data_fim: str, max_paginas: int = 300) -> list:
    """[(idNfe, tipo)] das notas de operação FINALIZADA no período. Para quando a
    página não traz nenhum id novo (trata a repetição da última página)."""
    filtros = (f"datainicio=&datafim=&datainicioOP=&datafimOP="
               f"&datainicioOPFinalizada={data_ini}&datafimOPFinalizada={data_fim}"
               f"&tCedente=&NumCedente=&tScado=&NumSacado="
               f"&statusnota=&statusmonitoramento=&numeroNota="
               f"&statusmonitoramentoserpro=&filtrotipo=")
    seen = set()
    notas = []
    page = 1
    while page <= max_paginas:
        html = await _get_texto(ctx, f"{URL_GRID}?page={page}&{filtros}")
        if _sessao_caiu(html):
            raise RuntimeError("sessão Smart caiu (expira.php) ao listar notas")
        novos = 0
        for m in _RE_CHK.finditer(html):
            tag = m.group(0)
            v = _RE_VAL.search(tag)
            t = _RE_TIPO.search(tag)
            if v and t and v.group(1) not in seen:
                seen.add(v.group(1))
                notas.append((v.group(1), t.group(1)))
                novos += 1
        if novos == 0:  # página vazia OU repetição da última → fim
            break
        page += 1
    return notas


async def pedir_zip(ctx, ids) -> str:
    """POST GET_LINK_FILE_ZIP para um lote de (id, tipo). Devolve o link relativo."""
    idnotas = ",".join(f"{i}@{t}" for i, t in ids)
    r = await ctx.request.post(
        URL_AJAX, form={"acao": "GET_LINK_FILE_ZIP", "idNotas": idnotas}, timeout=180000)
    body = (await r.body()).decode("iso-8859-1", errors="replace")
    if _sessao_caiu(body):
        raise RuntimeError("sessão Smart caiu (expira.php) ao pedir ZIP")
    try:
        j = json.loads(body)
    except Exception:
        raise RuntimeError(f"resposta não-JSON do ZIP: {body[:150]!r}")
    if (j.get("status") or "").upper() != "OK" or not j.get("link"):
        raise RuntimeError(f"ZIP recusado: {j.get('mensagem') or body[:150]!r}")
    return j["link"].replace("\\/", "/").lstrip("/")


async def baixar_zip(ctx, link: str) -> bytes:
    """GET o ZIP (link relativo a /smart/financeiro/). Devolve os bytes."""
    r = await ctx.request.get(f"{BASE}/{link}", timeout=180000)
    b = await r.body()
    if b[:2] != b"PK":
        raise RuntimeError(f"conteúdo não-ZIP ({len(b)}B, inicio={b[:8]!r})")
    return b


async def baixar_periodo(ctx, data_ini: str, data_fim: str, uploader, subpasta: str = None):
    """Baixa os XMLs das notas de operação finalizada no período e sobe pro Nextcloud
    (skip-existing por nome). Fatia o pedido do ZIP em lotes. Retorna (novos, pulados, erros)."""
    subpasta = subpasta or NC_SUBPASTA
    notas = await listar_notas(ctx, data_ini, data_fim)
    if not notas:
        print(f"[doc2you] xml: nenhuma nota (op finalizada {data_ini}..{data_fim}).", flush=True)
        return 0, 0, 0
    existentes = uploader.listar_nomes(subpasta)
    print(f"[doc2you] xml: {len(notas)} nota(s) no período; baixando em lotes de {_LOTE}...", flush=True)
    novos = pulados = erros = 0
    for i in range(0, len(notas), _LOTE):
        lote = notas[i:i + _LOTE]
        try:
            link = await pedir_zip(ctx, lote)
            zb = await baixar_zip(ctx, link)
        except Exception as e:
            erros += len(lote)
            print(f"  [xml lote {i // _LOTE + 1}] ERRO {type(e).__name__}: {e}", flush=True)
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(zb)) as zf:
                for nome in zf.namelist():
                    if not nome.lower().endswith(".xml"):
                        continue
                    base = nome.rsplit("/", 1)[-1]  # tira o AAAA-MM/ do caminho
                    if base in existentes:
                        pulados += 1
                        continue
                    try:
                        st = uploader.enviar(zf.read(nome), subpasta, base)
                        if st in (201, 204):
                            novos += 1
                        else:
                            erros += 1
                            print(f"  [xml] {base}: Nextcloud http {st}", flush=True)
                        existentes.add(base)
                    except Exception as e:
                        erros += 1
                        print(f"  [xml] {base} erro: {type(e).__name__}: {e}", flush=True)
        except zipfile.BadZipFile as e:
            erros += len(lote)
            print(f"  [xml lote {i // _LOTE + 1}] ZIP inválido: {e}", flush=True)
    return novos, pulados, erros
