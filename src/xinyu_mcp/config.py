"""配置文件管理 — ~/.xinyu-mcp/config.yaml 读写。

同时管理测试环境和生产环境两套端点。
环境变量覆盖的优先级：
  XINGMENG_MCP_*_URL > config.yaml > 默认值（空）
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_DEFAULT_CONFIG_DIR = Path.home() / ".xinyu-mcp"
_DEFAULT_CONFIG_PATH = _DEFAULT_CONFIG_DIR / "config.yaml"
_CC_MCP_JSON_PATH = Path.home() / ".claude" / ".mcp.json"


# ---------------------------------------------------------------------------
# 读取 / 写入 config.yaml
# ---------------------------------------------------------------------------


def _ensure_config_dir() -> Path:
    _DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_CONFIG_DIR


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """读取配置文件，不存在则返回空配置。"""
    target = path or _DEFAULT_CONFIG_PATH
    if not target.exists():
        return _default_config()
    try:
        text = target.read_text(encoding="utf-8")
        cfg = yaml.safe_load(text) or {}
    except Exception:
        return _default_config()
    return _default_config() | cfg


def save_config(cfg: Dict[str, Any], path: Optional[Path] = None) -> Path:
    """写入配置文件。"""
    target = path or _DEFAULT_CONFIG_PATH
    _ensure_config_dir()
    target.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return target


def _default_config() -> Dict[str, Any]:
    return {"endpoints": {}, "endpoints_test": {}}


# ---------------------------------------------------------------------------
# 环境变量覆盖
# ---------------------------------------------------------------------------

_ENV_TO_SERVICE: Dict[str, str] = {
    "XINGMENG_MCP_USER_SERVICE_URL":       "user-service",
    "XINGMENG_MCP_SOUL_USER_SERVICE_URL":   "soul-user-service",
    "XINGMENG_MCP_DREAM_SERVICE_URL":        "dream-service",
    "XINGMENG_MCP_PROFILE_SERVICE_URL":      "profile-service",
    "XINGMENG_MCP_SHORT_SERVICE_URL":        "short-service",
    "XINGMENG_MCP_CORE_SERVICE_URL":         "core-service",
}


def resolve_endpoints(
    cfg: Optional[Dict[str, Any]] = None,
    env: str = "prod",
) -> Dict[str, str]:
    """合并 config.yaml 与环境变量的端点列表，环境变量优先。

    Args:
        cfg: 配置字典
        env: 目标环境 "prod" 或 "test"

    返回 {service_name: url}。
    """
    key = "endpoints" if env == "prod" else "endpoints_test"
    cfg_endpoints: Dict[str, str] = {}
    if cfg and cfg.get(key):
        cfg_endpoints = {k: v for k, v in cfg[key].items() if v}

    # 从环境变量覆盖
    for env_name, service_name in _ENV_TO_SERVICE.items():
        url = os.getenv(env_name, "").strip()
        if url:
            cfg_endpoints[service_name] = url

    return cfg_endpoints


# ---------------------------------------------------------------------------
# Claude Code .mcp.json 注册
# ---------------------------------------------------------------------------

_XINYU_MCP_ENTRY = {
    "xinyu": {
        "command": "xinyu-mcp",
        "args": ["serve"],
    }
}


def _read_cc_mcp_json() -> Dict[str, Any]:
    if not _CC_MCP_JSON_PATH.exists():
        return {}
    try:
        text = _CC_MCP_JSON_PATH.read_text(encoding="utf-8")
        return json.loads(text) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cc_mcp_json(data: Dict[str, Any]) -> None:
    _CC_MCP_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CC_MCP_JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def register_to_claude_code() -> bool:
    """将 xinyu MCP server 注册到 ~/.claude/.mcp.json。

    返回 True 表示本次新增了条目；False 表示已存在无需修改。
    """
    data = _read_cc_mcp_json()
    servers = data.setdefault("mcpServers", {})

    if "xinyu" in servers:
        return False  # 已注册，跳过

    servers["xinyu"] = _XINYU_MCP_ENTRY["xinyu"]
    _write_cc_mcp_json(data)
    return True


def unregister_from_claude_code() -> bool:
    """从 ~/.claude/.mcp.json 中移除 xinyu 注册。"""
    data = _read_cc_mcp_json()
    servers = data.get("mcpServers", {})
    if "xinyu" not in servers:
        return False
    del servers["xinyu"]
    _write_cc_mcp_json(data)
    return True


def is_registered() -> bool:
    """检查 xinyu 是否已注册到 Claude Code。"""
    data = _read_cc_mcp_json()
    return "xinyu" in data.get("mcpServers", {})
