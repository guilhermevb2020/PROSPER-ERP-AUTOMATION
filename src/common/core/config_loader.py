#!/usr/bin/env python3
"""
=============================================================================================
MÓDULO: config_loader.py
DESCRIÇÃO: Carrega configurações de processadores (processors.yaml) e credenciais (credentials.csv)
           Implementa sistema de rotação de credenciais (round-robin, sequential)
=============================================================================================
"""

import csv
import yaml
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# =============================================================================================
# TIPOS E ENUMS
# =============================================================================================

class LoginPolicy(Enum):
    """Políticas de rotação de credenciais"""
    ROUND_ROBIN = "round_robin"  # Alterna entre credenciais a cada execução
    SEQUENTIAL = "sequential"    # Usa na ordem, uma por vez até esgotar
    RANDOM = "random"            # Escolhe aleatoriamente
    FIRST_AVAILABLE = "first"    # Sempre usa a primeira ativa


@dataclass
class Credential:
    """Representa uma credencial de login"""
    processador: str
    cliente: str
    usuario: str
    senha: str
    ativo: bool

    def __repr__(self):
        return f"Credential(processador={self.processador}, usuario={self.usuario[:3]}***)"


@dataclass
class ProcessorConfig:
    """Configuração de um processador"""
    nome: str
    display: str
    api_port: int
    vnc_port: Optional[int]  # Porta VNC (opcional, calculada automaticamente se None)
    execution_mode: str  # "one-shot" ou "loop"
    interval_seconds: int
    cron: str
    login_policy: LoginPolicy
    enable_screenshots: bool
    screenshot_level: str
    enable_execution_logs: bool
    log_level: str
    timeout_captcha: int
    timeout_download: int
    hardware_profile_index: Optional[int] = None  # Override de perfil de hardware (opcional)


@dataclass
class AntiDetectionConfig:
    """Configuração global de anti-detecção"""
    timezone: str
    locale: str
    hardware_auto_assign: bool
    hardware_default_index: Optional[int]
    viewport_width: Optional[int]
    viewport_height: Optional[int]
    proxy_enabled: bool
    proxy_type: str
    proxy_config: Dict[str, Any]
    webrtc_block: bool
    fingerprints_canvas: bool
    fingerprints_webgl: bool
    fingerprints_audio: bool
    fingerprints_navigator: bool
    fingerprints_chrome_runtime: bool
    network_restore_fetch: bool
    network_use_xhr: bool
    behavior_mouse_movements: bool
    behavior_typing_delays: bool
    behavior_scroll_simulation: bool
    behavior_min_delay_ms: int
    behavior_max_delay_ms: int
    headers: Dict[str, str]


# =============================================================================================
# CONFIG LOADER
# =============================================================================================

class ConfigLoader:
    """
    Carrega e gerencia configurações de processadores e credenciais.

    Arquivos:
    - config/processors.yaml: Configurações de cada processador
    - config/credentials.csv: Credenciais de login (com rotação)
    """

    def __init__(
        self,
        processors_yaml_path: str = "config/processors.yaml",
        credentials_csv_path: str = "config/credentials.csv",
        anti_detection_yaml_path: str = "config/anti_detection.yaml"
    ):
        """
        Args:
            processors_yaml_path: Caminho para processors.yaml
            credentials_csv_path: Caminho para credentials.csv
            anti_detection_yaml_path: Caminho para anti_detection.yaml
        """
        # Calcular caminho base: src/common/core/config_loader.py -> raiz do projeto
        # __file__ = src/common/core/config_loader.py
        # .parent = src/common/core/
        # .parent = src/common/
        # .parent = src/
        # .parent = raiz do projeto
        self.base_path = Path(__file__).parent.parent.parent.parent
        self.processors_yaml_path = self.base_path / processors_yaml_path
        self.credentials_csv_path = self.base_path / credentials_csv_path
        self.anti_detection_yaml_path = self.base_path / anti_detection_yaml_path

        self.processors_config: Dict[str, ProcessorConfig] = {}
        self.credentials: Dict[str, List[Credential]] = {}  # {processador: [credentials]}
        self.credential_index: Dict[str, int] = {}  # {processador: current_index}
        self.anti_detection_config: Optional[AntiDetectionConfig] = None

        self._load_configs()

    # =========================================================================================
    # CARREGAMENTO
    # =========================================================================================

    def _load_configs(self):
        """Carrega processors.yaml, credentials.csv e anti_detection.yaml"""
        self._load_processors_yaml()
        self._load_credentials_csv()
        self._load_anti_detection_yaml()

    def _load_processors_yaml(self):
        """Carrega configurações de processadores do YAML"""
        if not self.processors_yaml_path.exists():
            raise FileNotFoundError(
                f"Arquivo de configuração não encontrado: {self.processors_yaml_path}"
            )

        with open(self.processors_yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Configurações globais (fallback)
        global_config = data.get('_global', {})

        # Carregar cada processador
        for proc_name, proc_data in data.items():
            if proc_name.startswith('_'):  # Ignorar _global e outras chaves especiais
                continue

            # Mesclar com configurações globais (proc_data tem prioridade)
            merged_config = {**global_config, **proc_data}

            # Calcular vnc_port se não especificado (6080 + (display_num - 1))
            vnc_port = merged_config.get('vnc_port')
            if vnc_port is None:
                # Calcular automaticamente baseado no display
                display_str = merged_config.get('display', ':1')
                display_num = display_str.replace(':', '')
                try:
                    display_num_int = int(display_num) if display_num.isdigit() else 1
                    vnc_port = 6080 + (display_num_int - 1)
                except (ValueError, AttributeError):
                    vnc_port = 6080  # Fallback

            self.processors_config[proc_name] = ProcessorConfig(
                nome=proc_name,
                display=merged_config.get('display', ':1'),
                api_port=merged_config.get('api_port', 6090),
                vnc_port=vnc_port,
                execution_mode=merged_config.get('execution_mode', 'one-shot'),  # "one-shot" ou "loop"
                interval_seconds=merged_config.get('interval_seconds', 300),
                cron=merged_config.get('cron', '0 */2 * * *'),
                login_policy=LoginPolicy(merged_config.get('login_policy', 'round_robin')),
                enable_screenshots=merged_config.get('enable_screenshots', True),
                screenshot_level=merged_config.get('screenshot_level', 'milestones'),
                enable_execution_logs=merged_config.get('enable_execution_logs', True),
                log_level=merged_config.get('log_level', 'INFO'),
                timeout_captcha=merged_config.get('timeout_captcha', 100),
                timeout_download=merged_config.get('timeout_download', 90),
                hardware_profile_index=merged_config.get('hardware_profile_index', None),  # Override opcional
            )

    def _load_credentials_csv(self):
        """Carrega credenciais do CSV"""
        if not self.credentials_csv_path.exists():
            raise FileNotFoundError(
                f"Arquivo de credenciais não encontrado: {self.credentials_csv_path}"
            )

        with open(self.credentials_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                processador = row['processador']
                ativo = row['ativo'].lower() == 'true'

                if not ativo:
                    continue  # Ignora credenciais inativas

                credential = Credential(
                    processador=processador,
                    cliente=row['cliente'],
                    usuario=row['usuario'],
                    senha=row['senha'],
                    ativo=ativo
                )

                if processador not in self.credentials:
                    self.credentials[processador] = []
                    self.credential_index[processador] = 0

                self.credentials[processador].append(credential)

    def _load_anti_detection_yaml(self):
        """Carrega configurações de anti-detecção do YAML"""
        if not self.anti_detection_yaml_path.exists():
            # Usar valores padrão se arquivo não existe
            self.anti_detection_config = AntiDetectionConfig(
                timezone="America/Sao_Paulo",
                locale="pt-BR",
                hardware_auto_assign=True,
                hardware_default_index=None,
                viewport_width=None,
                viewport_height=None,
                proxy_enabled=False,
                proxy_type="iproyal",
                proxy_config={},
                webrtc_block=True,
                fingerprints_canvas=True,
                fingerprints_webgl=True,
                fingerprints_audio=True,
                fingerprints_navigator=True,
                fingerprints_chrome_runtime=True,
                network_restore_fetch=True,
                network_use_xhr=False,
                behavior_mouse_movements=True,
                behavior_typing_delays=True,
                behavior_scroll_simulation=True,
                behavior_min_delay_ms=100,
                behavior_max_delay_ms=500,
                headers={
                    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Connection': 'keep-alive',
                    'Cache-Control': 'max-age=0',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
            return

        with open(self.anti_detection_yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        # Hardware
        hardware = data.get('hardware', {})
        hardware_auto_assign = hardware.get('auto_assign', True)
        hardware_default_index = hardware.get('default_index')

        # Viewport
        viewport = data.get('viewport', {})
        viewport_width = viewport.get('width')
        viewport_height = viewport.get('height')

        # Proxy
        proxy = data.get('proxy', {})
        proxy_enabled = proxy.get('enabled', False)
        proxy_type = proxy.get('type', 'iproyal')
        proxy_config = {}
        if proxy_enabled:
            if proxy_type == 'iproyal':
                endpoint = proxy.get('iproyal', {}).get('endpoint', '')
                if endpoint:
                    proxy_config = {'server': endpoint}
            elif proxy_type == 'brightdata':
                # BrightData: não criar proxy_config aqui (será criado dinamicamente em create_browser())
                # Credenciais vêm do .env (BRIGHTDATA_PROXY_USERNAME, BRIGHTDATA_PROXY_PASSWORD)
                # Session ID será gerado automaticamente baseado no nome do processador
                proxy_config = {}  # Vazio - será criado dinamicamente
            elif proxy_type == 'custom':
                custom = proxy.get('custom', {})
                server = custom.get('server', '')
                username = custom.get('username', '')
                password = custom.get('password', '')
                if server:
                    proxy_config = {'server': server}
                    if username and password:
                        proxy_config['username'] = username
                        proxy_config['password'] = password

        # Fingerprints
        fingerprints = data.get('fingerprints', {})
        
        # Network
        network = data.get('network', {})
        
        # Behavior
        behavior = data.get('behavior', {})

        self.anti_detection_config = AntiDetectionConfig(
            timezone=data.get('timezone', 'America/Sao_Paulo'),
            locale=data.get('locale', 'pt-BR'),
            hardware_auto_assign=hardware_auto_assign,
            hardware_default_index=hardware_default_index,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            proxy_enabled=proxy_enabled,
            proxy_type=proxy_type,
            proxy_config=proxy_config,
            webrtc_block=data.get('webrtc', {}).get('block', True),
            fingerprints_canvas=fingerprints.get('canvas', True),
            fingerprints_webgl=fingerprints.get('webgl', True),
            fingerprints_audio=fingerprints.get('audio', True),
            fingerprints_navigator=fingerprints.get('navigator', True),
            fingerprints_chrome_runtime=fingerprints.get('chrome_runtime', True),
            network_restore_fetch=network.get('restore_fetch', True),
            network_use_xhr=network.get('use_xhr', False),
            behavior_mouse_movements=behavior.get('mouse_movements', True),
            behavior_typing_delays=behavior.get('typing_delays', True),
            behavior_scroll_simulation=behavior.get('scroll_simulation', True),
            behavior_min_delay_ms=behavior.get('min_delay_ms', 100),
            behavior_max_delay_ms=behavior.get('max_delay_ms', 500),
            headers=data.get('headers', {
                'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Connection': 'keep-alive',
                'Cache-Control': 'max-age=0',
                'Upgrade-Insecure-Requests': '1',
            })
        )

    # =========================================================================================
    # API PÚBLICA
    # =========================================================================================

    def get_processor_config(self, processor_name: str) -> ProcessorConfig:
        """
        Obtém configuração de um processador.

        Args:
            processor_name: Nome do processador (ex: "relatorio_operacao_desagio")

        Returns:
            ProcessorConfig com todas as configurações

        Raises:
            KeyError: Se processador não existe
        """
        if processor_name not in self.processors_config:
            raise KeyError(f"Processador '{processor_name}' não encontrado em processors.yaml")

        return self.processors_config[processor_name]

    def get_credentials(self, processor_name: str, all_credentials: bool = False) -> Optional[Credential]:
        """
        Obtém credencial para um processador (com rotação automática).

        Args:
            processor_name: Nome do processador
            all_credentials: Se True, retorna todas as credenciais (sem rotação)

        Returns:
            Credential ou None se não houver credenciais
        """
        if processor_name not in self.credentials:
            return None

        creds = self.credentials[processor_name]

        if not creds:
            return None

        if all_credentials:
            return creds

        # Obter política de login
        try:
            config = self.get_processor_config(processor_name)
            policy = config.login_policy
        except KeyError:
            policy = LoginPolicy.ROUND_ROBIN  # Padrão

        # Aplicar política
        if policy == LoginPolicy.ROUND_ROBIN:
            return self._get_round_robin_credential(processor_name)
        elif policy == LoginPolicy.SEQUENTIAL:
            return self._get_sequential_credential(processor_name)
        elif policy == LoginPolicy.FIRST_AVAILABLE:
            return creds[0]
        else:
            return creds[0]  # Fallback

    def _get_round_robin_credential(self, processor_name: str) -> Credential:
        """Retorna próxima credencial no round-robin"""
        creds = self.credentials[processor_name]
        current_index = self.credential_index[processor_name]

        # Pegar credencial atual
        credential = creds[current_index]

        # Avançar índice (circular)
        self.credential_index[processor_name] = (current_index + 1) % len(creds)

        return credential

    def _get_sequential_credential(self, processor_name: str) -> Credential:
        """Retorna credencial sequencial (não rotaciona até reiniciar)"""
        creds = self.credentials[processor_name]
        current_index = self.credential_index[processor_name]

        return creds[current_index]

    def list_processors(self) -> List[str]:
        """Lista todos os processadores configurados"""
        return list(self.processors_config.keys())

    def list_credentials_for_processor(self, processor_name: str) -> List[Credential]:
        """Lista todas as credenciais de um processador"""
        return self.credentials.get(processor_name, [])

    def get_anti_detection_config(self) -> AntiDetectionConfig:
        """
        Obtém configuração global de anti-detecção.

        Returns:
            AntiDetectionConfig com todas as configurações
        """
        if self.anti_detection_config is None:
            raise RuntimeError("Configuração de anti-detecção não foi carregada")
        return self.anti_detection_config


# =============================================================================================
# SINGLETON (Opcional)
# =============================================================================================

_config_loader_instance: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    """
    Retorna instância singleton do ConfigLoader.

    Usage:
        from src.common.core.config_loader import get_config_loader

        loader = get_config_loader()
        config = loader.get_processor_config("relatorio_operacao_desagio")
        credential = loader.get_credentials("relatorio_operacao_desagio")
    """
    global _config_loader_instance

    if _config_loader_instance is None:
        _config_loader_instance = ConfigLoader()

    return _config_loader_instance


# =============================================================================================
# EXEMPLO DE USO
# =============================================================================================

if __name__ == "__main__":
    loader = ConfigLoader()

    print("="*80)
    print("PROCESSADORES CONFIGURADOS")
    print("="*80)
    for proc_name in loader.list_processors():
        config = loader.get_processor_config(proc_name)
        print(f"\n{proc_name}:")
        print(f"  Display: {config.display}")
        print(f"  API Port: {config.api_port}")
        print(f"  Login Policy: {config.login_policy.value}")
        print(f"  Timeout Download: {config.timeout_download}s")

    print("\n" + "="*80)
    print("CREDENCIAIS")
    print("="*80)
    for proc_name in loader.list_processors():
        creds = loader.list_credentials_for_processor(proc_name)
        print(f"\n{proc_name}: {len(creds)} credenciais")
        for i, cred in enumerate(creds, 1):
            print(f"  {i}. {cred.usuario} (ativo: {cred.ativo})")

    print("\n" + "="*80)
    print("TESTE DE ROTAÇÃO (ROUND-ROBIN)")
    print("="*80)
    proc = "relatorio_operacao_desagio"
    print(f"\nProcessador: {proc}")
    for i in range(5):
        cred = loader.get_credentials(proc)
        print(f"  Execução {i+1}: {cred.usuario if cred else 'SEM CREDENCIAIS'}")
