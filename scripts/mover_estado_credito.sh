#!/usr/bin/env bash
# Tira o estado do credito de dentro de src/ e poe em data/, junto dos
# outros robos.
#
# Por que existe: ate 12/08/2026 o robo gravava `controle_downloads.csv` (1.335
# operacoes) dentro da propria pasta de codigo. Os robos de remessa e retorno
# sempre gravaram em /app/data/<robo>/.
#
# A troca e so um `cp`: o `config.py` ja usa data/ assim que o arquivo aparecer la
# (funcao `_arquivo_estado`). Nao ha janela em que o robo leia controle vazio.
#
# Desde 22/09/2026 o controle dos downloads e evento no banco (credito/banco.py) e o
# controle_downloads.csv nao e mais lido nem escrito: sobraram as duas listas de
# revisao manual.
#
# ⚠️ POR QUE ESTE SCRIPT SE RECUSA A RODAR COM O ROBO NO AR
# As listas sao gravadas por append durante o run. Copiar no meio de um run
# produziria uma copia velha, sem o que o run escreveu depois da copia.
# O robo roda das 07:45 as ~18:52 em dia util (timeout 11h10).
#
#   ./scripts/mover_estado_credito.sh              faz a troca
#   ./scripts/mover_estado_credito.sh --dry-run    so confere, nao mexe
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORIGEM="$RAIZ/src/processors/web/credito"
DESTINO="$RAIZ/data/robo_credito"
ARQUIVOS=(ops_move_revisar_manual.txt ops_digitais_revisar_manual.txt)
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# --- Porta 1: o robo nao pode estar rodando -------------------------------- #
if docker exec erp-automation pgrep -f "analisar_credito" >/dev/null 2>&1; then
  echo "ABORTADO: o analisar_credito_operacao esta RODANDO agora." >&2
  echo "           Copiar o controle no meio do run perde o historico." >&2
  echo "           Ele termina por volta das 18:52 em dia util. Rode depois." >&2
  exit 1
fi
echo "ok: analisar_credito_operacao nao esta rodando"

# --- Porta 2: nada em curso pelo orquestrador ------------------------------ #
em_curso=$(docker exec -i postgres psql -U prospere -d prosperedb -qtAX -c \
  "SELECT count(*) FROM hub_orchestration.task_execucao
   WHERE task_nome='analisar_credito_operacao' AND status='running'" 2>/dev/null || echo 0)
if [[ "${em_curso//[[:space:]]/}" != "0" ]]; then
  echo "ABORTADO: o orquestrador marca uma execucao como 'running'." >&2
  exit 1
fi
echo "ok: nenhuma execucao 'running' no orquestrador"

mkdir -p "$DESTINO"

for nome in "${ARQUIVOS[@]}"; do
  antigo="$ORIGEM/$nome"
  novo="$DESTINO/$nome"

  if [[ -f "$novo" ]]; then
    echo "  ja migrado: $nome"
    continue
  fi
  if [[ ! -f "$antigo" ]]; then
    echo "  nao existe:  $nome (nada a fazer)"
    continue
  fi

  linhas_antes=$(wc -l < "$antigo")
  if (( DRY_RUN )); then
    echo "  MIGRARIA:    $nome ($linhas_antes linhas)"
    continue
  fi

  cp -p "$antigo" "$novo"
  linhas_depois=$(wc -l < "$novo")
  if [[ "$linhas_antes" != "$linhas_depois" ]]; then
    echo "ERRO: copia de $nome saiu com $linhas_depois linhas, esperado $linhas_antes." >&2
    rm -f "$novo"
    exit 1
  fi

  # O antigo NAO e apagado — vira .migrado, rede de seguranca ate a proxima
  # execucao confirmar. `_arquivo_estado()` ja ignora o sufixo.
  mv "$antigo" "$antigo.migrado"
  echo "  migrado:     $nome ($linhas_antes linhas) -> data/robo_credito/"
done

if (( DRY_RUN )); then
  echo; echo "nada foi alterado (--dry-run)."
  exit 0
fi

# --- Verificacao: o robo enxerga o mesmo controle no lugar novo? ----------- #
echo
echo "conferindo pelo caminho que o robo realmente usa..."
docker exec -w /app/src/processors/web/credito erp-automation python -c "
import config
print('  revisar move   :', config.ARQ_MOVE_REVISAR)
"
echo
echo "Se o caminho aponta para data/robo_credito, a troca terminou."
echo "Os .migrado podem ser apagados depois da proxima execucao verde."
