"""
工具函数模块
提供限流器、数据格式化等通用功能
"""

import asyncio
import time
from typing import Optional


class RateLimiter:
    """
    令牌桶限流器
    用于控制 API 请求频率
    """

    def __init__(self, rate: float, capacity: Optional[float] = None):
        """
        Args:
            rate: 每秒生成的令牌数
            capacity: 桶容量，默认等于 rate
        """
        self.rate = rate
        self.capacity = capacity or rate
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """
        获取令牌，如果令牌不足则等待

        Args:
            tokens: 需要的令牌数
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # 计算需要等待的时间
                wait_time = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait_time)

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """
        尝试获取令牌，不等待

        Args:
            tokens: 需要的令牌数

        Returns:
            是否成功获取
        """
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


def format_market_cap(value: float) -> str:
    """格式化市值显示"""
    if value >= 1_000_000_000:
        return f"${value / 1e9:.2f}B"
    elif value >= 1_000_000:
        return f"${value / 1e6:.2f}M"
    elif value >= 1_000:
        return f"${value / 1e3:.2f}K"
    else:
        return f"${value:.2f}"


def format_percent(value: float) -> str:
    """格式化百分比显示"""
    return f"{value:+.2%}"


def format_number(value: int) -> str:
    """格式化数字显示（带千分位）"""
    return f"{value:,}"


def safe_float(value, default: float = 0.0) -> float:
    """安全转换为浮点数"""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default: int = 0) -> int:
    """安全转换为整数"""
    try:
        if value is None:
            return default
        return int(float(value))
    except (ValueError, TypeError):
        return default


# 导出
__all__ = [
    'RateLimiter',
    'format_market_cap',
    'format_percent',
    'format_number',
    'safe_float',
    'safe_int',
]
