# Gerenciamento de Displays VNC via Systemd

Este documento descreve como os displays VNC (Xvfb + x11vnc + noVNC) são gerenciados via systemd no PROSPER-ERP-AUTOMATION.

## 📋 Visão Geral

Todos os 10 displays VNC são gerenciados como serviços systemd, garantindo:

- ✅ **Auto-start no boot** - Iniciam automaticamente quando a VM liga
- ✅ **Proteção sudo** - Requerem privilégios sudo para parar/reiniciar
- ✅ **Auto-restart** - Reiniciam automaticamente se crasharem
- ✅ **Logs centralizados** - Via journalctl
- ✅ **Gerenciamento individual** - Controle granular por display

## 🗂️ Arquitetura

Cada display possui 3 serviços systemd:

```
Display :N
├── xvfb@N.service    → Display virtual (Xvfb)
├── x11vnc@N.service  → Servidor VNC (depende do Xvfb)
└── novnc@N.service   → Interface web (depende do x11vnc)
```

### Dependências

```
novnc@N → x11vnc@N → xvfb@N
```

- `x11vnc@N` só inicia depois que `xvfb@N` estiver rodando
- `novnc@N` só inicia depois que `x11vnc@N` estiver rodando
- Se `xvfb@N` parar, os outros 2 param automaticamente

## 📦 Arquivos do Sistema

### Serviços Systemd

Localizados em `/etc/systemd/system/`:

- **xvfb@.service** - Template para Xvfb
- **x11vnc@.service** - Template para x11vnc
- **novnc@.service** - Template para noVNC

### Scripts de Gerenciamento

Localizado em `systemd/`:

- **instalar_servicos_vnc.sh** - Script de instalação e gerenciamento

## 🚀 Instalação

Para instalar os serviços systemd pela primeira vez:

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
sudo bash systemd/instalar_servicos_vnc.sh install
```

Isso irá:
1. Copiar arquivos `.service` para `/etc/systemd/system/`
2. Recarregar configuração do systemd
3. Habilitar todos os serviços (10 displays) para auto-start

## 📖 Comandos de Gerenciamento

### Gerenciar Todos os Displays

```bash
# Iniciar todos os displays (1 a 10)
sudo bash systemd/instalar_servicos_vnc.sh start

# Parar todos os displays
sudo bash systemd/instalar_servicos_vnc.sh stop

# Reiniciar todos os displays
sudo bash systemd/instalar_servicos_vnc.sh restart

# Ver status de todos os displays
sudo bash systemd/instalar_servicos_vnc.sh status

# Desinstalar serviços systemd
sudo bash systemd/instalar_servicos_vnc.sh uninstall
```

### Gerenciar Display Individual

```bash
# Iniciar apenas o Display :2
sudo systemctl start xvfb@2.service
sudo systemctl start x11vnc@2.service
sudo systemctl start novnc@2.service

# Parar apenas o Display :3
sudo systemctl stop novnc@3.service
sudo systemctl stop x11vnc@3.service
sudo systemctl stop xvfb@3.service

# Reiniciar Display :4 (ordem correta)
sudo systemctl restart xvfb@4.service
sudo systemctl restart x11vnc@4.service
sudo systemctl restart novnc@4.service

# Ver status do Display :5
sudo systemctl status xvfb@5.service
sudo systemctl status x11vnc@5.service
sudo systemctl status novnc@5.service
```

### Listar Todos os Serviços VNC

```bash
# Ver todos os serviços VNC ativos
systemctl list-units "xvfb@*" "x11vnc@*" "novnc@*"

# Ver apenas serviços habilitados
systemctl list-unit-files "xvfb@*" "x11vnc@*" "novnc@*"
```

## 📊 Logs

### Ver Logs em Tempo Real

```bash
# Logs do Xvfb Display :1
sudo journalctl -u xvfb@1 -f

# Logs do x11vnc Display :2
sudo journalctl -u x11vnc@2 -f

# Logs do noVNC Display :3
sudo journalctl -u novnc@3 -f
```

### Ver Logs Históricos

```bash
# Últimas 50 linhas do Xvfb Display :1
sudo journalctl -u xvfb@1 -n 50

# Logs desde ontem
sudo journalctl -u xvfb@1 --since yesterday

# Logs entre datas específicas
sudo journalctl -u xvfb@1 --since "2025-10-20" --until "2025-10-25"
```

### Ver Logs de Todos os Displays

```bash
# Ver logs de todos os serviços Xvfb
sudo journalctl -u "xvfb@*" -f

# Ver logs de todos os serviços VNC (xvfb + x11vnc + novnc)
sudo journalctl -u "xvfb@*" -u "x11vnc@*" -u "novnc@*" -f
```

## 🗺️ Mapeamento de Portas

| Display | VNC Web Port | x11vnc Port | API Port | URL                                      |
|---------|--------------|-------------|----------|------------------------------------------|
| :1      | 6080         | 5900        | 6090     | http://3.148.126.73:6080/vnc.html       |
| :2      | 6081         | 5901        | 6091     | http://3.148.126.73:6081/vnc.html       |
| :3      | 6082         | 5902        | 6092     | http://3.148.126.73:6082/vnc.html       |
| :4      | 6083         | 5903        | 6093     | http://3.148.126.73:6083/vnc.html       |
| :5      | 6084         | 5904        | 6094     | http://3.148.126.73:6084/vnc.html       |
| :6      | 6085         | 5905        | 6095     | http://3.148.126.73:6085/vnc.html       |
| :7      | 6086         | 5906        | 6096     | http://3.148.126.73:6086/vnc.html       |
| :8      | 6087         | 5907        | 6097     | http://3.148.126.73:6087/vnc.html       |
| :9      | 6088         | 5908        | 6098     | http://3.148.126.73:6088/vnc.html       |
| :10     | 6089         | 5909        | 6099     | http://3.148.126.73:6089/vnc.html       |

## 🔧 Troubleshooting

### Display não inicia

```bash
# Verificar logs de erro
sudo journalctl -u xvfb@1 -n 50 --no-pager

# Verificar se porta está em uso
sudo netstat -tlnp | grep 6080

# Limpar locks do X11
sudo rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

# Reiniciar serviço
sudo systemctl restart xvfb@1
```

### x11vnc não conecta ao Xvfb

```bash
# Verificar se Xvfb está rodando
sudo systemctl status xvfb@1

# Verificar se Display :1 existe
DISPLAY=:1 xdpyinfo | head

# Reiniciar em ordem correta
sudo systemctl stop x11vnc@1 novnc@1
sudo systemctl restart xvfb@1
sleep 2
sudo systemctl start x11vnc@1
sleep 1
sudo systemctl start novnc@1
```

### noVNC não carrega no browser

```bash
# Verificar se x11vnc está ouvindo
sudo netstat -tlnp | grep 5900

# Verificar se noVNC está rodando
sudo systemctl status novnc@1

# Ver logs do noVNC
sudo journalctl -u novnc@1 -n 20

# Testar conexão direta ao x11vnc
nc -zv localhost 5900
```

### Serviço crashando repetidamente

```bash
# Ver logs de falhas
sudo journalctl -u xvfb@1 --since "1 hour ago" | grep -i error

# Ver contador de restarts
sudo systemctl show xvfb@1 | grep NRestarts

# Desabilitar auto-restart temporariamente
sudo systemctl edit xvfb@1
# Adicionar:
# [Service]
# Restart=no

# Iniciar manualmente para debug
sudo /usr/bin/Xvfb :1 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset
```

## 🔄 Migração do Script Antigo

O script antigo `iniciar_vnc_displays.sh` ainda existe e pode ser usado, mas **NÃO** deve ser usado em conjunto com os serviços systemd.

### Diferenças

| Aspecto              | Script Antigo          | Systemd              |
|----------------------|------------------------|----------------------|
| Inicialização        | Manual                 | Automática (boot)    |
| PIDs                 | `/tmp/vnc-pids/`       | Gerenciado systemd   |
| Logs                 | `/tmp/vnc-logs/`       | journalctl           |
| Requer sudo          | ❌ Não                 | ✅ Sim               |
| Auto-restart         | ❌ Não                 | ✅ Sim               |
| Persistente no boot  | ❌ Não                 | ✅ Sim               |

### Para voltar ao script antigo

```bash
# 1. Desinstalar serviços systemd
sudo bash systemd/instalar_servicos_vnc.sh uninstall

# 2. Usar script antigo
./iniciar_vnc_displays.sh start
```

## 📝 Notas Importantes

1. **Ordem de inicialização importa**: Sempre inicie Xvfb → x11vnc → noVNC
2. **Ordem de parada é inversa**: Pare noVNC → x11vnc → Xvfb
3. **Locks do X11**: Se houver conflito, remova `/tmp/.X*-lock` manualmente
4. **Dependências**: Os serviços têm `Requires=` e `BindsTo=` para garantir ordem correta
5. **Auto-restart**: Serviços reiniciam automaticamente após 5 segundos se falharem

## 🎯 Status Atual

**10/10 displays rodando via systemd** ✅

Todos os displays estão configurados, habilitados e rodando como serviços systemd desde 2025-10-25.

Para verificar status: `sudo bash systemd/instalar_servicos_vnc.sh status`
