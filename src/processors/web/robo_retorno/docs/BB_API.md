# Retorno reconstruído da API BB

Integrado no ERP em 09/09/2026 pelo commit `5ee7f65`, sem agendamento BB.
Os 14 arquivos de `src/` da mudança foram comparados byte a byte entre commit,
checkout principal e container. A publicação ocorreu pelo bind existente de
`/app/src`, sob a trava financeira, sem recriar o container.

O modo `--conta-bb-api` liga a conferência específica de `bb_api.py` e o controle
durável `bb_entrega.py`, usando o processador de retorno existente. Exige conta
Smart positiva e `--recibos-dir`. Não combina com depósito ou aceitação de conta
desconhecida. `--limite`, quando fornecido, deve ser positivo. `--arquivo` deve
ser um nome dentro da pasta. Ausência de um arquivo explicitamente solicitado
é pendência, não sucesso vazio.

```bash
# Prévia: upload e conferência, sem PROCESSAR_ARQUIVO.
sh /app/src/processors/web/robo_retorno/run_bb.sh --simular

# Processamento: somente depois de o produtor publicar o arquivo íntegro.
sh /app/src/processors/web/robo_retorno/run_bb.sh --pra-valer
```

O wrapper usa conta 395 e a pasta
`/app/data/retornos_a_processar/bb_api/retornos/producao/3770013/395`.
Sem argumento equivale à prévia. A flag real é obrigatória independentemente
do `DRY_RUN_RET` legado. Chrome usa o modo headless; sessão e autenticação são
as do processador existente, protegidas pela trava financeira comum.

## Identidade e recuperação

O controle usa conta e SHA-256 dos bytes, sem depender do CSV legado ou da
indicação de arquivo processado por nome do Smart. Sob trava exclusiva:

1. Confere os recibos anteriores do conteúdo.
2. Valida banco/conta e grade pelo processador existente.
3. Publica e sincroniza a intenção antes do passo irreversível.
4. Processa uma vez e grava o resultado antes de consultar críticas auxiliares.

Cada recibo é JSON atômico e imutável. Schema `prospere.retorno-bb-api.v1`;
metadados `conta_bb_api`, `tentativa` (UUID) e `etapa` (`intencao`/`resultado`).
Local: `_RESULTADOS/<conta>/<SHA-256>/<data>/`. O resultado preserva grade,
portão, resposta do Smart, contadores, identidade e estado final.

Uma confirmação anterior é revalidada contra os contadores esperados e usada
sem nova chamada Smart. Intenção sem resultado, timeout, queda do processo ou
falha ao guardar a resposta ficam inconclusivos e não permitem nova baixa
automática. Não apagar recibos para tentar de novo. A recuperação do efeito
inconclusivo exige conciliar a evidência do Smart; ainda não foi automatizada.

Prévia não cria intenção. Um recibo apenas de prévia não impede uma execução
real posterior. Recibo de sucesso sem intenção correspondente, identidade
divergente ou confirmação incompatível são recusados.

O arquivador comum move os arquivos processados/rejeitados/inconclusivos sem
sobrescrever. O financeiro precisa consumir os recibos confirmados antes de
marcar o processamento. O job `entregar_retornos_bb`, preparado no worktree PA,
já faz essa ligação: valida bytes, conta, intenção, grade e contadores e grava
o recibo junto aos marcadores dos pagamentos em uma transação. Ainda depende
da publicação e ativação em produção.

## Validação e limites

Regressão anterior à integração: 191 testes de remessa, retorno, recibos,
wrappers, descoberta e portão passaram, com serviços externos simulados.

125 testes passaram para entrega BB, conferência, retorno BB, depósito,
artefatos, descoberta e portão. Testes de entrega incluem persistência antes
do HTTP, repetição sem HTTP, timeout, interrupção abrupta, falha de gravação,
concorrência e erro de consulta auxiliar depois da confirmação. Smart simulado.

O comando 12 continua pendente de aceitação real pelo Smart. A prévia histórica
registrada no plano PA retornou “Ocorrência não encontrada”; não converter esse
código em outra ação nem tratar status OK isolado como sucesso.
