"""MCP stdio server 核心 — 聚合测试+生产两套后端 MCP 服务并代理给 Claude Code。

架构:
  Claude Code (stdio JSON-RPC)
    → _handle_list_tools()  → 聚合两套环境后端的 tool schema（缓存）
    → _handle_call_tool()   → 按环境前缀+动态路由表转发到对应后端，返回结果

工具名格式: [prod] toolName / [test] toolName
LLM 根据用户自然语言选择对应环境的工具，用户未指明环境时倾向于询问。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool,
)

from .config import load_config, resolve_endpoints

logger = logging.getLogger("xinyu_mcp.server")

# ---------------------------------------------------------------------------
# 后端通信 — JSON-RPC over streamable_http
# ---------------------------------------------------------------------------

JSONRPC_VERSION = "2.0"
_SEQ = 0

# 工具名环境前缀: [prod] / [test]
_ENV_PREFIX_RE = re.compile(r"^\[(prod|test)\]\s*")


def _add_env_prefix(tool_name: str, env: str) -> str:
    """给工具名加环境前缀。"""
    return f"[{env}] {tool_name}"


def _strip_env_prefix(tool_name: str) -> Tuple[str, str]:
    """从工具名中分离环境前缀，返回 (原工具名, 环境)。

    无前缀时返回 (原工具名, "")。
    """
    m = _ENV_PREFIX_RE.match(tool_name)
    if m:
        return tool_name[m.end():], m.group(1)
    return tool_name, ""


def _next_id() -> int:
    global _SEQ
    _SEQ += 1
    return _SEQ


async def _jsonrpc_call(
    url: str,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Any:
    """对单个后端 MCP Server 发送 JSON-RPC 请求。"""
    payload = {
        "jsonrpc": JSONRPC_VERSION,
        "id": _next_id(),
        "method": method,
        "params": params or {},
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        resp.raise_for_status()
        body = resp.json()

    if not isinstance(body, dict):
        raise RuntimeError(f"后端响应非 JSON 对象: {type(body)}")

    if body.get("error"):
        err = body["error"]
        raise RuntimeError(
            f"后端 JSON-RPC 错误 [code={err.get('code')}]: {err.get('message', err)}"
        )

    return body.get("result")


# ---------------------------------------------------------------------------
# 工具 schema 拉取 + 动态路由表构建
# ---------------------------------------------------------------------------


async def fetch_backend_tools(
    url: str,
    service_name: str,
    env: str,
) -> Tuple[List[Tool], Dict[str, str]]:
    """从单个后端拉取 tools/list，返回 (工具列表, {带前缀工具名: 服务名} 路由映射)。"""
    result = await _jsonrpc_call(url, "tools/list")
    tools_raw: List[Dict[str, Any]] = []

    if isinstance(result, dict) and "tools" in result:
        tools_raw = result["tools"]
    elif isinstance(result, list):
        tools_raw = result

    tools: List[Tool] = []
    routing: Dict[str, str] = {}
    for t in tools_raw:
        if not isinstance(t, dict):
            continue
        name = t.get("name", "")
        if not name:
            continue

        prefixed_name = _add_env_prefix(name, env)
        tools.append(
            Tool(
                name=prefixed_name,
                description=str(t.get("description", "") or ""),
                inputSchema=t.get("inputSchema", {}),
            )
        )
        routing[prefixed_name] = service_name

    return tools, routing


async def fetch_all_tools(
    endpoints: Dict[str, str],
    env: str = "prod",
) -> Tuple[List[Tool], Dict[str, str]]:
    """并行拉取所有后端服务的工具列表，返回 (聚合工具列表, 动态路由表)。

    路由表将每个带前缀工具名映射到其来源服务名，用于 tools/call 转发。
    """
    tasks = []
    for svc_name, url in endpoints.items():
        tasks.append(fetch_backend_tools(url, svc_name, env))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_tools: List[Tool] = []
    all_routing: Dict[str, str] = {}
    for svc_name, result in zip(endpoints.keys(), results):
        if isinstance(result, Exception):
            logger.warning("拉取工具失败 [%s @ %s]: %s", svc_name, env, result)
        else:
            tools, routing = result
            all_tools.extend(tools)
            all_routing.update(routing)
            logger.info(
                "服务 [%s @ %s] 拉取到 %d 个工具", svc_name, env, len(tools)
            )

    return all_tools, all_routing


# ---------------------------------------------------------------------------
# 工具调用转发
# ---------------------------------------------------------------------------


async def call_backend_tool(
    url: str,
    tool_name: str,  # 已去除环境前缀的原始工具名
    arguments: Dict[str, Any],
    timeout: float = 60.0,
) -> str:
    """调用后端单个工具并返回文本结果。"""
    result = await _jsonrpc_call(
        url,
        "tools/call",
        {"name": tool_name, "arguments": arguments},
        timeout=timeout,
    )
    return _coerce_result(result)


def _coerce_result(result: Any) -> str:
    """将 MCP 工具调用结果统一转为字符串。"""
    # MCP content list: [{"type": "text", "text": "..."}]
    if isinstance(result, dict) and "content" in result:
        content = result["content"]
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(str(item.get("text", "")))
            return "\n".join(texts)
        return str(content)

    # 直接是 JSON 可序列化对象
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)


# ---------------------------------------------------------------------------
# 工具描述增强
# ---------------------------------------------------------------------------


# 原始工具名 → 中文描述（不含环境前缀）
_TOOL_DESCRIPTIONS: Dict[str, str] = {
    # 角色服务
    "characterList": "查询角色列表 — 获取用户的全量角色信息（名称/性别/羁绊等级）",
    "characterDetail": "查询角色详情 — 获取单个角色的人设/性格/对话样本/羁绊关系",
    "queryBondLevelConfig": "查询羁绊等级配置 — 获取各关系等级的命名（如 Lv1=初识/Lv5=灵魂羁绊）",
    "queryUpgradeRoles": "查询升级待处理角色 — 获取当前存档中最近关系等级提升的角色列表",
    "queryUserBondCharacters": "查询用户羁绊角色 — 获取用户与所有角色的羁绊等级映射",
    "queryLightRoleRelationCards": "查询点亮羁绊关系 — 获取主角色的羁绊关系文本",
    "queryLightRoleRelationSupportingRoleIds": "查询点亮羁绊配角 — 获取已点亮关系的配角 ID 列表",
    "queryMainSupportingRoleRelationText": "查询主配角关系 — 获取两角色间的关系理解文本",
    "batchQueryCharacterDetail": "批量查询角色详情 — 批量获取多个角色的人设和羁绊关系",
    "resetUpgradeFlags": "重置升级标记 — 批量重置升级待处理标记为 false",
    # 星梦服务
    "queryDreamInventory": "查询星梦库存 — 获取某角色的历史星梦内容列表",
    "queryDreamById": "按 ID 查询星梦 — 获取单条星梦的完整详情",
    "queryFirstEncounter": "查询初遇库存 — 从初遇库存中取一条星梦",
    "queryFirstEncounterRemaining": "查询初遇库存剩余 — 获取某角色/窗口的初遇库存剩余数量",
    "queryDailyPlan": "查询日计划 — 获取当前存档下未消耗的日计划条目",
    "queryOldDailyPlan": "查询历史日计划 — 获取上批次日计划全量数据（含已消耗）",
    "queryDreamsNeedingSupplement": "查询缺星事的星梦 — 获取需补充星事钩子的星梦列表",
    "batchQueryFirstEncounterRemaining": "批量查询初遇库存剩余 — 批量查询多个角色/窗口的初遇库存剩余",
    "batchQueryDreamById": "批量查询星梦详情 — 批量查询多条星梦的完整内容",
    "batchFetchProductionContext": "批量拉取生产上下文 — 聚合获取人设/羁绊/对话/库存等完整上下文，用于 AI 生产星梦",
    "batchWriteDailyPlan": "批量写入日计划 — 将初遇库存星梦写入日计划表",
    "writeRewrittenDreamsBatch": "批量改写星梦 — 更新改写后的星梦标题/场景/开场白/星事",
    "writeProducedDreamsBatch": "批量写入生产星梦 — AI 新生产的星梦+星事落库",
    "writeStarEvent": "写入星事 — 为指定星梦补充新的星事钩子",
    "softDeleteConsumedDailyPlan": "软删已消费日计划 — 清理已曝光/已游玩的旧日计划条目",
    "softDeleteOnsiteDreams": "软删现场生成日计划 — 清理现场生成的日计划条目",
    # 用户服务
    "getUserInfo": "查询用户信息 — 获取用户昵称/性别/MBTI 等基础信息",
    "getUserInfoV2": "查询用户信息 V2 — 同 getUserInfo，使用字符串 ID 避免精度丢失",
    "getUserProfile": "查询用户画像 — 获取用户与某角色的关系画像",
    "getUserProfileV2": "查询用户画像 V2 — 同 getUserProfile，使用字符串 ID",
    # 对话服务
    "getAppShortChatMessage": "查询近期对话 — 获取用户与角色的最近 N 轮聊天记录",
    # 星球服务
    "getCharacterPlanetWorldOverview": "查询星球世界观 — 获取角色所属星球的全量地点列表",
}


def _normalize_tool_schema_for_llm(tool: Tool) -> Tool:
    """优化 tool 描述使其更易被 LLM 理解。

    1. 为已知工具补充中文描述
    2. 在描述末尾追加环境标识，帮助 LLM 区分测试/生产
    """
    # 分离环境前缀和原始工具名
    raw_name, env = _strip_env_prefix(tool.name)

    # 中文描述
    new_desc = _TOOL_DESCRIPTIONS.get(raw_name, tool.description or "")
    if not any("一" <= ch <= "鿿" for ch in new_desc):
        new_desc = tool.description or ""

    # 追加环境标识
    if env:
        env_label = "【生产环境】" if env == "prod" else "【测试环境】"
        if new_desc:
            new_desc = f"{new_desc} {env_label}"
        else:
            new_desc = env_label

    # Async 变体复用同步版本描述
    if not _TOOL_DESCRIPTIONS.get(raw_name) and raw_name.endswith("Async"):
        sync_name = raw_name[:-5]
        sync_desc = _TOOL_DESCRIPTIONS.get(sync_name)
        if sync_desc:
            env_label = "【生产环境】" if env == "prod" else "【测试环境】"
            new_desc = f"{sync_desc}（异步） {env_label}"

    return Tool(
        name=tool.name,
        description=new_desc,
        inputSchema=tool.inputSchema,
    )


# ---------------------------------------------------------------------------
# MCP stdio server
# ---------------------------------------------------------------------------


def _build_server(
    prod_endpoints: Dict[str, str],
    test_endpoints: Dict[str, str],
    *,
    tool_cache_ttl: int = 300,
) -> Server:
    """构建 MCP Server 实例。

    Args:
        prod_endpoints: {service_name: url} 生产环境
        test_endpoints: {service_name: url} 测试环境（可为空）
        tool_cache_ttl: 工具列表缓存秒数（默认 5 分钟），0 表示不缓存
    """
    server = Server("xinyu-mcp")

    # 缓存状态
    _tool_cache: List[Tool] = []
    _routing: Dict[str, str] = {}  # 动态路由表: 带前缀工具名 → service_name
    _cache_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # tools/list 处理器 — 合并两套环境工具
    # ------------------------------------------------------------------

    @server.list_tools()
    async def handle_list_tools() -> List[Tool]:
        nonlocal _tool_cache, _routing

        if _tool_cache and tool_cache_ttl > 0:
            logger.info("从缓存返回 %d 个工具", len(_tool_cache))
            return _tool_cache

        async with _cache_lock:
            logger.info("正在从后端拉取工具列表（生产+测试）...")
            all_tools: List[Tool] = []
            all_routing: Dict[str, str] = {}

            # 拉取生产环境
            if prod_endpoints:
                tools, routing = await fetch_all_tools(prod_endpoints, env="prod")
                all_tools.extend(tools)
                all_routing.update(routing)

            # 拉取测试环境
            if test_endpoints:
                tools, routing = await fetch_all_tools(test_endpoints, env="test")
                all_tools.extend(tools)
                all_routing.update(routing)

            _tool_cache = [_normalize_tool_schema_for_llm(t) for t in all_tools]
            _routing = all_routing
            logger.info("聚合完成: 共 %d 个工具（prod=%d, test=%d）",
                        len(_tool_cache),
                        sum(1 for t in _tool_cache if _strip_env_prefix(t.name)[1] == "prod"),
                        sum(1 for t in _tool_cache if _strip_env_prefix(t.name)[1] == "test"))
            return _tool_cache

    # ------------------------------------------------------------------
    # tools/call 处理器
    # ------------------------------------------------------------------

    @server.call_tool()
    async def handle_call_tool(
        name: str,
        arguments: Dict[str, Any],
    ) -> List[TextContent]:
        # 分离环境前缀获取原始工具名
        raw_name, env = _strip_env_prefix(name)

        # 查动态路由表确定目标服务
        svc = _routing.get(name)
        if svc is None:
            return [
                TextContent(
                    type="text",
                    text=f"未知工具: {name}。可用工具列表请通过 xinyu-mcp list-tools 查看。",
                )
            ]

        # 确定端点
        if env == "test" and test_endpoints:
            url = test_endpoints.get(svc)
        else:
            url = prod_endpoints.get(svc)

        if url is None:
            return [
                TextContent(
                    type="text",
                    text=f"服务 {svc} 未配置端点（工具: {name}）。"
                    f"请检查 `xinyu-mcp init` 配置。",
                )
            ]

        logger.info("转发工具调用 [%s] → %s @ %s, args=%s", name, svc, env or "prod", arguments)

        try:
            result_text = await call_backend_tool(url, raw_name, arguments)
            return [TextContent(type="text", text=result_text)]
        except Exception as e:
            logger.error("工具调用失败 [%s @ %s]: %s", name, svc, e)
            return [
                TextContent(
                    type="text",
                    text=f"工具调用失败 [{name} @ {svc}]: {e}",
                )
            ]

    # ------------------------------------------------------------------
    # MCP SDK 要求的 handler
    # ------------------------------------------------------------------

    @server.list_resource_templates()
    async def handle_list_resource_templates():
        return []

    return server


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------


async def run_server() -> None:
    """启动 MCP stdio server（由 Claude Code 自动调用）。"""
    cfg = load_config()
    prod_endpoints = resolve_endpoints(cfg, env="prod")
    test_endpoints = resolve_endpoints(cfg, env="test")

    if not prod_endpoints and not test_endpoints:
        logger.error(
            "未配置任何后端端点。请先执行: xinyu-mcp init --endpoint <URL>"
        )
        sys.exit(1)

    logger.info("xinyu-mcp 启动: prod=%d, test=%d",
                len(prod_endpoints), len(test_endpoints))

    server = _build_server(prod_endpoints, test_endpoints)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
