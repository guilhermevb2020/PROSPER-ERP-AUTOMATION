# -*- coding: utf-8 -*-
"""Watchdog + reset do zero para o robo de analise de credito.

PROBLEMA: o robo so tem timeout POR CHAMADA (goto 60s, frame 30s...). Se algo
TRAVA fora de um timeout (deadlock, sleep preso, rede pendurada), o processo
fica bloqueado para sempre, sem auto-recuperacao.

SOLUCAO: um WATCHDOG em thread separada monitora um "heartbeat". O robo bate o
heartbeat (`bater()`) no inicio de cada passo (ciclo, op, scan, download,
conferencia). Se ficar mais de `max_ocioso` segundos sem bater, o watchdog
MATA o Chrome (pkill no user-data-dir) -> a chamada Playwright travada do thread
principal levanta erro -> o main() cai no except -> RELANCA o contexto do ZERO
(Chrome novo + login limpo). E o "travar -> reiniciar do zero" automatico.

Tambem expoe `limpar_residual()` (mata chrome antigo + remove o lock do perfil)
para garantir um relancamento limpo, e `reapar_zumbis()` (best-effort).
"""
import os
import subprocess
import threading
import time


def limpar_residual(user_data_dir: str) -> None:
    """Mata qualquer Chrome rodando neste perfil e remove o SingletonLock, para o
    proximo launch_persistent_context subir limpo (reset do zero)."""
    try:
        subprocess.run(["pkill", "-9", "-f", f"user-data-dir={user_data_dir}"],
                       timeout=10)
    except Exception:
        pass
    time.sleep(1)
    for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            os.remove(os.path.join(user_data_dir, lock))
        except Exception:
            pass


def reapar_zumbis() -> None:
    """Best-effort: colhe filhos zumbis (defunct) deste processo p/ nao acumular."""
    try:
        while True:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
    except Exception:
        pass


class Watchdog:
    """Heartbeat watchdog em thread. Uso:
        wd = Watchdog(user_data_dir, max_ocioso=360)
        wd.start(); ... wd.bater("ciclo 1") ...; wd.parar()
    `disparou()` indica se ele matou o Chrome por travamento."""

    def __init__(self, user_data_dir: str, max_ocioso: int = 360,
                 checar_a_cada: int = 15):
        self.user_data_dir = user_data_dir
        self.max_ocioso = max_ocioso
        self.checar_a_cada = checar_a_cada
        self._ultimo = time.time()
        self._etapa = "inicio"
        self._stop = threading.Event()
        self._disparou = False
        self._thread = None

    def bater(self, etapa: str = "") -> None:
        """Marca atividade (chamar no inicio de cada passo do robo)."""
        self._ultimo = time.time()
        if etapa:
            self._etapa = etapa

    def start(self) -> None:
        self._stop.clear()
        self._disparou = False
        self._ultimo = time.time()
        self._thread = threading.Thread(target=self._rodar, daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._stop.set()

    def disparou(self) -> bool:
        return self._disparou

    def _rodar(self) -> None:
        while not self._stop.wait(self.checar_a_cada):
            ocioso = time.time() - self._ultimo
            if ocioso > self.max_ocioso:
                print(f"[WATCHDOG] TRAVOU ha {ocioso:.0f}s (etapa='{self._etapa}') "
                      f"-> matando Chrome p/ reiniciar do zero", flush=True)
                self._disparou = True
                limpar_residual(self.user_data_dir)
                return  # apos matar, encerra; o main() detecta o erro e relanca
