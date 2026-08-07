"""xinyu-mcp CLI — 心屿后端 MCP 聚合命令行工具。

安装后 Claude Code 即可通过自然语言操作后端服务:

    pip install xinyu-mcp-cli
    xinyu-mcp init --endpoint https://xinyu-backend.example.com
    # 重新打开 Claude Code，即可说:
    #   "查一下用户 10001 有哪些角色"

命令:
    init        初始化配置并注册到 Claude Code
    serve       启动 MCP stdio server（由 Claude Code 自动调用）
    list-tools  列出所有可用工具及其描述
    unregister  从 Claude Code 中移除注册
    status      查看当前配置状态
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from .backend_registry import (
    SERVICE_REGISTRY,
)
from .config import (
    is_registered,
    load_config,
    register_to_claude_code,
    resolve_endpoints,
    save_config,
    unregister_from_claude_code,
)
from .mcp_server import fetch_all_tools, run_server

# ---------------------------------------------------------------------------
# 日志：serve 模式写 stderr（避免污染 stdio JSON-RPC），其他模式写 stdout
# ---------------------------------------------------------------------------

LOG_FORMAT = "[%(levelname)s] %(message)s"

_app_typer = typer.Typer(
    name="xinyu-mcp",
    help="心屿后端 MCP 聚合 CLI — 安装后 Claude Code 即可用自然语言操作后端服务",
    add_completion=False,
)


def _setup_logging(*, stderr: bool = False) -> None:
    handler = logging.StreamHandler(sys.stderr if stderr else sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger("xinyu_mcp").handlers.clear()
    logging.getLogger("xinyu_mcp").addHandler(handler)
    level = logging.INFO
    if sys.flags.dev_mode or __debug__:
        level = logging.DEBUG
    logging.getLogger("xinyu_mcp").setLevel(level)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@_app_typer.command()
def init(
    endpoint: Optional[str] = typer.Option(
        None, "--endpoint", "-e",
        help="生产环境 API 网关基础 URL（如 https://apig.yuliyuli.ai）",
    ),
    endpoint_test: Optional[str] = typer.Option(
        None, "--endpoint-test", "-E",
        help="测试环境 API 网关基础 URL（如 https://apig.yuliyuli.ai）",
    ),
    user_service: Optional[str] = typer.Option(
        None, "--user-service",
        help="角色服务 URL（覆盖 --endpoint）",
    ),
    dream_service: Optional[str] = typer.Option(
        None, "--dream-service",
        help="星梦服务 URL（覆盖 --endpoint）",
    ),
    short_service: Optional[str] = typer.Option(
        None, "--short-service",
        help="短期对话服务 URL（覆盖 --endpoint）",
    ),
    soul_user_service: Optional[str] = typer.Option(
        None, "--soul-user-service",
        help="用户基础信息服务 URL（覆盖 --endpoint）",
    ),
    profile_service: Optional[str] = typer.Option(
        None, "--profile-service",
        help="用户画像服务 URL（覆盖 --endpoint）",
    ),
    core_service: Optional[str] = typer.Option(
        None, "--core-service",
        help="星球核心服务 URL（覆盖 --endpoint）",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="强制覆盖已有配置",
    ),
) -> None:
    """初始化 xinyu-mcp 配置并注册到 Claude Code。

    同时配置测试环境和生产环境，Claude Code 中可自然语言切换。

    示例:
        xinyu-mcp init --endpoint https://apig.yuliyuli.ai --endpoint-test https://apig.yuliyuli.ai
        xinyu-mcp init --dream-service https://dream.example.com

    配置保存在 ~/.xinyu-mcp/config.yaml，
    注册条目写入 ~/.claude/.mcp.json。
    """
    _setup_logging()

    # 读取已有配置
    existing = load_config()
    if (existing.get("endpoints") or existing.get("endpoints_test")) and not force:
        typer.echo(
            "⚠️  已有配置，如需覆盖请加 --force。\n"
            f"   当前生产端点: {list(existing.get('endpoints', {}).keys())}\n"
            f"   当前测试端点: {list(existing.get('endpoints_test', {}).keys())}"
        )
        raise typer.Exit(0)

    # 构建端点映射 — 生产环境
    endpoints: dict[str, str] = {}
    svc_mapping = {
        "user-service":       user_service,
        "dream-service":       dream_service,
        "short-service":       short_service,
        "soul-user-service":   soul_user_service,
        "profile-service":     profile_service,
        "core-service":        core_service,
    }
    for svc_name, url in svc_mapping.items():
        if url:
            endpoints[svc_name] = url

    if endpoint:
        for svc_name in SERVICE_REGISTRY:
            if svc_name not in endpoints:
                svc_config = SERVICE_REGISTRY[svc_name]
                server_key = svc_config["server_key_prod"]
                endpoints[svc_name] = endpoint.rstrip("/") + "/mcp-servers/" + server_key

    # 构建端点映射 — 测试环境
    endpoints_test: dict[str, str] = {}
    if endpoint_test:
        for svc_name in SERVICE_REGISTRY:
            svc_config = SERVICE_REGISTRY[svc_name]
            server_key = svc_config["server_key_test"]
            endpoints_test[svc_name] = endpoint_test.rstrip("/") + "/mcp-servers/" + server_key

    if not endpoints and not endpoints_test:
        typer.echo(
            "⛔ 未指定任何端点。请至少传入 --endpoint 或 --endpoint-test。\n"
            "   示例: xinyu-mcp init --endpoint https://apig.yuliyuli.ai --endpoint-test https://apig.yuliyuli.ai",
            err=True,
        )
        raise typer.Exit(1)

    # 写入配置
    cfg = {"endpoints": endpoints, "endpoints_test": endpoints_test}
    path = save_config(cfg)
    typer.echo(f"✅ 配置已保存: {path}")

    if endpoints:
        typer.echo(f"   [生产环境] {len(endpoints)} 个服务")
        for svc_name, url in endpoints.items():
            typer.echo(f"     • {svc_name}: {url}")
    if endpoints_test:
        typer.echo(f"   [测试环境] {len(endpoints_test)} 个服务")
        for svc_name, url in endpoints_test.items():
            typer.echo(f"     • {svc_name}: {url}")

    # 注册到 Claude Code
    newly_registered = register_to_claude_code()
    if newly_registered:
        typer.echo("✅ 已注册到 Claude Code (~/.claude/.mcp.json)")
    else:
        typer.echo("ℹ️  Claude Code 注册条目已存在，跳过")

    typer.echo("")
    typer.echo("🎉 配置完成！重新打开 Claude Code 即可用自然语言操作后端服务。")


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@_app_typer.command()
def serve() -> None:
    """启动 MCP stdio server（由 Claude Code 自动调用，用户无需手动执行）。

    Claude Code 启动时会自动运行 xinyu-mcp serve 作为子进程，
    通过 stdio JSON-RPC 通信。
    """
    _setup_logging(stderr=True)
    asyncio.run(run_server())


# ---------------------------------------------------------------------------
# list-tools
# ---------------------------------------------------------------------------


@_app_typer.command()
def list_tools(
    service: Optional[str] = typer.Option(
        None, "--service", "-s",
        help="仅列出指定服务的工具（user-service/dream-service/...）",
    ),
    env: Optional[str] = typer.Option(
        None, "--env",
        help="仅列出指定环境的工具（test/prod），默认全部",
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j",
        help="以 JSON 格式输出",
    ),
) -> None:
    """列出所有可用工具及其描述（调试用）。

    示例:
        xinyu-mcp list-tools
        xinyu-mcp list-tools --env prod
        xinyu-mcp list-tools --service dream-service --json
    """
    _setup_logging()

    cfg = load_config()

    # 收集要查询的环境
    envs_to_query: list[tuple[str, dict[str, str]]] = []
    if env != "test":
        prod_eps = resolve_endpoints(cfg, env="prod")
        if prod_eps:
            envs_to_query.append(("prod", prod_eps))
    if env != "prod":
        test_eps = resolve_endpoints(cfg, env="test")
        if test_eps:
            envs_to_query.append(("test", test_eps))

    if not envs_to_query:
        typer.echo("⛔ 未配置任何端点，请先执行: xinyu-mcp init --endpoint <URL> --endpoint-test <URL>", err=True)
        raise typer.Exit(1)

    all_tools_by_env: dict[str, list] = {}
    all_routing_by_env: dict[str, dict[str, str]] = {}

    for env_name, eps in envs_to_query:
        filtered_endpoints = eps
        if service:
            if service not in eps:
                typer.echo(f"⛔ [{env_name}] 未知服务: {service}", err=True)
                continue
            filtered_endpoints = {service: eps[service]}

        typer.echo(f"🔍 [{env_name}] 正在从后端拉取工具列表...")
        tools, routing = asyncio.run(fetch_all_tools(filtered_endpoints, env=env_name))
        all_tools_by_env[env_name] = tools
        all_routing_by_env[env_name] = routing

    if json_output:
        tools_data = []
        for env_name, tools in all_tools_by_env.items():
            routing = all_routing_by_env[env_name]
            for t in tools:
                tools_data.append({
                    "name": t.name,
                    "description": t.description,
                    "service": routing.get(t.name, "unknown"),
                    "environment": env_name,
                    "inputSchema": t.inputSchema,
                })
        typer.echo(json.dumps(tools_data, ensure_ascii=False, indent=2))
    else:
        total = sum(len(v) for v in all_tools_by_env.values())
        typer.echo(f"\n共 {total} 个可用工具:\n")

        for env_name in sorted(all_tools_by_env.keys()):
            tools = all_tools_by_env[env_name]
            routing = all_routing_by_env[env_name]
            typer.echo(f"━━━ {env_name} 环境 ({len(tools)} 个工具) ━━━")

            by_service: dict[str, list] = {}
            for t in tools:
                svc = routing.get(t.name, "unknown")
                by_service.setdefault(svc, []).append(t)

            for svc_name in sorted(by_service.keys()):
                svc_tools = by_service[svc_name]
                typer.echo(f"  ── {svc_name} ({len(svc_tools)} 个工具) ──")
                for t in sorted(svc_tools, key=lambda x: x.name):
                    desc = (t.description or "").split("\n")[0][:80]
                    typer.echo(f"    • {t.name}")
                    if desc:
                        typer.echo(f"      {desc}")
            typer.echo("")


# ---------------------------------------------------------------------------
# unregister
# ---------------------------------------------------------------------------


@_app_typer.command()
def unregister() -> None:
    """从 Claude Code 中移除 xinyu MCP server 注册条目。"""
    _setup_logging()

    if not is_registered():
        typer.echo("ℹ️  xinyu 未注册到 Claude Code，无需移除。")
        raise typer.Exit(0)

    unregister_from_claude_code()
    typer.echo("✅ 已从 Claude Code (~/.claude/.mcp.json) 移除 xinyu 注册。")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@_app_typer.command()
def status() -> None:
    """查看当前配置状态。"""
    _setup_logging()

    cfg = load_config()
    prod_endpoints = resolve_endpoints(cfg, env="prod")
    test_endpoints = resolve_endpoints(cfg, env="test")
    registered = is_registered()

    typer.echo("── xinyu-mcp 状态 ──")
    typer.echo(f"  已注册到 Claude Code: {'✅' if registered else '❌'}")
    if prod_endpoints:
        typer.echo(f"  [生产环境] {len(prod_endpoints)} 个服务")
        for svc_name, url in prod_endpoints.items():
            typer.echo(f"    • {svc_name}: {url}")
    else:
        typer.echo(f"  [生产环境] 未配置")
    if test_endpoints:
        typer.echo(f"  [测试环境] {len(test_endpoints)} 个服务")
        for svc_name, url in test_endpoints.items():
            typer.echo(f"    • {svc_name}: {url}")
    else:
        typer.echo(f"  [测试环境] 未配置")
    typer.echo(f"  Claude Code 配置: {Path.home() / '.claude' / '.mcp.json'}")
    typer.echo(f"  xinyu-mcp 配置: {Path.home() / '.xinyu-mcp' / 'config.yaml'}")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

app = _app_typer

if __name__ == "__main__":
    app()
