# Mapeamento HTTP — 22/09/2026

Navegação realizada com a identidade sandbox em navegador e perfil exclusivos. Nenhum agendamento foi alterado.
A interface autenticou e expôs o menu; o ping usado pelo login Python não confirmou a sessão. Durante a coleta, surgiram respostas HTTP 403. A causa não foi determinada.

Entradas de navegação: 79. Distribuição: `{"tela_observada": 19, "somente_menu": 25, "HTTP_403": 35}`.
As entradas incluem atalhos e variantes: não representam essa quantidade de capacidades únicas.

Os formulários, nomes/tipos dos campos, destinos e controles ficam em `data/sandbox/mapeamento_http/catalogo_telas.json` e `.csv` (locais, não versionados).
O inventário de código fica em `inventario_codigo.json`. A [API oficial](API_OFICIAL.md) tem catálogo separado: autenticação e contratos diferentes das telas PHP.

O detalhamento de [Checagem / SmartConf e anexos de canhotos](CHECAGEM.md) está
em catálogo separado, com contratos de leitura e escrita e seus limites de validação.

## Limites

- Não comprova todas as permissões nem ações ocultas ou módulos não contratados.
- Formulário e botão observados não comprovam execução da ação.
- Valores de query/campos, cookies e tokens não foram persistidos.
- HTTP 403 tem causa não determinada; não classificar como funcionalidade inexistente.
- Registros da primeira coleta sem identificação de frame foram excluídos da consolidação.

## Telas e navegação

| Menu | Caminho | Evidência | Formulários |
|---|---|---|---|
| (link auxiliar) | /smart/smartsecurities.php | tela_observada | 1 |
| Grupo econômico | /smart/factoring/grupoeconomicopessoa.php | tela_observada | 1 |
| Documentos | /smart/factoring/condocumento.php | tela_observada | 1 |
| Feriados | /smart/factoring/conferiado.php | tela_observada | 2 |
| Pessoas bloqueadas de operar | /smart/factoring/conlistanegra.php | tela_observada | 2 |
| Cedentes | /smart/cedente/concedente.php | tela_observada | 2 |
| Sacados | /smart/sacado/consacado.php | tela_observada | 1 |
| Operação Convencional | /smart/operacao/frmconoperacao.php | somente_menu | 0 |
| Dashboard | /smart/trustee/dashboard.php | tela_observada | 0 |
| Operações | /smart/trustee/trustoperacao2.php | tela_observada | 1 |
| Títulos em aberto | /smart/financeiro/titulosemaberto.php | tela_observada | 2 |
| Títulos quitados | /smart/financeiro/titulosquitados.php | HTTP_403 | 0 |
| Extratos | /smart/trustee/extratostrustee.php | HTTP_403 | 0 |
| Transferir Títulos Convencional para Trustee | /smart/trustee/transferirconvencional.php | somente_menu | 0 |
| Títulos | /smart/financeiro/pesquisa.php | tela_observada | 2 |
| Incluir contas a receber | /smart/financeiro/incluircontasreceber.php | somente_menu | 0 |
| Incluir parcelas a receber | /smart/financeiro/incluirparcelasreceber.php | somente_menu | 0 |
| Titulos Baixados | /smart/financeiro/titulosbaixados.php | somente_menu | 0 |
| Títulos em aberto | /smart/financeiro/titulosemaberto.php | HTTP_403 | 0 |
| Títulos quitados | /smart/financeiro/titulosquitados.php | HTTP_403 | 0 |
| Títulos repassados/pendências | /smart/financeiro/titulosrepassadospendencias.php | HTTP_403 | 0 |
| Títulos rejeitados em operações | /smart/financeiro/titulosrejeitadosop.php | HTTP_403 | 0 |
| Títulos prorrogados | /smart/financeiro/titulosprorrogados.php | HTTP_403 | 0 |
| Refinanciamento | /smart/financeiro/conrefinanciamento.php | HTTP_403 | 0 |
| Títulos Antecipados | /smart/financeiro/titulosantecipados.php | HTTP_403 | 0 |
| Títulos em atraso | /smart/financeiro/titulosematraso.php | HTTP_403 | 0 |
| Registro on-line | /smart/financeiro/contadigital/remessaocorrencia.php | somente_menu | 0 |
| Gerar Remessa | /smart/financeiro/remessaocorrencia.php | tela_observada | 1 |
| Processar Retorno | /smart/financeiro/retornoocorrencia.php | tela_observada | 1 |
| Remessa | /smart/financeiro/downloadremessa.php | tela_observada | 1 |
| Prorrogar vencimento de títulos | /smart/financeiro/prorrogartitulos.php | somente_menu | 0 |
| Inadimplentes | /smart/financeiro/inadimplentes.php | HTTP_403 | 0 |
| 1ª Via de Boleto | /smart/financeiro/frmimpriboleto.php | somente_menu | 0 |
| 1ª Via de Boleto em Lote | /smart/financeiro/frmimpriboleto.php | somente_menu | 0 |
| 2ª Via de Boleto | /smart/financeiro/frmimpriboleto.php | somente_menu | 0 |
| Gerar Remessa | /smart/financeiro/pagtobmp/pagtobmppesquisa.php | tela_observada | 1 |
| Processar retorno | /smart/financeiro/pagtobmp/retornopagtobmp.php | tela_observada | 1 |
| Vincular XML | /smart/financeiro/vincularxml.php | somente_menu | 0 |
| Prazo médio da carteira | /smart/relatorios/prazomediocarteira.php | HTTP_403 | 0 |
| Confirmação | /smart/checagem.php | somente_menu | 0 |
| Cobrança | /smart/modulonaoadquirido.php | somente_menu | 0 |
| Cedentes | /smart/relatorios/concentrcedente.php | tela_observada | 1 |
| Sacados | /smart/relatorios/concentrsacado.php | tela_observada | 1 |
| Cedente/Sacados | /smart/relatorios/concentrcedentesacado.php | tela_observada | 1 |
| Cedentes inoperantes | /smart/relatorios/cedentesinoperantes.php | HTTP_403 | 0 |
| Cadastro de cedentes | /smart/relatorios/cadastrocedente.php | HTTP_403 | 0 |
| Limites de cedentes | /smart/relatorios/cedentelimitevencer.php | HTTP_403 | 0 |
| Limites de sacados | /smart/relatorios/limitesacado.php | HTTP_403 | 0 |
| Títulos quitados com suspeita de fraude | /smart/relatorios/titulosquitadossuspeitafraude.php | HTTP_403 | 0 |
| Cadastro de sacados | /smart/relatorios/cadastrosacado.php | HTTP_403 | 0 |
| Cadastro de Fornecedores | /smart/relatorios/cadastrofornecedor.php | HTTP_403 | 0 |
| Títulos em aberto | /smart/relatorios/titulosabertos.php | HTTP_403 | 0 |
| Notificação ao sacado | /smart/relatorios/notificacaosacado.php | somente_menu | 0 |
| Individualizado | /smart/relatorios/operacoesindividualizado.php | HTTP_403 | 0 |
| Agrupado por cedente | /smart/relatorios/operacoesagrupadocedente.php | HTTP_403 | 0 |
| CCB | /smart/relatorios/operacoesccbnco.php | HTTP_403 | 0 |
| Agenda | /smart/relatorios/conagenda.php | HTTP_403 | 0 |
| Envio de Boleto | /smart/relatorios/historicoenvioboleto.php | HTTP_403 | 0 |
| Envio de Notificação | /smart/relatorios/historicoenvionotificacao.php | HTTP_403 | 0 |
| Envio de Aditivo | /smart/relatorios/historicoenvioaditivo.php | HTTP_403 | 0 |
| Envio de Duplicata | /smart/relatorios/historicoenvioduplicata.php | HTTP_403 | 0 |
| Envio de Nota Promissória | /smart/relatorios/historicoenviopromissoria.php | HTTP_403 | 0 |
| Recompra por motivo | /smart/relatorios/recompramotivo.php | HTTP_403 | 0 |
| Aniversariantes | /smart/relatorios/aniversariantes.php | HTTP_403 | 0 |
| Log de envio de e-mails | /smart/relatorios/logenvioemail.php | HTTP_403 | 0 |
| DOC2YOU | /smart/doc2you.php | somente_menu | 0 |
| Monitoramento de Notas | /smart/financeiro/monitoramentonota.php | somente_menu | 0 |
| SysPro | /smart/contabil/web/exportacao/conexportacaosyspro.php | HTTP_403 | 0 |
| Universidade | /smart/universidade.php | somente_menu | 0 |
| Política de privacidade | /smart/lgpd/politicaprivacidade.php | somente_menu | 0 |
| Documentação API | /smart/apismart/menu/documentacao.php | somente_menu | 0 |
| Extrato detalhado | /smart/minhaconta/extratoimportadoria.php | HTTP_403 | 0 |
| Resumo consumo/custos | /smart/minhaconta/extratousoimportadoria.php | HTTP_403 | 0 |
| Operação Trustee a receber | /smart/trustee/trustoperacao2.php | somente_menu | 0 |
| Títulos | /smart/financeiro/pesquisa.php | somente_menu | 0 |
| Processar retorno (banco) | /smart/financeiro/retornoocorrencia.php | somente_menu | 0 |
| Gerar remessa (banco) | /smart/financeiro/remessaocorrencia.php | somente_menu | 0 |
| (link auxiliar) | /smart/chat/chatcliente.php | somente_menu | 0 |
| (link auxiliar) | /smart/homedashboard.php | somente_menu | 0 |
