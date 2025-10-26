#!/bin/bash
# ================================================================================
# SCRIPT: iniciar_vnc_displays.sh
# DESCRIÇÃO: Gerencia displays virtuais (Xvfb + x11vnc + noVNC) para processadores
# VERSÃO: 1.0
# AUTOR: PROSPER-ERP-AUTOMATION
# ================================================================================
#
# USAGE:
#   ./iniciar_vnc_displays.sh start    # Inicia todos os displays
#   ./iniciar_vnc_displays.sh stop     # Para todos os displays
#   ./iniciar_vnc_displays.sh restart  # Reinicia todos os displays
#   ./iniciar_vnc_displays.sh status   # Verifica status de todos os displays
#
# MAPEAMENTO:
#   Display :1  → VNC 6080 → API 6090
#   Display :2  → VNC 6081 → API 6091
#   Display :3  → VNC 6082 → API 6092
#   Display :4  → VNC 6083 → API 6093
#   Display :5  → VNC 6084 → API 6094
#   Display :6  → VNC 6085 → API 6095
#   Display :7  → VNC 6086 → API 6096
#   Display :8  → VNC 6087 → API 6097
#   Display :9  → VNC 6088 → API 6098
#   Display :10 → VNC 6089 → API 6099
# ================================================================================

set -e

# ================================================================================
# CONFIGURAÇÕES
# ================================================================================

# Número de displays a criar
NUM_DISPLAYS=10

# Diretório para PIDs
PID_DIR="/tmp/vnc-pids"

# Diretório para logs
LOG_DIR="/tmp/vnc-logs"

# Servidor IP (AWS)
SERVER_IP="${SERVER_IP:-3.148.126.73}"

# Porta base VNC (6080, 6081, 6082...)
VNC_PORT_BASE=6080

# Porta base x11vnc (5900, 5901, 5902...)
X11VNC_PORT_BASE=5900

# Resolução do display
RESOLUTION="1920x1080x24"

# ================================================================================
# CORES PARA OUTPUT
# ================================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ================================================================================
# FUNÇÕES AUXILIARES
# ================================================================================

print_header() {
    echo -e "${CYAN}================================================================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}================================================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# ================================================================================
# CRIAR DIRETÓRIOS
# ================================================================================

setup_directories() {
    mkdir -p "$PID_DIR"
    mkdir -p "$LOG_DIR"
}

# ================================================================================
# VERIFICAR SE DISPLAY ESTÁ RODANDO
# ================================================================================

is_display_running() {
    local display_num=$1

    # Verificar Xvfb
    if ps aux | grep -v grep | grep -q "Xvfb :${display_num}"; then
        return 0
    fi
    return 1
}

is_x11vnc_running() {
    local display_num=$1
    local port=$((X11VNC_PORT_BASE + display_num - 1))

    if netstat -tlnp 2>/dev/null | grep -q ":${port}"; then
        return 0
    fi
    return 1
}

is_novnc_running() {
    local display_num=$1
    local port=$((VNC_PORT_BASE + display_num - 1))

    if netstat -tlnp 2>/dev/null | grep -q ":${port}"; then
        return 0
    fi
    return 1
}

# ================================================================================
# INICIAR UM DISPLAY
# ================================================================================

start_display() {
    local display_num=$1
    local vnc_port=$((VNC_PORT_BASE + display_num - 1))
    local x11vnc_port=$((X11VNC_PORT_BASE + display_num - 1))
    local api_port=$((vnc_port + 10))

    echo ""
    print_info "Iniciando Display :${display_num} (VNC: ${vnc_port}, API: ${api_port})"

    # Verificar se já está rodando
    if is_display_running $display_num; then
        print_warning "Display :${display_num} já está rodando (Xvfb)"
    else
        # Limpar locks do X11
        rm -f /tmp/.X${display_num}-lock 2>/dev/null || true
        rm -rf /tmp/.X11-unix/X${display_num} 2>/dev/null || true

        # Iniciar Xvfb
        Xvfb :${display_num} -screen 0 ${RESOLUTION} -ac +extension GLX +render -noreset \
            > "${LOG_DIR}/xvfb-${display_num}.log" 2>&1 &

        local xvfb_pid=$!
        echo $xvfb_pid > "${PID_DIR}/xvfb-${display_num}.pid"

        sleep 2

        # Verificar se iniciou
        if ps -p $xvfb_pid > /dev/null; then
            print_success "Xvfb :${display_num} iniciado (PID: ${xvfb_pid})"
        else
            print_error "Falha ao iniciar Xvfb :${display_num}"
            return 1
        fi
    fi

    # Verificar x11vnc
    if is_x11vnc_running $display_num; then
        print_warning "x11vnc já está rodando na porta ${x11vnc_port}"
    else
        # Iniciar x11vnc
        x11vnc -display :${display_num} -forever -nopw -shared -quiet -bg \
            -rfbport ${x11vnc_port} \
            -o "${LOG_DIR}/x11vnc-${display_num}.log" 2>&1

        sleep 1

        if is_x11vnc_running $display_num; then
            print_success "x11vnc iniciado na porta ${x11vnc_port}"
        else
            print_error "Falha ao iniciar x11vnc na porta ${x11vnc_port}"
        fi
    fi

    # Verificar noVNC
    if is_novnc_running $display_num; then
        print_warning "noVNC já está rodando na porta ${vnc_port}"
    else
        # Tentar iniciar noVNC usando novnc_proxy
        if [ -f "/home/ubuntu/noVNC/utils/novnc_proxy" ]; then
            cd /home/ubuntu/noVNC
            ./utils/novnc_proxy --vnc localhost:${x11vnc_port} --listen ${vnc_port} \
                > "${LOG_DIR}/novnc-${display_num}.log" 2>&1 &

            local novnc_pid=$!
            echo $novnc_pid > "${PID_DIR}/novnc-${display_num}.pid"

            sleep 2

            if is_novnc_running $display_num; then
                print_success "noVNC iniciado na porta ${vnc_port} (PID: ${novnc_pid})"
            else
                print_error "Falha ao iniciar noVNC na porta ${vnc_port}"
            fi
        elif command -v websockify &> /dev/null; then
            websockify --web=/usr/share/novnc/ ${vnc_port} localhost:${x11vnc_port} \
                > "${LOG_DIR}/novnc-${display_num}.log" 2>&1 &

            local novnc_pid=$!
            echo $novnc_pid > "${PID_DIR}/novnc-${display_num}.pid"

            sleep 2

            if is_novnc_running $display_num; then
                print_success "noVNC iniciado na porta ${vnc_port} (PID: ${novnc_pid})"
            else
                print_error "Falha ao iniciar noVNC na porta ${vnc_port}"
            fi
        else
            print_warning "noVNC não encontrado (nem em /home/ubuntu/noVNC nem websockify)"
        fi
    fi

    print_info "Display :${display_num} → http://${SERVER_IP}:${vnc_port}/vnc.html"
}

# ================================================================================
# PARAR UM DISPLAY
# ================================================================================

stop_display() {
    local display_num=$1

    echo ""
    print_info "Parando Display :${display_num}..."

    # Parar noVNC
    if [ -f "${PID_DIR}/novnc-${display_num}.pid" ]; then
        local novnc_pid=$(cat "${PID_DIR}/novnc-${display_num}.pid")
        if ps -p $novnc_pid > /dev/null 2>&1; then
            kill $novnc_pid 2>/dev/null || true
            print_success "noVNC parado (PID: ${novnc_pid})"
        fi
        rm -f "${PID_DIR}/novnc-${display_num}.pid"
    fi

    # Parar x11vnc
    local x11vnc_port=$((X11VNC_PORT_BASE + display_num - 1))
    pkill -f "x11vnc.*:${display_num}" 2>/dev/null || true
    print_success "x11vnc parado (porta ${x11vnc_port})"

    # Parar Xvfb
    if [ -f "${PID_DIR}/xvfb-${display_num}.pid" ]; then
        local xvfb_pid=$(cat "${PID_DIR}/xvfb-${display_num}.pid")
        if ps -p $xvfb_pid > /dev/null 2>&1; then
            kill $xvfb_pid 2>/dev/null || true
            print_success "Xvfb parado (PID: ${xvfb_pid})"
        fi
        rm -f "${PID_DIR}/xvfb-${display_num}.pid"
    fi

    # Limpar locks
    rm -f /tmp/.X${display_num}-lock 2>/dev/null || true
    rm -rf /tmp/.X11-unix/X${display_num} 2>/dev/null || true
}

# ================================================================================
# STATUS DE UM DISPLAY
# ================================================================================

status_display() {
    local display_num=$1
    local vnc_port=$((VNC_PORT_BASE + display_num - 1))
    local x11vnc_port=$((X11VNC_PORT_BASE + display_num - 1))
    local api_port=$((vnc_port + 10))

    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}Display :${display_num}${NC} │ VNC: ${vnc_port} │ API: ${api_port}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Xvfb
    if is_display_running $display_num; then
        local xvfb_pid=$(ps aux | grep -v grep | grep "Xvfb :${display_num}" | awk '{print $2}')
        print_success "Xvfb      : Rodando (PID: ${xvfb_pid})"
    else
        print_error "Xvfb      : NÃO está rodando"
    fi

    # x11vnc
    if is_x11vnc_running $display_num; then
        print_success "x11vnc    : Rodando (porta ${x11vnc_port})"
    else
        print_error "x11vnc    : NÃO está rodando"
    fi

    # noVNC
    if is_novnc_running $display_num; then
        print_success "noVNC     : Rodando (porta ${vnc_port})"
        echo -e "           ${BLUE}URL: http://${SERVER_IP}:${vnc_port}/vnc.html${NC}"
    else
        print_error "noVNC     : NÃO está rodando"
    fi
}

# ================================================================================
# COMANDOS PRINCIPAIS
# ================================================================================

cmd_start() {
    print_header "🚀 INICIANDO ${NUM_DISPLAYS} DISPLAYS VNC"

    setup_directories

    for i in $(seq 1 $NUM_DISPLAYS); do
        start_display $i
    done

    echo ""
    print_header "✅ INICIALIZAÇÃO CONCLUÍDA"
    echo ""
    print_info "Para ver o status: ./iniciar_vnc_displays.sh status"
    print_info "Para parar tudo: ./iniciar_vnc_displays.sh stop"
    echo ""
}

cmd_stop() {
    print_header "🛑 PARANDO TODOS OS DISPLAYS VNC"

    for i in $(seq 1 $NUM_DISPLAYS); do
        stop_display $i
    done

    echo ""
    print_header "✅ TODOS OS DISPLAYS FORAM PARADOS"
    echo ""
}

cmd_restart() {
    print_header "🔄 REINICIANDO TODOS OS DISPLAYS VNC"

    cmd_stop
    sleep 3
    cmd_start
}

cmd_status() {
    print_header "📊 STATUS DOS DISPLAYS VNC"

    for i in $(seq 1 $NUM_DISPLAYS); do
        status_display $i
    done

    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    print_header "📋 RESUMO"

    local running=0
    local stopped=0

    for i in $(seq 1 $NUM_DISPLAYS); do
        if is_display_running $i && is_x11vnc_running $i && is_novnc_running $i; then
            running=$((running + 1))
        else
            stopped=$((stopped + 1))
        fi
    done

    echo ""
    print_success "Displays rodando: ${running}/${NUM_DISPLAYS}"

    if [ $stopped -gt 0 ]; then
        print_warning "Displays parados: ${stopped}/${NUM_DISPLAYS}"
    fi

    echo ""
}

cmd_help() {
    echo ""
    echo "USAGE: $0 {start|stop|restart|status|help}"
    echo ""
    echo "COMANDOS:"
    echo "  start    - Inicia todos os ${NUM_DISPLAYS} displays VNC"
    echo "  stop     - Para todos os displays VNC"
    echo "  restart  - Reinicia todos os displays VNC"
    echo "  status   - Mostra status de todos os displays"
    echo "  help     - Mostra esta ajuda"
    echo ""
    echo "MAPEAMENTO DE PORTAS:"
    echo "  Display :1  → VNC 6080 → API 6090"
    echo "  Display :2  → VNC 6081 → API 6091"
    echo "  Display :3  → VNC 6082 → API 6092"
    echo "  ..."
    echo "  Display :10 → VNC 6089 → API 6099"
    echo ""
    echo "LOGS:"
    echo "  Diretório: ${LOG_DIR}"
    echo ""
    echo "PIDs:"
    echo "  Diretório: ${PID_DIR}"
    echo ""
}

# ================================================================================
# MAIN
# ================================================================================

main() {
    local command=${1:-help}

    case "$command" in
        start)
            cmd_start
            ;;
        stop)
            cmd_stop
            ;;
        restart)
            cmd_restart
            ;;
        status)
            cmd_status
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            print_error "Comando inválido: $command"
            cmd_help
            exit 1
            ;;
    esac
}

# Executar main com argumentos
main "$@"
