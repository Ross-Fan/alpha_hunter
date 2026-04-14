# Alpha Hunter

自动筛选有潜力早期 Alpha 币种的监控系统。

## 快速命令

```bash
# 运行
python main.py

# 安装依赖
pip install -r requirements.txt
```

## 项目架构

```
main.py                 # 主入口，AlphaHunter 类协调全流程
config/config.yaml      # 配置：市值范围、评分权重、API限流
src/
├── scanner/            # 扫描器
│   └── binance_alpha.py   # Binance Alpha API 获取代币列表
├── analyzers/          # 分析器
│   ├── security.py        # GoPlus API 安全检查(蜜罐/可铸造/买卖税)
│   └── liquidity.py       # GeckoTerminal API 流动性分析
├── storage.py          # SQLite 存储，快照追踪历史变化
├── models.py           # 数据模型(TokenInfo/SecurityInfo/AlphaCandidate)
├── config.py           # 配置加载器(单例模式)
├── logger.py           # loguru 日志系统
└── utils.py            # 工具函数、RateLimiter限流器
```

## 核心流程

1. Binance Alpha API → 获取代币列表 → 市值过滤($1M-$30M) → 过滤股票代币
2. GoPlus API → 安全检查 → 过滤 HIGH 风险
3. GeckoTerminal API → 流动性分析 → 过滤低流动性(<$100K)
4. 对比历史快照 → 计算变化率(持币人数/流动性)
5. Alpha Score 评分 → 排序输出 Top 20

## 过滤规则

- **股票锚定代币**: 自动排除 symbol 以 `on` 结尾的代币（如 ONDSon, COSTon, ASMLon）
  - 配置位置: `config/config.yaml` → `scanner.filters`
  - 原因: 这类代币价格跟随美股，不属于独立 Alpha

## Alpha Score 评分 (0-100分)

- 基础分: 50
- 安全等级: +0~20 (LOW风险满分)
- 持币人数变化24h: +0~15 (0-20%增长健康)
- 流动性变化24h: +0~10 (0-30%增长)
- 成交量/市值比: +0~10 (5%-30%活跃)
- 市值区间: +0~10 (<$10M满分)

## 数据库表

- `tokens`: 代币基础信息
- `snapshots`: 历史快照(用于计算变化率)
- `security`: 安全检查结果缓存

## 扩展点

- 新增链: 继承 `src/scanner/base.py` 的 `BaseScanner`
- 新增分析器: 继承 `src/analyzers/base.py` 的 `BaseAnalyzer`
- 评分权重: 修改 `config/config.yaml` 的 `scoring` 部分

## 技术栈

- Python 3.8+, asyncio, aiohttp
- SQLite (data/alpha_hunter.db)
- loguru 日志
- 令牌桶限流
