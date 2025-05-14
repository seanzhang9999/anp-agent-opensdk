# FAQ

## 如何调试 SSE Server?

要调试 SSE Server，可以使用以下 VS Code launch.json 配置，启动时输入 -t sse:
```  {
            "name": "mcp-debug-sse-server",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/anp_mcpwrapper/mcp_stdio_server.py",
            "args": "${command:pickArgs}",
            "console": "integratedTerminal",
            "justMyCode": true,
            "preLaunchTask": "activate-venv"
        },
```
对应 tasks.json 中的 activate-venv 任务。
```    "tasks": [
        {
            "label": "activate-venv",
            "type": "shell",
            "command": "source .venv/bin/activate",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "shared",
                "showReuseMessage": false,
                "clear": false
            },
            "problemMatcher": []
        }
]
```