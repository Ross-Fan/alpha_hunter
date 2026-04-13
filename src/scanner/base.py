"""
扫描器抽象基类
定义扫描器的通用接口，便于多链扩展
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import Chain, TokenInfo


class BaseScanner(ABC):
    """
    扫描器抽象基类

    所有具体的扫描器（Binance Alpha, DEX 等）都应继承此类
    """

    def __init__(self, chain: Chain):
        """
        Args:
            chain: 目标区块链
        """
        self.chain = chain
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """启动扫描器（初始化连接等）"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止扫描器（清理资源）"""
        pass

    @abstractmethod
    async def scan(self) -> List[TokenInfo]:
        """
        扫描并返回代币列表

        Returns:
            符合条件的代币列表
        """
        pass

    @abstractmethod
    async def get_token_detail(self, contract_address: str) -> Optional[TokenInfo]:
        """
        获取单个代币的详细信息

        Args:
            contract_address: 代币合约地址

        Returns:
            代币信息，如果找不到则返回 None
        """
        pass

    @property
    def is_running(self) -> bool:
        """扫描器是否正在运行"""
        return self._running
