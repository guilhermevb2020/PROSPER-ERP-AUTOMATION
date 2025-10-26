# Convenções de Portas - PROSPER-ERP-AUTOMATION

## Regra Geral: API sempre +10 da porta VNC

Cada processador utiliza **duas portas**:
- **Porta VNC**: Para acesso remoto ao display virtual (noVNC)
- **Porta API**: Para controle remoto (pause/resume/stop) via HTTP

**Convenção**: A porta da API é sempre **10 unidades acima** da porta VNC.

---

## Processadores Ativos

### 1. relatorio_operacao_desagio

**Display**: `:1`

**Portas**:
- **VNC**: `6080`
  - URL: `http://3.148.126.73:6080/vnc.html`
  - Protocolo: noVNC (WebSocket)
  - Acesso: Browser (visualização do display :1)

- **API**: `6090` (VNC + 10)
  - URL Base: `http://3.148.126.73:6090`
  - Endpoints:
    - `GET /status` - Status da automação
    - `GET /resume` - Retomar execução
    - `GET /pause` - Pausar execução
    - `GET /stop` - Parar execução
  - Protocolo: HTTP (Flask)

**Arquivos**:
- Processador: `src/processors/web/relatorio_operacao_desagio.py`
- API: `src/api/control_api.py`
- Env: `.env` (SERVER_PORT=6090)

### 2. relatorio_titulos_aberto

**Display**: `:2`

**Portas**:
- **VNC**: `6081`
  - URL: `http://3.148.126.73:6081/vnc.html`
  - Protocolo: noVNC (WebSocket)
  - Acesso: Browser (visualização do display :2)

- **API**: `6091` (VNC + 10)
  - URL Base: `http://3.148.126.73:6091`
  - Endpoints:
    - `GET /status` - Status da automação
    - `GET /resume` - Retomar execução
    - `GET /pause` - Pausar execução
    - `GET /stop` - Parar execução
  - Protocolo: HTTP (Flask)

**Arquivos**:
- Processador: `src/processors/web/relatorio_titulos_aberto.py`
- URL: `https://www.smartsecurities.com.br/smart/financeiro/titulosemaberto.php`

---

## Tabela de Referência

| Processador                  | Display | VNC Port | API Port | Status |
|------------------------------|---------|----------|----------|--------|
| relatorio_operacao_desagio   | :1      | 6080     | 6090     | ✅ Ativo |
| relatorio_titulos_aberto     | :2      | 6081     | 6091     | ✅ Ativo |
| (reservado para futuro)      | :3      | 6082     | 6092     | ⏸️ Planejado |

---

## Como Adicionar Novo Processador

Ao criar um novo processador, siga estas etapas:

### 1. Escolher Display e Portas

```python
# Exemplo: Novo processador no display :2
DISPLAY = ":2"
VNC_PORT = 6070    # Escolher porta VNC disponível
API_PORT = 6080    # Sempre VNC_PORT + 10
```

### 2. Configurar no Processador

```python
class ProcessadorNovo:
    def __init__(self):
        self.nome = "processador_novo"
        self.display = os.environ.get('DISPLAY', ':2')
```

**No header do arquivo**:
```python
# DISPLAY: :2 (VNC porta 6070)
# API: Porta 6080
```

**Nas URLs de notificação**:
```python
print(f"🖥️  Acesso VNC: http://{os.getenv('SERVER_IP')}:6070/vnc.html")
```

### 3. Configurar .env

```bash
# Adicionar variáveis do novo processador
DISPLAY_PROCESSADOR_NOVO=:2
VNC_PORT_PROCESSADOR_NOVO=6070
API_PORT_PROCESSADOR_NOVO=6080
```

### 4. Configurar Xvfb/VNC

```bash
# Iniciar display virtual
Xvfb :2 -screen 0 1920x1080x24 &

# Iniciar VNC no display :2
x11vnc -display :2 -rfbport 5901 -forever -shared &

# Configurar noVNC para porta 6070
# (ajustar configuração do noVNC ou nginx)
```

### 5. Abrir Portas no AWS

No Security Group da EC2, adicionar regras de entrada:
- **Porta 6070** (TCP) - VNC
- **Porta 6080** (TCP) - API
- Origem: `0.0.0.0/0` (ou IPs específicos para segurança)

### 6. Atualizar Esta Documentação

Adicionar nova linha na tabela acima com as informações do processador.

---

## Notas Importantes

### Por que API é +10 acima do VNC?

1. **Organização**: Fácil lembrar a relação entre as portas
2. **Padronização**: Todos os processadores seguem a mesma lógica
3. **Escalabilidade**: Fácil adicionar novos processadores
4. **Documentação**: Regra simples de documentar

### Exemplo de Uso

```bash
# Ver status do processador
curl http://3.148.126.73:6090/status

# Pausar processador
curl http://3.148.126.73:6090/pause

# Retomar processador
curl http://3.148.126.73:6090/resume

# Acessar VNC do processador
# No browser: http://3.148.126.73:6080/vnc.html
```

### Conflitos de Porta

Se houver conflito com outro serviço:
1. Escolher nova porta VNC disponível
2. Calcular API = VNC + 10
3. Atualizar documentação
4. Atualizar código do processador
5. Reiniciar serviços

---

---

## 🚀 Script de Inicialização: iniciar_vnc_displays.sh

### Localização
`/home/ubuntu/PROSPER-ERP-AUTOMATION/iniciar_vnc_displays.sh`

### Comandos Disponíveis

```bash
# Iniciar todos os 10 displays VNC
./iniciar_vnc_displays.sh start

# Ver status de todos os displays
./iniciar_vnc_displays.sh status

# Parar todos os displays
./iniciar_vnc_displays.sh stop

# Reiniciar todos os displays
./iniciar_vnc_displays.sh restart

# Ajuda
./iniciar_vnc_displays.sh help
```

### Features

✅ **Gerenciamento Completo**: Start/Stop/Status/Restart
✅ **Verificações de Saúde**: Detecta processos rodando antes de iniciar
✅ **PID Files**: Armazena PIDs em `/tmp/vnc-pids/`
✅ **Logs Organizados**: Logs em `/tmp/vnc-logs/`
✅ **Output Colorido**: Fácil visualização no terminal
✅ **Prevenção de Duplicatas**: Não inicia se já estiver rodando

### Exemplo de Uso

```bash
# 1. Iniciar todos os displays (EXECUTAR UMA VEZ)
./iniciar_vnc_displays.sh start

# 2. Verificar se estão rodando
./iniciar_vnc_displays.sh status

# 3. Executar processadores (conectam nos displays)
DISPLAY=:1 python src/processors/web/relatorio_operacao_desagio.py
DISPLAY=:2 python src/processors/web/outro_processador.py
```

### Ordem de Inicialização

```
1️⃣ SERVIDOR (UMA VEZ)
   └─ ./iniciar_vnc_displays.sh start
      → Inicia 10 displays (:1 até :10)
      → Fica rodando para sempre

2️⃣ PROCESSADORES (Quando necessário)
   └─ python src/processors/web/processador.py
      → Conecta no display já existente
      → Pode iniciar/parar livremente
```

---

## Histórico

| Data       | Versão | Mudança                                    |
|------------|--------|---------------------------------------------|
| 2025-01-XX | 1.0    | Criação da convenção (VNC base, API +10)  |
| 2025-01-XX | 1.1    | Processador relatorio_operacao_desagio     |
|            |        | VNC: 6080, API: 6090                       |
| 2025-01-XX | 1.2    | Script iniciar_vnc_displays.sh criado      |
|            |        | Suporte para 10 displays simultâneos       |

---

**Última atualização**: 2025-01-XX
**Mantido por**: Equipe PROSPER-ERP-AUTOMATION
