# Pesquisa: Bibliotecas de Humanização para Playwright Python (2025)

## Documentos Relacionados

Este diretório contém análise completa sobre bibliotecas de humanização/anti-detecção para Playwright Python em 2025.

### Arquivos Gerados

1. **SUMARIO_BIBLIOTECAS_HUMANIZACAO.txt** (18 KB)
   - Sumário executivo em formato texto
   - Leitura rápida: 5-10 minutos
   - Ideal para decisão rápida
   - Contém tabelas comparativas
   - **COMECE AQUI** para visão geral

2. **ANALISE_BIBLIOTECAS_HUMANIZACAO_2025.md** (19 KB)
   - Análise técnica completa em Markdown
   - Leitura profunda: 20-30 minutos
   - Detalhes de cada biblioteca analisada
   - Plano de ação com código exemplo
   - Checklist de implementação
   - **LEIA DEPOIS** para detalhes

### Bibliotecas Analisadas

| Biblioteca | Score | Recomendação | Razão |
|------------|-------|------|-------|
| **playwright-stealth** | 8.3/10 | ✅ SIM (complementar) | Maduro (832 stars), zero breaking changes, 1 linha |
| humanization-playwright | 6.3/10 | ❌ NÃO | Requer Patchright, breaking changes |
| botright | 5.0/10 | ❌ NÃO | Python 3.10 máximo (PROSPER usa 3.12) |
| emunium | 5.7/10 | ❌ NÃO | Over-engineered (OCR desnecessário) |
| python-ghost-cursor | 5.0/10 | ❌ NÃO | Manutenção descontinuada |
| undetected-playwright-python | 4.0/10 | ❌ NÃO | Descontinuado, successor é Patchright |

## Recomendação

**ESTRATÉGIA RECOMENDADA:** Não adicionar biblioteca externa de humanização

Seu código `HumanBehavior` em `/src/common/deprecated/human_behavior_utils.py` é excelente e já implementa bem a humanização. Em vez disso:

### Fase 1: Integrar playwright-stealth (1-2 dias)
```bash
pip install playwright-stealth
```

Ganho: +1.0-1.5 pts (7.5 → 8.5-9.0)
Risco: BAIXO
Esforço: 1 linha de código por processador

### Fase 2: Melhorar HumanBehavior (2-3 dias)
- Exploração de página mais realista
- Context-aware timing
- Scroll inteligente

Ganho: +0.5 pts (9.0 → 9.5)
Risco: BAIXO

### Fase 3 (OPCIONAL): Anti-detection Avançado (3-5 dias)
- Navigator spoofing
- Header naturalization

Ganho: +0.5 pts (9.5 → 10.0)
Risco: MÉDIO

## Resultado Esperado

- **Antes:** 7.5/10
- **Depois (Fases 1+2):** 9.0-9.5/10
- **Esforço Total:** 6-9 horas
- **Risco:** BAIXO
- **Manutenibilidade:** 1 pessoa continua mantendo facilmente

## Por Que Esta Estratégia?

✅ Mantém código simples (1 pessoa mantém)
✅ Zero breaking changes (compatível 100%)
✅ Não depende de libs alpha/nova
✅ Preserva código de humanização existente
✅ Score realista e sustentável

## Próximos Passos

1. **Leia primeiro:** `SUMARIO_BIBLIOTECAS_HUMANIZACAO.txt` (5 min)
2. **Depois aprofunde:** `ANALISE_BIBLIOTECAS_HUMANIZACAO_2025.md` (20 min)
3. **Implemente:** Fase 1 (integrar playwright-stealth)
4. **Documente:** Progresso em `CLAUDE.md`

## Referências

- **playwright-stealth:** https://github.com/AtuboDad/playwright_stealth
- **Seu HumanBehavior:** `/src/common/deprecated/human_behavior_utils.py`
- **Requirements:** `/requirements.txt`

---

**Data da Análise:** 2025-11-15
**Python:** 3.12+
**Framework:** Playwright + Nodriver
**Constraint:** 1 pessoa mantém
