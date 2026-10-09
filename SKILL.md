---
name: mai-mai-saver
description: 麦麦省钱助手。当用户给出吃饭预算（如“20元”）并说明想吃的品类（如“想吃汉堡”）时，自动筛选预算内可用的麦当劳优惠券，按“口味匹配度 + 省钱力度 + 预算利用率”打分，输出最划算的单品推荐和不多花钱的超值组合推荐。适用于“预算X元怎么点麦当劳最划算”“有什么券能用”“帮我凑一单”等场景。数据优先来自麦当劳 MCP 服务，不可用时自动降级到本地券库。
agent_created: true
---

# 麦麦省钱助手 (MaiMai Saver)

## 用途

给定「预算 + 想吃的」，从可用优惠券中挑出预算内的最优解：

- **单品优选**：单张券能拿到的最划算商品；
- **超值组合**：2–3 张券的组合，把预算用满但不浪费，并自动排除「买重了」的搭配（如套餐再叠一份薯条）。

所有推荐均严格满足「总价 ≤ 预算」的硬约束。

## 何时使用

用户表达以下意图时使用本技能：

- 「我有 20 元，想吃汉堡，怎么点最划算」
- 「麦当劳有什么券能用」
- 「帮我用 30 元凑一单」
- 「板烧鸡腿堡现在多少钱 / 有优惠吗」

## 前置条件

执行前确认：

1. 技能目录下存在 `mai_mai_saver.py`（与本文件同级）；
2. 环境有 Python 3.8+，用 `python --version`（macOS / Linux 用 `python3`）确认；
3. 无需安装任何第三方依赖；
4. 未联网、未配置 MCP 环境变量时可正常运行——会使用内置示例券库，属预期行为，**不要当成故障上报**。

## 执行步骤

### 1. 解析用户输入

从用户话语中提取两个参数：

- `--budget`：预算金额（元），纯数字。用户说「20元」「二十块」都归一化为 `20`。
- `--craving`：想吃的口味，多个用英文逗号分隔，如 `"汉堡,可乐"`。用户没提口味时省略该参数。

若用户未给出预算，先向用户确认预算，不要自行假设。

### 2. 在技能目录下执行

```bash
python mai_mai_saver.py --budget <预算> --craving <想吃的>
```

macOS / Linux 将 `python` 换成 `python3`。示例：

```bash
python mai_mai_saver.py --budget 20 --craving 汉堡
python mai_mai_saver.py --budget 35 --craving "汉堡,可乐"
python mai_mai_saver.py --budget 20 --craving 汉堡 --json
```

### 3. 解读输出并转述给用户

直接引用脚本输出中的关键信息：券名、商品、原价、到手价、省了多少、渠道，以及组合明细与剩余预算。不要编造脚本未返回的券或价格。

输出中「数据来源」一行说明了本次数据从哪来（麦当劳 MCP / 本地文件 / 内置示例券库），必要时向用户说明。

## 命令行参数

| 参数 | 说明 |
|------|------|
| `-b, --budget` | 预算（元）。省略则进入交互模式 |
| `-c, --craving` | 想吃的，多个用逗号分隔，如 `"汉堡,可乐"` |
| `--coupons-file` | 指定本地券库 JSON，完全替代内置券库 |
| `--no-mcp` | 跳过 MCP，只用本地数据 |
| `--no-combo` | 只推荐单品 |
| `--top N` | 每类推荐条数，默认 3 |
| `--list` | 列出全部券后退出（用户问「有哪些券」时用） |
| `--json` | 以 JSON 输出，便于后续处理 |
| `-v, --verbose` | 打印 MCP 调试信息（排查数据来源问题时加） |

## 数据来源与 MCP 接入

按以下优先级取数，任何一层失败都会自动降级，不会导致无结果：

1. **麦当劳 MCP 服务**（JSON-RPC 2.0）
2. **本地券库文件**（`--coupons-file`）
3. **内置示例券库**（开箱即用，价格仅供演示）

### 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `MCD_MCP_URL` | 二选一 | Streamable HTTP 端点，如 `https://your-mcd-mcp.example.com/mcp` |
| `MCD_MCP_COMMAND` | 二选一 | stdio 启动命令，如 `npx -y @your-scope/mcd-coupon-mcp` |
| `MCD_MCP_TOKEN` | 否 | Bearer Token，仅 HTTP 传输使用 |
| `MCD_MCP_TIMEOUT` | 否 | 单次请求超时秒数，默认 20 |

**优先级**：`MCD_MCP_URL` 高于 `MCD_MCP_COMMAND`。

设置方式（按平台选择，仅对当前终端会话生效）：

```bat
:: Windows CMD
set MCD_MCP_URL=https://your-mcd-mcp.example.com/mcp
```

```powershell
# Windows PowerShell
$env:MCD_MCP_URL = "https://your-mcd-mcp.example.com/mcp"
```

```bash
# macOS / Linux
export MCD_MCP_URL="https://your-mcd-mcp.example.com/mcp"
```

### 客户端行为

启用后依次执行：`initialize` → `notifications/initialized` → `tools/list` 握手；在返回的工具中按
`search_coupons` → `list_coupons` → `get_coupons` → `query_coupons` → `coupon_search` → 名称含 `coupon` 的顺序选中第一个可用工具；
以 `tools/call` 传入 `{"budget": ..., "max_price": ..., "keyword": ...}`；
返回值兼容 `structuredContent` 与 `content[].text`（JSON 字符串），HTTP 响应支持普通 JSON 与 SSE。

### MCP 服务的工具契约

对接真实 MCP 服务时，服务端需满足：

- **暴露**任一名称在候选列表中的查券工具，接受可选入参 `budget` / `max_price`（number）与 `keyword`（string）；
- **返回**券数组，每项字段名可用中文、驼峰、下划线任一风格（别名表见 `mai_mai_saver.py` 的 `_FIELD_ALIASES`）。

必需字段仅两个：**商品名**（`item` / `productName` / `商品名`）与**券后价**（`final_price` / `couponPrice` / `券后价` / `到手价`）。
建议同时提供**原价**（`original_price` / `listPrice` / `原价`）、**品类**（`category` / `categories` / `品类`）、
**有效期**（`valid_until` / `有效期`）——缺原价时「省了多少」会显示为 0，缺品类时口味匹配与组合去重会退化为按商品名判断。

### 当前状态

> ⚠️ 当前连接器市场中尚无麦当劳官方 MCP 服务。环境变量是预留的接入位；未配置时程序正常使用本地券库。

## 联调与验证

`tools/mock_mcd_mcp.py` 是本地模拟的麦当劳 MCP Server（stdio），用于验证 MCP 链路，同时是工具契约的参考实现：

```bash
# Windows CMD
set MCD_MCP_COMMAND=python tools/mock_mcd_mcp.py
python mai_mai_saver.py --budget 20 --craving 汉堡 -v
```

预期：数据来源显示「麦当劳 MCP · stdio(...)」，券名带【MCP】前缀。

## 故障排查

| 现象 | 处理 |
|------|------|
| 数据来源显示「内置示例券库（已降级）」 | MCP 未配置或连接失败。加 `-v` 查看原因；若用户未要求接 MCP，可忽略 |
| 提示「MCP 服务未暴露查券工具」 | 服务端工具名不在候选列表内，需改名或使用含 `coupon` 的名称 |
| 推荐结果为空 | 预算过低。脚本已给出最接近预算的券及需追加金额，直接转述 |
| 中文乱码（Windows） | 先执行 `chcp 65001` |
| 找不到 python 命令 | macOS / Linux 改用 `python3` |

## 注意事项

- 券面价格与有效期以麦当劳 App / 小程序实际展示为准；内置数据与模拟服务中的数据仅为演示，**不代表真实报价**，转述结果时不要当作真实价格承诺。
- `--coupons-file` 会完全替代内置券库，该文件需自足。
- 仅依赖 Python 标准库，无需安装第三方依赖。
