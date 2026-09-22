# Checagem / SmartConf — canhotos, histórico e levantamentos

Inspeção em 22/09/2026, em navegador exclusivo, com Playwright. Pesquisa de
cedentes e histórico executadas, respostas/anexos consultados e relatório de
pendências solicitado; nenhuma confirmação, inclusão de anexo, alerta, recompra ou
agendamento foi submetido. Contratos de escrita abaixo foram lidos no DOM e no
JavaScript entregue pela aplicação, não validados por execução.

## Objetivo confirmado pelo usuário

A automação desejada é **fazer upload do canhoto no Smart e vinculá-lo aos
títulos corretos**. Não é baixar um arquivo do Smart. A expressão anterior
“baixar o canhoto” foi esclarecida pelo usuário nesse sentido.

O catálogo abaixo já identifica os endpoints, o formato multipart e os campos
do envio. Isso permite começar a implementação, mas **não significa que o
upload ou todos os preenchimentos estejam validados para produção**.

### Fluxo pretendido da automação

1. Receber o arquivo do canhoto e os dados necessários para identificar seu vínculo.
2. Localizar cedente, sacado, nota fiscal, operação e títulos correspondentes.
3. Ler o fluxo, a etapa e os requisitos efetivamente apresentados pelo Smart.
4. Validar arquivo, vínculo e existência de anexos anteriores.
5. Preparar o upload e os metadados de confirmação conforme regra aprovada.
6. Enviar somente após habilitação explícita da escrita e teste controlado.
7. Consultar novamente a confirmação e seus anexos para comprovar o vínculo;
   registrar sucesso, erro ou resultado incerto sem repetir cegamente o envio.

### Preenchimentos: o que sabemos e o que falta definir

| Informação | Situação |
|---|---|
| Arquivo e nome | Campos identificados; extensões e tamanho validados pelo JavaScript documentados abaixo |
| Cedente, sacado, NF, operação e títulos | Devem ser resolvidos com os dados do documento/origem; regra de associação ainda não implementada |
| Fluxo, etapa e requisito | Ler do contexto real; não fixar IDs nem escolher requisito apenas pelo nome |
| Resposta do requisito | Códigos identificados; não presumir `OK` somente porque existe um arquivo |
| Canal de confirmação | Opções identificadas; usar o canal real, sem inventar telefone/e-mail/SMS/WhatsApp |
| Pessoa responsável e observação | Campos identificados; origem e regra de preenchimento ainda precisam ser definidas |
| Anexos existentes | Preservar; comparar antes de reenviar e não preencher remoções sem autorização |
| Avanço da etapa | Não validado; upload e confirmação compartilham a submissão |

**Principal pendência de negócio:** decidir se a ação deve apenas registrar o
comprovante ou também confirmar/avançar a etapa. Ainda não foi comprovado que
o mesmo formulário permite anexar mantendo a pendência. Não tratar upload de
arquivo e aprovação da checagem como ações equivalentes.

### Condições antes de usar em produção

- [ ] Definir a origem dos arquivos e os identificadores de vinculação.
- [ ] Definir tratamento de casos ambíguos, múltiplos títulos e múltiplos requisitos.
- [ ] Aprovar a regra de resposta, canal, pessoa e observação.
- [ ] Definir o efeito esperado sobre a etapa de checagem.
- [ ] Autorizar um teste controlado com título e canhoto reais identificados.
- [ ] Comprovar upload, persistência do anexo e vínculo correto após reler o Smart.
- [ ] Verificar duplicidade, falha parcial, timeout e preservação de anexos existentes.
- [ ] Implementar dry-run, auditoria de execução e coordenação da conta com os robôs.

O pedido atual é de documentação. Nenhuma automação de upload foi implementada
ou publicada, e nenhum teste de gravação foi autorizado ou executado nesta pesquisa.

## Como funciona

O menu Checagem do Smart (`/smart/checagem.php`) abre o **SmartConf**, em outro
domínio, mediante SSO. Não é a checagem de documentos/doc2you do robô finalizador
existente neste repositório. Não foi encontrada integração SmartConf em `src/`.

Fluxo observado: **cedente → pipeline → sacado/etapa → títulos agrupados por
nota fiscal → requisitos/respostas/anexos → confirmação da etapa**.

O painel apresenta, entre outras, as etapas “Confirmação pendente”, “Canhoto
pendente”, “Mercadoria entregue”, “Prazo”, “Programação de Pgto” e “Dispensado”.
Essas etapas não devem ser tratadas como uma sequência fixa sem ler o fluxo.

Na segunda inspeção (10h23–10h28), foi aberto o detalhe real da etapa
“Canhoto pendente”. Ele contém **dois requisitos com anexos independentes**:
“Canhoto da nota fiscal presente” e “Canhoto”. O detalhe inicial de “Dispensado”
não é mais a única evidência do mecanismo. IDs são configuração do ambiente,
não constantes para uma futura integração.

### Configuração versus tela operacional

| Objeto observado | ID neste ambiente | Evidência |
|---|---|---|
| Etapa Canhoto pendente | 5 | Cadastro e detalhe operacional abertos |
| Etapa Apenas canhotos | 11 | Link no cadastro de etapas |
| Requisito Canhoto da nota fiscal presente | 4 | Cadastro aberto e campo na confirmação |
| Requisito Canhoto | 12 | Link no cadastro e campo na confirmação |
| Requisito Dispensado | 11 | Inspeção anterior; não confundir com etapa 11 |

No cadastro `/etapa/edit/5`, apenas o requisito 4 estava marcado. No detalhe
operacional dessa etapa, apareceram **4 e 12**. A causa dessa diferença não foi
determinada (pode envolver o fluxo/contexto); não reconstruir a tela apenas pelo
cadastro de etapa. Ler os requisitos efetivamente devolvidos para cedente/sacado/fluxo.

## Catálogo HTTP

Base, salvo indicação: `https://smartconf.smartsecurities.com.br`.
Placeholders representam IDs obtidos da tela, nunca números fixos.

Evidências: **N** = navegação/consulta executada; **C** = contrato lido no
formulário/JavaScript, sem executar; **L** = link observado, conteúdo não validado.

| Método | Caminho | Capacidade | Evidência |
|---|---|---|---|
| GET | `https://wvw.smartsecurities.com.br/smart/checagem.php` | Entrada pelo Smart/iframe | N |
| POST | `/user/login?sf=…` | SSO do Smart para SmartConf; material transitório não documentado | N |
| GET | `/cedente` | Menu de confirmação | N |
| GET / POST | `/cedente/confirmacao` | Tela e pesquisa de cedentes | N |
| GET | `/checagem/pipeline-confirmacao` | Pipeline geral | N |
| GET | `/cedente/pipeline-confirmacao/{cedente}` | Sacados/títulos agrupados por etapa | N |
| GET | `/cedente/confirmacao-titulos/{cedente}/{sacado}/{etapa}` | Detalhar títulos e requisitos; query `f` identifica fluxo | N |
| POST | `/cedente/confirmacao-titulos/{cedente}/{sacado}/{etapa}` | Confirmar etapa com respostas e anexos, multipart | C |
| POST | `/cedente/get-dados-confirmacao` | Carregar confirmação existente, respostas e anexos | N |
| POST | `/cedente/recuperar-anexos` | Listar anexos de uma resposta; amostra retornou lista vazia | N |
| POST | `/cedente/atualiza-confirmacao-titulo/{cedente}/{sacado}/{etapa}` | Editar confirmação pelo histórico, multipart | C |
| POST | `/cedente/abrir-anexo` | Obter dados para visualização do anexo | C |
| GET | `/cedente/download-anexo?file={arquivo}&old={indicador}` | Download do anexo existente | C |
| POST | `/cedente/incluir-alerta` | Incluir alerta em títulos selecionados | C |
| POST | `/cedente/ignorar-checagem` | Ignorar checagem, com observação | C |
| POST | `/cedente/recomendarRecompra` | Recomendar recompra dos títulos | C |
| POST | `/agenda/agendarContato` | Agendar contato com sacado | C |
| GET | `/cedente/historico-confirmacao` | Filtros de histórico | N |
| POST | `/cedente/historico-confirmacao` | Pesquisar histórico | N |
| GET | `/cedente/historico-confirmacao-titulo/{titulo}` | Histórico individual; contexto em `numCedente` e `idFluxoCedente` | N |
| GET | `/cedente/performance-confirmacao` | Filtros de performance de confirmação | N |
| POST | `/cedente/performance-confirmacao` | Consultar performance por período | C |
| GET | `/cedente/performance-confirmacao-titulos` | Filtros de performance por títulos | N |
| POST | `/cedente/performance-confirmacao-titulos` | Consultar ou gerar relatório (`gerarRelatorio=1`) | C |
| POST | `/cedente/get-linhas-performance-confirmacao-titulos-concluidos` | Detalhar títulos concluídos de um usuário | C |
| GET | `/checagem/fluxo` | Configuração de fluxos | N |
| POST | `/checagem/fluxo` | Pesquisa/paginação de fluxos | C |
| POST | `/checagem/delete-fluxo` | Excluir fluxos por `ids`; não executado | C |
| GET | `/cedente/fluxo` | Filtros de configuração de fluxo por cedente | N |
| POST | `/cedente/fluxo` | Pesquisar configuração por cedente | C |
| GET | `/etapa` | Lista de etapas | N |
| GET | `/etapa/edit/{etapa}` | Configuração; inspecionado para Canhoto pendente | N |
| POST | `/etapa/edit/{etapa}` | Alterar descrição/requisitos/ordem; não executado | C |
| GET | `/requisito` | Lista de requisitos | N |
| POST | `/requisito` | Pesquisa/paginação por descrição | C |
| GET | `/requisito/edit/{requisito}` | Configuração; inspecionado para requisito 4 | N |
| POST | `/requisito/edit/{requisito}` | Alterar descrição; não executado | C |
| POST | `/requisito/delete` | Excluir IDs; não executado | C |
| GET | `/relatorio` | Menu de relatórios | N |
| GET | `/relatorio/pendencia-por-etapa` | Filtros de pendências | N |
| POST | `/relatorio/relatorio-pendencia-por-etapa` | Gerar relatório de pendências; retornou PDF para etapa de canhoto | N |
| POST | `/relatorio/planilha-pendencia-por-etapa` | Gerar planilha de pendências | C |
| GET | `/relatorio/liquidados-sem-checagem` | Filtros de liquidados sem checagem | N |
| POST | `/relatorio/relatorio-liquidados-sem-checagem` | Gerar relatório de liquidados sem checagem | C |
| POST | `/relatorio/planilha-liquidados-sem-checagem` | Gerar planilha de liquidados sem checagem | C |
| GET | `/agenda/agenda` | Calendário e controles da agenda | N |
| POST | `/agenda/agenda` | Consultar data/trocar mês | C |
| POST | `/agenda/removerAgendamentoContato` | Remover agendamento; não executado | C |
| POST | `/agenda/planilhaAgendamento` | Exportar agenda por período | C |
| GET | `/grafico/dashboard`, `/grafico` | Painéis (contratos de filtros não detalhados) | L |

## Contrato de anexos e confirmação

O formulário `form-modal` envia `multipart/form-data` para o mesmo caminho do
detalhe de títulos. `ConfirmarEtapa()` reúne os IDs selecionados;
`SubmeterForm()` cria `FormData(form)`, acrescenta os arquivos e envia por AJAX.
Não foi observado endpoint de upload independente nesse fluxo.

| Campo | Papel observado |
|---|---|
| `titulosSelecionados` | IDs de títulos separados por vírgula |
| `tituloPendente` | Título individual ao carregar confirmação existente |
| `tipoChecagem` | `M` ao preparar seleção múltipla; `I` ao carregar individual |
| `idFluxoCedente` | Contexto do fluxo |
| `idConfirmacao` | Identificador de confirmação existente, quando aplicável |
| `idResposta_{requisito}` | Resposta existente, quando aplicável |
| `respostas_{requisito}` | Resposta escolhida para cada requisito |
| `arquivosnew_{requisito}[]` | Binários novos acrescentados pelo JavaScript |
| `arquivosnew_nome_{requisito}[]` | Nomes atribuídos aos arquivos novos |
| `arquivos_id_{requisito}[]`, `arquivos_nome_{requisito}[]` | IDs e nomes de anexos existentes |
| `anexosDeletados` | IDs separados por vírgula para remoção ao salvar |
| `canal_confirmacao` | `T`: telefone; `E`: e-mail; `S`: SMS; `W`: WhatsApp |
| `responsavel_confirmacao` | Pessoa informada na confirmação |
| `observacao_confirmacao` | Observação |
| `ajax` | JavaScript define `1` |
| `numOperacao`, `numSacado`, `periodoInicial`, `periodoFinal`, `basepath` | Campos auxiliares presentes; preservar conforme tela |

O seletor visual chama-se `arquivos_{requisito}[]`, aceita múltiplos arquivos e
é esvaziado após a seleção. Os binários efetivos são mantidos em memória e enviados
como **`arquivosnew_{requisito}[]`**. Enviar apenas o campo visual não reproduz o fluxo.

Nos dois requisitos de canhoto, foi confirmado o de-para: `1=Pendente`, `2=OK`,
`3=Irregular`, `4=Ignorado`, `5=Não Aplicável`.

### Campos específicos de canhotos confirmados na tela

| Requisito | Resposta | Seletor visual | Binários no envio | Nomes no envio |
|---|---|---|---|---|
| Canhoto da nota fiscal presente | `respostas_4` | `arquivos_4[]` | `arquivosnew_4[]` | `arquivosnew_nome_4[]` |
| Canhoto | `respostas_12` | `arquivos_12[]` | `arquivosnew_12[]` | `arquivosnew_nome_12[]` |

Também existem `idResposta_4` e `idResposta_12`. Ambos os seletores permitem
múltiplos arquivos. Os controles inspecionados não têm atributo HTML `required`;
isso **não comprova** que o servidor aceite confirmação sem respostas/anexos/canal.
O envio continua sendo o POST multipart do detalhe, com `ajax=1` e contexto do
fluxo. Nenhum arquivo foi selecionado ou transmitido na inspeção.

Regras do JavaScript (`ValidaTipo`, `ValidaNomeArquivo`):

- Até **5.242.880 bytes (5 MiB) por arquivo**.
- Extensões: `jpg`, `jpeg`, `png`, `xml`, `pdf`, `doc`, `mp3`, `opus`, `3gpp`, `wav`, `ogg`.
- Nome validado por regex; corpo de 1–200 caracteres e extensão alfanumérica de 1–10.
  Há restrição de caracteres: letras, faixa acentuada definida no código, números,
  sublinhado, parênteses, espaço, ponto e hífen.
- Limites de quantidade, tamanho total e regras do servidor **não verificados**.

O cliente espera JSON com `message === "OK"`; `closeScreen === 1` fecha/recarrega
as telas. Isso é o contrato esperado pelo cliente, não uma resposta de gravação
obtida nesta pesquisa. Uma futura automação precisa reler o registro após gravar.

**Atenção:** anexar e confirmar compartilham a mesma submissão. Ainda não está
comprovado se é possível salvar um canhoto mantendo a etapa pendente.
`PularEtapa()` também usa o formulário, alterando respostas pendentes para Ignorado;
não é uma forma alternativa de salvar comprovantes.

## Editar confirmação existente: contrato diferente

O histórico individual tem o botão **Editar etapa**. `PreencheRequisitos()`
consulta os dados existentes antes de mostrar a edição. A gravação usa:

`POST /cedente/atualiza-confirmacao-titulo/{cedente}/{sacado}/{etapa}`

É `multipart/form-data`, mas **os nomes de campos não são os mesmos do cadastro
inicial**. Na tabela abaixo, `E` representa o ID da etapa e `R` o do requisito;
os nomes devem ser montados exatamente na posição indicada.

| Campo na edição | Função |
|---|---|
| `idEtapa`, `idFluxoCedente`, `status_checagem` | Contexto da edição |
| `tipoChecagemE`, `basepathE`, `idTituloE`, `idConfirmacaoE` | Contexto do título/confirmacão; `tipoChecagemE=I` |
| `key_E`, `situacaoEtapa_E` | Campos internos presentes; semântica ainda não validada |
| `ajaxE` | JavaScript define `1` |
| `anexosDeletadosE` | Remoções solicitadas ao salvar |
| `E_idResposta_R`, `E_respostas_R` | Identificador e estado da resposta |
| `E_arquivos_R[]` | Seletor visual de novos arquivos |
| `E_arquivosnew_R[]`, `E_arquivosnew_nome_R[]` | Binários e nomes novos |
| `E_arquivos_id_R[]`, `E_arquivos_nome_R[]` | Anexos existentes |
| `E_canal_confirmacao`, `E_responsavel_confirmacao`, `E_observacao_confirmacao` | Metadados da confirmação |

Exemplo apenas de nomenclatura: etapa 15/requisito 11 usa `ajax15`,
`15_respostas_11` e `15_arquivosnew_11[]`. Não usar esses IDs para canhotos.
O formulário inspecionado para edição era de outras etapas, não uma edição
real de canhoto. A aplicabilidade a uma etapa específica deve ser lida no histórico.

### Consultas de conferência comprovadas

- `POST /cedente/get-dados-confirmacao`, com `idConfirmacao` e `numTitulo`:
  HTTP 200, JSON `message=OK`; chaves `idConfirmacao`, `canalConfirmacao`,
  `responsavelConfirmacao`, `observacao`, `respostas`. Cada resposta tem
  `idResposta`, `idRequisito`, `respostaRequisito`, `anexos`.
- `POST /cedente/recuperar-anexos`, com `idResposta`: HTTP 200, JSON
  `message=OK`, `anexos=[]` para a resposta amostrada.
- O JavaScript da listagem espera, em cada anexo, `nome`, `anexo`, `old`;
  a edição também usa `idAnexo`. **Não houve amostra não vazia validada**.

Não confundir sucesso da consulta com presença de comprovante. Para conferir
um upload futuro, verificar a resposta correta, a lista não vazia e o vínculo
ao título/requisito. Não presumir idempotência de nenhum POST de escrita.

## Outros contratos identificados

- Pesquisa: `idCedente`, `docCedente`, `nomeCedente`, `numCedente`, `idSacado`,
  `docSacado`, `nomeSacado`, `numSacado`, `numOperacao`, `periodoInicial`,
  `periodoFinal`, `grupoEconomicoCedente`, `filtroControlador`, `filtroCobrador`,
  `page`, `ordenacao`, `ascDesc`, `urlPipeline`, `btnPesquisar`.
- Carregar confirmação: `idConfirmacao`, `numTitulo`; cliente espera
  `message`, `idConfirmacao`, `respostas` (com `idResposta`, `idRequisito`,
  `respostaRequisito`, `anexos`) e `observacao`.
- Abrir anexo: `file`, `old`; cliente espera `message`, `mime`, `src`.
- Alerta: `titulosAlerta`, `motivoAlerta`, `numCedenteAlerta`, `idSacadoAlerta`,
  `idEtapaAtualAlerta`, `idFluxoCedenteAlerta` e filtros com sufixo `Alerta`.
- Ignorar checagem: `numCedente`, `idEtapaAtual`, `idSacado`, `titulos`,
  `observacao`, `idFluxoCedente` e filtros de operação/sacado/período.
- Recomendar recompra: `titulos` separados por vírgula, `motivoRecomendacaoRecompra`.
- Agendar contato: `DataAgendarContato`, `HoraAgendarContato`, `idCedente`,
  `numSacado`, `ObservacaoAgendarContato`, `modo=N`.

## Aplicação no projeto

### Levantamentos / consultas e exportações

Não foi encontrado um menu com o rótulo literal “Levantamentos” nas telas
inspecionadas. As capacidades abaixo permitem levantar pendências e checagens;
se o termo designar outra tela, ainda é necessário identificar essa tela.

**Pendências por etapa:** o mesmo formulário alimenta relatório e planilha.
Campos: `idCedente`, `docCedente`, `nomeCedente`, `numCedente`, `idSacado`,
`docSacado`, `nomeSacado`, `numSacado`, `etapa`, `tipoTitulo`,
`grupoEconomicoCedente`, `filtroOperador`, `ordenaPorNFE`, `detalharTitulos`.
`GerarRelatorio()` troca o destino e abre nova aba; `GerarPlanilha()` submete
para o destino de planilha. A consulta com `etapa=5` foi executada: HTTP 200,
`Content-Type: application/pdf`, 21.369 bytes. O conteúdo do PDF não foi
inspecionado/persistido. Formato e colunas da planilha ainda não verificados.

**Liquidados sem a devida checagem:** campos de identificação de cedente/sacado
acima, `etapa`, `tipoTitulo`, `periodoInicial`, `periodoFinal`. O período se refere
à **quitação**, não à emissão ou vencimento. Controles são `date`; JavaScript
verifica tamanho da data informada e compara início/fim antes da submissão.

**Histórico:** filtros `tipoTitulo`, `numDocumento`, `numOperacao`, `notaFiscal`,
identificação de cedente/sacado, `statusChecagem`, `ordenacao`; auxiliares `page`
e `urlHistoricoTitulo`. Pesquisa por POST para a mesma página foi executada.
Colunas observadas: Checagem, Tipo, Número, Sacado, Vencimento, Valor, Situação,
NFe e Operação. O detalhe individual apresenta etapas, status, requisitos e
controles de anexos/edição. Foram abertos dois títulos, sem alterar registros.

**Performance:** a consulta geral usa `periodoInicial`, `periodoFinal`, `page`,
`urlPipeline` e `btnPesquisar`. A versão por títulos inclui `gerarRelatorio`
e `urlHistoricoTitulo`. Detalhamento de concluídos usa POST para
`/cedente/get-linhas-performance-confirmacao-titulos-concluidos` com campos
**`NumLogin`, `PeriodoInicial`, `PeriodoFinal`** (maiúsculas significativas).
O cliente insere o retorno como HTML, não o interpreta como JSON.

**Agenda:** consulta de calendário usa `anoAtual`, `mesAtual`, `acaoCalendario`
e `dataSelecionada`; a escolha de data define `acaoCalendario=3`.
Edição chama `/agenda/agendarContato` com `modo=E`, `IDAgendarContato`,
`DataAgendarContato`, `HoraAgendarContato`, `ObservacaoAgendarContato`.
A inclusão no detalhe de títulos usa `modo=N` e cedente/sacado, como descrito
acima. Remoção usa `IDAgendarContato`. Planilha usa
`PeriodoInicialPlanilhaAgenda`, `PeriodoFinalPlanilhaAgenda`.

**Cadastros:** edição de etapa usa `descricao`, `ordems[]`, `requisitos[]` e
`btnSalvar`; edição de requisito usa `descricao` e `btnSalvar`. A função
`ValidarForm()` do requisito exige descrição. Exclusão de requisito usa `ids`.
Essas são alterações de configuração, não passos necessários para anexar canhotos.

### Caminho de implementação proposto

Primeira capacidade sugerida: **consultar pendências e preparar vinculação de
canhotos**, sem confirmação automática inicial.

1. Consultar cedente, sacado, operação, nota fiscal e títulos candidatos.
2. Resolver a etapa e os requisitos reais do fluxo, sem IDs fixos.
3. Associar o comprovante à NF/títulos com evidência suficiente; casos ambíguos
   vão para revisão, nunca por semelhança de nome apenas.
4. Validar formato/tamanho e deduplicar por hash + vínculo do comprovante.
5. Apresentar quais respostas/etapas seriam alteradas antes de habilitar escrita.
6. Após autorização para implementação e validação controlada, enviar e reler
   anexos/respostas; registrar execução, arquivo e eventos no padrão do projeto.

Possibilidades posteriores: consulta de histórico, download de comprovantes,
agenda de contatos e alertas. Registrar canal WhatsApp não significa enviar mensagem.

Um job novo seguiria `src/processors/web/<job>/`, cliente compartilhado em
`src/common/clients/`, wrapper, configuração, lógica pura testável e dry-run no
ponto de gravação. A sessão Smart é única por identidade: perfil separado não
elimina disputa com outro robô da mesma conta.

## Evidências e pendências

Pesquisa baseada em telas, formulários e funções JavaScript inspecionados na
sessão `erp-checagem`. Metadados parciais locais:
`data/sandbox/mapeamento_http/navegacao_20260922_100741.json` e snapshots em
`.playwright-cli/` (não versionados). O coletor não preservou um dump completo
das funções; os contratos relevantes estão transcritos acima, sem dados de clientes.

Segunda coleta: `data/sandbox/mapeamento_http/navegacao_20260922_102334.json`.
Snapshots locais de referência (UTC nos nomes):

- `.playwright-cli/page-2026-09-22T13-26-25-375Z.yml`: cadastro da etapa.
- `.playwright-cli/page-2026-09-22T13-27-14-234Z.yml`: detalhe real de canhotos;
  campos ocultos complementados por leitura do DOM e de `SubmeterForm`.
- `.playwright-cli/page-2026-09-22T13-27-48-845Z.yml`: pendências por etapa.
- `.playwright-cli/page-2026-09-22T13-27-57-320Z.yml`: liquidados sem checagem.
- `.playwright-cli/page-2026-09-22T13-28-21-837Z.yml`: filtros de histórico.

Esses snapshots podem conter dados empresariais; permanecem locais e ignorados
pelo Git. O documento usa apenas contratos e IDs de configuração.

Terceira coleta (10h32–10h39):
`data/sandbox/mapeamento_http/navegacao_20260922_103200.json`.
Snapshots: `page-2026-09-22T13-35-23-214Z.yml` (resultado do histórico),
`page-2026-09-22T13-35-57-059Z.yml` (histórico individual),
`page-2026-09-22T13-37-25-146Z.yml` (performance por títulos),
`page-2026-09-22T13-37-53-226Z.yml` (agenda), na mesma pasta local.
Respostas JSON foram inspecionadas só por status/esquema, sem registrar conteúdo
de observações ou dados pessoais no catálogo. Navegador encerrado ao terminar.

Falta verificar: amostra de anexo existente não vazio e seu download,
regras de transição, obrigatoriedade dos campos, permissões de escrita, limites
do servidor, duplicidade e recuperação após timeout, arquivos exportados e
significado de “levantamentos” caso se refira a outra tela. **Este é um mapa observado,
não uma integração implementada nem uma lista comprovadamente completa.**
