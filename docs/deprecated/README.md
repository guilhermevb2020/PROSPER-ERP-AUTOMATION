# Documentações Deprecated (Histórico)

**Data de Migração:** 2025-11-15

---

## 📋 Por que estes arquivos estão aqui?

Esta pasta contém documentações **obsoletas** ou **temporárias** que não são mais relevantes para o uso atual do projeto, mas foram mantidas para:

1. **Histórico** - Registro de decisões e análises passadas
2. **Referência** - Consulta futura se necessário
3. **Auditoria** - Rastreabilidade de evolução do projeto

---

## 🗂️ Categorias de Arquivos

### 1. Roadmaps/Análises Temporárias (Já Implementadas)
Análises e roadmaps criados para planejar melhorias anti-bot. **Já foram implementados** e incorporados nos módulos atuais.

- `ROADMAP_SISTEMA_ANTIBOT_10_10.md`
- `ROADMAP_ANTI_BOT_PRAGMATICO.md`
- `ROADMAP_FINAL_SUMMARY.txt`
- `INDEX.md` (índice dos roadmaps)
- `00_LEIA_PRIMEIRO.txt`
- `SUMARIO_EXECUTIVO.md`
- `RESUMO_EXECUTIVO_ANTI_BOT.md`
- `REFERENCIAS_ANTI_BOT_2025.md`
- `ANALISE_ANTI_BOT_SMARTSECURITIES.md`
- `ANALISE_SMARTSECURITIES_VS_PROSPER.md`
- `PRINCIPIOS_MANUTENCAO_SIMPLIFICADA.md`

### 2. Análises de Bibliotecas Humanização (Já Decidido)
Análises de bibliotecas para humanização de comportamento. **Já foi decidido** não usar bibliotecas externas (implementação manual mais simples).

- `ANALISE_BIBLIOTECAS_HUMANIZACAO_2025.md`
- `README_HUMANIZACAO.md`
- `SUMARIO_BIBLIOTECAS_HUMANIZACAO.txt`
- `RELATORIO_FINAL_HUMANIZACAO.txt`
- `DADOS_TECNICO_BIBLIOTECAS.csv`

### 3. Debug/Soluções Técnicas Específicas (Já Resolvidas)
Documentações de debug de problemas específicos que já foram resolvidos e integrados no código.

- `DEBUG_POPUP_SMARTSECURITIES.md` - Debug de popups já resolvido
- `SOLUCAO_SUBMIT_LOGIN_SMARTSECURITIES.md` - Solução de login já aplicada
- `RESUMO_SOLUCAO_LOGIN.md` - Resumo já aplicado
- `SITE_KEY_CORRETO.md` - Site key descoberto e configurado

### 4. Migração/Proxy (Informações Desatualizadas)
Documentações sobre migração para Bright Data e configuração de proxy. **Já foi concluída** e consolidada em `GUIA_BRIGHT_DATA.md`.

- `MIGRACAO_BRIGHT_DATA.md` - Migração concluída
- `SOLUCAO_BRIGHTDATA_RECAPTCHA.md` - Solução já aplicada
- `GUIA_RAPIDO_PROXY_BYPASS.md` - Consolidado em novo guia
- `SOLUCAO_DEFINITIVA_ANTI_DETECCAO_2025.md` - Consolidado em novos módulos

---

## ✅ Onde encontrar informações atualizadas?

Se você está procurando documentação atual, consulte:

- **Criar processadores** → `docs/COMO_CRIAR_PROCESSADORES.md`
- **Módulos disponíveis** → `docs/README_MODULOS.md`
- **Bright Data proxy** → `docs/GUIA_BRIGHT_DATA.md`
- **Migração para novos módulos** → `docs/MIGRACAO_MODULOS_NOVOS.md`
- **Estrutura do projeto** → `docs/ESTRUTURA_DE_PASTAS.md`
- **Índice geral** → `docs/INDEX.md`

---

## 🚫 Não usar estes arquivos

**IMPORTANTE:** Estes arquivos **NÃO devem** ser usados como referência para desenvolvimento atual. Eles contêm:

- ❌ Referências a módulos obsoletos
- ❌ Configurações desatualizadas
- ❌ Análises de problemas já resolvidos
- ❌ Roadmaps já implementados

Para informações atualizadas, sempre consulte a documentação na pasta `docs/` principal.

---

**Mantido para:** Histórico e auditoria
**Última atualização:** 2025-11-15

---

## 21/09/2026 — a era 2025 sai do código

Medição: grafo de imports a partir das 12 entradas que o hub e o `boot_vnc.sh`
executam, conferido a mão com `grep`. Nada do que segue era alcançado por robô
vivo. O código saiu do repositório (histórico no git, no commit da remoção) e
está também em `backups/organizacao-20260921/legado-2025.tar.gz` (143 arquivos).

| o que saiu | onde está a história |
|---|---|
| os 8 processadores de 2025 (`emissao_boleto_primeira_via`, `envio_boleto_operacao_*`, `envio_cobranca_boleto_oculto`, `relatorio_*`, `baixar_documentos_doc2you`) e `src/processors/web/backup/` | git + tar; docs em [`processors-2025/`](processors-2025/) e [`fluxos_processadores-2025/`](fluxos_processadores-2025/) |
| o stack antibot: `src/common/{anti_detection,browser,captcha,fingerprinting,profiles,utils,base,deprecated}` e `src/common/core/{checkpoint_manager,database,execution_logger,screenshot_manager}` | git + tar; docs `*ANTIBOT*`, `WAIT_UTILS*`, `RELATORIO_ANTIBOT_2025_EMISSAOBOLETO.md` aqui |
| módulos soltos de `src/common/`: `captcha_solver`, `column_mappings`, `database`, `file_utils`, `nodriver_utils`, `notification_utils`, `timezone_utils` | git + tar |
| a API de controle (`src/api`, porta 6092), `src/config/settings.py`, `src/core/logging_config.py` | git + tar |
| scripts do host pré-Docker e os units do systemd | [`host-legado/`](host-legado/) |
| scripts de debug e mapeamento de 2025 | [`scripts-2025/`](scripts-2025/) |
| `config/anti_detection.yaml` | [`config/`](config/) |
| guias da era: `COMO_CRIAR_PROCESSADORES`, `CRIAR_PROCESSADOR`, `ESTRUTURA_DE_PASTAS`, `ARQUITETURA`, `TROUBLESHOOTING`, `ACESSO_VNC`, `SYSTEMD_VNC`, `SISTEMA_BACKUP`, `MIGRACAO_LOCAL_SERVIDOR`, `orchestracao` | aqui, com o nome original |

O que ficou de propósito: `src/common/core/config_loader.py` e `config/processors.yaml`
(o doc2you resolve credencial por eles), `doc2you/manter_sessao.py` e `login_manual.py`
(ferramentas de 2026), `boletos/_emissao_html.py` (usado pela emissão).
