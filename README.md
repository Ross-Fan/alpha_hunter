# Alpha Hunter

Binance Alpha 潜力币种监控系统，识别处于"吸筹期"的早期 Alpha 币种。

## 功能特性

- **Binance Alpha 扫描**：自动获取 Binance Alpha 代币列表
- **市值筛选**：过滤 $1M - $30M 市值范围的币种
- **安全检查**：通过 GoPlus API 进行合约安全分析
- **流动性分析**：通过 GeckoTerminal 获取流动性和交易量数据
- **变化追踪**：记录历史快照，计算持币人数、流动性等指标的变化率
- **Alpha 评分**：综合评估币种潜力

## 项目结构

```
alpha_hunter/
├── config/
│   └── config.yaml          # 配置文件
├── src/
│   ├── config.py            # 配置加载器
│   ├── logger.py            # 日志系统
│   ├── models.py            # 数据模型
│   ├── utils.py             # 工具函数
│   ├── storage.py           # SQLite 存储
│   ├── scanner/
│   │   ├── base.py          # 扫描器基类
│   │   └── binance_alpha.py # Binance Alpha 扫描器
│   └── analyzers/
│       ├── base.py          # 分析器基类
│       ├── security.py      # GoPlus 安全检查
│       └── liquidity.py     # GeckoTerminal 流动性分析
├── data/                    # 数据目录（自动生成）
├── logs/                    # 日志目录（自动生成）
├── main.py                  # 主程序入口
└── requirements.txt         # 依赖
```

## 安装

```bash
cd alpha_hunter
pip install -r requirements.txt
```

## 配置

编辑 `config/config.yaml`：

```yaml
scanner:
  chains:
    - "bsc"           # 支持的链
  min_market_cap: 1000000      # 最小市值 $1M
  max_market_cap: 30000000     # 最大市值 $30M
  min_liquidity: 100000        # 最小流动性 $100K

runtime:
  scan_interval: 3600          # 扫描间隔（秒）
  output_top_n: 20             # 输出 Top N
```

## 运行

```bash
python main.py
```

## 数据源

| API | 用途 | 限制 |
|-----|------|------|
| Binance Alpha | 代币列表、市值、持币人数 | 公开 API，无需认证 |
| GoPlus | 合约安全检查 | 免费，1 req/s |
| GeckoTerminal | 流动性、交易量 | 免费，~10 req/min |

## Alpha Score 评分逻辑

| 因素 | 权重 | 说明 |
|------|------|------|
| 安全等级 | 20 | 低风险 +20，中风险 +10 |
| 持币人数变化 | 15 | 0-20% 增长为健康 |
| 流动性变化 | 10 | 0-30% 增长加分 |
| 成交量/市值比 | 10 | 5%-30% 为活跃 |
| 市值区间 | 10 | <$10M +10，<$20M +5 |

## 输出

扫描结果保存到 `data/candidates.json`，格式：

```json
{
  "timestamp": 1234567890,
  "count": 20,
  "candidates": [
    {
      "symbol": "TOKEN",
      "chain": "bsc",
      "market_cap": 5000000,
      "holders": 1000,
      "alpha_score": 75.0,
      "risk_level": "low"
    }
  ]
}
```

## 扩展计划

- [ ] Phase 2: 支持 Base、Solana 链
- [ ] Phase 2: 持币者分析（集中度、资金流向）
- [ ] Phase 2: Telegram 报警通知

## License

MIT
