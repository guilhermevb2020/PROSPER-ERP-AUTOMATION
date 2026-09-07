# Validação do ERP Automation — 07/09/2026

## Resultado

**Após a limpeza e correção da recuperação: 352 testes passaram no host.** A validação anterior teve
327 testes na imagem em uso; a candidata limpa passou 331 testes antes da inclusão
do quinto teste de sandbox. Chrome 149 abriu na candidata, com certutil presente
e sem os arquivos .env/config/sandbox.env/.git. A candidata ainda não foi implantada.
Veja a [auditoria de credenciais](AUDITORIA_CREDENCIAIS_2026-09-07.md) para pendências.
As 20 tarefas cadastradas no Hub foram inventariadas: 11 habilitadas e nove
desabilitadas, apontando para dez entrypoints. Todos os entrypoints existem
e passaram na checagem de sintaxe dentro do container. Cada família abaixo
possui testes correspondentes; horários/aliases que chamam o mesmo processador
compartilham essa cobertura. Nenhuma tarefa desabilitada foi ativada.

Os testes de fluxos usam transporte simulado e arquivos temporários. Não
emitiram boletos reais, não deram baixas financeiras, não enviaram mensagens
e não fizeram novos logins no Smart. Evidências de produção foram obtidas
separadamente das execuções já agendadas. **Testes aprovados não significam
que todas as operações de negócio foram exercitadas em produção.**

## Execução real solicitada após os testes — concluída às 13:15

O usuário solicitou execução de ponta a ponta em produção. A rodada começou
às 12:25, com despacho sequencial pelo Hub e modos reais, preservando controles
de duplicidade. Houve escrita real no Nextcloud, no banco e geração de CNAB400.
As sete tarefas da sequência manual terminaram com exit 0. Pagamentos foram
conferidos nas execuções agendadas e crédito permaneceu no ciclo diário.
A pausa de manutenção do Hub foi resolvida e a sequência retomada pela API.

| Tarefa | Execução | Resultado conferido |
|---|---:|---|
| Emissão | 2664371 | 12:25–12:30, exit 0, EMISSAO REAL; 55 contas vazias, zero títulos novos. |
| Envio | 2664422 | 12:30, exit 0, ENVIO REAL; 685 títulos já enviados preservados, zero novos envios. |
| Doc2You | 2664453 | 12:30–12:51, exit 0; 683 listados e enviados/atualizados, zero erros. Banco confirma registro 60 e Nextcloud 683 respostas HTTP 204. |
| Doc2You antecipado | 2664759 | Exit 0, login confirmado; zero documentos, complementares, NFs e XMLs disponíveis. |
| Remessa de cobrança | 2664761 | 12:52–13:09, exit 0; 51 contas, uma remessa gerada, 14 títulos, um arquivo baixado e enviado ao Nextcloud. |
| Retorno de cobrança | 2665064 | Nova execução após liberação do Hub, exit 0, nenhum retorno bancário novo. Também houve execução agendada 2664752 às 12:51. Não houve baixa. |
| Remessa de pagamento | 2664972 | Agendada às 13:05, exit 0, login confirmado; zero pagamentos pendentes. |
| Retorno de pagamento | 2665013 | Agendada às 13:08, exit 0, login confirmado; entrada sem arquivos. |
| Crédito | 2663378 | Execução diária em andamento; ciclo 118 observado às 13:10. Sem duplicar ou reiniciar o processo. |
| Depósito | 2665065 | Nova execução às 13:13, exit 0; log próprio confirma nenhum `.RET`, pasta com zero arquivos. Não houve baixa. |

A remessa 26236 contém 14 títulos em CNAB400, 30 registros e 12.060 bytes.
Foi conferida no controle local (um registro, tamanho e MD5 corretos) e baixada
novamente do Nextcloud: conteúdo idêntico ao arquivo local. Isso prova a geração
e a entrega ao Nextcloud; não comprova aceite/processamento pelo banco.

O disparo manual do retorno às 13:09:51 recebeu HTTP 503. `/ready` confirmou
`lifecycle=maintenance`, `reason=manual`, persistente desde 13:08:45, enquanto
scheduler e heartbeat estavam saudáveis. A manutenção não foi removida por esta
sessão. Após o Hub voltar a `running`, o executor retomou pela API e concluiu
retorno 2665064 e depósito 2665065. O evento permanece no histórico da rodada.

Saída sem entrada não comprova escrita financeira. Não foram criados títulos
nem reapresentados retornos antigos para produzir cobertura artificial.
O processo temporário do Chrome foi encerrado com SIGINT após as tarefas.
O mantenedor normal `src.processors.web.boletos.manter_sessao` foi restaurado,
confirmou login automático e `keepalive: logado=True status=200`; CDP 9222
respondeu HTTP 200. Não foi necessário reiniciar o container nem o crédito.

IDs e despacho: `ponta-a-ponta-real.json`. Conferências: `conferencia-*-real.json`,
na pasta `auditoria/acompanhamento-erp-2026-09-07/` do access-guardian.

## Matriz das tarefas

| Tarefa no Hub | Habilitada | Família testada |
|---|---|---|
| `baixar_deposito_no_erp` | Sim | Depósito |
| `baixar_documentos_doc2you` | Sim | Doc2You |
| `baixar_documentos_doc2you_antecipado` | Sim | Doc2You |
| `boletos_healthcheck` | Não | Healthcheck |
| `emitir_lote_boletos` | Sim | Emissão |
| `emitir_lote_boletos_fim_manha` | Não | Emissão |
| `emitir_lote_boletos_tarde` | Sim | Emissão |
| `enviar_lote_boleto_avulso` | Não | Envio |
| `enviar_lote_boletos` | Sim | Envio |
| `gerar_remessa_cobranca_cnab_400` | Sim | Remessa de cobrança |
| `gerar_remessa_pagamento_bmp` | Não | Remessa de pagamento |
| `gerar_remessa_pagamento_cnab_240` | Sim | Remessa de pagamento |
| `gerar_remessas_cnab` | Não | Remessa de cobrança |
| `gerar_remessas_cnab400` | Não | Remessa de cobrança |
| `processar_retorno_cobranca_cnab_400` | Sim | Retorno de cobrança |
| `processar_retorno_pagamento_cnab_240` | Sim | Retorno de pagamento |
| `processar_retornos_cnab` | Não | Retorno de cobrança |
| `processar_retornos_cnab400` | Não | Retorno de cobrança |
| `robo_analise_credito` | Sim | Crédito |
| `robo_retorno_pagamento` | Não | Retorno de pagamento |

## O que os testes verificam

| Família | Evidência automatizada |
|---|---|
| Emissão | `test_emissao_evidencia.py`, `test_conferir_emissao.py`, `test_emissao_lote_simulada.py`: parâmetros, PDF, manifesto, beneficiário correto/divergente, modo seco e falha de gravação. |
| Envio | `test_envio_lote_fluxo.py`: SCAN/DRY/CONFIRMAR, teto, unicidade, exclusão de IDs já enviados, classificação de resposta e sessão expirada. |
| Doc2You | `test_doc2you_fluxo.py`: upload 201/204, erro 500, download vazio, colisão de nomes e paginação repetida. |
| Crédito | `test_conta_operacao.py`: conta existente preservada e escolha segura quando vazia; `test_credito_wrapper.py`: seis códigos de saída preservados pelo wrapper. |
| Remessa de cobrança | `test_remessa_cobranca_simulada.py`: geração, download CNAB400, gravação e controle, idempotência, arquivo inválido, falha Nextcloud e recuperação de geração sem ID. |
| Remessa de pagamento | `test_pagamento_analise.py`, `test_pagamento_robo.py`, `test_pagamento_config.py`, `test_pagamento_trava.py`: análise, CNAB240, sessão, geração, configuração e concorrência. |
| Retorno de cobrança | `test_portao_retorno.py`, `test_artefatos_retorno.py`: valores divergentes, quantidade, casamento, recibos e movimentação sem sobrescrever; inclui três capturas históricas com 1.238 títulos. |
| Depósito | `test_retorno_deposito.py` e portão: modo seco, rejeição antes da baixa, hash, comprovação exata e resultado inconclusivo. |
| Retorno de pagamento | `test_retorno_pagamento_fluxo.py`: upload e confirmação separados, falha em cada etapa, sessão expirada, idempotência e DRY sem movimentação. |
| Healthcheck | `test_boletos_healthcheck_fluxo.py`: Chrome indisponível, deduplicação de aviso, envio ativo, saudável, fora de janela e relogin com sucesso/falha. |
| Compartilhados | `test_smart_sessao.py`: timeout não equivale a expiração e não provoca login desnecessário; `test_fingerprinting.py`: 31 cenários assíncronos. |

## Correções realizadas durante esta validação

- O teste de fingerprinting importava `HardwareProfile` por um caminho antigo.
  Import atualizado para `src.common.profiles.hardware_profiles`.
- O módulo `emissao_evidencia` existia, mas não era chamado pelo core. O fluxo
  agora salva o PDF/resposta e manifesto após a impressão. `SALVAR_PDF_EMISSAO`
  controla a gravação (padrão true); `EVIDENCIA_DIR_EMISSAO` define a pasta
  (padrão `/app/data/boletos/emitidos`). Falha de evidência não repete a emissão.
- Retorno de pagamento movia arquivos duplicados mesmo em DRY. Agora apenas
  informa que arquivaria, preservando a entrada.
- Envio de boletos podia tratar HTML de sessão expirada como lista vazia.
  Consultas agora recusam sessão expirada/resposta vazia e HTTP diferente de 200.
- O wrapper do crédito devolvia o código de `tee`. Agora preserva o código do
  Python usando arquivo temporário, compatível com `sh`; não requer reinício
  do crédito em andamento. O novo wrapper vale nas próximas execuções.
- `pytest.ini` restringe a coleta aos testes automatizados. Scripts manuais
  em `tests/` que enviam notificações ou acessam serviços não são importados.
  Os dois arquivos `.mock.py` com apenas `assert True` não contam como cobertura.
- `requirements-test.txt` declara pytest e pytest-asyncio.

Correções anteriores desta mesma migração: validação repetida de sessão em
`smart_sessao`, limpeza de links Singleton órfãos no boot e credencial financeira
no Guardian ajustada ao valor efetivo de 11 caracteres que o campo do Smart
recebia antes da migração.

## Prova na imagem e reprodução

A prova de runtime usou a imagem exata retornada por `docker inspect` do ERP,
em container descartável com `--network none`, filesystem somente leitura,
`/tmp` temporário, código/testes montados somente leitura e três capturas de
retorno montadas individualmente, também somente leitura. Nenhum arquivo de
credencial de produção foi montado para o teste.

A suíte completa no host inclui 14 testes próprios desse ambiente: dez do
sandbox de pagamento e quatro da integração com conferidor PDF. Esses 14
foram excluídos **apenas** da prova na imagem: o teste de sandbox exige caminho
fora de `/app`, e o conferidor usa `pdftotext`, instalado no host e ausente na
imagem. Todos eles passaram no host. Assim: 341 no host, 327 na imagem.

Para reproduzir em um ambiente de testes com as dependências do projeto:

```bash
python3 -m venv .venv-testes
.venv-testes/bin/pip install -r requirements.txt -r requirements-test.txt
PYTHONPATH=. .venv-testes/bin/python -m pytest -q
```

A suíte usa `pdftotext` (poppler-utils) e as capturas locais
`data/robo_retorno/titulos_0508.csv`, `titulos_prod_0408.csv` e `titulos_teste.csv`.
Essas capturas contêm dados operacionais e não devem ser adicionadas ao Git.
Sem elas a suíte acusa ausência, em vez de apresentar sucesso sem cobertura.
O teste não instala dependências no container de produção.

## Evidências de produção e limites

- Emissão da manhã: 89 títulos; envio: 685 registros OK; Doc2You: 687 documentos
  enviados/atualizados, incluindo backlog. Essas execuções antecedem algumas
  correções; não são prova de execução real do código alterado depois delas.
- Credencial financeira corrigida na fonte às 11:40:00; worker recarregou às
  11:40:03. Geração e retorno confirmaram login e exit 0 às 11:41. Rodadas
  posteriores também tiveram sucesso, sem pagamentos/retornos pendentes.
- Houve uma falha do CapSolver às 11:53 (`createTask falhou: {}`), com exit 2.
  O retorno seguinte confirmou login e terminou com exit 0 às 11:59:08.
  É uma falha real preservada no histórico, não evidência de senha inválida.
- Banco validado com `current_user=app_erp_automation` e sessão efêmera do
  Guardian. Nextcloud respondeu 207 e CapSolver HTTP 200/errorId 0 na verificação.
- Crédito permanece em execução. Sua conclusão diária ainda não foi observada.
- Retorno de cobrança sem novidades por controle de hash; depósito sem `.RET`.
  Portanto não houve prova de baixa real dessas tarefas nesta janela.
- Os horários da tarde/noite ainda não ocorreram. Remessa de cobrança e
  Doc2You antecipado já foram executados manualmente na rodada acima.
  O observador segue até 21h.
- CDP de boletos inicialmente recuperado com processo temporário. Ao fim da
  rodada real, o mantenedor normal foi restaurado com login e keepalive válidos.
  A correção do boot não foi revalidada por novo restart do container.

O resultado fecha a rodada de testes automatizados e de configuração, com os
limites acima. Não constitui garantia de disponibilidade permanente do Smart,
CapSolver ou bancos, nem comprovação de todas as escritas financeiras reais.

Artefatos detalhados no projeto access-guardian:
`auditoria/acompanhamento-erp-2026-09-07/`: `testes-host.xml`, `testes-host.log`,
`testes-imagem-runtime.log`, `matriz-tasks-testes.json`, `STATUS.md` e `RELATORIO.md`.


## Auditoria de credenciais após a execução

A execução real bem-sucedida não comprova ausência de segredos em todo o
projeto. A [auditoria específica](AUDITORIA_CREDENCIAIS_2026-09-07.md) confirmou
apelidos no ambiente principal, mas identificou resíduos em sandbox/finalização,
no `.env` do container e no histórico SMTP. O padrão obrigatório é o Guardian
como fonte das credenciais core; as pendências estão registradas nessa auditoria.

## Recuperação após recreate — tarde de 07/09

Imagem limpa v2 implantada e Chrome/CA/CDP conferidos. Crédito retomado na execução
2665935 às 14:08. Pagamento 2666187 às 14:25 terminou exit 0, login e consulta sem
pendentes. Falhas anteriores preservadas no histórico. Retorno de pagamento também
concluiu após recreate. A task financeira permaneceu habilitada como critical;
o aviso de desativação do Hub estava contraditório. Ver auditoria de credenciais.
