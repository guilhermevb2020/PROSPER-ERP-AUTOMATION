# -*- coding: utf-8 -*-
"""
_ambiente.py - sobe o Chrome no host, entrega um contexto LOGADO no Smart.

Reusa o login de producao (`boletos._sessao.login_automatico_capsolver`), que
resolve o iframe `loginsec.php`, aciona os `data-callback` do reCAPTCHA via
CapSolver e seleciona a empresa. Nao reimplementa nada disso — a regra 3 do
CLAUDE.md proibe, e seria uma terceira copia.

O PONTO DELICADO: o `boletos._config` resolve credencial, URL e paths NO
IMPORT, e o `load_dotenv` dele NAO sobrescreve env ja definida. Logo, o
`carregar_env()` deste modulo publica as envs ANTES de qualquer import de
`boletos.*` — e por isso esses imports sao PREGUICOSOS (dentro das funcoes).
"""
from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ENV_SANDBOX = os.environ.get("SANDBOX_ENV_FILE", str(RAIZ / "config" / "sandbox.env"))


class SandboxSemCredencial(RuntimeError):
    """Faltou credencial/chave no config/sandbox.env."""


class SandboxSemSessao(RuntimeError):
    """Subiu o Chrome mas nao ficou logado no Smart."""


def _guardian(cfg: dict[str, str]) -> dict[str, str]:
    """Configura transporte e CA sem entregar a senha do cofre ao Python."""
    if RAIZ == Path("/app"):
        proxy = os.environ.get("HTTPS_PROXY", "http://guardian:3128")
        bundle = Path("/run/guardian/guardian-bundle.crt")
        browser_home = ""
    else:
        proxy = cfg.get("SANDBOX_GUARDIAN_PROXY", "")
        if not proxy:
            try:
                import ipaddress
                result = subprocess.run(
                    ["docker", "inspect", "access-guardian-worker", "--format",
                     '{{(index .NetworkSettings.Networks "kg_erp-automation").IPAddress}}'],
                    capture_output=True, text=True, check=True, timeout=10)
                address = str(ipaddress.ip_address(result.stdout.strip()))
                proxy = f"http://{address}:3128"
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                raise SandboxSemCredencial("Guardian indisponivel para o sandbox") from exc
        bundle = RAIZ.parents[1] / "infrastructure/access-guardian/runtime/erp-automation/guardian-bundle.crt"
        browser_home = str(RAIZ / f"data/sandbox/guardian_home_{os.getuid()}")
        if not (Path(browser_home) / ".pki/nssdb/cert9.db").is_file():
            raise SandboxSemCredencial("CA do Guardian ausente no perfil privado do sandbox")
    if not bundle.is_file():
        raise SandboxSemCredencial("Bundle de CA do Guardian indisponivel")
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ[name] = proxy
    os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    os.environ["REQUESTS_CA_BUNDLE"] = str(bundle)
    os.environ["SSL_CERT_FILE"] = str(bundle)
    os.environ["SANDBOX_GUARDIAN_PROXY"] = proxy
    if browser_home:
        os.environ["SANDBOX_GUARDIAN_BROWSER_HOME"] = browser_home
    return {"proxy": proxy, "bundle": str(bundle)}


def _ler_env_file(caminho: str) -> dict[str, str]:
    """Le KEY=VALUE simples. Sem dependencia externa (nem python-dotenv)."""
    dados: dict[str, str] = {}
    p = Path(caminho)
    if not p.exists():
        return dados
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        dados[chave.strip()] = valor.strip().strip('"').strip("'")
    return dados


def carregar_env(log=print) -> dict[str, str]:
    """Publica no ambiente o que o login de producao vai ler NO IMPORT.

    Mapeia as chaves SANDBOX_* para as que `boletos._config` espera. Faz isto
    ANTES de qualquer import de `boletos.*`.
    """
    cfg = _ler_env_file(ENV_SANDBOX)
    if not cfg:
        raise SandboxSemCredencial(
            f"{ENV_SANDBOX} nao existe ou esta vazio. Crie a partir de "
            "config/sandbox.example.env (modo 600, fora do git)."
        )

    email = cfg.get("SANDBOX_EMAIL", "")
    senha = cfg.get("SANDBOX_SENHA", "")
    capsolver = cfg.get("SANDBOX_CAPSOLVER_API_KEY", "")
    faltando = [n for n, v in (("SANDBOX_EMAIL", email), ("SANDBOX_SENHA", senha),
                               ("SANDBOX_CAPSOLVER_API_KEY", capsolver)) if not v]
    if faltando:
        raise SandboxSemCredencial(f"faltam em {ENV_SANDBOX}: {', '.join(faltando)}")

    # Apelidos da identidade propria, publicados apenas depois da importacao.
    if senha == "GSMARTPWD3":
        if capsolver != "__GUARDIAN_SANDBOX_CAPSOLVER_API_KEY__":
            raise SandboxSemCredencial("Sandbox deve usar sua chave CapSolver pelo Guardian")
        _guardian(cfg)

    # data/ do HOST — sem isto o boletos._config tenta /app/data, que nao existe.
    data_dir_host = cfg.get("SANDBOX_DATA_DIR", str(RAIZ / "data" / "boletos"))
    perfil = cfg.get("SANDBOX_PERFIL", str(RAIZ / "data" / "sandbox" / "perfil_chrome"))
    evidencia = cfg.get("SANDBOX_EVIDENCIA_DIR", str(RAIZ / "data" / "sandbox" / "emitidos"))

    # URL_SESSAO tem de apontar para uma tela que, DESLOGADO, devolva o redirect
    # `expira.php` — nao um corpo vazio. E o PAINEL. A tela de emissao responde
    # HTTP 200 com 0 bytes quando deslogado, e o `esta_logado` de producao le
    # isso como "logado" -> `login_automatico_capsolver` faz um curto-circuito
    # (`if esta_logado(): return True`) e NUNCA loga (medido 21/08/2026). Com o
    # painel, o esta_logado ve o `expira.php`, retorna False, e o login procede.
    # A permissao de EMISSAO e checada depois, por `alcanca_emissao()`.
    url_sessao = cfg.get(
        "SANDBOX_URL_SESSAO",
        "https://wvw.smartsecurities.com.br/smart/smartsecurities.php",
    )

    publicar = {
        "BOLETO_EMAIL": email,
        "BOLETO_SENHA": senha,
        "CAPSOLVER_API_KEY": capsolver,
        "BOLETO_DATA_DIR": data_dir_host,
        "URL_SESSAO": url_sessao,
        "EVIDENCIA_DIR_EMISSAO": evidencia,
        # o proprio env_file dos boletos aponta para o do sandbox, para o
        # load_dotenv nao puxar credencial do container por engano.
        "BOLETO_ENV_FILE": ENV_SANDBOX,
    }
    for k, v in publicar.items():
        if k in ("BOLETO_EMAIL", "BOLETO_SENHA", "CAPSOLVER_API_KEY"):
            # Dentro do container, nao herdar a identidade de producao.
            os.environ[k] = v
        else:
            os.environ.setdefault(k, v)

    # Display / VNC / gravacao (depuracao visual)
    # SANDBOX_HEADLESS=false so faz sentido se houver display (Xvfb do vnc.sh).
    # SANDBOX_DISPLAY publica o DISPLAY para o Chrome herdar. TRACE/VIDEO gravam
    # a execucao mesmo HEADLESS — a alternativa ao VNC enquanto o host nao tem X.
    headless = cfg.get("SANDBOX_HEADLESS", "true").strip().lower() not in ("0", "false", "nao", "no")
    display = cfg.get("SANDBOX_DISPLAY", "").strip()
    trace_dir = cfg.get("SANDBOX_TRACE_DIR", str(RAIZ / "data" / "sandbox" / "trace"))
    gravar = cfg.get("SANDBOX_GRAVAR", "false").strip().lower() not in ("0", "false", "nao", "no")
    if gravar and senha != "GSMARTPWD3":
        raise SandboxSemCredencial("Trace exige apelidos Guardian; senha real nao pode ser gravada")
    if display:
        os.environ["DISPLAY"] = display  # o Chrome herda o DISPLAY do processo

    Path(perfil).mkdir(parents=True, exist_ok=True)
    Path(evidencia).mkdir(parents=True, exist_ok=True)
    if gravar:
        Path(trace_dir).mkdir(parents=True, exist_ok=True)
    log(f"  sandbox: perfil={perfil}")
    log(f"  sandbox: evidencia={evidencia}")
    log(f"  sandbox: usuario Smart={email}")
    log(f"  sandbox: headless={headless}" + (f" display={display}" if display else "")
        + (f" grava trace/video em {trace_dir}" if gravar else ""))
    return {"perfil": perfil, "evidencia": evidencia, "email": email,
            "headless": headless, "display": display, "trace_dir": trace_dir,
            "gravar": gravar}


def abrir_chrome(p, perfil: str, headless: bool = True, log=print,
                 gravar_video_em: str | None = None):
    """Chrome no host. Headless por padrao — nao precisa de Xvfb.

    Os dois argumentos que nunca somem (o container ensina): --no-sandbox
    (roda como usuario sem privilegio) e --disable-dev-shm-usage (/dev/shm
    pequeno mata o Chrome). O canal 'chrome' do container nao existe aqui, entao
    usa o Chromium que o Playwright baixou.

    `gravar_video_em`: pasta para gravar VIDEO da sessao (mesmo headless). E a
    depuracao visual que funciona sem X no host — assiste-se depois em vez de
    ao vivo por VNC.
    """
    # ⚠️ --window-size e OBRIGATORIO em headless. `--start-maximized` depende de
    # window manager e NAO tem efeito sem X: o Chrome cai no default 800x600.
    # Com `no_viewport=True` o viewport E a janela, entao a pagina inteira
    # renderiza em 800px de largura — abaixo do breakpoint `md` (768px) de
    # Tailwind DENTRO dos frames do Smart. Telas responsivas escondem controles
    # (`class="hidden md:flex"`): o elemento existe no DOM, mas nunca fica
    # clicavel, e o clique morre por timeout sem dizer o porque.
    # Medido em 01/09/2026: `#btnPagamento` da grade de pagamento, invisivel a
    # 800x600 e clicavel a 1920x1080 — que e o tamanho do Xvfb do container.
    janela = os.environ.get("SANDBOX_JANELA", "1920,1080").strip()
    kwargs = dict(
        user_data_dir=perfil,
        headless=headless,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              f"--window-size={janela}", "--start-maximized"],
        no_viewport=True,
    )
    proxy = os.environ.get("SANDBOX_GUARDIAN_PROXY", "")
    if proxy:
        kwargs["proxy"] = {"server": proxy, "bypass": "localhost,127.0.0.1"}
        browser_home = os.environ.get("SANDBOX_GUARDIAN_BROWSER_HOME")
        if browser_home:
            kwargs["env"] = {**os.environ, "HOME": browser_home}
    if gravar_video_em:
        kwargs["record_video_dir"] = gravar_video_em
        kwargs["record_video_size"] = {"width": 1280, "height": 800}
    return p.chromium.launch_persistent_context(**kwargs)


def alcanca_emissao(ctx) -> bool:
    """Checagem POSITIVA: a tela de emissao respondeu com o form dela?

    NAO reusar o `boletos._sessao.esta_logado` para decidir isto: ele faz
    checagem NEGATIVA (procura marcas de 'deslogado') e um corpo VAZIO passa
    por logado — medido em 21/08/2026, o Smart responde HTTP 200 com 0 bytes
    na emissao sem sessao. E o mesmo modo de falha que o robo de retorno ja
    documentou (resposta vazia = deslogado). Aqui exigimos a MARCA da tela:
    o dropdown `contaCorrente` do form de emissao. Sem ela, nao esta logado.
    """
    try:
        r = ctx.request.get(
            "https://wvw.smartsecurities.com.br/smart/financeiro/impriboleto.php?Via=1",
            timeout=20_000,
        )
        if r.status >= 400:
            return False
        html = (r.body() or b"").decode("iso-8859-1", errors="replace").lower()
    except Exception:                                              # noqa: BLE001
        return False
    if not html.strip():
        return False   # corpo vazio = deslogado (a armadilha nº 1 do Smart)
    return "contacorrente" in html and 'name="femail"' not in html


_ENV_CARREGADO: dict[str, str] | None = None


def garantir_env(log=print) -> dict[str, str]:
    """Carrega o env do sandbox UMA vez. Idempotente.

    Tem de rodar ANTES de qualquer import de `boletos.*`, porque o `_config`
    resolve credencial/URL/paths NO IMPORT — importar antes disto pega tudo
    vazio. Quem chama o sandbox deve invocar isto no comeco, antes dos imports
    de producao.
    """
    global _ENV_CARREGADO
    if _ENV_CARREGADO is None:
        _ENV_CARREGADO = carregar_env(log=log)
    return _ENV_CARREGADO


@contextlib.contextmanager
def sessao(p, *, headless: bool | None = None, logar: bool = True, log=print):
    """Contexto logado no Smart, no host. Fecha o Chrome no fim.

    `headless=None` (padrao) respeita SANDBOX_HEADLESS do env; passe True/False
    para forcar. Grava video/trace se SANDBOX_GRAVAR estiver ligado — a
    depuracao visual que funciona sem X no host.

    Levanta SandboxSemSessao se o login falhar — o teste tem de MORRER com erro,
    nao seguir lendo tela deslogada como 'nada a fazer'.
    """
    info = garantir_env(log=log)
    usar_headless = info["headless"] if headless is None else headless
    video_dir = info["trace_dir"] if info["gravar"] else None
    ctx = abrir_chrome(p, info["perfil"], headless=usar_headless, log=log,
                       gravar_video_em=video_dir)
    tracing = info["gravar"]
    if tracing:
        with contextlib.suppress(Exception):
            ctx.tracing.start(screenshots=True, snapshots=True, sources=True)
    try:
        if logar:
            # import preguicoso: o _config resolveu tudo com as envs acima
            from src.processors.web.boletos._sessao import login_automatico_capsolver

            if alcanca_emissao(ctx):
                log("  sessao ja valida (perfil reusado) -> sem novo login")
            else:
                log("  sessao nao valida -> login automatico via CapSolver")
                if not login_automatico_capsolver(ctx):
                    raise SandboxSemSessao(
                        "login automatico falhou. Cheque SANDBOX_* em "
                        f"{ENV_SANDBOX} e a janela de horario do usuario no Smart."
                    )
                if not alcanca_emissao(ctx):
                    raise SandboxSemSessao(
                        "auto-login disse OK mas a tela de emissao nao respondeu "
                        "com o form (usuario sem acesso a emissao? janela de horario?)."
                    )
                log("  login OK")
        yield ctx
    finally:
        if tracing:
            import time as _t
            destino = os.path.join(info["trace_dir"], f"trace_{int(_t.time())}.zip")
            with contextlib.suppress(Exception):
                ctx.tracing.stop(path=destino)
                log(f"  trace salvo: {destino}")
                log("  veja com: .venv-sandbox/bin/playwright show-trace " + destino)
        with contextlib.suppress(Exception):
            ctx.close()   # fecha o contexto -> finaliza o video, se gravando
        log("  Chrome do sandbox fechado.")
