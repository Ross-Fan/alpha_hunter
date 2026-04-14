"""
配置加载器模块
负责加载和管理系统配置
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv


class Config:
    """配置管理类"""

    _instance: Optional['Config'] = None
    _config: Dict[str, Any] = {}

    def __new__(cls) -> 'Config':
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._config:
            self._load_config()

    def _load_config(self) -> None:
        """加载配置文件和环境变量"""
        # 加载 .env 文件
        project_root = Path(__file__).parent.parent
        env_path = project_root / '.env'
        load_dotenv(env_path)

        # 加载 config.yaml
        config_path = project_root / 'config' / 'config.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        else:
            # 使用默认配置
            self._config = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """返回默认配置"""
        return {
            'scanner': {
                'chains': ['bsc'],
                'min_market_cap': 1_000_000,
                'max_market_cap': 30_000_000,
                'min_liquidity': 100_000,
            },
            'security': {
                'max_buy_tax': 0.10,
                'max_sell_tax': 0.10,
                'require_open_source': True,
                'reject_honeypot': True,
            },
            'scoring': {
                'holders_change_ideal_min': 0.0,
                'holders_change_ideal_max': 0.2,
                'volume_ratio_ideal_min': 0.05,
                'volume_ratio_ideal_max': 0.3,
            },
            'runtime': {
                'scan_interval': 3600,
            },
            'rate_limit': {
                'binance_alpha': 1,
                'gecko_terminal': 0.15,
                'goplus': 1,
            },
            'logging': {
                'level': 'INFO',
                'console': True,
                'file': True,
                'rotation': '10 MB',
                'retention': '7 days',
            }
        }

    def reload(self) -> None:
        """重新加载配置"""
        self._config = {}
        self._load_config()

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项，支持点号分隔的嵌套路径
        例如: config.get('scanner.min_market_cap')
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    @property
    def scanner(self) -> Dict[str, Any]:
        """扫描器配置"""
        return self._config.get('scanner', {})

    @property
    def security(self) -> Dict[str, Any]:
        """安全检查配置"""
        return self._config.get('security', {})

    @property
    def scoring(self) -> Dict[str, Any]:
        """评分配置"""
        return self._config.get('scoring', {})

    @property
    def runtime(self) -> Dict[str, Any]:
        """运行时配置"""
        return self._config.get('runtime', {})

    @property
    def rate_limit(self) -> Dict[str, Any]:
        """限流配置"""
        return self._config.get('rate_limit', {})

    @property
    def logging_config(self) -> Dict[str, Any]:
        """日志配置"""
        return self._config.get('logging', {})

    @property
    def scan_interval(self) -> int:
        """扫描间隔（秒）"""
        return self.runtime.get('scan_interval', 3600)

    @property
    def supported_chains(self) -> List[str]:
        """支持的链列表"""
        return self.scanner.get('chains', ['bsc'])

    @property
    def min_market_cap(self) -> float:
        """最小市值"""
        return self.scanner.get('min_market_cap', 1_000_000)

    @property
    def max_market_cap(self) -> float:
        """最大市值"""
        return self.scanner.get('max_market_cap', 30_000_000)

    @property
    def min_liquidity(self) -> float:
        """最小流动性"""
        return self.scanner.get('min_liquidity', 100_000)

    @property
    def raw(self) -> Dict[str, Any]:
        """返回原始配置字典"""
        return self._config


# 全局配置实例
config = Config()
