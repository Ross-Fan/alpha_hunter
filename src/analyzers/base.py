"""
分析器抽象基类
定义分析器的通用接口
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..models import TokenInfo


class BaseAnalyzer(ABC):
    """
    分析器抽象基类

    所有具体的分析器（安全检查、流动性分析等）都应继承此类
    """

    def __init__(self):
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """启动分析器（初始化连接等）"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止分析器（清理资源）"""
        pass

    @abstractmethod
    async def analyze(self, token: TokenInfo) -> Any:
        """
        分析代币

        Args:
            token: 代币信息

        Returns:
            分析结果（具体类型由子类定义）
        """
        pass

    @property
    def is_running(self) -> bool:
        """分析器是否正在运行"""
        return self._running
