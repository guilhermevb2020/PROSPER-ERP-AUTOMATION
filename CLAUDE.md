# PROSPER-ERP-AUTOMATION - Diretrizes para Claude Code

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
- `config/` → Configurações (`processors.yaml`, `credentials.csv`)
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
- ✅ Carregar credenciais de `config/credentials.csv`
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

## Banco — a role deste projeto

`app_erp_automation`, credencial em `APP_DB_USER`/`APP_DB_PASSWORD` do `.env`. **Criada
em 03/08/2026, ainda NÃO em uso** — a troca da conexão é passo deliberado.

⚠️ **Hoje este container tem `DB_USER=prospere`, que é SUPERUSUÁRIO.** Superusuário
ignora qualquer permissão do banco. Sair disso é o motivo da role existir.

Ela **não é superusuário**, e por ora herda `dev_user` (andaime) para a troca não mudar
comportamento nenhum. O aperto vem depois, guiado pelo **log de DDL** — ligado em
03/08/2026, registra usuário, IP e aplicação de todo `CREATE`/`ALTER`/`DROP`/`GRANT`.

⛔ **Credencial nunca em arquivo versionado.**

**O que este projeto escreve, medido em 03/08:** `operacional.boleto_envio_log` /
`boleto_emissao_log` / `boleto_sessao_healthcheck`, e `stg.doc*` / `stg.robo_analise_*`.
⚠️ A tabela `operacional.boleto_envio_log` foi **criada pela migration 079 do
`process-automation`** e é escrita daqui — dependência cross-repo real, sem contrato de
schema versionado do lado de quem escreve.

Mapa completo:
`automation/process-automation/docs/ADR/diagnostico/2026-08-03-quem-escreve-no-banco-o-mapa-que-nunca-existiu.md`




