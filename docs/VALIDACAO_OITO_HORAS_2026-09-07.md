# ERP — validação de oito horas em 07/09/2026

**Em andamento.** Janela solicitada: 07/09 16:34:17 até 08/09 00:34:17,
horário de Brasília. A rodada manual iniciou às 17:03 e abrange as 11 tarefas
finitas habilitadas. Crédito foi acompanhado na execução 2665935, sem duplicação,
até encerrar normalmente às 18:50:28, com exit 0, no fim do expediente.
As rotinas desabilitadas ou aposentadas não foram reativadas.

As 11 tarefas finitas da rodada manual estão conferidas. Uma emissão adicional,
2670656, comprovou a recuperação de sessão às 19:21:39, conforme o registro
abaixo. A conferência conjunta confirmou também as 18 tarefas finitas do
data-hub; isso não encerra a observação de oito horas.

O objetivo foi reaberto após a falha de deságio do data-hub. O relatório
anterior de feriado é histórico e não encerra esta observação. A imagem ERP
`guardian-clean-20260907-v2` permanece em uso; nenhum novo reinício do ERP
ou do crédito foi feito nesta janela.

## Resultados manuais conferidos até 17:59

| Rotina | Execução | Resultado e limite |
|---|---:|---|
| Doc2You | 2668640 | 683 documentos enviados/atualizados, zero erros, 51 operações; banco confirma registro 62 em `stg.doc2you_execucao`. |
| Emissão | 2668960 | Modo real, 55 contas vazias, zero falhas e zero títulos novos. |
| Envio | 2669015 | Modo real, 685 títulos de 22 contas já enviados; todos preservados pela idempotência, sem reenvio. |
| Doc2You antecipado | 2669016 | Login confirmado; sem documentos, notas ou operações novas do dia. |
| Emissão da tarde | 2669030 | Modo real, sem títulos novos; exit 0. |
| Remessa de cobrança | 2669097 | Login confirmado; 51 contas consultadas, nenhuma com títulos, zero arquivos gerados. |
| Retorno de cobrança | 2669358 | Sem retorno novo na janela e no controle de processamento; saiu antes de acessar o Smart. |
| Depósito | 2669360 | Log real `robo_deposito_2026-09-07.log` confirma entrada sem `.RET`; sem baixa. |
| Geração de pagamento | 2669386 | Consulta concluiu, zero pagamentos pendentes. |
| Retorno de pagamento | 2669389 | Login confirmado; nenhum arquivo para inserir. |
| Healthcheck | 2669491 | `estado=healthy`, exit 0 às 17:58:02. |

As 11 tarefas finitas concluíram a rodada manual, com os limites acima.
O despacho inicial do healthcheck recebeu HTTP 503 às 17:51:56: o Hub estava
temporariamente em `lifecycle=maintenance`. Não chegou a iniciar o robô.
Após confirmar `running` no lifecycle, o executor local retomou somente essa
tarefa, sem repetir as dez anteriores. O incidente foi preservado no JSON.
Os pagamentos agendados também estão sendo observados: 2668796 e 2668824
confirmaram login e consulta, sem arquivos de retorno ou pagamentos pendentes.
Saída sem entrada não comprova baixa nem geração financeira nova.

## Incidente do CapSolver às 18:13 e recuperação

A execução agendada 2669741 falhou com exit 2 às 18:13:41. O login alcançou
o CapSolver, que respondeu `ERROR_CAPTCHA_SOLVE_FAILED` ao consultar o desafio,
sem entregar token. A tentativa 2 do mesmo run, 2669760, concluiu com success
às 18:15:45, antes da alteração abaixo. Não atribuir essa recuperação ao código
novo nem apagar a tentativa que falhou. As 11 execuções manuais anteriores
continuam válidas; não significam ausência de incidentes posteriores.

O solver compartilhado passa a criar uma segunda task somente quando o desafio
retorna exatamente `ERROR_CAPTCHA_SOLVE_FAILED`. Aguarda 5s, conserva o mesmo
prazo total (180s, agora incluindo criação) e limita a duas tasks. Chave inválida,
saldo insuficiente e erros desconhecidos continuam encerrando imediatamente.
Falhas de transporte no polling continuam consultando a mesma task.

36 testes de solver/sessão passaram em container isolado, com rede desativada,
incluindo recuperação, esgotamento, prazo compartilhado e privacidade dos logs.
A fonte é montada em `/app/src`: a publicação por commit alcança os próximos
processos sem recriar o ERP nem encerrar crédito/mantenedor. A instância longa
já carregada mantém seu módulo até o encerramento normal.

O commit `d244857` foi aplicado às 18:18:37; hash do arquivo igual no host e
container. A geração 2669857 concluiu às 18:20:20 reutilizando sessão, sem solver.
O retorno 2669905 concluiu às 18:24:25: o log contém o marcador novo
`desafio 1/2`, token recebido e login confirmado. Não havia arquivo para inserir.
Não ocorreu falha do fornecedor nessa execução; o ramo de segunda tentativa
permanece comprovado pelos testes automatizados. Artefatos no Guardian:
`incidente-capsolver-2669741.json` e
`retorno-pos-correcao-capsolver-2669905.json`, em `observacao-oito-horas/`.

A remessa de cobrança agendada 2669533 também passou, às 18:16:10:
51 contas consultadas, zero com títulos e zero arquivos novos. O crédito
preservou o PID 807 e alcançou o ciclo 265 na conferência das 18:13.

## Provas de continuidade e credenciais

### Sessão expirada fora da janela e recuperação pela emissão

O healthcheck 2670616 terminou às 19:15:05 com exit 0, mas registrou
`chrome_ok=true`, `logado=false`, `needs_login_fora_janela` (registro 8634).
A janela efetiva passada pelo Hub é 7h–18h; os valores 9h–12h no módulo
são apenas padrões, sobrescritos nessa execução. Esse estado não deve ser
rotulado como sessão saudável só porque a task terminou com sucesso.

O mantenedor faz login ao iniciar e mantém o Chrome; seu loop não refaz login
quando a sessão expira. O healthcheck trata a recuperação dentro da janela,
e a emissão tem seu próprio caminho de recuperação. Para comprová-lo, a
emissão 2670656 foi executada pelo Hub às 19:17:38, sem outro robô ERP ativo,
sem alterar a janela nem os controles de idempotência. Detectou a sessão caída,
chamou o CapSolver com o código atualizado (`desafio 1/2`), confirmou login
às 19:18:25 e concluiu às 19:21:39 com exit 0. Consultou 55 contas, zero
títulos novos. O banco confirma 55 registros `vazio` e soma zero no lote.
Artefato no Guardian: `observacao-oito-horas/prova-recuperacao-emissao-19h.json`.

O healthcheck agendado seguinte, 2670808, confirmou `healthy`, Chrome disponível
e Smart logado às 19:30:07 (registro 8635), sem ação adicional. O observador
passa a registrar também esse estado operacional e a hora da verificação,
separados do exit code da task.

### Crédito e identidades do banco

O crédito 2665935 terminou às 18:50:28 com `success`, exit 0. O último ciclo foi
306/1000; o log registra `[janela] fim do expediente (18:50 BRT) -> robo encerrado`.
O teto de 1.000 ciclos não exige ultrapassar a janela diária. O PID 807 foi
preservado até essa saída normal e não foi reiniciado; o mantenedor da sessão
PID 67 continuou ativo na conferência das 18:56. Artefato no Guardian:
`observacao-oito-horas/credito-encerramento-normal-2665935.json`.

O crédito manteve o PID 807 e avançou até o ciclo 208 na conferência das 17:23.
O healthcheck 2668819 retornou `estado=busy` porque o Doc2You estava ativo:
isso comprova respeito à tarefa em curso, sem novo teste de autenticação.
A verificação manual posterior, 2669491, confirmou `estado=healthy`.
Às 17:59, os PIDs 807 (crédito) e 67 (mantenedor) permaneciam ativos.

O Guardian girou os logins dos dois projetos na janela 17:25:52–17:26:53.
Novas conexões às 17:28 pelos módulos reais das aplicações funcionaram com
`current_user=app_erp_automation` e `app_data_hub`, ambas com `session_user`
efêmero. Nenhuma senha ou passfile foi exibido.

Outra rotação ocorreu às 18:16:49. Novas conexões pelos mesmos clientes às
18:29 passaram; a identidade de `session_user`, comparada por hash, corresponde
exatamente ao login anunciado pelo worker para cada projeto. Prova em
`banco-conexoes-20260907-182916.json`. O conferidor reutilizável
`conferir_banco_rotativo.py`, no Guardian, usa transações somente leitura e
não imprime valores de credenciais.

O giro seguinte dos logins ocorreu às 19:07:19. Conexões novas nos dois
projetos passaram às 19:07:53, com hash de `session_user` idêntico ao da
identidade anunciada pelo worker. A conferência temporária
`acompanhar_rotacoes_oito_horas.py` acompanha cada login novo até 00:34:17,
sem escrever nos serviços. Resultados, inclusive divergências ou erros de
leitura, ficam em `observacao-oito-horas/rotacoes-verificadas.json` e nos
respectivos arquivos JSONL do Guardian.

O Doc2You antecipado agendado 2670468 concluiu às 19:01:22, exit 0. O log
confirma `logado. SSO Doc2You`; listados, enviados e erros ficaram em zero,
assim como documentos complementares, notas e XMLs novos. Comprova login,
consulta e conclusão sem entrada nova, sem envio adicional. Prova:
`observacao-oito-horas/doc2you-antecipado-agendado-2670468.json`, no Guardian.

A varredura de credenciais iniciada às 18:49 leu 3.737 arquivos do ERP:
somente VNC esperado em `.env.guardian`, nenhum arquivo pulado. O data-hub
teve 3.278 arquivos lidos, sem correspondências e sem arquivos pulados.
Escopo e limites em `AUDITORIA_CREDENCIAIS_2026-09-07.md`. OpenBao e Infisical
continuam sem containers ou imagens; só restam os avisos de aposentadoria,
com recuperação antiga cifrada no Guardian.

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
