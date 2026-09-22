#!/usr/bin/env bash
# bancada_pg.sh - um Postgres DESCARTAVEL, da MESMA imagem do de producao, para provar
# migrations e testes de integracao sem encostar no prosperedb.
#
#   scripts/bancada_pg.sh subir      sobe o container, cria as roles e aplica database/erp_*.sql
#   scripts/bancada_pg.sh derrubar   remove o container (o dado e descartado)
#   scripts/bancada_pg.sh psql       abre um psql administrativo na bancada
#   scripts/bancada_pg.sh env        imprime os exports que os testes de integracao leem
#
# Por que a mesma imagem: e o Postgres 17 com as mesmas extensoes do de producao.
# Por que roles com LOGIN aqui: em producao app_erp_automation NAO tem login (o
# Guardian cria logins efemeros); na bancada o teste conecta direto como ela, com
# senha gerada na hora e guardada em data/bancada_pg.env (600, ignorado).
#
# A migration entra pela MESMA porta que em producao: database/aplicar.sh, com
# DB_ADMIN_* apontando para a bancada (o aplicar.sh nao le .env quando DB_ADMIN_USER
# ja vem do ambiente - ver o comentario la).
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOME="${BANCADA_NOME:-erp-bancada-pg}"
PORTA="${BANCADA_PORTA:-55432}"
IMAGEM="${BANCADA_IMAGEM:-postgres-postgres}"
# BANCADA_REDE: rede Docker a que a bancada tambem se liga (ex.: prospere-network), para um
# container de producao alcancar a bancada pelo nome - e como o ensaio entra pela porta
# de producao (run_agendado.sh no container) com ERP_EXECUCAO_DSN apontando para ca.
REDE="${BANCADA_REDE:-}"
ENV_ARQ="$RAIZ/data/bancada_pg.env"

# sem pipe: `tr </dev/urandom | head` leva SIGPIPE e, com pipefail, mata o script em silencio
gerar_senha() { python3 -c 'import secrets; print(secrets.token_hex(12))'; }

subir() {
    if docker ps -a --format '{{.Names}}' | grep -qx "$NOME"; then
        echo "ja existe: $NOME (use 'derrubar' antes)"; exit 1
    fi
    mkdir -p "$(dirname "$ENV_ARQ")"
    local admin_pw app_pw
    admin_pw="$(gerar_senha)"; app_pw="$(gerar_senha)"
    umask 077
    cat > "$ENV_ARQ" <<EOF
BANCADA_ADMIN_DSN=postgresql://postgres:${admin_pw}@127.0.0.1:${PORTA}/prosperedb
ERP_BANCADA_DSN=postgresql://app_erp_automation:${app_pw}@127.0.0.1:${PORTA}/prosperedb
EOF
    docker run -d --name "$NOME" -p "127.0.0.1:${PORTA}:5432" \
        -e POSTGRES_PASSWORD="$admin_pw" -e POSTGRES_DB=prosperedb \
        -e TZ=America/Sao_Paulo --shm-size=256m "$IMAGEM" \
        -c timezone=America/Sao_Paulo -c log_timezone=America/Sao_Paulo >/dev/null
    if [[ -n "$REDE" ]]; then
        docker network connect "$REDE" "$NOME" && echo "ligada tambem a rede $REDE (nome: $NOME:5432)"
    fi
    echo "aguardando o Postgres..."
    for _ in $(seq 1 60); do
        docker exec "$NOME" pg_isready -U postgres -d prosperedb >/dev/null 2>&1 && break
        sleep 1
    done
    docker exec "$NOME" pg_isready -U postgres -d prosperedb >/dev/null
    # As roles que a migration cita. Em producao existem; aqui nascem vazias.
    docker exec -i "$NOME" psql -U postgres -d prosperedb -v ON_ERROR_STOP=1 -q <<EOF
CREATE ROLE app_erp_automation LOGIN PASSWORD '${app_pw}';
CREATE ROLE dev_user NOLOGIN;
CREATE ROLE app_process_automation NOLOGIN;
CREATE ROLE app_data_hub NOLOGIN;
CREATE ROLE app_hub_orch NOLOGIN;
CREATE ROLE app_forms_hub NOLOGIN;
CREATE ROLE app_crm NOLOGIN;
CREATE ROLE app_metas NOLOGIN;
CREATE ROLE app_scatambulo NOLOGIN;
CREATE SCHEMA erp_automation AUTHORIZATION app_erp_automation;
EOF
    echo "bancada no ar: $NOME em 127.0.0.1:${PORTA}"
    echo "aplicando database/erp_*.sql pelo aplicar.sh..."
    # erp_001..003 movem/ajustam tabelas que so existem em producao: aqui elas nao
    # existem, e a 001 aborta por desenho ("nao existe e o destino tambem nao").
    # So a 004 em diante e aplicavel do zero; registra as tres no ledger como
    # "nao aplicaveis na bancada" para o aplicar.sh nao tentar.
    DB_ADMIN_HOST=127.0.0.1 DB_PORT="$PORTA" DB_NAME=prosperedb \
    DB_ADMIN_USER=postgres DB_ADMIN_PASSWORD="$admin_pw" \
    BANCADA_PULAR="erp_001_schema_erp_automation.sql erp_002_revogar_heranca_dev_user.sql erp_003_limpar_acl_herdada_da_mudanca.sql" \
        "$RAIZ/database/aplicar.sh"
    echo
    echo "para os testes de integracao:"
    env_exports
}

env_exports() {
    [[ -f "$ENV_ARQ" ]] || { echo "bancada nao esta no ar (sem $ENV_ARQ)"; exit 1; }
    sed 's/^/export /' "$ENV_ARQ"
}

derrubar() {
    docker rm -f "$NOME" >/dev/null 2>&1 && echo "removido: $NOME" || echo "nao existia: $NOME"
    rm -f "$ENV_ARQ"
}

psql_admin() {
    [[ -f "$ENV_ARQ" ]] || { echo "bancada nao esta no ar"; exit 1; }
    docker exec -it "$NOME" psql -U postgres -d prosperedb
}

case "${1:-}" in
    subir) subir ;;
    derrubar) derrubar ;;
    psql) psql_admin ;;
    env) env_exports ;;
    *) sed -n '2,12p' "$0"; exit 1 ;;
esac
