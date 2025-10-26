# 📊 Fluxos de Processadores

Esta pasta contém a documentação detalhada dos fluxos de cada processador do sistema PROSPER-ERP-AUTOMATION.

---

## 📋 O Que São Fluxos de Processadores?

Cada arquivo nesta pasta documenta **passo a passo** como um processador específico funciona, incluindo:

- ✅ **URLs de destino**
- ✅ **Elementos HTML** (seletores CSS, IDs, nomes)
- ✅ **Sequência de ações** (clicar, digitar, aguardar)
- ✅ **Tratamento de erros**
- ✅ **Exemplos de código**
- ✅ **Checklist de implementação**

---

## 📚 Fluxos Disponíveis

### ✅ **Implementados**

| Processador | Arquivo | Fluxo | Status | Display | Frequência |
|-------------|---------|-------|--------|---------|------------|
| Relatório Operação Deságio | [relatorio_operacao_desagio.py](../../src/processors/web/relatorio_operacao_desagio.py) | [📄 Fluxo](relatorio_operacao_desagio.md) | ✅ **100% FUNCIONAL - PRODUÇÃO** | `:1` | **Loop contínuo (5s)** |

### 📋 **Documentados (Aguardando Implementação)**

| Processador | Arquivo de Fluxo | Status | Display | Frequência |
|-------------|------------------|--------|---------|------------|
| *(Nenhum no momento)* | - | - | - | - |

### ⏳ **Planejados**

| Processador | Descrição | Display Proposto |
|-------------|-----------|------------------|
| Títulos Vencidos | Extração de títulos vencidos | `:3` |
| Relatório de Cobrança | Relatório completo de cobranças | `:4` |
| Extrato Cliente | Extrato detalhado por cliente | `:5` |
| Posição Custódia | Posição de custódia de títulos | `:6` |

---

## 🎯 Como Usar Esta Documentação

### **1. Para Criar um Novo Processador:**

1. Leia o [Guia de Criação de Processadores](../CRIAR_PROCESSADOR.md)
2. Escolha um fluxo documentado nesta pasta
3. Use o fluxo como guia para implementação
4. Siga o template de código fornecido

### **2. Para Entender um Processador Existente:**

1. Abra o arquivo de fluxo correspondente
2. Leia a "Visão Geral" para contexto
3. Siga o "Fluxo Completo" passo a passo
4. Consulte o "Mapeamento de Elementos" para seletores CSS

### **3. Para Debugar um Problema:**

1. Identifique em qual etapa o erro ocorreu
2. Consulte a seção "Tratamento de Erros"
3. Verifique os seletores CSS no "Mapeamento de Elementos"
4. Use o VNC para ver a execução em tempo real

---

## 📝 Template de Fluxo

Todo fluxo de processador segue esta estrutura:

```markdown
# 📊 Fluxo: [Nome do Processador]

## 🎯 Visão Geral
- URL de destino
- Dados extraídos
- Pré-requisitos

## 🔄 Fluxo Completo
- ETAPA 1: Inicialização
- ETAPA 2: Login
- ETAPA 3: Navegação
- ETAPA 4: Extração
- ETAPA 5: Download

## 🗺️ Mapeamento de Elementos
- Tabela com seletores CSS
- IDs, names, valores

## 💻 Lógica de Código
- Estrutura da classe
- Métodos principais
- Exemplos

## ⚠️ Tratamento de Erros
- Possíveis erros
- Tratamentos
- Código de retry

## 📝 Exemplos de Código
- Código completo simplificado

## 🎯 Checklist de Implementação
- [ ] Tarefas a completar
```

---

## 🔧 Convenções

### **Nomenclatura de Arquivos**

- **Padrão:** `nome_do_processador.md`
- **Exemplo:** `relatorio_operacao_desagio.md`
- **Formato:** Snake case, minúsculas, sem espaços

### **Nomenclatura de Processadores Python**

- **Padrão:** `nome_do_processador.py`
- **Exemplo:** `relatorio_operacao_desagio.py`
- **Localização:** `src/processors/web/`

### **Display Virtual**

- **Display :1** → Processador principal (relatorios_operacoes.py)
- **Display :2** → Relatório de deságio
- **Display :3** → Títulos vencidos
- **Display :n** → Outros processadores

Cada processador roda em seu próprio display isolado!

---

## 🚀 Contribuindo com Novos Fluxos

### **Passo 1: Criar o Arquivo**

```bash
touch docs/fluxos_processadores/novo_processador.md
```

### **Passo 2: Seguir o Template**

Copie a estrutura do template acima.

### **Passo 3: Documentar Detalhadamente**

- URLs completas
- Seletores CSS testados
- Formato de dados
- Exemplos de código

### **Passo 4: Atualizar Este README**

Adicione o novo fluxo na tabela "Documentados".

---

## 📖 Recursos Relacionados

- [Guia de Criação de Processadores](../CRIAR_PROCESSADOR.md)
- [Arquitetura do Sistema](../ARQUITETURA.md)
- [Acesso VNC](../ACESSO_VNC.md)
- [Troubleshooting](../TROUBLESHOOTING.md)

---

## 📞 Suporte

**Dúvidas sobre fluxos?**

1. Consulte o fluxo específico
2. Leia o [Guia de Criação](../CRIAR_PROCESSADOR.md)
3. Use o VNC para ver a execução
4. Entre em contato com a equipe de TI

---

**Última atualização:** 2025-10-26
**Fluxos documentados:** 2
**Fluxos implementados:** 1 (100% funcional)
