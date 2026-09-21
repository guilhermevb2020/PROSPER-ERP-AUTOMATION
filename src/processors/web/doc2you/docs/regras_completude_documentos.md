# Regras de Completude — Documentos Assinados por Operação (Doc2You)

> Base para o **futuro job de verificação** que vai conferir, por operação, se todos
> os documentos assinados esperados foram baixados, e **avisar os operadores** quando
> faltar algo. Regras passadas pelo operacional em 23/06/2026 (validação do dia 19/06).

## 1. Documentos esperados em TODA operação
- **Aditivo** (de securitização)
- **Nota Promissória**
- **Carta de Cessão** — **UMA POR SACADO** (nº de cartas na pasta = nº de sacados
  distintos da operação no DWH). Esta é uma regra de CONTAGEM, não só de presença.

## 2. Documento de LASTRO conforme o TIPO DO TÍTULO
O documento de lastro varia conforme o **tipo do título** da operação (campo do ERP).
**NÃO basta checar "tem duplicata?"** — depende do tipo:

| Tipo do título | Sigla (DWH `dim_tipo_titulo`) | Documento de lastro esperado | Tem Duplicata? |
|----------------|-------|------------------------------|----------------|
| Duplicata       | `DMR` (mercantil) / `DSR` (serviço) / `DUR` (rural) | **Duplicata** | ✅ Sim |
| Letra de Câmbio | `LCB` | **Letra de Câmbio**          | ❌ Não |
| Cheque          | `CHQ` | (cheque — sem doc de lastro no Doc2You) | ❌ Não |
| Nota Promissória| `NPP` | (a própria Nota Promissória) | ❌ Não |

> Resumo: só operações **DUP** devem ter Duplicata. **LCB** deve ter Letra de Câmbio.
> **CHQ** e **NPP** não têm duplicata — não é falta, é o tipo do título.

## 3. Lógica recomendada para o job de verificação
Para cada operação do dia:
1. Buscar no DWH: **tipo do título** (`dim_tipo_titulo`) e o **nº de sacados distintos**
   (`SELECT COUNT(DISTINCT fk_sacado) FROM dwh.fct_operacoes_detalhe WHERE id_operacao=...`).
2. Conferir na pasta `DOCUMENTOS ASSINADOS/<operação>/`:
   - tem **Aditivo**? (≥1)
   - tem **Nota Promissória**? (≥1)
   - **nº de Cartas de Cessão == nº de sacados**? (uma por sacado — regra de contagem)
   - tem o **lastro do tipo** (Duplicata se DMR/DSR/DUR; Letra de Câmbio se LCB)?
3. Se faltar algo **esperado para aquele tipo** → mensagem para os operadores
   (Marcos, Fernando, Raphael) via instância Prosperito.
4. NÃO alertar falta de duplicata em operações CHQ/NPP/LCB (é o esperado).

## 4. Casos validados (19/06/2026)
| Operação | Situação | Veredito |
|----------|----------|----------|
| 62192 | falta duplicata — tipo **CHQ** | ✅ correto (cheque não tem duplicata) |
| 62131 | falta duplicata — tipo **NPP** | ✅ correto |
| 62125 | falta duplicata, tem letra — tipo **LCB** | ✅ correto (LCB tem Letra de Câmbio, não duplicata) |
| 62172 | falta **Nota Promissória** | ⚠️ falta no SISTEMA também — não é erro do robô; operador envia manual |
| 62138 | falta **Aditivo** | ✅ robô correto — tinha 2 aditivos: o de **19/06 foi IGNORADO** (status `I`), e o **válido/concluído é de 22/06** (`C`). O robô rodou pra 19/06 → pulou o ignorado certo; o concluído entra no run de **22/06**, na mesma pasta `62138/` |

## 5. Status do documento no Doc2You (CRÍTICO)
Cada documento tem um **status**. O robô só baixa os **`C` = Concluído/Assinado**.
- **`C`** = concluído/assinado → **baixado**.
- **`I`** = **Ignorado** (documento substituído/cancelado — ex.: aditivo re-emitido) → **NÃO baixado** (correto).

Implicações para o job de verificação:
- **Documentos de uma operação podem estar em DATAS diferentes.** Ex.: a 62138 teve o
  aditivo ignorado em 19/06 e o aditivo válido **re-emitido em 22/06**. A estrutura
  **por operação** junta tudo (o run de cada dia faz upload na mesma pasta `<operação>/`).
- Por isso a verificação deve olhar a **operação como um todo** (todas as datas), não só
  o dia. Uma operação pode parecer incompleta logo após o 1º dia e completar dias depois
  (re-emissão). Dar essa folga antes de alertar o operador.
- "Faltando na pasta" pode ser: **(a)** doc ignorado/substituído (status `I`), **(b)**
  doc válido em outra data ainda não processada, ou **(c)** realmente inexistente.
  Distinguir consultando o Doc2You (status + datas) antes de alertar.

## 6. Pendência conhecida do robô (a corrigir)
- **Colisão de nomes**: no dia 19/06, 896 baixados → 882 arquivos (14 sobrescritos).
  Acontece quando a operação tem **2+ documentos do mesmo tipo sem campo distintivo**
  no nome (Aditivo/NP/Recibo só levam o nº da operação). Fix: incluir o id do doc
  (`chk`) ou um contador no nome quando houver repetição, para não perder documento.
