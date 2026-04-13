#!/usr/bin/env python3
"""
Alpha Hunter - Binance Alpha 潜力币种监控系统
主程序入口
"""

import asyncio
import json
import signal
import sys
import time
from pathlib import Path
from typing import List, Optional

from src.config import config
from src.logger import get_logger, log_candidate, setup_logger
from src.models import AlphaCandidate, RiskLevel, TokenSnapshot
from src.scanner.binance_alpha import BinanceAlphaScanner
from src.analyzers.security import SecurityAnalyzer
from src.analyzers.liquidity import LiquidityAnalyzer
from src.storage import AlphaStorage

logger = get_logger("main")


class AlphaHunter:
    """
    Alpha Hunter 主类

    负责协调扫描、分析和输出
    """

    def __init__(self):
        self._scanner = BinanceAlphaScanner()
        self._security_analyzer = SecurityAnalyzer()
        self._liquidity_analyzer = LiquidityAnalyzer()
        self._storage = AlphaStorage()

        self._running = False
        self._scan_interval = config.scan_interval
        self._output_top_n = config.runtime.get('output_top_n', 20)

        # 评分配置
        self._scoring_config = config.scoring

    async def start(self) -> None:
        """启动 Alpha Hunter"""
        logger.info("=" * 60)
        logger.info("Alpha Hunter - Binance Alpha 潜力币种监控系统")
        logger.info("=" * 60)

        # 显示配置
        self._log_config()

        # 启动各组件
        await self._scanner.start()
        await self._security_analyzer.start()
        await self._liquidity_analyzer.start()

        self._running = True

        # 首次扫描
        await self._run_scan_cycle()

        # 主循环
        while self._running:
            logger.info(f"下次扫描将在 {self._scan_interval // 60} 分钟后...")
            await asyncio.sleep(self._scan_interval)

            if self._running:
                await self._run_scan_cycle()

    async def stop(self) -> None:
        """停止 Alpha Hunter"""
        logger.info("正在停止 Alpha Hunter...")
        self._running = False

        await self._scanner.stop()
        await self._security_analyzer.stop()
        await self._liquidity_analyzer.stop()

        # 清理旧数据
        cleanup_days = config.get('storage.cleanup_days', 7)
        self._storage.cleanup_old_snapshots(cleanup_days)

        # 显示统计
        stats = self._storage.get_statistics()
        logger.info(f"数据库统计: {stats['tokens']} 代币, {stats['snapshots']} 快照")

        logger.info("Alpha Hunter 已停止")

    def _log_config(self) -> None:
        """输出配置信息"""
        logger.info(f"支持的链: {config.supported_chains}")
        logger.info(f"市值范围: ${config.min_market_cap/1e6:.1f}M - ${config.max_market_cap/1e6:.1f}M")
        logger.info(f"扫描间隔: {self._scan_interval // 60} 分钟")
        logger.info(f"输出 Top: {self._output_top_n}")

    async def _run_scan_cycle(self) -> None:
        """执行一次扫描周期"""
        start_time = time.time()
        logger.info("-" * 60)
        logger.info("开始扫描周期...")

        # 1. 扫描 Alpha 列表
        tokens = await self._scanner.scan()
        logger.info(f"扫描到 {len(tokens)} 个候选代币")

        if not tokens:
            logger.warning("未扫描到任何代币，跳过本次周期")
            return

        candidates: List[AlphaCandidate] = []
        skipped_security = 0
        skipped_liquidity = 0

        for i, token in enumerate(tokens):
            logger.debug(f"[{i+1}/{len(tokens)}] 分析 {token.symbol}...")

            # 2. 安全检查
            security = await self._security_analyzer.analyze(token)

            # 保存安全检查结果
            self._storage.save_security(security)

            # 跳过高风险代币
            if security.risk_level == RiskLevel.HIGH:
                logger.debug(f"{token.symbol}: 高风险，跳过")
                skipped_security += 1
                continue

            # 3. 流动性分析
            liquidity_data = await self._liquidity_analyzer.analyze(token)

            # 更新代币信息
            if liquidity_data:
                token.liquidity_usd = liquidity_data.get('total_reserve_in_usd', 0)
                token.volume_24h = liquidity_data.get('volume_24h', 0)
                token.price_change_24h = liquidity_data.get('price_change_24h', 0)

                # 检查流动性
                if token.liquidity_usd < config.min_liquidity:
                    logger.debug(f"{token.symbol}: 流动性不足，跳过")
                    skipped_liquidity += 1
                    continue

            # 4. 保存代币信息和快照
            self._storage.save_token(token)

            snapshot = TokenSnapshot(
                contract_address=token.contract_address,
                symbol=token.symbol,
                timestamp=time.time(),
                market_cap=token.market_cap,
                holders=token.holders,
                liquidity_usd=token.liquidity_usd,
                volume_24h=token.volume_24h,
                price=token.price
            )
            self._storage.save_snapshot(snapshot)

            # 5. 计算变化率
            holders_change = self._storage.calculate_change(
                token.contract_address, 'holders', hours=24
            )
            liquidity_change = self._storage.calculate_change(
                token.contract_address, 'liquidity_usd', hours=24
            )

            # 6. 创建候选对象
            candidate = AlphaCandidate(
                token=token,
                security=security,
                holders_change_24h=holders_change,
                liquidity_change_24h=liquidity_change,
                volume_ratio=token.volume_24h / token.market_cap if token.market_cap > 0 else 0
            )

            # 7. 计算 Alpha Score
            candidate.alpha_score, candidate.score_breakdown = self._calculate_alpha_score(candidate)

            candidates.append(candidate)

        # 8. 排序并输出
        candidates.sort(key=lambda x: x.alpha_score, reverse=True)

        elapsed = time.time() - start_time
        logger.info(
            f"分析完成: {len(candidates)} 有效 | "
            f"安全过滤 {skipped_security} | "
            f"流动性过滤 {skipped_liquidity} | "
            f"耗时 {elapsed:.1f}s"
        )

        self._output_results(candidates[:self._output_top_n])

    def _calculate_alpha_score(self, c: AlphaCandidate) -> tuple:
        """
        计算 Alpha 评分

        Returns:
            (总分, 分项明细)
        """
        score = 50.0  # 基础分
        breakdown = {'base': 50.0}

        cfg = self._scoring_config

        # 安全评分
        if c.security:
            if c.security.risk_level == RiskLevel.LOW:
                s = cfg.get('security_weight', 20)
                score += s
                breakdown['security_low'] = s
            elif c.security.risk_level == RiskLevel.MEDIUM:
                s = cfg.get('security_weight', 20) * 0.5
                score += s
                breakdown['security_medium'] = s

        # 持币人数变化
        h_min = cfg.get('holders_change_ideal_min', 0)
        h_max = cfg.get('holders_change_ideal_max', 0.2)
        h_weight = cfg.get('holders_change_weight', 15)

        if h_min <= c.holders_change_24h <= h_max:
            score += h_weight
            breakdown['holders_change'] = h_weight
        elif c.holders_change_24h > h_max:
            # 增长过快，可能已经热了
            penalty = min(h_weight, h_weight * (c.holders_change_24h - h_max) / h_max)
            score -= penalty
            breakdown['holders_change_penalty'] = -penalty

        # 流动性变化
        l_min = cfg.get('liquidity_change_ideal_min', 0)
        l_max = cfg.get('liquidity_change_ideal_max', 0.3)
        l_weight = cfg.get('liquidity_change_weight', 10)

        if l_min <= c.liquidity_change_24h <= l_max:
            score += l_weight
            breakdown['liquidity_change'] = l_weight

        # 成交量/市值比
        v_min = cfg.get('volume_ratio_ideal_min', 0.05)
        v_max = cfg.get('volume_ratio_ideal_max', 0.3)
        v_weight = cfg.get('volume_ratio_weight', 10)

        if v_min <= c.volume_ratio <= v_max:
            score += v_weight
            breakdown['volume_ratio'] = v_weight

        # 市值评分
        mc = c.token.market_cap
        mc_t1 = cfg.get('market_cap_tier1_max', 10_000_000)
        mc_t2 = cfg.get('market_cap_tier2_max', 20_000_000)
        mc_weight = cfg.get('market_cap_weight', 10)

        if mc < mc_t1:
            score += mc_weight
            breakdown['market_cap'] = mc_weight
        elif mc < mc_t2:
            s = mc_weight * 0.5
            score += s
            breakdown['market_cap'] = s

        return min(max(score, 0), 100), breakdown

    def _output_results(self, candidates: List[AlphaCandidate]) -> None:
        """输出结果"""
        if not candidates:
            logger.info("没有符合条件的候选币种")
            return

        logger.info("=" * 70)
        logger.info(f"Top {len(candidates)} Alpha 候选币种")
        logger.info("=" * 70)

        for i, c in enumerate(candidates, 1):
            # 控制台输出
            risk = c.security.risk_level.value if c.security else 'N/A'
            holders_chg = f"{c.holders_change_24h:+.1%}" if c.holders_change_24h else "N/A"

            logger.info(
                f"{i:2d}. {c.token.symbol:12s} | "
                f"MC: ${c.token.market_cap/1e6:>6.2f}M | "
                f"Holders: {c.token.holders:>7,} ({holders_chg:>7}) | "
                f"Score: {c.alpha_score:5.1f} | "
                f"Risk: {risk:6s}"
            )

            # 信号日志
            log_candidate(
                rank=i,
                symbol=c.token.symbol,
                market_cap=c.token.market_cap,
                holders=c.token.holders,
                alpha_score=c.alpha_score,
                risk_level=risk,
                HoldersChg=holders_chg
            )

        logger.info("=" * 70)

        # 保存到 JSON
        output_path = Path(__file__).parent / 'data' / 'candidates.json'
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_data = {
            'timestamp': time.time(),
            'count': len(candidates),
            'candidates': [c.to_dict() for c in candidates]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        logger.info(f"结果已保存到 {output_path}")


async def main():
    """主函数"""
    # 重新配置日志
    setup_logger()

    hunter = AlphaHunter()

    # 设置信号处理
    loop = asyncio.get_event_loop()

    def handle_signal():
        asyncio.create_task(hunter.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    try:
        await hunter.start()
    except KeyboardInterrupt:
        pass
    finally:
        await hunter.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(0)
