# anp agent opensdk

anp agent opensdk是基于ANP核心协议栈agent_connect开发的一个anp快速集成开发工具包

## 开发背景

- ANP协议基于DID建立身份认证，涉及到密钥文件的生成、DID文档的组织和管理，但是一般开发者对此相对陌生。
- ANP协议的DID文档基于域名发布，DID标识符指引认证者向特定url获取DID文档，DID发布需要运行服务器。
- ANP协议的DID认证目前基于FastAPI框架的路由和中间件机制，对开发者也有一定学习成本。
- ANP协议的认证完全是点对点完成，中间涉及首次DID认证以及后续Token颁发存储，需要开发者理解DID的工作原理和相关的安全性问题。
- ANP协议现有web版demo，是一个公共的DID身份，提升了用户快速感知的体验，但是对开发者后续开发，密钥身份问题还是需要了解和处理。

## 项目目标

- 简化对智能体开发者使用ANP协议的WBA-DID认证的开发流程，降低开发复杂度

  - 一个函数直接创建anp用户密钥文件夹和相关DID文档，DID标识符格式符合ANP协议要求，开发者熟悉后可以自己修改
  - 拥有密钥文件夹后，import SDK，一行代码创建LocalAgent（ANP的网络连接实例）
- 提供开发者本地快速测试环境，支持快速迭代和调试多智能体互操作

  - LocalAgent可以调用其他agent的api，向其他agent发送消息，请求中自动进行DID认证，开发者无需操作
  - LocalAgent可以注册到SDK的FastAPI服务上，支持多个LocalAgent并存
    - 对外发布自身DID文档、智能体描述json文件
    - FastAPI服务为注册LocalAgent默认提供接收其他agent发送消息的消息监听接口，开发者可以直接注册处理函数
    - LocalAgent可以通过装饰器、函数注册将本地API一行代码转换为Agent的API，自动发布到FastAPI服务，方便其他agent调用
    - 所有调用事件均传入调用者DID，并且已经进行过验证，开发者可以自由定制对不同调用者DID的权限控制
- 为几种DID使用场景提供解决方案和示例代码

  - 用户自动绑定模式：
    - 如果开发者给用户提供服务时，希望让用户访问anp服务，但是又不想麻烦用户了解DID，可以利用SDK自动给用户创建身份，自动发布DID文档到FastAPI服务，并将用户的DID与其服务进行绑定，访问ANP其他agent获取服务
  - 内网公共服务器发布DID文档模式：
    - 如果开发者给企业开发时，希望所有DID文档发布在一个公共服务器，但是agent运行在不同笔记本/桌面电脑，可以利用SDK的hosted DID模式，将本地agent的DID文档自动邮件提交给公共服务器管理员，公共服务器进行审核和发布，并将最终公共服务器host的DID文档发还本地agent，此后本地agent可以使用这个DID文档自由访问其他agent
  - ANPTool模式：
    - ANP的特色能力，通过大模型自动连接分析其他anp agent提供的ad.json及链接的url，自动调用其中描述的api，完成用户功能
  - GroupRunner模式：
    - 不同网络的agent可以在一个公共服务器上加入一个Group，通过SSE监听响应消息，消息处理成员管理功能由创建者管理的GroupRunner具体执行，GroupRunner可以继承扩展，自定义各种额外行为，方便跨网agent尽可能安全的互相连接，在GroupRunner中，成员可以通过DID进行身份验证，确保消息的安全性和隐私性。

## 核心功能

1. DID 身份管理
   创建去中心化身份（DID）
   DID 与域名绑定
   DID 文档发布和管理
   支持托管 DID 模式
2. 智能体通信
   点对点消息：智能体间直接消息传递
   API 调用：RESTful API 的发布和调用
   群组通信：基于 SSE 的群组消息功能
   双向认证：安全的身份验证机制，当前支持三种模式兼容：
   请求者提交DID认证，响应者验证，不返回token（一次一验）
   请求者提交DID认证，响应者验证，返回token（方便后续访问）
   请求者提交DID认证，响应者验证后，返回token，并返回自己DID认证（双向认证）
3. 服务发现与互操作
   智能体可信信息发布（ad.json/yaml/did文档接口，可以自定义）
   智能爬虫功能（anp_tool）
   智能体发现（提供了查询接口，可以自定义）

## 快速运行演示

1. 克隆项目
2. python创建venv环境，并进入venv环境
3. 使用poetry安装依赖
4. python anp_demo_main.py
   python anp_demo_main.py [-h] [-d] [-s] [-f] [--domain DOMAIN]
   参数说明：
   -h, --help       显示帮助信息
   -d               开发测试模式（默认）- 包含详细日志输出
   -s               步骤执行模式 - 每个步骤暂停等待确认，适合学习
   -f               快速执行模式 - 跳过所有暂停，适合自动化测试

## 主要演示内容

1. API 调用演示 (run_api_demo)
   展示智能体间的 API 调用功能
   演示 POST/GET 请求到其他智能体的接口
   显示智能体的 ad.json 信息
2. 消息传递演示 (run_message_demo)
   演示点对点消息发送
   展示消息自动回复功能
   多个智能体间的消息交互
3. 智能体生命周期演示 (run_agent_lifecycle_demo)
   动态创建临时智能体
   注册消息处理器
   智能体间消息交互
   智能体的注销和清理
4. ANP 工具爬虫演示 (run_anp_tool_crawler_agent_search_ai_ad_jason)
   使用 ANP 协议进行智能体信息爬取
   智能爬虫自主决定爬取路径
   支持双向认证的安全爬取
   集成 AI 模型进行智能分析和决策
5. 托管 DID 演示 (run_hosted_did_demo)
   申请托管 DID
   查询托管状态
   托管智能体与普通智能体的消息交互
   托管智能体之间的通信
6. 群组聊天演示 (run_group_chat_demo)
   创建和加入群组
   群组消息广播
   审核群聊功能（消息过滤）
   群组成员管理
   消息存储和统计功能

## 演示模式

开发模式（-d）：适合开发调试，包含详细的日志输出
步骤模式（-s）：每个演示步骤都会暂停，适合学习和理解
快速模式（-f）：跳过所有暂停，适合自动化测试

## 🔧 集成指南

  基础集成步骤

1. 创建 DID 身份

   ```python
   1. from anp_open_sdk.anp_sdk_tool import did_create_user

     params = {
         'name': 'MyAgent',
         'host': 'localhost',
         'port': 9527,
         'dir': 'wba',
         'type': 'agent'
     }
     did_document = did_create_user(params)

   ```
2. 初始化 SDK

```python
  from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent

  sdk = ANPSDK(host="localhost", port=9527)
  agent = LocalAgent(sdk, did_document['id'])
  sdk.register_agent(agent)
```

3. 注册消息处理器
   ```python
   @agent.register_message_handler("*")
     def handle_message(msg):
         print(f"收到消息: {msg}")
         return {"reply": "消息已收到"}
   ```

```
  
3. 注册 API 端点
   ```python
  @agent.register_api_handler("/info", methods=["GET", "POST"])
  async def handle_info(request):
      return {"name": agent.name, "status": "online"}
```

4、 启动服务

```python
  sdk.start_server()
```

## 🏗️ 架构说明
```
  anp-agent-opensdk/
  ├── anp_open_sdk/          # SDK 核心代码
  │   ├── anp_sdk.py         # 主 SDK 类
  │   ├── anp_sdk_agent.py   # 智能体实现
  │   ├── anp_users_hosted/  # 作为托管服务器托管的DID文档
  │   ├── auth/              # 认证相关模块
  │   ├── config             # 配置相关模块/
  │   ├── auth/              # 认证相关模块
  │   └── service/           # 服务模块
  ├── anp_sdk_demo/          # 演示相关代码
  │   ├── demo_modules/      # 演示模块
  │   └── services/          # 演示服务
  ├── anp_demo_main.py       # 综合演示程序
  └── docs/                  # 文档
```
# 📄 许可证

  本项目采用 Apache License 2.0 进行授权，详情请查看 LICENSE 文件。

# 🔍 常见问题

  Q: 如何在内网环境使用？
  A: 1. 如果内网内使用，参见  - 内网公共服务器发布DID文档模式：
     2. 如果希望跨内网使用，参见  - GroupRunner模式：
     3. 当前作为演示，GroupRunner没有加入did验证，可以按需扩展

  Q: 支持哪些 AI 模型？
  A: 智能爬虫功能目前支持 Azure OpenAI 和 OpenAI API。通过配置 .env 文件中的相关参数即可切换。

  Q: 如何自定义群组逻辑？
  A: 继承 BaseGroupRunner 类并实现自定义逻辑，然后通过 sdk.register_group_runner() 注册即可。

  Q: DID 文档存储在哪里？
  A: 1. DID 文档默认存储在 /anp_open_sdk/anp_users/ 目录下，每个用户有独立的目录。
     2. 如果是hosted用户，目录名为 user_hosted_hosturl_port_随机数
     3. 如果是公网共享用户，暂时要手动配置，请参考 user_hosted_agent-did.com_80_/

# 🌟 设计思路

[ANP Open SDK 未来想法](docs/anp_open_sdk_design_doc.html)
[ANP Open SDK 重构设想](docs/anp_open_sdk_refactoring_plan.html)
[ANP Open SDK 当前架构](docs/anp_sdk_architecture.html)
[ANP Open SDK 遵循理念](docs/anp_sdk_principles_guide.html)
[ANP Open SDK WBA类比](docs/did_story.html)
[ANP Open SDK WBA价值](docs/did_web_crypto.html)

# 📈 路线图

   近期设想，欢迎共建
   [ ] 本地DNS模拟，方便本地多智能体开发
   [ ] 开发视频生成智能体的anp消息互调用演示
   [ ] 完善智能体发现服务、ad.json/yaml生成、配合ANP_Tool
   [ ] 群组增加DID认证，计划是GroupRunner具有DID，由创建者管理，自主与申请者DID双向验证
   [ ] 对接客户端app、智能体开发框架、mcp、a2a、AG-UI
   [ ] 支持更多编程语言 如TS
   [ ] 中文注释英文化，log统一翻译成英文
   [ ] 增加自动测试，参考Python a2a
   [ ] GroupRunner支持ws连接和json-rpc转发

# 💬 社区支持

    [ANP](https://github.com/agent-network-protocol/AgentNetworkProtocol)
    [个人] seanzhang9999@gmail.com

# 🙏 致谢

   感谢所有贡献者和社区成员的支持！

  特别感谢：

  ANP 协议设计团队
  开源社区的宝贵建议
  早期测试用户的反馈
  让智能体互联变得简单！ 🚀

  如有任何问题或建议，欢迎联系我们或提交 Issue。

欢迎反馈建议，共同完善 anp agent opensdk！
本项目采用 Apache License 2.0 进行授权，详情请查看 LICENSE 文件。
