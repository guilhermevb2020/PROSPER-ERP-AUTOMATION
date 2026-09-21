# Estrutura de Pastas

Visão geral da organização atual do projeto.

```
PROSPER-ERP-AUTOMATION/
├─ README.md
├─ requirements.txt
├─ .env.example
├─ docs/
│  ├─ BRIGHT_DATA_SETUP.md
│  ├─ ESTRUTURA_DE_PASTAS.md
│  ├─ MIGRACAO_BRIGHT_DATA.md
│  ├─ SITE_KEY_CORRETO.md
│  └─ orchestracao.md
├─ scripts/
│  ├─ start_fresh.sh
│  ├─ restart_environment.sh
│  ├─ iniciar_vnc_displays.sh
│  ├─ mapear_botao_confirmar_popup.js
│  ├─ mapear_botao_gerar.js
│  └─ mapear_recaptchas.js
├─ config/
│  ├─ credentials.example.csv
│  └─ processors.example.yaml
├─ data/                             # Dados e outputs
│  ├─ raw_inputs/                    # Arquivos baixados (CSVs, etc)
│  ├─ processed_outputs/             # Arquivos processados
│  ├─ checkpoints/                   # Checkpoints de execução
│  │  └─ relatorio_desagio_state.mock.json
│  ├─ screenshots/                   # Screenshots de execução
│  └─ assets/                        # Assets estáticos
│     └─ email/
│        ├─ logo_prosper.png
│        ├─ prosperito.png
│        └─ templates/               # ⭐ Templates de mensagens de email
│           └─ mensagem_boletos.txt
├─ logs/
├─ src/
│  ├─ core/
│  │  └─ logging_config.py          # Configuração de logging
│  │
│  ├─ config/
│  │  └─ settings.py                 # Configurações centralizadas
│  │
│  ├─ common/                        # ⭐ Biblioteca compartilhada (REORGANIZADA)
│  │  ├─ __init__.py
│  │  │
│  │  ├─ core/                       # Módulos essenciais (uso em 100% dos processadores)
│  │  │  ├─ __init__.py
│  │  │  ├─ database.py              # Conexão PostgreSQL
│  │  │  ├─ config_loader.py         # Configurações (processors.yaml, credentials.csv)
│  │  │  ├─ execution_logger.py      # Sistema de logs
│  │  │  └─ screenshot_manager.py    # Gerenciador de screenshots
│  │  │
│  │  ├─ captcha/                    # CAPTCHA (web automation)
│  │  │  ├─ __init__.py
│  │  │  ├─ playwright_captcha_manager.py  # Gerenciador CAPTCHA
│  │  │  └─ captcha_solver.py        # API CapSolver
│  │  │
│  │  ├─ utils/                      # Utilitários
│  │  │  ├─ __init__.py
│  │  │  ├─ notification_utils.py    # Notificações por email
│  │  │  ├─ file_rename.py           # Renomeação de arquivos
│  │  │  ├─ wait_utils.py            # Waits para proxy
│  │  │  └─ rate_limit_handler.py    # Rate limiting HTTP 429
│  │  │
│  │  ├─ anti_detection/             # Sistema anti-detecção
│  │  │  ├─ __init__.py
│  │  │  ├─ main.py                  # anti_detection_2025.py (renomeado)
│  │  │  ├─ behavior.py              # Comportamento humano
│  │  │  ├─ brightdata_proxy.py      # Proxy Bright Data
│  │  │  ├─ brightdata_playwright_fix.py  # Fix BrightData
│  │  │  ├─ human_behavior_utils.py  # Utilitários comportamento
│  │  │  ├─ browser.py               # Configuração browser
│  │  │  ├─ fingerprints.py          # Fingerprinting integrado
│  │  │  ├─ network.py               # Network monitoring
│  │  │  └─ profiles.py              # Perfis de hardware
│  │  │
│  │  ├─ browser/                    # Browser stealth
│  │  │  ├─ __init__.py
│  │  │  ├─ stealth_browser.py       # Browser com args anti-bot
│  │  │  ├─ stealth_context.py       # Context com fingerprinting
│  │  │  ├─ stealth_integration.py   # Integração stealth
│  │  │  └─ stealth_page.py          # Page com injeção automática
│  │  │
│  │  ├─ fingerprinting/             # Fingerprints individuais
│  │  │  ├─ __init__.py
│  │  │  ├─ canvas_fingerprint.py    # Canvas fingerprint
│  │  │  ├─ webgl_fingerprint.py     # WebGL fingerprint
│  │  │  ├─ audio_fingerprint.py     # Audio fingerprint
│  │  │  ├─ navigator_overrides.py   # Navigator overrides
│  │  │  ├─ webrtc_blocker.py        # WebRTC blocker
│  │  │  └─ chrome_runtime.py        # Chrome runtime
│  │  │
│  │  ├─ profiles/                   # Gerenciamento de perfis
│  │  │  ├─ __init__.py
│  │  │  ├─ profile_manager.py       # Gerenciador de perfis
│  │  │  └─ hardware_profiles.py     # Perfis de hardware
│  │  │
│  │  ├─ base/                       # Classes base
│  │  │  ├─ __init__.py
│  │  │  └─ base_processor.py        # Classe base para processadores
│  │  │
│  │  └─ deprecated/                 # Módulos obsoletos (histórico)
│  │     ├─ README.md
│  │     ├─ anti_detection_2025.py
│  │     ├─ brightdata_browser.py
│  │     ├─ browser/
│  │     ├─ column_mappings.py
│  │     ├─ database.py
│  │     ├─ file_utils.py
│  │     ├─ fingerprinting/
│  │     ├─ hardware_profiles.py
│  │     ├─ human_behavior_utils.py
│  │     ├─ profiles/
│  │     └─ timezone_utils.py
│  │
│  ├─ api/                           # APIs HTTP (servidores REST)
│  │  ├─ __init__.py
│  │  ├─ control_api.py              # API de controle geral
│  │  ├─ control_api_titulos.py      # API de controle títulos
│  │  └─ titulos_abertos_dias_corridos.py  # ⚠️ Processador ETL (deveria estar em processors/)
│  │
│  └─ processors/
│     └─ web/                        # Processadores web (temporário - será reorganizado)
│        ├─ relatorio_operacao_desagio.py
│        ├─ relatorio_titulos_aberto.py
│        ├─ emissao_boleto_primeira_via.py
│        ├─ envio_boleto_operacao_oculto.py
│        ├─ envio_boleto_operacao_oculto_retry.py
│        ├─ envio_boleto_operacao_padrao.py
│        └─ backup/
├─ tests/
│  ├─ unit/
│  │  └─ test_file_rename.mock.py
│  └─ integration/
│     └─ test_scheduler.mock.py
├─ temp/
└─ venv/
```

## 📋 Notas sobre Organização

### `src/common/` - Estrutura Reorganizada (2025-11-15)
- **core/**: Módulos essenciais usados por todos os processadores (database, config, logger, screenshots)
- **captcha/**: Módulos relacionados a CAPTCHA (CapSolver, Playwright manager)
- **utils/**: Utilitários diversos (notifications, files, waits, rate limit)
- **anti_detection/**: Sistema complexo de anti-detecção (score 9.0/10)
- **browser/**: Browser stealth (separado do anti_detection)
- **fingerprinting/**: Fingerprints individuais (canvas, webgl, audio, etc)
- **profiles/**: Gerenciamento de perfis de hardware
- **base/**: Classes base para processadores

### `data/assets/email/templates/`
- Templates de mensagens de email em formato `.txt`
- Placeholders: `%NOME_SACADO%`, `%NOME_CEDENTE%`, `%RELACAO_TITULOS%`

### `src/processors/`
- Atualmente em `processors/web/` (temporário)
- Planejado: Reorganizar por funcionalidade (relatorios/, boletos/, cobranca/, api/)

> **IMPORTANTE**: Atualize este documento sempre que novos diretórios relevantes forem adicionados ou removidos.

