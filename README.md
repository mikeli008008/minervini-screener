# Minervini Screener 📈

基于 Mark Minervini 的 **SEPA 方法论**（Specific Entry Point Analysis）每日自动扫描美股，识别同时满足 **技术面突破形态** + **基本面 Leader Profile** 的顶级候选股票，通过邮件推送筛选结果。

> "We want to find stocks that are early in stage 2, with fundamentals that explain why the stock is going up."
> — *Mark Minervini, Trade Like a Stock Market Wizard*

---
https://mikeli008008.github.io/minervini-screener/

## 核心功能

### 四层筛选引擎

本系统实现了 Minervini 方法论的完整量化版本，每只股票经过四道独立的筛选层：

#### 第一层：技术趋势（8条模板）
Minervini 的 Stage 2 Trend Template 全部量化实现：

1. 价格 > MA150 & MA200
2. MA150 > MA200
3. MA200 向上（20日前 MA200 < 今日 MA200）
4. MA50 > MA150 & MA200
5. 价格 > MA50
6. 价格 ≥ 52周低点的130%
7. 价格距 52周高点 ≤ 25%
8. RS Rating ≥ 70

#### 第二层：VCP 形态（Volatility Contraction Pattern）
- 基于峰谷识别的算法自动检测连续收缩
- 验证收缩次数 ≥ 2、深度递减、最后一次 < 15%、成交量萎缩
- 输出精确的 **pivot price**（Minervini 定义的买入触发价）
- VCP 评分 0-100

#### 第三层：相对强度（RS Rating）
- IBD 式百分位排名（0-99）
- 基于股票 1 年涨幅相对扫描全集的分布位置

#### 第四层：基本面 Leader Profile
抓取每只股票的季度财务数据，评估 Minervini "Leader Profile" 五项硬性标准：

1. **EPS 同比增长 ≥ 25%**
2. **EPS 加速**（本季同比 > 上季同比）
3. **营收同比正增长**
4. **ROE ≥ 17%**
5. **净利润率扩张或 ≥ 15%**

基本面评分 0-50 + 字母等级 A/B/C/D/F

### 信号分层

| 信号 | 触发条件 | 含义 |
|---|---|---|
| **★★ Super Stock** | 真VCP + 8/8 + near pivot + Leader Profile | Minervini 大牛股四重共振 |
| **★ Perfect Setup** | 真VCP + 8/8 + near pivot | 技术面完美但基本面未必达标 |
| **🏆 Leader Profile** | 基本面 5 条达标 ≥ 4 | 基本面领头羊，等待技术确认 |
| **👁 Watchlist** | 历史曾出现过 Super 或 Perfect | 长期跟踪池 |

### 综合评分（0-220分）

```
技术面 (0-160):
  - 8条趋势模板 × 10 = 80分
  - RS评分 × 0.3 = 30分
  - 真VCP × 25 = 25分
  - ATR/Volume/近高/近pivot/全通过/perfect 加分 = 最高25分

基本面 (0-50):
  - 基本面评分 × 1.0

加成 (0-15):
  - Leader Profile +10
  - Super Stock +5 (四重共振奖励)
```

### 自动 Watchlist 沉淀

- 每次扫描自动把 Super Stock 和 Perfect Setup 加入 `watchlist.txt`
- 保留首次发现日期、历史最高信号、历史最高评分
- 支持**手动编辑**（加备注、删除）— 手动修改的 note 永远不会被覆盖
- 邮件每天显示 watchlist 所有股票的当前状态：
  - ● 维持（信号级别与历史峰值一致）
  - ↓ 降级（从 Super 降到 Perfect/Leader/Watching）
  - ↑ 升级（稀有，一般只在刚加入时发生）

### 每日推送

**邮件内容**（HTML 富文本）：
- 6列 Stats 仪表板：Universe / Super / Perfect / Leader / 8-Pass / Grade A+B
- 👁 Watchlist 专区（紫色，个人关注池状态追踪）
- ★★ Super Stock 专区（绿色高亮，最高优先级）
- ★ Perfect Setup 专区（黄色，技术面完美）
- 🏆 Leader Profile 专区（深绿，基本面领头羊）
- Top 20 by Minervini Score（含 Grade 列和所有 tag）
- True VCP + Breakout Watch 双列
- 板块分布统计

**交互式 HTML 报告**（GitHub Pages 托管）：
- 8列 Stats 栏
- 10 个 Filter 按钮（All / Super / Perfect / Leader / Watchlist / True VCP / 8-Pass / Grade A+B / Near Pivot / RS≥90）
- 按任意列排序
- 点击任意股票展开 **4 列详情页**：
  - Trend Template（8条勾叉 + MA数据）
  - VCP Analysis（收缩序列 + pivot 距离 + 成交量比）
  - **Fundamentals**（Grade大字 + EPS/Rev/ROE + Leader Check 5项勾叉）
  - Price Action（6个月图表 + ATR + RS）

---

## 架构

```
tickers.txt       → 627 只股票池（S&P 500 + 精选成长股 + 国际ADR）
    ↓
scanner.py        → 四层扫描引擎（技术 + VCP + RS + 基本面）
    ↓
fundamentals.py   → 基本面抓取和评分模块
vcp.py            → VCP 峰谷识别算法
watchlist.py      → Watchlist 自动沉淀和状态追踪
    ↓
reports/latest.json → 结构化扫描结果
    ↓
┌───────────────────┬──────────────────────┐
│ send_email.py     │ generate_report.py   │
│ HTML邮件推送      │ 交互式网页报告       │
└───────────────────┴──────────────────────┘
    ↓                       ↓
Gmail SMTP         docs/index.html → GitHub Pages
```

---

## 一次性部署（约 15 分钟）

### 第 1 步：Fork 或上传到你的 GitHub

1. 在 GitHub 创建一个新 repo（建议命名 `minervini-screener`，设为 **私有**）
2. 把本项目所有文件上传到这个 repo

### 第 2 步：准备 SMTP 邮箱

推荐用 **Gmail 应用专用密码**（最简单，免费）：

1. 登录 Gmail → 账户设置 → 安全性 → **2 步验证**（先启用）
2. 安全性 → **应用专用密码** → 新建 → 名称随便填
3. Google 会生成一个 16 位密码（例如 `abcd efgh ijkl mnop`）— **记下来**

### 第 3 步：在 GitHub 设置 Secrets

Repo → Settings → **Secrets and variables** → **Actions** → **New repository secret**

设置以下 secrets：

| Name | Value |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `你的邮箱@gmail.com` |
| `SMTP_PASS` | `你刚刚生成的16位应用密码`（去掉空格） |
| `EMAIL_TO` | `收件邮箱@xxx.com`（可以和 SMTP_USER 相同，也可多个用逗号分隔） |

**可选**（启用 GitHub Pages 后）：

| Name | Value |
|---|---|
| `REPORT_URL` | `https://你的用户名.github.io/minervini-screener/` |

### 第 4 步：启用 GitHub Actions 写入权限

Repo → Settings → **Actions** → **General** → 滚到底部

**Workflow permissions** 选择 **Read and write permissions** → Save

### 第 5 步：启用 GitHub Pages（可选但推荐）

Repo → Settings → **Pages**

- Source: **Deploy from a branch**
- Branch: **main**, Folder: **/docs**
- Save

几分钟后你会得到：`https://你的用户名.github.io/minervini-screener/`

### 第 6 步：手动触发第一次扫描

Actions → Daily Minervini Scan → **Run workflow**

等 20-30 分钟，第一封邮件会到你的收件箱。

---

## 日常使用

### 自动运行

GitHub Actions 设置为每周一到周五 **美东盘后自动运行**（UTC 21:30 和 22:30 各一次，提供冗余）。

### 编辑股票池

`tickers.txt` — 直接在 GitHub 网页编辑添加/删除股票：
- 每行一只股票代码
- `#` 开头为注释
- 大小写不敏感，自动去重

### 编辑 Watchlist

`watchlist.txt` — 第一次扫描后自动生成，你可以手动编辑：

```
TICKER | FIRST_SEEN | PEAK_SIGNAL | PEAK_SCORE | NOTE
TSLA | 2026-04-18 | Perfect | 102.8 | 叙事驱动:Robotaxi 等待基本面兑现
NVDA | 2026-04-18 | Super | 144.0 | AI leader 已兑现
```

- 加备注：在 NOTE 列写任何中英文（会显示在邮件里）
- 删除股票：直接删除那一行
- 手动添加股票：直接加一行（填什么信号都可以，扫描时会更新）

---

## 如何使用筛选结果交易

> **免责声明：本工具仅为研究辅助，不构成投资建议。所有交易决策和后果由使用者自行承担。**

### Minervini 的核心规则

1. **单笔风险 ≤ 总账户 1%**：入场前必须算好止损位，用仓位倒推股数
2. **硬止损执行**：触发就走，不讨价还价
3. **止损位**：pivot 下方 **7-8%**（新手用 5%）
4. **同时持仓 ≤ 5 只**：不过度分散
5. **熊市清仓**：SPY 跌破 MA200 → 减半仓位；跌破 MA50 且放量 → 清仓观望
6. **从不逆势加仓**（never average down）

### 信号优先级

```
★★ Super Stock  →  最高优先级, 可做核心仓位
★ Perfect Setup →  第二优先级, 但必须检查 Grade，D/F 慎入
🏆 Leader       →  加入 Watchlist，等技术面触发
👁 Watchlist    →  每天观察状态变化
```

### 建议的三阶段学习路径

1. **第 1-2 周**：只看邮件，不下单，做交易日志（每天选 2-3 只 Perfect/Super，记录假设入场价/止损/预期目标）
2. **第 3-6 周**：Paper Trading（TradingView/Webull/ThinkOrSwim 的模拟账户）
3. **第 7 周+**：真金白银，但用小仓位（0.25% 单笔风险），每周复盘

---

## 方法论参考

- Mark Minervini, *Trade Like a Stock Market Wizard* (2013)
- Mark Minervini, *Think & Trade Like a Champion* (2017)
- William O'Neil, *How to Make Money in Stocks* (CANSLIM 方法，SEPA 的思想源头之一)
- Richard Wyckoff, *Wyckoff Method* (阶段分析的理论基础)

---

## 免责声明

**本工具不是投资建议。使用本工具进行的任何交易决策和结果由使用者自行承担。** 股票数据由 Yahoo Finance 提供。
