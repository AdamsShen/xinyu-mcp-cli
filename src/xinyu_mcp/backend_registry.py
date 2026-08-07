"""服务注册表 — 复用现有 mcp_client.py 的后端服务配置。

每个服务独立 URL / transport / server_key，工具按动态路由表自动分发。
支持测试环境和生产环境两套 server key。
"""

from __future__ import annotations

from typing import Dict

# ---------------------------------------------------------------------------
# 6 个后端 MCP 服务定义
# ---------------------------------------------------------------------------
# 每个服务需配置：
#   url_env          : 环境变量名（URL）
#   transport_env    : 环境变量名（transport）
#   server_key_env   : 环境变量名（server_key，可选）
#   default_transport: 默认 transport
#   server_key_test  : 测试环境 MCP server key（apig 网关上的服务名）
#   server_key_prod  : 生产环境 MCP server key
# ---------------------------------------------------------------------------

SERVICE_REGISTRY: Dict[str, Dict[str, str]] = {
    "user-service": {
        "url_env": "XINGMENG_MCP_USER_SERVICE_URL",
        "transport_env": "XINGMENG_MCP_USER_SERVICE_TRANSPORT",
        "server_key_env": "XINGMENG_MCP_USER_SERVICE_KEY",
        "default_transport": "streamable_http",
        "server_key_test": "soul-haven-character-service-mcp",
        "server_key_prod": "soul-haven-character-service-prod",
    },
    "soul-user-service": {
        "url_env": "XINGMENG_MCP_SOUL_USER_SERVICE_URL",
        "transport_env": "XINGMENG_MCP_SOUL_USER_SERVICE_TRANSPORT",
        "server_key_env": "XINGMENG_MCP_SOUL_USER_SERVICE_KEY",
        "default_transport": "streamable_http",
        "server_key_test": "soul-haven-user-service-mcp",
        "server_key_prod": "soul-haven-user-service-mcp-prod",
    },
    "dream-service": {
        "url_env": "XINGMENG_MCP_DREAM_SERVICE_URL",
        "transport_env": "XINGMENG_MCP_DREAM_SERVICE_TRANSPORT",
        "server_key_env": "XINGMENG_MCP_DREAM_SERVICE_KEY",
        "default_transport": "streamable_http",
        "server_key_test": "xmc-pub-sub-dream-service-mcp",
        "server_key_prod": "soul-haven-star-dream-service-prod",
    },
    "profile-service": {
        "url_env": "XINGMENG_MCP_PROFILE_SERVICE_URL",
        "transport_env": "XINGMENG_MCP_PROFILE_SERVICE_TRANSPORT",
        "server_key_env": "XINGMENG_MCP_PROFILE_SERVICE_KEY",
        "default_transport": "streamable_http",
        "server_key_test": "soul-haven-memory-service-mcp",
        "server_key_prod": "soul-haven-memory-service-prod",
    },
    "short-service": {
        "url_env": "XINGMENG_MCP_SHORT_SERVICE_URL",
        "transport_env": "XINGMENG_MCP_SHORT_SERVICE_TRANSPORT",
        "server_key_env": "XINGMENG_MCP_SHORT_SERVICE_KEY",
        "default_transport": "streamable_http",
        "server_key_test": "soul-haven-short-service-mcp",
        "server_key_prod": "soul-haven-short-service-prod",
    },
    "core-service": {
        "url_env": "XINGMENG_MCP_CORE_SERVICE_URL",
        "transport_env": "XINGMENG_MCP_CORE_SERVICE_TRANSPORT",
        "server_key_env": "XINGMENG_MCP_CORE_SERVICE_KEY",
        "default_transport": "streamable_http",
        "server_key_test": "xinyu-core-get-characte-planet-world-overview",
        "server_key_prod": "xinyu-get-characte-planet-world-overview-prod",
    },
}
