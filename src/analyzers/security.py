"""
GoPlus 安全检查分析器
调用 GoPlus Security API 检查代币合约安全性
"""

import time
from typing import Optional

import aiohttp

from ..config import config
from ..logger import get_logger, log_signal
from ..models import Chain, RiskLevel, SecurityInfo, TokenInfo
from ..utils import RateLimiter, safe_float
from .base import BaseAnalyzer

logger = get_logger("security")


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

        # 构建 SecurityInfo
        security = SecurityInfo(
            contract_address=token.contract_address,
            chain=token.chain,
            # 基础安全项
            is_open_source=result.get('is_open_source') == '1',
            is_proxy=result.get('is_proxy') == '1',
            is_mintable=result.get('is_mintable') == '1',
            can_take_back_ownership=result.get('can_take_back_ownership') == '1',
            owner_change_balance=result.get('owner_change_balance') == '1',
            hidden_owner=result.get('hidden_owner') == '1',
            selfdestruct=result.get('selfdestruct') == '1',
            external_call=result.get('external_call') == '1',
            honeypot=result.get('is_honeypot') == '1',
            # 交易税
            buy_tax=safe_float(result.get('buy_tax', 0)),
            sell_tax=safe_float(result.get('sell_tax', 0)),
            # 持有者
            holder_count=int(result.get('holder_count', 0) or 0),
            lp_holder_count=int(result.get('lp_holder_count', 0) or 0),
            is_in_dex=result.get('is_in_dex') == '1',
            # 元数据
            last_check=time.time(),
            raw_data=result
        )

        # 计算风险评分
        security.risk_score = self._calculate_risk_score(security)
        security.risk_level = self._determine_risk_level(security.risk_score)
        security.risk_items = self._get_risk_items(security)

        # 记录日志
        log_signal(
            "SECURITY",
            token.symbol,
            Risk=security.risk_level.value,
            Score=security.risk_score,
            BuyTax=f"{security.buy_tax:.1%}",
            SellTax=f"{security.sell_tax:.1%}"
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
        """
        score = 0

        # 严重风险项（每项 +30-50 分）
        if s.honeypot:
            score += 50
        if s.is_mintable:
            score += 30
        if s.can_take_back_ownership:
            score += 25
        if s.owner_change_balance:
            score += 25

        # 中等风险项（每项 +15-20 分）
        if not s.is_open_source:
            score += 20
        if s.hidden_owner:
            score += 15
        if s.selfdestruct:
            score += 20
        if s.external_call:
            score += 10

        # 交易税（超过阈值加分）
        max_buy_tax = self._security_config.get('max_buy_tax', 0.10)
        max_sell_tax = self._security_config.get('max_sell_tax', 0.10)

        if s.buy_tax > max_buy_tax:
            score += 15
        if s.sell_tax > max_sell_tax:
            score += 15

        # 高税率额外惩罚
        if s.buy_tax > 0.20 or s.sell_tax > 0.20:
            score += 20

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
        """获取具体的风险项"""
        return {
            'honeypot': s.honeypot,
            'mintable': s.is_mintable,
            'not_open_source': not s.is_open_source,
            'hidden_owner': s.hidden_owner,
            'can_take_back_ownership': s.can_take_back_ownership,
            'owner_change_balance': s.owner_change_balance,
            'selfdestruct': s.selfdestruct,
            'high_buy_tax': s.buy_tax > 0.10,
            'high_sell_tax': s.sell_tax > 0.10,
        }
