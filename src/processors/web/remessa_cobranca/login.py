# -*- coding: utf-8 -*-
"""
login.py - deteccao de sessao e login do robo de remessa.

Duas responsabilidades, e a primeira e a mais importante:

1) `parece_deslogado()` - a resposta do Smart e "voce nao esta logado"?
   Quando a sessao expira o Smart responde **HTTP 200** com um corpo de 93 bytes:

       <script>top.location.href='.../smart/php/expira.php';</script>

   Sem 'recaptcha', sem status de erro, e sem a palavra 'expirou' (e "expira",
   sem o U). Quem nao checa isso ve toda tela como "pagina vazia" e conclui
   "essa conta nao tem titulo" -> a rodada inteira termina dizendo "nenhuma
   remessa" sem ter olhado nada. E o unico ponto do robo que precisa estar
   certo para todos os outros fazerem sentido.

2) `login()` - autentica sem gente.
   NAO reimplementa o fluxo de login: delega para
   `boletos._sessao.login_automatico_capsolver`, que ja esta em producao e
   resolve as tres armadilhas do login do Smart (iframe `loginsec.php`,
   acionamento dos `data-callback` do reCAPTCHA e selecao de empresa).

   Como aquele modulo le credencial/ping de `boletos._config` — que e
   env-driven — publicamos os NOSSOS valores no ambiente ANTES de importa-lo.
   E por isso que o import esta dentro da funcao: `boletos._config` resolve
   tudo no import, entao importar no topo do arquivo pegaria a credencial dos
   boletos. Fazer uma terceira copia do fluxo (ja existe a sync dos boletos e a
   async do doc2you) e o que a regra 3 do CLAUDE.md deste repo proibe.
"""
import os
import time

import remessa_config as cfg


def parece_deslogado(html) -> bool:
    """True se a resposta do Smart e, na verdade, 'voce nao esta logado'.

    Ver o item 1 do docstring do modulo: o caso perigoso e o `expira.php`
    devolvido com status 200. Resposta vazia tambem conta como deslogado —
    e melhor abortar a rodada do que trata-la como "conta sem titulo".
    """
    if not html:
        return True
    baixo = html.lower()
    return ("expira.php" in baixo
            or "recaptcha" in baixo
            or "loginsec" in baixo
            or "sessão expirou" in baixo or "sessao expirou" in baixo
            or "faça login" in baixo or "faca login" in baixo)


def esta_logado(ctx) -> bool:
    """Ping HTTP autenticado (nao abre aba nem navega).

    Aponta para a PROPRIA tela de remessa (`cfg.URL_PING`): assim "logado"
    significa "alcanca a tela que o robo precisa". Usuario sem permissao no
    CNAB falha aqui, no comeco, em vez de virar "nenhuma conta com remessa".
    """
    try:
        r = ctx.request.get(cfg.URL_PING, timeout=20_000)
        corpo = r.body().decode("iso-8859-1", errors="replace")
    except Exception:
        return False
    if r.status != 200:
        return False
    return not parece_deslogado(corpo)


def _publicar_credenciais_para_o_modulo_de_boletos() -> None:
    """Escreve as nossas credenciais nas envs que `boletos._config` le.

    `load_dotenv` do modulo de boletos NAO sobrescreve env ja definida, e
    `_config` resolve os valores no import — por isso isto tem de rodar ANTES
    do import de `boletos._sessao`, e por isso ele e feito preguicosamente.
    """
    cfg.exigir_credenciais()
    os.environ["BOLETO_EMAIL"] = cfg.EMAIL
    os.environ["BOLETO_SENHA"] = cfg.SENHA
    # ping do login = a nossa tela de remessa (senao ele valida a sessao contra
    # a tela de boleto, que o usuario da remessa pode nem ter)
    os.environ["URL_SESSAO"] = cfg.URL_PING
    os.environ.setdefault("URL_LOGIN", cfg.URL_LOGIN)


def login(ctx, timeout_total_s: int = 300, log=print) -> bool:
    """Garante sessao logada. Retorna True se (ficou) logado.

    NUNCA bloqueia esperando teclado: o robo roda desatendido. Se o CapSolver
    falhar, devolve False e quem chamou decide (o modo agendado aborta).
    """
    if esta_logado(ctx):
        log("  sessao ja valida -> sem novo login")
        return True

    try:
        # credencial ausente levanta RuntimeError aqui — e o motivo mais comum
        # de o robo nao logar, entao vira log e False (o chamador transforma em
        # exit code), nunca traceback cru na saida do hub.
        _publicar_credenciais_para_o_modulo_de_boletos()
        from src.processors.web.boletos._sessao import login_automatico_capsolver

        log(f"  sessao nao valida -> auto-login via CapSolver ({cfg.EMAIL})")
        ok = login_automatico_capsolver(ctx, timeout_total_s=timeout_total_s)
    except RuntimeError as e:
        log(f"  [login] ERRO: {e}")
        return False

    # O modulo de boletos valida com a heuristica dele; confirmamos com a nossa,
    # que e a que o resto do robo usa (e a que enxerga o expira.php).
    if ok and esta_logado(ctx):
        log("  login OK")
        return True
    if ok:
        log("  [login] o auto-login disse OK mas o ping da tela de remessa nao "
            "confirmou (usuario sem acesso ao CNAB? janela de horario?)")
    else:
        log("  [login] auto-login FALHOU")
    return False


def aguardar_login_manual(ctx, segundos: int, log=print) -> bool:
    """Polling por um login feito A MAO no VNC. So para operacao assistida.

    Existe porque a primeira sessao de um perfil novo as vezes precisa de gente
    (ex.: 'Procedimento de seguranca' inedito). Nunca e chamado pelo agendado.
    """
    fim = time.time() + segundos
    log(f"  aguardando login manual no VNC (ate {segundos}s)...")
    while time.time() < fim:
        time.sleep(5)
        if esta_logado(ctx):
            log("  login manual concluido")
            return True
    log("  tempo esgotado sem login")
    return False
