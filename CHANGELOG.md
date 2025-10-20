# 📝 Changelog - PROSPER-ERP-AUTOMATION

## [1.0.0] - 2025-10-17

### ✅ Criado
- Estrutura completa do projeto separado do PROSPER_DATA_HUB
- Diretórios organizados (src/, data/, logs/, scripts/, docs/, config/)
- Sistema de notificações por email com HTML e imagens

### 📦 Arquivos Copiados
- `src/processors/web/titulos_abertos_e_marcados_recompras.py` - Processador web principal
- `src/common/selenium_utils.py` - Utilitários Selenium com stealth mode
- `src/common/timezone_utils.py` - Gestão de timezone Brasília
- `src/common/reporting_utils.py` - Sistema de notificações por email
- `src/core/logging_config.py` - Configuração de logs
- `assets/email/logo_prosper.png` - Logo para emails
- `assets/email/prosperito.png` - Mascote para emails

### 📄 Documentação
- README.md completo com instruções de instalação e uso
- .env.example com template de configuração
- .gitignore configurado para não versionar dados sensíveis

### 🔧 Configuração
- requirements.txt específico para automações web
- Dependências: Selenium, undetected-chromedriver, CapSolver, pandas

### 🎯 Próximos Passos
- [ ] Testar em ambiente local
- [ ] Configurar VNC para execução headless
- [ ] Implementar noVNC (VNC no navegador)
- [ ] Sistema de notificação quando CAPTCHA travar
- [ ] Migrar para VM dedicada

---

## Localização
**Pasta atual**: `/home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION/`
**Quando mover para VM**: Copiar toda esta pasta para o novo servidor
