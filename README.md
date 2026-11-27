# 多空罗盘

多空方向看板：数据为王，结果为王。每个数字可溯源（交易所、时间、算法），每个方向进只追加台账、用已结清战绩说话。

- 标的：BTC、ETH、SOL、BNB、XRP、DOGE、ADA、LINK（USDT 现货）。美股不在 v1 范围。
- 周期：4小时 / 日线 / 周线 / 月线，只用已收盘 K 线。短周期不进正式信号、不进台账。
- 呈现：动量与趋势分开。动量按 MACD 动量结构判定（金叉状态 / 柱放大向下 / 柱连续收敛的修复结构，定义在 `tools/engine.py` 并公开）；趋势按均线类趋势因子投票判定。分歧时综合方向记中性（观察）。
- 没有合成百分比：因子只展示票数和原始数值；命中率只统计台账里已结清的方向记录，并同时展示样本数。
- 数据源：主源 Gate.io 现货公开接口，兜底 Binance Vision；长历史段不足时由 Binance Vision 补全并在来源里标注。周线由日线按周一对齐重采样，月线按 UTC 自然月重采样，只取已结束的周/月。
- 联系：Telegram @onefanlab · onefanlab@gmail.com

## 台账（只追加）

`data/ledger.jsonl` 一行一条，只许追加，永不修改删除：
- signal 记录：标的、周期、方向（综合/动量/趋势）、记录时间（UTC + 北京时间双标）、发出价、所依据的已收盘 K 线时间、MACD 与均线数值、数据来源。
- settlement 记录：指向被结清的 signal 记录 ID，写明入场/出场价、期间涨跌幅（正绿负红）、命中/未命中（中性记录记「观察结清」，不计命中率分母）。
结清规则：同一标的×周期出现新一根已收盘 K 线时，上一条进行中记录到期结清，再追加新记录。重复运行按 K 线时间去重，不会重复记账。

## 更新脚本

```bash
python3 tools/update.py   # 重算 current.json + 结清/追加台账，幂等，可重复运行
python3 tools/verify.py   # 独立核验（第二数据源 + 独立代码重算），结果写 VERIFY_RESULT.json
```

定时：VM 侧 cron 每 4 小时跑一次 `tools/update.py`（覆盖 4h 收盘；日/周/月在新 K 线出现时自动结清追加）；仓库内另附 GitHub Actions 工作流（`.github/workflows/update.yml`，每 4 小时）作为同节奏备份，两边幂等去重。

## 文件

- `index.html` / `styles.css` / `app.js` / `logo.svg` — 静态站（纯黑底、白字、亮黄绿 accent；一排两个方块）
- `data/current.json` — 最新信号快照；`data/ledger.jsonl` / `data/ledger.json` — 台账
- `tools/engine.py` — 计算引擎；`tools/update.py` — 台账更新；`tools/verify.py` — 独立核验
- `FACTOR_AUDIT.md` — 因子核验清单；`OLD_BOARD_ISSUES.md` — 旧看板数据问题总结
- `tools/proxy-connect.py` — git SSH 隧道辅助（部署用）

仅供信息展示与学习，不构成投资建议。
