# ANP SDK 公网代理模式

本文档介绍如何使用ANP SDK的公网代理模式，使内网的ANP SDK能够对外暴露API和聊天接口。

## 功能概述

ANP SDK的公网代理模式包含两个主要组件：

1. **公网WebSocket转发服务**：部署在公网服务器上，接收来自外部的请求并转发给内网的ANP SDK。
2. **SDK公网代理客户端**：在内网运行的ANP SDK连接到公网WebSocket转发服务，接收并处理来自公网的请求。

通过这种方式，内网的ANP SDK可以对外暴露以下接口：

- **API服务**：通过HTTP接口暴露SDK的API。
- **WebSocket聊天接口**：支持实时双向通信。
- **HTTP POST聊天接口**：支持传统的HTTP请求。
- **HTTP SSE聊天接口**：支持服务器推送事件。

## 部署公网WebSocket转发服务

### 方法一：使用提供的脚本

我们提供了一个简单的脚本来启动公网WebSocket转发服务：

```bash
python examples/start_proxy_server.py --host 0.0.0.0 --port 8000
```

参数说明：
- `--host`：服务器监听的主机地址，默认为`0.0.0.0`（所有网络接口）。
- `--port`：服务器监听的端口，默认为`8000`。
- `--reload`：是否启用热重载，开发时使用。
- `--log-level`：日志级别，可选值为`debug`、`info`、`warning`、`error`、`critical`，默认为`info`。

### 方法二：直接使用uvicorn

如果你熟悉FastAPI和uvicorn，也可以直接使用uvicorn启动服务：

```bash
uvicorn anp_core.proxy.ws_proxy_server:app --host 0.0.0.0 --port 8000
```

### 方法三：在生产环境中部署

在生产环境中，建议使用Nginx、Gunicorn等工具进行部署。以下是一个使用Gunicorn的示例：

```bash
gunicorn anp_core.proxy.ws_proxy_server:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 -w 4
```

## 在SDK中启用公网代理模式

### 方法一：使用提供的示例脚本

我们提供了一个示例脚本来演示如何启用公网代理模式：

```bash
python examples/proxy_mode_example.py --proxy-url ws://your-server:8000/ws/proxy
```

参数说明：
- `--proxy-url`：公网WebSocket转发服务的URL，格式为`ws://host:port/ws/proxy`。
- `--did`：可选，指定使用的DID。
- `--user-dir`：可选，指定用户目录。
- `--port`：可选，指定本地服务器端口，默认为`8080`。

### 方法二：在代码中使用

你也可以在自己的代码中使用公网代理模式：

```python
import asyncio
from anp_open_sdk.anp_sdk import ANPSDK

async def main():
    # 创建ANPSDK实例
    sdk = ANPSDK()
    
    # 启动本地服务器
    sdk.start_server()
    
    # 启动公网代理模式
    await sdk.start_proxy_mode("ws://your-server:8000/ws/proxy")
    
    # 保持程序运行
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
```

## 公网接口说明

启动公网代理模式后，以下接口将在公网可用：

### 1. HTTP消息接口

```
POST /api/message
```

请求体格式：
```json
{
  "req_did": "请求方DID",
  "resp_did": "目标智能体DID",
  "type": "消息类型",
  "content": "消息内容",
  "timestamp": "可选，时间戳"
}
```

### 2. API代理接口

```
POST /api/proxy/{path}
```

请求体格式：
```json
{
  "req_did": "请求方DID",
  "resp_did": "目标智能体DID",
  "api_path": "API路径",
  "method": "请求方法，默认为GET",
  "params": {}
}
```

### 3. SSE连接接口

```
GET /sse/connect/{did}
```

其中`{did}`是目标智能体的DID。

### 4. 管理接口

```
GET /admin/clients          # 获取所有连接的客户端
GET /admin/clients/{did}    # 获取特定客户端信息
```

## 安全注意事项

1. 公网代理模式会将你的API和聊天接口暴露在公网上，请确保添加适当的认证和授权机制。
2. 建议在生产环境中使用HTTPS和WSS协议，以保证通信安全。
3. 可以在Nginx等反向代理服务器中添加IP白名单、访问频率限制等安全措施。
4. 定期检查连接日志，及时发现并处理异常连接。

## 故障排除

1. 如果无法连接到公网WebSocket转发服务，请检查网络连接和防火墙设置。
2. 如果连接成功但无法接收请求，请检查DID是否正确。
3. 如果接收到请求但无法处理，请检查API路径和消息处理器是否正确注册。
4. 查看日志以获取更详细的错误信息。