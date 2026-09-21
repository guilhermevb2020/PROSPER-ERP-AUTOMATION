# 📘 Como Criar um Novo Processador

**Versão:** 1.0
**Data:** 2025-10-25

---

## 📋 Índice

1. [Pré-requisitos](#pré-requisitos)
2. [Estrutura de um Processador](#estrutura-de-um-processador)
3. [Passo a Passo](#passo-a-passo)
4. [Template Completo](#template-completo)
5. [Métodos Obrigatórios](#métodos-obrigatórios)
6. [Boas Práticas](#boas-práticas)
7. [Configuração de Display](#configuração-de-display)
8. [Testes](#testes)
9. [Deploy](#deploy)

---

## ✅ Pré-requisitos

Antes de criar um novo processador, você deve ter:

- ✅ Python 3.12+ instalado
- ✅ Ambiente virtual configurado (`venv/`)
- ✅ Dependências instaladas (`pip install -r requirements.txt`)
- ✅ Display virtual configurado (Xvfb + VNC)
- ✅ Credenciais no `.env` (SMART_EMAIL, SMART_PASSWORD, CAPSOLVER_API_KEY)
- ✅ Conhecimento básico de async/await Python
- ✅ Familiaridade com Nodriver (sucessor do Selenium)

---

## 🏗️ Estrutura de um Processador

Todo processador segue este padrão arquitetural:

```python
class ProcessadorNome:
    """
    Processador [Nome] - 100% Nodriver Async

    Características:
    - Anti-detecção nativa
    - 100% async/await
    - Isolamento total (display próprio)
    - Notificações por email
    - Controle remoto via API
    - Máquina de estados
    """

    def __init__(self):
        # Configuração inicial

    def escutar_teclado(self):
        # Thread para controlar P/R/Q

    async def iniciar_navegador(self):
        # Inicializa Nodriver

    async def fazer_login_automatico(self):
        # Login no sistema

    async def executar_extracao_completa(self):
        # Pipeline de extração

    async def processar(self):
        # Loop principal
```

---

## 📝 Passo a Passo

### **Passo 1: Criar Arquivo do Processador**

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
touch src/processors/web/meu_processador.py
```

### **Passo 2: Copiar Template (veja seção abaixo)**

Use o template completo e adapte para sua necessidade específica.

### **Passo 3: Implementar Métodos Específicos**

Implemente os métodos de extração específicos do seu caso de uso:

```python
async def navegar_para_relatorio(self):
    """Navega para a página do relatório"""
    await self.tab.get("https://smartsecurities.com.br/relatorios")
    await asyncio.sleep(2)

async def preencher_filtros(self):
    """Preenche filtros da página"""
    # Buscar elemento
    input_data = await wait_for_element(self.tab, "#data_inicio", timeout=10)

    # Preencher com comportamento humano
    await human_type(input_data, "01/10/2025")

    # Clicar botão
    btn_pesquisar = await self.tab.find("#btn_pesquisar")
    await human_click(btn_pesquisar)

async def baixar_csv(self):
    """Gera e baixa CSV"""
    btn_exportar = await self.tab.find("#btn_exportar")
    await human_click(btn_exportar)

    # Aguardar download
    await asyncio.sleep(5)
```

### **Passo 4: Configurar Display**

Cada processador deve rodar em seu próprio display isolado:

```bash
# Processador 1 - Display :1
DISPLAY=:1 python src/processors/web/meu_processador.py

# Processador 2 - Display :2
DISPLAY=:2 python src/processors/web/outro_processador.py
```

### **Passo 5: Testar Localmente**

```bash
# Ativar venv
source venv/bin/activate

# Configurar display e PYTHONPATH
export DISPLAY=:1
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION

# Executar processador
python src/processors/web/meu_processador.py
```

---

## 📄 Template Completo

```python
#!/usr/bin/env python3
"""
Processador: [NOME DO PROCESSADOR]
Descrição: [DESCRIÇÃO DO QUE FAZ]
Autor: Equipe PROSPER
Data: 2025-10-25
"""

import os
import sys
import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Imports Nodriver
import nodriver as uc
from nodriver import Browser, Tab
from nodriver.core.element import Element

# Imports do projeto
from src.common.nodriver_utils import (
    init_browser,
    wait_for_element,
    close_browser,
    human_click,
    human_type,
    simulate_human_activity
)
from src.core.logging_config import get_logger
from src.common.timezone_utils import now_br, formatted_now_br
from src.common.notification_utils import (
    enviar_alerta_captcha,
    enviar_alerta_erro_critico
)
from src.common.captcha_solver import CapSolverAPI

# Configuração
load_dotenv()
logger = get_logger(__name__)


class ProcessadorMeuNome:
    """Processador [Nome] - 100% Nodriver Async"""

    def __init__(self):
        """Inicializa o processador"""
        self.nome = "meu_processador"
        self.browser: Browser = None
        self.tab: Tab = None
        self.display = os.environ.get('DISPLAY', ':1')

        # Controles
        self.pausado = False
        self.parar = False

        # CAPTCHA Solver
        self.capsolver = CapSolverAPI(os.getenv("CAPSOLVER_API_KEY"))

        # Credenciais
        self.usuario = os.getenv("USUARIO_SITE_SMART")
        self.senha = os.getenv("SENHA_SITE_SMART")

        # Diretórios
        self.download_dir = Path("data/raw_inputs/")
        self.download_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{self.nome}] Processador inicializado - Display {self.display}")

    def escutar_teclado(self):
        """Thread para escutar comandos do teclado (P/R/Q)"""
        logger.info(f"[{self.nome}] Listener de teclado iniciado (P=Pausar, R=Retomar, Q=Parar)")

        while not self.parar:
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    if msvcrt.kbhit():
                        tecla = msvcrt.getch().decode('utf-8').upper()
                        self.processar_comando(tecla)
                else:
                    import select
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        tecla = sys.stdin.read(1).upper()
                        self.processar_comando(tecla)

                time.sleep(0.1)
            except Exception as e:
                logger.debug(f"[{self.nome}] Erro no listener de teclado: {e}")

    def processar_comando(self, tecla: str):
        """Processa comando do teclado"""
        if tecla == 'P' and not self.pausado:
            self.pausado = True
            logger.warning(f"[{self.nome}] ⏸️  EXECUÇÃO PAUSADA!")
            print(f"\n⏸️  [{self.nome}] PAUSADO - Pressione [R] para retomar\n")

        elif tecla == 'R' and self.pausado:
            self.pausado = False
            logger.info(f"[{self.nome}] ▶️  EXECUÇÃO RETOMADA!")
            print(f"\n▶️  [{self.nome}] RETOMADO\n")

        elif tecla == 'Q':
            self.parar = True
            logger.warning(f"[{self.nome}] ⏹️  PARANDO...")
            print(f"\n⏹️  [{self.nome}] PARANDO...\n")

    async def verificar_pausa(self):
        """Aguarda enquanto pausado (não bloqueia event loop)"""
        while self.pausado and not self.parar:
            await asyncio.sleep(0.2)

    async def iniciar_navegador(self):
        """Inicializa navegador Nodriver com anti-detecção"""
        logger.info(f"[{self.nome}] Iniciando navegador Nodriver...")

        try:
            os.environ['DISPLAY'] = self.display

            self.browser = await init_browser(
                download_dir=str(self.download_dir),
                headless=False,
                display=self.display
            )

            self.tab = self.browser.main_tab

            logger.info(f"[{self.nome}] ✅ Navegador iniciado com sucesso!")

        except Exception as e:
            logger.error(f"[{self.nome}] ❌ Erro ao iniciar navegador: {e}")
            raise

    async def fazer_login_automatico(self):
        """Realiza login no SmartSecurities"""
        logger.info(f"[{self.nome}] Fazendo login no SmartSecurities...")

        try:
            # Navegar para página de login
            await self.tab.get("https://smartsecurities.com.br/smartsecurities")
            await asyncio.sleep(2)

            # Buscar campos de login (adapte os seletores!)
            input_email = await wait_for_element(self.tab, "#email", timeout=10)
            input_senha = await wait_for_element(self.tab, "#senha", timeout=10)

            # Preencher credenciais com comportamento humano
            await human_type(input_email, self.usuario)
            await asyncio.sleep(0.5)
            await human_type(input_senha, self.senha)
            await asyncio.sleep(0.5)

            # Clicar no botão de login
            btn_login = await self.tab.find("#btn_login")
            await human_click(btn_login)

            # Aguardar redirecionamento
            await asyncio.sleep(3)

            logger.info(f"[{self.nome}] ✅ Login realizado com sucesso!")

        except Exception as e:
            logger.error(f"[{self.nome}] ❌ Erro ao fazer login: {e}")
            raise

    async def executar_extracao_completa(self):
        """
        Pipeline completo de extração

        Adapte este método para sua lógica específica!
        """
        logger.info(f"[{self.nome}] Iniciando extração completa...")

        try:
            # EXEMPLO: Adapte para seu caso

            # 1. Navegar para página
            await self.tab.get("https://smartsecurities.com.br/relatorios")
            await asyncio.sleep(2)

            # 2. Preencher filtros
            logger.info(f"[{self.nome}] Preenchendo filtros...")
            # TODO: Implementar lógica de filtros

            # 3. Clicar em pesquisar
            logger.info(f"[{self.nome}] Executando pesquisa...")
            # TODO: Implementar lógica de pesquisa

            # 4. Baixar CSV
            logger.info(f"[{self.nome}] Gerando CSV...")
            # TODO: Implementar lógica de download

            # 5. Renomear arquivo
            logger.info(f"[{self.nome}] Renomeando arquivo...")
            # TODO: Implementar lógica de renomeação

            logger.info(f"[{self.nome}] ✅ Extração completa finalizada!")

        except Exception as e:
            logger.error(f"[{self.nome}] ❌ Erro na extração: {e}")

            # Enviar email de erro
            await enviar_alerta_erro_critico(
                processador=self.nome,
                erro=str(e),
                display=self.display
            )

            raise

    async def processar(self, modo_simulacao: bool = False):
        """
        Loop principal do processador

        Args:
            modo_simulacao: Se True, executa apenas 1 ciclo
        """
        try:
            logger.info(f"[{self.nome}] ========================================")
            logger.info(f"[{self.nome}] Iniciando processador")
            logger.info(f"[{self.nome}] Display: {self.display}")
            logger.info(f"[{self.nome}] Modo simulação: {modo_simulacao}")
            logger.info(f"[{self.nome}] ========================================")

            # Iniciar listener de teclado
            listener_thread = threading.Thread(
                target=self.escutar_teclado,
                daemon=True
            )
            listener_thread.start()

            # Iniciar navegador
            await self.iniciar_navegador()

            # Fazer login
            await self.fazer_login_automatico()

            # Loop de ciclos
            ciclo = 1
            while not self.parar:
                # Verificar se está pausado
                await self.verificar_pausa()

                if self.parar:
                    break

                logger.info(f"[{self.nome}] ========== CICLO {ciclo} ==========")

                try:
                    # Executar extração
                    await self.executar_extracao_completa()

                    logger.info(f"[{self.nome}] ✅ Ciclo {ciclo} concluído com sucesso!")

                except Exception as e:
                    logger.error(f"[{self.nome}] ❌ Erro no ciclo {ciclo}: {e}")

                ciclo += 1

                # Se modo simulação, executa apenas 1 ciclo
                if modo_simulacao:
                    logger.info(f"[{self.nome}] Modo simulação - Finalizando após 1 ciclo")
                    break

                # Aguardar antes do próximo ciclo
                logger.info(f"[{self.nome}] Aguardando 60 segundos até próximo ciclo...")
                await asyncio.sleep(60)

            # Fechar navegador
            if self.browser:
                logger.info(f"[{self.nome}] Fechando navegador...")
                await close_browser(self.browser)

            logger.info(f"[{self.nome}] ✅ Processamento concluído!")

            return {
                "status": "sucesso",
                "ciclos_executados": ciclo - 1,
                "processador": self.nome
            }

        except Exception as e:
            logger.error(f"[{self.nome}] ❌ Erro fatal: {e}")

            # Fechar navegador em caso de erro
            if self.browser:
                try:
                    await close_browser(self.browser)
                except:
                    pass

            raise


# ============================================================================
# WRAPPER SYNC - Permite chamar função async de forma síncrona
# ============================================================================

def processar_meu_processador(modo_simulacao: bool = False) -> dict:
    """
    Wrapper síncrono para o processador async

    Args:
        modo_simulacao: Se True, executa apenas 1 ciclo

    Returns:
        dict com resultado da execução
    """
    processador = ProcessadorMeuNome()
    return asyncio.run(processador.processar(modo_simulacao=modo_simulacao))


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Executar processador
    resultado = processar_meu_processador(modo_simulacao=False)
    print(f"\n✅ Processador finalizado: {resultado}\n")
```

---

## 🔧 Métodos Obrigatórios

Todo processador **DEVE** implementar:

| Método | Descrição | Obrigatório |
|--------|-----------|-------------|
| `__init__()` | Inicialização | ✅ Sim |
| `escutar_teclado()` | Listener P/R/Q | ✅ Sim |
| `processar_comando()` | Handler P/R/Q | ✅ Sim |
| `verificar_pausa()` | Aguarda se pausado | ✅ Sim |
| `async iniciar_navegador()` | Inicia Nodriver | ✅ Sim |
| `async fazer_login_automatico()` | Login no sistema | ✅ Sim |
| `async executar_extracao_completa()` | Pipeline de extração | ✅ Sim |
| `async processar()` | Loop principal | ✅ Sim |

---

## ✨ Boas Práticas

### **1. Sempre Use Async/Await**

```python
# ❌ ERRADO (bloqueante)
time.sleep(2)

# ✅ CORRETO (não bloqueante)
await asyncio.sleep(2)
```

### **2. Use Funções Helper de nodriver_utils**

```python
# ❌ ERRADO (sem retry, sem comportamento humano)
elemento = await self.tab.find("#botao")
await elemento.click()

# ✅ CORRETO (com retry e comportamento humano)
elemento = await wait_for_element(self.tab, "#botao", timeout=10)
await human_click(elemento)
```

### **3. Sempre Faça Log de Ações Importantes**

```python
logger.info(f"[{self.nome}] Iniciando extração do relatório X")
logger.debug(f"[{self.nome}] Valor encontrado: {valor}")
logger.warning(f"[{self.nome}] Tentativa {i}/3 falhou")
logger.error(f"[{self.nome}] Erro crítico: {e}")
```

### **4. Trate Erros e Envie Notificações**

```python
try:
    await self.executar_extracao_completa()
except Exception as e:
    logger.error(f"[{self.nome}] Erro: {e}")

    # Enviar email de alerta
    await enviar_alerta_erro_critico(
        processador=self.nome,
        erro=str(e),
        display=self.display
    )

    raise
```

### **5. Use Máquina de Estados**

```python
# Estados possíveis
ESTADOS = [
    "INICIANDO",
    "FAZENDO_LOGIN",
    "NAVEGANDO",
    "EXTRAINDO_DADOS",
    "BAIXANDO_CSV",
    "AGUARDANDO_PROXIMO_CICLO",
    "PAUSADO",
    "ERRO"
]

self.estado = "INICIANDO"
```

---

## 🖥️ Configuração de Display

### **Desenvolvimento (Local)**

```bash
# Usar display :1 (padrão)
export DISPLAY=:1
python src/processors/web/meu_processador.py
```

### **Produção (Múltiplos Processadores)**

```bash
# Processador 1 - Display :1, VNC 6080
DISPLAY=:1 python src/processors/web/processador1.py &

# Processador 2 - Display :2, VNC 6081
DISPLAY=:2 python src/processors/web/processador2.py &

# Processador 3 - Display :3, VNC 6082
DISPLAY=:3 python src/processors/web/processador3.py &
```

**Acesso VNC:**
```
http://3.148.126.73:6080/vnc.html  # Display :1
http://3.148.126.73:6081/vnc.html  # Display :2
http://3.148.126.73:6082/vnc.html  # Display :3
```

---

## 🧪 Testes

### **Teste 1: Modo Simulação (1 ciclo)**

```bash
source venv/bin/activate
export DISPLAY=:1
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION

python -c "from src.processors.web.meu_processador import processar_meu_processador; processar_meu_processador(modo_simulacao=True)"
```

### **Teste 2: Execução Normal**

```bash
python src/processors/web/meu_processador.py
```

### **Teste 3: Testar Pausar/Retomar**

Durante a execução, pressione:
- `P` - Pausar
- `R` - Retomar
- `Q` - Parar

---

## 🚀 Deploy

### **Opção 1: Execução Direta**

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
source venv/bin/activate
export DISPLAY=:1
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION

python src/processors/web/meu_processador.py
```

### **Opção 2: Script Helper**

Crie um script `run_meu_processador.sh`:

```bash
#!/bin/bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
source venv/bin/activate
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION
export DISPLAY=:1

python src/processors/web/meu_processador.py
```

Dê permissão e execute:

```bash
chmod +x run_meu_processador.sh
./run_meu_processador.sh
```

### **Opção 3: Systemd Service (24/7)**

Crie `/etc/systemd/system/meu-processador.service`:

```ini
[Unit]
Description=Processador Meu Nome - PROSPER ERP
After=network.target xvfb-display-1.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/PROSPER-ERP-AUTOMATION
Environment="DISPLAY=:1"
Environment="PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION"
ExecStart=/home/ubuntu/PROSPER-ERP-AUTOMATION/venv/bin/python src/processors/web/meu_processador.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Ativar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable meu-processador.service
sudo systemctl start meu-processador.service
sudo systemctl status meu-processador.service
```

---

## 📚 Recursos Adicionais

- [Fluxos de Processadores](fluxos_processadores/) - **Exemplos detalhados de fluxos**
- [Arquitetura do Sistema](ARQUITETURA.md)
- [Como Acessar VNC](ACESSO_VNC.md)
- [Sistema de Notificações](NOTIFICACOES.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Documentação Nodriver](https://github.com/ultrafunkamsterdam/nodriver)

---

## 💡 Dicas Finais

1. **Copie o template** e adapte gradualmente
2. **Teste em modo simulação** antes de rodar em loop
3. **Use VNC** para ver o que está acontecendo
4. **Monitore os logs** para detectar problemas
5. **Implemente retry** com backoff exponencial
6. **Envie notificações** em eventos críticos
7. **Documente** seletores CSS e lógica específica

---

**Última atualização:** 2025-10-25
**Versão:** 1.0
