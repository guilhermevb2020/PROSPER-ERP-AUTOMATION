# Catálogo da API oficial do Smart

Fonte: https://api.smartsecurities.com.br/api-tools/documentation/Smartsecurities-v2

Coletado em 2026-09-22T12:54:03.537909+00:00.

Uma linha por variante documentada. Não comprova contratação, permissão da conta ou execução.
Autenticação OAuth2; a documentação informa token de 1 hora e limite de 20 chamadas/minuto.
Os contratos completos extraídos (parâmetros e fonte por ação) ficam em `data/sandbox/mapeamento_http/api_oficial.json` e `.csv`.

| Método | Caminho | Capacidade documentada | Parâmetros |
|---|---|---|---|
| POST | /oauth | POST /oauth | grant_type, client_id, client_secret |
| POST | /smartsecurities/avaliacao-carater-cedente | Cadastro de avaliação de caráter para o cedente | cpfCnpj, observacao |
| GET | /smartsecurities/captador | GET /smartsecurities/captador |  |
| GET | /smartsecurities/cedente | Relatório de cedentes | tipoSaida, dataIniCedente, dataFimCedente, dataEmissao, exibePessoasRelacionadas, cpfCnpjCedente |
| GET | /smartsecurities/cedente | Relatório de Receitas por cedente | tipo, emissaoInicial, emissaoFinal, pagamentoInicial, pagamentoFinal, modalidade, tipoReceita, tipoSaida |
| POST | /smartsecurities/cedente | Cadastro de cedente | cpfCnpj, razaoSocial, nomeFantasia, clienteDesde, numeroContratoMae, emailPrincipal, idSetor, idGerente, cpfCnpjGerente, dataNascimento, idEstadoCivil, idRegimeTributario, dataFundacao, capitalSocial, inscricaoEstadual, cnae, idFonteCaptacao, idGrupoAnaliseVadu, idOperador, cpfCnpjOperador, idCaptador, cpfCnpjCaptador, idControlador, cpfCnpjControlador, idResponsavelCobranca, cpfCnpjResponsavelCobranca, cepEnderecoPrincipal, logradouroEnderecoPrincipal, numeroEnderecoPrincipal, complementoEnderecoPrincipal, bairroEnderecoPrincipal, codigoMunicipioIbgeEnderecoPrincipal, cepEnderecoCobranca, logradouroEnderecoCobranca, numeroEnderecoCobranca, complementoEnderecoCobranca, bairroEnderecoCobranca, codigoMunicipioIbgeEnderecoCobranca, enderecoCobrancaIgualAoEnderecoPrincipal, telefones |
| GET | /smartsecurities/cedente[/:cedente_id] | GET /smartsecurities/cedente[/:cedente_id] |  |
| POST | /smartsecurities/configuracao-cobranca-cedente | Cadastro de Configuração de cobrança para o cedente | cpfCnpj, numContaBancaria, numCarteira |
| GET | /smartsecurities/conta-bancaria | Listagem de contas bancárias | cpfCnpjCedenteEscrow |
| GET | /smartsecurities/controlador | GET /smartsecurities/controlador |  |
| POST | /smartsecurities/documento-digitalizado-cedente | Cadastro de documento digitalizado para o cedente | cpfCnpj, idTipoDocumentoDigitalizado, data, extensaoArquivo, conteudoArquivo, idImovel, idVeiculo |
| GET | /smartsecurities/estado-civil | GET /smartsecurities/estado-civil |  |
| GET | /smartsecurities/fonte-captacao | GET /smartsecurities/fonte-captacao |  |
| GET | /smartsecurities/gerente | GET /smartsecurities/gerente |  |
| GET | /smartsecurities/grupo-analise-vadu | GET /smartsecurities/grupo-analise-vadu |  |
| GET | /smartsecurities/imovel | Listagem de imóveis | tipoPessoa, cpfCnpj |
| POST | /smartsecurities/limite-cedente | Cadastro de limite para o cedente | cpfCnpj, limiteDeCredito, dataAprovacao, dataVencimento, controlarclasseRiscoBoletoEspecial, percentualClasseRiscoBoletoEspecial, controlarClasseRiscoOperacaoTranche, percentualClasseRiscoOperacaoTranche, controlarClasseRiscoOperacaoComissaria, percentualClasseRiscoOperacaoComissaria, controlarClasseRiscoBoletoEspecialMaisTranche, percentualClasseRiscoBoletoEspecialMaisTranche, controlarClasseRiscoBoletoGarantido, percentualClasseRiscoBoletoGarantido, controlarClasseRiscoOperacaoClean, percentualClasseRiscoOperacaoClean, controlarClasseRiscoComissariaComEscrow, percentualClasseRiscoComissariaComEscrow, controlarClasseRiscoIntercompany, percentualClasseRiscoIntercompany, controlarClasseRiscoBarter, percentualClasseRiscoBarter, observacoes |
| GET | /smartsecurities/operacao | Relatório de operações individualizado | tipo, tipoSaida, dataIniOperacao, dataFimOperacao, dataIniPagamento, dataFimPagamento, dataIniCedente, dataFimCedente, dataEmissao |
| GET | /smartsecurities/operacao | Relatório de deságio | tipo, tipoSaida, dataIniOperacao, dataFimOperacao, dataIniPagamento, dataFimPagamento, dataIniCedente, dataFimCedente, dataEmissao |
| GET | /smartsecurities/operacao[/:operacao_id] | GET /smartsecurities/operacao[/:operacao_id] |  |
| GET | /smartsecurities/operador | GET /smartsecurities/operador |  |
| GET | /smartsecurities/proximo-numero-contrato-mae-cedente | GET /smartsecurities/proximo-numero-contrato-mae-cedente |  |
| GET | /smartsecurities/regime-tributario | GET /smartsecurities/regime-tributario |  |
| POST | /smartsecurities/regra-cobranca-convencional-cedente | Cadastro de regra de cobrança convencional para o cedente | cpfCnpj, porcentagemDesagio |
| GET | /smartsecurities/relatorio[/:relatorio_id] | Relatório de análise mensal | mes, ano, tipo |
| GET | /smartsecurities/relatorio[/:relatorio_id] | Relatório de receitas financeiras | dataIni, dataFim, tipoConsulta, modalidade, docCedente, tipoSaida |
| GET | /smartsecurities/relatorio[/:relatorio_id] | Relatório de receitas avulsas | dataIni, dataFim, modalidade, docCedente, tipoSaida |
| GET | /smartsecurities/responsavel-cobranca | GET /smartsecurities/responsavel-cobranca |  |
| GET | /smartsecurities/sacado | Relatório de cadastro de sacados | tipoSaida, docSacado, dataIniSacado, dataFimSacado |
| GET | /smartsecurities/setor | GET /smartsecurities/setor |  |
| GET | /smartsecurities/tipo-documento-digitalizado | GET /smartsecurities/tipo-documento-digitalizado |  |
| GET | /smartsecurities/titulo | Relatório de títulos em aberto (receita) | tipo, tipoSaida, noTitulo, noOperacao, nossoNumero, emissaoIni, emissaoFim, vencimentoIni, vencimentoFim, valorIni, valorFim, valorFaceIni, valorFaceFim, apenasTitulosPenhorados, mostrarTitulosInadimplentes, imprimirEndereco, ocultarTarifasJurosMulta, somenteTitulosParciais, titulosComAlertaConfirmacao, mercadoriaPendenteEntrega, titulosComRecomendacaoCompra, dataEmissao |
| GET | /smartsecurities/titulo | Relatório de títulos quitados (receita) | tipo, tipoSaida, noTitulo, quitacaoIni, quitacaoFim, emissaoIni, emissaoFim, valorIni, valorFim, valorFaceIni, valorFaceFim, noOperacao, ocultarTarifasJurosMulta, recebimentoEmAtraso, recebimentoJurosMulta, vencimentoIni, vencimentoFim, nossoNumero, apenasTitulosPenhorados, dataEmissao, docCedente |
| GET | /smartsecurities/titulo | Relatório de títulos quitados (receita) com suspeita de fraude | tipo, tipoSaida, quitacaoIni, quitacaoFim, docCedente, docSacado |
| GET | /smartsecurities/titulo | Relatório de títulos recomprados (receita) | tipo, tipoSaida, tipoTitulo, noTitulo, nossoNumero, periodoRecompraIni, periodoRecompraFim, vencimentoIni, vencimentoFim, valorIni, valorFim, valorFaceIni, valorFaceFim, apenasTitulosPenhorados, ocultarTarifasJurosMulta, dataEmissao |
| GET | /smartsecurities/titulo | Relatório de títulos prorrogados (receita) | tipo, tipoSaida, tipoTitulo, noTitulo, nossoNumero, periodoProrrogacaoIni, periodoProrrogacaoFim, vencimentoIni, vencimentoFim, valorFaceIni, valorFaceFim, apenasTitulosPenhorados, ocultarTarifasJurosMulta, dataEmissao |
| GET | /smartsecurities/titulo | Relatório de títulos rejeitados | tipo, tipoSaida, noTitulo, nossoNumero, vencimentoIni, vencimentoFim, dataOperacaoIni, dataOperacaoFim, valorIni, valorFim, valorFaceIni, valorFaceFim, docCedente, docSacado, apenasTitulosPenhorados, dataEmissao |
| GET | /smartsecurities/titulo | Relatório de títulos baixados | tipo, tipoSaida, noTitulo, noOperacao, nossoNumero, emissaoIni, emissaoFim, dataBaixaIni, dataBaixaFim, vencimentoIni, vencimentoFim, valorFaceIni, valorFaceFim, apenasTitulosPenhorados, mostrarTitulosInadimplementes, ocultarTarifasJurosMulta, dataEmissao, exibirDetalhesBaixaComNegativacao |
| GET | /smartsecurities/titulo | Relatório de títulos a pagar | tipo, tipoSaida, noTitulo, noOperacao, nossoNumero, emissaoIni, emissaoFim, vencimentoIni, vencimentoFim, valorIni, valorFim, valorFaceIni, valorFaceFim, ocultarTarifasJurosMulta, somenteTitulosParciais, titulosComAlertaConfirmacao, titulosDeDespesaOperacional, dataEmissao |
| GET | /smartsecurities/titulo | Relatório de títulos pagos | tipo, tipoSaida, noTitulo, noOperacao, nossoNumero, emissaoIni, emissaoFim, vencimentoIni, vencimentoFim, quitacaoIni, quitacaoFim, valorIni, valorFim, valorFaceIni, valorFaceFim, ocultarTarifasJurosMulta, titulosDeDespesaOperacional, dataEmissao |
| GET | /smartsecurities/veiculo | Listagem de veículos | tipoPessoa, cpfCnpj |
