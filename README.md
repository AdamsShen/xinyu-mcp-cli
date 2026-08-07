# xinyu-mcp-cli

心屿后端 MCP 聚合 CLI — 将 6 个心屿后端微服务的 MCP 接口聚合成一个统一的 MCP Server，安装后 Claude Code 即可通过自然语言操作角色/星梦/用户等后端服务。

## 安装

```bash
pip install xinyu-mcp-cli
```

## 快速开始

```bash
# 初始化配置并注册到 Claude Code
xinyu-mcp init --endpoint https://backend.example.com

# 如需写操作权限
xinyu-mcp init --endpoint https://backend.example.com --mode full --force

# 查看状态
xinyu-mcp status

# 列出所有可用工具
xinyu-mcp list-tools
```

## 命令

| 命令 | 说明 |
|------|------|
| `init` | 初始化配置并注册到 Claude Code |
| `serve` | 启动 MCP stdio server（由 Claude Code 自动调用） |
| `list-tools` | 列出所有可用工具及其描述 |
| `unregister` | 从 Claude Code 中移除注册 |
| `status` | 查看当前配置状态 |

## 架构

```
Claude Code (stdio JSON-RPC)
    ↕
xinyu-mcp-cli (聚合代理层)
    ↕ streamable_http (JSON-RPC)
┌────────┬────────┬────────┬────────┬────────┬────────┐
│  user  │ dream  │ short  │ soul-  │profile │ core   │
│service │service │service │  user  │service │service │
└────────┴────────┴────────┴────────┴────────┴────────┘
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `XINGMENG_MCP_USER_SERVICE_URL` | 角色服务 URL |
| `XINGMENG_MCP_DREAM_SERVICE_URL` | 星梦服务 URL |
| `XINGMENG_MCP_SHORT_SERVICE_URL` | 短期对话服务 URL |
| `XINGMENG_MCP_SOUL_USER_SERVICE_URL` | 用户基础信息服务 URL |
| `XINGMENG_MCP_PROFILE_SERVICE_URL` | 用户画像服务 URL |
| `XINGMENG_MCP_CORE_SERVICE_URL` | 星球核心服务 URL |
