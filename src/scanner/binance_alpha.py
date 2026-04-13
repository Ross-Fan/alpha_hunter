"""
Binance Alpha 列表扫描器
从 Binance Alpha API 获取代币列表并进行初步筛选
"""

import time
from typing import List, Optional

import aiohttp

from ..config import config
from ..logger import get_logger, log_signal
from ..models import Chain, TokenInfo
from ..utils import RateLimiter, safe_float, safe_int
from .base import BaseScanner

logger = get_logger("scanner")


class BinanceAlphaScanner(BaseScanner):
    """
    Binance Alpha 列表扫描器

    通过 Binance 公开 API 获取 Alpha 代币列表
    """

    # Binance Alpha API 端点
    API_URL = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"

    def __init__(self):
        # 初始化时不指定链，因为 Alpha 列表包含多链代币
        super().__init__(Chain.BSC)

        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limiter = RateLimiter(
            rate=config.rate_limit.get('binance_alpha', 1),
            capacity=5
        )

        # 配置
        self._min_market_cap = config.min_market_cap
        self._max_market_cap = config.max_market_cap

        # 将配置中的链名转换为所有可能的链 ID
        self._supported_chain_ids = set()
        for chain_name in config.supported_chains:
            chain_ids = Chain.get_chain_ids(chain_name)
            self._supported_chain_ids.update(chain_ids)

    async def start(self) -> None:
        """启动扫描器"""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)

        self._running = True
        logger.info("Binance Alpha 扫描器已启动")
        logger.info(f"  支持的链 ID: {self._supported_chain_ids}")
        logger.info(f"  市值范围: ${self._min_market_cap/1e6:.1f}M - ${self._max_market_cap/1e6:.1f}M")

    async def stop(self) -> None:
        """停止扫描器"""
        self._running = False

        if self._session:
            await self._session.close()
            self._session = None

        logger.info("Binance Alpha 扫描器已停止")

    async def scan(self) -> List[TokenInfo]:
        """
        扫描 Binance Alpha 列表

        Returns:
            符合筛选条件的代币列表
        """
        if not self._session:
            await self.start()

        # 限流
        await self._rate_limiter.acquire()

        try:
            async with self._session.get(self.API_URL) as resp:
                if resp.status != 200:
                    logger.error(f"API 请求失败: HTTP {resp.status}")
                    return []

                data = await resp.json()

        except aiohttp.ClientError as e:
            logger.error(f"网络请求异常: {e}")
            return []
        except Exception as e:
            logger.error(f"扫描异常: {e}")
            return []

        # 解析响应
        if data.get('code') != '000000' or not data.get('success'):
            logger.warning(f"API 返回异常: {data.get('message', 'Unknown error')}")
            return []

        tokens_data = data.get('data', [])
        logger.info(f"API 返回 {len(tokens_data)} 个代币")

        # 筛选
        result = []
        filtered_stats = {
            'chain': 0,
            'market_cap_low': 0,
            'market_cap_high': 0,
            'passed': 0,
        }

        for t in tokens_data:
            # 链过滤
            chain_id = str(t.get('chainId', '')).lower()
            if chain_id not in self._supported_chain_ids:
                filtered_stats['chain'] += 1
                continue

            # 市值过滤
            market_cap = safe_float(t.get('marketCap', 0))
            if market_cap < self._min_market_cap:
                filtered_stats['market_cap_low'] += 1
                continue
            if market_cap > self._max_market_cap:
                filtered_stats['market_cap_high'] += 1
                continue

            # 创建 TokenInfo
            token = TokenInfo(
                symbol=t.get('symbol', ''),
                name=t.get('name', ''),
                contract_address=t.get('contractAddress', ''),
                chain=Chain.from_string(chain_id),
                token_id=str(t.get('tokenId', '')),
                price=safe_float(t.get('price', 0)),
                market_cap=market_cap,
                holders=safe_int(t.get('holders', 0)),
                alpha_points=safe_float(t.get('alphaPoints', 0)),
                last_update=time.time()
            )

            result.append(token)
            filtered_stats['passed'] += 1

            # 记录扫描日志
            log_signal(
                "SCAN",
                token.symbol,
                Chain=token.chain.value,
                MC=f"${market_cap/1e6:.2f}M",
                Holders=f"{token.holders:,}"
            )

        logger.info(
            f"筛选结果: 通过 {filtered_stats['passed']} | "
            f"链不匹配 {filtered_stats['chain']} | "
            f"市值过低 {filtered_stats['market_cap_low']} | "
            f"市值过高 {filtered_stats['market_cap_high']}"
        )

        return result

    async def get_token_detail(self, contract_address: str) -> Optional[TokenInfo]:
        """
        获取单个代币详情

        注意: Binance Alpha API 不支持单个查询，需要从完整列表中查找

        Args:
            contract_address: 代币合约地址

        Returns:
            代币信息
        """
        tokens = await self.scan()

        for token in tokens:
            if token.contract_address.lower() == contract_address.lower():
                return token

        return None

    async def get_all_tokens(self) -> List[TokenInfo]:
        """
        获取所有代币（不进行市值筛选）

        Returns:
            所有代币列表
        """
        if not self._session:
            await self.start()

        await self._rate_limiter.acquire()

        try:
            async with self._session.get(self.API_URL) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()

        except Exception as e:
            logger.error(f"获取全量代币异常: {e}")
            return []

        if data.get('code') != '000000':
            return []

        tokens_data = data.get('data', [])
        result = []

        for t in tokens_data:
            chain_id = str(t.get('chainId', '')).lower()

            # 只过滤链，不过滤市值
            if chain_id not in self._supported_chain_ids:
                continue

            token = TokenInfo(
                symbol=t.get('symbol', ''),
                name=t.get('name', ''),
                contract_address=t.get('contractAddress', ''),
                chain=Chain.from_string(chain_id),
                token_id=str(t.get('tokenId', '')),
                price=safe_float(t.get('price', 0)),
                market_cap=safe_float(t.get('marketCap', 0)),
                holders=safe_int(t.get('holders', 0)),
                alpha_points=safe_float(t.get('alphaPoints', 0)),
                last_update=time.time()
            )
            result.append(token)

        return result
