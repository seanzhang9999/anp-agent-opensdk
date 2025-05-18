# anp agent opensdk

anp agent opensdk 致力于为 Agent 开发者提供一个快速上手、易于集成的 SDK，帮助你自己的智能体快速集成基于 ANP 协议的互联能力，扩展开发者的服务范围。

## 项目目标

- 为 Agent 开发者提供一套开箱即用的 SDK，降低集成门槛。
- 通过自动演示脚本，帮助用户直观了解 SDK 的关键能力和工作流程。
- 提供详细的集成步骤说明，助力开发者将自有 Agent 快速接入 ANP 网络。
- 为智能体提供互联的开箱即用基本能力：
    1. 创建一个DID身份，身份与一个域名绑定，可以将DID文档和描述发布到公网域名，作为基本信任源
    2. 可以与其他 Agent 进行点对点身份认证与互信验证
    3. 可以与其他 Agent 进行点对点post消息/接收对方post消息、发布和调用api
    4. 在无法点对点联系的情况下（例如内网），可以与其他Agent在共同确认的sse公网服务建立“消息群”
    5. sse公网服务可以接收post，sse推送到目标Agent，从而完成Agent间的基本消息传递

## 自动演示脚本

项目内置自动演示脚本，用户启动后可自动体验 SDK 的完整流程，关键步骤会在控制台输出，便于理解各环节：

现在
1. 通过工具自动创建一个did身份，并拥有自己的一个agent目录来放置配置
2. 在自己的agent/代码中加载did身份
2. 启动本地 ANPSDK服务，这是anp帮助agent发布自身DID-doc，发布api，发布消息接收端口的对外交互服务
3. 同一服务可以承载多个agent，自动路由对应消息/api请求
4. 启动了ANPSDK服务的agent，可以互相通过api（get/post）、消息（post）、消息群（post+sse）交流
5. 对于开发者
    可以将自己要提供的对外api通过装饰器或者注册方式发布在ANPSDK服务上
    也可以简单将自己的消息处理函数注册为消息监听/消息群监听的处理器
    也可以随时向任何did用户直接发送消息或在消息群发送消息
未来
1. 向anp的目录服务发布自己的信息
2. 发现其他 Agent 并拉取其描述信息
3. 发起探索与互操作请求
4. 内网和移动场景下，通过anp的sse公网服务与其他智能体交互
5. 简化版ANPSDK，在托管DID-doc的情况下，无需启动http server，只用公网sse对外监听，适用于智能体网络中的从节点

> 启动演示脚本：
>
> ```bash
> python anp_sdk_demo.py -h

    usage: anp_sdk_demo.py [-h] [-p] [-f] [-n name host port host_dir agent_type]

    ANP SDK 演示程序

    options:
    -h, --help            show this help message and exit
    -p                    启用步骤模式，每个步骤都会暂停等待用户确认———适合作为学习与调试
    -f                    快速模式，跳过所有等待用户确认的步骤————适合作为回归测试
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

1. **基于 Agent 核心能力**：在您的智能体项目内引入SDK。
2. **配置 anp agent opensdk**：创建did身份，简单配置sdk。
3. **实现 ANP 服务注册**：参考示例代码，将您的代码注册到 ANP SDK的接口（如身份、发现、认证、探索、互操作等）。
4. **注册与发布 Agent**：通过 SDK 提供的注册接口，将你的 Agent 发布到 ANP 网络。
5. **测试与调试**：使用自动演示脚本或手动调用接口，验证集成效果。

详细集成文档请参考 [doc/architecture](doc/architecture/) 及示例代码。

## 运行过程体验

支持多进程或多主机下的 ANPSDK 互操作体验：

- 各 ANPSDK 可在不同进程或主机上独立运行，通过 ANP 协议交换彼此agent信息。
- 支持身份认证、互信验证，保障通信安全。
- 可发起探索、互操作请求，体验 Agent 开放互联协作。

> 你可以在多台主机分别运行 anp_sdk_demo.py，体验真实网络环境下的 Agent 发现与互操作。

## 目录结构



## 快速开始

1. 克隆项目并安装依赖
2. 配置 .env 文件
3. 运行 anp_sdk_demo.py 体验自动演示
4. 按照集成步骤将 SDK 集成到你的 Agent 项目

## 参考文档

- [ANP 协议规范](https://github.com/agent-network-protocol/AgentNetworkProtocol)
- 示例代码与自动演示脚本

欢迎反馈建议，共同完善 anp agent opensdk！
