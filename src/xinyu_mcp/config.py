"""配置文件管理 — ~/.xinyu-mcp/config.yaml 读写。

同时管理 Claude Code / Cursor / Codex 三端的 MCP 注册。
环境变量覆盖的优先级：
  XINGMENG_MCP_*_URL > config.yaml > 默认值（空）
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_DEFAULT_CONFIG_DIR = Path.home() / ".xinyu-mcp"
_DEFAULT_CONFIG_PATH = _DEFAULT_CONFIG_DIR / "config.yaml"

# 三端 MCP 配置文件路径
_CLAUDE_JSON_PATH = Path.home() / ".claude.json"
_CURSOR_MCP_JSON_PATH = Path.home() / ".cursor" / "mcp.json"
_CODEX_CONFIG_TOML_PATH = Path.home() / ".codex" / "config.toml"
# 旧版 Claude Code MCP 配置路径（需清理）
_OLD_CC_MCP_JSON_PATH = Path.home() / ".claude" / ".mcp.json"

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
    return {"endpoints": {}}


# ---------------------------------------------------------------------------
# 环境变量覆盖
# ---------------------------------------------------------------------------

_ENV_TO_SERVICE: Dict[str, str] = {
    "XINGMENG_MCP_USER_SERVICE_URL":      "user-service",
    "XINGMENG_MCP_SOUL_USER_SERVICE_URL": "soul-user-service",
    "XINGMENG_MCP_DREAM_SERVICE_URL":     "dream-service",
    "XINGMENG_MCP_PROFILE_SERVICE_URL":   "profile-service",
    "XINGMENG_MCP_SHORT_SERVICE_URL":     "short-service",
    "XINGMENG_MCP_CORE_SERVICE_URL":      "core-service",
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

    for env_name, service_name in _ENV_TO_SERVICE.items():
        url = os.getenv(env_name, "").strip()
        if url:
            cfg_endpoints[service_name] = url

    return cfg_endpoints


# ---------------------------------------------------------------------------
# 通用 JSON MCP 文件读写（Claude Code / Cursor 共用）
# ---------------------------------------------------------------------------

_XINYU_MCP_ENTRY = {
    "xinyu": {
        "command": "xinyu-mcp",
        "args": ["serve"],
    }
}


def _read_json_mcp(path: Path) -> Dict[str, Any]:
    """读取 { "mcpServers": { ... } } 格式的 JSON 配置文件。"""
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json_mcp(path: Path, data: Dict[str, Any]) -> None:
    """写入 JSON 配置文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _register_to_json_mcp(path: Path) -> bool:
    """通用：将 xinyu 注册到 JSON 格式的 MCP 配置文件。"""
    data = _read_json_mcp(path)
    servers = data.setdefault("mcpServers", {})
    if "xinyu" in servers:
        return False
    servers["xinyu"] = _XINYU_MCP_ENTRY["xinyu"]
    _write_json_mcp(path, data)
    return True


def _unregister_from_json_mcp(path: Path) -> bool:
    """通用：从 JSON 格式的 MCP 配置文件中移除 xinyu。"""
    data = _read_json_mcp(path)
    servers = data.get("mcpServers", {})
    if "xinyu" not in servers:
        return False
    del servers["xinyu"]
    _write_json_mcp(path, data)
    return True


def _is_json_mcp_registered(path: Path) -> bool:
    """检查 xinyu 是否已注册到 JSON 格式的 MCP 配置。"""
    data = _read_json_mcp(path)
    return "xinyu" in data.get("mcpServers", {})


# ---------------------------------------------------------------------------
# Claude Code — ~/.claude.json（根级别 mcpServers）
# ---------------------------------------------------------------------------

def _cleanup_old_cc_mcp_json() -> None:
    """清理旧版 ~/.claude/.mcp.json 中的 xinyu 注册条目。"""
    if _OLD_CC_MCP_JSON_PATH.exists():
        _unregister_from_json_mcp(_OLD_CC_MCP_JSON_PATH)


def register_to_claude_code() -> bool:
    """将 xinyu 注册到 ~/.claude.json（根级别 mcpServers）。"""
    # 先清理旧版配置文件中的条目
    _cleanup_old_cc_mcp_json()
    return _register_to_json_mcp(_CLAUDE_JSON_PATH)


def unregister_from_claude_code() -> bool:
    """从 ~/.claude.json 中移除 xinyu 注册。"""
    result = _unregister_from_json_mcp(_CLAUDE_JSON_PATH)
    _cleanup_old_cc_mcp_json()
    return result


def is_cc_registered() -> bool:
    """检查 xinyu 是否已注册到 Claude Code。"""
    return _is_json_mcp_registered(_CLAUDE_JSON_PATH)


# ---------------------------------------------------------------------------
# Cursor — ~/.cursor/mcp.json
# ---------------------------------------------------------------------------

register_to_cursor = lambda: _register_to_json_mcp(_CURSOR_MCP_JSON_PATH)
unregister_from_cursor = lambda: _unregister_from_json_mcp(_CURSOR_MCP_JSON_PATH)
is_cursor_registered = lambda: _is_json_mcp_registered(_CURSOR_MCP_JSON_PATH)


# ---------------------------------------------------------------------------
# Codex — ~/.codex/config.toml（TOML 格式，文本操作避免额外依赖）
# ---------------------------------------------------------------------------

_CODEX_SECTION_NAME = "[mcp_servers.xinyu]"
_CODEX_SECTION_BODY = """\
[mcp_servers.xinyu]
type = "stdio"
command = "xinyu-mcp"
args = ["serve"]
"""


def register_to_codex() -> bool:
    """将 xinyu 注册到 ~/.codex/config.toml。"""
    if not _CODEX_CONFIG_TOML_PATH.exists():
        return False  # 未安装 Codex，跳过

    text = _CODEX_CONFIG_TOML_PATH.read_text(encoding="utf-8")

    if _CODEX_SECTION_NAME in text:
        return False  # 已注册

    # 确保末尾有换行后追加
    if not text.endswith("\n"):
        text += "\n"
    text += _CODEX_SECTION_BODY

    _CODEX_CONFIG_TOML_PATH.write_text(text, encoding="utf-8")
    return True


def unregister_from_codex() -> bool:
    """从 ~/.codex/config.toml 中移除 xinyu 注册。"""
    if not _CODEX_CONFIG_TOML_PATH.exists():
        return False

    text = _CODEX_CONFIG_TOML_PATH.read_text(encoding="utf-8")

    if _CODEX_SECTION_NAME not in text:
        return False

    # 找到 [mcp_servers.xinyu] 段，移除到下一个 [ 或文件末尾
    lines = text.split("\n")
    start_idx = None
    end_idx = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == _CODEX_SECTION_NAME:
            start_idx = i
        elif start_idx is not None and stripped.startswith("[") and i > start_idx:
            end_idx = i
            break

    if start_idx is None:
        return False

    # 移除该段（含段前空行）
    while start_idx > 0 and lines[start_idx - 1].strip() == "":
        start_idx -= 1

    new_lines = lines[:start_idx] + lines[end_idx:]
    # 去掉末尾多余空行
    while new_lines and new_lines[-1].strip() == "":
        new_lines.pop()
    new_lines.append("")  # 文件末尾一个换行

    _CODEX_CONFIG_TOML_PATH.write_text("\n".join(new_lines), encoding="utf-8")
    return True


def is_codex_registered() -> bool:
    """检查 xinyu 是否已注册到 Codex。"""
    if not _CODEX_CONFIG_TOML_PATH.exists():
        return False
    return _CODEX_SECTION_NAME in _CODEX_CONFIG_TOML_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 三端批量操作
# ---------------------------------------------------------------------------

TARGETS = {
    "cc":     ("Claude Code", register_to_claude_code, unregister_from_claude_code, is_cc_registered),
    "cursor": ("Cursor",      register_to_cursor,       unregister_from_cursor,       is_cursor_registered),
    "codex":  ("Codex",       register_to_codex,        unregister_from_codex,        is_codex_registered),
}


def register_to_targets(targets: list[str]) -> Dict[str, bool]:
    """向指定工具注册 xinyu MCP server。

    Args:
        targets: 目标工具列表，如 ["cc", "cursor", "codex"]

    Returns:
        {target: 是否新增}
    """
    results: Dict[str, bool] = {}
    for t in targets:
        if t in TARGETS:
            _, register_fn, _, _ = TARGETS[t]
            results[t] = register_fn()
    return results


def unregister_from_targets(targets: list[str]) -> Dict[str, bool]:
    """从指定工具移除 xinyu MCP 注册。"""
    results: Dict[str, bool] = {}
    for t in targets:
        if t in TARGETS:
            _, _, unregister_fn, _ = TARGETS[t]
            results[t] = unregister_fn()
    return results


def is_registered(target: str) -> bool:
    """检查 xinyu 是否已注册到指定工具。"""
    if target in TARGETS:
        _, _, _, check_fn = TARGETS[target]
        return check_fn()
    return False
