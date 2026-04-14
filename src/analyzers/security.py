"""
GoPlus 安全检查分析器
调用 GoPlus Security API 检查代币合约安全性
"""

import time
from typing import Optional, Any

import aiohttp

from ..config import config
from ..logger import get_logger, log_signal
from ..models import Chain, RiskLevel, SecurityInfo, TokenInfo
from ..utils import RateLimiter, safe_float
from .base import BaseAnalyzer

logger = get_logger("security")


def _parse_bool(value: str) -> Optional[bool]:
    """
    解析 GoPlus API 返回的布尔值

    GoPlus 返回 '1' 表示 True, '0' 表示 False, None/空 表示未知
    """
    if value is None or value == '':
        return None
    return value == '1'


def _parse_float(value) -> Optional[float]:
    """
    解析 GoPlus API 返回的浮点数

    None/空 表示未知
    """
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_int(value) -> int:
    """解析整数，失败返回 0"""
    if value is None or value == '':
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


class SecurityAnalyzer(BaseAnalyzer):
    """
    GoPlus 安全检查分析器

    通过 GoPlus Security API 检查代币合约的安全性
    """

    # GoPlus API 端点
    GOPLUS_API = "https://api.gopluslabs.io/api/v1/token_security"

    # 链 ID 映射
    CHAIN_MAP = {
        Chain.BSC: "56",
        Chain.BASE: "8453",
        # Solana 需要使用不同的 API 端点
    }

    def __init__(self):
        super().__init__()
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limiter = RateLimiter(
            rate=config.rate_limit.get('goplus', 1),
            capacity=5
        )

        # 配置
        self._security_config = config.security

    async def start(self) -> None:
        """启动分析器"""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)

        self._running = True
        logger.info("GoPlus 安全分析器已启动")

    async def stop(self) -> None:
        """停止分析器"""
        self._running = False

        if self._session:
            await self._session.close()
            self._session = None

        logger.info("GoPlus 安全分析器已停止")

    async def analyze(self, token: TokenInfo) -> SecurityInfo:
        """
        执行安全检查

        Args:
            token: 代币信息

        Returns:
            安全检查结果
        """
        if not self._session:
            await self.start()

        chain_id = self.CHAIN_MAP.get(token.chain)

        # 不支持的链返回未知状态
        if not chain_id:
            logger.warning(f"{token.symbol}: 不支持的链 {token.chain.value}")
            return SecurityInfo(
                contract_address=token.contract_address,
                chain=token.chain,
                risk_level=RiskLevel.UNKNOWN
            )

        # 限流
        await self._rate_limiter.acquire()

        url = f"{self.GOPLUS_API}/{chain_id}"
        params = {'contract_addresses': token.contract_address}

        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"{token.symbol}: GoPlus API 返回 {resp.status}")
                    return self._create_unknown_security(token)

                data = await resp.json()

        except aiohttp.ClientError as e:
            logger.error(f"{token.symbol}: GoPlus 请求异常 - {e}")
            return self._create_unknown_security(token)
        except Exception as e:
            logger.error(f"{token.symbol}: 安全检查异常 - {e}")
            return self._create_unknown_security(token)

        # 解析结果
        result = data.get('result', {}).get(token.contract_address.lower(), {})

        if not result:
            logger.warning(f"{token.symbol}: GoPlus 未返回数据")
            return self._create_unknown_security(token)

        # 构建 SecurityInfo - 使用辅助函数正确处理缺失数据
        security = SecurityInfo(
            contract_address=token.contract_address,
            chain=token.chain,
            # 基础安全项 - None 表示 API 未返回该数据
            is_open_source=_parse_bool(result.get('is_open_source')),
            is_proxy=_parse_bool(result.get('is_proxy')),
            is_mintable=_parse_bool(result.get('is_mintable')),
            can_take_back_ownership=_parse_bool(result.get('can_take_back_ownership')),
            owner_change_balance=_parse_bool(result.get('owner_change_balance')),
            hidden_owner=_parse_bool(result.get('hidden_owner')),
            selfdestruct=_parse_bool(result.get('selfdestruct')),
            external_call=_parse_bool(result.get('external_call')),
            honeypot=_parse_bool(result.get('is_honeypot')),
            # 交易税 - None 表示未知
            buy_tax=_parse_float(result.get('buy_tax')),
            sell_tax=_parse_float(result.get('sell_tax')),
            # 持有者
            holder_count=_parse_int(result.get('holder_count')),
            lp_holder_count=_parse_int(result.get('lp_holder_count')),
            is_in_dex=_parse_bool(result.get('is_in_dex')),
            # 元数据
            last_check=time.time(),
            raw_data=result
        )

        # 计算风险评分
        security.risk_score = self._calculate_risk_score(security)
        security.risk_level = self._determine_risk_level(security.risk_score)
        security.risk_items = self._get_risk_items(security)

        # 记录日志
        buy_tax_str = f"{security.buy_tax:.1%}" if security.buy_tax is not None else "N/A"
        sell_tax_str = f"{security.sell_tax:.1%}" if security.sell_tax is not None else "N/A"
        log_signal(
            "SECURITY",
            token.symbol,
            Risk=security.risk_level.value,
            Score=security.risk_score,
            BuyTax=buy_tax_str,
            SellTax=sell_tax_str
        )

        return security

    def _create_unknown_security(self, token: TokenInfo) -> SecurityInfo:
        """创建未知状态的安全信息"""
        return SecurityInfo(
            contract_address=token.contract_address,
            chain=token.chain,
            risk_level=RiskLevel.UNKNOWN,
            last_check=time.time()
        )

    def _calculate_risk_score(self, s: SecurityInfo) -> int:
        """
        计算风险评分

        0-100 分，越低越安全

        对于未知数据（None），采取保守策略：
        - 危险项未知：假设存在风险（加分但比确认存在少）
        - 安全项未知：假设不安全（加分）
        """
        score = 0

        # 严重风险项（每项 +30-50 分）
        # honeypot: True=危险, False=安全, None=未知(保守+25)
        if s.honeypot is True:
            score += 50
        elif s.honeypot is None:
            score += 25  # 未知，保守处理

        # is_mintable: True=危险, False=安全, None=未知
        if s.is_mintable is True:
            score += 30
        elif s.is_mintable is None:
            score += 15

        if s.can_take_back_ownership is True:
            score += 25
        elif s.can_take_back_ownership is None:
            score += 12

        if s.owner_change_balance is True:
            score += 25
        elif s.owner_change_balance is None:
            score += 12

        # 中等风险项（每项 +15-20 分）
        # is_open_source: True=安全, False=危险, None=未知
        if s.is_open_source is False:
            score += 20
        elif s.is_open_source is None:
            score += 10  # 未知，保守处理

        if s.hidden_owner is True:
            score += 15
        elif s.hidden_owner is None:
            score += 8

        if s.selfdestruct is True:
            score += 20
        elif s.selfdestruct is None:
            score += 10

        if s.external_call is True:
            score += 10
        elif s.external_call is None:
            score += 5

        # 交易税（超过阈值加分）
        max_buy_tax = self._security_config.get('max_buy_tax', 0.10)
        max_sell_tax = self._security_config.get('max_sell_tax', 0.10)

        # buy_tax: None=未知，保守假设有一定税
        if s.buy_tax is not None:
            if s.buy_tax > max_buy_tax:
                score += 15
            if s.buy_tax > 0.20:
                score += 10  # 高税率额外惩罚
        else:
            score += 8  # 未知税率，保守处理

        if s.sell_tax is not None:
            if s.sell_tax > max_sell_tax:
                score += 15
            if s.sell_tax > 0.20:
                score += 10
        else:
            score += 8

        return min(score, 100)

    def _determine_risk_level(self, score: int) -> RiskLevel:
        """根据评分确定风险等级"""
        if score <= 20:
            return RiskLevel.LOW
        elif score <= 50:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.HIGH

    def _get_risk_items(self, s: SecurityInfo) -> dict:
        """
        获取具体的风险项

        返回值说明：
        - True: 确认存在风险
        - False: 确认安全
        - 'unknown': 数据未知，保守处理
        """
        def _risk_status(value: Optional[bool], is_danger_when_true: bool = True) -> Any:
            """将 Optional[bool] 转换为风险状态"""
            if value is None:
                return 'unknown'
            return value if is_danger_when_true else not value

        return {
            'honeypot': _risk_status(s.honeypot),
            'mintable': _risk_status(s.is_mintable),
            'not_open_source': _risk_status(s.is_open_source, is_danger_when_true=False),
            'hidden_owner': _risk_status(s.hidden_owner),
            'can_take_back_ownership': _risk_status(s.can_take_back_ownership),
            'owner_change_balance': _risk_status(s.owner_change_balance),
            'selfdestruct': _risk_status(s.selfdestruct),
            'high_buy_tax': s.buy_tax > 0.10 if s.buy_tax is not None else 'unknown',
            'high_sell_tax': s.sell_tax > 0.10 if s.sell_tax is not None else 'unknown',
        }
