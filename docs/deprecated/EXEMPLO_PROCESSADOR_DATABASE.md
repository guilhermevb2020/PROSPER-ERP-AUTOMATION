# Exemplo de Processador com Banco de Dados

Este documento demonstra como criar um processador que extrai dados do banco de dados Azure PostgreSQL.

## Cenário de Exemplo

Processador que:
1. Consulta dados no banco de dados PostgreSQL
2. Faz login em um sistema web
3. Preenche formulário com dados do banco
4. Baixa relatório gerado

---

## Código Completo do Exemplo

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Processador de Exemplo com Banco de Dados
==========================================

Demonstra integração entre:
- Consulta ao banco de dados (Azure PostgreSQL)
- Automação web (Playwright)
- Sistema de configuração e credenciais

Fluxo:
1. Conectar ao banco de dados
2. Buscar lista de clientes ativos
3. Para cada cliente:
   - Login no sistema web
   - Gerar relatório específico
   - Download do arquivo
"""

import asyncio
import os
from datetime import datetime
from typing import List, Dict, Any

from playwright.async_api import async_playwright, Page, Browser

# Módulos do projeto
from src.common.database import get_db_engine, query_db
from src.common.execution_logger import ExecutionLogger
from src.common.screenshot_manager import ScreenshotManager
from src.common.playwright_captcha_manager import PlaywrightCaptchaManager
from src.common.config_loader import get_config_loader
from src.common.file_rename import aguardar_download_e_renomear

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

PROCESSOR_NAME = "exemplo_database"
DEBUG = os.getenv("DEBUG_MODE", "false").lower() == "true"
SERVER_IP = os.getenv("SERVER_IP", "localhost")


# =============================================================================
# CLASSE PRINCIPAL
# =============================================================================

class ProcessadorExemploDatabase:
    """
    Processador que consulta banco de dados e realiza automação web.
    """

    def __init__(self):
        """Inicializa o processador."""
        self.nome = PROCESSOR_NAME

        # Logger de execução
        self.logger_exec = ExecutionLogger(
            processador=self.nome,
            diretorio_logs="logs"
        )

        # Gerenciador de screenshots
        self.screenshot_manager = ScreenshotManager(
            processador=self.nome,
            base_dir="data/screenshots"
        )

        # Playwright
        self.playwright = None
        self.browser: Browser = None
        self.page: Page = None

        # Gerenciador de CAPTCHA
        self.captcha_manager = None

        # Configuração
        self.config_loader = get_config_loader()
        self.processor_config = self.config_loader.get_processor_config(self.nome)

        # Credenciais
        credential = self.config_loader.get_credentials(self.nome)
        if credential:
            self.email = credential.usuario
            self.senha = credential.senha
            self.logger_exec.log(f"✅ Credenciais carregadas: {credential.usuario}")
        else:
            raise ValueError(f"Nenhuma credencial configurada para {self.nome}")

        # Diretório de download
        self.download_dir = os.path.abspath("data/raw_inputs")
        os.makedirs(self.download_dir, exist_ok=True)

        self.logger_exec.log(f"🚀 Processador '{self.nome}' inicializado")
        self.logger_exec.log(f"📂 Diretório de download: {self.download_dir}")

    # =========================================================================
    # CONSULTAS AO BANCO DE DADOS
    # =========================================================================

    def buscar_clientes_ativos(self) -> List[Dict[str, Any]]:
        """
        Busca clientes ativos no banco de dados.

        Returns:
            List[Dict]: Lista de clientes com id, nome, cnpj
        """
        self.logger_exec.log("🔍 Consultando clientes ativos no banco de dados...")

        try:
            # Query de exemplo (ajustar para sua tabela real)
            sql = """
                SELECT
                    id,
                    nome,
                    cnpj,
                    email
                FROM
                    clientes
                WHERE
                    ativo = true
                ORDER BY
                    nome
            """

            clientes = query_db(sql)

            self.logger_exec.log(f"✅ {len(clientes)} clientes encontrados")

            return clientes

        except Exception as e:
            self.logger_exec.log(f"❌ Erro ao consultar banco de dados: {e}")
            raise

    def buscar_parametros_relatorio(self, cliente_id: int) -> Dict[str, Any]:
        """
        Busca parâmetros específicos do cliente para gerar relatório.

        Args:
            cliente_id (int): ID do cliente

        Returns:
            Dict: Parâmetros do relatório
        """
        sql = """
            SELECT
                tipo_relatorio,
                data_inicio,
                data_fim,
                categorias
            FROM
                parametros_relatorio
            WHERE
                cliente_id = :cliente_id
                AND ativo = true
            LIMIT 1
        """

        parametros = query_db(sql, {"cliente_id": cliente_id})

        if not parametros:
            # Usar valores padrão se não houver parametros
            return {
                "tipo_relatorio": "completo",
                "data_inicio": datetime.now().strftime("%Y-%m-01"),
                "data_fim": datetime.now().strftime("%Y-%m-%d"),
                "categorias": "todas"
            }

        return parametros[0]

    def registrar_execucao(self, cliente_id: int, status: str, mensagem: str = ""):
        """
        Registra resultado da execução no banco de dados.

        Args:
            cliente_id (int): ID do cliente
            status (str): Status da execução (sucesso, erro, pendente)
            mensagem (str): Mensagem de log
        """
        from src.common.database import execute_db

        sql = """
            INSERT INTO historico_execucoes
            (processador, cliente_id, status, mensagem, data_execucao)
            VALUES
            (:processador, :cliente_id, :status, :mensagem, NOW())
        """

        try:
            execute_db(sql, {
                "processador": self.nome,
                "cliente_id": cliente_id,
                "status": status,
                "mensagem": mensagem
            })

            self.logger_exec.log(f"📝 Execução registrada no banco: {status}")

        except Exception as e:
            self.logger_exec.log(f"⚠️ Erro ao registrar execução: {e}")
            # Não falhar se registro falhar (não é crítico)

    # =========================================================================
    # AUTOMAÇÃO WEB
    # =========================================================================

    async def inicializar_browser(self):
        """Inicializa Playwright e browser."""
        self.logger_exec.log("🌐 Inicializando browser Playwright...")

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )

        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            accept_downloads=True
        )

        self.page = await context.new_page()

        # Inicializar gerenciador de CAPTCHA
        self.captcha_manager = PlaywrightCaptchaManager(
            page=self.page,
            logger_exec=self.logger_exec,
            screenshot_manager=self.screenshot_manager
        )

        self.logger_exec.log("✅ Browser Playwright inicializado")

    async def fazer_login(self):
        """Realiza login no sistema."""
        self.logger_exec.log("🔐 Realizando login...")

        # Navegar para página de login
        await self.page.goto("https://exemplo.com.br/login")
        await self.screenshot_manager.capturar(self.page, "01_login_page")

        # Preencher credenciais
        await self.page.fill("#email", self.email)
        await self.page.fill("#senha", self.senha)

        # Resolver CAPTCHA se houver
        site_key = "6Le-exemplo-site-key"
        await self.captcha_manager.resolver_recaptcha_v2(site_key)

        # Submeter formulário
        await self.page.click("button[type='submit']")
        await self.page.wait_for_load_state("networkidle")

        await self.screenshot_manager.capturar(self.page, "02_login_success")
        self.logger_exec.log("✅ Login realizado com sucesso")

    async def gerar_relatorio_cliente(self, cliente: Dict[str, Any]):
        """
        Gera relatório específico de um cliente.

        Args:
            cliente (Dict): Dados do cliente do banco de dados
        """
        cliente_id = cliente["id"]
        cliente_nome = cliente["nome"]

        self.logger_exec.log(f"📊 Gerando relatório para: {cliente_nome}")

        try:
            # Buscar parâmetros do relatório no banco
            parametros = self.buscar_parametros_relatorio(cliente_id)

            # Navegar para página de relatórios
            await self.page.goto("https://exemplo.com.br/relatorios")

            # Preencher formulário com dados do banco
            await self.page.select_option("#tipo_relatorio", parametros["tipo_relatorio"])
            await self.page.fill("#data_inicio", parametros["data_inicio"])
            await self.page.fill("#data_fim", parametros["data_fim"])
            await self.page.fill("#cnpj_cliente", cliente["cnpj"])

            await self.screenshot_manager.capturar(self.page, f"03_form_{cliente_id}")

            # Gerar relatório
            await self.page.click("#btn_gerar")
            await self.page.wait_for_load_state("networkidle")

            # Download
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            novo_nome = f"relatorio_{cliente_nome.replace(' ', '_')}_{timestamp}.pdf"

            arquivo_baixado = await aguardar_download_e_renomear(
                download_dir=self.download_dir,
                novo_nome=novo_nome,
                timeout=60
            )

            self.logger_exec.log(f"✅ Relatório gerado: {arquivo_baixado}")

            # Registrar sucesso no banco
            self.registrar_execucao(cliente_id, "sucesso", f"Arquivo: {novo_nome}")

        except Exception as e:
            self.logger_exec.log(f"❌ Erro ao gerar relatório para {cliente_nome}: {e}")
            # Registrar erro no banco
            self.registrar_execucao(cliente_id, "erro", str(e))
            raise

    # =========================================================================
    # FLUXO PRINCIPAL
    # =========================================================================

    async def executar_extracao_completa(self):
        """Executa fluxo completo de extração."""
        try:
            # 1. Consultar banco de dados
            clientes = self.buscar_clientes_ativos()

            if not clientes:
                self.logger_exec.log("⚠️ Nenhum cliente ativo encontrado")
                return

            # 2. Inicializar browser
            await self.inicializar_browser()

            # 3. Fazer login
            await self.fazer_login()

            # 4. Processar cada cliente
            for idx, cliente in enumerate(clientes, 1):
                self.logger_exec.log(f"📍 Cliente {idx}/{len(clientes)}: {cliente['nome']}")

                try:
                    await self.gerar_relatorio_cliente(cliente)
                except Exception as e:
                    self.logger_exec.log(f"⚠️ Pulando cliente devido ao erro: {e}")
                    continue

            self.logger_exec.log("✅ Extração concluída para todos os clientes")

        finally:
            # Fechar browser
            if self.browser:
                await self.browser.close()
                self.logger_exec.log("🔒 Browser fechado")

            if self.playwright:
                await self.playwright.stop()


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Função principal."""
    processador = ProcessadorExemploDatabase()

    try:
        await processador.executar_extracao_completa()

        if DEBUG:
            print("🔧 MODO DEBUG ATIVO")
            print(f"   Acesse: http://{SERVER_IP}:6080/vnc.html")
            while True:
                await asyncio.sleep(10)
        else:
            print("✅ EXTRAÇÃO CONCLUÍDA COM SUCESSO!")

    except Exception as e:
        print(f"❌ ERRO CRÍTICO: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Uso das Funções de Banco de Dados

### 1. Query Simples (SELECT)

```python
from src.common.database import query_db

# Query básica
clientes = query_db("SELECT * FROM clientes WHERE ativo = true")

# Query com parâmetros
cliente = query_db(
    "SELECT * FROM clientes WHERE id = :id",
    {"id": 123}
)

# Acessar resultados (lista de dicts)
for c in clientes:
    print(f"ID: {c['id']}, Nome: {c['nome']}")
```

### 2. Query com Pandas

```python
from src.common.database import get_db_engine
import pandas as pd

engine = get_db_engine()

# Ler diretamente para DataFrame
df = pd.read_sql("SELECT * FROM clientes", engine)

# Query parametrizada com Pandas
df = pd.read_sql(
    "SELECT * FROM vendas WHERE data >= :data_inicio",
    engine,
    params={"data_inicio": "2025-01-01"}
)

# Salvar DataFrame no banco
df.to_sql("nova_tabela", engine, if_exists="replace", index=False)
```

### 3. INSERT/UPDATE/DELETE

```python
from src.common.database import execute_db

# INSERT
rows = execute_db(
    "INSERT INTO log_processamento (processador, status) VALUES (:proc, :status)",
    {"proc": "exemplo", "status": "sucesso"}
)
print(f"{rows} linha(s) inserida(s)")

# UPDATE
rows = execute_db(
    "UPDATE clientes SET ativo = false WHERE id = :id",
    {"id": 123}
)

# DELETE
rows = execute_db(
    "DELETE FROM temp_data WHERE data < :data_limite",
    {"data_limite": "2024-01-01"}
)
```

### 4. Transações (Múltiplas Operações)

```python
from src.common.database import db_transaction
from sqlalchemy import text

# Context manager com commit/rollback automático
with db_transaction() as conn:
    # Inserir registro
    conn.execute(
        text("INSERT INTO pedidos (cliente_id, total) VALUES (:cliente, :total)"),
        {"cliente": 123, "total": 100.50}
    )

    # Atualizar saldo
    conn.execute(
        text("UPDATE clientes SET saldo = saldo - :valor WHERE id = :id"),
        {"valor": 100.50, "id": 123}
    )

    # Se chegar aqui, faz commit automático
    # Se houver exception, faz rollback automático
```

---

## Configuração no processors.yaml

```yaml
exemplo_database:
  display: ":1"
  api_port: 6093
  interval_seconds: 3600
  cron: "0 6 * * *"  # Todo dia às 6h da manhã
  login_policy: round_robin
  timeout_captcha: 100
  timeout_download: 300
```

---

## Configuração no credentials.csv

```csv
processador,cliente,usuario,senha,ativo
exemplo_database,prosper,usuario@exemplo.com,SenhaTeste123,true
```

---

## Checklist de Implementação

- [ ] Criar tabelas necessárias no banco de dados
- [ ] Adicionar configuração em `config/processors.yaml`
- [ ] Adicionar credenciais em `config/credentials.csv`
- [ ] Testar conexão com banco: `python3 -m src.common.database`
- [ ] Implementar queries específicas
- [ ] Testar processador em modo DEBUG
- [ ] Validar registros no banco após execução
- [ ] Agendar no cron

---

## Exemplos de Queries Úteis

### Buscar Últimas Execuções

```python
historico = query_db("""
    SELECT
        cliente_id,
        status,
        mensagem,
        data_execucao
    FROM historico_execucoes
    WHERE processador = :proc
    ORDER BY data_execucao DESC
    LIMIT 10
""", {"proc": "exemplo_database"})
```

### Contar Execuções por Status

```python
stats = query_db("""
    SELECT
        status,
        COUNT(*) as total
    FROM historico_execucoes
    WHERE processador = :proc
        AND data_execucao >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY status
""", {"proc": "exemplo_database"})
```

### Buscar Clientes com Erro Recorrente

```python
problematicos = query_db("""
    SELECT
        cliente_id,
        COUNT(*) as erros_consecutivos
    FROM historico_execucoes
    WHERE processador = :proc
        AND status = 'erro'
        AND data_execucao >= CURRENT_DATE - INTERVAL '3 days'
    GROUP BY cliente_id
    HAVING COUNT(*) >= 3
""", {"proc": "exemplo_database"})
```

---

## Notas Importantes

1. **Connection Pooling**: O módulo usa pool de conexões - não precisa abrir/fechar manualmente
2. **Parâmetros**: SEMPRE use parâmetros (`:param`) ao invés de concatenar strings (previne SQL injection)
3. **Transactions**: Use `db_transaction()` quando precisar garantir atomicidade de múltiplas operações
4. **Pandas Integration**: `pd.read_sql()` funciona diretamente com a engine
5. **Timeout Azure**: Conexões são recicladas a cada 1h para evitar timeout do Azure
6. **Testing**: Execute `python3 -m src.common.database` para testar conexão

---

## Performance Tips

### Use índices adequados:
```sql
CREATE INDEX idx_clientes_ativo ON clientes(ativo);
CREATE INDEX idx_historico_data ON historico_execucoes(data_execucao);
```

### Limite resultados grandes:
```python
# Bom: processar em lotes
BATCH_SIZE = 100
offset = 0
while True:
    clientes = query_db(
        "SELECT * FROM clientes LIMIT :limit OFFSET :offset",
        {"limit": BATCH_SIZE, "offset": offset}
    )
    if not clientes:
        break

    # Processar lote
    for cliente in clientes:
        processar(cliente)

    offset += BATCH_SIZE
```

### Use SELECT específico:
```python
# Ruim
query_db("SELECT * FROM clientes")

# Bom (mais rápido, menos memória)
query_db("SELECT id, nome, cnpj FROM clientes WHERE ativo = true")
```

---

**Última atualização:** 2025-11-10
**Módulo:** `src/common/database.py` v2.0
