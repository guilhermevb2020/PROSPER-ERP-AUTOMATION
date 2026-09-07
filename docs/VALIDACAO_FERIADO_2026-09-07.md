# Validação após limpeza e recreate — 07/09/2026

Rodada ERP: as 12 tarefas habilitadas foram alcançadas,
11 concluídas com sucesso e o crédito em seu ciclo diário, avançando no ciclo 90.
Horários de Brasília. Execução real iniciada às 14:42, pelo Hub,
com o código e a imagem limpa v2 em produção. O despacho respeita idempotência;
ausência de entrada não equivale a comprovação de escrita financeira.

Atualização às 16:17: o retorno de pagamento 2667714 falhou às 16:09,
após ficar no aviso de revalidação de e-mail do Smart. A retentativa 2667826
concluiu às 16:11:54. A execução 2667863, já com a correção abaixo, clicou
Prosseguir pelo controle habilitado, confirmou login e concluiu às 16:14:23.
Pagamento 2667891 concluiu às 16:16:07. Ambas consultaram a entrada real,
sem pagamentos/arquivos pendentes. A falha original permanece no histórico.

## Correções encontradas nesta rodada

- `f457b2a`: geração e retorno de pagamento agora compartilham uma trava
  `flock` antes de tocar nos perfis do Chrome. A espera é limitada a 300 s,
  com exit 6 se excedida; o descritor não é herdado por Xvfb/noVNC/Chrome.
  O botão desabilitado do aviso de segurança não é mais registrado como
  clicado por JavaScript. A inspeção confirmou o estado desabilitado, mas
  não estabeleceu a causa da resposta pendente do site na primeira falha.
  Houve sobreposição às 16:05, com geração reutilizando a sessão; isso
  comprova a lacuna de exclusão, não um novo login concorrente nessa rodada.
  Não foi enviado e-mail de revalidação nem alterado o estado do botão.

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

Validação automatizada atualizada: 382 testes no host, usando o ambiente
`.venv-sandbox` com as dependências de teste de `/tmp/erp-validation-20260907-deps`.
Os 57 testes de sessão/transporte/travas/modal também passaram na imagem
efetiva, em container descartável sem rede. Na validação anterior,
35 testes de transporte/sessão e 18 de healthcheck passaram em containers
descartáveis sem rede e sem credenciais de produção. Código em `src/` é montado
no ERP; as novas execuções já o carregam, sem recreate do container.

## Execuções reais

| Rotina | Execução | Evidência |
|---|---:|---|
| Emissão | 2666432 | Success, modo real, zero títulos novos. |
| Emissão da tarde | 2667139 | Success, modo real; 55 contas sem títulos novos, zero falhas. |
| Envio | 2666498 | Success, modo real; 685 títulos de 22 contas já enviados foram preservados, zero reenvios. |
| Doc2You | 2666501 | Success; 683 listados/enviados, zero erros. Registro 61 em `erp_automation.doc2you_execucao`; 683 respostas HTTP 204 do Nextcloud. |
| Doc2You antecipado | 2666827 | Success, login confirmado; zero documentos disponíveis. |
| Remessa de cobrança | 2666828 | Success, 51 contas consultadas; nenhuma nova remessa necessária. |
| Pagamento | 2667112 | Success às 15:25; consulta sem pagamentos pendentes. |
| Retorno de pagamento | 2667160 | Success às 15:28, login confirmado; entrada sem arquivos. |
| Retorno de cobrança | 2667101 | Success, sem retorno bancário novo. |
| Depósito | 2667102 | Success, nenhum `.RET` na entrada; sem baixa. |
| Healthcheck | 2667122, 2667175, 2667183 | Primeiro recuperou a sessão por login automático; depois da emissão confirmou `healthy`, `chrome_ok=true`, `logado=true` às 15:29 e 15:30. |
| Crédito | 2665935 | Ciclo diário desde 14:08; ciclo 90 observado às 15:30, sem duplicar o processo. |

Na rodada anterior houve escrita financeira real: remessa 26236, de 14 títulos.
O envio 373 em `financeiro.cnab_remessa_enviada` confirma recebimento pela API do
banco às 14:00:08, com protocolo e hash igual ao controle do ERP. O campo
`registro_confirmado_em` ainda está vazio: registro dos títulos depende do retorno
bancário. Não confundir recebimento do arquivo com registro confirmado.

Saídas sem entrada não provam baixa nem geração de pagamentos. O crédito não
foi encerrado para fabricar uma conclusão da tarefa diária. Os estados
individuais, incluindo tentativas malsucedidas, são preservados no Guardian em
`auditoria/acompanhamento-erp-2026-09-07/validacao-feriado-erp-real.json` e
`conferencia-feriado.json`.

As correções anteriores de validação também foram versionadas em `9f5d4a0`:
escrita dos logs no schema ERP, evidências da emissão, recusa de HTML de login no
envio, preservação do exit code do crédito, classificação de indisponibilidade
e modo seco do retorno de pagamento sem mover arquivos.

## Configuração e outras dependências

Nova varredura exata de 3.730 arquivos do ERP não encontrou cópias dos segredos
conhecidos fora da credencial VNC materializada em `.env.guardian`. Não houve
arquivos pulados por erro de leitura. Git, ambientes virtuais e perfis do Chrome
ficam fora da varredura; cookies não são fonte administrativa de configuração.
O data-hub teve 3.253 arquivos verificados após seu deploy, sem correspondências
ou erros de leitura. A busca foi ampliada para nomes SECRET/TOKEN/PRIVATE_KEY/ACCESS_KEY,
além de SENHA/PASSWORD/API_KEY; considera valores conhecidos com oito ou mais caracteres.
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
