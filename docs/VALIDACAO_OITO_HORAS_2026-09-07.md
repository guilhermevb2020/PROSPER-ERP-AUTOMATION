# ERP — validação de oito horas em 07/09/2026

**Em andamento.** Janela solicitada: 07/09 16:34:17 até 08/09 00:34:17,
horário de Brasília. A rodada manual iniciou às 17:03 e abrange as 11 tarefas
finitas habilitadas. Crédito é acompanhado na execução 2665935, sem duplicação.
As rotinas desabilitadas ou aposentadas não foram reativadas.

O objetivo foi reaberto após a falha de deságio do data-hub. O relatório
anterior de feriado é histórico e não encerra esta observação. A imagem ERP
`guardian-clean-20260907-v2` permanece em uso; nenhum novo reinício do ERP
ou do crédito foi feito nesta janela.

## Resultados manuais conferidos até 17:34

| Rotina | Execução | Resultado e limite |
|---|---:|---|
| Doc2You | 2668640 | 683 documentos enviados/atualizados, zero erros, 51 operações; banco confirma registro 62 em `stg.doc2you_execucao`. |
| Emissão | 2668960 | Modo real, 55 contas vazias, zero falhas e zero títulos novos. |
| Envio | 2669015 | Modo real, 685 títulos de 22 contas já enviados; todos preservados pela idempotência, sem reenvio. |
| Doc2You antecipado | 2669016 | Login confirmado; sem documentos, notas ou operações novas do dia. |
| Emissão da tarde | 2669030 | Modo real, sem títulos novos; exit 0. |
| Remessa de cobrança | 2669097 | Em execução na última conferência. |

Retornos, depósito, pagamentos e healthcheck seguem na sequência manual.
Os pagamentos agendados também estão sendo observados: 2668796 e 2668824
confirmaram login e consulta, sem arquivos de retorno ou pagamentos pendentes.
Saída sem entrada não comprova baixa nem geração financeira nova.

## Provas de continuidade e credenciais

O crédito manteve o PID 807 e avançou até o ciclo 208 na conferência das 17:23.
O healthcheck 2668819 retornou `estado=busy` porque o Doc2You estava ativo:
isso comprova respeito à tarefa em curso, sem novo teste de autenticação.
A sequência manual inclui outro healthcheck após os demais robôs.

O Guardian girou os logins dos dois projetos na janela 17:25:52–17:26:53.
Novas conexões às 17:28 pelos módulos reais das aplicações funcionaram com
`current_user=app_erp_automation` e `app_data_hub`, ambas com `session_user`
efêmero. Nenhuma senha ou passfile foi exibido.

Na conferência do envio, a view `operacional.boleto_envio_log` e a tabela
`erp_automation.boleto_envio_log` retornaram as mesmas 685 linhas e 685 IDs
distintos para a data de emissão 04/09. O robô consultou os 685 boletos e
pulou o reenvio, preservando o histórico após a mudança de schema.

## Artefatos e critérios de encerramento

No Guardian, pasta
`auditoria/acompanhamento-erp-2026-09-07/observacao-oito-horas/`:

- `STATUS.md`, `latest.json`, `tentativas.json` e `observations.jsonl`:
  catálogo, tentativas individuais, pós-checks e saúde dos serviços.
- `rodada-erp-automation.json`: sequência manual com IDs, resultados e limites.
- `banco-doc2you-2668640.json`: confirmação numérica no banco.
- `banco-envio-idempotencia-2669015.json`: correspondência entre view, tabela e robô.
- `banco-apos-rotacao-1726.json`: novas conexões após o giro dos logins.

O observador mantém falhas de tentativas anteriores e espera os pós-checks.
Ter iniciado o monitor ou obter exit 0 sem entrada não encerra a validação.
Os testes de código já aprovados continuam registrados na matriz anterior;
esta etapa executa os robôs reais e confere seus resultados.
