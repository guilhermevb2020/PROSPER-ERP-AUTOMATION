# Como as credenciais chegam ao erp-automation — em uma página

Desde 06/09/2026 este container **não carrega o `shared.env`** e **não tem senha de banco**.
Tudo o que ele usa de credencial vem do `access-guardian`
(`/home/prospere/docker/infrastructure/access-guardian`). Esta página diz de onde vem cada
coisa, como operar, e o que nunca fazer. Este projeto é o **molde** para migrar os outros.

## De onde vem cada credencial

| arquivo ou caminho | o que é | quem escreve |
|---|---|---|
| `.env` | configuração **local** do projeto: portas, caminhos, flags. Sem segredo | o projeto |
| `.env.guardian` | chaves declaradas na política, **geradas** da fonte cifrada. Nunca editar à mão | `guardian gerar erp-automation` |
| `/run/guardian/` (pasta montada) | o `.pgpass` da capability do banco e o `guardian-bundle.crt` (CA) | o worker, sozinho |
| `config/*.env` | configuração dos robôs, sem senhas reais; limpeza concluída em 07/09 | o projeto |

O compose carrega `.env` e depois `.env.guardian` — o último vence.

## O banco: sem senha no container

```
DB_HOST=guardian   POSTGRES_HOST=guardian   DB_PASSWORD=(vazia)   POSTGRES_PASSWORD=(vazia)
```

O código conecta em `guardian`, que é o worker na rede privada `kg_erp-automation`. O worker
autentica no Postgres com um **login efêmero** (`gdh_erp_automation_…`, 1 h, graça 10 min)
que é membro de `app_erp_automation` — a role do projeto, **sem login**, dona do schema
`erp_automation`. A senha real do banco nunca entra aqui. A capability tem prazo
de 4h e graça de 5min. A queda do worker interrompe novas conexões pelo proxy;
a recuperação precisa ser conferida, sem assumir duração fixa.

## As integrações: o container tem apelidos, não senhas

| chave no container | valor que o código vê | quem troca pelo real |
|---|---|---|
| `CAPSOLVER_API_KEY`, `EVOLUTION_API_KEY`, `NEXTCLOUD_PASSWORD` | apelido `__GUARDIAN_…__` | o proxy HTTP (`HTTP_PROXY=guardian:3128`) na saída |
| `SENHA_SITE_SMART`, `BOLETO_SENHA`, `SMART_SENHA`, `REMESSA_SENHA`, `RETORNO_SENHA` | `GSMARTPWD1` (apelido de 9 caracteres; o campo tem `maxlength=11`) | o túnel HTTPS troca a representação base64 no formulário enviado |
| `PAGAMENTO_SENHA` (identidade financeira do Smart) | `GSMARTPWD2` | idem |
| `SANDBOX_SENHA` / consumidores sandbox e finalizador | `GSMARTPWD3` | idem, com identidade própria |
| `SANDBOX_CAPSOLVER_API_KEY` | `__GUARDIAN_SANDBOX_CAPSOLVER_API_KEY__` | o proxy, com a chave própria da sandbox |
| `SMTP_PASSWORD` | **vazia**; `SMTP_SERVER=guardian`, porta 2525 | o broker SMTP do worker refaz a conversa com o MailerSend |
| `VNC_PASSWORD`, `VNC_SENHA` | **real**, somente para execução do VNC dos robôs | entrega administrativa pelo Guardian |

O Chrome dos robôs confia na CA do guardian pela base NSS (`boot_vnc.sh`); `NO_PROXY` e a
lista `direto` da política poupam o que não precisa passar pelo proxy.
Apelidos não significam rotação automática da senha do fornecedor: esses valores
podem ser estáticos na fonte cifrada. Cookies e tokens são material privado de sessão.

## Como operar

| quero | comando |
|---|---|
| listar nomes no ambiente efetivo, sem valores | `docker exec erp-automation python -c 'import os; print("\n".join(sorted(os.environ)))'` |
| conferir antes de mexer | `bin/guardian conferir erp-automation` · `bin/guardian redes` · `bin/guardian sobras` |
| uma chave nova ou mudada | 1. `bin/guardian gravar CHAVE --projeto erp-automation` (ou `importar`) · 2. acrescentar em `gerar:` no `config/projetos.yaml` · 3. `bin/guardian gerar erp-automation` · 4. `docker compose up -d` **na janela** |
| conferir a entrega pelo worker | `bin/guardian sonda`; complementar com conexão pelo módulo real do ERP e consulta de identidade, sem imprimir senha/passfile |
| recriar o container | só na janela **19:05–07:30** em dia útil; `docker compose up -d`, sem `--build` a menos que a imagem deva mudar |

Os comandos `bin/guardian` rodam em `/home/prospere/docker/infrastructure/access-guardian`,
como `prospere`; Compose roda no checkout principal do ERP. Os que mexem na fonte
pedem a senha da Gerência. O worker rotaciona automaticamente login e capability;
trocar a senha da role NOLOGIN não substitui esse mecanismo.

## O que nunca fazer

- Voltar o `shared.env` ao compose, ou copiar uma linha dele para o `.env`.
- Escrever senha real em `config/*.env`, código, log, documentação ou commit. Se um robô
  precisa de uma senha nova, ela entra na **fonte** e chega por apelido ou por `.env.guardian`.
- Editar o `.env.guardian` à mão — o próximo `gerar` apaga a edição.
- Usar `dev_user`, `POSTGRES_PASSWORD` do `shared.env` ou a senha de outro projeto.
- Testar login no Smart fora do combinado: a sessão é única e derruba a produção.

## Molde para migrar o próximo projeto (é o que foi feito aqui)

1. **Medir os consumidores efetivos**, incluindo wrappers e `config/*.env`, sem imprimir
   valores. O `conferir` sozinho não cobre todos os arquivos e caminhos de execução.
2. **Chaves próprias entram na fonte** com `importar … --projeto <nome>`; as compartilhadas
   já estão lá. Escrever a lista `gerar:` na política.
3. **Definir a entrega pelo Guardian**: login efêmero de banco, apelidos por proxy/túnel
   para integrações e relay SMTP. Conferir compatibilidade do worker, confiança TLS,
   destinos e redes; antes do `implantar`, `guardian rotador --simular` lista a role.
4. **`guardian gerar <projeto>`**; no Compose, `.env.guardian` no lugar do `shared.env`.
   Publicar na janela operacional ou sob autorização explícita, respeitando tarefas em voo.
5. **Provar com tarefas reais**, identidade do banco, transporte e resultado de negócio.
   Saída sem entrada e healthcheck ocupado não comprovam escrita nem novo login.
   Varrer valores conhecidos em arquivos e histórico sem imprimir segredos.
6. Restringir privilégios adicionais somente depois de medir com `guardian uso`;
   não usar a migração de credenciais para apertar acesso sem evidência.

Detalhes, incidentes e o porquê de cada escolha: `DECISOES.md` do access-guardian, entradas
de 04/09 a 07/09/2026.
