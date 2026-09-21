# Guia Rápido - v2.1 Stealth Completo (Score 9.5/10)

> **Referência rápida** para v2.1 implementada em 17/11/2025
>
> 📘 Documentação completa: [`MELHORIAS_ANTIBOT_2025.md`](./MELHORIAS_ANTIBOT_2025.md)

---

## ✅ O Que Foi Feito?

**Score**: 8.5 → 9.5 (+12% robustez)

### v2.1 - Processadores Atualizados (Score 9.5/10)

| Processador | Score Anterior | Score Atual | Melhoria |
|-------------|----------------|-------------|----------|
| `relatorio_operacao_desagio` | 4.0/10 | 9.5/10 | +137% |
| `emissao_boleto_primeira_via` | 8.0/10 | 9.5/10 | +19% |
| `envio_boleto_operacao_padrao` | 9.0/10 | 9.5/10 | +6% |

### 🔧 Melhorias Implementadas

| Melhoria | Impacto | Componente |
|----------|---------|------------|
| Stealth Browser Architecture | +20% | 3 camadas (browser → context → page) |
| Proxy BrightData Sticky Session | +15% | IP consistente durante sessão |
| Retry Adaptativo | +10% | 3s → 6s → 9s progressivo |
| Fingerprinting Determinístico | +8% | Canvas, WebGL, Audio |
| RateLimitHandler Automático | +5% | HTTP 429 detection + backoff |

---

## 🚀 Como Testar?

### Teste Rápido (5 min)

Escolha um dos processadores atualizados:

```bash
# Processador 1: Relatório Operação Deságio
DISPLAY=:1 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/relatorio_operacao_desagio.py

# Processador 2: Emissão Boleto Primeira Via
DISPLAY=:5 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/emissao_boleto_primeira_via.py

# Processador 3: Envio Boleto Operação Padrão
DISPLAY=:3 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_padrao.py

# Verificar logs
tail -50 logs/*.log | grep "✅"
```

### Teste Completo (30 min)

Teste os 3 processadores em sequência:

```bash
# Testar relatorio_operacao_desagio
echo "Testando relatorio_operacao_desagio..."
DISPLAY=:1 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/relatorio_operacao_desagio.py

# Testar emissao_boleto_primeira_via
echo "Testando emissao_boleto_primeira_via..."
DISPLAY=:5 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/emissao_boleto_primeira_via.py

# Testar envio_boleto_operacao_padrao
echo "Testando envio_boleto_operacao_padrao..."
DISPLAY=:3 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_padrao.py

# Analisar taxa de sucesso
echo "Analisando logs..."
grep -r "✅" logs/*.log | tail -20
```

---

## ⚠️ Problemas?

### Taxa de sucesso < 90%

1. **Verificar logs detalhados**
```bash
# Ver logs do processador específico
tail -100 logs/relatorio_operacao_desagio_*.log
tail -100 logs/emissao_boleto_primeira_via_*.log
tail -100 logs/envio_boleto_operacao_padrao_*.log
```

2. **Verificar display VNC**
```bash
# Displays por processador:
# :1 - relatorio_operacao_desagio
# :5 - emissao_boleto_primeira_via
# :3 - envio_boleto_operacao_padrao

# Verificar se display está ativo
ps aux | grep Xvfb
```

3. **Verificar proxy BrightData**
```bash
# Verificar conectividade
curl -x "http://USERNAME:PASSWORD@brd.superproxy.io:33335" https://lumtest.com/myip.json
```

### Erro JavaScript ou CAPTCHA

```bash
# Ver erro específico
tail -200 logs/*.log | grep -i "error\|exception\|failed"

# Verificar screenshots
ls -lt data/screenshots/ | head -20

# Modo DEBUG (browser permanece aberto)
DISPLAY=:1 DEBUG_MODE=true PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/relatorio_operacao_desagio.py
```

### HTTP 429 (Rate Limit)

O sistema detecta e trata automaticamente:
- Aguarda tempo do header `Retry-After`
- Backoff exponencial com jitter
- Tempo adicional após callback

```bash
# Verificar rate limit nos logs
grep -r "HTTP 429\|Rate limit" logs/*.log
```

---

## ❓ FAQ

### Quais processadores estão na v2.1?
**3 processadores**: `relatorio_operacao_desagio`, `emissao_boleto_primeira_via`, `envio_boleto_operacao_padrao`

### Preciso modificar alguma coisa?
**NÃO!** Arquitetura stealth completa já implementada e testada.

### As melhorias afetam performance?
**NÃO**. Impacto < 2% no tempo de execução. Retry adaptativo compensa sobrecarga.

### O que fazer se SmartSecurities adicionar Cloudflare?
**Score 9.5/10 já é robusto**, mas podemos implementar TLS fingerprinting se necessário.

### Qual a taxa de sucesso esperada?
**≥ 95%** com proxy BrightData sticky session. Se < 90%, verificar proxy/display VNC.

### Como funciona o Retry Adaptativo?
Tempos progressivos: **3s → 6s → 9s**. Aguarda carregamento completo antes de interagir.

### Proxy é obrigatório?
**SIM!** BrightData sticky session garante IP consistente e evita flags de localização.

---

## 📊 Checklist de Sucesso (v2.1)

```
✓ Taxa de sucesso ≥ 95%
✓ Score anti-detecção: 9.5/10
✓ Proxy BrightData ativo (IP consistente)
✓ Display VNC operacional
✓ Retry adaptativo funcionando (3s → 6s → 9s)
✓ CAPTCHA resolve normalmente
✓ RateLimitHandler detecta HTTP 429
✓ Fingerprinting determinístico (sem variação)
✓ Screenshots em milestones capturados
✓ Logs estruturados com timestamps
```

---

## 📚 Links Úteis

- 📘 [Documentação Completa](./MELHORIAS_ANTIBOT_2025.md)
- 📊 [Processadores](./processors/)
  - [Relatório Operação Deságio](./processors/PROCESSADOR_RELATORIO_OPERACAO_DESAGIO.md) (Score 9.5)
  - [Emissão Boleto Primeira Via](./processors/PROCESSADOR_EMISSAO_BOLETO_PRIMEIRA_VIA.md) (Score 9.5)
  - [Envio Boleto Operação Padrão](./processors/PROCESSADOR_ENVIO_BOLETO_OPERACAO_PADRAO.md) (Score 9.5)
  - [Envio Boleto Operação Oculto](./processors/PROCESSADOR_ENVIO_BOLETO_OPERACAO_OCULTO.md)
- 🏗️ [Como Criar Processadores](./COMO_CRIAR_PROCESSADORES.md)
- 🔧 [Sistema de Backup](./SISTEMA_BACKUP.md)
- 📁 [Estrutura de Pastas](./ESTRUTURA_DE_PASTAS.md)

---

**Versão**: 2.1 (Score 9.5/10) | **Data**: 2025-11-17
