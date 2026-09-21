#!/bin/bash
# ================================================================================
# SCRIPT: instalar_servicos_vnc.sh
# DESCRIÇÃO: Instala serviços systemd para displays VNC (Xvfb + x11vnc + noVNC)
# VERSÃO: 1.0
# AUTOR: PROSPER-ERP-AUTOMATION
# ================================================================================
#
# USAGE:
#   sudo ./instalar_servicos_vnc.sh install   # Instala e habilita os serviços
#   sudo ./instalar_servicos_vnc.sh uninstall # Remove os serviços
#   sudo ./instalar_servicos_vnc.sh start     # Inicia todos os serviços
#   sudo ./instalar_servicos_vnc.sh stop      # Para todos os serviços
#   sudo ./instalar_servicos_vnc.sh status    # Verifica status dos serviços
#
# ================================================================================

set -e

# ================================================================================
# CONFIGURAÇÕES (idêntico ao script original)
# ================================================================================

NUM_DISPLAYS=10
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ================================================================================
# CORES PARA OUTPUT
# ================================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

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
# VERIFICAR PERMISSÕES
# ================================================================================

check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "Este script precisa ser executado como root (use sudo)"
        exit 1
    fi
}

# ================================================================================
# INSTALAR SERVIÇOS
# ================================================================================

cmd_install() {
    check_root

    print_header "📦 INSTALANDO SERVIÇOS SYSTEMD PARA ${NUM_DISPLAYS} DISPLAYS VNC"

    # Copiar arquivos de serviço
    print_info "Copiando arquivos de serviço para /etc/systemd/system/..."

    cp "${SCRIPT_DIR}/xvfb@.service" /etc/systemd/system/
    print_success "xvfb@.service copiado"

    cp "${SCRIPT_DIR}/x11vnc@.service" /etc/systemd/system/
    print_success "x11vnc@.service copiado"

    cp "${SCRIPT_DIR}/novnc@.service" /etc/systemd/system/
    print_success "novnc@.service copiado"

    # Recarregar systemd
    print_info "Recarregando configuração do systemd..."
    systemctl daemon-reload
    print_success "Systemd recarregado"

    # Habilitar serviços para auto-start
    print_info "Habilitando serviços para iniciar automaticamente no boot..."

    for i in $(seq 1 $NUM_DISPLAYS); do
        systemctl enable xvfb@${i}.service
        systemctl enable x11vnc@${i}.service
        systemctl enable novnc@${i}.service
        print_success "Display :${i} habilitado (VNC porta 607$((i-1)))"
    done

    echo ""
    print_header "✅ INSTALAÇÃO CONCLUÍDA"
    echo ""
    print_info "Serviços instalados e habilitados para iniciar no boot"
    print_info "Para iniciar agora: sudo ./instalar_servicos_vnc.sh start"
    print_info "Para verificar status: sudo ./instalar_servicos_vnc.sh status"
    echo ""
}

# ================================================================================
# DESINSTALAR SERVIÇOS
# ================================================================================

cmd_uninstall() {
    check_root

    print_header "🗑️  DESINSTALANDO SERVIÇOS SYSTEMD VNC"

    # Parar todos os serviços
    print_info "Parando todos os serviços..."

    for i in $(seq 1 $NUM_DISPLAYS); do
        systemctl stop novnc@${i}.service 2>/dev/null || true
        systemctl stop x11vnc@${i}.service 2>/dev/null || true
        systemctl stop xvfb@${i}.service 2>/dev/null || true

        systemctl disable novnc@${i}.service 2>/dev/null || true
        systemctl disable x11vnc@${i}.service 2>/dev/null || true
        systemctl disable xvfb@${i}.service 2>/dev/null || true
    done

    print_success "Todos os serviços parados e desabilitados"

    # Remover arquivos de serviço
    print_info "Removendo arquivos de serviço..."

    rm -f /etc/systemd/system/xvfb@.service
    rm -f /etc/systemd/system/x11vnc@.service
    rm -f /etc/systemd/system/novnc@.service

    print_success "Arquivos de serviço removidos"

    # Recarregar systemd
    print_info "Recarregando configuração do systemd..."
    systemctl daemon-reload
    print_success "Systemd recarregado"

    echo ""
    print_header "✅ DESINSTALAÇÃO CONCLUÍDA"
    echo ""
}

# ================================================================================
# INICIAR SERVIÇOS
# ================================================================================

cmd_start() {
    check_root

    print_header "🚀 INICIANDO ${NUM_DISPLAYS} DISPLAYS VNC"

    for i in $(seq 1 $NUM_DISPLAYS); do
        local vnc_port=$((6080 + i - 1))
        local api_port=$((vnc_port + 10))

        echo ""
        print_info "Iniciando Display :${i} (VNC: ${vnc_port}, API: ${api_port})"

        systemctl start xvfb@${i}.service
        sleep 1
        systemctl start x11vnc@${i}.service
        sleep 1
        systemctl start novnc@${i}.service

        # Verificar status
        if systemctl is-active --quiet xvfb@${i}.service && \
           systemctl is-active --quiet x11vnc@${i}.service && \
           systemctl is-active --quiet novnc@${i}.service; then
            print_success "Display :${i} iniciado com sucesso"
        else
            print_error "Falha ao iniciar Display :${i}"
        fi
    done

    echo ""
    print_header "✅ INICIALIZAÇÃO CONCLUÍDA"
    echo ""
    print_info "Para ver status detalhado: sudo ./instalar_servicos_vnc.sh status"
    echo ""
}

# ================================================================================
# PARAR SERVIÇOS
# ================================================================================

cmd_stop() {
    check_root

    print_header "🛑 PARANDO TODOS OS DISPLAYS VNC"

    for i in $(seq 1 $NUM_DISPLAYS); do
        echo ""
        print_info "Parando Display :${i}..."

        systemctl stop novnc@${i}.service 2>/dev/null || true
        systemctl stop x11vnc@${i}.service 2>/dev/null || true
        systemctl stop xvfb@${i}.service 2>/dev/null || true

        print_success "Display :${i} parado"
    done

    echo ""
    print_header "✅ TODOS OS DISPLAYS FORAM PARADOS"
    echo ""
}

# ================================================================================
# REINICIAR SERVIÇOS
# ================================================================================

cmd_restart() {
    check_root

    print_header "🔄 REINICIANDO TODOS OS DISPLAYS VNC"

    cmd_stop
    sleep 3
    cmd_start
}

# ================================================================================
# STATUS DOS SERVIÇOS
# ================================================================================

cmd_status() {
    check_root

    print_header "📊 STATUS DOS SERVIÇOS VNC"

    local running=0
    local stopped=0

    for i in $(seq 1 $NUM_DISPLAYS); do
        local vnc_port=$((6080 + i - 1))
        local api_port=$((vnc_port + 10))

        echo ""
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}Display :${i}${NC} │ VNC: ${vnc_port} │ API: ${api_port}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

        # Xvfb
        if systemctl is-active --quiet xvfb@${i}.service; then
            print_success "Xvfb      : Rodando"
        else
            print_error "Xvfb      : Parado"
        fi

        # x11vnc
        if systemctl is-active --quiet x11vnc@${i}.service; then
            print_success "x11vnc    : Rodando"
        else
            print_error "x11vnc    : Parado"
        fi

        # noVNC
        if systemctl is-active --quiet novnc@${i}.service; then
            print_success "noVNC     : Rodando"
            echo -e "           ${BLUE}URL: http://3.148.126.73:${vnc_port}/vnc.html${NC}"

            # Contar como rodando apenas se todos os 3 estiverem ativos
            if systemctl is-active --quiet xvfb@${i}.service && \
               systemctl is-active --quiet x11vnc@${i}.service; then
                running=$((running + 1))
            else
                stopped=$((stopped + 1))
            fi
        else
            print_error "noVNC     : Parado"
            stopped=$((stopped + 1))
        fi
    done

    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    print_header "📋 RESUMO"
    echo ""
    print_success "Displays rodando: ${running}/${NUM_DISPLAYS}"

    if [ $stopped -gt 0 ]; then
        print_warning "Displays parados: ${stopped}/${NUM_DISPLAYS}"
    fi

    echo ""
    print_info "Comandos úteis:"
    echo -e "  ${BLUE}journalctl -u xvfb@1 -f${NC}      # Ver logs do Xvfb Display :1"
    echo -e "  ${BLUE}journalctl -u x11vnc@1 -f${NC}    # Ver logs do x11vnc Display :1"
    echo -e "  ${BLUE}journalctl -u novnc@1 -f${NC}     # Ver logs do noVNC Display :1"
    echo -e "  ${BLUE}systemctl restart xvfb@1${NC}     # Reiniciar Xvfb Display :1"
    echo ""
}

# ================================================================================
# HELP
# ================================================================================

cmd_help() {
    echo ""
    echo "USAGE: sudo $0 {install|uninstall|start|stop|restart|status|help}"
    echo ""
    echo "COMANDOS:"
    echo "  install    - Instala e habilita os serviços systemd (${NUM_DISPLAYS} displays)"
    echo "  uninstall  - Remove os serviços systemd"
    echo "  start      - Inicia todos os serviços VNC"
    echo "  stop       - Para todos os serviços VNC"
    echo "  restart    - Reinicia todos os serviços VNC"
    echo "  status     - Mostra status detalhado de todos os serviços"
    echo "  help       - Mostra esta ajuda"
    echo ""
    echo "MAPEAMENTO DE PORTAS (idêntico ao script original):"
    echo "  Display :1  → VNC 6080 → API 6090"
    echo "  Display :2  → VNC 6081 → API 6091"
    echo "  Display :3  → VNC 6082 → API 6092"
    echo "  ..."
    echo "  Display :10 → VNC 6089 → API 6099"
    echo ""
    echo "LOGS:"
    echo "  journalctl -u xvfb@1 -f      # Ver logs do Xvfb Display :1"
    echo "  journalctl -u x11vnc@2 -f    # Ver logs do x11vnc Display :2"
    echo "  journalctl -u novnc@3 -f     # Ver logs do noVNC Display :3"
    echo ""
    echo "CONTROLE INDIVIDUAL:"
    echo "  sudo systemctl start xvfb@1       # Iniciar apenas Xvfb Display :1"
    echo "  sudo systemctl stop x11vnc@2      # Parar apenas x11vnc Display :2"
    echo "  sudo systemctl restart novnc@3    # Reiniciar apenas noVNC Display :3"
    echo "  sudo systemctl status xvfb@4      # Ver status do Xvfb Display :4"
    echo ""
}

# ================================================================================
# MAIN
# ================================================================================

main() {
    local command=${1:-help}

    case "$command" in
        install)
            cmd_install
            ;;
        uninstall)
            cmd_uninstall
            ;;
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
