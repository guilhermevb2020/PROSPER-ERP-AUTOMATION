# Comportamento de Erro no Processador: Envio Boleto Operação Oculto

## Visão Geral

Este documento descreve o comportamento do processador `envio_boleto_operacao_oculto.py` quando ocorre um erro durante o processamento de uma operação.

## Fluxo de Processamento

O processador trabalha com **grupos de operações** agrupadas por credenciais (login_smart + senha_smart). Para cada grupo:

1. Inicializa o browser
2. Faz login uma vez para todo o grupo
3. Navega para página de emissão
4. Processa cada operação do grupo sequencialmente
5. Fecha o browser após processar todo o grupo

## Comportamento Quando Há Erro

### 1. Erro Durante Processamento de uma Operação Individual

**Localização no código:** Linhas 1468-1534

#### Tentativas de Retry

Quando uma operação falha, o processador tenta **até 2 vezes** (1 tentativa inicial + 1 retry):

```python
tentativas_retry = 2  # Máximo de 2 tentativas
```

**Fluxo:**
1. **Primeira tentativa:** Executa `processar_operacao()`
2. **Se falhar:**
   - Aguarda 10 segundos
   - Tenta novamente (retry)
3. **Se retry também falhar:**
   - Operação é marcada como falhada
   - **NÃO interrompe o processamento das outras operações**

#### Ações Após Falha

Quando uma operação falha após todas as tentativas:

1. **Log do erro:**
   ```python
   self.logger_exec.log(f"⚠️ Pulando operação '{id_operacao}' devido ao erro: {erro_msg}")
   ```

2. **Screenshot de erro:**
   - Captura screenshot com nome `ERROR_operacao_{idx:03d}`

3. **Adiciona à lista de retry:**
   - Cria um objeto com informações da operação falhada:
     ```python
     operacao_falhada = {
         "id_operacao": operacao.get('id_operacao'),
         "conta_bancaria": operacao.get('conta_bancaria'),
         "login_smart": login_smart,
         "senha_smart": senha_smart,
         "erro": erro_msg,
         "tentativa": 1,
         "data_original": datetime.now().strftime("%Y-%m-%d")
     }
     ```
   - Adiciona à lista `operacoes_falhadas`

4. **Continua processamento:**
   - **NÃO para o processamento**
   - **NÃO fecha o browser**
   - Continua com a próxima operação do grupo
   - Se não for a última operação, aguarda 5 segundos antes de continuar

5. **Incrementa contador de erros:**
   ```python
   erros += 1
   ```

### 2. Erro Durante Processamento de um Grupo Inteiro

**Localização no código:** Linhas 1594-1633

Se ocorrer um erro que afeta todo o grupo (ex: erro de login, erro de navegação, erro de proxy):

#### Ações

1. **Log do erro:**
   ```python
   self.logger_exec.log(f"⚠️ Erro ao processar grupo '{login_smart}': {erro_msg}")
   ```

2. **Detecção de erro de proxy:**
   - Verifica se é erro de proxy/navegação:
     ```python
     erro_proxy = "ERR_HTTP_RESPONSE_CODE_FAILURE" in erro_msg or "net::ERR_" in erro_msg
     ```
   - Se for erro de proxy, loga dicas de diagnóstico

3. **Marca todas as operações do grupo como falhadas:**
   - Adiciona **todas** as operações do grupo à lista `operacoes_falhadas`
   - Conta todas como erros:
     ```python
     erros += len(operacoes_grupo)
     ```

4. **Fecha o browser:**
   - Tenta fechar o browser mesmo em caso de erro
   - Usa `try/except` para garantir que não trave se já estiver fechado

5. **Delay antes do próximo grupo:**
   - Se for erro de proxy: aguarda **30 segundos**
   - Caso contrário: aguarda **10 segundos**

6. **Continua processamento:**
   - **NÃO para a execução completa**
   - Continua com o próximo grupo de credenciais

### 3. Salvamento de Operações Falhadas

**Localização no código:** Linhas 1635-1663

Ao final do processamento de todos os grupos, se houver operações falhadas:

1. **Cria arquivo JSON:**
   - Diretório: `data/checkpoints/`
   - Nome: `envio_boleto_operacao_oculto_failed_{timestamp}.json`
   - Formato:
     ```json
     {
       "timestamp": "2025-01-15T10:30:00",
       "processador": "envio_boleto_operacao_oculto",
       "operacoes_falhadas": [
         {
           "id_operacao": 12345,
           "conta_bancaria": "Banco X",
           "login_smart": "usuario@email.com",
           "senha_smart": "senha123",
           "erro": "Mensagem do erro",
           "tentativa": 1,
           "data_original": "2025-01-15"
         }
       ]
     }
     ```

2. **Log do arquivo:**
   ```python
   self.logger_exec.log(f"📝 {len(operacoes_falhadas)} operação(ões) falhada(s) salva(s) em: {arquivo_retry}")
   ```

### 4. Resumo Final

**Localização no código:** Linhas 1665-1676

Ao final, o processador sempre exibe um resumo:

```
================================================================================
📊 RESUMO DA EXECUÇÃO
================================================================================
Total de operações: X
Grupos de credenciais: Y
✅ Sucessos: Z
❌ Erros: W
📝 Arquivo de retry: /caminho/para/arquivo.json
================================================================================
```

## Características Importantes

### ✅ O que o processador FAZ em caso de erro:

1. **Tenta retry automático** (até 2 tentativas por operação)
2. **Continua processamento** - não para por causa de uma operação falhada
3. **Salva operações falhadas** em arquivo JSON para retry posterior
4. **Registra logs detalhados** de cada erro
5. **Captura screenshots** de erros
6. **Fecha browser corretamente** mesmo em caso de erro
7. **Trata HTTP 429 automaticamente** via RateLimitHandler (não precisa retry manual)

### ❌ O que o processador NÃO faz:

1. **NÃO interrompe** o processamento de outras operações
2. **NÃO para** a execução completa por causa de erros
3. **NÃO tenta infinitamente** - máximo de 2 tentativas por operação
4. **NÃO reprocessa** operações falhadas na mesma execução (salva para retry posterior)

## Tratamento Especial de Erros

### HTTP 429 (Rate Limiting)

- **Tratado automaticamente** pelo `RateLimitHandler`
- Não precisa retry manual
- O handler monitora automaticamente e faz retry quando detecta HTTP 429
- Navega de volta para página de emissão automaticamente

### Erros de Proxy/Navegação

- Detectados automaticamente
- Loga dicas de diagnóstico
- Aguarda mais tempo (30s) antes de continuar
- Todas as operações do grupo são marcadas como falhadas

## Arquivo de Retry

As operações falhadas são salvas em `data/checkpoints/envio_boleto_operacao_oculto_failed_{timestamp}.json`.

Este arquivo pode ser processado posteriormente pelo processador `envio_boleto_operacao_oculto_retry.py` para tentar novamente as operações que falharam.

## Exemplo de Fluxo com Erros

```
1. Processa Operação 1 ✅ Sucesso
2. Processa Operação 2 ❌ Erro (tentativa 1)
   → Aguarda 10s
   → Tenta novamente ❌ Erro (tentativa 2)
   → Adiciona à lista de retry
   → Continua...
3. Processa Operação 3 ✅ Sucesso
4. Processa Operação 4 ❌ Erro (tentativa 1)
   → Aguarda 10s
   → Tenta novamente ✅ Sucesso
5. Processa Operação 5 ✅ Sucesso
...
Final: Salva arquivo JSON com Operação 2 falhada
```

## Conclusão

O processador é **resiliente a erros** e foi projetado para:

- **Continuar processando** mesmo quando algumas operações falham
- **Tentar recuperar** erros transitórios com retry automático
- **Registrar tudo** para análise posterior
- **Salvar falhas** para retry em execução separada

Isso garante que o máximo de operações possível seja processado, mesmo em ambientes instáveis ou com problemas temporários de rede/proxy.

