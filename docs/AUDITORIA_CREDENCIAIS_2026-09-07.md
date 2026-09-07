# Auditoria e limpeza de credenciais do ERP — 07/09/2026

## Padrão obrigatório

O Access Guardian é a fonte única de administração das credenciais core.
O ERP consome apelidos, identidade efêmera do banco e relay SMTP. Não cadastrar
senhas reais em código, documentação, configurações independentes ou backups locais.
VNC entregue pelo Guardian e cookies de sessão são material de execução;
continuam privados e não constituem outra fonte administrativa.

## Estado da limpeza

**Configurações e imagem do ERP migradas.** Sandbox e finalizador usam apelidos;
a imagem limpa v2 está em produção. Reinícios autorizados expressamente pelo usuário.
A única entrega de senha real esperada no ERP é o VNC, gerado pelo Guardian.

| Área | Resultado |
|---|---|
| Ambiente principal e credentials.csv | Apelidos Guardian; senhas de banco e SMTP vazias. VNC mantém entrega operacional pelo Guardian. |
| `/app/.env` do container | Literal legado de DB_PASSWORD removido, campo vazio. Cópia anterior cifrada no Guardian. |
| Logs antigos | Chave CapSolver retirada de oito logs Doc2You e senha VNC de três logs de login manual. Originais cifrados no Guardian. |
| Traces Playwright | 24 ZIPs contendo credencial removidos do ERP após cifragem e conferência integral. Total: 1.197.443.235 bytes. |
| Comentário em robo_pagamento.env | Credencial retirada do comentário; configuração operacional preservada. |
| Histórico Git | Literal SMTP removido de todas as referências locais e do main publicado no GitHub, com force-with-lease. Árvore de trabalho preservada; Git anterior cifrado no Guardian. |
| Build e versionamento | .dockerignore e .gitignore ampliados; exemplos orientam apelidos e relay. |
| Imagem limpa | `erp-automation-erp-automation:guardian-clean-20260907-v2` implantada. Mantém Chrome 149 e certutil. Imagem antiga removida; v2 restaura diretórios /tmp, /run e /var/log sem conteúdo legado. |
| Sandbox e finalizador | Importação, rotas e consumidores ativados. GSMARTPWD3 e __GUARDIAN_SANDBOX_CAPSOLVER_API_KEY__; proxy/CA e NSS privado, trace desativado. |

## Evidência da varredura

O scan final está em `scan_exato-final.json`. Os três literais anteriormente
presentes em sandbox.env e robo_finalizar.env foram retirados. Ao ampliar a
busca para senhas menores, encontramos VNC em três logs antigos e os limpamos.
A correspondência esperada remanescente é VNC no .env.guardian, entrega operacional.
Perfis Chrome e cookies vivos ficam privados e foram preservados.

O histórico Git local e main remoto tiveram a senha SMTP antiga removida. Outros
clones, caches externos e revogação no provedor não foram verificados. A varredura
exata pesquisa segredos conhecidos e variantes raw/base64/URL, não garante ausência
de segredos desconhecidos. Recuperação cifrada está somente no Guardian, na pasta
`auditoria/acompanhamento-erp-2026-09-07/quarentena-erp/`.

## Validação e intercorrências

352 testes passaram no host após a correção da retomada de sessão. A imagem limpa
passou 342 testes com dependências de teste montadas separadamente e rede desligada,
antes dos quatro novos testes de retomada. Os cenários de conferência de PDF destinados
ao host ficaram na suíte do host. Chrome abriu na imagem sem tmpfs de teste.

O primeiro recreate revelou ausência de /tmp na imagem achatada: o teste anterior
usava tmpfs e mascarou essa falta. A imagem v2 corrigiu os diretórios; novo recreate
confirmou container healthy, CDP 9222 e sessão Smart principal autenticada. Crédito
foi retomado pelo Hub. Não tratar as execuções interrompidas como sucessos.

O retorno de pagamento concluiu login e consulta sem arquivos novos após o recreate.
A geração às 14:10 e 14:15 falhou porque Smart apresentou 'Usuário logado' e o
robô procurava #fEmail. O fluxo compartilhado passou a reconhecer a identidade
esperada no campo desabilitado, clicar Entrar e concluir a seleção de empresa.
Seis testes verificam retomada, recusa de outra conta, campo oculto e outro frame.
O desfecho da validação real é registrado no relatório de acompanhamento.

Sandbox CapSolver foi validado por getBalance via apelido (HTTP 200, errorId 0),
sem enviar mensagens nem fazer login desnecessário. Banco consultado com current_user
app_erp_automation e session_user efêmero gdh_*. OpenBao foi removido e a role do ERP
agora é NOLOGIN; os privilégios e propriedade permanecem na role lógica.

## Recuperação operacional confirmada às 14:26

Geração de pagamento 2666187 (14:25) concluiu login, consulta de pendentes e exit 0,
sem pagamentos pendentes. Perfil financeiro tinha cookie de sessão expirado; foi
reiniciado somente o cookie Smart daquele perfil. O fluxo agora aguarda também a
identidade reconhecida durante carregamento assíncrono, tenta retomar e reinicia
cookies Smart quando o site devolve explicitamente 'Sessão Expirada', uma única vez.
A task continua enabled=true e criticality=critical no catálogo. O alerta que diz
'DESABILITADA' é um defeito de apresentação do Hub, corrigido em commit separado.

Crédito 2665935 segue em execução desde 14:08:14, processo e avanço de log conferidos.
As falhas 137 da tentativa anterior e de /tmp ausente são consequência do recreate;
a recuperação não apaga esses registros. Commit da correção Smart: 2381603.

### Segunda rodada confirmada — 14:30

Execução 2666258 de gerar_remessa_pagamento_cnab_240: success/exit 0 em 14:30,
sessão válida e consulta de pendentes concluída, zero pagamentos. Confirma duas
rodadas consecutivas boas (14:25 e 14:30). Retorno 2666231 de 14:28 também success.
Crédito 2665935 continua em execução, sem novo restart. O catálogo mantém pagamento
enabled=true; correção de texto do alerta está no commit b9367b4 do Hub e ainda
não foi implantada no processo principal do orquestrador.
