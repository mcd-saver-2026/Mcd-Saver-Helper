#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦省钱助手 (MaiMai Saver)
===========================

输入预算 + 想吃的，自动匹配预算内的麦当劳优惠券并给出推荐。

数据来源（三级降级，保证永远能跑出结果）：
  1. 麦当劳 MCP 服务（JSON-RPC 2.0，支持 stdio 与 Streamable HTTP 两种传输）
  2. 本地 coupons.json（--coupons-file 指定，便于你自己维护/更新）
  3. 内置示例券库（开箱即用，仅用于演示，价格请以官方渠道为准）

用法示例：
    python mai_mai_saver.py --budget 20 --craving 汉堡
    python mai_mai_saver.py --budget 35 --craving "汉堡,可乐"
    python mai_mai_saver.py --budget 15 --craving 炸鸡 --json
    python mai_mai_saver.py                      # 进入交互模式

接入真实麦当劳 MCP：设置环境变量后重跑即可
    MCD_MCP_URL      = https://your-mcd-mcp.example.com/mcp     # HTTP 传输
    MCD_MCP_COMMAND  = "npx -y @your-scope/mcd-coupon-mcp"      # stdio 传输
    MCD_MCP_TOKEN    = <bearer token，可选>

仅依赖 Python 标准库，无需 pip 安装任何东西。
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import shlex
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# 0. 基础环境
# --------------------------------------------------------------------------- #

try:  # Windows 控制台默认 GBK，强制 UTF-8 避免中文/emoji 报错
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

DEFAULT_TIMEOUT = 20  # MCP 请求超时（秒），可用 MCD_MCP_TIMEOUT 环境变量覆盖


def env_timeout() -> int:
    """读取 MCD_MCP_TIMEOUT，非法值回落到默认超时。"""
    raw = os.environ.get("MCD_MCP_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        return max(1, int(float(raw)))
    except ValueError:
        return DEFAULT_TIMEOUT


# 麦当劳 MCP 中「查券」工具的候选名称，按顺序探测，命中第一个可用的
COUPON_TOOL_CANDIDATES = (
    "search_coupons",
    "list_coupons",
    "get_coupons",
    "query_coupons",
    "coupon_search",
    "listCoupons",
)

# 口味关键词 -> 同义词扩展表（提升匹配命中率）
SYNONYMS: Dict[str, List[str]] = {
    "汉堡": ["汉堡", "堡", "burger", "包"],
    "炸鸡": ["炸鸡", "鸡", "麦乐鸡", "鸡块", "辣翅", "鸡翅"],
    "鸡肉": ["鸡", "鸡腿", "鸡肉"],
    "牛肉": ["牛", "牛肉", "巨无霸"],
    "薯条": ["薯条", "薯", "fries"],
    "可乐": ["可乐", "雪碧", "汽水", "饮品", "饮料", "coke"],
    "咖啡": ["咖啡", "拿铁", "美式", "卡布"],
    "饮品": ["可乐", "雪碧", "咖啡", "拿铁", "美式", "饮品", "饮料", "奶茶"],
    "甜品": ["冰淇淋", "甜筒", "麦旋风", "新地", "派", "甜品", "冰"],
    "早餐": ["早餐", "松饼", "粥", "麦满分", "汉堡"],
    "套餐": ["套餐", "组合", "桶", "餐"],
    "鱼": ["鱼", "鳕鱼", "麦香鱼"],
}


# --------------------------------------------------------------------------- #
# 1. 内置示例券库（兜底数据）
# --------------------------------------------------------------------------- #

LOCAL_COUPONS: List[Dict[str, Any]] = [
    # ---- 汉堡类 ----
    dict(coupon_id="HB001", title="板烧鸡腿堡单品券", item="板烧鸡腿堡",
         category=["汉堡", "鸡肉"], original_price=22.5, final_price=15.9,
         channel="麦当劳App", valid_until="2026-12-31", note="每日限领1张"),
    dict(coupon_id="HB002", title="麦辣鸡腿堡单品券", item="麦辣鸡腿堡",
         category=["汉堡", "鸡肉"], original_price=21.0, final_price=14.9,
         channel="麦当劳App", valid_until="2026-12-31"),
    dict(coupon_id="HB003", title="双层吉士汉堡券", item="双层吉士汉堡",
         category=["汉堡", "牛肉"], original_price=18.0, final_price=12.5,
         channel="小程序", valid_until="2026-12-31"),
    dict(coupon_id="HB004", title="吉士汉堡特惠券", item="吉士汉堡",
         category=["汉堡", "牛肉"], original_price=12.5, final_price=8.9,
         channel="小程序", valid_until="2026-12-31"),
    dict(coupon_id="HB005", title="巨无霸优惠券", item="巨无霸",
         category=["汉堡", "牛肉"], original_price=25.0, final_price=19.9,
         channel="麦当劳App", valid_until="2026-12-31", min_spend=0),
    dict(coupon_id="HB006", title="麦香鸡汉堡券", item="麦香鸡",
         category=["汉堡", "鸡肉"], original_price=13.5, final_price=9.9,
         channel="小程序", valid_until="2026-12-31"),
    dict(coupon_id="HB007", title="麦香鱼汉堡券", item="麦香鱼",
         category=["汉堡", "鱼"], original_price=14.0, final_price=10.5,
         channel="小程序", valid_until="2026-12-31"),

    # ---- 炸鸡 / 小食 ----
    dict(coupon_id="SN001", title="麦乐鸡(5块)券", item="麦乐鸡5块",
         category=["炸鸡", "小食"], original_price=13.0, final_price=8.5,
         channel="麦当劳App", valid_until="2026-12-31"),
    dict(coupon_id="SN002", title="麦辣鸡翅(2块)券", item="麦辣鸡翅2块",
         category=["炸鸡", "小食"], original_price=13.5, final_price=9.0,
         channel="麦当劳App", valid_until="2026-12-31"),
    dict(coupon_id="SN003", title="那么大鸡排券", item="那么大鸡排",
         category=["炸鸡", "小食"], original_price=18.0, final_price=12.9,
         channel="小程序", valid_until="2026-12-31"),
    dict(coupon_id="SN004", title="中薯条券", item="中薯条",
         category=["薯条", "小食"], original_price=11.0, final_price=6.9,
         channel="麦当劳App", valid_until="2026-12-31"),
    dict(coupon_id="SN005", title="大薯条券", item="大薯条",
         category=["薯条", "小食"], original_price=14.0, final_price=9.5,
         channel="小程序", valid_until="2026-12-31"),

    # ---- 饮品 ----
    dict(coupon_id="DR001", title="中杯可乐券", item="中杯可乐",
         category=["可乐", "饮品"], original_price=9.5, final_price=5.9,
         channel="麦当劳App", valid_until="2026-12-31"),
    dict(coupon_id="DR002", title="大杯可乐券", item="大杯可乐",
         category=["可乐", "饮品"], original_price=11.5, final_price=7.9,
         channel="小程序", valid_until="2026-12-31"),
    dict(coupon_id="DR003", title="雪碧中杯券", item="雪碧中杯",
         category=["饮品"], original_price=9.5, final_price=5.9,
         channel="小程序", valid_until="2026-12-31"),
    dict(coupon_id="DR004", title="鲜煮咖啡(中)券", item="鲜煮咖啡中杯",
         category=["咖啡", "饮品"], original_price=11.0, final_price=6.9,
         channel="麦当劳App", valid_until="2026-12-31"),
    dict(coupon_id="DR005", title="拿铁(中)优惠券", item="拿铁中杯",
         category=["咖啡", "饮品"], original_price=16.0, final_price=11.9,
         channel="麦当劳App", valid_until="2026-12-31"),

    # ---- 甜品 ----
    dict(coupon_id="DS001", title="圆筒冰淇淋券", item="圆筒冰淇淋",
         category=["甜品"], original_price=5.0, final_price=2.9,
         channel="麦当劳App", valid_until="2026-12-31"),
    dict(coupon_id="DS002", title="麦旋风(奥利奥)券", item="奥利奥麦旋风",
         category=["甜品"], original_price=14.0, final_price=9.9,
         channel="小程序", valid_until="2026-12-31"),
    dict(coupon_id="DS003", title="苹果派券", item="苹果派",
         category=["甜品"], original_price=8.0, final_price=5.5,
         channel="小程序", valid_until="2026-12-31"),

    # ---- 套餐 ----
    dict(coupon_id="CM001", title="1+1随心选券", item="1+1随心选",
         category=["套餐", "汉堡", "饮品"], original_price=19.5, final_price=13.9,
         channel="麦当劳App", valid_until="2026-12-31", note="1款主食+1款小食/饮品"),
    dict(coupon_id="CM002", title="板烧鸡腿堡超值套餐券", item="板烧鸡腿堡套餐",
         category=["套餐", "汉堡", "薯条", "饮品"], original_price=34.0, final_price=24.9,
         channel="麦当劳App", valid_until="2026-12-31", note="汉堡+中薯+中可"),
    dict(coupon_id="CM003", title="巨无霸超值套餐券", item="巨无霸套餐",
         category=["套餐", "汉堡", "薯条", "可乐"], original_price=37.0, final_price=27.9,
         channel="麦当劳App", valid_until="2026-12-31", note="汉堡+中薯+中可"),
    dict(coupon_id="CM004", title="麦乐鸡欢乐桶券", item="麦乐鸡20块桶",
         category=["套餐", "炸鸡", "小食"], original_price=42.0, final_price=29.9,
         channel="小程序", valid_until="2026-12-31"),
    dict(coupon_id="CM005", title="早餐组合券", item="早餐组合",
         category=["早餐", "套餐"], original_price=18.0, final_price=11.9,
         channel="麦当劳App", valid_until="2026-12-31", note="早餐时段 05:00-10:30"),
]


# --------------------------------------------------------------------------- #
# 2. 数据模型
# --------------------------------------------------------------------------- #

@dataclass
class Coupon:
    """一张优惠券。价格统一为「单个商品/套餐的到手价」。"""

    coupon_id: str
    title: str
    item: str
    category: List[str] = field(default_factory=list)
    original_price: float = 0.0
    final_price: float = 0.0
    channel: str = "麦当劳App"
    min_spend: float = 0.0
    valid_until: str = ""
    note: str = ""

    # ---- 派生指标 ----
    @property
    def saved(self) -> float:
        """省下多少钱。"""
        return round(max(self.original_price - self.final_price, 0.0), 2)

    @property
    def discount_rate(self) -> float:
        """折扣力度，1.0 表示无优惠。"""
        if self.original_price <= 0:
            return 1.0
        return round(self.final_price / self.original_price, 3)

    def is_expired(self, today: Optional[date] = None) -> bool:
        today = today or date.today()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(self.valid_until, fmt).date() < today
            except (ValueError, TypeError):
                continue
        return False  # 解析不了就当长期有效

    def searchable_text(self) -> str:
        return " ".join([self.title, self.item, " ".join(self.category)]).lower()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["saved"] = self.saved
        d["discount_rate"] = self.discount_rate
        return d


# MCP / 外部数据源的字段别名表（中文、驼峰、下划线全兼容）
_FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "coupon_id": ("coupon_id", "id", "couponId", "couponID", "couponCode", "券id", "编号", "券编号"),
    "title": ("title", "name", "coupon_name", "couponName", "couponTitle",
              "标题", "券名", "名称"),
    "item": ("item", "product", "product_name", "productName", "productTitle",
             "sku", "skuName", "商品", "商品名", "适用商品"),
    "category": ("category", "categories", "categoryName", "categoryNames",
                 "tags", "tag", "品类", "分类", "标签"),
    "original_price": ("original_price", "originalPrice", "list_price", "listPrice",
                       "originPrice", "price", "原价", "门市价"),
    "final_price": ("final_price", "finalPrice", "coupon_price", "couponPrice",
                    "discounted_price", "discountedPrice", "deal_price", "dealPrice",
                    "salePrice", "券后价", "现价", "到手价"),
    "channel": ("channel", "source", "platform", "渠道", "来源", "平台"),
    "min_spend": ("min_spend", "minSpend", "threshold", "minAmount", "门槛", "最低消费"),
    "valid_until": ("valid_until", "validUntil", "expire_at", "expireAt", "expireTime",
                    "end_date", "endDate", "有效期", "到期时间"),
    "note": ("note", "remark", "description", "desc", "说明", "备注"),
}


def _pick(raw: Dict[str, Any], key: str, default: Any = None) -> Any:
    for alias in _FIELD_ALIASES[key]:
        if alias in raw and raw[alias] not in (None, ""):
            return raw[alias]
    return default


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return round(float(str(v).replace("¥", "").replace("元", "").strip()), 2)
    except (TypeError, ValueError):
        return default


def coupon_from_raw(raw: Dict[str, Any]) -> Optional[Coupon]:
    """把任意来源（MCP / JSON）的一条记录规范化为 Coupon，字段缺失则返回 None。"""
    if not isinstance(raw, dict):
        return None

    item = str(_pick(raw, "item", "") or "").strip()
    title = str(_pick(raw, "title", "") or item).strip()
    if not item and not title:
        return None

    cat = _pick(raw, "category", []) or []
    if isinstance(cat, str):
        cat = [c.strip() for c in cat.replace("，", ",").replace("、", ",").split(",") if c.strip()]
    elif not isinstance(cat, list):
        cat = []

    original = _to_float(_pick(raw, "original_price"))
    final = _to_float(_pick(raw, "final_price"))
    if final <= 0:
        # 只给了原价没有券后价 => 视为无优惠，避免推荐出错
        final = original
    if original <= 0:
        original = final

    return Coupon(
        coupon_id=str(_pick(raw, "coupon_id", "") or f"AUTO-{abs(hash(item + title)) % 100000}"),
        title=title,
        item=item or title,
        category=[str(c) for c in cat],
        original_price=original,
        final_price=final,
        channel=str(_pick(raw, "channel", "未知渠道") or "未知渠道"),
        min_spend=_to_float(_pick(raw, "min_spend")),
        valid_until=str(_pick(raw, "valid_until", "") or ""),
        note=str(_pick(raw, "note", "") or ""),
    )


# --------------------------------------------------------------------------- #
# 3. MCP 客户端（JSON-RPC 2.0）
# --------------------------------------------------------------------------- #

class McpError(RuntimeError):
    pass


class _McpJsonRpc:
    """JSON-RPC 2.0 收发骨架，子类只需实现 _send / _recv。"""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._next_id = 0
        self.tools: List[Dict[str, Any]] = []
        self._ready = False

    # -- 子类实现 --
    def _start(self) -> None:
        raise NotImplementedError

    def _send(self, message: Dict[str, Any]) -> None:
        raise NotImplementedError

    def _recv(self, want_id: int) -> Dict[str, Any]:
        raise NotImplementedError

    def _stop(self) -> None:
        pass

    # -- 公共接口 --
    def _call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._next_id += 1
        req = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}
        self._send(req)
        resp = self._recv(self._next_id)
        if "error" in resp:
            err = resp["error"]
            raise McpError(f"{method} 失败: {err.get('message', err)}")
        return resp.get("result", {}) or {}

    def _notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def handshake(self) -> None:
        if self._ready:
            return
        self._start()
        self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mai-mai-saver", "version": "1.0.0"},
        })
        self._notify("notifications/initialized")
        result = self._call("tools/list")
        self.tools = result.get("tools", []) or []
        self._ready = True

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self.handshake()
        result = self._call("tools/call", {"name": name, "arguments": arguments})
        return self._unwrap_tool_result(result)

    @staticmethod
    def _unwrap_tool_result(result: Dict[str, Any]) -> Any:
        """MCP tools/call 返回 {content:[{type:'text',text:'...'}], structuredContent:{...}}，
        这里尽力把里面真正的数据挖出来。"""
        if not isinstance(result, dict):
            return result
        if isinstance(result.get("structuredContent"), (dict, list)):
            return result["structuredContent"]

        chunks: List[str] = []
        for block in result.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                chunks.append(str(block.get("text", "")))
        text = "\n".join(chunks).strip()
        if not text:
            return result
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def pick_coupon_tool(self) -> Optional[str]:
        self.handshake()
        names = {t.get("name") for t in self.tools if isinstance(t, dict)}
        for cand in COUPON_TOOL_CANDIDATES:
            if cand in names:
                return cand
        # 退而求其次：名字里带 coupon 的任意工具
        for n in sorted(n for n in names if n and "coupon" in n.lower()):
            return n
        return None


class McpStdioClient(_McpJsonRpc):
    """通过子进程 stdin/stdout 与 MCP server 通信（换行分隔 JSON）。"""

    def __init__(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        super().__init__(timeout)
        self.command = command
        self.proc: Optional[subprocess.Popen] = None

    def describe(self) -> str:
        return f"stdio({self.command})"

    def _start(self) -> None:
        self.proc = subprocess.Popen(
            shlex.split(self.command, posix=os.name != "nt"),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )

    def _send(self, message: Dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise McpError("stdio 通道未启动")
        self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _recv(self, want_id: int) -> Dict[str, Any]:
        if not self.proc or not self.proc.stdout:
            raise McpError("stdio 通道未启动")
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise McpError("stdio 通道已关闭")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # 服务端日志混入 stdout，跳过
            if msg.get("id") == want_id:
                return msg

    def _stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass


class McpHttpClient(_McpJsonRpc):
    """Streamable HTTP 传输：POST JSON-RPC，响应可能是 JSON 或 SSE。"""

    def __init__(self, url: str, token: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> None:
        super().__init__(timeout)
        self.url = url
        self.token = token

    def describe(self) -> str:
        return f"http({self.url})"

    def _headers(self) -> Dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _start(self) -> None:
        return

    def _send(self, message: Dict[str, Any]) -> None:
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            raise McpError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}") from e
        except urllib.error.URLError as e:
            raise McpError(f"无法连接 MCP 服务: {e.reason}") from e

        self._last = self._parse_body(raw, ctype)

    @staticmethod
    def _parse_body(raw: str, ctype: str) -> Optional[Dict[str, Any]]:
        raw = raw.strip()
        if not raw:
            return None
        if "text/event-stream" in ctype or raw.startswith("event:") or raw.startswith("data:"):
            last = None
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        last = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
            return last
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _recv(self, want_id: int) -> Dict[str, Any]:
        msg = getattr(self, "_last", None)
        if msg is None:
            raise McpError("MCP 服务返回了空响应")
        return msg

    def _stop(self) -> None:
        return


def build_mcp_client_from_env(verbose: bool = False):
    """按环境变量构造 MCP 客户端；未配置则返回 None（走本地兜底）。

    优先级：MCD_MCP_URL（HTTP） > MCD_MCP_COMMAND（stdio）。
    """
    url = os.environ.get("MCD_MCP_URL", "").strip()
    command = os.environ.get("MCD_MCP_COMMAND", "").strip()
    token = os.environ.get("MCD_MCP_TOKEN", "").strip() or None
    timeout = env_timeout()
    if url:
        return McpHttpClient(url, token, timeout=timeout)
    if command:
        return McpStdioClient(command, timeout=timeout)
    if verbose:
        print("[i] 未检测到 MCD_MCP_URL / MCD_MCP_COMMAND，使用本地券库。", file=sys.stderr)
    return None


def fetch_coupons_via_mcp(client, budget: Optional[float], keywords: Sequence[str],
                          verbose: bool = False) -> List[Coupon]:
    """调用 MCP 上的查券工具，返回规范化后的 Coupon 列表。"""
    tool = client.pick_coupon_tool()
    if not tool:
        raise McpError(f"MCP 服务未暴露查券工具（已探测：{', '.join(COUPON_TOOL_CANDIDATES)}）")

    arguments: Dict[str, Any] = {}
    if budget is not None:
        arguments.update({"budget": budget, "max_price": budget})
    if keywords:
        arguments["keyword"] = " ".join(keywords)

    data = client.call_tool(tool, arguments)

    if isinstance(data, dict):
        for key in ("coupons", "data", "items", "list", "results", "result"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise McpError(f"查券工具返回了无法解析的数据类型：{type(data).__name__}")

    coupons = [c for c in (coupon_from_raw(r) for r in data) if c is not None]
    if verbose:
        print(f"[i] MCP({tool}) 返回 {len(coupons)} 张券。", file=sys.stderr)
    return coupons


# --------------------------------------------------------------------------- #
# 4. 券数据仓库：MCP -> 本地 JSON -> 内置数据
# --------------------------------------------------------------------------- #

@dataclass
class LoadResult:
    coupons: List[Coupon]
    source: str
    warning: str = ""


class CouponRepository:
    def __init__(self, use_mcp: bool = True, coupons_file: Optional[str] = None,
                 verbose: bool = False) -> None:
        self.use_mcp = use_mcp
        self.coupons_file = coupons_file
        self.verbose = verbose
        self._client = build_mcp_client_from_env(verbose) if use_mcp else None

    @property
    def client(self):
        return self._client

    def load(self, budget: Optional[float] = None, keywords: Sequence[str] = ()) -> LoadResult:
        warn = ""

        # 1) MCP
        if self._client is not None:
            try:
                coupons = fetch_coupons_via_mcp(self._client, budget, keywords, self.verbose)
                if coupons:
                    return LoadResult(coupons, f"麦当劳 MCP · {self._client.describe()}")
                warn = "MCP 返回 0 张券"
            except Exception as e:  # 任何异常都降级，不让用户用不了
                warn = f"MCP 不可用（{e}）"
                if self.verbose:
                    print(f"[!] {warn}", file=sys.stderr)
            finally:
                try:
                    self._client._stop()
                except Exception:
                    pass

        # 2) 本地 JSON
        if self.coupons_file:
            try:
                with open(self.coupons_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    raw = raw.get("coupons", [])
                coupons = [c for c in (coupon_from_raw(r) for r in raw) if c is not None]
                if coupons:
                    return LoadResult(coupons, f"本地文件 · {self.coupons_file}", warn)
                warn = (warn + "；" if warn else "") + "本地文件里没有有效券"
            except Exception as e:
                warn = (warn + "；" if warn else "") + f"读取 {self.coupons_file} 失败（{e}）"

        # 3) 内置
        coupons = [c for c in (coupon_from_raw(r) for r in LOCAL_COUPONS) if c is not None]
        source = "内置示例券库"
        if warn:
            source += "（已降级）"
            if self.verbose:
                print(f"[!] {warn}", file=sys.stderr)
        return LoadResult(coupons, source, warn)


# --------------------------------------------------------------------------- #
# 5. 推荐引擎
# --------------------------------------------------------------------------- #

# 品类分桶，用于判断组合是否「买重了」
BUCKETS: Dict[str, str] = {
    "汉堡": "main", "炸鸡": "main", "套餐": "main", "早餐": "main", "鱼": "main",
    "可乐": "drink", "饮品": "drink", "咖啡": "drink",
    "薯条": "side", "小食": "side",
    "甜品": "dessert",
}
BUCKET_CAP = {"main": 3, "drink": 1, "side": 1, "dessert": 1}  # 单桶最大件数
SETMEAL_EXCLUDED_BUCKETS = {"drink", "side", "dessert"}        # 有套餐时不该再配这些


def coupon_bucket(c: Coupon) -> str:
    for cat in c.category:
        if cat in BUCKETS:
            return BUCKETS[cat]
    return "main"


def is_valid_combo(group: Sequence[Coupon]) -> bool:
    """组合合理性校验，避免「买重了」：
    1) 商品名不重复；
    2) 最多 1 张套餐券；
    3) 含套餐时不再搭配饮品/小食/甜品（套餐通常已包含）；
    4) 各品类桶不超过上限。
    """
    items = [g.item.strip() for g in group]
    if len(set(items)) != len(items):
        return False

    setmeals = [g for g in group if "套餐" in g.category]
    if len(setmeals) > 1:
        return False

    if setmeals:
        for g in group:
            if g is setmeals[0]:
                continue
            if coupon_bucket(g) in SETMEAL_EXCLUDED_BUCKETS:
                return False

    counts: Dict[str, int] = {}
    for g in group:
        b = coupon_bucket(g)
        counts[b] = counts.get(b, 0) + 1
    for b, n in counts.items():
        if n > BUCKET_CAP.get(b, 3):
            return False
    return True


def parse_craving(text: str) -> List[str]:
    """把「想吃汉堡，顺便来杯可乐」拆成关键词列表。"""
    if not text:
        return []
    raw = text.replace("，", ",").replace("、", ",").replace("；", ",").replace(";", ",")
    raw = raw.replace("和", ",").replace("+", ",").replace(" ", ",").replace("/", ",")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or [text.strip()]


def expand_keywords(keywords: Sequence[str]) -> List[str]:
    """关键词同义词扩展（用于匹配）。"""
    out: List[str] = []
    for kw in keywords:
        k = kw.strip().lower()
        if not k:
            continue
        out.append(k)
        for key, syns in SYNONYMS.items():
            if key in kw or kw in key:
                out.extend(s.lower() for s in syns)
    # 去重保序
    seen, uniq = set(), []
    for k in out:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq


def keyword_groups(craving: str) -> List[Tuple[str, List[str]]]:
    """把用户输入拆成 [(原始词, 同义词集合), ...]，原始词用于展示，同义词用于匹配。"""
    groups: List[Tuple[str, List[str]]] = []
    for kw in parse_craving(craving):
        syns = {kw.strip().lower()}
        for key, lst in SYNONYMS.items():
            if key in kw or kw in key:
                syns.update(s.lower() for s in lst)
        syns.discard("")
        groups.append((kw, sorted(syns)))
    return groups


def matched_keywords(coupon: Coupon, groups: Sequence[Tuple[str, List[str]]]) -> List[str]:
    """返回命中的「用户原始词」，避免把同义词噪音暴露给用户。"""
    text = coupon.searchable_text()
    return [name for name, syns in groups if any(s in text for s in syns)]


@dataclass
class Pick:
    coupons: List[Coupon]
    score: float
    hit: List[str]

    @property
    def total_price(self) -> float:
        return round(sum(c.final_price for c in self.coupons), 2)

    @property
    def total_original(self) -> float:
        return round(sum(c.original_price for c in self.coupons), 2)

    @property
    def total_saved(self) -> float:
        return round(self.total_original - self.total_price, 2)


def score_single(c: Coupon, groups: Sequence[Tuple[str, List[str]]],
                 budget: float) -> Tuple[float, List[str]]:
    """打分：覆盖用户口味(主) + 省钱力度 + 预算利用率(辅)。"""
    hit = matched_keywords(c, groups)
    coverage = (len(hit) / len(groups)) if groups else 1.0
    savings_ratio = (c.saved / c.original_price) if c.original_price > 0 else 0.0
    utilization = min(c.final_price / budget, 1.0) if budget > 0 else 0.0
    score = coverage * 100 + savings_ratio * 45 + utilization * 15
    return round(score, 3), hit


def recommend(coupons: Iterable[Coupon], budget: float, craving: str,
              top_n: int = 3, allow_combo: bool = True) -> Dict[str, Any]:
    """核心推荐逻辑：预算过滤 + 口味匹配打分 + 单品/组合推荐。"""
    groups = keyword_groups(craving)
    keywords = [name for name, _ in groups]
    today = date.today()

    valid: List[Coupon] = []
    expired: List[Coupon] = []
    over_budget: List[Coupon] = []

    for c in coupons:
        if c.is_expired(today):
            expired.append(c)
            continue
        if c.final_price > budget + 1e-9:
            over_budget.append(c)
            continue
        if c.min_spend > 0 and c.min_spend > budget + 1e-9:
            over_budget.append(c)
            continue
        valid.append(c)

    scored: List[Tuple[float, List[str], Coupon]] = []
    for c in valid:
        s, hit = score_single(c, groups, budget)
        scored.append((s, hit, c))
    scored.sort(key=lambda x: (x[0], x[2].saved), reverse=True)

    singles = [Pick([c], s, hit) for s, hit, c in scored[:top_n]]

    combos: List[Pick] = []
    if allow_combo and len(scored) >= 2:
        pool = [c for _, _, c in scored[:12]]
        for size in (2, 3):
            for group in itertools.combinations(pool, size):
                ids = {g.coupon_id for g in group}
                if len(ids) != size:  # 同一张券不能叠加
                    continue
                total = sum(g.final_price for g in group)
                if total > budget + 1e-9:
                    continue
                if not is_valid_combo(group):
                    continue
                hit_union: List[str] = []
                base = 0.0
                for g in group:
                    s, hit = score_single(g, groups, budget)
                    base += s
                    hit_union.extend(hit)
                hit_union = list(dict.fromkeys(hit_union))
                coverage = (len(hit_union) / len(groups)) if groups else 1.0
                savings_ratio = sum(g.saved for g in group) / max(sum(g.original_price for g in group), 0.01)
                utilization = total / budget if budget > 0 else 0.0
                complexity_penalty = 8.0 * (size - 1)
                combo_score = (base * 0.75) + coverage * 70 + savings_ratio * 25 \
                    + utilization * 30 - complexity_penalty
                combos.append(Pick(list(group), round(combo_score, 3), hit_union))
        combos.sort(key=lambda p: (p.score, p.total_saved), reverse=True)
        combos = combos[:top_n]

    # 兜底建议：预算不够时，给出最接近的券
    nearest: List[Coupon] = sorted(over_budget, key=lambda c: c.final_price)[:3]

    return {
        "budget": budget,
        "craving": craving,
        "keywords": keywords,
        "total_coupons": len(valid) + len(over_budget) + len(expired),
        "singles": singles,
        "combos": combos,
        "nearest_over_budget": nearest,
        "expired_count": len(expired),
        "over_budget_count": len(over_budget),
        "pool_count": len(valid),
    }


# --------------------------------------------------------------------------- #
# 6. 输出渲染
# --------------------------------------------------------------------------- #

def dwidth(s: str) -> int:
    """按终端显示宽度计算字符串长度（中日韩全角算 2）。"""
    w = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad(s: str, width: int, align: str = "left") -> str:
    gap = max(width - dwidth(s), 0)
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def render_table(rows: List[List[str]], headers: List[str]) -> List[str]:
    cols = len(headers)
    widths = []
    for i in range(cols):
        widths.append(max([dwidth(headers[i])] + [dwidth(r[i]) for r in rows]))
    lines = [
        "  ".join(pad(headers[i], widths[i]) for i in range(cols)).rstrip(),
        "  ".join("-" * widths[i] for i in range(cols)),
    ]
    for r in rows:
        lines.append("  ".join(pad(r[i], widths[i]) for i in range(cols)).rstrip())
    return lines


def render_report(result: Dict[str, Any], source: str) -> str:
    budget = result["budget"]
    craving = result["craving"] or "（不限）"
    L: List[str] = []
    W = 66

    L.append("=" * W)
    L.append(f" 麦麦省钱助手 · 预算 ¥{budget:.2f} · 想吃：{craving}")
    L.append(f" 数据来源：{source}")
    L.append("=" * W)

    singles: List[Pick] = result["singles"]
    combos: List[Pick] = result["combos"]

    if not singles and not combos:
        L.append("")
        L.append(" 没有找到预算内的可用券。")
        if result["nearest_over_budget"]:
            L.append("")
            L.append(" 最接近预算的优惠（稍微加点预算就能拿下）：")
            rows = [[c.title, c.item, f"¥{c.final_price:.2f}",
                     f"+¥{c.final_price - budget:.2f}"] for c in result["nearest_over_budget"]]
            L.extend(render_table(rows, ["券名", "商品", "到手价", "需追加"]))
        return "\n".join(L)

    if singles:
        L.append("")
        L.append("【推荐一】单品优选（最划算的几张券）")
        rows = []
        for i, p in enumerate(singles, 1):
            c = p.coupons[0]
            hit = "、".join(p.hit) if p.hit else "-"
            rows.append([str(i), c.title, c.item, f"¥{c.original_price:.2f}",
                         f"¥{c.final_price:.2f}", f"省¥{c.saved:.2f}", hit, c.channel])
        L.extend(render_table(rows, ["#", "券名", "商品", "原价", "到手价", "省", "命中口味", "渠道"]))

    if combos:
        L.append("")
        L.append("【推荐二】超值组合（一次吃完预算，性价比最高）")
        rows = []
        for i, p in enumerate(combos, 1):
            names = " + ".join(c.item for c in p.coupons)
            rows.append([str(i), names, f"¥{p.total_price:.2f}",
                         f"省¥{p.total_saved:.2f}",
                         f"{p.total_price / budget * 100:.0f}%"])
        L.extend(render_table(rows, ["#", "组合内容", "合计", "共省", "预算利用"]))
        best = combos[0]
        L.append("")
        L.append(f" 组合明细 #{1}：")
        for c in best.coupons:
            note = f"（{c.note}）" if c.note else ""
            L.append(f"   · {pad(c.title, 22)} {pad(c.item, 16)}"
                     f" ¥{c.original_price:.2f} -> ¥{c.final_price:.2f}{note}")
        L.append(f"   合计 ¥{best.total_price:.2f}，共省 ¥{best.total_saved:.2f}，"
                 f"剩余预算 ¥{budget - best.total_price:.2f}")

    L.append("")
    L.append("-" * W)
    stats = f" 预算内可用券 {result['pool_count']} 张"
    if result["over_budget_count"]:
        stats += f" · 超预算 {result['over_budget_count']} 张"
    if result["expired_count"]:
        stats += f" · 已过期 {result['expired_count']} 张"
    L.append(stats)
    L.append(" 提示：价格为示例数据，下单前请以麦当劳 App / 小程序实际券面为准。")
    L.append("-" * W)
    return "\n".join(L)


def result_to_json(result: Dict[str, Any], source: str) -> str:
    def pack(p: Pick) -> Dict[str, Any]:
        return {
            "score": p.score,
            "hit": p.hit,
            "total_price": p.total_price,
            "total_saved": p.total_saved,
            "items": [c.to_dict() for c in p.coupons],
        }
    return json.dumps({
        "budget": result["budget"],
        "craving": result["craving"],
        "keywords": result["keywords"],
        "source": source,
        "singles": [pack(p) for p in result["singles"]],
        "combos": [pack(p) for p in result["combos"]],
        "pool_count": result["pool_count"],
    }, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# 7. CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mai_mai_saver",
        description="麦麦省钱助手 —— 按预算和口味匹配麦当劳优惠券并给出推荐",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python mai_mai_saver.py --budget 20 --craving 汉堡\n"
            "  python mai_mai_saver.py --budget 35 --craving \"汉堡,可乐\"\n"
            "  python mai_mai_saver.py --list\n"
            "  python mai_mai_saver.py            # 交互模式\n\n"
            "接入真实麦当劳 MCP:\n"
            "  set MCD_MCP_URL=https://your-mcd-mcp.example.com/mcp\n"
            "  set MCD_MCP_COMMAND=npx -y @your-scope/mcd-coupon-mcp\n"
        ),
    )
    p.add_argument("-b", "--budget", type=float, help="预算（元）")
    p.add_argument("-c", "--craving", type=str, default="", help="想吃的，多个用逗号分隔")
    p.add_argument("--coupons-file", type=str, default=None, help="本地券库 JSON 路径")
    p.add_argument("--no-mcp", action="store_true", help="跳过 MCP，直接用本地券库")
    p.add_argument("--no-combo", action="store_true", help="只推荐单品，不推荐组合")
    p.add_argument("--top", type=int, default=3, help="每类推荐条数，默认 3")
    p.add_argument("--list", action="store_true", help="列出所有券后退出")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    p.add_argument("-v", "--verbose", action="store_true", help="打印调试信息")
    return p


def cmd_list(args: argparse.Namespace) -> int:
    repo = CouponRepository(use_mcp=not args.no_mcp, coupons_file=args.coupons_file,
                            verbose=args.verbose)
    res = repo.load()
    print(f"券库来源：{res.source}，共 {len(res.coupons)} 张\n")
    rows = [[c.coupon_id, c.title, c.item, f"¥{c.original_price:.2f}",
             f"¥{c.final_price:.2f}", c.channel] for c in res.coupons]
    print("\n".join(render_table(rows, ["券ID", "券名", "商品", "原价", "到手价", "渠道"])))
    return 0


def run_once(budget: float, craving: str, args: argparse.Namespace) -> int:
    if budget <= 0:
        print("预算必须大于 0", file=sys.stderr)
        return 2

    repo = CouponRepository(use_mcp=not args.no_mcp, coupons_file=args.coupons_file,
                            verbose=args.verbose)
    res = repo.load(budget=budget, keywords=parse_craving(craving))
    result = recommend(res.coupons, budget, craving,
                       top_n=max(args.top, 1), allow_combo=not args.no_combo)

    if args.json:
        print(result_to_json(result, res.source))
    else:
        print(render_report(result, res.source))
    return 0


def interactive(args: argparse.Namespace) -> int:
    print("=" * 66)
    print(" 麦麦省钱助手 · 交互模式（直接回车退出）")
    print("=" * 66)
    while True:
        try:
            budget_raw = input("\n预算（元）> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not budget_raw:
            break
        try:
            budget = float(budget_raw.replace("元", "").replace("¥", "").strip())
        except ValueError:
            print("  请输入数字，例如 20")
            continue
        try:
            craving = input("想吃什么（如：汉堡 / 汉堡,可乐）> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        args.budget, args.craving = budget, craving
        run_once(budget, craving, args)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        return cmd_list(args)
    if args.budget is None:
        return interactive(args)
    return run_once(args.budget, args.craving, args)


if __name__ == "__main__":
    raise SystemExit(main())
