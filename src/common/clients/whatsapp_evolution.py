# -*- coding: utf-8 -*-
"""
whatsapp_evolution.py - envio de WhatsApp pela Evolution API.

POR QUE EXISTE: ate 09/2026 o unico envio de WhatsApp deste repo era um bloco
inline dentro de `boletos/healthcheck.py`. O robo de finalizacao de operacao e
o segundo usuario, e a regra 3 do CLAUDE.md manda extrair antes de duplicar.
As env vars sao DELIBERADAMENTE as mesmas do healthcheck - quem ja configurou
o container nao configura de novo.

NAO CONFUNDIR com `src/clients/whatsapp.py` do process-automation: aquele tem
teto de cadencia por LINHA (8 msg/min, medido em 08/2026 depois de um pico de
16), side-effect guard e DWH, e e o caminho certo para AVISO DE NEGOCIO
recorrente. Este aqui e o minimo para ALERTA OPERACIONAL disparado de dentro
do erp-automation, no mesmo espirito do healthcheck.

⚠️ SEM teto de cadencia. Uma mensagem por execucao de robo e o uso previsto.
   Para disparo em lote (por sacado, por titulo), use o cliente do
   process-automation - o WhatsApp bloqueia a conta, nao a instancia.

Variaveis de ambiente:
  EVOLUTION_API_URL   default `http://evolution-api:8080` (hostname da rede do
                      Docker). No HOST - sandbox - a MESMA API responde em
                      `http://127.0.0.1:8085`, entao la e preciso publicar.
  EVOLUTION_API_KEY   obrigatoria: a API devolve 401 sem ela.
  EVOLUTION_INST_<TAG>_NAME
                      nome real da instancia. TAG e o nome em maiusculas com
                      espaco e hifen virando `_` (Prosperito -> PROSPERITO).
                      Sem a var, usa o proprio nome passado.

Uso:
    from src.common.clients import whatsapp_evolution as wpp
    ok, detalhe = wpp.enviar_texto("5511963226389", "Ola!")
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

#: Instancia padrao do parque. E a linha que fala com o operacional.
INSTANCIA_PADRAO = "Prosperito"

#: Default de container. No host o sandbox publica 127.0.0.1:8085.
URL_PADRAO = "http://evolution-api:8080"

TIMEOUT_S = 15


class SemCredencialEvolution(RuntimeError):
    """EVOLUTION_API_KEY ausente - falha FECHADO, nunca finge que enviou."""


def _api_url() -> str:
    return os.environ.get("EVOLUTION_API_URL", URL_PADRAO).rstrip("/")


def _nome_instancia(instancia: str) -> str:
    """Resolve o nome real da instancia via `EVOLUTION_INST_<TAG>_NAME`.

    Mesma convencao do healthcheck dos boletos: o nome amigavel ('Prosperito')
    nao e necessariamente o nome cadastrado na Evolution.
    """
    tag = instancia.upper().replace(" ", "_").replace("-", "_")
    return os.environ.get(f"EVOLUTION_INST_{tag}_NAME", instancia)


def enviar_texto(numero: str, texto: str, instancia: str = INSTANCIA_PADRAO,
                 timeout: int = TIMEOUT_S) -> tuple[bool, str]:
    """Manda UMA mensagem. Retorna (ok, detalhe). Nunca levanta por falha de rede.

    `numero` no formato internacional sem `+` nem pontuacao: 5511963226389.
    """
    chave = os.environ.get("EVOLUTION_API_KEY", "").strip()
    if not chave:
        # Falha FECHADO e explicita: um "enviado" falso aqui vira robo que
        # ninguem sabe que parou.
        return False, ("EVOLUTION_API_KEY nao definida - a Evolution devolve 401 "
                       "sem ela; nada foi enviado")

    nome = _nome_instancia(instancia)
    alvo = f"{_api_url()}/message/sendText/{nome}"
    corpo = json.dumps({"number": str(numero), "text": texto}).encode("utf-8")
    req = urllib.request.Request(
        alvo, data=corpo, method="POST",
        headers={"Content-Type": "application/json", "apikey": chave})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status in (200, 201):
                return True, f"enviado via {nome}"
            return False, f"HTTP {r.status} de {alvo}"
    except urllib.error.HTTPError as e:
        detalhe = ""
        try:
            detalhe = (e.read() or b"").decode("utf-8", errors="replace")[:160]
        except Exception:  # noqa: BLE001 - o motivo do erro ja e o HTTP
            pass
        dica = ""
        if e.code == 401:
            dica = " (apikey invalida ou ausente)"
        elif e.code == 404:
            dica = f" (instancia '{nome}' nao existe na Evolution)"
        return False, f"HTTP {e.code}{dica}: {detalhe}"
    except urllib.error.URLError as e:
        return False, (f"nao alcancou {alvo}: {e.reason} - dentro do container a "
                       f"URL e {URL_PADRAO}; no host, http://127.0.0.1:8085")
    except Exception as e:  # noqa: BLE001 - aviso nunca derruba quem chama
        return False, f"falha inesperada: {type(e).__name__}: {str(e)[:140]}"


def enviar(numeros, texto: str, instancia: str = INSTANCIA_PADRAO,
           timeout: int = TIMEOUT_S) -> tuple[int, list[tuple[str, bool, str]]]:
    """Manda a MESMA mensagem para varios numeros.

    Retorna (quantos_ok, [(numero, ok, detalhe), ...]).
    """
    if isinstance(numeros, str):
        numeros = [n.strip() for n in numeros.split(",") if n.strip()]
    resultados = []
    for numero in numeros:
        ok, detalhe = enviar_texto(numero, texto, instancia, timeout)
        resultados.append((str(numero), ok, detalhe))
    return sum(1 for _n, ok, _d in resultados if ok), resultados


def main() -> int:
    """Teste manual: `python -m src.common.clients.whatsapp_evolution <numero>`."""
    import argparse

    ap = argparse.ArgumentParser(description="Testa o canal WhatsApp (Evolution).")
    ap.add_argument("numero", nargs="?", default="5511963226389")
    ap.add_argument("--instancia", default=INSTANCIA_PADRAO)
    ap.add_argument("--texto", default="[TESTE] canal WhatsApp do erp-automation.")
    ap.add_argument("--enviar", action="store_true",
                    help="envia de verdade (sem isso so mostra a configuracao)")
    args = ap.parse_args()

    print(f"  url ......: {_api_url()}")
    print(f"  instancia : {args.instancia} -> {_nome_instancia(args.instancia)}")
    print(f"  apikey ...: {'definida' if os.environ.get('EVOLUTION_API_KEY') else 'AUSENTE'}")
    print(f"  destino ..: {args.numero}")
    if not args.enviar:
        print("\n  (use --enviar para mandar de verdade)")
        return 0
    ok, detalhe = enviar_texto(args.numero, args.texto, args.instancia)
    print(f"\n  {'OK' if ok else 'FALHOU'}: {detalhe}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
