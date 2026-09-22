#!/usr/bin/env bash
# Aplica as migrations de database/ na ordem, uma vez cada.
#
# Roda com credencial ADMINISTRATIVA (DB_ADMIN_USER/DB_ADMIN_PASSWORD), nao com a
# credencial de runtime: app_erp_automation nao tem — e nao deve ter — poder para
# conceder e revogar permissao.
#
#   ./database/aplicar.sh              aplica o que falta
#   ./database/aplicar.sh --dry-run    lista o que falta, sem aplicar
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR_MIGRATIONS="$RAIZ/database"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# Credencial explicita no ambiente VENCE os arquivos: e assim que a bancada
# (scripts/bancada_pg.sh) aponta o runner para o Postgres descartavel sem que o
# .env do projeto o devolva para producao. Sem DB_ADMIN_USER no ambiente, le
# shared.env primeiro e .env do projeto por cima (mesma ordem do docker-compose).
if [[ -z "${DB_ADMIN_USER:-}" ]]; then
  for arquivo in /home/prospere/docker/shared.env "$RAIZ/.env"; do
    [[ -f "$arquivo" ]] && set -a && . "$arquivo" && set +a
  done
fi

# O runner roda do HOST, onde o nome de rede "postgres" nao resolve.
PGHOST="${DB_ADMIN_HOST:-localhost}"
PGPORT="${DB_PORT:-5432}"
PGDATABASE="${DB_NAME:-prosperedb}"
PGUSER="${DB_ADMIN_USER:?defina DB_ADMIN_USER}"
PGPASSWORD="${DB_ADMIN_PASSWORD:?defina DB_ADMIN_PASSWORD}"
PGSSLMODE=disable
export PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGSSLMODE
echo "alvo: ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"

# BANCADA_PULAR: migrations que so fazem sentido em producao (movem tabelas que a
# bancada nao tem) entram no ledger como puladas, sem rodar. NUNCA na porta de
# producao: pular migration la e corromper o ledger.
# RECONCILIAR + RECONCILIAR_MOTIVO: o ledger diz que um arquivo foi aplicado com um
# conteudo, e o arquivo no disco tem outro. Acontece com migration aplicada ANTES de o
# projeto versionar o database/ — o original nao existe mais para comparar. Isto NAO roda
# SQL nenhum: so admite, no proprio ledger e com motivo obrigatorio, que o conteudo de hoje
# foi conferido contra o estado real do banco. Reaplicar nao e opcao quando a migration
# referencia objeto que outro projeto ja renomeou.
# ⛔ Nunca use para "fazer passar" uma migration que voce editou e quer ver aplicada: essa
#    vai em arquivo novo. Aqui o conteudo novo nao e executado — ele so para de alarmar.
RECONCILIAR="${RECONCILIAR:-}"
RECONCILIAR_MOTIVO="${RECONCILIAR_MOTIVO:-}"
RECONCILIAR_MOTIVO="${RECONCILIAR_MOTIVO//\'/}"   # sem aspa simples: o motivo entra num literal SQL
if [[ -n "$RECONCILIAR" && -z "$RECONCILIAR_MOTIVO" ]]; then
  echo "ERRO: RECONCILIAR exige RECONCILIAR_MOTIVO (fica gravado no ledger)." >&2; exit 1
fi

BANCADA_PULAR="${BANCADA_PULAR:-}"
if [[ -n "$BANCADA_PULAR" && "$PGPORT" == "5432" ]]; then
  echo "ERRO: BANCADA_PULAR so vale na bancada (porta != 5432)." >&2; exit 1
fi

psql_q() { psql -v ON_ERROR_STOP=1 -qtAX -c "$1"; }

# Bootstrap do ledger. Idempotente; erp_001 repete o CREATE SCHEMA por ser o passo
# que o documenta.
# Guardado por existencia, nao por IF NOT EXISTS: o Postgres checa o privilegio de CREATE
# no banco/schema ANTES de ver que o objeto ja existe, e a sessao do Guardian nao tem
# (nem precisa de) CREATE no banco. Medido na bancada em 21/09/2026.
psql_q "
DO \$\$
BEGIN
    IF to_regnamespace('erp_automation') IS NULL THEN
        CREATE SCHEMA erp_automation AUTHORIZATION app_erp_automation;
    END IF;
    IF to_regclass('erp_automation.migration_aplicada') IS NULL THEN
        CREATE TABLE erp_automation.migration_aplicada (
            arquivo      TEXT PRIMARY KEY,
            sha256       TEXT        NOT NULL,
            aplicada_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
            aplicada_por TEXT        NOT NULL DEFAULT current_user
        );
        -- o ledger e do projeto, nunca da sessao que o criou: uma tmp_ do Guardian que o
        -- deixasse de posse dela o perderia no revogar (DROP OWNED). Medido na bancada.
        ALTER TABLE erp_automation.migration_aplicada OWNER TO app_erp_automation;
    END IF;
END \$\$;" >/dev/null

pendentes=0
for caminho in "$DIR_MIGRATIONS"/erp_*.sql; do
  [[ -e "$caminho" ]] || { echo "nenhuma migration em $DIR_MIGRATIONS"; exit 0; }
  arquivo="$(basename "$caminho")"
  hash_atual="$(sha256sum "$caminho" | cut -d' ' -f1)"
  hash_gravado="$(psql_q "SELECT sha256 FROM erp_automation.migration_aplicada WHERE arquivo = '$arquivo'")"

  if [[ -n "$hash_gravado" ]]; then
    if [[ "$hash_gravado" != "$hash_atual" ]]; then
      if [[ " $RECONCILIAR " == *" $arquivo "* ]]; then
        if (( DRY_RUN )); then
          echo "  RECONCILIARIA: $arquivo (ledger ${hash_gravado:0:12}... -> conteudo de hoje; nada e executado)"
        else
          psql_q "UPDATE erp_automation.migration_aplicada
                     SET sha256 = '$hash_atual',
                         aplicada_por = current_user || ' (reconciliada: $RECONCILIAR_MOTIVO)'
                   WHERE arquivo = '$arquivo'" >/dev/null
          echo "  reconciliada: $arquivo — conteudo de hoje aceito no ledger, SQL nao reexecutado"
        fi
        continue
      fi
      echo "ERRO: $arquivo ja foi aplicada e o conteudo MUDOU." >&2
      echo "      Migration aplicada e imutavel — corrija em arquivo novo." >&2
      echo "      Se a mudanca e anterior ao versionamento e o banco ja confere, use" >&2
      echo "      RECONCILIAR=\"$arquivo\" RECONCILIAR_MOTIVO=\"...\" (nao reexecuta SQL)." >&2
      exit 1
    fi
    echo "  ja aplicada: $arquivo"
    continue
  fi

  if [[ " $BANCADA_PULAR " == *" $arquivo "* ]]; then
    echo "  pulada (bancada): $arquivo"
    psql_q "INSERT INTO erp_automation.migration_aplicada (arquivo, sha256, aplicada_por)
            VALUES ('$arquivo', '$hash_atual', current_user || ' (pulada: bancada)')" >/dev/null
    continue
  fi
  pendentes=$((pendentes + 1))
  if (( DRY_RUN )); then
    echo "  PENDENTE:    $arquivo"
    continue
  fi

  echo "  aplicando:   $arquivo"
  # A migration inteira num unico psql, com ON_ERROR_STOP: qualquer erro aborta a
  # transacao que o proprio arquivo abre, e o ledger nao e gravado.
  psql -v ON_ERROR_STOP=1 -qX -f "$caminho"
  psql_q "INSERT INTO erp_automation.migration_aplicada (arquivo, sha256)
          VALUES ('$arquivo', '$hash_atual')" >/dev/null
done

if (( pendentes == 0 )); then
  echo "nada a aplicar."
elif (( DRY_RUN )); then
  echo "$pendentes pendente(s) — nada foi aplicado (--dry-run)."
else
  echo "$pendentes migration(s) aplicada(s)."
fi
