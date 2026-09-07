# PROSPER-ERP-AUTOMATION - Diretrizes para Claude Code

## Em um minuto: as credenciais deste projeto (07/09/2026)

Este container **não carrega o `shared.env` e não tem senha de banco**. Tudo vem do
`access-guardian`: o `.env.guardian` é gerado, nunca editado à mão; o banco
é `DB_HOST=guardian` com senha vazia e login efêmero pelo worker; as integrações são
**apelidos** que o proxy troca na saída (`GSMARTPWD1`/`GSMARTPWD2`/`GSMARTPWD3` para o Smart,
`__GUARDIAN_…__` para CapSolver, Evolution e Nextcloud; SMTP pelo broker, senha vazia).
Só VNC tem entrega de senha real para execução. A página inteira, com os comandos de operar e o molde para
migrar os outros projetos: [`docs/CREDENCIAIS_GUARDIAN.md`](docs/CREDENCIAIS_GUARDIAN.md).

Cinco regras que valem sempre: conferir o ambiente efetivo por nomes e classificação,
sem exibir valores; chave nova entra na fonte e no `gerar:` da política, depois `guardian gerar
erp-automation`; recriar só na janela 19:05–07:30; nada de senha real em `config/*.env`,
código, log ou commit; nunca `dev_user` nem `POSTGRES_PASSWORD` do `shared.env`.

## Credenciais: fonte única no Access Guardian

Credenciais core pertencem à fonte cifrada do Access Guardian. O ERP consome
apelidos, identidade efêmera do banco e relay SMTP; não cadastrar senha real
em configuração, código, documentação ou backup local. Material de sessão e
VNC entregue para execução não constitui uma segunda fonte de administração.

A [auditoria de credenciais](docs/AUDITORIA_CREDENCIAIS_2026-09-07.md) registra
limpeza de configuracoes, logs, traces e historico Git local/GitHub. Sandbox e
finalizador usam a identidade propria GSMARTPWD3; CapSolver proprio por apelido.
A imagem guardian-clean-20260907-v2 esta implantada, a imagem antiga foi removida.
VNC continua entregue pelo Guardian como material de execucao. Nunca misturar
identidades nem reintroduzir senhas reais nos arquivos dos robos.
Reconferência de 16:32:55: 3.735 arquivos; só VNC esperado, sem erros de leitura.
Login do banco: 1h/graca 10min; capability: 4h/graca 5min. Apelido não significa
que a senha do fornecedor seja rotativa; a fonte administrativa fica no Guardian.

## Estado verificado em 07/09/2026

Nova rodada manual autorizada em andamento desde 17:03, dentro da validação de
16:34:17 até 08/09 00:34:17. Abrange as 11 tarefas finitas habilitadas; crédito
foi acompanhado na execução 2665935, sem duplicação, até a saída normal às
18:50:28: success/exit 0, ciclo 306, fim do expediente configurado. Não reiniciar
o robô fora dessa janela para continuar a observação. O histórico abaixo registra
a rodada anterior e não encerra o acompanhamento atual. Resultados e limites:
`docs/VALIDACAO_OITO_HORAS_2026-09-07.md`.

Às 18:13, retorno de pagamento 2669741 falhou por
`ERROR_CAPTCHA_SOLVE_FAILED`; retentativa 2669760 recuperou às 18:15:45.
O solver compartilhado ganhou uma segunda tentativa de desafio, limitada ao
mesmo prazo total, sem repetir erros de chave/saldo. 36 testes isolados sem
rede aprovados; publicação alcança novos processos pelo bind de `/app/src`,
sem reiniciar ERP/crédito. Commit `d244857` aplicado às 18:18:37; retorno
2669905 usou o solver novo, confirmou login e concluiu às 18:24:25, sem arquivo
de entrada. Não precisou da segunda resolução; esse ramo tem prova automatizada.
Não confundir os 11 sucessos manuais com ausência
de falhas posteriores; acompanhar cada tentativa até 00:34:17.

Consulte [a matriz de validação](docs/VALIDACAO_ERP_2026-09-07.md) antes de
repetir testes operacionais: 382 testes no host; 20 tarefas inventariadas, das
quais 12 habilitadas foram alcançadas na rodada real de feriado (11 concluídas
e crédito em execução). Sessão principal saudável às 15:30, após recuperação
automática e emissão da tarde. Veja `docs/VALIDACAO_FERIADO_2026-09-07.md`.
O Smart tem sessão única por identidade; novos logins podem
interromper outro robô. Testes de regressão usam serviços simulados.
Geração e retorno de pagamento usam uma trava financeira comum antes do Chrome
(`src/common/smart_financeiro_lock.sh`). Não remover a trava nem apagar seu
arquivo enquanto houver uso. A falha do aviso de segurança às 16:03 recuperou
na retentativa; retorno e geração concluíram novamente às 16:14 e 16:16.

A rodada real das 12:25–13:15 confirmou 683 documentos enviados,
registro no banco e remessa CNAB400 de 14 títulos entregue ao Nextcloud.
Emissão/envio executaram em modo real sem novos títulos; pagamentos logaram
sem entrada pendente. Retorno e depósito também executaram, sem arquivos novos.
Consulte a matriz para os IDs e limites: isso não comprova baixas sem entrada.
A manutenção manual do Hub pausou o despacho e foi liberada externamente;
a sequência terminou após a retomada. O mantenedor normal do Chrome foi
restaurado com login automático e keepalive válido. Crédito segue o ciclo diário.

O ERP usa o Guardian para banco e integrações. A conta financeira usa
`PAGAMENTO_SENHA=GSMARTPWD2` no ambiente; não restaurar a senha real em
`config/robo_pagamento.env`. O valor da fonte foi corrigido para respeitar os
11 caracteres efetivamente enviados pelo campo antes da migração. Logins de
pagamento confirmados após a correção. Credenciais nunca devem ser exibidas.

`pytest` coleta somente a suíte automatizada definida em `pytest.ini`.
Scripts manuais de email e browser em `tests/` têm efeitos externos ao importar.
Dependências de teste: `requirements-test.txt`. PDFs de emissão são guardados
em `/app/data/boletos/emitidos`, com manifesto; não versionar esses documentos.


## 🔴 REGRAS PRINCIPAIS (SEMPRE RESPEITAR)

### 1. SEMPRE USAR AGENTES ESPECIALIZADOS PARA TAREFAS

**IMPORTANTE**: Cada tarefa deve ser executada pelo processador especializado correspondente.

#### Processadores Disponíveis em `src/processors/web/`:
- `relatorio_operacao_desagio.py` → Extração de relatórios de operação de deságio
- `relatorio_titulos_aberto.py` → Extração de relatórios de títulos em aberto
- `emissao_boleto_primeira_via.py` → Emissão de boletos (primeira via)
- `envio_boleto_operacao_oculto.py` → Envio de boletos (modo oculto)
- `envio_boleto_operacao_padrao.py` → Envio de boletos (modo padrão)

#### Regras:
- ❌ **NUNCA** modificar um processador para fazer tarefa de outro
- ❌ **NUNCA** criar código duplicado quando já existe um módulo comum em `src/common/`
- ✅ **SEMPRE** verificar se existe processador especializado antes de criar novo código
- ✅ **SEMPRE** criar novo processador seguindo o padrão em `docs/COMO_CRIAR_PROCESSADORES.md`

---

### 2. SEMPRE RESPEITAR AS PASTAS

**IMPORTANTE**: A estrutura de pastas é rigorosa e deve ser respeitada.

#### `src/common/` - Módulos Compartilhados (Código Reutilizável)
- `config_loader.py` → Carregamento de configurações e credenciais
- `execution_logger.py` → Sistema de logging estruturado
- `screenshot_manager.py` → Gerenciamento de screenshots
- `rate_limit_handler.py` → Tratamento de rate limiting (HTTP 429)
- `playwright_captcha_manager.py` → Resolução de CAPTCHAs
- `notification_utils.py` → Envio de notificações por email
- `file_rename.py` → Utilitários de renomeação de arquivos
- `human_behavior_utils.py` → Utilitários de comportamento humano
- `captcha_solver.py` → Solver de CAPTCHA
- `database.py` → Operações de banco de dados

**Regra**: Código reutilizável **SEMPRE** vai em `src/common/`

#### `src/processors/web/` - Processadores Especializados
- Cada processador é independente e especializado
- Todos importam módulos de `src/common/`
- Backups ficam em `src/processors/web/backup/`

**Regra**: Processadores específicos **SEMPRE** vão em `src/processors/web/`

#### Outras Pastas Importantes:
- `config/` → Configurações operacionais (`processors.yaml`), sem senhas reais
- `data/raw_inputs/` → Arquivos CSV baixados
- `data/screenshots/` → Screenshots das execuções
- `logs/` → Logs de execução (com timestamp no nome)
- `src/api/` → APIs de controle
- `scripts/` → Scripts utilitários
- `docs/` → Documentação
- `tests/unit/` → Testes unitários
- `tests/integration/` → Testes de integração

#### Regras de Organização:
1. ✅ Novo código reutilizável → `src/common/`
2. ✅ Novo processador específico → `src/processors/web/`
3. ✅ Nova configuração → `config/`
4. ✅ Módulos de API → `src/api/`
5. ✅ Scripts utilitários → `scripts/`
6. ✅ Documentação → `docs/`
7. ✅ Testes → `tests/` (unit/ ou integration/)

---

### 3. SEMPRE USAR MÓDULOS COMMON AO INVÉS DE RECRIAR

**IMPORTANTE**: Sempre usar módulos existentes em `src/common/` ao invés de criar código novo.

#### Antes de criar novo código, verificar:
- ✅ `src/common/config_loader.py` → Para carregar configurações e credenciais
- ✅ `src/common/execution_logger.py` → Para logging estruturado
- ✅ `src/common/rate_limit_handler.py` → Para tratamento de rate limiting
- ✅ `src/common/playwright_captcha_manager.py` → Para resolução de CAPTCHAs
- ✅ `src/common/screenshot_manager.py` → Para captura de screenshots
- ✅ `src/common/notification_utils.py` → Para envio de notificações
- ✅ `src/common/file_rename.py` → Para renomeação de arquivos

#### Regras:
- ❌ **NUNCA** duplicar funcionalidade que já existe em `src/common/`
- ❌ **NUNCA** criar código novo quando já existe módulo equivalente
- ✅ **SEMPRE** importar e usar módulos de `src/common/`
- ✅ **SEMPRE** verificar `src/common/` antes de criar novo código

---

## 📋 COMANDOS BASH COMUNS

### Executar Processador Manualmente
```bash
# Modo Produção (finaliza após execução)
DISPLAY=:1 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/relatorio_operacao_desagio.py

# Modo Debug (mantém browser aberto)
DISPLAY=:1 DEBUG_MODE=true PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/relatorio_operacao_desagio.py
```

### Executar via API
```bash
# Iniciar API de controle
python3 src/api/control_api_titulos.py

# Disparar execução
curl -X POST http://localhost:6092/run
```

### Infraestrutura VNC
```bash
# Iniciar displays VNC
./scripts/iniciar_vnc_displays.sh

# Acessar via navegador: http://SEU_IP:6080/vnc.html
```

### Testes
```bash
# Testes unitários
pytest tests/unit/

# Testes de integração
pytest tests/integration/

# Todos os testes
pytest
```

### Backup
```bash
# Criar backup
./scripts/criar_backup.sh
```

---

## 📐 PADRÕES DE CÓDIGO

### Logging
- ✅ Usar `ExecutionLogger` de `src/common/execution_logger.py`
- ✅ Sempre incluir timestamps no formato `[YYYY-MM-DD HH:MM:SS]`
- ✅ Usar emojis para indicar status:
  - ✅ Sucesso
  - ⚠️ Aviso
  - ❌ Erro
  - 🔄 Processando
  - ⏳ Aguardando

### Screenshots
- ✅ Usar `ScreenshotManager` de `src/common/screenshot_manager.py`
- ✅ Respeitar `screenshot_level` configurado em `processors.yaml`:
  - `none`: Sem screenshots
  - `errors-only`: Apenas em erros
  - `milestones`: Pontos-chave (padrão recomendado)
  - `full`: Todos os screenshots disponíveis

### Rate Limiting
- ✅ **SEMPRE** usar `RateLimitHandler` de `src/common/rate_limit_handler.py`
- ✅ Respeitar header `Retry-After` quando disponível
- ✅ Usar backoff exponencial com jitter
- ✅ Aguardar tempo adicional após callback de retry

### Configuração e Credenciais
- ✅ Usar `ConfigLoader` de `src/common/config_loader.py`
- ✅ Carregar configurações de `config/processors.yaml`
- ✅ Consumir credenciais exclusivamente pela entrega do Access Guardian
- ✅ Respeitar política de rotação de credenciais configurada

### CAPTCHA
- ✅ Usar `PlaywrightCaptchaManager` de `src/common/playwright_captcha_manager.py`
- ✅ Não criar novo código de CAPTCHA
- ✅ Seguir padrão já implementado

---

## 🔧 ESTILO DE CÓDIGO

### Imports
- ✅ Organizar imports: stdlib, third-party, local
- ✅ Usar imports absolutos quando possível
- ✅ Agrupar imports relacionados

### Estrutura de Arquivos
- ✅ Incluir docstring no topo do arquivo com nome do módulo e descrição
- ✅ Usar type hints quando possível
- ✅ Seguir PEP 8

### Tratamento de Erros
- ✅ Usar logging estruturado para erros
- ✅ Capturar exceções específicas
- ✅ Incluir contexto útil nas mensagens de erro

---

## 📁 ESTRUTURA DO PROJETO

```
PROSPER-ERP-AUTOMATION/
├── config/                      # Configurações
│   ├── processors.yaml          # Config dos processadores
│   └── credentials.csv          # Credenciais (múltiplas contas)
│
├── src/
│   ├── common/                  # Módulos compartilhados ⚠️ NÃO DUPLICAR
│   ├── processors/web/         # Processadores especializados
│   └── api/                     # APIs de controle
│
├── data/
│   ├── raw_inputs/              # Arquivos CSV baixados
│   └── screenshots/             # Screenshots de execução
│
├── logs/                        # Logs de execução
├── scripts/                     # Scripts utilitários
├── docs/                        # Documentação
└── tests/                       # Testes
    ├── unit/
    └── integration/
```

---

## ⚠️ COMPORTAMENTOS ESPECÍFICOS DO PROJETO

### Processadores
- Cada processador roda em seu próprio display VNC (ex: `:1`, `:2`)
- Cada display tem sua própria porta VNC (6080, 6081, 6082...)
- Processadores podem rodar em modo `one-shot` ou `loop`
- Modo `one-shot`: executa uma vez e finaliza (ideal para cron)
- Modo `loop`: executa continuamente em loop (browser permanece aberto)

### Rate Limiting
- Servidor pode retornar HTTP 429 (Too Many Requests)
- Sistema tem tratamento automático com retry e backoff
- Respeitar header `Retry-After` quando disponível
- Aguardar tempo adicional após callback de retry

### Credenciais
- Múltiplas credenciais por processador (em `config/credentials.csv`)
- Políticas de rotação: `round_robin`, `sequential`, `random`, `first`
- Rotação configurada em `config/processors.yaml`

---

## 🚫 O QUE NÃO FAZER

- ❌ Modificar um processador para fazer tarefa de outro
- ❌ Duplicar código que já existe em `src/common/`
- ❌ Criar novo código de CAPTCHA (usar `playwright_captcha_manager.py`)
- ❌ Criar novo sistema de logging (usar `execution_logger.py`)
- ❌ Criar novo sistema de rate limiting (usar `rate_limit_handler.py`)
- ❌ Colocar código reutilizável em `src/processors/web/`
- ❌ Colocar processador específico em `src/common/`
- ❌ Commitar credenciais reais em `config/credentials.csv`
- ❌ Ignorar estrutura de pastas

---

## ✅ CHECKLIST ANTES DE CRIAR CÓDIGO

1. [ ] Verificar se já existe processador especializado para a tarefa
2. [ ] Verificar se funcionalidade já existe em `src/common/`
3. [ ] Verificar documentação em `docs/` (especialmente `COMO_CRIAR_PROCESSADORES.md`)
4. [ ] Confirmar pasta correta para o novo código
5. [ ] Verificar se precisa atualizar `config/processors.yaml`
6. [ ] Verificar se precisa atualizar `config/credentials.csv`
7. [ ] Verificar padrões de código e logging

---

## 📚 DOCUMENTAÇÃO ÚTIL

- `docs/COMO_CRIAR_PROCESSADORES.md` → Guia completo para criar processadores
- `docs/SISTEMA_BACKUP.md` → Sistema de backup
- `docs/ESTRUTURA_DE_PASTAS.md` → Organização do projeto
- `README.md` → Visão geral do projeto

---

**Última atualização**: 2025-11-14
**Python**: 3.12+
**Playwright**: Latest

## Banco — estado atual

O ERP conecta pelo proxy do access-guardian. A identidade efetiva verificada é
`app_erp_automation`, com `session_user` efêmero `gdh_erp_automation_...`.
As variáveis de senha de banco do container ficam vazias; o proxy usa a
capability/passfile. A descrição antiga de conexão como superusuário ficou
obsoleta após a migração.

Emissão/envio escrevem em `erp_automation.boleto_emissao_log` e
`erp_automation.boleto_envio_log`. A leitura legada de
`operacional.boleto_envio_log` usa view de compatibilidade. Não alterar schemas
ou permissões baseado apenas em nomes antigos deste documento.

# hub orchestration

leia a documantecacao da api do hub-orchestration   para acessar via api


voce tem os dados em .env

⛔ **Credencial nunca em arquivo versionado.**

**Registro histórico (03/08; não usar como estado atual):** `operacional.boleto_envio_log` /
`boleto_emissao_log` / `boleto_sessao_healthcheck`, e `stg.doc*` / `stg.robo_analise_*`.
⚠️ A tabela `operacional.boleto_envio_log` foi **criada pela migration 079 do
`process-automation`** e é escrita daqui — dependência cross-repo real, sem contrato de
schema versionado do lado de quem escreve.

Mapa completo: registro
`2026-08-03-quem-escreve-no-banco-o-mapa-que-nunca-existiu` no PostgreSQL do Learn
(`learn contexto "quem escreve no banco"`).
