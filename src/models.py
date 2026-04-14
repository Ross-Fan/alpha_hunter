"""
数据模型定义
定义系统中使用的所有数据结构
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


# 链 ID 到链名的映射（在 Enum 外部定义）
CHAIN_ID_MAP = {
    '56': 'bsc',      # BSC
    'bsc': 'bsc',
    'bnb': 'bsc',
    '8453': 'base',   # Base
    'base': 'base',
    '1': 'eth',       # Ethereum
    'eth': 'eth',
    '42161': 'arb',   # Arbitrum
    'arb': 'arb',
    'solana': 'solana',
    'sol': 'solana',
}


class Chain(Enum):
    """支持的区块链"""
    BSC = "bsc"
    BASE = "base"
    SOLANA = "solana"
    ETH = "eth"
    ARB = "arb"

    @classmethod
    def from_string(cls, value: str) -> 'Chain':
        """从字符串解析链类型"""
        normalized = CHAIN_ID_MAP.get(str(value).lower(), 'bsc')
        return cls(normalized)

    @classmethod
    def get_chain_ids(cls, chain_name: str) -> list:
        """获取链名对应的所有可能 ID"""
        ids = []
        for chain_id, name in CHAIN_ID_MAP.items():
            if name == chain_name.lower():
                ids.append(chain_id)
        return ids


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass
class TokenInfo:
    """代币基础信息"""
    symbol: str
    name: str
    contract_address: str
    chain: Chain

    # Binance Alpha 数据
    token_id: str = ""
    price: float = 0.0
    market_cap: float = 0.0
    holders: int = 0
    alpha_points: float = 0.0

    # GeckoTerminal 补充数据
    liquidity_usd: float = 0.0
    volume_24h: float = 0.0
    price_change_24h: float = 0.0

    # 元数据
    first_seen: float = 0.0
    last_update: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'symbol': self.symbol,
            'name': self.name,
            'contract_address': self.contract_address,
            'chain': self.chain.value,
            'token_id': self.token_id,
            'price': self.price,
            'market_cap': self.market_cap,
            'holders': self.holders,
            'liquidity_usd': self.liquidity_usd,
            'volume_24h': self.volume_24h,
            'price_change_24h': self.price_change_24h,
            'first_seen': self.first_seen,
            'last_update': self.last_update,
        }


@dataclass
class SecurityInfo:
    """
    代币安全检查结果

    注意：Optional 字段为 None 表示 API 未返回该数据，需要保守处理
    """
    contract_address: str
    chain: Chain

    # GoPlus 检查项 - None 表示未知（需保守处理）
    is_open_source: Optional[bool] = None
    is_proxy: Optional[bool] = None
    is_mintable: Optional[bool] = None
    can_take_back_ownership: Optional[bool] = None
    owner_change_balance: Optional[bool] = None
    hidden_owner: Optional[bool] = None
    selfdestruct: Optional[bool] = None
    external_call: Optional[bool] = None
    honeypot: Optional[bool] = None

    # 交易税 - None 表示未知
    buy_tax: Optional[float] = None
    sell_tax: Optional[float] = None

    # 持有者信息
    holder_count: int = 0
    lp_holder_count: int = 0
    is_in_dex: Optional[bool] = None

    # 综合评估
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    risk_score: int = 0  # 0-100, 越低越安全
    risk_items: Dict[str, Any] = field(default_factory=dict)  # 包含未知状态

    # 元数据
    last_check: float = 0.0
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'contract_address': self.contract_address,
            'chain': self.chain.value,
            'is_open_source': self.is_open_source,
            'is_mintable': self.is_mintable,
            'honeypot': self.honeypot,
            'buy_tax': self.buy_tax,
            'sell_tax': self.sell_tax,
            'risk_level': self.risk_level.value,
            'risk_score': self.risk_score,
            'last_check': self.last_check,
        }


@dataclass
class TokenSnapshot:
    """代币快照（用于追踪变化）"""
    contract_address: str
    symbol: str
    timestamp: float

    market_cap: float = 0.0
    holders: int = 0
    liquidity_usd: float = 0.0
    volume_24h: float = 0.0
    price: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'contract_address': self.contract_address,
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'market_cap': self.market_cap,
            'holders': self.holders,
            'liquidity_usd': self.liquidity_usd,
            'volume_24h': self.volume_24h,
            'price': self.price,
        }


@dataclass
class AlphaCandidate:
    """Alpha 候选币种（完整分析结果）"""
    token: TokenInfo
    security: Optional[SecurityInfo] = None

    # Alpha 评分
    alpha_score: float = 0.0  # 0-100

    # 变化追踪（24小时）- None 表示数据不足无法计算
    holders_change_24h: Optional[float] = None
    liquidity_change_24h: Optional[float] = None
    volume_change_24h: Optional[float] = None
    price_change_24h: Optional[float] = None

    # 计算指标
    volume_ratio: float = 0.0  # 成交量/市值比
    liquidity_ratio: float = 0.0  # 流动性/市值比

    # 信号标记
    signals: Dict[str, Any] = field(default_factory=dict)

    # 评分细节
    score_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'symbol': self.token.symbol,
            'name': self.token.name,
            'contract_address': self.token.contract_address,
            'chain': self.token.chain.value,
            'market_cap': self.token.market_cap,
            'holders': self.token.holders,
            'liquidity_usd': self.token.liquidity_usd,
            'volume_24h': self.token.volume_24h,
            'price': self.token.price,
            'alpha_score': self.alpha_score,
            'risk_level': self.security.risk_level.value if self.security else 'unknown',
            'risk_score': self.security.risk_score if self.security else 0,
            'holders_change_24h': self.holders_change_24h,
            'liquidity_change_24h': self.liquidity_change_24h,
            'volume_ratio': self.volume_ratio,
            'signals': self.signals,
            'score_breakdown': self.score_breakdown,
        }


# 导出
__all__ = [
    'Chain',
    'RiskLevel',
    'TokenInfo',
    'SecurityInfo',
    'TokenSnapshot',
    'AlphaCandidate',
]
