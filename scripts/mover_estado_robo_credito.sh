#!/usr/bin/env bash
# Tira o estado do robo_credito de dentro de src/ e poe em data/, junto dos
# outros robos.
#
# Por que existe: ate 12/08/2026 o robo gravava `controle_downloads.csv` (1.335
# operacoes) dentro da propria pasta de codigo. Os robos de remessa e retorno
# sempre gravaram em /app/data/<robo>/.
#
# A troca e so um `cp`: o `config.py` ja usa data/ assim que o arquivo aparecer la
# (funcao `_arquivo_estado`). Nao ha janela em que o robo leia controle vazio.
#
# ⚠️ POR QUE ESTE SCRIPT SE RECUSA A RODAR COM O ROBO NO AR
# `banco._salvar_controle()` reescreve o CSV INTEIRO a cada gravacao. Copiar no
# meio de um run produziria uma copia velha; o run seguinte leria essa copia e
# regravaria por cima — perdendo tudo o que o run atual escreveu depois da copia.
# O robo roda das 07:45 as ~18:52 em dia util (timeout 11h10).
#
#   ./scripts/mover_estado_robo_credito.sh              faz a troca
#   ./scripts/mover_estado_robo_credito.sh --dry-run    so confere, nao mexe
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORIGEM="$RAIZ/src/processors/web/robo_credito"
DESTINO="$RAIZ/data/robo_credito"
ARQUIVOS=(controle_downloads.csv ops_move_revisar_manual.txt ops_digitais_revisar_manual.txt)
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# --- Porta 1: o robo nao pode estar rodando -------------------------------- #
if docker exec erp-automation pgrep -f "robo_analise_credito" >/dev/null 2>&1; then
  echo "ABORTADO: o robo_analise_credito esta RODANDO agora." >&2
  echo "           Copiar o controle no meio do run perde o historico." >&2
  echo "           Ele termina por volta das 18:52 em dia util. Rode depois." >&2
  exit 1
fi
echo "ok: robo_analise_credito nao esta rodando"

# --- Porta 2: nada em curso pelo orquestrador ------------------------------ #
em_curso=$(docker exec -i postgres psql -U prospere -d prosperedb -qtAX -c \
  "SELECT count(*) FROM hub_orchestration.task_execucao
   WHERE task_nome='robo_analise_credito' AND status='running'" 2>/dev/null || echo 0)
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
docker exec -w /app/src/processors/web/robo_credito erp-automation python -c "
import config, banco
print('  caminho :', config.ARQ_CONTROLE_DOWNLOAD)
print('  registros:', len(banco.carregar_controle()))
"
echo
echo "Se 'registros' bate com o que havia antes, a troca terminou."
echo "Os .migrado podem ser apagados depois da proxima execucao verde."
