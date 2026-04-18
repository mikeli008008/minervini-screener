# Minervini Screener 📈

基于 Mark Minervini 的 **SEPA 方法论** 每日扫描美股、发现符合 Stage 2 强势趋势的候选标的，并通过邮件推送筛选结果。
https://mikeli008008.github.io/minervini-screener/
---

## 功能特性

- **Minervini 8条趋势模板**：全部量化实现，自动判断是否符合 Stage 2 上升趋势
- **相对强度 RS Rating**：基于全部扫描股票的百分位排名（0-99）
- **真·VCP 检测**：基于峰谷识别算法，识别 2-4 次连续收缩的 Minervini 级 VCP 形态，输出精确 pivot price（买入触发点）
- **综合评分**（0-160分）：趋势模板 + RS + 真VCP + 接近pivot + perfect setup 加权
- **Perfect Setup 识别**：真VCP + 8/8通过 + 接近pivot 三重共振的最高优先级信号
- **HTML 邮件**：Perfect Setup 专区 + Top 20 + 突破候选 + VCP 列表 + 板块分布
- **完整交互式报告**：支持按 Perfect/True VCP/8-pass/Near Pivot/RS90 筛选，可展开查看完整 VCP 拆解
- **每日自动运行**：通过 GitHub Actions 免费定时

---

## 一次性部署（约 15 分钟）

### 第 1 步：Fork 或上传到你的 GitHub

1. 在 GitHub 创建一个新 repo（建议命名 `minervini-screener`，设为 **私有**）
2. 把本项目所有文件上传到这个 repo

### 第 2 步：准备 SMTP 邮箱

推荐用 **Gmail 应用专用密码**（最简单，免费）：

1. 打开 [Google 账户 → 安全性](https://myaccount.google.com/security)
2. 开启 **两步验证**（如果还没开）
3. 进入 [应用专用密码页面](https://myaccount.google.com/apppasswords)
4. 生成一个新密码（应用名随意填 `Minervini Screener`）
5. 复制生成的 16 位密码（格式如 `abcd efgh ijkl mnop`，**去掉空格**使用）

> 不想用 Gmail？支持任何 SMTP：Outlook（smtp.office365.com:587）、QQ 邮箱（smtp.qq.com:587）、自建等。

### 第 3 步：在 GitHub 配置 Secrets

进入你的 repo → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

按顺序添加以下 secrets：

| Secret 名称 | 说明 | 示例 |
|---|---|---|
| `SMTP_USER` | 发件邮箱 | `you@gmail.com` |
| `SMTP_PASS` | 应用专用密码（16位） | `abcdefghijklmnop` |
| `EMAIL_TO` | 收件邮箱（多个用逗号分隔） | `you@gmail.com,backup@gmail.com` |
| `SMTP_HOST` | SMTP 服务器（Gmail 可不填） | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 端口（默认 587，可不填） | `587` |
| `EMAIL_FROM` | 发件人显示（可不填，默认同 SMTP_USER） | `Minervini Bot <you@gmail.com>` |
| `REPORT_URL` | 完整报告链接（可选，开启 Pages 后填） | `https://USER.github.io/minervini-screener/` |

**最少必填的是前 3 个**：`SMTP_USER`、`SMTP_PASS`、`EMAIL_TO`。

### 第 4 步：开启 GitHub Actions

1. 进入 repo → `Actions` 标签页
2. 如果提示启用 workflows，点击启用
3. 点击左侧 `Daily Minervini Scan` → 右上角 `Run workflow` → 选 `main` 分支 → `Run workflow`
4. 等待约 5-10 分钟完成扫描
5. 如果配置正确，你会收到第一封邮件 📬

### 第 5 步（可选）：开启 GitHub Pages 查看完整报告

1. 进入 repo → `Settings` → `Pages`
2. Source 选 `Deploy from a branch`
3. Branch 选 `main`，目录选 `/docs`
4. 保存后等待 1-2 分钟，就能通过 `https://你的用户名.github.io/minervini-screener/` 访问完整的交互式报告
5. 把这个 URL 填回 Secret `REPORT_URL`，之后邮件里会带有跳转链接

---

## 自动运行时间

默认配置为 **美东盘后** 跑两次（避开夏令时/冬令时切换）：

- UTC 21:30（美东冬令时 16:30 / 夏令时 17:30）
- UTC 22:30（美东冬令时 17:30 / 夏令时 18:30）

**注意**：GitHub Actions 的定时触发会被延迟几分钟到几十分钟（免费版共享资源，不保证准时）。如果要求高准时可以改用 AWS EventBridge 或服务器 cron。

修改运行时间：编辑 `.github/workflows/daily_scan.yml` 里的 `cron` 字段。[Cron 语法参考](https://crontab.guru/)

---

## 自定义股票池

编辑 `tickers.txt` 文件：
- 每行一个美股 ticker
- `#` 开头是注释
- 默认约 350-400 只，覆盖主流成长股 + S&P 500 主要成分 + 热门中小盘

想扫全市场？去下载最新的 S&P 500、Nasdaq 100、Russell 2000 成分列表塞进去即可。扫描耗时大约每 100 只股票 30 秒左右（10 线程并发），跑 2000 只大约 8-10 分钟。

---

## 本地测试

如果想在本地先试跑：

```bash
# 安装依赖
pip install -r requirements.txt

# 运行扫描（约 5 分钟）
python scanner.py

# 生成 HTML 报告
python generate_report.py

# 预览邮件（不发送，只生成 reports/email_preview.html）
python send_email.py

# 真实发送邮件（需先设置环境变量）
export SMTP_USER="you@gmail.com"
export SMTP_PASS="应用专用密码"
export EMAIL_TO="you@gmail.com"
python send_email.py
```

---

## 文件结构

```
minervini-screener/
├── scanner.py              # 核心扫描引擎
├── vcp.py                  # VCP峰谷识别算法
├── send_email.py           # 邮件生成与发送
├── generate_report.py      # 完整 HTML 报告生成
├── tickers.txt             # 股票池（默认 570 只：S&P 500 + 精选成长股）
├── requirements.txt        # Python 依赖
├── .github/workflows/
│   └── daily_scan.yml     # GitHub Actions 配置
├── reports/               # 每日扫描数据（自动生成）
│   ├── latest.json
│   ├── data_YYYY-MM-DD.json
│   └── email_preview.html
└── docs/                  # 完整 HTML 报告（GitHub Pages）
    ├── index.html         # 最新报告
    └── report_YYYY-MM-DD.html
```

---

## Minervini 8 条趋势模板

只有同时满足以下全部条件的股票才被判定为 "Stage 2 qualifier"：

1. 当前股价 **>** MA150 和 MA200
2. MA150 **>** MA200
3. MA200 正在向上（至少近一个月）
4. MA50 **>** MA150 和 MA200
5. 当前股价 **>** MA50
6. 股价 **≥** 52 周低点的 **130%**
7. 股价 **≥** 52 周高点的 **75%**（即距离高点 ≤ 25%）
8. RS Rating **≥** 70（相对强度百分位排名）

---

## 综合评分逻辑（0-160）

| 项目 | 分值 |
|---|---|
| 通过的趋势模板条数 | ×10 = 最高 80 分 |
| RS Rating 加权 | ×0.3 = 最高 30 分 |
| 真 VCP 评分 | ×0.25 = 最高 25 分 ★主要setup加分 |
| ATR 收缩（辅助指标） | +3 分 |
| 成交量萎缩 | +3 分 |
| 距 52 周高点 ≤15% | +5 分 |
| 接近 VCP pivot ≤5% | +4 分 |
| 8 条全部通过奖励 | +5 分 |
| Perfect Setup 奖励（真VCP + 8/8 + near pivot） | +5 分 |

**阅读评分的经验法则**：
- **130+ 分**：高概率 Perfect Setup，最优先关注
- **110-130 分**：强势股，多数符合 Stage 2 + 有形态支撑
- **90-110 分**：合格趋势，但可能缺乏即时 entry signal
- **< 90 分**：有瑕疵，不建议追涨

## 真·VCP 识别标准

VCP (Volatility Contraction Pattern) 必须同时满足：

1. **至少 2 次连续回调**（越多越好，3-4 次最理想）
2. **回调深度递减**（tightening）——每次回调比上次浅
3. **最后一次回调 < 15%**（紧凑整理，为突破蓄力）
4. **整理期成交量萎缩**（后半段平均成交量 < 前半段的 85%）
5. **当前价接近 pivot point**（最后一次回调的起点）

VCP 得分 ≥ 50 且满足前述底线条件，判定为 **真 VCP**。

**Perfect Setup** = 真 VCP + 8/8 趋势模板 + 接近 pivot 三重共振，是最高优先级信号。

---

## 常见问题

**Q: 邮件收不到？**
- 检查垃圾邮件
- 去 Actions 标签页看 workflow 是否成功运行
- 点进 failed 的 workflow 看具体错误（通常是 SMTP 密码错误或邮箱配置问题）

**Q: 怎么调整扫描时间？**
- 编辑 `.github/workflows/daily_scan.yml` 里的 `cron`
- 用 [crontab.guru](https://crontab.guru/) 帮你生成正确的表达式
- 注意 GitHub Actions 使用 **UTC 时间**

**Q: 想扫 A 股？**
- yfinance 支持部分 A 股（后缀 `.SS` / `.SZ`），但数据质量一般
- 推荐换用 `akshare` 库重写 scanner 的数据抓取部分
- 筛选逻辑完全通用，只需换数据源

**Q: GitHub Actions 会花钱吗？**
- 公开 repo：完全免费
- 私有 repo：每月 2000 分钟免费额度，每次扫描约 8-12 分钟（570只股票），一个月消耗约 250-400 分钟，**绰绰有余**

**Q: 为什么有些股票拉不到数据？**
- Yahoo Finance 偶尔会 rate limit（特别是跑到 500+ 只股票的后面）
- 这通常是暂时的，下次扫描会正常
- 如果发现特定股票长期拉不到，可以在 tickers.txt 中删除它

---

## 免责声明

本工具仅供研究和学习使用，**不构成任何投资建议**。股市有风险，投资需谨慎。Minervini 本人也承认他的方法在熊市环境下表现会显著下降——熊市里最好的策略是空仓等待，而不是频繁交易。

策略参考：Mark Minervini - *Trade Like a Stock Market Wizard*, *Think & Trade Like a Champion*
