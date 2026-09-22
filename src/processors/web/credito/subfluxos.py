"""
Sub-fluxos chamados pelo robo principal (antes eram External.RunFlow no PAD).

Convertidos a partir dos fluxos PAD exportados:
  - "baixar nfe e resumo.txt"  -> baixar_nf_e_resumo()
  - "Enviar DIGITAIS VM.txt"   -> digitais_vm()

MELHORIA (Python): o download da NF e do resumo, que no PAD usava o visualizador
de PDF do Chrome + dialogo "Salvar como" com COORDENADAS DE MOUSE fixas (fragil),
aqui e feito por requisicao HTTP autenticada direta:
  - NF:     GET  gerardanfes.php?NumOperacao=<op>      -> application/pdf
  - Resumo: POST popuprelatoriopreanalise.php?numOp=<op> (GERAR=1) -> application/pdf
"""

import os
import time

import config
import _analisar_credito_base as robo
import banco
import _nextcloud


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _garantir_pasta(caminho: str) -> None:
    os.makedirs(caminho, exist_ok=True)


# Ops de DIGITAIS que ficaram PARCIAIS (alguns docs gerados, outros nao) sao
# marcadas aqui e NUNCA reprocessadas -> evita gerar documento duplicado.
# Persistido em arquivo (sobrevive a reinicios do robo).
_ARQ_REVISAR = os.path.join(config.DEBUG_DIR, "ops_digitais_revisar_manual.txt")


def _carregar_ops_revisar() -> set:
    try:
        with open(_ARQ_REVISAR, encoding="utf-8") as f:
            return {l.strip() for l in f if l.strip()}
    except Exception:
        return set()


def _marcar_op_revisar(op: str) -> None:
    try:
        os.makedirs(config.DEBUG_DIR, exist_ok=True)
        with open(_ARQ_REVISAR, "a", encoding="utf-8") as f:
            f.write(f"{op}\n")
    except Exception:
        pass


def _mudar_etapa(ctx, op: str, rotulo: str) -> bool:
    """Abre a edicao, muda a etapa (#etapaOperacao) e VERIFICA se persistiu.
    Retorna True so se a op realmente ficou na etapa 'rotulo'."""
    page = None
    _tm = time.time()
    try:
        page = ctx.new_page()
        page.goto(config.URL_EDITAR.format(op=op),
                  wait_until="domcontentloaded", timeout=60_000)
        robo.selecionar_etapa_edicao(page, rotulo)  # ja trata o modal e dialogos
        print(f"  etapa da op {op} -> {rotulo} (solicitado)")
        robo.esperar(3, "apos mudar etapa")
    finally:
        robo.fechar_pagina(page)
    ok = _verificar_etapa(ctx, op, rotulo)
    print(f"  [move etapa] op {op} levou {time.time()-_tm:.0f}s")
    return ok


def _verificar_etapa(ctx, op: str, rotulo: str) -> bool:
    """Reabre a edicao e confere a etapa atual do #etapaOperacao."""
    page = None
    try:
        page = ctx.new_page()
        page.goto(config.URL_EDITAR.format(op=op),
                  wait_until="domcontentloaded", timeout=60_000)
        try:
            page.wait_for_load_state("load", timeout=8_000)
        except Exception:
            pass
        fr = robo.frame_com(page, config.SEL_STATUS_EDICAO, timeout=20)
        atual = fr.locator(config.SEL_STATUS_EDICAO).first.evaluate(
            "el => (el.options[el.selectedIndex] && el.options[el.selectedIndex].text) || ''")
        atual = (atual or "").strip()
        ok = atual.lower() == rotulo.strip().lower()
        print(f"  [verifica etapa] op {op}: atual='{atual}' alvo='{rotulo}' "
              f"-> {'OK (moveu)' if ok else 'NAO MUDOU'}")
        return ok
    except Exception as e:
        print(f"  [verifica etapa] op {op}: erro ao verificar ({e})")
        return False
    finally:
        robo.fechar_pagina(page)


# --------------------------------------------------------------------------- #
# Download de PDFs (NF e Resumo) - via HTTP direto
# --------------------------------------------------------------------------- #
def _entregar(body: bytes, nome: str, subpasta_nc: str,
              pasta_local: str, rotulo: str) -> str | None:
    """Entrega o PDF baixado: destino final = Nextcloud (WebDAV); se estiver
    desligado/indisponivel OU o upload falhar, salva LOCAL (fail-safe: nunca
    perder o documento). Retorna um caminho truthy p/ o controle de idempotencia
    (path do Nextcloud OU local), ou None se nao gravou em lugar nenhum."""
    if config.SALVAR_NEXTCLOUD and _nextcloud.disponivel():
        try:
            st = _nextcloud.enviar(body, subpasta_nc, nome)
            if st in (201, 204):
                destino = f"{_nextcloud.DEST_BASE}/{subpasta_nc}/{nome}"
                print(f"  {rotulo} -> Nextcloud: {destino} ({len(body)} bytes, http {st})")
                return destino
            print(f"  [{rotulo}] Nextcloud retornou http {st}; salvando local (fallback)")
        except Exception as e:
            print(f"  [{rotulo}] upload Nextcloud falhou ({e}); salvando local (fallback)")
    # Local: Nextcloud desligado/indisponivel OU fallback de falha de upload.
    try:
        _garantir_pasta(pasta_local)
        cam = os.path.join(pasta_local, nome)
        with open(cam, "wb") as fh:
            fh.write(body)
        print(f"  {rotulo} salvo local: {cam} ({len(body)} bytes)")
        return cam
    except Exception as e:
        print(f"  [{rotulo}] falha ao salvar local ({e})")
        return None


def baixar_nf(ctx, op: str) -> str | None:
    """Baixa o PDF da NF (DANFEs) e entrega em <Nextcloud>/nf operacao/NFE<op>.pdf
    (fallback local). Retorna o destino ou None."""
    r = ctx.request.get(config.URL_NF_PDF.format(op=op), timeout=120_000)
    body = r.body()
    if r.status == 200 and body[:4] == b"%PDF":
        return _entregar(body, f"NFE{op}.pdf", config.NC_SUBPASTA_NF,
                         config.PASTA_NFE, "NF")
    print(f"  [NF] resposta inesperada: status={r.status} "
          f"ct={r.headers.get('content-type','')} ({len(body)} bytes)")
    return None


def baixar_resumo(ctx, op: str) -> str | None:
    """Gera e baixa o resumo (relatorio de pre-analise) -> inbox\\resumo<op>.pdf.

    Replica o POST do form (GERAR=1 + checkboxes) que o PAD disparava clicando
    em "Relatório" (#InputPDF). Os checkboxes marcados sao os mesmos do PAD.
    Entrega em <Nextcloud>/resumo da operacao/resumo<op>.pdf (fallback local).
    """
    campos = {
        "numOperacao": str(op), "numFactoring": config.NUM_FACTORING,
        "documentoOperacao": "0", "GERAR": "1", "sacadosChk": "", "FIDC": "0",
        # checkboxes marcados pelo PAD:
        "mroperacao": "1", "r1": "1", "r2": "1", "r3": "1", "r4": "1",
        "r6": "1", "r7": "1", "r8": "1",
        "mrcedente": "1", "mrsacado": "1", "mtitulos": "1",
        "mcriticas": "1", "mconsultas": "1",
    }
    r = ctx.request.post(config.URL_RESUMO_POST.format(op=op),
                         form=campos, timeout=120_000)
    body = r.body()
    if r.status == 200 and body[:4] == b"%PDF":
        return _entregar(body, f"resumo{op}.pdf", config.NC_SUBPASTA_RESUMO,
                         config.PASTA_RESUMO, "resumo")
    print(f"  [resumo] resposta inesperada: status={r.status} "
          f"ct={r.headers.get('content-type','')} ({len(body)} bytes)")
    return None


def baixar_documentos_complementares(ctx, op: str) -> tuple[int, int]:
    """Baixa TODOS os documentos complementares (aba "Outros documentos") da op e
    sobe no Nextcloud em <complementares>/<op>/<nome>, criando a SUBPASTA por op
    (MKCOL recursivo do _nextcloud). Igual a NF, mas um doc por arquivo, agrupados
    pela operacao. Retorna (subidos, total). Best-effort: nunca derruba o ciclo."""
    if not (config.SALVAR_NEXTCLOUD and _nextcloud.disponivel()):
        return 0, 0
    from smart_session import Smart   # import tardio (evita custo no load do modulo)
    import op_docs
    try:
        s = Smart.attach(ctx)
        _st, docs = op_docs.listar_docs(s, op)
    except Exception as e:
        print(f"  [complementares op {op}] erro ao listar: {e}")
        return 0, 0
    if not docs:
        return 0, 0
    subpasta = f"{config.NC_SUBPASTA_COMPLEMENTARES}/{op}"
    subidos = 0
    for d in docs:
        nome = d.get("nome") or f"doc_{d.get('idDoc')}"
        try:
            b, nome_final = op_docs.obter_doc_bytes(s, d["idDoc"], nome)
            if b is None:
                print(f"  [complementares op {op}] '{nome}' falhou: {nome_final}")
                continue
            stt = _nextcloud.enviar(b, subpasta, nome_final)
            if stt in (201, 204):
                subidos += 1
                print(f"  complementar -> Nextcloud: {subpasta}/{nome_final} "
                      f"({len(b)} bytes, http {stt})")
            else:
                print(f"  [complementares op {op}] '{nome_final}': Nextcloud http {stt}")
        except Exception as e:
            print(f"  [complementares op {op}] doc {d.get('idDoc')} erro: {e}")
    print(f"  [complementares op {op}] {subidos}/{len(docs)} doc(s) no Nextcloud")
    return subidos, len(docs)


# --------------------------------------------------------------------------- #
# Sub-fluxo: BAIXAR NF E RESUMO PARA ANALISE
# --------------------------------------------------------------------------- #
def _descobrir_ops_feedback(ctx):
    """Lista as operacoes em "Feedback Analise ROB". Tenta o BANCO
    (trs.operacao_desagio WHERE etapa = 'FEEDBACK ANALISE ROB'); se o banco
    estiver inacessivel (ex.: VPN fora), cai p/ a raspagem da UI do Smart.
    Retorna (ops, origem)."""
    if config.USAR_BANCO_DOWNLOAD:
        try:
            ops = banco.operacoes_na_etapa(config.ETAPA_DB_FEEDBACK_ROB)
            return ops, "banco"
        except Exception as e:
            print(f"  [BAIXAR NF] banco indisponivel ({e}); usando raspagem da UI (fallback)")
    ops = robo.listar_operacoes_etapa(
        ctx, config.VALOR_ETAPA_FEEDBACK_ROB, "Feedback Analise ROB")
    return ops, "ui"


# Contador EM MEMORIA de ciclos consecutivos em que tentamos mover uma op que
# NAO saiu da fila de Feedback ROB. Zera quando a op deixa a fila (move pegou).
_tentativas_move = {}

# Hook OPCIONAL chamado apos baixar NF/resumo de cada op (assinatura: (ctx, op)).
# None por padrao = NO-OP (comportamento do V1 inalterado). A V2
# (robo_analise_credito_v2.py) injeta aqui a conferencia de documentos.
pos_download_hook = None


def _carregar_move_revisar() -> set:
    """Le ops_move_revisar_manual.txt -> set de ops que devem ser PULADAS no move
    (ja tentamos N vezes e nunca sairam da fila; precisam de acao manual)."""
    try:
        if os.path.exists(config.ARQ_MOVE_REVISAR):
            with open(config.ARQ_MOVE_REVISAR, encoding="utf-8") as f:
                return {linha.strip() for linha in f if linha.strip()}
    except Exception:
        pass
    return set()


def _marcar_move_revisar(op) -> None:
    """Acrescenta a op em ops_move_revisar_manual.txt (uma vez)."""
    op = str(op)
    if op in _carregar_move_revisar():
        return
    try:
        with open(config.ARQ_MOVE_REVISAR, "a", encoding="utf-8") as f:
            f.write(op + "\n")
    except Exception as e:
        print(f"  [move] nao consegui gravar revisar_manual: {e}")


def baixar_nf_e_resumo(ctx) -> None:
    """Etapa "Feedback Analise ROB": DESCOBRE as operacoes (via BANCO; fallback
    UI), baixa NF + resumo das que ainda nao foram baixadas (controle local) e
    DEPOIS move p/ "Análise de crédito" (so as que baixaram ok e ainda nao
    foram movidas)."""
    # 1) DESCOBRIR as operacoes na etapa
    ops, origem = _descobrir_ops_feedback(ctx)
    if not ops:
        print("  [BAIXAR NF] nenhuma operacao em 'Feedback Analise ROB' (FIMFEEDBACK)")
        return
    print(f"  [BAIXAR NF] {len(ops)} operacao(oes) [origem={origem}]: {ops}")

    # 2) BAIXAR NF + resumo de TODAS as ops que estao na fila AGORA (SOBRESCREVE).
    #    Regra (decisao do usuario): enquanto a op ESTIVER em "Feedback Analise
    #    ROB", re-baixa NF/Resumo/complementares. O Smart e a FONTE DA VERDADE,
    #    entao uma op DEVOLVIDA pra reanalise (ex.: incluiram mais sacados) fica
    #    com os docs ATUALIZADOS -> o WebDAV PUT sobrescreve o arquivo antigo
    #    (mesmo nome deterministico) e complementares novos entram na pasta da op.
    #    Excecao: ops ja em revisar_manual (move nunca sai da fila) NAO sao
    #    rebaixadas em loop -> ficam p/ tratamento manual (evita HTTP a toa).
    #    Somente-leitura no Smart -> ocorre mesmo em DRY_RUN.
    revisar_dl = _carregar_move_revisar()
    for op in ops:
        if str(op) in revisar_dl:
            print(f"  [BAIXAR NF] op {op}: em revisar_manual (move preso) -> nao rebaixa")
            continue
        print(f"  [BAIXAR NF] baixando op {op} (sobrescreve se ja existia)")
        robo._bater(f"baixar op {op}")   # heartbeat
        cam_nf = baixar_nf(ctx, op)
        cam_resumo = baixar_resumo(ctx, op)
        # documentos complementares (aba "Outros documentos") -> Nextcloud/<op>/
        try:
            baixar_documentos_complementares(ctx, op)
        except Exception as e:
            print(f"  [complementares op {op}] erro ignorado: {e}")
        banco.registrar_download(op, cam_nf, cam_resumo)
        # V2: conferencia de documentos (no-op no V1; injetada via pos_download_hook)
        if pos_download_hook:
            try:
                pos_download_hook(ctx, op)
            except Exception as e:
                print(f"  [hook pos-download] erro ignorado op {op}: {e}")

    # 3) MOVER etapa das que baixaram ok e ainda NAO foram movidas. Se o download
    #    ficou incompleto, NAO move (retenta no proximo ciclo, sem rebaixar).
    if config.DRY_RUN:
        print("  [DRY_RUN] pularia mover etapa -> Análise de crédito")
        return
    controle = banco.carregar_controle(ops)
    revisar = _carregar_move_revisar()
    # Limpa o contador das ops que JA sairam da fila (move pegou): so contam
    # tentativas das ops que CONTINUAM reaparecendo em Feedback ROB.
    _atuais = {str(o) for o in ops}
    for _o in list(_tentativas_move):
        if _o not in _atuais:
            _tentativas_move.pop(_o, None)
    for op in ops:
        op = str(op)
        reg = controle.get(op)
        # Regra: exige o RESUMO; a NF e opcional (ha operacoes sem nota fiscal).
        if not banco.pode_mover(reg):
            print(f"  [BAIXAR NF] op {op}: sem resumo -> NAO move etapa (retenta)")
            continue
        if op in revisar:
            print(f"  [BAIXAR NF] op {op}: marcada p/ REVISAR MANUAL "
                  f"(move nao tira da fila) -> pulando")
            continue
        # A op esta na fila de Feedback ROB AGORA -> precisa mover, MESMO que o
        # controle ja diga 'etapa_movida'. O que vale e a op SAIR da fila, o que
        # e conferido pela redescoberta no proximo ciclo (se reaparecer, o move
        # nao pegou). Assim um move que "verifica OK" mas nao tira da fila deixa
        # de prender a operacao para sempre.
        n = _tentativas_move.get(op, 0) + 1
        _tentativas_move[op] = n
        if not reg.get("nfe_ok"):
            print(f"  [BAIXAR NF] op {op}: SEM NF (operacao sem nota fiscal) "
                  f"-> movendo assim mesmo")
        _mudar_etapa(ctx, op, config.ROTULO_ANALISE_CREDITO)
        banco.marcar_etapa_movida(op)  # informativo (registra a ultima tentativa)
        if config.MAX_TENTATIVAS_MOVE and n >= config.MAX_TENTATIVAS_MOVE:
            _marcar_move_revisar(op)
            print(f"  [BAIXAR NF] op {op}: {n} tentativas e ainda na fila -> "
                  f"REVISAR MANUAL (parei de tentar p/ evitar loop)")


# --------------------------------------------------------------------------- #
# Sub-fluxo: DIGITAIS - VM
# --------------------------------------------------------------------------- #
# OBS: este fluxo (geracao de Resumir/Aditivo/Promissória + duplicata digital)
# usa popups e dialogos JS. Implementado de forma fiel, mas AINDA NAO TESTADO
# end-to-end (depende de haver operacao na etapa "Enviar Digitais").
def _aceitar_dialogos(page) -> None:
    """Auto-confirma dialogos JS (equivale ao DialogButton: 'OK' do PAD)."""
    page.on("dialog", lambda d: d.accept())


def _gerar_documentos_digitais(ctx, op: str) -> None:
    """Abre a edicao e gera os documentos (Resumir, Aditivo, Promissória)."""
    page = None
    try:
        page = ctx.new_page()
        _aceitar_dialogos(page)
        page.goto(config.URL_EDITAR.format(op=op),
                  wait_until="domcontentloaded", timeout=60_000)
        for doc in ("Resumir", "Aditivo", "Promissória"):
            try:
                fr = robo.frame_com(page, f"span:has-text('{doc}')", timeout=10)
                fr.locator(f"span:has-text('{doc}')").first.click()
                robo.esperar(2, f"gerando documento: {doc}")
                # Janela de geracao: seleciona tipo de documento e clica em Gerar
                try:
                    frg = robo.frame_com(page, "#rTipoDocumento, [name='rTipoDocumento']", timeout=8)
                    frg.locator("#rTipoDocumento, [name='rTipoDocumento']").first.check()
                    robo.frame_com(page, "button:has-text('Gerar'), input[value='Gerar']", timeout=8) \
                        .locator("button:has-text('Gerar'), input[value='Gerar']").first.click()
                    robo.esperar(2, f"documento {doc} gerado")
                except Exception as e:
                    print(f"  [digitais] '{doc}': etapa Gerar nao concluida ({e})")
            except Exception as e:
                print(f"  [digitais] documento '{doc}' nao encontrado ({e})")
    finally:
        robo.fechar_pagina(page)


def _gerar_duplicata_digital(ctx, op: str) -> None:
    """Gera a duplicata digital (duplicatadigital.php)."""
    page = None
    try:
        page = ctx.new_page()
        _aceitar_dialogos(page)
        url = (f"https://wvw.smartsecurities.com.br/smart/operacao/"
               f"duplicatadigital.php?NumOperacao={op}")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        try:
            fr = robo.frame_com(page, "[name='cSelecionarTodosCasa'], #cSelecionarTodosCasa", timeout=10)
            fr.locator("[name='cSelecionarTodosCasa'], #cSelecionarTodosCasa").first.check()
        except Exception as e:
            print(f"  [duplicata] cSelecionarTodosCasa: {e}")
        try:
            fr = robo.frame_com(page, "[name='lq'], #lq", timeout=5)
            fr.locator("[name='lq'], #lq").first.uncheck()
        except Exception:
            pass
        try:
            robo.frame_com(page, "button:has-text('Gerar'), input[value='Gerar']", timeout=8) \
                .locator("button:has-text('Gerar'), input[value='Gerar']").first.click()
            robo.esperar(5, "gerando duplicata digital")
        except Exception as e:
            print(f"  [duplicata] botao Gerar: {e}")
    finally:
        robo.fechar_pagina(page)


def gerar_documento(ctx, op: str, botao_id: str, tipo: str = "fisico") -> bool:
    """Resumir -> clica o botao do documento (#aditivo / #imprimirNP) -> na popup
    marca TODAS as assinaturas (chkAssinDigital), escolhe o tipo (fisico/digital)
    e clica Gerar (#Input). GERA DOCUMENTO REAL. Screenshots em DEBUG_DIR.
    (funcao recarregavel via 'reload' no servidor de teste)."""
    # A duplicata digital tem fluxo proprio (pagina separada, checkboxes).
    if botao_id == "#duplicatadigital":
        return _gerar_duplicata(ctx, op)

    page = ctx.new_page()
    pop = None
    _t0 = time.time()
    page.on("dialog", lambda d: (print(f"  [dialog] '{d.message[:70]}'"), d.accept()))
    try:
        page.goto(config.URL_EDITAR.format(op=op),
                  wait_until="domcontentloaded", timeout=60_000)
        time.sleep(2)
        robo.frame_com(page, "#invocarResumirOperacao", timeout=20) \
            .locator("#invocarResumirOperacao").click()
        print("  Resumir clicado; aguardando barra de documentos...")
        # o frame_com(botao_id) abaixo ja espera o botao aparecer; pequena folga.
        time.sleep(2)
        with ctx.expect_page(timeout=15_000) as pinfo:
            robo.frame_com(page, botao_id, timeout=15).locator(botao_id).click(timeout=10_000)
        pop = pinfo.value
        pop.wait_for_load_state("domcontentloaded", timeout=20_000)
        pop.on("dialog", lambda d: (print(f"  [dialog popup] '{d.message[:70]}'"), d.accept()))
        # DETECTOR DE PDF POR REDE (2026-05-29): o sistema atualizou o modulo de
        # documentos. Antes, clicar Gerar navegava o popup DIRETO p/ o .pdf
        # (a URL virava temp/...pdf). Agora o Gerar faz um passo HTML
        # intermediario (recibocliente.php SEM query) e o PDF (temp/...pdf) chega
        # alguns segundos DEPOIS - a URL do TOPO pode nem refletir o .pdf a tempo.
        # Por isso a deteccao por URL falhava (GEROU? NAO) mesmo gerando de
        # verdade. Capturar a resposta application/pdf e o sinal confiavel.
        _pdfs = []

        def _cap_pdf(resp):
            try:
                u = resp.url or ""
                ct = (resp.headers or {}).get("content-type", "").lower()
                if ("application/pdf" in ct) or ("/temp/" in u.lower() and ".pdf" in u.lower()):
                    _pdfs.append(u)
            except Exception:
                pass
        pop.on("response", _cap_pdf)
        time.sleep(2)
        url_inicial = pop.url
        print(f"  popup geracao: {url_inicial}")
        # 1) PRIMEIRO seleciona o tipo Digital (obrigatorio antes de enviar) e
        #    ESPERA o formulario atualizar (o Digital auto-preenche os socios).
        if "digital" in str(tipo).lower():
            try:
                pop.locator("input[name='rTipoDocumento'][value='2']").check(timeout=5_000)
                print("  tipo de documento -> Digital (aguardando auto-fill dos signatarios...)")
                # CRITICO (atualizacao do sistema, 2026-05-29): o botao Gerar
                # agora ja vem HABILITADO de imediato -> 'Gerar habilitou' deixou
                # de indicar que o auto-fill das assinaturas terminou. Clicar
                # cedo submete o form SEM as assinaturas digitais e o servidor
                # NAO gera o documento (nenhum PDF). Por isso esperamos o
                # auto-fill ANTES de habilitar.
                _esperar_autofill_assinaturas(pop, timeout=25)
                _esperar_gerar_habilitar(pop, timeout=60)
            except Exception as e:
                print(f"  aviso ao marcar Digital: {e}")
        # 2) Assinaturas:
        # No DIGITAL os signatarios (socios) sao preenchidos AUTOMATICAMENTE ao
        # selecionar "Digital" -> NAO marcar nada manualmente (marcar bagunca
        # os signatarios). So no Fisico e preciso marcar.
        if "digital" in str(tipo).lower():
            print("  (digital) assinaturas preenchidas automaticamente (socios) - nao marco")
        else:
            marc = pop.evaluate("""() => {
                let n=0;
                document.querySelectorAll("input[type=checkbox]").forEach(c=>{
                    if((c.name||'')==='chkAssinDigital'){ if(!c.checked){ c.click(); } n++; }
                });
                return n;
            }""")
            print(f"  (fisico) assinaturas marcadas: {marc}")
        time.sleep(1)
        # screenshots SO em DEBUG (full_page e lento; em producao e desperdicio)
        if config.DEBUG:
            os.makedirs(config.DEBUG_DIR, exist_ok=True)
            try:
                pop.screenshot(path=os.path.join(config.DEBUG_DIR, f"gerar_{op}_{tipo}_antes.png"), full_page=True)
            except Exception:
                pass
        # MODO DRY: so verifica quais assinaturas ficaram (auto-preenchidas) e
        # NAO clica em Gerar (nao envia).
        if "dry" in str(tipo).lower():
            time.sleep(6)  # espera extra p/ o auto-fill completar
            checked = pop.evaluate("""() => [...document.querySelectorAll("input[name=chkAssinDigital]")].map(c=>{const r=c.closest('tr')||c.parentElement; return (c.checked?'[x] ':'[ ] ')+((r?r.innerText:'')||'').replace(/\\s+/g,' ').trim().slice(0,32);})""")
            print("  [DRY] assinaturas (apos Digital + espera):")
            for c in checked:
                print("    " + c)
            gstate = pop.evaluate("""() => { const b=document.querySelector('#Input'); return b? ('#Input disabled='+b.disabled+' visivel='+(b.offsetParent!==null)) : 'sem #Input'; }""")
            print(f"  [DRY] botao Gerar: {gstate}")
            print("  [DRY] NAO clicando Gerar (apenas verificacao)")
            return True

        # botao Gerar varia por documento (#Input no Aditivo; outro na Promissória)
        # -> clica por papel/texto, com fallbacks.
        _pdfs.clear()  # ignora qualquer pdf carregado antes do clique
        clicou = False
        try:
            pop.get_by_role("button", name="Gerar", exact=True).first.click(timeout=8_000)
            clicou = True
        except Exception:
            for sel in ("#Input", "input[value='Gerar']", "input[value='GERAR']",
                        "button:has-text('Gerar')", "a:has-text('Gerar')"):
                try:
                    loc = pop.locator(sel).first
                    if loc.count() > 0:
                        loc.click(timeout=6_000)
                        clicou = True
                        break
                except Exception:
                    continue
        print(f"  >> GERAR clicado={clicou}")
        # Espera o resultado. Para a Promissoria (#imprimirNP) o sucesso e a
        # navegacao do frameset (tratada adiante) -> basta esperar a URL mudar
        # (rapido). Para os demais (Aditivo) o PDF chega por REDE alguns segundos
        # DEPOIS do passo HTML intermediario -> esperamos a resposta
        # application/pdf (ate 25s) em vez de so olhar a URL do topo.
        # A geracao virou ASSINCRONA com a atualizacao do sistema (2026-05-29): o
        # POST de submit retorna uma pagina HTML intermediaria ("gerando...") e o
        # PDF (temp/...pdf, application/pdf) so chega DEPOIS. MEDIDO: geracao "a
        # frio" (1a vez de uma op) leva ~180s; ops ja geradas voltam em ~10s.
        # Esperamos ate 210s pela resposta application/pdf p/ TODOS os docs (a
        # Promissoria renderiza o PDF num frame interno que tb dispara
        # application/pdf -> _cap_pdf captura igual). pop.url/is_closed a cada
        # iteracao pumpa os eventos do Playwright -> _cap_pdf dispara e o loop sai
        # assim que o PDF chega (nao espera os 210s cheios quando ja foi gerada).
        _fim_g = time.time() + 210
        while time.time() < _fim_g:
            try:
                if pop.is_closed() or _pdfs or (".pdf" in (pop.url or "").lower()):
                    break
            except Exception:
                break
            time.sleep(0.5)
        if config.DEBUG:
            try:
                pop.screenshot(path=os.path.join(config.DEBUG_DIR, f"gerar_{op}_{tipo}_depois.png"), full_page=True)
            except Exception:
                pass
        url2 = pop.url if not pop.is_closed() else "(popup fechou)"
        print(f"  url popup apos gerar: {url2}")
        url2_low = (url2 or "").lower()

        # PROMISSORIA - RACE CONDITION corrigida (insight do usuario, 28/05):
        # O 'Gerar' do wrapper navega p/ frmnotapromissoria.php (frameset). O
        # FRAME INTERNO (name=NotaPromissoria) faz uma 2a request:
        # notapromissoria.php?Imprimir=<op>&assinaturasDigital2=...&... que e a
        # que EFETIVAMENTE gera/envia a NPP no servidor (assinaturas digitais).
        # Se fechamos a popup logo apos a navegacao do frameset (URL pai mudou),
        # o frame interno pode nem ter enviado a request ainda -> NPP NAO
        # gerada de verdade. Por isso algumas NPPs nao apareciam no Smart.
        # Solucao: aguardar o frame interno carregar com 'Imprimir=' (sinal de
        # que a request foi enviada) e dar margem p/ o servidor processar.
        frame_ok = False
        if (botao_id == "#imprimirNP"
                and "frmnotapromissoria" in url2_low
                and not pop.is_closed()):
            print("  [promiss] aguardando o frame interno enviar a request da NPP ao servidor...")
            _f_fr = time.time() + 12
            while time.time() < _f_fr:
                try:
                    if pop.is_closed():
                        break
                    for fr in pop.frames:
                        if fr == pop.main_frame:
                            continue
                        furl = (fr.url or "").lower()
                        if "imprimir=" in furl or ".pdf" in furl:
                            frame_ok = True
                            try:
                                fr.wait_for_load_state("load", timeout=8_000)
                            except Exception:
                                pass
                            break
                    if frame_ok:
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            if frame_ok:
                # margem p/ o servidor concluir (assinaturas digitais demoram).
                time.sleep(5)
                print("  [promiss] frame interno OK -> NPP enviada ao servidor")
            else:
                print("  [promiss] AVISO: frame interno NAO confirmou a request "
                      "em 12s -> NPP nao foi enviada -> falha-stop")

        # SUCESSO depende do documento:
        # - Promissoria: URL = frmnotapromissoria.php E frame interno enviou
        #   a request (frame_ok = True). Antes aceitavamos so a URL pai, mas o
        #   frame interno pode nao ter processado -> NPP nao gerada de verdade.
        # - Outros docs (Aditivo, etc.): URL virou .pdf / temp/...
        if botao_id == "#imprimirNP":
            gerou = (bool(_pdfs) or ("frmnotapromissoria" in url2_low and frame_ok)
                     or (".pdf" in url2_low))
        else:
            # Aditivo (e demais docs do popup): sucesso = PDF chegou pela rede
            # (temp/...pdf / application/pdf) OU a URL virou .pdf/temp.
            gerou = (bool(_pdfs) or (".pdf" in url2_low)
                     or ("/temp/" in url2_low) or ("\\temp\\" in url2_low))
        print(f"  >> GEROU? {'SIM' if gerou else 'NAO'} (clicou={clicou}, "
              f"pdf_rede={_pdfs[-1] if _pdfs else 'nao'}, "
              f"url_final={url2}) [doc levou {time.time()-_t0:.0f}s]")

        # Diagnostico automatico: se Promissoria falhou, dumpa screenshot+HTML do
        # form p/ analise (assim conseguimos ajustar o seletor exato sem precisar
        # de outra sessao de investigacao com login manual).
        if (not gerou) and botao_id == "#imprimirNP" and not pop.is_closed():
            try:
                os.makedirs("debug", exist_ok=True)
                png = os.path.join("debug", f"falha_promissoria_{op}.png")
                htm = os.path.join("debug", f"falha_promissoria_{op}.html")
                pop.screenshot(path=png, full_page=True)
                with open(htm, "w", encoding="utf-8") as fh:
                    fh.write(pop.content())
                print(f"  [promiss FAIL] dump: {png} + {htm}")
            except Exception as e:
                print(f"  [promiss FAIL] erro ao dumpar: {e}")

        return gerou
    finally:
        # fecha SOMENTE as abas que esta funcao criou (popup + page),
        # nunca outras (pra nao esvaziar o contexto e fechar o navegador).
        robo.fechar_pagina(pop)
        robo.fechar_pagina(page)


def _esperar_autofill_assinaturas(pop, piso: int = 10, timeout: int = 25) -> bool:
    """Apos marcar 'Digital', o sistema auto-preenche os signatarios via 2 AJAX
    (configuracoesdocumentocedentefunctions.php). Com a atualizacao do sistema
    (2026-05-29) o botao Gerar ja vem HABILITADO, entao 'Gerar habilitou' deixou
    de indicar auto-fill pronto: clicar cedo (durante/entre os AJAX) submete o
    form num estado transitorio -> o servidor NAO gera o documento (nenhum PDF).
    VALIDADO: a geracao so sai de forma confiavel quando se aguarda ~10s apos
    marcar Digital. Por isso: PISO fixo de ~10s (igual ao fluxo que comprovamos)
    + confirmacao de que >=1 assinatura ficou marcada (estende ate timeout se
    ainda nao marcou). NAO marca nada manualmente (so observa)."""
    import time as _t
    _t.sleep(piso)  # piso comprovado: da tempo dos 2 AJAX de auto-fill assentarem
    fim = _t.time() + max(0, timeout - piso)
    n = 0
    while _t.time() < fim:
        try:
            n = pop.evaluate(
                "() => [...document.querySelectorAll('input[name=chkAssinDigital]')]"
                ".filter(c => c.checked).length")
        except Exception:
            n = 0
        if n >= 1:
            break
        _t.sleep(0.5)
    print(f"  auto-fill de assinaturas: {max(n,0)} marcada(s) (apos piso {piso}s)")
    return n >= 1


def _esperar_gerar_habilitar(pop, timeout: int = 60) -> bool:
    """Aguarda o botao 'Gerar' habilitar (o auto-fill dos socios completar).
    Evita clicar cedo demais (Gerar disabled) e ter que reprocessar. Default
    60s: ops com muitos signatarios estouravam o limite anterior (30s) e o robo
    pulava sem gerar (ver bug ops 61224/60990)."""
    import time as _t
    fim = _t.time() + timeout
    while _t.time() < fim:
        try:
            b = pop.get_by_role("button", name="Gerar", exact=True).first
            if b.count() > 0 and b.is_enabled():
                print("  Gerar habilitou")
                return True
        except Exception:
            pass
        try:
            b = pop.locator("#Input").first
            if b.count() > 0 and b.is_enabled():
                print("  Gerar (#Input) habilitou")
                return True
        except Exception:
            pass
        _t.sleep(1)
    print("  Gerar NAO habilitou dentro do tempo (op sera pulada/retentada)")
    return False


def _clicar_gerar(loc_root):
    """Clica o botao 'Gerar' (por papel/texto, com fallbacks)."""
    try:
        loc_root.get_by_role("button", name="Gerar", exact=True).first.click(timeout=8_000)
        return True
    except Exception:
        for sel in ("input[value='Gerar']", "input[value='GERAR']",
                    "button:has-text('Gerar')", "#Input", "a:has-text('Gerar')"):
            try:
                loc = loc_root.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=6_000)
                    return True
            except Exception:
                continue
    return False


def _gerar_duplicata(ctx, op: str) -> bool:
    """Gera a DUPLICATA DIGITAL: abre duplicatadigital.php, marca
    cSelecionarTodosCasa, desmarca lq e clica Gerar (com dialogo OK)."""
    page = ctx.new_page()
    page.on("dialog", lambda d: (print(f"  [dialog dup] '{d.message[:70]}'"), d.accept()))
    try:
        url = ("https://wvw.smartsecurities.com.br/smart/operacao/"
               f"duplicatadigital.php?NumOperacao={op}")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(3)
        fr = robo.frame_com(page, "[name='cSelecionarTodosCasa'], #cSelecionarTodosCasa", timeout=20)
        cbs = fr.evaluate("""() => [...document.querySelectorAll('input[type=checkbox]')]
            .map(c=>(c.id||c.name||'?')+'='+c.checked).slice(0,30)""")
        print(f"  duplicata checkboxes: {cbs}")
        try:
            fr.locator("[name='cSelecionarTodosCasa'], #cSelecionarTodosCasa").first.check(timeout=5_000)
            print("  cSelecionarTodosCasa -> marcado")
        except Exception as e:
            print(f"  aviso cSelecionarTodosCasa: {e}")
        try:
            fr.locator("[name='lq'], #lq").first.uncheck(timeout=3_000)
            print("  lq -> desmarcado")
        except Exception:
            pass
        os.makedirs(config.DEBUG_DIR, exist_ok=True)
        try:
            page.screenshot(path=os.path.join(config.DEBUG_DIR, f"dup_{op}_antes.png"), full_page=True)
        except Exception:
            pass
        url_ini = page.url
        clicou = _clicar_gerar(fr)
        print(f"  >> GERAR duplicata clicado={clicou}")
        time.sleep(7)
        try:
            page.screenshot(path=os.path.join(config.DEBUG_DIR, f"dup_{op}_depois.png"), full_page=True)
        except Exception:
            pass
        url2 = page.url if not page.is_closed() else ""
        print(f"  url apos gerar duplicata: {url2}")
        # SUCESSO = gerou o PDF (a URL virou .pdf) OU navegou. O popup de cota
        # ("cota mensal excedida") interfere na deteccao do clique, mas o PDF
        # SAI mesmo assim -> nao confiar so no 'clicou'.
        gerou = (".pdf" in (url2 or "").lower()) or (url2 != url_ini and "duplicatadigital.php" not in (url2 or "")) or clicou
        print(f"  >> duplicata GEROU? {gerou}")
        return gerou
    finally:
        robo.fechar_pagina(page)


# --------------------------------------------------------------------------- #
# GERACAO DE DIGITAIS VIA HTTP (2026-05-29) - substitui o clique em "Gerar" +
# espera do PDF (a atualizacao do sistema tornou a geracao na UI assincrona/lenta
# e com armadilha anti-automacao). Aqui a chamada que GERA e um ctx.request HTTP,
# com o corpo montado pelo PROPRIO form (signatarios auto-preenchidos ao marcar
# Digital). 200 = gerado. Mapa dos endpoints reais (capturados ao vivo):
#   - Aditivo:     POST recibocliente.php
#   - Promissoria: POST montanotapromissoria.php  +  GET notapromissoria.php?Imprimir=...
#                  (o GET e quem ASSINA/finaliza a NPP - sem ele a NPP nao sai)
#   - Duplicata:   POST montaduplicatamercantil.php (corpo com arrays +-juntados,
#                  montado pelo JS do site -> deixo montar, CAPTURO+ABORTO o POST
#                  do navegador e dou REPLAY via HTTP, p/ ter o corpo exato)
# --------------------------------------------------------------------------- #
_SMART_OP = "https://wvw.smartsecurities.com.br/smart/operacao"
_SMART_AJAX = "https://wvw.smartsecurities.com.br/smart/operacaoajax/web"

# Monta o corpo urlencoded do form como o browser; preenche os campos listados em
# 'assinFields' com o join dos chkAssinDigital/chkAssn marcados (o JS faz isso).
_JS_BODY = r"""(assinFields) => {
  const f = document.Form || document.forms[0];
  if(!f) return null;
  const assin = [];
  for (const el of f.elements) {
    if (!el.name) continue;
    if ((el.type==='checkbox'||el.type==='radio') && !el.checked) continue;
    if (el.name==='chkAssinDigital' || el.name==='chkAssn') assin.push(el.value);
  }
  const joined = assin.join(',');
  const parts = [];
  for (const el of f.elements) {
    if (!el.name) continue;
    if ((el.type==='checkbox'||el.type==='radio') && !el.checked) continue;
    let v = el.value;
    if (assinFields.indexOf(el.name) >= 0) v = joined;
    parts.push(encodeURIComponent(el.name)+'='+encodeURIComponent(v));
  }
  return {body: parts.join('&'), assin: assin};
}"""


def _http_post_ok(ctx, url, body, ref) -> bool:
    r = ctx.request.post(
        url, data=body,
        headers={"content-type": "application/x-www-form-urlencoded", "referer": ref},
        timeout=240_000)
    print(f"    [HTTP] POST {url.rsplit('/', 1)[-1]} -> {r.status}")
    return r.status == 200


def _abrir_resumir(page) -> None:
    robo.frame_com(page, "#invocarResumirOperacao", timeout=20) \
        .locator("#invocarResumirOperacao").click()
    time.sleep(2)


def _http_aditivo(ctx, op) -> bool:
    """Aditivo: abre a edicao + Resumir, clica #aditivo (que agora abre um MODAL em
    iframe, nao mais janela popup) e le o form DE DENTRO do iframe
    (recibocliente.php?...modal=1); marca Digital e POSTa em recibocliente.php.
    NAO clica Gerar.

    A atualizacao do Smart (28/07/2026) trocou a POPUP por MODAL -> o antigo
    ctx.expect_page (esperava JANELA) estourava 'waiting for event page'. Navegar
    DIRETO na URL do form NAO funciona (o form so monta certo carregado pelo
    proprio modal), entao lemos do iframe que o site abre. Pagina propria (isolada)
    evita ter de fechar o modal entre os documentos. Ver _diag_dump_modal()."""
    page = ctx.new_page()
    page.on("dialog", lambda d: d.accept())
    try:
        page.goto(config.URL_EDITAR.format(op=op), wait_until="domcontentloaded", timeout=60_000)
        time.sleep(2)
        _abrir_resumir(page)
        robo.frame_com(page, "#aditivo", timeout=15).locator("#aditivo").click(timeout=10_000)
        # o clique abre o form num iframe aninhado (iframeModalPopup). Achamos esse
        # frame com frame_com, que faz POLL com round-trip (fr.locator().count()) e
        # por isso ATUALIZA a lista de frames -> enxerga o iframe novo. Varrer so por
        # fr.url NAO funciona: url e propriedade local/cacheada, page.frames congela.
        # rTipoDocumento so existe no form do modal (nao na edicao/resumir).
        fr = robo.frame_com(page, "input[name='rTipoDocumento']", timeout=25)
        time.sleep(1)
        try:
            fr.locator("input[name='rTipoDocumento'][value='2']").check(timeout=5_000)
        except Exception:
            pass
        time.sleep(11)  # remonta o grid de signatarios (apos marcar Digital)
        d = fr.evaluate(_JS_BODY, ["AssinaturasDigital"])
        print(f"    [ADITIVO {op}] assinaturas={d['assin']}")
        return _http_post_ok(
            ctx, f"{_SMART_OP}/recibocliente.php", d["body"],
            f"{_SMART_OP}/recibocliente.php?contrato=X&NumOperacao={op}")
    finally:
        robo.fechar_pagina(page)


def _http_promiss(ctx, page, op) -> bool:
    """NPP em 2 passos: POST montanotapromissoria.php + GET notapromissoria.php?
    Imprimir=... (o GET assina/finaliza). NAO clica Gerar."""
    from urllib.parse import quote
    with ctx.expect_page(timeout=15_000) as pi:
        robo.frame_com(page, "#imprimirNP", timeout=15).locator("#imprimirNP").click(timeout=10_000)
    pop = pi.value
    try:
        pop.wait_for_load_state("domcontentloaded", timeout=20_000)
        time.sleep(2)
        try:
            pop.locator("input[name='rTipoDocumento'][value='2']").check(timeout=5_000)
        except Exception:
            pass
        time.sleep(11)
        d = pop.evaluate(_JS_BODY, ["AssinaturasDigital", "Assinaturas"])
        extra = pop.evaluate(r"""() => {
            const f = document.Form || document.forms[0];
            const g = n => { const e=f.elements[n]; return e ? (e.length ? e[0].value : e.value) : ''; };
            const assin=[]; let adic='';
            for (const el of f.elements){ if(!el.name) continue;
              if((el.type==='checkbox'||el.type==='radio')&&!el.checked) continue;
              if(el.name==='chkAssinDigital') assin.push(el.value);
              if(el.name==='AssinaturaAdicional[]') adic=el.value; }
            return {dataE:g('dataE'), dataVenc:g('dataVenc'), join:assin.join(','), adic};
        }""")
        print(f"    [PROMISS {op}] assinaturas={d['assin']}")
        ok = _http_post_ok(
            ctx, f"{_SMART_OP}/montanotapromissoria.php", d["body"],
            f"{_SMART_OP}/notapromissoria.php?NumOperacao={op}")
        time.sleep(3)
        get_url = (
            f"{_SMART_OP}/notapromissoria.php?envioDocEmail=0&Imprimir={op}"
            f"&assinaturasDigital2={quote(extra['join'])}"
            f"&assinaturaAdicional={quote(extra['adic'])}&EmailRemetente=1"
            "&subCoobrigados=&subSocios=&operacaoESC=0&AssinaturasDigitalOU="
            f"&dataEmissao={quote(extra['dataE'])}&dataVencimento={quote(extra['dataVenc'])}"
            "&AssinaturaProcuradores=&datageracao=")
        try:
            rg = ctx.request.get(get_url, timeout=240_000)
            print(f"    [PROMISS {op}] GET finalizacao -> {rg.status}")
            ok = ok and (rg.status == 200)
        except Exception as e:
            print(f"    [PROMISS {op}] GET finalizacao falhou: {e}")
            ok = False
        return ok
    finally:
        robo.fechar_pagina(pop)


def _http_dup(ctx, op):
    """Duplicata via HTTP. Retorna:
      True       -> gerou (POST montaduplicatamercantil.php = 200)
      'SEM_DUP'  -> a op NAO tem duplicata (ex.: CTR/LCB) -> NAO e erro; a etapa
                    deve ser movida assim mesmo (Aditivo+NPP ja sairam)
      False      -> TEM itens de duplicata mas nao gerou (cota mensal / erro) -> revisao manual
    Deixa o JS do site montar o corpo complexo (arrays +-juntados), CAPTURA+ABORTA
    o POST do navegador e da REPLAY via HTTP."""
    page_url = f"{_SMART_OP}/duplicatadigital.php?NumOperacao={op}"
    monta_url = f"{_SMART_OP}/montaduplicatamercantil.php"
    dpage = ctx.new_page()
    cap = {}
    dlg = {}

    def on_route(route):
        try:
            if route.request.method == "POST" and not cap.get("body"):
                cap["body"] = route.request.post_data or ""
        except Exception:
            pass
        try:
            route.abort()
        except Exception:
            pass

    def on_dialog(d):
        dlg["msg"] = d.message
        try:
            d.accept()
        except Exception:
            pass
    try:
        dpage.route("**/montaduplicatamercantil.php", on_route)
        dpage.on("dialog", on_dialog)
        dpage.goto(page_url, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(3)
        # A op TEM itens de duplicata? CTR/LCB NAO tem -> nao e erro (mover assim mesmo).
        try:
            fr = robo.frame_com(dpage, "[name='cSelecionarTodosCasa'], #cSelecionarTodosCasa", timeout=12)
        except Exception:
            print(f"    [DUPLICATA {op}] pagina sem form de duplicata -> op SEM duplicata (CTR/LCB) - ok")
            return "SEM_DUP"
        try:
            n_itens = fr.evaluate("() => document.querySelectorAll('input[name=checkImpressao]').length")
        except Exception:
            n_itens = 0
        if not n_itens:
            print(f"    [DUPLICATA {op}] sem itens de duplicata -> op SEM duplicata (CTR/LCB) - ok")
            return "SEM_DUP"
        print(f"    [DUPLICATA {op}] {n_itens} item(ns) de duplicata")
        try:
            fr.locator("[name='cSelecionarTodosCasa'], #cSelecionarTodosCasa").first.check(timeout=4_000)
        except Exception:
            pass
        try:
            fr.locator("[name='lq'], #lq").first.uncheck(timeout=2_000)
        except Exception:
            pass
        time.sleep(2)
        try:
            fr.get_by_role("button", name="Gerar", exact=True).first.click(timeout=8_000)
        except Exception:
            for sel in ("#Input", "input[value='Gerar']", "input[value='GERAR']",
                        "button:has-text('Gerar')", "a:has-text('Gerar')"):
                try:
                    loc = fr.locator(sel).first
                    if loc.count() > 0:
                        loc.click(timeout=5_000)
                        break
                except Exception:
                    continue
        for _ in range(30):  # espera o JS montar+enviar (capturado e abortado)
            if cap.get("body"):
                break
            time.sleep(0.5)
        body = cap.get("body")
        if not body:
            motivo = (f"popup='{dlg['msg'][:70]}'" if dlg.get("msg")
                      else "sem POST em 15s (timing?)")
            print(f"    [DUPLICATA {op}] TEM itens mas nao gerou -> {motivo}")
            return False
        print(f"    [DUPLICATA {op}] corpo capturado ({len(body)}b)")
        return _http_post_ok(ctx, monta_url, body, page_url)
    finally:
        robo.fechar_pagina(dpage)


# Carta de cessao de credito: NAO fica na barra de documentos (pos-Resumir) - e
# acessada na pagina de edicao pelo botao "Docs" (#bDocumentos) -> link
# "Emitir a carta de cessao" -> popup emitircartacessao.php -> Digital -> Imprimir.
# Geracao real = POST emitircartacessao.php (mesmo padrao do Aditivo). O campo
# 'cedentes' e montado pelo JS como join dos chkCed (sacados selecionados).
_JS_CESSAO = r"""() => {
  const f = document.Form || document.forms[0];
  if(!f) return null;
  const ced = [];
  for (const el of f.elements) {
    if (!el.name) continue;
    if ((el.type==='checkbox'||el.type==='radio') && !el.checked) continue;
    if (el.name==='chkCed') ced.push(el.value);
  }
  const joined = ced.join(',');
  const parts = [];
  for (const el of f.elements) {
    if (!el.name) continue;
    if ((el.type==='checkbox'||el.type==='radio') && !el.checked) continue;
    let v = el.value;
    if (el.name==='cedentes' && (v===''||v==null)) v = joined;
    if (el.name==='Imprimir') v = '1';
    parts.push(encodeURIComponent(el.name)+'='+encodeURIComponent(v));
  }
  return {body: parts.join('&'), ced: ced};
}"""


def _http_cessao(ctx, op) -> bool:
    """Carta de cessao: abre a edicao, #bDocumentos -> 'carta de cessao' (que agora
    abre um MODAL em iframe: emitircartacessao.php?...&modal=1, nao mais popup) e
    le o form DE DENTRO do iframe; marca sacados (chkCed) + Digital e POSTa em
    emitircartacessao.php. NAO clica Imprimir. 200 = gerado.

    Mesma mudanca do Aditivo (Smart 28/07/2026: popup -> modal); lemos do iframe
    (navegar direto na URL do form nao monta certo). Ver _diag_dump_modal()."""
    page = ctx.new_page()
    page.on("dialog", lambda d: d.accept())
    try:
        page.goto(config.URL_EDITAR.format(op=op), wait_until="domcontentloaded", timeout=60_000)
        time.sleep(2)
        fr_edit = robo.frame_com(page, "#bDocumentos", timeout=20)
        fr_edit.locator("#bDocumentos").click()
        time.sleep(2)
        fr_edit.get_by_text("carta de cess", exact=False).first.click(timeout=8_000)
        # frame_com faz poll com round-trip -> enxerga o iframe do modal. chkCed so
        # existe no form da carta de cessao (nao na edicao) -> identifica o frame.
        fr = robo.frame_com(page, "input[name=chkCed]", timeout=25)
        # marca TODOS os sacados (chkCed) ANTES do Digital - nem sempre vem
        # pre-marcado; sem isso o 'cedentes' fica vazio e o POST volta 500 (o
        # auto-fill das assinaturas tambem depende dos sacados selecionados).
        try:
            nsac = fr.evaluate("""() => { let n=0;
                document.querySelectorAll('input[name=chkCed]').forEach(c => { if(!c.checked){ c.click(); } n++; });
                return n; }""")
            print(f"    [CESSAO {op}] sacados (chkCed) marcados: {nsac}")
        except Exception:
            pass
        time.sleep(2)
        try:
            fr.locator("input[name='rTipoDocumento'][value='2']").check(timeout=5_000)
        except Exception:
            pass
        time.sleep(11)  # auto-fill das assinaturas
        d = fr.evaluate(_JS_CESSAO)
        print(f"    [CESSAO {op}] cedentes(chkCed)={d['ced']}")
        return _http_post_ok(
            ctx, f"{_SMART_AJAX}/emitircartacessao.php", d["body"], fr.url)
    finally:
        robo.fechar_pagina(page)


def _diag_dump_modal(ctx, op) -> None:
    """DIAGNOSTICO read-only (ligado por env DIAG_MODAL=1). O Smart passou a abrir
    um MODAL na mesma pagina no lugar da popup -> o ctx.expect_page das funcoes de
    doc estoura. Aqui a gente clica cada botao SEM esperar janela, deixa o modal
    montar e faz DUMP de todos os frames (url + tem form 'Form'? + campos) + HTML +
    screenshot em DEBUG_DIR. NAO clica Gerar, NAO faz POST -> nao gera documento."""
    dbg = config.DEBUG_DIR if os.path.isabs(config.DEBUG_DIR) else os.path.join("/app", config.DEBUG_DIR)
    os.makedirs(dbg, exist_ok=True)

    def _dump(page, tag):
        base = os.path.join(dbg, f"diag_modal_{op}_{tag}")
        linhas = [f"=== op {op} | {tag} | page.url={page.url} ==="]
        for i, fr in enumerate(page.frames):
            try:
                tem_form = fr.evaluate("() => !!(document.Form || document.forms.length)")
                forms = fr.evaluate("() => [...document.forms].map(f => f.name||f.id||'?').slice(0,6)")
                campos = fr.evaluate(
                    "() => { const f=document.Form||document.forms[0]; "
                    "return f ? [...f.elements].map(e=>e.name).filter(Boolean).slice(0,50) : []; }")
                # pistas de modal: iframes visiveis, containers .modal/.ui-dialog
                modais = fr.evaluate(
                    "() => [...document.querySelectorAll("
                    "'iframe,.modal,.ui-dialog,[role=dialog],[class*=modal]')]"
                    ".map(e=>({tag:e.tagName,id:e.id,cls:e.className,src:e.getAttribute&&e.getAttribute('src')||''})).slice(0,10)")
            except Exception as e:
                tem_form, forms, campos, modais = f"err:{e}", [], [], []
            linhas.append(f"\n--- frame[{i}] url={fr.url}")
            linhas.append(f"    tem_form={tem_form} forms={forms}")
            linhas.append(f"    campos={campos}")
            linhas.append(f"    modais/iframes={modais}")
            try:
                with open(f"{base}_frame{i}.html", "w", encoding="utf-8") as fh:
                    fh.write(fr.content())
            except Exception:
                pass
        try:
            with open(f"{base}.txt", "w", encoding="utf-8") as fh:
                fh.write("\n".join(str(x) for x in linhas))
        except Exception as e:
            print(f"  [DIAG] falha ao gravar txt {tag}: {e}")
        try:
            page.screenshot(path=f"{base}.png", full_page=True)
        except Exception:
            pass
        print(f"  [DIAG] dump {tag} da op {op} -> {base}.*  ({len(page.frames)} frame(s))")

    # Aditivo + NPP: barra "Resumir" (pagina de edicao)
    for sel, tag in (("#aditivo", "aditivo"), ("#imprimirNP", "npp")):
        page = ctx.new_page()
        dlg = {}

        def _on_dialog(d, _dlg=dlg):
            _dlg.setdefault("msg", d.message)
            try:
                d.accept()
            except Exception:
                pass
        page.on("dialog", _on_dialog)
        try:
            page.goto(config.URL_EDITAR.format(op=op), wait_until="domcontentloaded", timeout=60_000)
            time.sleep(2)
            _abrir_resumir(page)
            try:
                robo.frame_com(page, sel, timeout=15).locator(sel).click(timeout=10_000)
            except Exception as e:
                print(f"  [DIAG] clique {sel} op {op}: {e}")
            time.sleep(6)   # deixa o modal montar (form + auto-fill)
            if dlg.get("msg"):
                print(f"  [DIAG] {tag}: DIALOG='{dlg['msg'][:150]}'")
            _dump(page, tag)
        finally:
            robo.fechar_pagina(page)

    # Cessao: pagina de edicao -> #bDocumentos -> "carta de cessao"
    page = ctx.new_page()
    dlg = {}

    def _on_dialog_c(d, _dlg=dlg):
        _dlg.setdefault("msg", d.message)
        try:
            d.accept()
        except Exception:
            pass
    page.on("dialog", _on_dialog_c)
    try:
        page.goto(config.URL_EDITAR.format(op=op), wait_until="domcontentloaded", timeout=60_000)
        time.sleep(2)
        fr = robo.frame_com(page, "#bDocumentos", timeout=20)
        fr.locator("#bDocumentos").click()
        time.sleep(2)
        try:
            fr.get_by_text("carta de cess", exact=False).first.click(timeout=8_000)
        except Exception as e:
            print(f"  [DIAG] clique carta cessao op {op}: {e}")
        time.sleep(6)
        if dlg.get("msg"):
            print(f"  [DIAG] cessao: DIALOG='{dlg['msg'][:150]}'")
        _dump(page, "cessao")
    finally:
        robo.fechar_pagina(page)


def digitais_vm(ctx) -> None:
    """Etapa "Enviar Digitais": para TODAS as operacoes (Home E Smart), gera
    documentos + duplicata e move p/ "Aguardando Ass."."""
    ops = robo.listar_operacoes_etapa(
        ctx, config.VALOR_ETAPA_ENVIAR_DIGITAIS, "Enviar Digitais")
    if not ops:
        print("  [DIGITAIS] nenhuma operacao em 'Enviar Digitais' (FIM)")
        return
    print(f"  [DIGITAIS] {len(ops)} operacao(oes): {ops}")
    # Filtro opcional p/ TESTE: DIGITAIS_ONLY_OP=<op> processa SO aquela op.
    _only = os.getenv("DIGITAIS_ONLY_OP", "").strip()
    if _only:
        ops = [o for o in ops if str(o) == _only]
        print(f"  [DIGITAIS] DIGITAIS_ONLY_OP={_only} -> ops filtradas: {ops}")
        if not ops:
            print(f"  [DIGITAIS] op {_only} nao esta na fila agora -> nada a fazer")
            return
    # Teto opcional p/ TESTE SUPERVISIONADO: DIGITAIS_MAX_OPS=1 processa so a 1a op
    # (valida o fix em 1 caso antes de liberar geral). 0/ausente = sem limite.
    _max = int(os.getenv("DIGITAIS_MAX_OPS", "0") or 0)
    if _max > 0 and len(ops) > _max:
        print(f"  [DIGITAIS] DIGITAIS_MAX_OPS={_max} -> processando so {ops[:_max]} "
              f"(demais {len(ops)-_max} ficam p/ o proximo ciclo)")
        ops = ops[:_max]
    # DIAGNOSTICO read-only: captura o modal novo e SAI (nao gera nada). Ligar so
    # p/ investigar a mudanca de UI do Smart (popup -> modal). Env DIAG_MODAL=1.
    if os.getenv("DIAG_MODAL", "").strip().lower() in ("1", "true", "yes", "sim"):
        # usa a op fixa (DIAG_MODAL_OP) SO se ela estiver de fato na fila agora;
        # senao captura a primeira op REAL da fila (evita mirar op que ja passou).
        _alvo_env = os.getenv("DIAG_MODAL_OP", "").strip()
        _na_fila = {str(o) for o in ops}
        alvo = _alvo_env if _alvo_env in _na_fila else str(ops[0])
        print(f"  [DIAG] DIAG_MODAL ligado -> capturando modal da op {alvo} (sem gerar nada)")
        try:
            _diag_dump_modal(ctx, alvo)
        except Exception as e:
            print(f"  [DIAG] erro no dump: {e}")
        return
    revisar = _carregar_ops_revisar()

    for op in ops:
        if str(op) in revisar:
            print(f"  [DIGITAIS] op {op} marcada p/ REVISAO MANUAL (parcial antes) "
                  "-> PULANDO (nao reprocessa, evita duplicar)")
            continue
        if config.DRY_RUN:
            print(f"  [DRY_RUN] geraria documentos/duplicata da op {op} "
                  "e mudaria etapa -> Aguardando Ass.")
            continue
        # um erro numa op (ex.: cota de duplicata) nao pode travar as demais
        try:
            _t_op = time.time()
            robo._bater(f"digitais op {op}")   # heartbeat (op leva ~120s)
            print(f"  [DIGITAIS] processando op {op}")
            # GERACAO VIA HTTP (recibocliente / montanotapromissoria / montaduplicata).
            # Marca Digital no form (auto-fill dos signatarios) e dispara o POST/GET
            # que GERA - sem clicar Gerar nem esperar o PDF renderizar. Se o 1o doc
            # (Aditivo) nao retornar 200, PULA a op (sem gerar o resto nem mover) ->
            # evita documento duplicado ao reprocessar.
            page = ctx.new_page()
            page.on("dialog", lambda d: d.accept())
            try:
                page.goto(config.URL_EDITAR.format(op=op),
                          wait_until="domcontentloaded", timeout=60_000)
                time.sleep(2)
                _abrir_resumir(page)   # abre a barra Resumir (necessaria p/ o NPP,
                #                        que AINDA usa popup via #imprimirNP). Aditivo
                #                        e Cessao nao usam mais esta pagina (viraram
                #                        modal -> navegam direto na URL do form).
                ok_aditivo = _http_aditivo(ctx, op)
                if not ok_aditivo:
                    print(f"  [DIGITAIS] op {op}: Aditivo nao retornou 200 (1a). Retentando...")
                    ok_aditivo = _http_aditivo(ctx, op)
                if not ok_aditivo:
                    print(f"  [DIGITAIS] op {op}: Aditivo falhou 2x -> PULANDO op "
                          "(sem gerar resto, sem mover). Tratamento manual.")
                    continue
                ok_promiss = _http_promiss(ctx, page, op)
                time.sleep(getattr(config, "ESPACO_NPP_DUP", 15))  # espacamento NPP -> Duplicata
                ok_dup = _http_dup(ctx, op)
                # carta de cessao por ULTIMO (obrigatoria p/ mover - toda op tem)
                ok_cessao = _http_cessao(ctx, op)
            finally:
                robo.fechar_pagina(page)
            # Duplicata: True=gerou, 'SEM_DUP'=op nao tem duplicata (CTR/LCB, ok),
            # False=tem itens mas falhou (cota/erro). SEM_DUP NAO bloqueia o move.
            dup_ok = (ok_dup is True) or (ok_dup == "SEM_DUP")
            if ok_promiss and dup_ok and ok_cessao:
                # move e VERIFICA. Se nao mover, marca p/ revisao manual: NAO pode
                # reprocessar (regeraria os docs = DUPLICADOS) e nao pode ficar
                # em loop na etapa "Enviar Digitais".
                # RETRY do MOVE: mover etapa e IDEMPOTENTE (nao duplica nada, ao
                # contrario de re-gerar os docs) -> retenta ate 3x antes de desistir,
                # p/ nao mandar p/ revisao manual por falha TRANSITORIA de pagina
                # (ex.: "#etapaOperacao nao encontrado" quando a tela nao carregou).
                movida = False
                for _tent_move in range(1, 4):
                    try:
                        movida = _mudar_etapa(ctx, op, config.ROTULO_AGUARDANDO_ASS)
                    except Exception as e:
                        print(f"  [DIGITAIS] erro ao mover etapa da op {op} "
                              f"(tentativa {_tent_move}/3): {e}")
                    if movida:
                        break
                    if _tent_move < 3:
                        time.sleep(4)   # backoff antes de retentar o move
                if movida:
                    _sem = " (op SEM duplicata - CTR/LCB)" if ok_dup == "SEM_DUP" else ""
                    print(f"  [DIGITAIS] op {op} concluida (docs gerados + etapa movida p/ Aguardando Ass.){_sem} "
                          f"[op levou {time.time()-_t_op:.0f}s]")
                else:
                    _marcar_op_revisar(op)
                    print(f"  [DIGITAIS] op {op}: docs gerados MAS a etapa NAO mudou "
                          "-> marcada p/ REVISAO MANUAL (nao reprocessa, evita duplicar). "
                          "MOVA manualmente p/ 'Aguardando Ass.'.")
            else:
                # parcial: Aditivo (e talvez Promissoria) ja sairam -> NAO pode
                # reprocessar (duplicaria). Marca p/ revisao manual permanente.
                _marcar_op_revisar(op)
                print(f"  [DIGITAIS] op {op} PARCIAL (promiss={ok_promiss} "
                      f"dup={ok_dup} cessao={ok_cessao}) - marcada p/ REVISAO MANUAL (nao reprocessa)")
        except Exception as e:
            print(f"  [DIGITAIS] erro na op {op} (ignorado, segue p/ proxima): {e}")
