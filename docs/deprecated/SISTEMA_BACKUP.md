# Sistema de Backup - PROSPER-ERP-AUTOMATION

## Visão Geral

Este documento explica como realizar backups do projeto, o que incluir, onde armazenar e como restaurar. O sistema de backup foi projetado para permitir recuperação rápida e documentar melhorias incrementais.

---

## O Que Fazer Backup

### ✅ INCLUIR NO BACKUP

#### 1. Código Fonte
```
src/
├── common/              # Módulos compartilhados
├── processors/          # Processadores (web, local, etc)
├── config/              # Configurações
└── api/                 # APIs de controle
```

#### 2. Configurações
```
config/
├── processors.yaml      # Configuração dos processadores
└── credentials.csv      # Credenciais (CRIPTOGRAFAR antes do backup!)
```

#### 3. Documentação
```
docs/
├── COMO_CRIAR_PROCESSADORES.md
├── SISTEMA_BACKUP.md
├── BRIGHT_DATA_SETUP.md
└── *.md                 # Todos os documentos
```

#### 4. Scripts e Utilitários
```
scripts/
└── *.sh                 # Scripts de inicialização e manutenção
```

#### 5. Arquivos de Configuração Raiz
```
requirements.txt         # Dependências Python
.env.example            # Template de variáveis de ambiente
README.md               # Documentação principal
```

#### 6. Testes
```
tests/
├── unit/               # Testes unitários
└── integration/        # Testes de integração
```

### ❌ EXCLUIR DO BACKUP

```
# Pastas de ambiente virtual
venv/
env/
.venv/

# Dados temporários e cache
data/
logs/
screenshots/
__pycache__/
*.pyc
.pytest_cache/

# Arquivos sensíveis (fazer backup separado criptografado)
.env
config/credentials.csv  # Backup criptografado separadamente

# Arquivos de sistema
.git/                   # Git já é controle de versão
.DS_Store
*.swp
*.swo
*~

# Pastas de máquina virtual (VNC, displays, etc)
/tmp/
/var/
```

---

## Estrutura de Backup Recomendada

### Localização
```
/backups/
└── PROSPER-ERP-AUTOMATION/
    ├── 2025-11-10_v1.0_credential-rotation/
    │   ├── src/
    │   ├── config/
    │   ├── docs/
    │   ├── scripts/
    │   ├── tests/
    │   ├── requirements.txt
    │   ├── CHANGELOG.md
    │   └── README.md
    │
    └── 2025-11-XX_vX.X_feature-name/
        └── ...
```

### Convenção de Nomenclatura
```
YYYY-MM-DD_vX.X_feature-name/

Exemplos:
- 2025-11-10_v1.0_credential-rotation
- 2025-11-10_v1.1_popup-captcha-fix
- 2025-11-10_v1.2_debug-conditional-mode
```

---

## Script de Backup Automático

### Criar Script: `scripts/criar_backup.sh`

```bash
#!/bin/bash

# =============================================================================
# Script de Backup Automático - PROSPER-ERP-AUTOMATION
# =============================================================================

set -e

# Configurações
PROJECT_DIR="/home/ubuntu/PROSPER-ERP-AUTOMATION"
BACKUP_BASE_DIR="/backups/PROSPER-ERP-AUTOMATION"
DATE=$(date +%Y-%m-%d_%H%M%S)

# Solicitar informações do backup
read -p "Versão (ex: v1.0): " VERSION
read -p "Nome da feature (ex: credential-rotation): " FEATURE_NAME

# Criar nome do backup
BACKUP_NAME="${DATE}_${VERSION}_${FEATURE_NAME}"
BACKUP_DIR="${BACKUP_BASE_DIR}/${BACKUP_NAME}"

echo "📦 Criando backup: ${BACKUP_NAME}"

# Criar diretório de backup
mkdir -p "${BACKUP_DIR}"

# Copiar código fonte
echo "📂 Copiando código fonte..."
rsync -av --progress \
    --exclude='venv/' \
    --exclude='env/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='data/' \
    --exclude='logs/' \
    --exclude='screenshots/' \
    --exclude='.git/' \
    --exclude='.env' \
    "${PROJECT_DIR}/src/" "${BACKUP_DIR}/src/"

# Copiar configurações (SEM credentials.csv original)
echo "🔧 Copiando configurações..."
mkdir -p "${BACKUP_DIR}/config"
cp "${PROJECT_DIR}/config/processors.yaml" "${BACKUP_DIR}/config/"
# Criar credentials.csv de exemplo
cat > "${BACKUP_DIR}/config/credentials.example.csv" << 'EOF'
processador,cliente,usuario,senha,ativo
relatorio_operacao_desagio,prosper,email@example.com,senha_example,true
EOF

# Copiar documentação
echo "📚 Copiando documentação..."
rsync -av --progress "${PROJECT_DIR}/docs/" "${BACKUP_DIR}/docs/"

# Copiar scripts
echo "🔨 Copiando scripts..."
rsync -av --progress "${PROJECT_DIR}/scripts/" "${BACKUP_DIR}/scripts/"

# Copiar testes
echo "🧪 Copiando testes..."
rsync -av --progress \
    --exclude='__pycache__/' \
    "${PROJECT_DIR}/tests/" "${BACKUP_DIR}/tests/"

# Copiar arquivos raiz
echo "📄 Copiando arquivos raiz..."
cp "${PROJECT_DIR}/requirements.txt" "${BACKUP_DIR}/"
cp "${PROJECT_DIR}/README.md" "${BACKUP_DIR}/"
[ -f "${PROJECT_DIR}/.env.example" ] && cp "${PROJECT_DIR}/.env.example" "${BACKUP_DIR}/"

# Criar CHANGELOG para este backup
echo "📝 Criando CHANGELOG..."
cat > "${BACKUP_DIR}/CHANGELOG.md" << EOF
# Changelog - ${BACKUP_NAME}

## Versão: ${VERSION}
## Data: ${DATE}
## Feature: ${FEATURE_NAME}

## Melhorias Implementadas

### [Descrever melhorias aqui]

1. **Melhoria 1**
   - Descrição...
   - Impacto...

2. **Melhoria 2**
   - Descrição...
   - Impacto...

## Arquivos Modificados

### [Listar arquivos principais]

- src/processors/web/relatorio_operacao_desagio.py
- src/common/config_loader.py
- etc...

## Testes Realizados

### [Descrever testes]

- [ ] Teste 1
- [ ] Teste 2

## Notas Adicionais

[Informações adicionais relevantes]

EOF

# Criar arquivo de metadados
cat > "${BACKUP_DIR}/BACKUP_INFO.txt" << EOF
Backup: ${BACKUP_NAME}
Data: ${DATE}
Versão: ${VERSION}
Feature: ${FEATURE_NAME}
Origem: ${PROJECT_DIR}
Python: $(python3 --version)
Sistema: $(uname -a)
EOF

# Calcular tamanho
BACKUP_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)

echo ""
echo "✅ Backup criado com sucesso!"
echo "📍 Localização: ${BACKUP_DIR}"
echo "📊 Tamanho: ${BACKUP_SIZE}"
echo ""
echo "⚠️  Lembre-se de:"
echo "   1. Editar ${BACKUP_DIR}/CHANGELOG.md com as melhorias"
echo "   2. Fazer backup separado e criptografado das credenciais se necessário"
echo "   3. Testar a restauração do backup"
echo ""
```

---

## Como Usar o Script de Backup

### 1. Tornar Executável
```bash
chmod +x scripts/criar_backup.sh
```

### 2. Executar
```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
./scripts/criar_backup.sh
```

### 3. Responder Perguntas
```
Versão (ex: v1.0): v1.2
Nome da feature (ex: credential-rotation): debug-conditional-mode
```

### 4. Editar CHANGELOG
```bash
nano /backups/PROSPER-ERP-AUTOMATION/2025-11-10_*_debug-conditional-mode/CHANGELOG.md
```

---

## Restauração de Backup

### Restauração Completa

```bash
#!/bin/bash

# Configurar variáveis
BACKUP_DIR="/backups/PROSPER-ERP-AUTOMATION/2025-11-10_v1.2_debug-conditional-mode"
PROJECT_DIR="/home/ubuntu/PROSPER-ERP-AUTOMATION"

# Fazer backup do estado atual primeiro!
mv "${PROJECT_DIR}" "${PROJECT_DIR}.old.$(date +%Y%m%d_%H%M%S)"

# Copiar backup para projeto
cp -r "${BACKUP_DIR}" "${PROJECT_DIR}"

# Restaurar ambiente virtual
cd "${PROJECT_DIR}"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configurar credenciais
cp config/credentials.example.csv config/credentials.csv
nano config/credentials.csv  # Editar com credenciais reais

# Configurar .env
cp .env.example .env
nano .env  # Editar com valores reais

echo "✅ Restauração concluída!"
```

### Restauração Parcial (Apenas Código)

```bash
# Restaurar apenas um processador específico
BACKUP_DIR="/backups/PROSPER-ERP-AUTOMATION/2025-11-10_v1.2_debug-conditional-mode"
cp "${BACKUP_DIR}/src/processors/web/relatorio_operacao_desagio.py" \
   "/home/ubuntu/PROSPER-ERP-AUTOMATION/src/processors/web/"
```

---

## Documentação de Melhorias

### Backup v1.0 - Sistema de Rotação de Credenciais (2025-11-10)

#### Melhorias Implementadas

1. **Sistema de Configuração Centralizado**
   - Criado `src/common/config_loader.py`
   - Suporte a múltiplas políticas de rotação:
     - `round_robin`: Rotação circular automática
     - `sequential`: Uso sequencial
     - `random`: Seleção aleatória
     - `first`: Sempre usa primeira credencial disponível

2. **Arquivo de Configuração YAML**
   - `config/processors.yaml`: Configurações de cada processador
   - Separação clara entre config e código
   - Facilita adicionar novos processadores

3. **Arquivo de Credenciais CSV**
   - `config/credentials.csv`: Múltiplas credenciais por processador
   - Suporte a flag `ativo` para desabilitar credenciais
   - Rotação automática entre credenciais ativas

4. **Integração com Processadores**
   - `relatorio_operacao_desagio.py` atualizado para usar ConfigLoader
   - Fallback para `.env` mantido para compatibilidade
   - Log detalhado da política de rotação utilizada

#### Arquivos Criados/Modificados

**Criados:**
- `src/common/config_loader.py` (322 linhas)
- `config/credentials.csv`

**Modificados:**
- `src/processors/web/relatorio_operacao_desagio.py`:
  - Linhas 66-97: Carregamento de configuração
  - Linhas 134-151: Rotação de credenciais
  - Redução de código: Melhor organização

#### Testes Realizados

- [x] Carregamento de configuração do YAML
- [x] Rotação round-robin entre 2 credenciais
- [x] Fallback para .env quando config não disponível
- [x] Log correto da política utilizada
- [x] Execução completa com primeira credencial
- [x] Execução completa com segunda credencial (após rotação)

#### Impacto
- ✅ Reduz bloqueios por uso excessivo de uma conta
- ✅ Facilita adicionar novos processadores
- ✅ Centraliza configuração
- ✅ Mantém compatibilidade com sistema antigo

---

### Backup v1.1 - Correção do Popup CAPTCHA (2025-11-10)

#### Problema Identificado

O processador não estava capturando o popup do CAPTCHA durante a geração do relatório. O erro ocorria porque o listener de popup era registrado APÓS o botão já ter sido clicado.

**Log do Erro:**
```
[2025-11-10 15:31:03] 📝 Formulário preenchido (prof: 2, botão: True)
[2025-11-10 15:31:16] ℹ️ Usando site_key hardcoded para relatorio
[2025-11-10 15:31:37] ❌ CapSolver - falha ao injetar token
```

#### Correção Implementada

**Antes (Bugado):**
```python
# Linha ~480
resultado = await self.page.evaluate(script_preencher)  # Click aqui
# ... código ...
async with self.page.expect_popup(timeout=10000) as popup_info:  # Tarde demais!
    pass
```

**Depois (Corrigido):**
```python
# Linhas 471-504
async with self.page.expect_popup(timeout=10000) as popup_info:
    resultado = await self.page.evaluate(script_preencher)  # Click dentro do context
popup_page = await popup_info.value  # Agora captura o popup!
```

#### Arquivos Modificados

- `src/processors/web/relatorio_operacao_desagio.py`:
  - Linhas 471-504: Reestruturação do context manager

#### Testes Realizados

- [x] Popup capturado corretamente
- [x] CAPTCHA resolvido com sucesso
- [x] Download do relatório completado
- [x] Arquivo renomeado corretamente

#### Log de Sucesso
```
[2025-11-10 15:35:54] ✅ Popup CAPTCHA detectado
[2025-11-10 15:36:22] ✅ CapSolver resolveu CAPTCHA com sucesso
[2025-11-10 15:36:25] ✅ Botão Confirmar clicado - download iniciado
[2025-11-10 15:37:17] 📝 Arquivo renomeado
[2025-11-10 15:37:17] ✅ Extração concluída com sucesso
```

---

### Backup v1.2 - Modo Debug Condicional (2025-11-10)

#### Problema Identificado

Após conclusão bem-sucedida da extração, o processador continuava rodando indefinidamente ao invés de finalizar e liberar recursos.

**Causa Raiz:**
Loop infinito incondicional no final da execução:
```python
# TEMPORÁRIO: Manter browser aberto para testes
while True:
    await asyncio.sleep(10)  # Roda para sempre!
```

#### Correção Implementada

**Modo Debug Condicional:**
```python
# Linhas 709-726
await self.executar_extracao_completa()

if DEBUG:
    # MODO DEBUG: Manter browser aberto indefinidamente
    print("🔧 MODO DEBUG ATIVO")
    print(f"   Browser permanecerá aberto para inspeção")
    print(f"   Acesse: http://{SERVER_IP}:6080/vnc.html")
    print("   Pressione Ctrl+C para encerrar")

    while True:
        await asyncio.sleep(10)
else:
    # MODO PRODUÇÃO: Fechar normalmente
    print("✅ EXTRAÇÃO CONCLUÍDA COM SUCESSO!")
    print("   Encerrando browser e finalizando processo...")
    # Continua para bloco finally que fecha tudo
```

**Variável de Ambiente:**
```python
# Linha 50
DEBUG = os.getenv("DEBUG_MODE", "false").lower() == "true"
```

#### Arquivos Modificados

- `src/processors/web/relatorio_operacao_desagio.py`:
  - Linha 50: Variável DEBUG
  - Linhas 709-726: Condicional de finalização

#### Uso

**Modo Produção (padrão):**
```bash
DISPLAY=:1 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/relatorio_operacao_desagio.py
```

**Modo Debug:**
```bash
DISPLAY=:1 DEBUG_MODE=true PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/relatorio_operacao_desagio.py
```

#### Testes Realizados

- [x] Modo produção finaliza corretamente após extração
- [x] Modo debug mantém browser aberto
- [x] Log de finalização exibido corretamente
- [x] Recursos liberados em modo produção

#### Log de Sucesso (Produção)
```
[2025-11-10 16:31:53] ✅ Extração concluída com sucesso
[2025-11-10 16:31:54] 🔒 Browser fechado
[2025-11-10 16:31:54] 🏁 Processador finalizado

================================================================================
FIM: 2025-11-10 16:31:54
================================================================================
```

#### Impacto
- ✅ Permite execução via cron sem processos órfãos
- ✅ Libera recursos (browser, display VNC) corretamente
- ✅ Mantém capacidade de debug quando necessário
- ✅ Facilita troubleshooting em desenvolvimento

---

## Checklist de Backup

Antes de criar um backup, verifique:

- [ ] Todas as alterações foram testadas
- [ ] Logs mostram execução bem-sucedida
- [ ] Código está comentado adequadamente
- [ ] requirements.txt está atualizado
- [ ] Documentação foi atualizada
- [ ] Credenciais sensíveis foram removidas
- [ ] .env não está incluído
- [ ] Testes passam (se houver)
- [ ] CHANGELOG.md foi preenchido
- [ ] Versão foi incrementada adequadamente

---

## Segurança de Credenciais

### Backup Separado de Credenciais

```bash
# Criar backup criptografado de credenciais
tar -czf credentials_backup.tar.gz config/credentials.csv .env
gpg -c credentials_backup.tar.gz
rm credentials_backup.tar.gz

# Mover para local seguro
mv credentials_backup.tar.gz.gpg /secure/backups/
```

### Restaurar Credenciais
```bash
# Descriptografar
gpg -d /secure/backups/credentials_backup.tar.gz.gpg > credentials_backup.tar.gz

# Extrair
tar -xzf credentials_backup.tar.gz

# Limpar
rm credentials_backup.tar.gz
```

---

## Versionamento Semântico

```
vX.Y.Z

X = Major (mudanças incompatíveis)
Y = Minor (novas features compatíveis)
Z = Patch (correções de bugs)

Exemplos:
- v1.0.0 - Release inicial com rotação de credenciais
- v1.0.1 - Correção do popup CAPTCHA
- v1.0.2 - Modo debug condicional
- v1.1.0 - Nova feature: notificações por Telegram
- v2.0.0 - Migração para nova arquitetura
```

---

## Manutenção de Backups

### Rotação de Backups Antigos

```bash
# Manter apenas últimos 10 backups
cd /backups/PROSPER-ERP-AUTOMATION
ls -t | tail -n +11 | xargs rm -rf
```

### Backup para Cloud (Opcional)

```bash
# Exemplo: Sync para AWS S3
aws s3 sync /backups/PROSPER-ERP-AUTOMATION \
    s3://prosper-erp-backups/automation/ \
    --exclude "*.csv" \
    --exclude ".env"
```

---

## Conclusão

Este sistema de backup permite:

1. ✅ Recuperação rápida de código funcional
2. ✅ Documentação incremental de melhorias
3. ✅ Rastreamento de mudanças entre versões
4. ✅ Onboarding rápido de novos desenvolvedores/IAs
5. ✅ Histórico claro de evolução do projeto

**Lembre-se:** Backups regulares são essenciais. Crie um backup sempre que:
- Implementar nova feature significativa
- Corrigir bug crítico
- Refatorar código importante
- Antes de mudanças arriscadas
