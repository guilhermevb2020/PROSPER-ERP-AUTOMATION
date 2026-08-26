# Criar uma automação nova no sandbox

Receita para escrever uma automação **sem reimplementar login, CapSolver, perfil
de Chrome nem detecção de sessão morta**. Tudo isso já está pronto em
[`_ambiente.py`](_ambiente.py). Você escreve **só o trabalho**.

> Regra 3 do `CLAUDE.md`: nunca recrie o que já existe em módulo comum. Login do
> Smart é o exemplo nº 1 — já são três implementações (boletos, doc2you,
> smart_sessao). Uma quarta é proibida. **Importe.**

---

## O que você NÃO escreve (o `_ambiente` faz)

- subir o Chrome no host, com perfil próprio (`data/sandbox/perfil_chrome`)
- publicar as credenciais de `config/sandbox.env` antes dos imports
- **login automático via CapSolver** (delega ao fluxo de produção)
- reusar a sessão se o perfil ainda estiver logado (não gasta CapSolver à toa)
- detectar sessão morta pela marca certa (não o corpo vazio que engana)
- gravar vídeo + trace da execução para você depurar
- fechar o Chrome no fim, mesmo se der erro

## O que você escreve (só isto)

Uma função que recebe um `ctx` **já logado** e faz o trabalho por HTTP:

```python
def trabalho(ctx, log=print):
    # ctx.request.get / ctx.request.post já saem autenticados
    r = ctx.request.get("https://wvw.smartsecurities.com.br/smart/<sua_tela>.php")
    html = r.body().decode("iso-8859-1", errors="replace")
    ...
    return {"ok": True}
```

---

## O esqueleto — copie e comece daqui

Copie [`_modelo_automacao.py`](_modelo_automacao.py) e troque o miolo:

```bash
cp scripts/sandbox/_modelo_automacao.py scripts/sandbox/minha_automacao.py
```

O modelo já tem a estrutura inteira: argumentos, sessão logada, exit codes.
Você mexe só na função `trabalho()`.

## Rodar

```bash
PYTHONPATH=$PWD .venv-sandbox/bin/python scripts/sandbox/minha_automacao.py
```

Ver o navegador ao vivo (depois de `sh scripts/sandbox/vnc.sh` — ver README):

```bash
... scripts/sandbox/minha_automacao.py --ver-navegador
```

O trace da execução fica em `data/sandbox/trace/` — abra com
`.venv-sandbox/bin/playwright show-trace <zip>`.

---

## As 5 regras que evitam as armadilhas medidas

1. **Trabalhe por HTTP sobre a sessão, não por clique.** `ctx.request.get/post`
   já leva os cookies. Clicar em tela é lento e quebra a cada mudança de layout.

2. **Cheque `parece_deslogado` em TODO ponto que lê resposta do Smart.** Sessão
   morta responde **HTTP 200** com um corpo minúsculo que redireciona para
   `expira.php` — sem erro, sem a palavra "expirou". Quem não checa lê tela vazia
   como "nada a fazer" e termina com cara de sucesso sem ter olhado nada:

   ```python
   from src.common.clients.smart_sessao import parece_deslogado
   if parece_deslogado(html):
       raise RuntimeError("sessão caiu no meio")  # não trate como "sem trabalho"
   ```

3. **Corpo vazio = deslogado.** Algumas telas respondem 200 com **0 bytes**
   quando não há sessão. Trate vazio como sessão caída, nunca como "sem dados".

4. **Nada de emitir/enviar/dar baixa sem uma flag explícita.** O padrão é
   dry-run: monte o POST, mostre o que faria, **não dispare**. Ligar o efeito
   real é decisão de quem roda, com `--confirmar` (ou equivalente) — igual à
   emissão e ao retorno.

5. **Um exit code para "fez pela metade".** Distinga "não havia trabalho" (0) de
   "comecei e travei" (um código próprio). Quem chama precisa saber a diferença.

---

## Levar do sandbox para produção (quando validar)

O sandbox é para **testar no host**. Quando a automação estiver certa, ela vira
um robô de produção seguindo [`docs/COMO_SUBIR_UM_ROBO.md`](../../docs/COMO_SUBIR_UM_ROBO.md).
A diferença é só a sessão:

| | sandbox (host) | produção (container) |
|---|---|---|
| sessão | `scripts/sandbox/_ambiente.sessao` | `src/common/clients/smart_sessao.sessao` |
| credencial | `config/sandbox.env` | `config/<robo>.env` |
| Chrome | headless no host, ou VNC `:90` | Xvfb próprio no container |
| dispara | quem agenda o hub | a task no hub |

A **função `trabalho()` é a mesma nos dois** — foi para isso que ela recebe um
`ctx` logado em vez de saber como logar. Escreva-a uma vez, teste no sandbox,
suba para produção sem reescrever a lógica.
