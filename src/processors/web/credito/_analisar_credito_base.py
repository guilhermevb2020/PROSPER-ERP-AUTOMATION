"""
Robo de Analise de Credito - Smart Securities
==============================================

Replica em Python (Playwright) do fluxo do Power Automate Desktop
"robo analise de credito.txt".

A estrutura segue 1:1 o fluxo original. Os comentarios indicam as linhas
correspondentes do .txt para auditoria.

Fluxo geral:
  LOOP 1..100 (reinicios)                              -> main()
    +-- (em caso de erro) BLOCK 'reiniciar 2'          -> bloco_reiniciar_2()
    +-- BLOCK reiniciar                                -> bloco_reiniciar()
          +-- login (com reCAPTCHA manual)             -> login()
          +-- LOOP 1..1000 (operacoes)                 -> loop_operacoes()
                +-- LOOP 1..2                           -> processar_operacao()
                +-- sub-fluxo DIGITAIS - VM
                +-- sub-fluxo BAIXAR NF E RESUMO
                +-- WAIT 40
"""

import os
import sys
import time
import unicodedata
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

import config
import subfluxos
import _watchdog


# --------------------------------------------------------------------------- #
# Watchdog (anti-travamento) - global injetado pelo main(); o loop bate o
# heartbeat a cada passo. None = sem watchdog (ex.: testes isolados).
# --------------------------------------------------------------------------- #
_watchdog_atual = None


def _bater(etapa: str = "") -> None:
    """Marca atividade no watchdog (no-op se nao houver)."""
    if _watchdog_atual is not None:
        _watchdog_atual.bater(etapa)


# --------------------------------------------------------------------------- #
# Janela de operacao (opcao B: o robo para sozinho no fim do expediente).
# Horario de Brasilia via offset FIXO -3 (Brasil sem horario de verao desde 2019),
# p/ nao depender do TZ do container (que roda em UTC) nem de tzdata.
# --------------------------------------------------------------------------- #
_TZ_BRT = timezone(timedelta(hours=-3))


def _dentro_janela() -> bool:
    """True se o horario de Brasilia esta em [JANELA_INICIO, JANELA_FIM). Fora
    dela o robo encerra limpo. Em erro de parse retorna True (nao trava o robo)."""
    try:
        ini = tuple(int(x) for x in config.JANELA_INICIO.split(":"))
        fim = tuple(int(x) for x in config.JANELA_FIM.split(":"))
        agora = datetime.now(_TZ_BRT)
        hm = (agora.hour, agora.minute)
        return ini <= hm < fim
    except Exception:
        return True


# --------------------------------------------------------------------------- #
# Utilitarios
# --------------------------------------------------------------------------- #
def esperar(segundos: int, motivo: str = "") -> None:
    """Equivalente ao WAIT do PAD (em segundos)."""
    if motivo:
        print(f"  [wait {segundos}s] {motivo}")
    time.sleep(segundos)


def frame_com(page: Page, seletor: str, timeout: float = 30.0):
    """Encontra o frame (iframe/frameset/frame) que contem o seletor.

    O Smart Securities aninha o conteudo em iframe[name=stage] -> frameset ->
    frame, entao varremos todos os frames ate achar o elemento. Substitui a
    navegacao de frames que o PAD fazia implicitamente nos seletores 'appmask'.
    """
    fim = time.time() + timeout
    while time.time() < fim:
        for fr in page.frames:
            try:
                if fr.locator(seletor).count() > 0:
                    return fr
            except Exception:
                continue
        time.sleep(0.5)
    raise PWTimeout(f"Seletor '{seletor}' nao encontrado em nenhum frame da pagina.")


def fechar_pagina(page) -> None:
    """Fecha uma pagina ignorando erros (equivale ao 'ON ERROR / END' do PAD)."""
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def salvar_diagnostico(page: Page, nome: str) -> None:
    """Salva screenshot + HTML de cada frame para diagnostico (DEBUG)."""
    import os
    os.makedirs(config.DEBUG_DIR, exist_ok=True)
    base = os.path.join(config.DEBUG_DIR, nome)
    try:
        page.screenshot(path=f"{base}.png", full_page=True)
    except Exception as e:
        print(f"  [debug] screenshot falhou: {e}")
    try:
        partes = []
        for i, fr in enumerate(page.frames):
            try:
                partes.append(f"\n\n<!-- ===== FRAME {i}: {fr.url} ===== -->\n"
                              + fr.content())
            except Exception:
                continue
        with open(f"{base}.html", "w", encoding="utf-8") as fh:
            fh.write("".join(partes))
        print(f"  [debug] diagnostico salvo em {base}.png / .html")
    except Exception as e:
        print(f"  [debug] dump html falhou: {e}")


# --------------------------------------------------------------------------- #
# BLOCK 'reiniciar 2'  (linhas 4-16) - rotina de limpeza/recuperacao
# --------------------------------------------------------------------------- #
def bloco_reiniciar_2(ctx) -> None:
    """Limpeza executada quando o bloco principal falha (GOTO reinicair).

    No PAD os passos de clicar em 'Sair' estavam DESABILITADOS (DISABLE), logo
    o efeito real e: abrir a tela de boleto, esperar e fechar tudo. Aqui
    fechamos todas as paginas abertas (equivale a matar a janela do Chrome
    pela barra de tarefas, linhas 14-15) e aguardamos.
    """
    print("[reiniciar 2] limpando sessao do navegador...")
    try:
        page = ctx.new_page()
        page.goto(config.URL_BOLETO, wait_until="domcontentloaded", timeout=60_000)
        esperar(6, "estabilizando tela de boleto")
        fechar_pagina(page)
    except Exception as e:
        print(f"  [reiniciar 2] aviso: {e}")

    # Linhas 14-15: fechar a janela do Chrome. Em Playwright, fechamos todas as paginas.
    for p in list(ctx.pages):
        fechar_pagina(p)

    esperar(config.WAIT_POS_CLEANUP, "apos limpeza (WAIT 20)")  # linha 16


# --------------------------------------------------------------------------- #
# Login  (linhas 22-48)
# --------------------------------------------------------------------------- #
def esta_logado(ctx) -> bool:
    """Checagem barata pela URL, REUTILIZANDO a aba de operacoes (nao abre/fecha
    aba a cada ciclo). Deslogado vai p/ raiz/loginsec; logado fica sob /smart/."""
    try:
        p = _pagina_busca(ctx)            # MESMA aba de operacoes (nao fecha)
        p.goto(config.URL_CONSULTA, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(1.5)
        u = p.url.lower()
        if "loginsec" in u or "/smart/" not in u:
            return False
        # a pagina "Sua sessão expirou! ... faça login" tambem fica sob /smart/
        for fr in p.frames:
            try:
                txt = (fr.locator("body").inner_text(timeout=2000) or "").lower()
            except Exception:
                continue
            if "expirou" in txt or "faça login" in txt or "faca login" in txt:
                return False
        return True
    except Exception:
        return False


def login(ctx):
    """Autentica (tratando reCAPTCHA). Se a sessao do perfil ja for valida,
    nao faz nada -- evita relogin desnecessario."""
    if esta_logado(ctx):
        print("  sessao ja valida -> sem novo login")
        return
    # vai relogar -> a aba de consulta cacheada esta com estado invalido
    _invalidar_busca()
    page = ctx.new_page()
    page.goto(config.URL_LOGIN, wait_until="domcontentloaded", timeout=60_000)  # linha 22

    # O formulario de login fica dentro de um <iframe> (body#bodyindexsistema).
    fr = frame_com(page, config.SEL_LOGIN_EMAIL)

    # Linhas 23-29: preencher email e senha (fill ja limpa o campo, equivalendo
    # aos {Back} do PAD).
    fr.locator(config.SEL_LOGIN_EMAIL).fill(config.EMAIL)
    esperar(1)  # linha 26
    try:
        fr.locator(config.SEL_LOGIN_SENHA).fill(config.SENHA)
    except Exception:
        # Fallback fiel ao PAD: Tab a partir do email e digitar a senha.
        fr.locator(config.SEL_LOGIN_EMAIL).press("Tab")
        page.keyboard.type(config.SENHA, delay=10)

    # Linha 30: botao 'Entrar' (#OK, type=submit)
    try:
        fr.locator(config.SEL_LOGIN_ENTRAR).click()
    except Exception as e:
        print(f"  [login] aviso ao clicar Entrar: {e}")

    # ----------------------------------------------------------------------- #
    # reCAPTCHA "Não sou um robô" (linhas 34-46)
    # ----------------------------------------------------------------------- #
    tratar_recaptcha(page)

    esperar(config.WAIT_POS_LOGIN, "apos login")  # linha 48
    return page


def _capsolver_token(site_url: str, site_key: str, timeout: int = 180, tentativas: int = 3):
    """Resolve reCAPTCHA v2 via CapSolver HTTP (mesma lógica dos boletos). RETENTA
    em erros TRANSITORIOS (conexao abortada/RemoteDisconnected, erro 1001) ate
    `tentativas` vezes — a API do CapSolver falha por rede de vez em quando."""
    import requests
    api_key = os.getenv("CAPSOLVER_API_KEY", "").strip()
    if not api_key:
        print("  [login] CAPSOLVER_API_KEY ausente")
        return None
    for tent in range(1, tentativas + 1):
        try:
            r = requests.post("https://api.capsolver.com/createTask", json={
                "clientKey": api_key,
                "task": {"type": "ReCaptchaV2TaskProxyLess",
                         "websiteURL": site_url, "websiteKey": site_key}}, timeout=30)
            d = r.json() if r.status_code == 200 else {}
            if d.get("errorId") != 0:
                print(f"  [login] CapSolver createTask (tent {tent}/{tentativas}):",
                      d.get("errorDescription"))
                time.sleep(3)
                continue
            task_id = d.get("taskId")
            fim = time.time() + timeout
            while time.time() < fim:
                _bater("capsolver")   # heartbeat enquanto resolve o captcha
                time.sleep(2)
                rr = requests.post("https://api.capsolver.com/getTaskResult",
                                   json={"clientKey": api_key, "taskId": task_id}, timeout=30)
                dd = rr.json() if rr.status_code == 200 else {}
                if dd.get("errorId") != 0:
                    break   # erro na task -> sai do poll e retenta criar
                if dd.get("status") == "ready":
                    return (dd.get("solution") or {}).get("gRecaptchaResponse")
            # poll esgotou sem resposta -> retenta
        except Exception as e:
            print(f"  [login] CapSolver erro (tent {tent}/{tentativas}):", e)
            time.sleep(3)
    print(f"  [login] CapSolver falhou apos {tentativas} tentativas")
    return None


def tratar_recaptcha(page: Page) -> None:
    """CapSolver (substitui o manual do PAD): resolve o reCAPTCHA, injeta o token e
    ACIONA os data-callbacks (senão o Smart não habilita Acessar), clica Acessar/
    #OKExtra e trata seleção de empresa + modal de segurança."""
    SITE_KEY = "6Le-JHwUAAAAAGZJWerkysOyQeo-Ehm7704vfT1q"
    esperar(3, "iframe recarregar com reCAPTCHA")
    token = _capsolver_token(config.URL_LOGIN, SITE_KEY)
    if token:
        for fr in page.frames:
            try:
                fr.evaluate(
                    "(t)=>{let n=0;document.querySelectorAll('textarea[name=\"g-recaptcha-response\"],"
                    "textarea[id^=\"g-recaptcha-response\"]').forEach(x=>{x.value=t;x.innerHTML=t;n++;});"
                    "const w=document.defaultView||window;document.querySelectorAll('.g-recaptcha').forEach("
                    "e=>{const c=e.getAttribute('data-callback');if(c&&typeof w[c]==='function')"
                    "{try{w[c](t);n++;}catch(_){}}});return n;}", token)
            except Exception:
                continue
        print(f"  [login] token CapSolver injetado + callbacks ({len(token)} chars)")
    else:
        print("  [login] CapSolver não resolveu — seguindo mesmo assim")

    esperar(1)
    clicou = False
    for _ in range(12):
        for fr in page.frames:
            for sel in (config.SEL_ACESSAR, "#OKExtra", "[name='OKExtra']", "#OK"):
                try:
                    loc = fr.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        loc.click(timeout=3000)
                        clicou = True
                        break
                except Exception:
                    continue
            if clicou:
                break
        if clicou:
            break
        esperar(2)
    print("  [login] Acessar pós-captcha:", "clicado" if clicou else "não achei")

    esperar(4)
    for _ in range(3):
        emp = False
        for fr in page.frames:
            try:
                b = fr.locator("a:has-text('Acessar'), button:has-text('Acessar'), "
                               "input[value='Acessar']").first
                if b.count() > 0 and b.is_visible():
                    b.click(timeout=5000)
                    emp = True
                    break
            except Exception:
                pass
            try:
                fr.evaluate("()=>{const b=[...document.querySelectorAll('button,input,a')]"
                            ".find(e=>((e.innerText||e.value||'').trim().toLowerCase())==='prosseguir');"
                            "if(b){b.click();}}")
            except Exception:
                pass
        if emp:
            break
        esperar(2)
    aguardar_login_concluido(page, timeout=120)


def aguardar_login_concluido(page: Page, timeout: int = 240) -> None:
    """Espera ate o formulario de login desaparecer (login efetuado na tela)."""
    print(f"  aguardando login manual (ate {timeout}s)...")
    fim = time.time() + timeout
    while time.time() < fim:
        _bater("aguardando login")   # heartbeat: o login pode demorar ~2 min
        ainda_no_login = any(
            _tem_seletor(fr, config.SEL_LOGIN_EMAIL) for fr in page.frames
        )
        if not ainda_no_login:
            print("  login detectado, prosseguindo.")
            return
        time.sleep(3)
    print("  tempo esgotado aguardando login; prosseguindo mesmo assim.")


def _tem_seletor(frame, seletor: str) -> bool:
    try:
        return frame.locator(seletor).count() > 0
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Processar UMA operacao (corpo do LOOP 1..2, linhas 52-100)
# --------------------------------------------------------------------------- #
class SemOperacao(Exception):
    """Sinaliza o GOTO FIMSALVAR (nenhuma operacao pendente encontrada)."""


class SistemaForaDaJanela(Exception):
    """Sinaliza fim do expediente (opcao B) -> encerra o robo, sem reiniciar."""


def listar_operacoes_etapa(ctx, valor_etapa: str, rotulo: str = "") -> list:
    """Retorna TODOS os numeros de operacao na etapa, somando os DOIS tipos de
    consulta (Home-Securities e SmartSecurities). Sem duplicatas."""
    todas = []
    for sel_tipo in (config.SEL_RADIO_TIPO_HOME, config.SEL_RADIO_TIPO_SMART):
        tipo_nome = "Home" if sel_tipo == config.SEL_RADIO_TIPO_HOME else "Smart"
        for n in _buscar_numeros_uma(ctx, valor_etapa, f"{rotulo}/{tipo_nome}", sel_tipo):
            if n not in todas:
                todas.append(n)
    return todas


def buscar_proxima_operacao(ctx, valor_etapa: str, rotulo: str = "") -> str:
    """Devolve a 1a operacao na etapa (ou None). Usa listar_operacoes_etapa."""
    ops = listar_operacoes_etapa(ctx, valor_etapa, rotulo)
    return ops[0] if ops else None


# Aba de consulta REUTILIZAVEL: em vez de abrir/fechar uma aba a cada busca
# (cada etapa x cada tipo), mantemos UMA aba e so trocamos o filtro + Pesquisar.
_PAGINA_BUSCA = None


def _invalidar_busca() -> None:
    """Fecha/zera a aba de consulta cacheada (forca recriacao na proxima busca).
    Chamar ao relogar ou apos erro, p/ nao reaproveitar estado invalido."""
    global _PAGINA_BUSCA
    fechar_pagina(_PAGINA_BUSCA)
    _PAGINA_BUSCA = None


def _pagina_busca(ctx):
    """Devolve a aba de consulta reutilizavel (cria/navega se nao existir ou se
    morreu). O 'Trocar layout' e tratado em _buscar_numeros_uma (best-effort)."""
    global _PAGINA_BUSCA
    p = _PAGINA_BUSCA
    try:
        morta = (p is None) or p.is_closed()
    except Exception:
        morta = True
    if morta:
        p = ctx.new_page()
        _PAGINA_BUSCA = p
        try:
            total = len(ctx.pages)
        except Exception:
            total = -1
        print(f"  [aba operacoes] ABRINDO a janela de operacoes (abas abertas={total})")
        p.goto(config.URL_CONSULTA, wait_until="domcontentloaded", timeout=60_000)
    return p


# --------------------------------------------------------------------------- #
# Resultado da consulta: esperar a RECARGA e conferir a ETAPA de cada linha
# --------------------------------------------------------------------------- #
# Medido em 22/09/2026 (inspecao da tela): o Pesquisar faz POST de conoperacao.php no
# frame 'pesq', que troca de documento. ANTES da 1a pesquisa esse frame ja mostra as 10
# operacoes mais recentes, de QUALQUER etapa e das duas securitizadoras. Com a espera
# fixa de 1,5 s, quando o Smart demorava, a leitura pegava essa tabela (9x no credito em
# 22/09) e o job processava operacao de outra etapa: 65854 e 65877 sairam de
# 'Aguardando Ass.' para 'Analise de credito', com a classe de risco dos titulos trocada.
# Agora: (1) so le depois que o frame de resultado troca de documento; (2) so devolve a
# linha cuja coluna Etapa e a pesquisada. Sem a coluna, nada e devolvido: quem consome
# muda etapa e grava, e na duvida nao age.
FRAME_RESULTADO = "pesq"

_JS_LINHAS_CONSULTA = r"""() => {
  for (const t of document.querySelectorAll('table')) {
    const cab = Array.from(t.querySelectorAll('th')).map(th => (th.innerText || '').trim());
    let iEtapa = cab.findIndex(h => /^etapa$/i.test(h));
    if (iEtapa < 0) iEtapa = cab.findIndex(h => /etapa/i.test(h));
    const linhas = [];
    for (const r of t.querySelectorAll('tbody tr')) {
      const td = r.querySelectorAll('td');
      if (td.length < 3) continue;
      const num = (td[2].innerText || '').trim();
      if (!/^\d+$/.test(num)) continue;
      linhas.push({num: num,
                   etapa: (iEtapa >= 0 && td[iEtapa]) ? (td[iEtapa].innerText || '').trim() : null});
    }
    if (linhas.length) return {linhas: linhas, tem_etapa: iEtapa >= 0};
  }
  return {linhas: [], tem_etapa: null};
}"""


def _norm_etapa(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if c.isalnum()).lower()


def filtrar_por_etapa(linhas, alvos):
    """Separa (aceitas, descartadas): aceita a linha cuja coluna Etapa casa com algum
    dos rotulos `alvos`, sem acento, caixa, espaco ou pontuacao."""
    alvos_n = {_norm_etapa(a) for a in alvos} - {""}
    aceitas, descartadas = [], []
    for linha in linhas:
        (aceitas if _norm_etapa(linha.get("etapa")) in alvos_n else descartadas).append(linha)
    return aceitas, descartadas


def numeros_conferidos(dados, alvos):
    """-> (numeros, descartadas, motivo). `motivo` preenchido = nada foi devolvido
    porque nao da para conferir a etapa (sem coluna Etapa ou sem rotulo alvo)."""
    linhas = (dados or {}).get("linhas") or []
    if not linhas:
        return [], [], None
    if not dados.get("tem_etapa"):
        return [], linhas, "a tabela de resultado nao tem a coluna Etapa"
    if not {_norm_etapa(a) for a in alvos} - {""}:
        return [], linhas, "sem o rotulo da etapa pesquisada para conferir"
    aceitas, descartadas = filtrar_por_etapa(linhas, alvos)
    numeros = []
    for linha in aceitas:
        if linha["num"] not in numeros:
            numeros.append(linha["num"])
    return numeros, descartadas, None


def _linhas_da_consulta(page) -> dict:
    """Linhas {num, etapa} da tabela de resultado. So o frame de resultado, se ele
    existir; sem ele, o primeiro frame com linhas (o comportamento antigo)."""
    fr = page.frame(name=FRAME_RESULTADO)
    for f in ([fr] if fr is not None else list(page.frames)):
        try:
            dados = f.evaluate(_JS_LINHAS_CONSULTA)
        except Exception:
            continue
        if dados and dados.get("linhas"):
            return dados
    return {"linhas": [], "tem_etapa": None}


def _marcar_resultado(page):
    """Marca o documento ATUAL do frame de resultado. -> (frame, marca) ou (None, None)."""
    fr = page.frame(name=FRAME_RESULTADO)
    if fr is None:
        return None, None
    marca = f"busca-{time.time():.6f}"
    try:
        fr.evaluate("m => { window.__buscaAntiga = m; }", marca)
    except Exception:
        return None, None
    return fr, marca


def _esperar_recarga(fr, marca, limite_s: float, intervalo: float = 0.25) -> bool:
    """True quando o frame trocou de documento (a marca sumiu) e terminou de carregar."""
    fim = time.time() + limite_s
    while time.time() < fim:
        try:
            if fr.evaluate("m => window.__buscaAntiga !== m && document.readyState === 'complete'",
                           marca):
                return True
        except Exception:
            pass          # navegando: o contexto foi destruido no meio da leitura
        time.sleep(intervalo)
    return False


def _buscar_numeros_uma(ctx, valor_etapa: str, rotulo: str, sel_tipo: str,
                        _tentativa: int = 0) -> list:
    """Uma busca (um tipo) REUTILIZANDO a aba de consulta: garante o layout,
    marca o tipo, filtra a etapa, pesquisa e extrai os numeros. NAO abre/fecha
    aba. Em caso de erro, invalida a aba e tenta UMA vez recriando-a (p/ nao
    perder operacoes por um problema transitorio de pagina)."""
    try:
        page_busca = _pagina_busca(ctx)

        # 'Trocar layout' -> clicar no ICONE <i> (so existe no layout errado;
        # se ja estiver no layout certo, o botao nao existe e isto e no-op).
        try:
            frame_com(page_busca, config.SEL_TROCAR_LAYOUT, timeout=3) \
                .locator(config.SEL_TROCAR_LAYOUT).click()
            esperar(2, "aguardando o layout assentar")
        except Exception:
            pass

        # tipo de consulta (Home ou Smart) + radio de pesquisa por etapa
        for sel_radio in (sel_tipo, config.SEL_RADIO_PESQUISA):
            try:
                frame_com(page_busca, sel_radio, timeout=5).locator(sel_radio).check()
            except Exception:
                pass

        # CRITICO: filtro de etapa (sem ele a pesquisa traz "Todas as etapas").
        fr_etapa = frame_com(page_busca, config.SEL_FILTRO_ETAPA, timeout=15)
        fr_etapa.locator(config.SEL_FILTRO_ETAPA).select_option(value=valor_etapa)
        valor_sel = fr_etapa.locator(config.SEL_FILTRO_ETAPA).input_value()
        try:
            rotulo_sel = (fr_etapa.locator(config.SEL_FILTRO_ETAPA).evaluate(
                "s => (s.options[s.selectedIndex] || {}).text || ''") or "").strip()
        except Exception:
            rotulo_sel = ""
        # a linha vale se a coluna Etapa casar com o rotulo da opcao OU com o do chamador
        alvos = [rotulo_sel, (rotulo or "").split("/")[0]]

        fr_res, marca = _marcar_resultado(page_busca)
        frame_com(page_busca, config.SEL_PESQUISAR).locator(config.SEL_PESQUISAR).click()
        if fr_res is not None:
            if not _esperar_recarga(fr_res, marca, config.WAIT_MAX_PESQUISA):
                raise RuntimeError(f"a pesquisa nao recarregou o resultado em "
                                   f"{config.WAIT_MAX_PESQUISA:.0f}s (tabela antiga na tela)")
        else:
            print(f"  [busca] frame '{FRAME_RESULTADO}' nao achado: espera fixa "
                  "(a etapa de cada linha continua conferida)")
            esperar(config.WAIT_POS_PESQUISA, "aguardando resultado da pesquisa")

        if config.DEBUG:
            salvar_diagnostico(page_busca, f"consulta_{rotulo}".replace("/", "_"))

        nums, descartadas, motivo = numeros_conferidos(_linhas_da_consulta(page_busca), alvos)
        if motivo:
            print(f"  [busca] ATENCAO '{rotulo}': {motivo} - {len(descartadas)} linha(s) "
                  "NAO devolvida(s)")
        elif descartadas:
            print(f"  [busca] '{rotulo}': {len(descartadas)} op(s) de OUTRA etapa descartada(s): "
                  f"{[(d['num'], d['etapa']) for d in descartadas][:10]}")
        print(f"  filtro fEtapaOperacao={valor_sel} ({rotulo}): {len(nums)} op(s) {nums}")
        return nums
    except Exception as e:
        print(f"  [busca] erro em '{rotulo}': {e}")
        _invalidar_busca()
        if _tentativa == 0:
            # recria a aba (proxima _pagina_busca faz goto+layout) e tenta de novo
            return _buscar_numeros_uma(ctx, valor_etapa, rotulo, sel_tipo, _tentativa=1)
        return []


def processar_operacao(ctx) -> None:
    page_edit = page_status = None
    try:
        # Busca a proxima operacao em "Análise Home" (linhas 53-72).
        numero_op = buscar_proxima_operacao(
            ctx, config.VALOR_ETAPA_ANALISE_HOME, "Análise Home")
        if not numero_op:
            raise SemOperacao()
        print(f"  >> operacao encontrada: {numero_op}")

        if config.DRY_RUN:
            print(f"  [DRY_RUN] pularia Salvar e mudanca de status da op {numero_op} "
                  "(nenhum dado de producao alterado)")
        else:
            # Linhas 76-78: abrir edicao (Browser99) e Salvar
            page_edit = ctx.new_page()
            page_edit.goto(config.URL_EDITAR.format(op=numero_op),
                           wait_until="domcontentloaded", timeout=60_000)
            esperar(config.WAIT_POS_SALVAR, "carregando tela de edicao")  # linha 77
            if config.DEBUG:
                salvar_diagnostico(page_edit, f"edicao_op{numero_op}_antes_salvar")
            # HOOK PRE-SALVAR (V3): ajusta a classe de risco dos titulos ANTES do SALVAR.
            if pre_salvar_hook:
                try:
                    pre_salvar_hook(page_edit, numero_op)
                except Exception as e:
                    print(f"  [pre_salvar_hook] erro ignorado: {e}")
            botao_salvar = frame_com(page_edit, config.SEL_SALVAR).locator(config.SEL_SALVAR)
            # espera o botao habilitar (ate 8s) p/ nao travar 30s se vier disabled
            fim = time.time() + 8
            while time.time() < fim and not botao_salvar.is_enabled():
                time.sleep(0.5)
            if botao_salvar.is_enabled():
                botao_salvar.click(timeout=8_000)
                print(f"  >> SALVAR clicado para op {numero_op}")
                # Aguarda o Salvar processar server-side: e isso que habilita o
                # #etapaOperacao (em Análise Home ele vem disabled ate o Salvar).
                try:
                    page_edit.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                esperar(3, "aguardando o Salvar processar")
            else:
                print(f"  [salvar] botao continua desabilitado p/ op {numero_op}; seguindo")

            # Linhas 79-80: reabrir edicao (mudarstatus) e mudar status p/ Feedback ROB
            page_status = ctx.new_page()
            page_status.goto(config.URL_EDITAR.format(op=numero_op),
                             wait_until="domcontentloaded", timeout=60_000)
            try:
                selecionar_etapa_edicao(page_status, config.OPCAO_STATUS_FEEDBACK)
            except Exception as e:
                print(f"  [status] aviso ao mudar status: {e}")
            esperar(config.WAIT_POS_SALVAR, "apos mudar status")  # linha 81

    except SemOperacao:
        # LABEL FIMSALVAR (linha 94): nenhuma operacao -> apenas fecha e segue.
        print("  >> nenhuma operacao pendente (FIMSALVAR)")
    finally:
        # Linhas 82-95: fechar as janelas de edicao/status (cada uma ON ERROR/END)
        for p in (page_status, page_edit):
            fechar_pagina(p)


def extrair_numeros_operacao(page: Page) -> list:
    """Retorna TODOS os numeros de operacao (coluna 'Número', 3a celula) da
    tabela de resultados. Lista vazia se nao houver registros."""
    for fr in page.frames:
        try:
            linhas = fr.locator("table tbody tr")
            nums = []
            for i in range(linhas.count()):
                celulas = linhas.nth(i).locator("td")
                if celulas.count() >= 3:
                    t = (celulas.nth(2).inner_text() or "").strip()
                    if t.isdigit():
                        nums.append(t)
            if nums:
                return nums
        except Exception:
            continue
    return []


def extrair_numero_operacao(page: Page):
    """Linha 72: ExtractSingleValue do numero da operacao na tabela de resultados.

    Procura o frame com a tabela de resultados e le a 3a coluna (td:eq(2)).
    Retorna None se nao houver resultado (equivale ao ON ERROR -> FIMSALVAR).
    """
    try:
        fr = frame_com(page, config.CSS_NUMERO_OPERACAO, timeout=15)
        texto = fr.locator(config.CSS_NUMERO_OPERACAO).first.inner_text(timeout=10_000)
        return texto.strip() or None
    except Exception:
        # Fallback: primeira celula numerica de qualquer tabela de resultados.
        try:
            for fr in page.frames:
                celulas = fr.locator("table tbody tr td")
                n = celulas.count()
                for i in range(min(n, 30)):
                    t = (celulas.nth(i).inner_text() or "").strip()
                    if t.isdigit():
                        return t
        except Exception:
            pass
    return None


def selecionar_etapa_edicao(page, rotulo: str) -> None:
    """Na tela de EDICAO, muda o status/etapa (#etapaOperacao) pela LABEL.

    O <select id=etapaOperacao> da edicao difere do filtro #fEtapaOperacao da
    consulta; a selecao e por texto da opcao (igual ao SetDropDownListValueByName
    OptionNames do PAD). A mudanca dispara o onchange que salva via AJAX.
    """
    page.on("dialog", lambda d: d.accept())  # confirma eventual confirm JS
    # esperar a pagina carregar ANTES de mexer no select. Usamos 'load' (e nao
    # 'networkidle') porque o Smart mantem conexoes abertas e o networkidle
    # quase sempre estoura o tempo cheio sem necessidade.
    try:
        page.wait_for_load_state("load", timeout=10_000)
    except Exception:
        pass
    fr = frame_com(page, config.SEL_STATUS_EDICAO, timeout=25)
    sel = fr.locator(config.SEL_STATUS_EDICAO).first
    # o #etapaOperacao pode vir DESABILITADO por alguns segundos -> esperar
    fim = time.time() + 12
    while time.time() < fim and not sel.is_enabled():
        time.sleep(0.5)
    # seleciona pela label; se nao casar exatamente, tenta por texto normalizado
    try:
        sel.select_option(label=rotulo)
    except Exception:
        casou = False
        for i in range(sel.locator("option").count()):
            o = sel.locator("option").nth(i)
            txt = (o.inner_text() or "").strip()
            if txt.lower() == rotulo.strip().lower() or rotulo.strip().lower() in txt.lower():
                sel.select_option(value=(o.get_attribute("value") or ""))
                casou = True
                break
        if not casou:
            raise
    print(f"  status (#etapaOperacao) -> {rotulo}")
    # O onchange (changeEtapa) salva via AJAX. Em algumas transicoes abre o
    # modal #modalAlterarEtapaOperacao -> confirmar 'Mover operação' (procura em
    # todos os frames, com timeout maior).
    _confirmar_modal_mover(page, timeout=6)
    # aguarda o AJAX de gravacao concluir antes de fechar (sem networkidle, que
    # estoura). A gravacao real e CONFERIDA depois por _verificar_etapa.
    try:
        page.wait_for_load_state("load", timeout=8_000)
    except Exception:
        pass
    time.sleep(3)
    return True


def _confirmar_modal_mover(page, timeout: int = 8) -> bool:
    """Clica 'Mover operação' no modal de troca de etapa, se aparecer. Procura
    em todos os frames por ate 'timeout' segundos (o modal pode demorar)."""
    fim = time.time() + timeout
    while time.time() < fim:
        for fr in page.frames:
            for sel in ("#modalAlterarEtapaOperacao button:has-text('Mover')",
                        "button:has-text('Mover operação')",
                        "button:has-text('Mover operacao')",
                        "input[value*='Mover']", "a:has-text('Mover')"):
                try:
                    b = fr.locator(sel)
                    if b.count() > 0 and b.first.is_visible():
                        b.first.click(timeout=4_000)
                        print("  modal de etapa confirmado: 'Mover operação'")
                        return True
                except Exception:
                    continue
        time.sleep(0.5)
    return False


def mudar_status_credito(frame, opcao: str) -> None:
    """Linha 80: muda a etapa da operacao para 'Feedback Analise ROB'.

    Tenta primeiro o <select id=fEtapaOperacao> pelo value (18); se nao houver,
    procura a opcao pelo rotulo em qualquer <select> da tela.
    """
    # Caminho preferido: o select de etapa, por value.
    etapa = frame.locator(config.SEL_FILTRO_ETAPA)
    if etapa.count() > 0:
        etapa.select_option(value=config.VALOR_ETAPA_FEEDBACK_ROB)
        print(f"  status alterado: fEtapaOperacao={etapa.input_value()} (Feedback Analise ROB)")
        return

    # Fallback: procurar a opcao pelo texto em qualquer <select>.
    selects = frame.locator("select")
    for i in range(selects.count()):
        try:
            selects.nth(i).select_option(label=opcao)
            print(f"  status alterado (por rotulo) no select #{i}: {opcao}")
            return
        except Exception:
            continue
    raise RuntimeError(f"Opcao '{opcao}' nao encontrada em nenhum <select>.")


# --------------------------------------------------------------------------- #
# LOOP de operacoes  (linhas 49-114)
# --------------------------------------------------------------------------- #
# Hook OPCIONAL chamado ao FIM de cada ciclo (depois de Análise Home/DIGITAIS/NF).
# Usado pelo Robo 1 V3 p/ rodar a varredura de conferencia (toda op com doc).
# V1/V2 deixam None -> sem alteracao de comportamento.
pos_ciclo_hook = None

# Hook PRE-SALVAR (V3): ajusta a classe de risco dos titulos ANTES de clicar SALVAR
# em processar_operacao. Recebe (page_edit, numero_op). None = comportamento V1/V2.
pre_salvar_hook = None


def _contexto_vivo(ctx) -> bool:
    """True se o navegador/contexto ainda esta vivo. Quando a JANELA do Chrome e
    fechada (sem querer), o contexto morre e o robo ficaria em loop de erro
    ('Target ... has been closed') = ZUMBI. Detectamos isso checando se ha ao menos
    uma pagina aberta; se nao, o chamador encerra o ciclo p/ o .bat reabrir o Chrome."""
    try:
        pages = ctx.pages
    except Exception as e:
        return "closed" not in str(e).lower()
    if not pages:
        return False
    for pg in pages:
        try:
            if not pg.is_closed():
                return True
        except Exception:
            continue
    return False


def loop_operacoes(ctx) -> None:
    for loop2 in range(1, config.MAX_OPERACOES + 1):       # LOOP 1..1000
        # Opcao B: fora da janela de operacao (ex.: passou das 18:50) -> encerra
        # limpo no inicio do ciclo (nao interrompe op em andamento).
        if not _dentro_janela():
            print(f"\n[janela] fim do expediente ({config.JANELA_FIM}) -> encerrando o robo")
            raise SistemaForaDaJanela()
        print(f"\n--- operacao (ciclo {loop2}/{config.MAX_OPERACOES}) ---")
        _bater(f"ciclo {loop2}")

        # AUTO-RECUPERACAO: se a janela do Chrome foi fechada, o contexto morre e
        # ficariamos em loop de erro (zumbi). Detectamos e ENCERRAMOS levantando
        # excecao -> sobe pro main -> o .bat reabre o Chrome em ~30s (sessao persiste).
        if not _contexto_vivo(ctx):
            raise RuntimeError("navegador/contexto fechado (browser has been closed) "
                               "-> encerrando p/ reinicio limpo")

        # ROBUSTEZ: revalida a sessao a cada ciclo. login() so faz login se a
        # sessao tiver expirado (senao retorna na hora). Cobre expiracao no meio.
        try:
            login(ctx)
        except Exception as e:
            print(f"  [sessao] aviso ao revalidar login: {e}")

        if config.SKIP_ANALISE_HOME:
            print("  [Análise Home] PULADO (SKIP_ANALISE_HOME=True)")
        else:
            for _loop3 in range(1, config.REPETICOES_INTERNAS + 1):  # LOOP 1..2
                try:
                    _bater("processar op (Analise Home)")
                    processar_operacao(ctx)
                except Exception as e:
                    # uma op com problema nao derruba o ciclo todo
                    print(f"  [processar_operacao] erro ignorado: {e}")

        # Linha 103: sub-fluxo DIGITAIS - VM (pulavel enquanto em ajuste)
        if config.SKIP_DIGITAIS:
            print("  [DIGITAIS - VM] PULADO (SKIP_DIGITAIS=True)")
        else:
            try:
                _bater("digitais")
                subfluxos.digitais_vm(ctx)
            except Exception as e:
                print(f"  [DIGITAIS - VM] erro ignorado: {e}")

        # Linha 109: sub-fluxo BAIXAR NF E RESUMO PARA ANALISE
        try:
            _bater("baixar nf/resumo")
            subfluxos.baixar_nf_e_resumo(ctx)
        except Exception as e:
            print(f"  [BAIXAR NF] erro ignorado: {e}")

        # Hook de FIM de ciclo (V3: varredura de conferencia em toda op com doc).
        if pos_ciclo_hook:
            try:
                _bater("conferencia IA")
                pos_ciclo_hook(ctx)
            except Exception as e:
                print(f"  [pos_ciclo_hook] erro ignorado: {e}")

        esperar(config.WAIT_ENTRE_OPERACOES, "entre ciclos")  # linha 113


# --------------------------------------------------------------------------- #
# BLOCK reiniciar  (linhas 18-115) - login + processamento
# --------------------------------------------------------------------------- #
def bloco_reiniciar(ctx) -> None:
    login(ctx)            # linhas 22-48
    loop_operacoes(ctx)   # linhas 49-114


# --------------------------------------------------------------------------- #
# main  (LOOP 1..100, linhas 1-116)
# --------------------------------------------------------------------------- #
def main() -> None:
    """Loop INFINITO de reinicios (robo de 11h/dia). A cada reinicio LANCA um
    Chrome NOVO (reset do zero) protegido por WATCHDOG: se algum passo travar >
    WATCHDOG_MAX_OCIOSO s, o watchdog mata o Chrome -> a chamada bloqueada levanta
    erro -> caimos aqui e RELANCAMOS limpo. Backoff cresce com falhas seguidas.
    MAX_REINICIOS=0 => infinito (a janela 7:45-18:50 e controlada pelo wrapper)."""
    global _watchdog_atual
    if not config.EMAIL or not config.SENHA:
        print("ERRO: defina SMART_EMAIL e SMART_SENHA no arquivo .env "
              "(copie de .env.example).")
        sys.exit(1)

    with sync_playwright() as p:
        reinicio = 0
        falhas_seguidas = 0
        while True:
            reinicio += 1
            if config.MAX_REINICIOS and reinicio > config.MAX_REINICIOS:
                print(f"[main] MAX_REINICIOS={config.MAX_REINICIOS} atingido -> encerrando")
                break
            # Opcao B: fora da janela de operacao -> nem inicia o reinicio.
            if not _dentro_janela():
                print(f"[janela] fora do expediente "
                      f"({config.JANELA_INICIO}-{config.JANELA_FIM} BRT) -> encerrando")
                break
            rotulo = (f"/{config.MAX_REINICIOS}" if config.MAX_REINICIOS else " (infinito)")
            print(f"\n========== REINICIO {reinicio}{rotulo} ==========")

            # RESET DO ZERO: mata Chrome residual deste perfil + remove o lock, para
            # o launch subir limpo (cobre travamento anterior, lock orfao, zumbis).
            _watchdog.limpar_residual(config.USER_DATA_DIR)
            _watchdog.reapar_zumbis()
            _invalidar_busca()   # aba de busca cacheada pertence ao contexto antigo

            ctx = None
            wd = _watchdog.Watchdog(config.USER_DATA_DIR,
                                    max_ocioso=config.WATCHDOG_MAX_OCIOSO,
                                    checar_a_cada=config.WATCHDOG_CHECAR)
            _watchdog_atual = wd
            try:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=config.USER_DATA_DIR,
                    headless=config.HEADLESS,
                    channel="chrome",            # Google Chrome instalado (como o PAD)
                    # --no-sandbox/--disable-dev-shm-usage: rodar como root no container.
                    args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage"],
                    no_viewport=True,
                )
                try:
                    ctx.new_page()   # keepalive (nunca fica sem abas)
                except Exception:
                    pass
                wd.start()
                bloco_reiniciar(ctx)            # login + loop_operacoes (com heartbeats)
                falhas_seguidas = 0            # retorno normal = nao foi falha
            except SistemaForaDaJanela:
                # Opcao B: fim do expediente sinalizado de dentro do ciclo. O `finally`
                # abaixo faz a limpeza; o break encerra o robo (sem backoff/reinicio).
                print(f"[janela] fim do expediente ({config.JANELA_FIM} BRT) -> robo encerrado")
                break
            except Exception as e:
                falhas_seguidas += 1
                if wd.disparou():
                    print(f"[main] reinicio por TRAVAMENTO (watchdog matou o Chrome) "
                          f"-> relancando do zero")
                else:
                    print(f"[main] erro no bloco principal: {str(e)[:200]}")
            finally:
                wd.parar()
                _watchdog_atual = None
                if ctx is not None:
                    try:
                        ctx.close()
                    except Exception:
                        pass
                _watchdog.limpar_residual(config.USER_DATA_DIR)  # garante Chrome morto
                _invalidar_busca()

            # backoff antes do proximo reinicio (cresce com falhas seguidas, ate o teto)
            espera = min(config.REINICIO_BACKOFF * max(1, falhas_seguidas),
                         config.REINICIO_BACKOFF_MAX)
            esperar(espera, f"backoff p/ reiniciar (falhas seguidas={falhas_seguidas})")


if __name__ == "__main__":
    main()
