# Guia Rápido: Usando Database em Processadores

Este guia mostra como usar o módulo `database.py` (versão simplificada) nos seus processadores.

---

## 🎯 Filosofia do Módulo

**Versão Simplificada** - Otimizada para processadores one-shot:
- ✅ **80 linhas** (vs 400 da versão complexa)
- ✅ **3 funções** principais: `query()`, `execute()`, `query_to_dataframe()`
- ✅ **Context manager** - abre/fecha conexão automaticamente
- ✅ **Sem pool** - cada processador cria sua própria conexão
- ✅ **SSL obrigatório** - Azure requirement
- ✅ **Parâmetros seguros** - previne SQL injection

---

## 📦 Importação

```python
from src.common.database import query, execute, query_to_dataframe
```

---

## 🔍 Uso Básico: SELECT (query)

### Query Simples

```python
from src.common.database import query

# Buscar todos os clientes ativos
clientes = query("SELECT * FROM clientes WHERE ativo = true")

# Iterar sobre resultados (lista de dicionários)
for cliente in clientes:
    print(f"ID: {cliente['id']}")
    print(f"Nome: {cliente['nome']}")
    print(f"CNPJ: {cliente['cnpj']}")
```

### Query com Parâmetros (SEMPRE use parâmetros!)

```python
# ✅ CORRETO - usa parâmetros (previne SQL injection)
cliente_id = 123
cliente = query(
    "SELECT * FROM clientes WHERE id = :id",
    {"id": cliente_id}
)

# ❌ ERRADO - NUNCA concatene strings (vulnerável a SQL injection)
# cliente = query(f"SELECT * FROM clientes WHERE id = {cliente_id}")  # NÃO FAÇA ISSO!
```

### Múltiplos Parâmetros

```python
# Buscar com múltiplos filtros
dados = query("""
    SELECT *
    FROM vendas
    WHERE data >= :data_inicio
      AND data <= :data_fim
      AND cliente_id = :cliente_id
      AND status = :status
""", {
    "data_inicio": "2025-01-01",
    "data_fim": "2025-12-31",
    "cliente_id": 123,
    "status": "ativo"
})
```

### Query com JOIN

```python
# Query complexa com JOIN
resultado = query("""
    SELECT
        c.id,
        c.nome as cliente_nome,
        v.data,
        v.valor
    FROM clientes c
    INNER JOIN vendas v ON v.cliente_id = c.id
    WHERE c.ativo = :ativo
      AND v.data >= :data_inicio
    ORDER BY v.data DESC
    LIMIT :limite
""", {
    "ativo": True,
    "data_inicio": "2025-01-01",
    "limite": 100
})
```

---

## ✏️ Uso Básico: INSERT/UPDATE/DELETE (execute)

### INSERT

```python
from src.common.database import execute

# Inserir registro simples
rows = execute("""
    INSERT INTO logs_processamento
    (processador, status, mensagem, data_execucao)
    VALUES
    (:processador, :status, :mensagem, NOW())
""", {
    "processador": "relatorio_desagio",
    "status": "sucesso",
    "mensagem": "Extração concluída com sucesso"
})

print(f"✅ {rows} linha(s) inserida(s)")
```

### UPDATE

```python
# Atualizar registros
rows = execute("""
    UPDATE clientes
    SET
        ultima_atualizacao = NOW(),
        status = :status
    WHERE id = :id
""", {
    "status": "processado",
    "id": 123
})

print(f"✅ {rows} linha(s) atualizada(s)")
```

### DELETE

```python
# Deletar registros antigos
rows = execute("""
    DELETE FROM logs_processamento
    WHERE data_execucao < NOW() - INTERVAL '30 days'
""")

print(f"🗑️ {rows} linha(s) deletada(s)")
```

---

## 📊 Uso com Pandas

```python
from src.common.database import query_to_dataframe
import pandas as pd

# Query diretamente para DataFrame
df = query_to_dataframe("""
    SELECT
        data,
        cliente_id,
        valor,
        status
    FROM vendas
    WHERE data >= :data_inicio
""", {
    "data_inicio": "2025-01-01"
})

# Usar funcionalidades do Pandas
print(df.head())
print(df.describe())
print(df.groupby("status")["valor"].sum())

# Salvar CSV
df.to_csv("vendas_2025.csv", index=False)
```

---

## 🏗️ Exemplo: Processador Completo

```python
#!/usr/bin/env python3
"""
Processador que busca clientes no banco e processa cada um.
"""
import asyncio
from src.common.database import query, execute
from src.common.execution_logger import ExecutionLogger

class ProcessadorComDatabase:
    def __init__(self):
        self.logger = ExecutionLogger("processador_db", "logs")

    def buscar_clientes_pendentes(self):
        """Busca clientes que precisam ser processados."""
        self.logger.log("🔍 Buscando clientes pendentes no banco...")

        clientes = query("""
            SELECT
                id,
                nome,
                cnpj,
                email
            FROM clientes
            WHERE ativo = true
              AND ultima_atualizacao < NOW() - INTERVAL '1 day'
            ORDER BY nome
        """)

        self.logger.log(f"✅ {len(clientes)} clientes encontrados")
        return clientes

    def registrar_processamento(self, cliente_id: int, status: str, mensagem: str = ""):
        """Registra resultado do processamento no banco."""
        try:
            execute("""
                INSERT INTO historico_processamento
                (processador, cliente_id, status, mensagem, data)
                VALUES
                (:processador, :cliente_id, :status, :mensagem, NOW())
            """, {
                "processador": "processador_db",
                "cliente_id": cliente_id,
                "status": status,
                "mensagem": mensagem
            })

            self.logger.log(f"📝 Processamento registrado: {status}")

        except Exception as e:
            self.logger.log(f"⚠️ Erro ao registrar: {e}")

    def atualizar_cliente(self, cliente_id: int):
        """Atualiza timestamp de última atualização."""
        execute("""
            UPDATE clientes
            SET ultima_atualizacao = NOW()
            WHERE id = :id
        """, {"id": cliente_id})

    async def processar_cliente(self, cliente):
        """Processa um cliente específico."""
        cliente_id = cliente["id"]
        cliente_nome = cliente["nome"]

        self.logger.log(f"📋 Processando: {cliente_nome}")

        try:
            # ... sua lógica de scraping/processamento aqui ...

            # Sucesso - atualizar banco
            self.atualizar_cliente(cliente_id)
            self.registrar_processamento(cliente_id, "sucesso", "Processado com sucesso")

            self.logger.log(f"✅ {cliente_nome} processado")

        except Exception as e:
            # Erro - registrar no banco
            self.registrar_processamento(cliente_id, "erro", str(e))
            self.logger.log(f"❌ Erro ao processar {cliente_nome}: {e}")

    async def executar(self):
        """Fluxo principal."""
        # 1. Buscar clientes do banco
        clientes = self.buscar_clientes_pendentes()

        if not clientes:
            self.logger.log("ℹ️ Nenhum cliente pendente")
            return

        # 2. Processar cada cliente
        for idx, cliente in enumerate(clientes, 1):
            self.logger.log(f"📍 Cliente {idx}/{len(clientes)}")
            await self.processar_cliente(cliente)

        self.logger.log("✅ Processamento concluído")


# Main
async def main():
    processador = ProcessadorComDatabase()
    await processador.executar()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📝 Padrões Comuns

### 1. Verificar se Registro Existe

```python
# Verificar se cliente já foi processado hoje
resultado = query("""
    SELECT COUNT(*) as total
    FROM historico_processamento
    WHERE cliente_id = :cliente_id
      AND data::date = CURRENT_DATE
      AND status = 'sucesso'
""", {"cliente_id": 123})

ja_processado = resultado[0]["total"] > 0

if ja_processado:
    print("Cliente já processado hoje")
```

### 2. Buscar Último Registro

```python
# Buscar última execução do processador
ultima = query("""
    SELECT *
    FROM historico_processamento
    WHERE processador = :processador
    ORDER BY data DESC
    LIMIT 1
""", {"processador": "meu_processador"})

if ultima:
    print(f"Última execução: {ultima[0]['data']}")
    print(f"Status: {ultima[0]['status']}")
```

### 3. Contar Registros por Categoria

```python
# Estatísticas de processamento
stats = query("""
    SELECT
        status,
        COUNT(*) as total,
        MAX(data) as ultima_ocorrencia
    FROM historico_processamento
    WHERE processador = :processador
      AND data >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY status
    ORDER BY total DESC
""", {"processador": "meu_processador"})

for stat in stats:
    print(f"{stat['status']}: {stat['total']} ocorrências")
```

### 4. Processar em Lotes (Batching)

```python
# Processar 50 clientes por vez
BATCH_SIZE = 50
offset = 0

while True:
    clientes = query("""
        SELECT *
        FROM clientes
        WHERE ativo = true
        ORDER BY id
        LIMIT :limit
        OFFSET :offset
    """, {
        "limit": BATCH_SIZE,
        "offset": offset
    })

    if not clientes:
        break  # Terminou

    # Processar lote
    for cliente in clientes:
        processar(cliente)

    offset += BATCH_SIZE
```

---

## ⚠️ Tratamento de Erros

```python
from src.common.database import query, execute

def buscar_dados_seguro():
    """Busca dados com tratamento de erros."""
    try:
        dados = query("SELECT * FROM tabela_que_pode_nao_existir")
        return dados

    except Exception as e:
        print(f"❌ Erro ao buscar dados: {e}")

        # Retornar lista vazia ou valor padrão
        return []

def inserir_com_retry():
    """Tenta inserir até 3 vezes."""
    for tentativa in range(3):
        try:
            rows = execute("""
                INSERT INTO logs (mensagem) VALUES (:msg)
            """, {"msg": "teste"})

            print(f"✅ Inserido com sucesso (tentativa {tentativa + 1})")
            return True

        except Exception as e:
            print(f"⚠️ Erro na tentativa {tentativa + 1}: {e}")

            if tentativa == 2:  # Última tentativa
                print("❌ Falhou após 3 tentativas")
                return False

            import time
            time.sleep(2)  # Aguardar antes de tentar novamente
```

---

## 🚫 O Que NÃO Fazer

### ❌ Concatenar Strings (SQL Injection)

```python
# ❌ PERIGOSO - Vulnerável a SQL injection
cliente_id = request.get("id")  # Vindo de input do usuário
query(f"SELECT * FROM clientes WHERE id = {cliente_id}")

# ✅ CORRETO - Sempre use parâmetros
query("SELECT * FROM clientes WHERE id = :id", {"id": cliente_id})
```

### ❌ Queries em Loop Intenso

```python
# ❌ INEFICIENTE - 1000 queries (N+1 problem)
clientes = query("SELECT id FROM clientes")
for cliente in clientes:
    vendas = query(
        "SELECT * FROM vendas WHERE cliente_id = :id",
        {"id": cliente["id"]}
    )

# ✅ EFICIENTE - 1 query com JOIN
resultado = query("""
    SELECT c.*, v.*
    FROM clientes c
    LEFT JOIN vendas v ON v.cliente_id = c.id
""")
```

### ❌ Não Fechar Conexões

```python
# ❌ Não precisa - context manager fecha automaticamente
# O módulo já usa 'with' internamente, você só chama query() ou execute()

# ✅ Você só faz:
dados = query("SELECT * FROM tabela")
# Conexão já foi fechada aqui
```

---

## 📊 Performance Tips

### 1. Use LIMIT para Queries Grandes

```python
# Limitar resultados
clientes = query("""
    SELECT * FROM clientes
    WHERE ativo = true
    ORDER BY nome
    LIMIT 100
""")
```

### 2. Crie Índices Adequados

```sql
-- No banco de dados (via SQL direto)
CREATE INDEX idx_clientes_ativo ON clientes(ativo);
CREATE INDEX idx_vendas_data ON vendas(data);
CREATE INDEX idx_historico_processador ON historico_processamento(processador, data);
```

### 3. SELECT Específico (não use SELECT *)

```python
# ❌ Busca todas as colunas (pode ser lento)
query("SELECT * FROM clientes")

# ✅ Busca apenas o necessário (mais rápido)
query("SELECT id, nome, email FROM clientes WHERE ativo = true")
```

---

## 🧪 Testando Queries

Use o Python interativo para testar:

```bash
# Abrir Python com ambiente do projeto
PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION venv/bin/python3

# No console Python:
>>> from src.common.database import query, execute
>>>
>>> # Testar query
>>> clientes = query("SELECT * FROM clientes LIMIT 5")
>>> print(len(clientes))
>>> print(clientes[0])
>>>
>>> # Testar insert
>>> rows = execute("INSERT INTO teste (col) VALUES (:val)", {"val": "teste"})
>>> print(f"{rows} linhas inseridas")
```

---

## 📚 Referências

- **Módulo:** `src/common/database.py` (355 linhas)
- **Dependências:** SQLAlchemy 2.0.36 + psycopg2-binary 2.9.10
- **Documentação SQLAlchemy:** https://docs.sqlalchemy.org/
- **PostgreSQL Docs:** https://www.postgresql.org/docs/

---

**Versão:** 2.0-simple
**Data:** 2025-11-10
**Autor:** Sistema de automação PROSPER
