# ANP Agent OpenSDK

ANP Agent OpenSDK is a rapid integration development toolkit based on the ANP core protocol stack agent_connect.

## Development Background

- ANP protocol establishes identity authentication based on DID, involving key file generation, DID document organization and management, which are relatively unfamiliar to general developers.
- ANP protocol's DID documents are published based on domain names. DID identifiers guide authenticators to obtain DID documents from specific URLs, requiring server operation for DID publishing.
- ANP protocol's DID authentication is currently based on FastAPI framework's routing and middleware mechanisms, which has a learning curve for developers.
- ANP protocol authentication is completely peer-to-peer, involving initial DID authentication and subsequent token issuance and storage, requiring developers to understand DID working principles and related security issues.
- ANP protocol's existing web demo uses a public DID identity, improving user experience for quick perception, but developers still need to understand and handle key identity issues for subsequent development.

## Project Goals

- Simplify the development process of WBA-DID authentication using ANP protocol for agent developers, reducing development complexity
- Create ANP user key folders and related DID documents with a single function, with DID identifier format compliant with ANP protocol requirements, which developers can modify after familiarization
- After obtaining key folders, import SDK and create LocalAgent (ANP network connection instance) with one line of code
- Provide developers with a local rapid testing environment, supporting quick iteration and debugging of multi-agent interoperability
- LocalAgent can call other agents' APIs, send messages to other agents, with automatic DID authentication in requests, requiring no developer operation
- LocalAgent can be registered to SDK's FastAPI service, supporting multiple LocalAgent coexistence
- Publish own DID documents and agent description JSON files externally
- FastAPI service provides message listening interface for registered LocalAgent to receive messages from other agents by default, developers can directly register handler functions
- LocalAgent can convert local APIs to Agent APIs with one line of code through decorators and function registration, automatically publishing to FastAPI service for other agents to call
- All call events pass in caller DID and have been verified, developers can freely customize permission control for different caller DIDs
- Provide solutions and sample code for several DID usage scenarios

### User Auto-binding Mode:
- When developers provide services to users and want users to access ANP services without troubling them to understand DID, SDK can automatically create identities for users, automatically publish DID documents to FastAPI service, bind users' DID with their services, and access other ANP agents for services

### Intranet Public Server DID Document Publishing Mode:
- When developing for enterprises, if all DID documents need to be published on a public server while agents run on different laptops/desktops, SDK's hosted DID mode can be used to automatically email submit local agent's DID documents to public server administrator for review and publishing, returning the final public server hosted DID document to local agent for free access to other agents

### ANPTool Mode:
- ANP's distinctive capability, automatically connecting and analyzing ad.json and linked URLs provided by other ANP agents through large models, automatically calling described APIs to complete user functions

### GroupRunner Mode:
- Agents from different networks can join a Group on a public server, listening for response messages through SSE. Message processing and member management functions are executed by the creator-managed GroupRunner. GroupRunner can be inherited and extended to customize various additional behaviors, facilitating cross-network agent connections as securely as possible. In GroupRunner, members can authenticate through DID to ensure message security and privacy.

## Core Features

### 1. DID Identity Management
- Create decentralized identity (DID)
- DID binding with domain names
- DID document publishing and management
- Support hosted DID mode

### 2. Agent Communication
- **Point-to-point messaging**: Direct message passing between agents
- **API calls**: RESTful API publishing and calling
- **Group communication**: SSE-based group messaging functionality
- **Two-way authentication**: Secure identity verification mechanism, currently supporting three compatible modes:
  - Requester submits DID authentication, responder verifies, no token returned (one-time verification)
  - Requester submits DID authentication, responder verifies, returns token (convenient for subsequent access)
  - Requester submits DID authentication, responder verifies, returns token and own DID authentication (two-way authentication)

### 3. Service Discovery and Interoperability
- Agent trusted information publishing (ad.json/yaml/DID document interface, customizable)
- Intelligent crawler functionality (anp_tool)
- Agent discovery (provides query interface, customizable)

## Quick Demo Run

1. Clone the project
2. Create Python venv environment and enter venv environment
3. Install dependencies using poetry
4. Run `python anp_demo_main.py`

```bash
python anp_demo_main.py [-h] [-d] [-s] [-f] [--domain DOMAIN]

Parameters:
  -h, --help       Show help message
  -d               Development test mode (default) - includes detailed log output
  -s               Step-by-step execution mode - pauses at each step for confirmation, suitable for learning
  -f               Fast execution mode - skips all pauses, suitable for automated testing
```

## Main Demo Content

### 1. API Call Demo (run_api_demo)
- Demonstrates API calling functionality between agents
- Shows POST/GET requests to other agents' interfaces
- Displays agent's ad.json information

### 2. Message Passing Demo (run_message_demo)
- Demonstrates point-to-point message sending
- Shows automatic message reply functionality
- Message interaction between multiple agents

### 3. Agent Lifecycle Demo (run_agent_lifecycle_demo)
- Dynamically create temporary agents
- Register message handlers
- Message interaction between agents
- Agent deregistration and cleanup

### 4. ANP Tool Crawler Demo (run_anp_tool_crawler_agent_search_ai_ad_jason)
- Use ANP protocol for agent information crawling
- Intelligent crawler autonomously decides crawling path
- Supports secure crawling with two-way authentication
- Integrates AI models for intelligent analysis and decision-making

### 5. Hosted DID Demo (run_hosted_did_demo)
- Apply for hosted DID
- Query hosting status
- Message interaction between hosted agents and regular agents
- Communication between hosted agents

### 6. Group Chat Demo (run_group_chat_demo)
- Create and join groups
- Group message broadcasting
- Moderated chat functionality (message filtering)
- Group member management
- Message storage and statistics functionality

## Demo Modes

- **Development mode (-d)**: Suitable for development debugging, includes detailed log output
- **Step mode (-s)**: Pauses at each demo step, suitable for learning and understanding
- **Fast mode (-f)**: Skips all pauses, suitable for automated testing

## 🔧 Integration Guide

### Basic Integration Steps

1. **Create DID Identity**

```python

from anp_open_sdk.anp_sdk_userdata_tool import did_create_user

params = {
    'name': 'MyAgent',
    'host': 'localhost',
    'port': 9527,
    'dir': 'wba',
    'type': 'agent'
}
did_document = did_create_user(params)
```

2. **Initialize SDK**
```python
from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent

sdk = ANPSDK(host="localhost", port=9527)
agent = LocalAgent(sdk, did_document['id'])
sdk.register_agent(agent)
```

3. **Register Message Handler**
```python
@agent.register_message_handler("*")
def handle_message(msg):
    print(f"Received message: {msg}")
    return {"reply": "Message received"}
```

4. **Register API Endpoint**
```python
@agent.register_api_handler("/info", methods=["GET", "POST"])
async def handle_info(request):
    return {"name": agent.name, "status": "online"}
```

5. **Start Service**
```python
sdk.start_server()
```

## 🏗️ Architecture Overview

```
anp-agent-opensdk/
├── anp_open_sdk/          # SDK core code
│   ├── anp_sdk.py         # Main SDK class
│   ├── anp_sdk_agent.py   # Agent implementation
│   ├── anp_users_hosted/  # DID documents hosted as hosting server
│   ├── auth/              # Authentication related modules
│   ├── config/            # Configuration related modules
│   └── service/           # Service modules
├── anp_sdk_demo/          
├── anp_sdk_demo/          # Demo related code
│   ├── demo_modules/      # Demo modules
│   └── services/          # Demo services
├── anp_demo_main.py       # Comprehensive demo program
└── docs/                  # Documentation
```

## 📄 License

This project is licensed under Apache License 2.0. See LICENSE file for details.

## 🔍 FAQ

**Q: How to use in intranet environment?**
A: 
1. For intranet usage, see - Intranet Public Server DID Document Publishing Mode
2. For cross-intranet usage, see - GroupRunner Mode
3. Currently as a demo, GroupRunner doesn't include DID verification, can be extended as needed

**Q: Which AI models are supported?**
A: The intelligent crawler functionality currently supports Azure OpenAI and OpenAI API. Switch by configuring relevant parameters in .env file.

**Q: How to customize group logic?**
A: Inherit BaseGroupRunner class and implement custom logic, then register through `sdk.register_group_runner()`.

**Q: Where are DID documents stored?**
A: 
1. DID documents are stored by default in `/anp_open_sdk/anp_users/` directory, each user has an independent directory
2. For hosted users, directory name is `user_hosted_hosturl_port_randomnumber`
3. For public network shared users, manual configuration is required temporarily, refer to `user_hosted_agent-did.com_80_/`

## 🌟 Design Philosophy

- [ANP Open SDK Future Ideas](docs/anp_open_sdk_design_doc.html)
- [ANP Open SDK Refactoring Vision](docs/anp_open_sdk_refactoring_plan.html)
- [ANP Open SDK Current Architecture](docs/anp_sdk_architecture.html)
- [ANP Open SDK Guiding Principles](docs/anp_sdk_principles_guide.html)
- [ANP Open SDK WBA Analogy](docs/did_story.html)
- [ANP Open SDK WBA Value](docs/did_web_crypto.html)

## 📈 Roadmap

Near-term plans, contributions welcome:

- [ ] Local DNS simulation for convenient local multi-agent development
- [ ] Develop video generation agent ANP message inter-calling demo
- [ ] Improve agent discovery service, ad.json/yaml generation, cooperate with ANP_Tool
- [ ] Add DID authentication to groups, plan is for GroupRunner to have DID, managed by creator, autonomously perform two-way verification with applicant DID
- [ ] Connect with client apps, agent development frameworks, MCP, A2A, AG-UI
- [ ] Support more programming languages like TypeScript
- [ ] Translate Chinese comments to English, unify logs to English
- [ ] Add automated testing, reference Python A2A
- [ ] GroupRunner support for WebSocket connections and JSON-RPC forwarding

## 💬 Community Support

- [ANP](https://github.com/agent-network-protocol/AgentNetworkProtocol)
- [Personal] seanzhang9999@gmail.com

## 🙏 Acknowledgments

Thanks to all contributors and community members for their support!

Special thanks to:
- ANP protocol design team
- Valuable suggestions from the open source community
- Feedback from early test users

**Making agent interconnection simple!** 🚀

If you have any questions or suggestions, please feel free to contact us or submit an Issue.

Welcome feedback and suggestions to improve ANP Agent OpenSDK together!

This project is licensed under Apache License 2.0. See LICENSE file for details.