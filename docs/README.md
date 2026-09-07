[Validação do ERP após Guardian — 07/09/2026](VALIDACAO_ERP_2026-09-07.md)

# Documentação PROSPER-ERP-AUTOMATION

**Versão**: 2.1 (Score 9.5/10)
**Última atualização**: 2025-11-18
**Processadores Documentados**: 6/6 ✅

---

## 📚 Índice de Documentação

### 🚀 Início Rápido

- 📖 [README Principal](../README.md) - Visão geral do projeto
- ⚡ [Guia Rápido Anti-Bot](./GUIA_RAPIDO_ANTIBOT.md) - Referência rápida das melhorias

### 🔧 Configuração e Uso

- 🏗️ [Como Criar Processadores](./COMO_CRIAR_PROCESSADORES.md) - Guia completo para novos processadores
- 📁 [Estrutura de Pastas](./ESTRUTURA_DE_PASTAS.md) - Organização do projeto
- 💾 [Sistema de Backup](./SISTEMA_BACKUP.md) - Backups automáticos

### 🛡️ Anti-Bot e Segurança (NOVO - 2025-11-17)

- 📘 **[Melhorias Anti-Bot 2025](./MELHORIAS_ANTIBOT_2025.md)** ⭐ Principal
  - Documentação técnica completa
  - Todas as 7 melhorias implementadas
  - Guia de testes e troubleshooting
  - Rollback e roadmap futuro

- ⚡ **[Guia Rápido Anti-Bot](./GUIA_RAPIDO_ANTIBOT.md)** ⭐ Referência
  - Teste rápido (5 min)
  - Rollback em 1 comando
  - FAQ e checklist

### 📖 Guias Técnicos

- 🔍 [Exemplo de Processador com Database](./EXEMPLO_PROCESSADOR_DATABASE.md)
- 💾 [Exemplo de Uso do Database](./EXEMPLO_USO_DATABASE.md)
- ⏱️ [Wait Utils - Utilitários de Espera](./WAIT_UTILS.md)
- ⏱️ [Exemplo de Uso Wait Utils](./EXEMPLO_USO_WAIT_UTILS.md)

### 🎯 Processadores Específicos (6/6 Documentados ✅)

#### Extração de Relatórios
- 📊 [`relatorio_operacao_desagio`](./processors/PROCESSADOR_RELATORIO_OPERACAO_DESAGIO.md) (Score 9.5/10) ⭐
- 📋 [`relatorio_titulos_aberto`](./processors/PROCESSADOR_RELATORIO_TITULOS_ABERTO.md) (Nodriver, Loop) 🆕

#### Emissão de Boletos
- 📄 [`emissao_boleto_primeira_via`](./processors/PROCESSADOR_EMISSAO_BOLETO_PRIMEIRA_VIA.md) (Score 9.5/10, 62 contas) ⭐

#### Envio de Boletos
- 📧 [`envio_boleto_operacao_oculto`](./processors/PROCESSADOR_ENVIO_BOLETO_OPERACAO_OCULTO.md) (Login por operação)
- 📮 [`envio_boleto_operacao_padrao`](./processors/PROCESSADOR_ENVIO_BOLETO_OPERACAO_PADRAO.md) (Score 9.5/10) ⭐
- 🔄 [`envio_boleto_operacao_oculto_retry`](./processors/PROCESSADOR_ENVIO_BOLETO_OPERACAO_OCULTO_RETRY.md) (Sistema de retry) 🆕

### 🔄 Orquestração

- 🎭 [Sistema de Orquestração](./orchestracao.md) - Como coordenar múltiplos processadores

### 📦 Deprecated

- 📁 [Documentação Antiga](./deprecated/) - Documentos obsoletos (mantidos para referência)

---

## 🎯 Documentos por Função

### Para Desenvolvedores

1. 🏗️ [Como Criar Processadores](./COMO_CRIAR_PROCESSADORES.md)
2. 📁 [Estrutura de Pastas](./ESTRUTURA_DE_PASTAS.md)
3. 🔍 [Exemplo de Processador com Database](./EXEMPLO_PROCESSADOR_DATABASE.md)
4. 📘 [Melhorias Anti-Bot 2025](./MELHORIAS_ANTIBOT_2025.md)

### Para Operação

1. ⚡ [Guia Rápido Anti-Bot](./GUIA_RAPIDO_ANTIBOT.md)
2. 💾 [Sistema de Backup](./SISTEMA_BACKUP.md)
3. 🎭 [Sistema de Orquestração](./orchestracao.md)

### Para Troubleshooting

1. 📘 [Melhorias Anti-Bot 2025](./MELHORIAS_ANTIBOT_2025.md) - Seção "Troubleshooting"
2. ⚡ [Guia Rápido Anti-Bot](./GUIA_RAPIDO_ANTIBOT.md) - Seção "Problemas?"

---

## 🆕 Novidades (2025-11-17)

### ✨ v2.1 - Stealth Completo (Score 9.5/10)

**Score atualizado**: 8.5 → 9.5 (+12% robustez)

#### ✅ Processadores Atualizados (2025-11-17)

**Arquitetura**: Stealth Browser (3 camadas) + Proxy BrightData Sticky Session

| Processador | Score Anterior | Score Atual | Melhoria |
|-------------|----------------|-------------|----------|
| `relatorio_operacao_desagio` | 4.0/10 | 9.5/10 | +137% |
| `emissao_boleto_primeira_via` | 8.0/10 | 9.5/10 | +19% |
| `envio_boleto_operacao_padrao` | 9.0/10 | 9.5/10 | +6% |

#### 🔧 Melhorias Implementadas

1. ✅ **Stealth Browser Architecture** (3 camadas: browser → context → page)
2. ✅ **Proxy BrightData Sticky Session** (IP consistente durante sessão)
3. ✅ **Retry Adaptativo** (3s, 6s, 9s progressivo)
4. ✅ **Fingerprinting Determinístico** (Canvas, WebGL, Audio)
5. ✅ **RateLimitHandler Automático** (HTTP 429 detection)

**Documentação**:
- 📘 [Melhorias Anti-Bot 2025](./MELHORIAS_ANTIBOT_2025.md)
- ⚡ [Guia Rápido Anti-Bot](./GUIA_RAPIDO_ANTIBOT.md)

---

## 📊 Estatísticas do Projeto

### Linhas de Código
```
src/common/          ~8.500 linhas
src/processors/      ~12.000 linhas
tests/               ~2.000 linhas
docs/                ~6.000 linhas
TOTAL:               ~28.500 linhas
```

### Módulos Principais
```
Anti-Detection:      9 módulos
Fingerprinting:      7 módulos (1 novo: Font)
Processadores:       5 ativos
Testes:             15+ suítes
```

### Score Anti-Bot
```
Canvas:             9.5/10 ✅ (determinístico)
WebGL:              9.5/10 ✅ (determinístico)
Audio:              9.5/10 ✅ (determinístico)
Navigator:          9.5/10 ✅
Fingerprinting:     9.5/10 ✅
Headers:            9.5/10 ✅
Stealth:            9.5/10 ✅ (3-layer architecture)
Proxy:              9.5/10 ✅ (BrightData sticky session)
TOTAL:              9.5/10 ✅ (era 8.5/10)
```

---

## 🗺️ Roadmap Futuro

### Fase 2 - Anti-Bot Avançado (Quando necessário)

1. **CDP Detection Mitigation** (Prioridade Máxima)
   - Persistent Context (1 dia)
   - Ou migrar para Nodriver (1-2 semanas)

2. **TLS Fingerprinting** (Prioridade Alta)
   - Integrar curl_cffi (2-3 dias)

3. **HTTP/2 Fingerprinting** (Prioridade Média)
   - Complemento do TLS (incluído)

**Gatilho**: Quando/se SmartSecurities adicionar Cloudflare ou taxa de sucesso < 70%

---

## 📞 Suporte

### Encontrou um problema?

1. 📘 Consulte [Troubleshooting](./MELHORIAS_ANTIBOT_2025.md#troubleshooting)
2. ⚡ Veja [FAQ](./GUIA_RAPIDO_ANTIBOT.md#faq)
3. 🔄 Execute [Rollback](./GUIA_RAPIDO_ANTIBOT.md#rollback) se necessário

### Reportar Bug

```bash
# 1. Capturar logs
tail -100 logs/*.log > bug_report.log

# 2. Incluir informações:
# - Processador afetado
# - Erro específico
# - Taxa de sucesso atual
# - Se fez rollback ou não
```

---

## 🔗 Links Úteis

- 🌐 [Playwright Documentation](https://playwright.dev/python/)
- 🔍 [BrowserLeaks - Teste Fingerprinting](https://browserleaks.com/)
- 📊 [Pixelscan - Bot Detection Test](https://pixelscan.net/)

---

**Última atualização**: 2025-11-18 | **Versão**: 2.1 (Score 9.5/10) | **Processadores Documentados**: 6/6 ✅

- [Auditoria de credenciais e padrão Guardian — 07/09/2026](AUDITORIA_CREDENCIAIS_2026-09-07.md)
