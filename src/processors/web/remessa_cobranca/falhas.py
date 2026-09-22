# -*- coding: utf-8 -*-
"""
falhas.py - a remessa que o Smart GEROU e que nao chegou ao banco deixa rastro.

18/09/2026: em 15/09 o Smart gerou a remessa da MP PROSPERE (id 26381, 60 titulos) e o
robo a DESCARTOU: dois registros com 406 bytes, porque os titulos 104-001 e 105-001 da
NATURAL FOODS traziam o nosso numero de 17 digitos da BB Ativos num campo de 11. O Smart
ja considerava os 60 titulos despachados, o arquivo nunca foi ao banco, e o robo so
escreveu "DESCARTADO - 2 linha(s) fora dos 400 chars (1a: linha 118)". Tres dias depois
eram R$ 492.734,47 sem registro (os 60 titulos, todos em aberto), com os boletos na mao do
sacado, e ninguem sabia de quem era a linha 118.

Agora toda geracao que o robo nao conseguiu baixar, descartou ou deixou incerta vira um
registro no volume compartilhado com o process-automation (`remessa_config.PASTA_FALHAS`):

    <id>.json  quando, conta, motivo, os titulos que a geracao levou (da grade do Smart)
               e os registros culpados (de qual titulo, quantos bytes, por que)
    <id>.REM   os bytes, quando houve download

O vigia do process-automation le isso e investiga todo dia: quanto esta parado, por que e
o que fazer. Nada aqui levanta: registrar a falha e acessorio e nao pode derrubar a rodada.
"""
import json
import os
import re
from datetime import datetime

import exclusoes
import remessa_config as cfg

#: Tamanho do registro CNAB 400.
TAMANHO_REGISTRO = 400
#: Tamanho do nosso numero no layout do MoneyPlus (posicoes 71-81).
DIGITOS_NOSSO_NUMERO_MP = 11


def _registros(dados):
    """Os registros como o banco os conta: separados por fim de linha, e SO por ele.

    (O `splitlines()` do Python tambem quebra em 0x85, 0x0b, 0x0c e 0x1c-0x1e.)
    """
    return [r for r in re.split(rb"\r?\n", dados or b"") if r.strip()]


def _campos(registro):
    """Documento, nosso numero, CNPJ e nome do sacado de um detalhe (tipo 1), tolerando o
    registro maior que 400 bytes por causa do nosso numero longo."""
    texto = registro.decode("latin-1", "replace")
    desloc = max(len(registro) - TAMANHO_REGISTRO, 0)
    return {
        "nosso_numero": texto[70:81 + desloc].strip().lstrip("0"),
        "documento": texto[110 + desloc:120 + desloc].strip(),
        "vencimento": texto[120 + desloc:126 + desloc].strip(),
        "sacado_cnpj": texto[220 + desloc:234 + desloc].strip().lstrip("0"),
        "sacado": texto[234 + desloc:274 + desloc].strip(),
    }


def titulos_do_form(form):
    """Os titulos MARCADOS da grade: documento, CNPJ do sacado, vencimento e valor."""
    saida = []
    for t in form.get("titulos", []) or []:
        if not t.get("marcado"):
            continue
        saida.append({
            "documento": exclusoes.coluna(t, "NO") or "",
            "sacado_cnpj": exclusoes.coluna(t, "SACADO") or "",
            "vencimento": exclusoes.coluna(t, "VENCIMENTO") or "",
            "valor": exclusoes.coluna(t, "VALOR (R$)") or "",
        })
    return saida


def culpados(dados, titulos=None):
    """Os registros com tamanho errado, e de qual titulo sao.

    O titulo sai da grade quando ela veio (o documento aparece dentro do registro, qualquer
    que seja o deslocamento); senao, dos campos lidos com a tolerancia de `_campos`.
    """
    docs = [str(t.get("documento") or "").strip() for t in (titulos or [])]
    achados = []
    for i, reg in enumerate(_registros(dados), 1):
        if len(reg) == TAMANHO_REGISTRO:
            continue
        texto = reg.decode("latin-1", "replace")
        campos = _campos(reg) if texto[:1] == "1" else {}
        doc = next((d for d in docs if d and d in texto), None) or campos.get("documento") or ""
        nosso = campos.get("nosso_numero") or ""
        if len(reg) > TAMANHO_REGISTRO and len(nosso) > DIGITOS_NOSSO_NUMERO_MP:
            motivo = (f"nosso numero de {len(nosso)} digitos ({nosso}) num campo de {DIGITOS_NOSSO_NUMERO_MP}: "
                      f"boleto de outro banco - precisa de boleto novo nesta conta")
        else:
            motivo = f"registro com {len(reg)} bytes (o layout tem {TAMANHO_REGISTRO})"
        achados.append({"linha": i, "bytes": len(reg), "tipo_registro": texto[:1], "documento": doc,
                        "nosso_numero": nosso, "sacado": campos.get("sacado", ""),
                        "sacado_cnpj": campos.get("sacado_cnpj", ""), "motivo": motivo})
    return achados


def titulos_do_arquivo(dados):
    """Os titulos de ENTRADA (01) do arquivo, lidos com tolerancia ao registro longo."""
    saida = []
    for reg in _registros(dados):
        if reg[:1] != b"1":
            continue
        desloc = max(len(reg) - TAMANHO_REGISTRO, 0)
        if reg[108 + desloc:110 + desloc] != b"01":
            continue
        campos = _campos(reg)
        valor = reg[126 + desloc:139 + desloc].decode("latin-1", "replace")
        campos["valor"] = f"{int(valor) / 100:.2f}" if valor.isdigit() else ""
        saida.append(campos)
    return saida


def eh_cnab(dados):
    """O corpo baixado e uma remessa CNAB 400 (cabecalho `01REMESSA`)?

    Com a sessao do Smart caida o download devolve HTML; as linhas dele nao sao registros e
    nao tem culpado — o arquivo no Smart esta integro e basta baixa-lo de novo.
    """
    return bool(dados) and dados.lstrip()[:9] == b"01REMESSA"


def _gravar_atomico(caminho, conteudo):
    temporario = f"{caminho}.tmp{os.getpid()}"
    with open(temporario, "wb") as fh:
        fh.write(conteudo)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(temporario, 0o644)
    os.replace(temporario, caminho)


def registrar(smart_id, *, conta, rotulo, motivo, dados=None, titulos=None, gerada_em=None, pasta=None,
              nome_arquivo=None, log=print):
    """Grava `<smart_id>.json` (e `.REM`, quando ha bytes). Devolve o registro, ou None."""
    try:
        pasta = pasta or cfg.PASTA_FALHAS
        os.makedirs(pasta, exist_ok=True)
        cnab = eh_cnab(dados)
        do_arquivo = titulos_do_arquivo(dados) if cnab else []
        titulos = [dict(t) for t in (titulos or [])] or do_arquivo
        if cnab and titulos is not do_arquivo:
            # completa o nosso numero dos titulos da grade com o que o arquivo traz
            por_doc = {t["documento"]: t for t in do_arquivo}
            for t in titulos:
                extra = por_doc.get(str(t.get("documento") or "").strip()) or {}
                t.setdefault("nosso_numero", extra.get("nosso_numero", ""))
        registro = {
            "versao": 1,
            "smart_id": smart_id,
            "nome_arquivo": nome_arquivo,
            "conta": str(conta or ""),
            "rotulo": rotulo,
            "gerada_em": gerada_em or datetime.now(exclusoes.TZ_SP).isoformat(timespec="seconds"),
            "motivo": motivo,
            "titulos": titulos,
            "culpados": culpados(dados, titulos) if cnab else [],
            "arquivo": f"{smart_id}.REM" if cnab else None,
            "bytes": len(dados) if dados else 0,
            "conteudo_cnab": cnab,
        }
        if cnab:
            _gravar_atomico(os.path.join(pasta, f"{smart_id}.REM"), dados)
        _gravar_atomico(os.path.join(pasta, f"{smart_id}.json"),
                        json.dumps(registro, ensure_ascii=False, indent=1).encode("utf-8"))
        log(f"  falha registrada para o process-automation: {pasta}/{smart_id}.json "
            f"({len(titulos)} titulo(s), {len(registro['culpados'])} culpado(s))")
        return registro
    except Exception as e:                                          # noqa: BLE001
        log(f"  ATENCAO: nao registrei a falha da remessa {smart_id} ({type(e).__name__}: {e})")
        return None


def exportar_controle(controle, caminho=None, log=print):
    """{arquivo: [{id, tipo, md5, bytes, baixado_em}, ...]} no volume compartilhado.

    O nome e o do Smart (sem o `_dupHHMMSS` da pasta local), que e o que o process-automation
    ve em `cnab_remessa_enviada`. Serve para dizer o id da remessa a cancelar na tela
    Download de Remessa. E uma LISTA por nome porque o nome se repete entre contas (18/09/2026:
    CB08090000011 era da mp prospere e da mp wj moreira) — quem escolhe e o md5, que e o dos
    bytes que sobem ao banco.
    """
    try:
        mapa = {}
        for chave, linha in (controle or {}).items():
            nome = re.sub(r"_dup\d+(?=\.REM$)", "", str(linha.get("arquivo") or ""), flags=re.I)
            if nome:
                mapa.setdefault(nome, []).append({
                    "id": int(chave), "tipo": linha.get("tipo"), "md5": linha.get("md5"),
                    "bytes": linha.get("bytes"), "baixado_em": linha.get("baixado_em"),
                })
        caminho = caminho or cfg.ARQ_REMESSAS_GERADAS
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        _gravar_atomico(caminho, json.dumps(mapa, ensure_ascii=False, indent=1).encode("utf-8"))
        return len(mapa)
    except Exception as e:                                          # noqa: BLE001
        log(f"  ATENCAO: nao exportei o controle das remessas ({type(e).__name__}: {e})")
        return 0
