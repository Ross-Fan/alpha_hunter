"""
日志系统模块
基于 loguru 提供统一的日志记录功能
"""

import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .config import config

# 移除默认处理器
logger.remove()

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def setup_logger() -> None:
    """配置日志系统"""
    log_config = config.logging_config

    log_level = log_config.get('level', 'INFO')
    enable_console = log_config.get('console', True)
    enable_file = log_config.get('file', True)
    rotation = log_config.get('rotation', '10 MB')
    retention = log_config.get('retention', '7 days')

    # 控制台输出
    if enable_console:
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | {message}",
            level=log_level,
            colorize=True,
            filter=lambda record: record["extra"].get("name") != "signal"
        )

    # 文件输出
    if enable_file:
        log_dir = PROJECT_ROOT / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)

        # 主日志文件
        logger.add(
            log_dir / 'alpha_hunter.log',
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            level=log_level,
            rotation=rotation,
            retention=retention,
            encoding='utf-8'
        )

        # 信号日志（独立文件，便于分析）
        logger.add(
            log_dir / 'signals.log',
            format="{time:HH:mm:ss} | {message}",
            level="INFO",
            rotation=rotation,
            retention=retention,
            encoding='utf-8',
            filter=lambda record: record["extra"].get("name") == "signal"
        )

        # 错误日志（独立文件）
        logger.add(
            log_dir / 'errors.log',
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
            level="ERROR",
            rotation=rotation,
            retention=retention,
            encoding='utf-8'
        )


def get_logger(name: str = "alpha_hunter"):
    """
    获取带有名称绑定的 logger

    Args:
        name: 模块名称

    Returns:
        绑定了名称的 logger 实例
    """
    return logger.bind(name=name)


def log_signal(action: str, symbol: str, **kwargs) -> None:
    """
    记录信号日志

    Args:
        action: 动作类型 (SCAN, FILTER, ANALYZE, SCORE)
        symbol: 代币符号
        **kwargs: 额外的键值对
    """
    extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    msg = f"{action:8s} | {symbol:12s}"
    if extra_info:
        msg += f" | {extra_info}"

    logger.bind(name="signal").info(msg)


def log_candidate(rank: int, symbol: str, market_cap: float, holders: int,
                  alpha_score: float, risk_level: str, **kwargs) -> None:
    """
    记录候选币种日志

    Args:
        rank: 排名
        symbol: 代币符号
        market_cap: 市值
        holders: 持币人数
        alpha_score: Alpha 评分
        risk_level: 风险等级
    """
    mc_str = f"${market_cap / 1e6:.2f}M"
    msg = (
        f"#{rank:2d} | {symbol:12s} | MC: {mc_str:>10s} | "
        f"Holders: {holders:>8,} | Score: {alpha_score:5.1f} | Risk: {risk_level}"
    )

    extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    if extra_info:
        msg += f" | {extra_info}"

    logger.bind(name="signal").info(msg)


# 初始化日志系统
setup_logger()
