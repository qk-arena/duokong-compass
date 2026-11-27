# 多空罗盘

多空方向看板：数据为王，结果为王。每个数字可溯源（交易所、时间、算法），每个方向进只追加台账、用已结清战绩说话。一凡工作室出品。

- 标的：加密 10 个 BTC、ETH、SOL、BNB、XRP、DOGE、ADA、LINK、AVAX、LTC（USDT 现货）；美股 9 个 AAPL、AMZN、GOOGL、META、MSFT、NVDA、QQQ、SPY、TSLA 走币安币股（bStocks，如 NVDAB/USDT）——币股行情跟踪股价可能有小幅偏离，不冒充交易所股价；币股历史短，台账只开 4h/日线。
- 前端：以旧看板单文件版式为底本复刻（芯片墙、7 周期仪表、因子矩阵、风控面板、轮询 + WS 实时价），浏览器端直拉交易所公开接口现算。展示周期 5分–周线；正式信号与台账周期为 4小时 / 日线 / 周线 / 月线，只用已收盘 K 线；短周期（5分–1时）只展示方向，不进台账、未做回测。
- 因子：39 个（动量 21、趋势 18），全部经两套独立实现 + 两家数据源交叉核验（见 `FACTOR_AUDIT.md`）。每个因子只投方向票（多 / 空 / 中），不合成分数、不做 IC 加权；旧版的逻辑函数「做多概率」、衍生品快照因子、横截面动量已剔除。
- 呈现：动量与趋势分开。动量按 MACD 动量结构判定（金叉状态 / 柱放大向下 / 柱连续收敛的修复结构，定义在 `tools/engine.py` 并公开）；趋势按趋势因子投票判定。分歧时综合方向记中性（观察）。
- 百分比只有一种：同引擎历史回测命中率。芯片与仪表卡上的百分比来自 `tools/backtest.py` 用与线上完全相同的引擎在历史已收盘 K 线上逐根回放（结算 = 下一根收盘 vs 发出收盘），必须同时带样本量，样本 < 30 只显示「样本不足」。这是历史信号命中率，不是未来涨跌概率。台账的实盘命中率与回测命中率是两套统计，分开标注。
- 引擎双实现：Python 引擎（`tools/engine.py`，管台账与回测）与页面内 JS 引擎（管实时展示）口径逐行一致，本地实测 BTC 日线动量/趋势/综合三项完全对上。
- 联系：Telegram @onefanlab · onefanlab@gmail.com

## 台账（只追加）

`data/ledger.jsonl` 一行一条，只许追加，永不修改删除：
- signal 记录：标的、周期、方向（综合/动量/趋势）、记录时间（UTC + 北京时间双标）、发出价、所依据的已收盘 K 线时间、MACD 与均线数值、数据来源。
- settlement 记录：指向被结清的 signal 记录 ID，写明入场/出场价、期间涨跌幅、命中/未命中（中性记录记「观察结清」，不计命中率分母）。
结清规则：同一标的×周期出现新一根已收盘 K 线时，上一条进行中记录到期结清，再追加新记录。重复运行按 K 线时间去重，不会重复记账。

## 脚本

```bash
python3 tools/update.py    # 重算 current.json + 结清/追加台账，幂等，可重复运行
python3 tools/backtest.py  # 同引擎历史回测，产出 data/backtest.json（可复跑）
python3 tools/verify.py    # 第一轮独立核验（22 因子），结果写 VERIFY_RESULT.json
python3 tools/verify2.py   # 第二轮复活因子核验，结果写 VERIFY2_RESULT.json
```

定时：VM 侧 cron 每 4 小时跑一次 `tools/update.py`（覆盖 4h 收盘；日/周/月在新 K 线出现时自动结清追加）；仓库内另附 GitHub Actions 工作流（`.github/workflows/update.yml`，每 4 小时）作为同节奏备份，两边幂等去重。

## 文件

- `index.html` — 静态站单文件（复刻版式 + JS 引擎 + 台账/联系区）；`logo.svg` — 多空罗盘自有 logo
- `data/current.json` — 最新信号快照；`data/ledger.jsonl` / `data/ledger.json` — 台账；`data/backtest.json` — 回测结果；`data/backtest_btc_1d_signals.json` — BTC 日线回测逐条明细（供人工复核）
- `tools/engine.py` — 计算引擎；`tools/update.py` — 台账更新；`tools/backtest.py` — 回测；`tools/verify.py` / `tools/verify2.py` — 独立核验
- `FACTOR_AUDIT.md` — 因子核验清单（两轮）；`OLD_BOARD_ISSUES.md` — 旧看板数据问题总结
- `tools/proxy-connect.py` — git SSH 隧道辅助（部署用，本地文件不入库）

仅供信息展示与学习，不构成投资建议。
