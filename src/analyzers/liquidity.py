"""
GeckoTerminal 流动性分析器
从 GeckoTerminal API 获取代币的流动性和交易数据
"""

import time
from typing import Any, Dict, Optional

import aiohttp

from ..config import config
from ..logger import get_logger, log_signal
from ..models import Chain, TokenInfo
from ..utils import RateLimiter, safe_float
from .base import BaseAnalyzer

logger = get_logger("liquidity")


class LiquidityAnalyzer(BaseAnalyzer):
    """
    GeckoTerminal 流动性分析器

    通过 GeckoTerminal API 获取代币的流动性、交易量等数据
    """

    # GeckoTerminal API 端点
    API_BASE = "https://api.geckoterminal.com/api/v2"

    # 网络 ID 映射
    NETWORK_MAP = {
        Chain.BSC: "bsc",
        Chain.BASE: "base",
        Chain.SOLANA: "solana",
    }

    def __init__(self):
        super().__init__()
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limiter = RateLimiter(
            rate=config.rate_limit.get('gecko_terminal', 0.15),  # ~10 calls/min
            capacity=3
        )

    async def start(self) -> None:
        """启动分析器"""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                'Accept': 'application/json',
            }
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)

        self._running = True
        logger.info("GeckoTerminal 流动性分析器已启动")

    async def stop(self) -> None:
        """停止分析器"""
        self._running = False

        if self._session:
            await self._session.close()
            self._session = None

        logger.info("GeckoTerminal 流动性分析器已停止")

    async def analyze(self, token: TokenInfo) -> Dict[str, Any]:
        """
        获取代币的流动性数据

        Args:
            token: 代币信息

        Returns:
            流动性数据字典
        """
        if not self._session:
            await self.start()

        network = self.NETWORK_MAP.get(token.chain)
        if not network:
            logger.warning(f"{token.symbol}: 不支持的网络 {token.chain.value}")
            return {}

        # 限流（GeckoTerminal 免费版限制较严）
        await self._rate_limiter.acquire()

        # 先尝试直接获取代币信息
        token_data = await self._get_token_info(network, token.contract_address, token.symbol)

        if token_data:
            return token_data

        # 如果直接获取失败，尝试搜索池子
        pool_data = await self._search_pools(network, token.contract_address, token.symbol)

        return pool_data

    async def _get_token_info(
        self,
        network: str,
        contract_address: str,
        symbol: str
    ) -> Dict[str, Any]:
        """获取代币信息"""
        url = f"{self.API_BASE}/networks/{network}/tokens/{contract_address}"

        try:
            async with self._session.get(url) as resp:
                if resp.status == 404:
                    # 代币未找到，不算错误
                    return {}
                if resp.status != 200:
                    logger.debug(f"{symbol}: GeckoTerminal 返回 {resp.status}")
                    return {}

                data = await resp.json()

        except aiohttp.ClientError as e:
            logger.debug(f"{symbol}: GeckoTerminal 请求异常 - {e}")
            return {}
        except Exception as e:
            logger.error(f"{symbol}: 流动性分析异常 - {e}")
            return {}

        # 解析数据
        attributes = data.get('data', {}).get('attributes', {})

        if not attributes:
            return {}

        result = {
            'name': attributes.get('name', ''),
            'symbol': attributes.get('symbol', ''),
            'price_usd': safe_float(attributes.get('price_usd')),
            'fdv_usd': safe_float(attributes.get('fdv_usd')),
            'total_reserve_in_usd': safe_float(attributes.get('total_reserve_in_usd')),
            'volume_24h': safe_float(
                attributes.get('volume_usd', {}).get('h24', 0)
                if isinstance(attributes.get('volume_usd'), dict) else 0
            ),
            'price_change_24h': safe_float(
                attributes.get('price_change_percentage', {}).get('h24', 0)
                if isinstance(attributes.get('price_change_percentage'), dict) else 0
            ),
        }

        # 记录日志
        log_signal(
            "LIQUIDITY",
            symbol,
            Reserve=f"${result['total_reserve_in_usd']/1e3:.1f}K" if result['total_reserve_in_usd'] > 0 else "N/A",
            Vol24h=f"${result['volume_24h']/1e3:.1f}K" if result['volume_24h'] > 0 else "N/A"
        )

        return result

    async def _search_pools(
        self,
        network: str,
        contract_address: str,
        symbol: str
    ) -> Dict[str, Any]:
        """搜索代币的交易池"""
        # 限流
        await self._rate_limiter.acquire()

        url = f"{self.API_BASE}/networks/{network}/tokens/{contract_address}/pools"
        params = {'page': 1}

        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return {}

                data = await resp.json()

        except Exception as e:
            logger.debug(f"{symbol}: 搜索池子异常 - {e}")
            return {}

        pools = data.get('data', [])

        if not pools:
            return {}

        # 取流动性最大的池子
        best_pool = None
        max_reserve = 0

        for pool in pools:
            attrs = pool.get('attributes', {})
            reserve = safe_float(attrs.get('reserve_in_usd', 0))
            if reserve > max_reserve:
                max_reserve = reserve
                best_pool = attrs

        if not best_pool:
            return {}

        result = {
            'price_usd': safe_float(best_pool.get('base_token_price_usd')),
            'total_reserve_in_usd': max_reserve,
            'volume_24h': safe_float(
                best_pool.get('volume_usd', {}).get('h24', 0)
                if isinstance(best_pool.get('volume_usd'), dict) else 0
            ),
            'price_change_24h': safe_float(
                best_pool.get('price_change_percentage', {}).get('h24', 0)
                if isinstance(best_pool.get('price_change_percentage'), dict) else 0
            ),
        }

        log_signal(
            "POOL",
            symbol,
            Reserve=f"${max_reserve/1e3:.1f}K",
            Vol24h=f"${result['volume_24h']/1e3:.1f}K" if result['volume_24h'] > 0 else "N/A"
        )

        return result
