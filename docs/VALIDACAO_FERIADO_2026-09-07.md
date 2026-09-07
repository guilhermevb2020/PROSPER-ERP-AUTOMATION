# Validação após limpeza e recreate — 07/09/2026

Em andamento. Horários de Brasília. Rodada real iniciada às 14:42, pelo Hub,
com o código e a imagem limpa v2 em produção. O despacho respeita idempotência;
ausência de entrada não equivale a comprovação de escrita financeira.

## Correções encontradas nesta rodada

- `cdaf991`: o Guardian registrou EOF ao acessar CapSolver às 14:41. O ERP
  ocultava HTTP diferente de 200 como `{}` e abandonava o login. O cliente
  síncrono agora faz até três tentativas para falhas temporárias no createTask,
  mantém o prazo do polling e registra HTTP/tipo de erro sem resposta bruta ou
  credenciais. Erros explícitos de chave/saldo não são repetidos. Tentativas
  de criação são limitadas porque uma resposta perdida pode ter criado tarefa
  no fornecedor. Pagamentos posteriores às 14:45, 14:50 e 14:55 concluíram.
- `fede866`: `boletos_healthcheck` estava desabilitado por circuit breaker desde
  falhas de DNS de `guardian` em 06/09. A conexão atual usa a identidade efêmera
  do Guardian e funciona. Reativado às 14:52. Antes de recuperar a sessão, o
  healthcheck agora verifica emissão, envio, Doc2You, remessa e retorno/depósito
  ativos, inclusive quando o Chrome principal está indisponível. Registra
  `busy` com verificação adiada, sem afirmar que a sessão foi autenticada.
  Isso evita interromper uma rotina por novo login da identidade compartilhada.

Validação automatizada: 373 testes no host. Na imagem efetiva de produção,
35 testes de transporte/sessão e 18 de healthcheck passaram em containers
descartáveis sem rede e sem credenciais de produção. Código em `src/` é montado
no ERP; as novas execuções já o carregam, sem recreate do container.

## Execuções reais

| Rotina | Execução | Evidência |
|---|---:|---|
| Emissão | 2666432 | Success, modo real, zero títulos novos. |
| Envio | 2666498 | Success, modo real; conferência de duplicidade em andamento. |
| Doc2You | 2666501 | Em execução. |
| Pagamento | 2666484, 2666571, 2666646 | Success; consulta sem pagamentos pendentes. |
| Retorno de pagamento | 2666539, 2666617 | Success, login confirmado; entrada sem arquivos. |
| Retorno de cobrança agendado | 2666578 | Success, sem retorno bancário novo. |
| Healthcheck | 2666621 | Success; registrou `busy` porque Doc2You estava ativo. |
| Crédito | 2665935 | Ciclo diário em andamento desde 14:08; não duplicado. |

Doc2You antecipado, remessa de cobrança e depósito permanecem na sequência de
validação. A sessão principal será conferida novamente ao término. Os estados
individuais, incluindo tentativas malsucedidas, são preservados no Guardian em
`auditoria/acompanhamento-erp-2026-09-07/validacao-feriado-erp-real.json` e
`conferencia-feriado.json`.

## Configuração e outras dependências

Nova varredura exata de 3.728 arquivos do ERP não encontrou cópias dos segredos
conhecidos fora da credencial VNC materializada em `.env.guardian`. Não houve
arquivos pulados por erro de leitura. Git, ambientes virtuais e perfis do Chrome
ficam fora da varredura; cookies não são fonte administrativa de configuração.
O data-hub teve 2.625 arquivos verificados, sem correspondências ou erros de leitura.
Esses números não representam busca universal de segredos desconhecidos.

O texto contraditório do alerta de desativação foi corrigido no commit `b9367b4`
do Hub, mas ainda não foi implantado em seu processo principal. Reiniciar o Hub
com tarefas longas em voo exige uma janela de drain; não confundir commit com
deploy. As credenciais próprias `DB_HUB_PASSWORD` e `POSTGRES_PASSWORD` desse
outro projeto ainda não estão na fonte Guardian (reconferido nesta rodada).

Na varredura geral, `enriquecer_sacados` está desabilitado por falhas do motor
`ocr-documental`. O ia-lab informa GPU reservada para treinamento desde 06/09,
sentinela pausada e motores OCR/embedding/busca desligados. A retomada compete
com o treinamento ativo; não foi alterado o modelo nem interrompido o treinamento.
