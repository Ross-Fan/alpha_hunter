"""
SQLite 数据存储模块
负责存储代币信息、快照和安全检查结果
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

from .logger import get_logger
from .models import Chain, RiskLevel, SecurityInfo, TokenInfo, TokenSnapshot

logger = get_logger("storage")


class AlphaStorage:
    """
    SQLite 数据存储

    存储代币信息、历史快照和安全检查结果
    支持计算变化率等分析功能
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Args:
            db_path: 数据库文件路径，默认为 data/alpha_hunter.db
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / 'data' / 'alpha_hunter.db'

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript('''
                -- 代币信息表
                CREATE TABLE IF NOT EXISTS tokens (
                    contract_address TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    name TEXT,
                    chain TEXT NOT NULL,
                    token_id TEXT,
                    first_seen REAL NOT NULL,
                    last_update REAL NOT NULL
                );

                -- 代币快照表（用于追踪变化）
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_address TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    market_cap REAL DEFAULT 0,
                    holders INTEGER DEFAULT 0,
                    liquidity_usd REAL DEFAULT 0,
                    volume_24h REAL DEFAULT 0,
                    price REAL DEFAULT 0,
                    FOREIGN KEY (contract_address) REFERENCES tokens(contract_address)
                );

                -- 安全检查结果表
                CREATE TABLE IF NOT EXISTS security (
                    contract_address TEXT PRIMARY KEY,
                    chain TEXT NOT NULL,
                    is_open_source INTEGER DEFAULT 0,
                    is_mintable INTEGER DEFAULT 0,
                    honeypot INTEGER DEFAULT 0,
                    buy_tax REAL DEFAULT 0,
                    sell_tax REAL DEFAULT 0,
                    risk_score INTEGER DEFAULT 0,
                    risk_level TEXT DEFAULT 'unknown',
                    last_check REAL NOT NULL,
                    raw_data TEXT,
                    FOREIGN KEY (contract_address) REFERENCES tokens(contract_address)
                );

                -- 创建索引
                CREATE INDEX IF NOT EXISTS idx_snapshots_address
                    ON snapshots(contract_address);
                CREATE INDEX IF NOT EXISTS idx_snapshots_time
                    ON snapshots(timestamp);
                CREATE INDEX IF NOT EXISTS idx_snapshots_address_time
                    ON snapshots(contract_address, timestamp);
                CREATE INDEX IF NOT EXISTS idx_tokens_chain
                    ON tokens(chain);
            ''')

        logger.info(f"数据库已初始化: {self.db_path}")

    def save_token(self, token: TokenInfo) -> None:
        """
        保存或更新代币信息

        Args:
            token: 代币信息
        """
        now = time.time()

        with sqlite3.connect(self.db_path) as conn:
            # 检查是否已存在
            cursor = conn.execute(
                'SELECT first_seen FROM tokens WHERE contract_address = ?',
                (token.contract_address,)
            )
            row = cursor.fetchone()

            if row:
                # 更新
                conn.execute('''
                    UPDATE tokens SET
                        symbol = ?,
                        name = ?,
                        chain = ?,
                        token_id = ?,
                        last_update = ?
                    WHERE contract_address = ?
                ''', (
                    token.symbol,
                    token.name,
                    token.chain.value,
                    token.token_id,
                    now,
                    token.contract_address
                ))
            else:
                # 插入
                conn.execute('''
                    INSERT INTO tokens
                    (contract_address, symbol, name, chain, token_id, first_seen, last_update)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    token.contract_address,
                    token.symbol,
                    token.name,
                    token.chain.value,
                    token.token_id,
                    now,
                    now
                ))

    def save_snapshot(self, snapshot: TokenSnapshot) -> None:
        """
        保存代币快照

        Args:
            snapshot: 代币快照
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO snapshots
                (contract_address, symbol, timestamp, market_cap, holders,
                 liquidity_usd, volume_24h, price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                snapshot.contract_address,
                snapshot.symbol,
                snapshot.timestamp,
                snapshot.market_cap,
                snapshot.holders,
                snapshot.liquidity_usd,
                snapshot.volume_24h,
                snapshot.price
            ))

    def save_security(self, security: SecurityInfo) -> None:
        """
        保存安全检查结果

        Args:
            security: 安全检查结果
        """
        import json

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO security
                (contract_address, chain, is_open_source, is_mintable, honeypot,
                 buy_tax, sell_tax, risk_score, risk_level, last_check, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                security.contract_address,
                security.chain.value,
                1 if security.is_open_source else 0,
                1 if security.is_mintable else 0,
                1 if security.honeypot else 0,
                security.buy_tax,
                security.sell_tax,
                security.risk_score,
                security.risk_level.value,
                security.last_check,
                json.dumps(security.raw_data) if security.raw_data else None
            ))

    def get_token(self, contract_address: str) -> Optional[Dict]:
        """获取代币信息"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM tokens WHERE contract_address = ?',
                (contract_address,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_latest_snapshot(self, contract_address: str) -> Optional[TokenSnapshot]:
        """获取最新快照"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM snapshots
                WHERE contract_address = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (contract_address,))

            row = cursor.fetchone()
            if not row:
                return None

            return TokenSnapshot(
                contract_address=row['contract_address'],
                symbol=row['symbol'],
                timestamp=row['timestamp'],
                market_cap=row['market_cap'],
                holders=row['holders'],
                liquidity_usd=row['liquidity_usd'],
                volume_24h=row['volume_24h'],
                price=row['price']
            )

    def get_snapshots_range(
        self,
        contract_address: str,
        hours: int = 24
    ) -> List[TokenSnapshot]:
        """
        获取指定时间范围内的快照

        Args:
            contract_address: 合约地址
            hours: 回溯小时数

        Returns:
            快照列表（按时间升序）
        """
        cutoff = time.time() - (hours * 3600)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM snapshots
                WHERE contract_address = ? AND timestamp >= ?
                ORDER BY timestamp ASC
            ''', (contract_address, cutoff))

            snapshots = []
            for row in cursor.fetchall():
                snapshots.append(TokenSnapshot(
                    contract_address=row['contract_address'],
                    symbol=row['symbol'],
                    timestamp=row['timestamp'],
                    market_cap=row['market_cap'],
                    holders=row['holders'],
                    liquidity_usd=row['liquidity_usd'],
                    volume_24h=row['volume_24h'],
                    price=row['price']
                ))

            return snapshots

    def calculate_change(
        self,
        contract_address: str,
        field: str,
        hours: int = 24
    ) -> float:
        """
        计算指定时间范围内的变化率

        Args:
            contract_address: 合约地址
            field: 字段名（market_cap, holders, liquidity_usd, volume_24h, price）
            hours: 回溯小时数

        Returns:
            变化率（小数形式），如果数据不足返回 0
        """
        snapshots = self.get_snapshots_range(contract_address, hours)

        if len(snapshots) < 2:
            return 0.0

        old_snapshot = snapshots[0]
        new_snapshot = snapshots[-1]

        old_value = getattr(old_snapshot, field, 0)
        new_value = getattr(new_snapshot, field, 0)

        if old_value == 0:
            return 0.0

        return (new_value - old_value) / old_value

    def get_security(self, contract_address: str) -> Optional[SecurityInfo]:
        """获取安全检查结果"""
        import json

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM security WHERE contract_address = ?',
                (contract_address,)
            )

            row = cursor.fetchone()
            if not row:
                return None

            return SecurityInfo(
                contract_address=row['contract_address'],
                chain=Chain.from_string(row['chain']),
                is_open_source=bool(row['is_open_source']),
                is_mintable=bool(row['is_mintable']),
                honeypot=bool(row['honeypot']),
                buy_tax=row['buy_tax'],
                sell_tax=row['sell_tax'],
                risk_score=row['risk_score'],
                risk_level=RiskLevel(row['risk_level']),
                last_check=row['last_check'],
                raw_data=json.loads(row['raw_data']) if row['raw_data'] else {}
            )

    def cleanup_old_snapshots(self, days: int = 7) -> int:
        """
        清理旧快照数据

        Args:
            days: 保留天数

        Returns:
            删除的记录数
        """
        cutoff = time.time() - (days * 24 * 3600)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'DELETE FROM snapshots WHERE timestamp < ?',
                (cutoff,)
            )
            deleted = cursor.rowcount

        if deleted > 0:
            logger.info(f"清理了 {deleted} 条旧快照记录")

        return deleted

    def get_statistics(self) -> Dict:
        """获取数据库统计信息"""
        with sqlite3.connect(self.db_path) as conn:
            tokens_count = conn.execute(
                'SELECT COUNT(*) FROM tokens'
            ).fetchone()[0]

            snapshots_count = conn.execute(
                'SELECT COUNT(*) FROM snapshots'
            ).fetchone()[0]

            security_count = conn.execute(
                'SELECT COUNT(*) FROM security'
            ).fetchone()[0]

            return {
                'tokens': tokens_count,
                'snapshots': snapshots_count,
                'security_checks': security_count,
            }
