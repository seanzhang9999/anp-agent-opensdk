# anp agent openchat 开放互联智能体网络演示框架

[English Version](README_EN.md)

本项目展示了 anp 开放互联智能体网络的一个实现框架，围绕 anp agent openchat 客户端和 anp agent openchat publisher 发布端，演示了智能体的开放集成、身份机制与互联通信能力。

## 演示目标

1. **任何人**都可以启动 anp agent openchat 客户端，自由探索 anp 网络智能体世界。
2. **任何开发者**都可以快速集成 anp 协议，并通过 anp agent openchat publisher 自主可控地发布智能体。
3. 智能体之间通过 **DID** 确认身份唯一性，可信性可通过开放方式提供：
   当前主要是 DID 发布域名、ad.json 丰富信息
   未来会考虑域名方/组织/社群的 DID 签名背书等方式。

## 演示启动

- **anp agent openchat**：为使用者提供 AI 聊天、发现智能体、与智能体聊天。运行 `web_api.py`，默认启动在 8000 端口。
- **anp agent openchat publisher**：帮助服务者启动和监控本地多个 agent，并公布运行中的 agent 地址。运行 `web_anp_llmagent_launcher.py`，默认启动在 8080 端口。

## 演示功能

### anp agent openchat
1. 从 anp agent openchat publisher 加载智能体书签。
2. 通过本地 AI 智能体基于 anp 协议探索智能体，了解其细节，探索中需验证自身身份。
3. 本地 AI 智能体根据用户需求推荐智能体。
4. 支持 @网络智能体 聊天。
5. 与本地 AI 智能体多轮对话交流。

### anp agent openchat publisher
1. 下拉菜单选择并运行本地智能体。
2. 查看智能体运行状况。
3. 运行中的智能体地址通过 `/api/public/instances` 发布，供 anp agent openchat 获取。

## 安装方法

### 环境准备

1. 克隆项目
2. 创建环境配置文件
   ```
   cp .env.example .env
   ```
3. 编辑 .env 文件，设置必要的配置项

### 使用 Poetry 安装依赖

```bash
# 激活虚拟环境(如果已存在)
source .venv/bin/activate

# 安装依赖
poetry install
```

## 运行方法

本项目支持多种运行方式：

### 1. 启动 anp agent openchat 客户端

```bash
python web_api.py
```
默认监听 8000 端口，提供 Web 聊天与智能体发现。

### 2. 启动 anp agent openchat publisher 发布端

```bash
python web_anp_llmagent_launcher.py
```
默认监听 8080 端口，管理本地 agent 并对外发布。

### 3. 命令行方式调用 ANP 接口，体验交互过程

```bash
python anp_llmapp.py
```

### 4. 通过 stdio/SSE 调用 MCP 接口，体验在MCP客户端的可行性

```bash
# 启动服务端
python -m anp_mcpwrapper.mcp_stdio_server
# 启动客户端
python -m anp_mcpwrapper.mcp_stdio_client
# 或以 SSE 方式启动
python -m anp_mcpwrapper.mcp_stdio_server -t sse
```

**注意**：MCP 相关方法已在 TRAE 环境中测试通过。

## 项目结构

```
.
├── anp_core/            # 封装便于开发者调用的ANP接口
├── anp_mcpwrapper/      # 实现MCP接口的对接
├── api/                 # API路由模块
├── core/                # 应用框架
├── doc/                 # 文档说明和测试用key
├── examples/            # 未来增加面向开发者的更多示例
├── utils/               # 工具函数
├── logs/                # 日志文件
├── setup/               # 后续增加安装方案（当前暂时无用）
├── anp_llmapp.py        # 直接调用ANP接口的应用
├── anp_llmagent.py      # 计划开发为开箱即用的agent
├── web_api.py           # anp agent openchat
└── web_anp_llmagent_launcher.py # anp agent openchat publisher
```

## API端点

Agent API端点
- `GET /agents/example/ad.json`: 获取代理描述信息
- `GET /ad.json`: 获取广告JSON数据，需要鉴权
- `POST /auth/did-wba`: DID WBA首次鉴权
- `GET /auth/verify`: 验证Bearer Token
- `GET /wba/test`: 测试DID WBA认证
- `POST /wba/anp-nlp`: ANP自然语言通信接口
- `GET /wba/user/{user_id}/did.json`: 获取用户DID文档
- `PUT /wba/user/{user_id}/did.json`: 保存用户DID文档
Publisher API端点
- `GET /api/public/instances`: 获取已发布的本地智能体实例（由 publisher 提供）

## 工作流程

### 智能体身份与互信
- 每个智能体拥有唯一 DID，身份可信性可通过开放方式（如域名、ad.json、权威签名、社群背书等）验证。

### 客户端流程
1. 启动 anp agent openchat，加载书签，发现和探索智能体。
2. 通过本地 AI 智能体推荐、探索、与网络智能体聊天。
3. 需要时进行 DID 身份验证。

### 发布端流程
1. 启动 anp agent openchat publisher，选择并运行本地 agent。
2. 实时监控 agent 状态。
3. 通过 `/api/public/instances` 对外发布可用 agent 信息。

## 鉴权说明

本项目实现了两种鉴权方式：

1. **首次DID WBA鉴权**：根据DID WBA规范进行签名验证。
2. **Bearer Token鉴权**：通过JWT令牌进行后续请求鉴权。

详细鉴权流程请参考代码实现和 [DID WBA规范](https://github.com/agent-network-protocol/AgentNetworkProtocol/blob/main/chinese/03-did%3Awba%E6%96%B9%E6%B3%95%E8%A7%84%E8%8C%83.md)

如需进一步了解 anp agent openchat 及其开放互联能力，欢迎参考代码和文档，或直接运行体验。
