# anp agent opensdk

anp agent opensdk 致力于为 Agent 开发者提供一个快速上手、易于集成的 SDK，帮助你高效开发、集成和体验基于 ANP 协议的智能体。

## 项目目标

- 为 Agent 开发者提供一套开箱即用的 SDK，降低集成门槛。
- 通过自动演示脚本，帮助用户直观了解 SDK 的关键能力和工作流程。
- 提供详细的集成步骤说明，助力开发者将自有 Agent 快速接入 ANP 网络。
- 支持多进程/多主机下 Agent 的发现、认证、探索与互操作体验。

## 自动演示脚本

项目内置自动演示脚本，用户启动后可自动体验 SDK 的完整流程，关键步骤会在控制台输出，便于理解各环节：

1. 启动本地 Agent 并注册到 ANP 网络
2. 发现其他 Agent 并拉取其描述信息
3. 进行身份认证与互信验证
4. 发起探索与互操作请求

> 启动演示脚本：
>
> ```bash
> python anp_sdk_demo.py -h

    usage: anp_sdk_demo.py [-h] [-p] [-f] [-u name host port host_dir agent_type]

    ANP SDK 演示程序

    options:
    -h, --help            show this help message and exit
    -p                    启用步骤模式，每个步骤都会暂停等待用户确认
    -f                    快速模式，跳过所有等待用户确认的步骤
    -n name host port host_dir agent_type
                            创建新用户，需要提供：用户名 主机名 端口号 主机路径 用户类型
> ```
>
python anp_sdk_demo.py -n cool_anper localhost 9527 wba user
创建一个名为cool_anper的用户，主机名为localhost，端口号为9527，主机路径为wba，用户类型为user
其地址为did:wba:localhost%3A9527%3A:wba:user:8位随机数
python anp_sdk_demo.py -n cool_anp_agent localhost 9527 wba agent
创建一个名为cool_anp_agent的用户，主机名为localhost，端口号为9527，主机路径为wba，用户类型为agent
其地址为did:wba:localhost%3A9527%3A:wba:agent:unique_id（8位随机数）
did及其他信息存储在 /anp_open_sdk/anp_users/user_unique_id/目录下
agent类型会额外创建一个/anp_open_sdk/anp_users/user_unique_id/agent目录,用于配合开发者进行agent的各种配置
重复用户名会创建为用户名+日期+当日序号




## Agent 集成步骤说明

1. **实现 Agent 核心能力**：开发你的智能体核心逻辑。
2. **引入 anp agent opensdk**：将本 SDK 集成到你的项目中。
3. **实现 ANP 协议适配**：参考示例代码，实现 ANP 协议接口（如身份、发现、认证、探索、互操作等）。
4. **注册与发布 Agent**：通过 SDK 提供的注册接口，将你的 Agent 发布到 ANP 网络。
5. **测试与调试**：使用自动演示脚本或手动调用接口，验证集成效果。

详细集成文档请参考 [doc/architecture](doc/architecture/) 及示例代码。

## 运行过程体验

支持多进程或多主机下的 Agent 互操作体验：

- 各 Agent 可在不同进程或主机上独立运行，通过 ANP 协议自动发现彼此。
- 支持身份认证、互信验证，保障通信安全。
- 可发起探索、互操作请求，体验跨 Agent 协作。

> 你可以在多台主机分别运行 demo_autorun.py，体验真实网络环境下的 Agent 发现与互操作。

## 目录结构

```
.
├── anp_core/            # ANP 协议核心接口
├── anp_mcpwrapper/      # MCP 协议适配
├── api/                 # API 路由模块
├── core/                # 应用框架
├── doc/                 # 文档与示例
├── examples/            # 集成示例
├── utils/               # 工具函数
├── logs/                # 日志
├── demo_autorun.py      # 自动演示脚本
├── ...
```

## 快速开始

1. 克隆项目并安装依赖
2. 配置 .env 文件
3. 运行 demo_autorun.py 体验自动演示
4. 按照集成步骤将 SDK 集成到你的 Agent 项目

## 参考文档

- [ANP 协议规范](https://github.com/agent-network-protocol/AgentNetworkProtocol)
- 示例代码与自动演示脚本

欢迎反馈建议，共同完善 anp agent opensdk！
