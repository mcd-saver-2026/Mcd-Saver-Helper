# 麦麦省钱助手 (MaiMai Saver)

输入「预算 + 想吃的」，自动匹配预算内的麦当劳优惠券，给出最划算的单品推荐和不多花钱的组合推荐。

```
==================================================================
 麦麦省钱助手 · 预算 ¥20.00 · 想吃：汉堡
 数据来源：内置示例券库
==================================================================

【推荐一】单品优选（最划算的几张券）
#  券名              商品        原价    到手价  省       命中口味  渠道
-  ----------------  ----------  ------  ------  -------  --------  ---------
1  板烧鸡腿堡单品券  板烧鸡腿堡  ¥22.50  ¥15.90  省¥6.60  汉堡      麦当劳App
2  麦辣鸡腿堡单品券  麦辣鸡腿堡  ¥21.00  ¥14.90  省¥6.10  汉堡      麦当劳App
3  巨无霸优惠券      巨无霸      ¥25.00  ¥19.90  省¥5.10  汉堡      麦当劳App

【推荐二】超值组合（一次吃完预算，性价比最高）
#  组合内容               合计    共省     预算利用
-  ---------------------  ------  -------  --------
1  吉士汉堡 + 麦香鱼      ¥19.40  省¥7.10  97%
2  吉士汉堡 + 麦香鸡      ¥18.80  省¥7.20  94%
3  双层吉士汉堡 + 中薯条  ¥19.40  省¥9.60  97%
```

---

## 一、项目介绍

**解决什么问题**：麦当劳的优惠券散落在 App、小程序、不同活动里，每次点单都要在一堆券里翻来翻去，还容易为了用券而买了不该买的东西。本项目把这件事收敛成一次查询——**告诉它预算和想吃的，它告诉你这笔钱怎么花最值**。

**核心特性**

| 特性 | 说明 |
|------|------|
| 预算硬约束 | 所有推荐（含组合）的总价都严格 ≤ 预算，绝不超支 |
| 口味理解 | 支持「汉堡,可乐」这类多口味输入，并做同义词扩展——说「炸鸡」也能命中麦乐鸡、辣翅 |
| 双重推荐 | 既给「单品优选」（省得最多的一张券），也给「超值组合」（把预算用满但不浪费） |
| 防买重 | 自动排除「套餐再叠一份薯条」「一个汉堡配两杯可乐」这类冗余搭配 |
| 数据可插拔 | MCP 服务、本地 JSON、内置数据三级降级，任何一层失败都不会导致无结果 |
| 零依赖 | 只用 Python 标准库，不需要 pip 安装任何东西 |

**工作原理（三级数据降级）**

```
        ┌─────────────────────────────┐
        │ 1. 麦当劳 MCP 服务（优先）   │  配置 MCD_MCP_URL / MCD_MCP_COMMAND 时启用
        └──────────────┬──────────────┘
                       │ 未配置 / 连接失败 / 返回空
                       ▼
        ┌─────────────────────────────┐
        │ 2. 本地券库 JSON             │  由 --coupons-file 指定
        └──────────────┬──────────────┘
                       │ 未指定 / 读取失败
                       ▼
        ┌─────────────────────────────┐
        │ 3. 内置示例券库（兜底）       │  开箱即用
        └─────────────────────────────┘
                       │
                       ▼
             筛选 → 打分 → 单品推荐 + 组合推荐
```

**推荐结果怎么来的**：先剔除过期券和超预算券，再按「口味覆盖率 × 100 + 省钱比例 × 45 + 预算利用率 × 15」打分排序；组合推荐在此基础上穷举 2–3 张券的搭配，并通过合理性校验。详见下文「推荐算法」。

---

## 二、环境要求

| 项目 | 要求 |
|------|------|
| Python | 3.8 及以上（开发与测试环境为 3.13） |
| 第三方依赖 | **无**，仅使用标准库 |
| 操作系统 | Windows / macOS / Linux 均可 |
| 网络 | 走内置或本地券库时**不需要联网**；仅接入远程 MCP 时才有网络要求 |

确认 Python 版本：

```bash
python --version      # Windows
python3 --version     # macOS / Linux
```

若提示找不到命令，请先安装 Python 3.8+ 并确保已加入 PATH。

---

## 三、安装与运行

### 1. 获取项目

本项目已位于：

```
C:\Users\John\Desktop\MCD-Project
```

无需 clone、无需 `pip install`，目录拷走即可用。

### 2. 运行

进入项目根目录后执行：

```bash
# Windows
cd C:\Users\John\Desktop\MCD-Project
python mai_mai_saver.py --budget 20 --craving 汉堡

# macOS / Linux
cd /path/to/MCD-Project
python3 mai_mai_saver.py --budget 20 --craving 汉堡
```

更多用法：

```bash
python mai_mai_saver.py --budget 35 --craving "汉堡,可乐"   # 多口味
python mai_mai_saver.py --list                             # 看看券库里有哪些券
python mai_mai_saver.py --budget 20 --craving 汉堡 --json   # JSON 输出，便于程序处理
```

> **Windows 终端中文乱码？** 脚本已内置强制 UTF-8 输出，一般不会乱码。若仍异常，先执行 `chcp 65001` 切换到 UTF-8 代码页。

### 3. 交互模式

不传 `--budget` 即进入交互模式，按提示逐步输入，适合手动试：

```bash
python mai_mai_saver.py
```

```
==================================================================
 麦麦省钱助手 · 交互模式（直接回车退出）
==================================================================

预算（元）> 20
想吃什么（如：汉堡 / 汉堡,可乐）> 汉堡
...输出推荐结果...
预算（元）>          ← 直接回车退出
```

### 4. 安装为 WorkBuddy 技能（可选）

把整个目录放到用户级技能目录下即可，文件夹名需与 `SKILL.md` 中的 `name` 一致（`mai-mai-saver`）：

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.workbuddy\skills\mai-mai-saver"
Copy-Item -Recurse -Force "C:\Users\John\Desktop\MCD-Project\*" "$env:USERPROFILE\.workbuddy\skills\mai-mai-saver\"
```

```bash
# macOS / Linux
mkdir -p ~/.workbuddy/skills/mai-mai-saver
cp -R /path/to/MCD-Project/* ~/.workbuddy/skills/mai-mai-saver/
```

安装后，直接对 WorkBuddy 说「我有 20 元想吃汉堡」这类话，技能会自动触发并调用本脚本。

> 想团队共享，可改放到项目级目录 `{项目}/.workbuddy/skills/mai-mai-saver/`。

---

## 四、目录结构

```
MCD-Project/
├── mai_mai_saver.py            # 主程序（单文件，自包含，可直接运行）
├── SKILL.md                    # Skill 定义（供 AI 智能体使用）
├── README.md                   # 本文件（供人阅读）
├── data/
│   └── coupons.sample.json     # 本地券库模板
└── tools/
    └── mock_mcd_mcp.py         # 本地模拟「麦当劳 MCP Server」，用于联调
```

---

## 五、命令行参数

| 参数 | 说明 |
|------|------|
| `-b, --budget` | 预算（元）。省略则进入交互模式 |
| `-c, --craving` | 想吃的，多个用逗号分隔，如 `"汉堡,可乐"` |
| `--coupons-file` | 指定本地券库 JSON，**完全替代**内置券库 |
| `--no-mcp` | 跳过 MCP，只用本地数据 |
| `--no-combo` | 只推荐单品，不推荐组合 |
| `--top N` | 每类推荐条数，默认 3 |
| `--list` | 列出全部券后退出 |
| `--json` | 以 JSON 输出，便于程序化处理 |
| `-v, --verbose` | 打印 MCP 调试信息 |

---

## 六、输出说明

| 列 / 字段 | 含义 |
|------|------|
| 券名 | 优惠券名称 |
| 商品 | 券适用的商品 |
| 原价 | 门市价 |
| 到手价 | 用券后的实付价 |
| 省 | 原价 − 到手价 |
| 命中口味 | 该券匹配到了你输入的哪些口味词（展示你输入的原词） |
| 渠道 | 券的领取渠道，如「麦当劳App」「小程序」 |
| 合计 / 共省 | 组合内各券到手价之和 / 原价之和 − 合计 |
| 预算利用 | 组合合计 ÷ 预算，越接近 100% 说明钱花得越满 |

底部统计行会显示「预算内可用券 N 张 · 超预算 N 张 · 已过期 N 张」。

---

## 七、推荐算法

**筛选**：剔除已过期、到手价超预算、门槛金额超预算的券。

**单品打分**（`score_single`）：

```
总分 = 口味覆盖率 × 100        # 命中用户想吃的程度，权重最高
     + 省钱比例   × 45         # (原价 − 到手价) / 原价
     + 预算利用率 × 15         # 到手价 / 预算，避免只挑最便宜的
```

口味词做同义词扩展（见代码中的 `SYNONYMS`）；展示时只回显你输入的原词，不暴露同义词噪音。

> 早期版本「预算利用率」权重为 25，会导致推荐最贵的商品而非折扣最优的，已下调至 15。

**组合推荐**：从打分前 12 名的券里穷举 2–3 张的组合，要求总价不超预算，并通过 `is_valid_combo` 合理性校验：

1. 商品名不重复；
2. 最多 1 张套餐券；
3. 含套餐时不再搭配饮品 / 小食 / 甜品（套餐通常已包含）；
4. 各品类桶（主食 ≤3、饮品 ≤1、小食 ≤1、甜品 ≤1）不超过上限。

这样能避免「套餐 + 可乐」这类买重的搭配。组合分在单品分基础上叠加口味覆盖、省钱比例、预算利用率，并扣除搭配复杂度惩罚。

**兜底**：预算内一张券都匹配不上时，给出最接近预算的券及需要追加的金额。

---

## 八、接入真实麦当劳 MCP

程序采用「MCP 优先 + 本地兜底」架构，配置环境变量即可启用，**无需修改任何代码**。

### 1. 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `MCD_MCP_URL` | 二选一 | Streamable HTTP 端点，如 `https://your-mcd-mcp.example.com/mcp` |
| `MCD_MCP_COMMAND` | 二选一 | stdio 启动命令，如 `npx -y @your-scope/mcd-coupon-mcp` |
| `MCD_MCP_TOKEN` | 否 | Bearer Token，仅 HTTP 传输时使用 |
| `MCD_MCP_TIMEOUT` | 否 | 单次请求超时秒数，默认 20；非法值自动回落到默认值 |

**优先级**：`MCD_MCP_URL` 优先于 `MCD_MCP_COMMAND`，两者都配置时走 HTTP。

### 2. 按操作系统设置

```bat
:: Windows CMD
set MCD_MCP_URL=https://your-mcd-mcp.example.com/mcp
set MCD_MCP_TOKEN=your-token
python mai_mai_saver.py --budget 20 --craving 汉堡 -v
```

```powershell
# Windows PowerShell
$env:MCD_MCP_URL = "https://your-mcd-mcp.example.com/mcp"
$env:MCD_MCP_TOKEN = "your-token"
python mai_mai_saver.py --budget 20 --craving 汉堡 -v
```

```bash
# macOS / Linux
export MCD_MCP_URL="https://your-mcd-mcp.example.com/mcp"
export MCD_MCP_TOKEN="your-token"
python3 mai_mai_saver.py --budget 20 --craving 汉堡 -v
```

想持久生效，请把变量写入系统环境变量（Windows：系统属性 → 环境变量）或 shell 配置文件（`~/.bashrc` / `~/.zshrc`）。

**取消配置**：CMD 用 `set MCD_MCP_URL=`，PowerShell 用 `Remove-Item Env:\MCD_MCP_URL`，bash 用 `unset MCD_MCP_URL`。

### 3. 客户端行为

启用后会依次执行：

1. `initialize` → `notifications/initialized` → `tools/list` 完成握手；
2. 在 `tools/list` 返回的工具中，按 `search_coupons` → `list_coupons` → `get_coupons` → `query_coupons` → `coupon_search` → 名称含 `coupon` 的顺序，选中第一个可用的；
3. 以 `tools/call` 调用，参数为 `{"budget": <预算>, "max_price": <预算>, "keyword": "<口味词，空格分隔>"}`；
4. 解析返回值，兼容 `structuredContent` 与 `content[].text`（JSON 字符串）两种封装；HTTP 响应同时支持普通 JSON 与 SSE。

### 4. MCP 服务的工具契约

要让本程序正确对接，你的 MCP 服务需满足：

**必须暴露的工具**：任一名称在上述候选列表中的查券工具，接受以下入参（均为可选，按需使用）：

| 入参 | 类型 | 说明 |
|------|------|------|
| `budget` / `max_price` | number | 预算上限（元） |
| `keyword` | string | 口味关键词，空格分隔 |

**返回内容**：一个券数组，每项字段名可用中文、驼峰、下划线任一风格书写（别名表见 `mai_mai_saver.py` 的 `_FIELD_ALIASES`）。

| 字段 | 必需 | 别名示例 |
|------|:---:|------|
| 商品名 | ✅ | `item` / `productName` / `商品名` |
| 券后价 | ✅ | `final_price` / `couponPrice` / `券后价` / `到手价` |
| 券名 | 建议 | `title` / `couponName` / `券名` |
| 原价 | 建议 | `original_price` / `listPrice` / `原价`（缺失则按无优惠处理） |
| 品类 | 建议 | `category` / `categories` / `品类`（用于口味匹配与组合去重） |
| 渠道 | 否 | `channel` / `平台` |
| 有效期 | 否 | `valid_until` / `validUntil` / `有效期`（已过期的券会被剔除） |
| 门槛 | 否 | `min_spend` / `threshold` / `门槛` |
| 备注 | 否 | `note` / `remark` / `备注` |

只提供最少的「商品名 + 券后价」也能跑通，只是原价缺失时「省了多少」会显示为 0。

### 5. 当前状态说明

> ⚠️ 经全量检索，**当前连接器市场中尚无麦当劳官方 MCP 服务**。上面的环境变量是为后续拿到真实 MCP 端点预留的接入位；在此之前程序会正常使用本地券库，不属于故障。

---

## 九、联调与自测

`tools/mock_mcd_mcp.py` 是一个本地模拟的「麦当劳 MCP Server」（stdio 传输），可用于验证 MCP 链路，同时是接入真实 MCP 时的工具契约参考实现。

```bash
# 1) 验证 MCP 链路
set MCD_MCP_COMMAND=python tools/mock_mcd_mcp.py
python mai_mai_saver.py --budget 20 --craving 汉堡 -v
# 预期：数据来源显示「麦当劳 MCP · stdio(...)」，券名带【MCP】前缀

# 2) 验证本地券库
python mai_mai_saver.py --budget 20 --craving 汉堡 --coupons-file data/coupons.sample.json

# 3) 验证降级（MCP 连不上时自动回落）
set MCD_MCP_URL=http://127.0.0.1:9/mcp
python mai_mai_saver.py --budget 20 --craving 汉堡 -v
# 预期：数据来源显示「内置示例券库（已降级）」
```

---

## 十、维护本地券库

复制模板并填入真实数据：

```bash
# Windows
copy data\coupons.sample.json data\coupons.json
# macOS / Linux
cp data/coupons.sample.json data/coupons.json
```

编辑 `data/coupons.json` 后使用：

```bash
python mai_mai_saver.py --budget 20 --craving 汉堡 --coupons-file data/coupons.json
```

`--coupons-file` 会**完全替代**内置券库，因此该文件里的数据必须自足。

---

## 十一、常见问题

| 现象 | 原因与处理 |
|------|------|
| 数据来源显示「内置示例券库（已降级）」 | MCP 未配置或连接失败。加 `-v` 看具体原因，或忽略——这是预期降级行为 |
| 数据来源显示「本地文件」但券很少 | 用了 `--coupons-file`，该文件会完全替代内置券库，请确认文件内容完整 |
| 提示「MCP 服务未暴露查券工具」 | 服务端的工具名不在候选列表中。改名或改用含 `coupon` 的工具名 |
| 推荐结果为空 | 预算过低。程序会给出最接近预算的券及需追加金额 |
| 中文显示为乱码 | Windows 下先执行 `chcp 65001` |
| `python: command not found` | 未安装 Python 或未加入 PATH；macOS/Linux 试 `python3` |
| 想固定用本地数据 | 加 `--no-mcp`，或清空 MCD 相关环境变量 |

---

## 十二、免责声明

内置券库与 `tools/mock_mcd_mcp.py` 中的价格、有效期均为**示例数据**，不代表麦当劳真实报价。实际下单请以麦当劳 App / 小程序券面为准。
