# xinyu-mcp-cli 使用手册

## 简介

xinyu-mcp-cli 是心屿后端 MCP 聚合 CLI 工具，将 6 个后端微服务的 MCP 接口聚合为一个统一的 MCP Server。安装后 Claude Code / Cursor / Codex 均可通过自然语言操作角色、星梦、用户等后端数据。

## 安装

### 前置：获取凭证

联系管理员获取云效制品仓库的访问凭证（用户名 + 密码）。

### 方式一：uv tool（推荐，全局隔离安装）

```bash
uv tool install xinyu-mcp-cli \
  --trusted-host yulidev-ap-southeast-1.devops.alibabacloudcs.com \
  -i https://<USERNAME>:<PASSWORD>@yulidev-ap-southeast-1.devops.alibabacloudcs.com/packages/api/protocol/pypi/repo-zplnh
```

### 方式二：pip3

不写版本号默认安装最新版：

```bash
pip3 install --trusted-host yulidev-ap-southeast-1.devops.alibabacloudcs.com \
  -i https://<USERNAME>:<PASSWORD>@yulidev-ap-southeast-1.devops.alibabacloudcs.com/packages/api/protocol/pypi/repo-zplnh \
  xinyu-mcp-cli
```

指定版本：

```bash
pip3 install --trusted-host yulidev-ap-southeast-1.devops.alibabacloudcs.com \
  -i https://<USERNAME>:<PASSWORD>@yulidev-ap-southeast-1.devops.alibabacloudcs.com/packages/api/protocol/pypi/repo-zplnh \
  xinyu-mcp-cli==0.1.4
```

> `pip3 install` 不加版本号即安装最新版，无需 `==latest` 语法。
> 如本地已有旧版本缓存，加 `--upgrade` 可强制更新：`pip3 install --upgrade xinyu-mcp-cli`

### 免密配置（一次性）

将凭证写入 `~/.pip/pip.conf`（macOS/Linux 也兼容 `pip3`），后续安装无需每次输入：

```ini
[global]
index-url = https://<USERNAME>:<PASSWORD>@yulidev-ap-southeast-1.devops.alibabacloudcs.com/packages/api/protocol/pypi/repo-zplnh
trusted-host = yulidev-ap-southeast-1.devops.alibabacloudcs.com
```

配置后直接 `pip3 install xinyu-mcp-cli` 即可。

## 初始化

```bash
# 生产环境
xinyu-mcp init --endpoint https://apig.yuliyuli.ai

# 同时配置生产 + 测试环境
xinyu-mcp init \
  --endpoint https://apig.yuliyuli.ai \
  --endpoint-test https://apig-test.yuliyuli.ai

# 强制覆盖已有配置
xinyu-mcp init --endpoint https://apig.yuliyuli.ai --force
```

执行后自动完成：
1. 写入 `~/.xinyu-mcp/config.yaml`（后端服务地址）
2. 注册到 Claude Code（`~/.claude.json`）
3. 注册到 Cursor（`~/.cursor/mcp.json`）
4. 注册到 Codex（`~/.codex/config.toml`）

## 日常使用

重启 Claude Code / Cursor / Codex 后即可用自然语言操作：

```
"查一下用户 10001 有哪些角色"
"查询角色'安迷修'的星梦库存"
"获取用户和角色的近期 20 轮对话"
"查询当前日计划条目"
"批量查询角色详情：角色ID xxx, yyy"
```

> 生产环境和测试环境的工具会以 `[prod]` / `[test]` 前缀区分，LLM 会根据语境自动选择。

## 命令参考

| 命令 | 说明 |
|------|------|
| `xinyu-mcp init` | 初始化配置并注册 |
| `xinyu-mcp status` | 查看当前配置和注册状态 |
| `xinyu-mcp list-tools` | 列出所有可用工具 |
| `xinyu-mcp list-tools --env prod` | 仅列出生产环境工具 |
| `xinyu-mcp list-tools --service dream-service` | 仅列出星梦服务工具 |
| `xinyu-mcp unregister` | 从三端工具中移除注册 |

## 环境变量（可选）

可通过环境变量覆盖配置文件中的服务 URL：

```bash
export XINGMENG_MCP_USER_SERVICE_URL="https://custom.example.com/mcp"
export XINGMENG_MCP_DREAM_SERVICE_URL="https://custom.example.com/mcp"
export XINGMENG_MCP_SHORT_SERVICE_URL="https://custom.example.com/mcp"
export XINGMENG_MCP_SOUL_USER_SERVICE_URL="https://custom.example.com/mcp"
export XINGMENG_MCP_PROFILE_SERVICE_URL="https://custom.example.com/mcp"
export XINGMENG_MCP_CORE_SERVICE_URL="https://custom.example.com/mcp"
```

环境变量优先级高于 `config.yaml`。

## 后端服务说明

| 服务名 | 说明 | 示例工具 |
|--------|------|----------|
| `user-service` | 角色服务 | characterList、characterDetail、queryUserBondCharacters |
| `dream-service` | 星梦服务 | queryDreamById、queryDailyPlan、batchFetchProductionContext |
| `short-service` | 短期对话 | getAppShortChatMessage |
| `soul-user-service` | 用户信息 | getUserInfo、getUserInfoV2 |
| `profile-service` | 用户画像 | getUserProfile、getUserProfileV2 |
| `core-service` | 星球世界观 | getCharacterPlanetWorldOverview |

## 常见问题

### Q: 安装后 `xinyu-mcp` 命令找不到？

确认安装路径在 PATH 中。使用 `uv tool install` 时命令在 `~/.local/bin/`，确保该目录在 PATH：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Q: 重启工具后还是看不到 xinyu 的工具？

```bash
# 确认注册状态
xinyu-mcp status
# 确认能拉到工具
xinyu-mcp list-tools
```

### Q: 如何只注册到某个特定工具？

目前 init 默认注册到全部三端。如需仅注册到 Claude Code：

```bash
# 先用 init 注册全部
xinyu-mcp init --endpoint https://apig.yuliyuli.ai

# 再单独取消 Cursor 和 Codex
xinyu-mcp unregister --target cursor
xinyu-mcp unregister --target codex
```

### Q: 如何切换工具版本？

```bash
# 升级到最新版
uv tool upgrade xinyu-mcp-cli \
  --trusted-host yulidev-ap-southeast-1.devops.alibabacloudcs.com \
  -i https://<USERNAME>:<PASSWORD>@yulidev-ap-southeast-1.devops.alibabacloudcs.com/packages/api/protocol/pypi/repo-zplnh

# 列出已安装版本
uv tool list | grep xinyu-mcp
```
