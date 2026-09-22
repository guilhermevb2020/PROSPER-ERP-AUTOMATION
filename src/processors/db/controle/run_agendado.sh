#!/bin/sh
# Wrapper do hub para a paridade CSV x banco (task comparar_controle_csv_banco).
# Sem navegador, sem display, sem trava do Smart: so le os CSVs em /app/data e o banco
# pelo Guardian (mesma identidade dos registros). Propaga o exit do python com o truque
# do $RC — o hub chama com dash e o tee esconderia o codigo (docs/COMO_SUBIR_UM_JOB.md).
# Exit: 0 paridade · 3 divergencia (o hub alerta) · 1 erro de leitura.
set -u
cd /app || exit 1
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1
LOGROBO="/app/logs/controle_paridade_$(date +%Y-%m-%d).log"
RC="/tmp/controle_paridade_rc.$$"
echo "===== inicio $(date '+%F %T %Z') =====" >> "$LOGROBO"
{ python /app/src/processors/db/controle/comparar_controle_csv_banco.py "$@"; echo $? > "$RC"; } 2>&1 | tee -a "$LOGROBO"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1)
rm -f "$RC"
echo "===== fim $(date '+%F %T %Z') exit=$CODIGO =====" >> "$LOGROBO"
exit "$CODIGO"
