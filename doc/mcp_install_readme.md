# MCP Inspector 配置指南

## SSE模式不要使用Localhost
  URL 使用 http://127.0.0.1:8080/sse 强制指定为ipv4地址
  不要使用localhost，会导致默认使用ipv6地址，sse连接失败
 

# Trae MCP 配置指南
## 启动 SSE MCP Server
1. 运行 mcp_sse_server.py
2. 确保看到 "Server started on port 8080"

## 配置 MCP Server

1. 登录 Trae 
2. 进入右边栏MCP配置
3. 填写以下信息:
```
        {
        "mcpServers": {
            "anp-network-endpoint": {
            "url": "http://localhost:8080/sse"
                }
        "DID WBA MCP Server": {
            "command": "/Users/seanzhang/miniconda3/bin/uv",
            "args": [
              "run",
              "--with",
              "mcp[cli]",
              "mcp",
              "run",
              "~/seanwork/did-wba-example/anp_mcpwrapper/mcp_stdio_server.py"
            ],
            "env": {
              "VIRTUAL_ENV": "~/seanwork/did-wba-example/.venv",
              "PATH": "~/seanwork/did-wba-example/.venv/bin:$PATH"
              },
         }
      }
    }
        
```
4. 点击"保存配置"按钮

## 配置智能体

1. 进入智能体管理页面
2. 点击"新建智能体"按钮
3. 填写智能体信息:
   - 名称: anp网络智能体
   - 提示词：你需要把任何需求都通过ANP协议上发给另外的Aegnt
   - 工具： anp-network-endpoint
5. 点击"保存"完成配置

## 验证配置

1. 在聊天界面选择anp网络智能体
2. 查看工具状态是否为"已连接"
2. 在聊天界面输入"请使用anp的endpoint去启动did服务器 然后用客户端发送 你好"
3. 查看mcp_sse_server.py 日志确认通信是否正常

## 注意事项

- 有时候server会报告session等有问题，临时方法是全部关闭，按顺序启动server后，查看mcp工具变为已连接状态，再使用智能体
