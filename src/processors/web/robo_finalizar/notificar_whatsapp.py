# -*- coding: utf-8 -*-
"""
notificar_whatsapp.py - canal de WhatsApp do robo de finalizar operacao.

ADAPTADO AO SERVIDOR em 02/09/2026. O pacote de origem tinha tres providers e
o default era `baileys_local` - um bot Node na maquina Windows do autor, que
chamava ate PowerShell para checar processo. Nada disso existe aqui. O envio
real agora e DELEGADO a `src/common/clients/whatsapp_evolution.py`, o mesmo
codigo que ja atende o healthcheck dos boletos:

  - dentro do CONTAINER: EVOLUTION_API_URL/EVOLUTION_API_KEY ja estao no
    ambiente (env_file do docker-compose) e `evolution-api:8080` resolve na
    prospere-network -> funciona sem configurar nada;
  - no SANDBOX (host): o harness publica as duas a partir de
    config/sandbox.env (a API responde em 127.0.0.1:8085 do host).

A INTERFACE do pacote foi preservada - `enviar(texto, destinos, provider)`
retornando (n_ok, [(numero, ok, detalhe)]) - porque e o que o orquestrador
(`robo_finalizar._avisar_finalizacao`) chama. So os providers mudaram:

  evolution -> modulo comum (default)
  arquivo   -> grava num .txt em vez de enviar (ensaio)
  nenhum    -> desligado
  baileys_local -> APOSENTADO; devolve erro explicativo em vez de sumir,
                   para um env antigo nao virar silencio.

Uso isolado:
  python notificar_whatsapp.py --teste --provider arquivo
"""
import argparse
import os
import sys
from datetime import datetime

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import r7_config as cfg  # noqa: E402

# O modulo comum vive em src/common/clients/. Quando rodamos com PYTHONPATH na
# raiz do projeto (producao: /app; sandbox: o repo) o import absoluto resolve.
try:
    from src.common.clients import whatsapp_evolution as _wpp
except ImportError:  # rodando avulso, sem PYTHONPATH na raiz
    _RAIZ_REPO = os.path.abspath(os.path.join(_AQUI, "..", "..", ".."))
    if _RAIZ_REPO not in sys.path:
        sys.path.insert(0, _RAIZ_REPO)
    from src.common.clients import whatsapp_evolution as _wpp


# --------------------------------------------------------------------------- #
# providers
# --------------------------------------------------------------------------- #
def _via_evolution(numero, texto):
    return _wpp.enviar_texto(numero, texto, instancia=cfg.WHATSAPP_INSTANCIA)


def _via_arquivo(numero, texto):
    try:
        with open(cfg.WHATSAPP_ARQUIVO_SAIDA, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} -> {numero} =====\n{texto}\n")
        return True, f"gravado em {cfg.WHATSAPP_ARQUIVO_SAIDA}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:120]


def _via_baileys_aposentado(numero, _texto):
    return False, ("provider 'baileys_local' era o bot da maquina Windows de "
                   "origem e nao existe neste servidor - use evolution")


_PROVIDERS = {"evolution": _via_evolution, "arquivo": _via_arquivo,
              "baileys_local": _via_baileys_aposentado}


def enviar(texto, destinos=None, provider=None):
    """Manda a mensagem. Retorna (enviados, [(numero, ok, detalhe)])."""
    provider = (provider or cfg.WHATSAPP_PROVIDER).strip().lower()
    destinos = destinos or cfg.WHATSAPP_DESTINO
    if not cfg.WHATSAPP_ATIVO or provider in ("nenhum", "", "off"):
        return 0, [("-", False, "WhatsApp desligado (R7_WHATSAPP_ATIVO=0)")]
    fn = _PROVIDERS.get(provider)
    if fn is None:
        return 0, [("-", False, f"provider desconhecido: {provider}")]
    resultados = []
    for numero in destinos:
        ok, detalhe = fn(numero, texto)
        resultados.append((numero, ok, detalhe))
    return sum(1 for _n, ok, _d in resultados if ok), resultados


def main():
    ap = argparse.ArgumentParser(description="Canal WhatsApp do robo de finalizar.")
    ap.add_argument("--teste", action="store_true", help="manda uma mensagem de teste")
    ap.add_argument("--para", default="", help="numero(s) separados por virgula")
    ap.add_argument("--provider", default="", help="evolution | arquivo | nenhum")
    ap.add_argument("--texto", default="")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    tem_chave = "definida" if os.environ.get("EVOLUTION_API_KEY") else "AUSENTE"
    print(f"provider: {args.provider or cfg.WHATSAPP_PROVIDER} | "
          f"instancia: {cfg.WHATSAPP_INSTANCIA} | apikey: {tem_chave}")
    print(f"destino: {[d for d in (args.para.split(',') if args.para else cfg.WHATSAPP_DESTINO) if d]}")
    if not args.teste:
        print("\n(use --teste para enviar de verdade)")
        return 0
    texto = args.texto or ("[TESTE] Robo de finalizar operacao - canal de WhatsApp "
                           "funcionando. Este e o aviso das finalizacoes.")
    destinos = [d.strip() for d in args.para.split(",") if d.strip()] or None
    n, res = enviar(texto, destinos, args.provider or None)
    for numero, ok, detalhe in res:
        print(f"  {numero}: {'OK' if ok else 'FALHOU'} - {detalhe}")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
