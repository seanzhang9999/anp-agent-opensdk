# anp agent openchat Open Interconnected Agent Network Demo Framework

[中文版](README.md)

This project demonstrates an implementation framework of the anp open interconnected agent network, focusing on the anp agent openchat client and the anp agent openchat publisher. It showcases open integration of agents, identity mechanisms, and inter-agent communication capabilities.

## Demo Objectives

1. **Anyone** can launch the anp agent openchat client to freely explore the world of anp network agents.
2. **Any developer** can quickly integrate the anp protocol and independently publish agents via the anp agent openchat publisher.
3. Agents confirm unique identity via **DID**. Trustworthiness can be provided openly:
   Currently mainly through DID publishing domain and rich ad.json information
   In the future, domain/organization/community DID signature endorsements will be considered.

## Demo Startup

- **anp agent openchat**: Provides users with AI chat, agent discovery, and chatting with agents. Run `web_api.py`, default port 8000.
- **anp agent openchat publisher**: Helps service providers launch and monitor multiple local agents, and publishes running agent addresses. Run `web_anp_llmagent_launcher.py`, default port 8080.

## Demo Features

### anp agent openchat
1. Load agent bookmarks from anp agent openchat publisher.
2. Explore agents via local AI agent based on anp protocol, learn details, and verify own identity during exploration.
3. Local AI agent recommends agents based on user needs.
4. Supports chatting with @network agents.
5. Multi-turn conversation with local AI agent.

### anp agent openchat publisher
1. Select and run local agents via dropdown menu.
2. View agent running status.
3. Publish running agent addresses via `/api/public/instances` for anp agent openchat to fetch.

## Installation

### Environment Preparation

1. Clone the project
2. Create environment config file
   ```
   cp .env.example .env
   ```
3. Edit the .env file and set necessary configuration items

### Install Dependencies with Poetry

```bash
# Activate virtual environment (if exists)
source .venv/bin/activate

# Install dependencies
poetry install
```

## Running Methods

This project supports multiple running methods:

### 1. Start anp agent openchat client

```bash
python web_api.py
```
Default listens on port 8000, provides web chat and agent discovery.

### 2. Start anp agent openchat publisher

```bash
python web_anp_llmagent_launcher.py
```
Default listens on port 8080, manages local agents and publishes externally.

### 3. Command line call to ANP interface for interactive experience

```bash
python anp_llmapp.py
```

### 4. Call MCP interface via stdio/SSE to experience feasibility in MCP client

```bash
# Start server
python -m anp_mcpwrapper.mcp_stdio_server
# Start client
python -m anp_mcpwrapper.mcp_stdio_client
# Or start as SSE
python -m anp_mcpwrapper.mcp_stdio_server -t sse
```

**Note**: MCP-related methods have been tested and passed in the TRAE environment.

## Project Structure

```
.
├── anp_core/            # Encapsulated ANP interfaces for developers
├── anp_mcpwrapper/      # MCP interface integration
├── api/                 # API routing module
├── core/                # Application framework
├── doc/                 # Documentation and test keys
├── examples/            # More examples for developers in the future
├── utils/               # Utility functions
├── logs/                # Log files
├── setup/               # Installation solutions (currently unused)
├── anp_llmapp.py        # Application directly calling ANP interfaces
├── anp_llmagent.py      # Planned out-of-the-box agent
├── web_api.py           # anp agent openchat
└── web_anp_llmagent_launcher.py # anp agent openchat publisher
```

## API Endpoints

Agent API endpoints
- `GET /agents/example/ad.json`: Get agent description info
- `GET /ad.json`: Get advertisement JSON data, requires authentication
- `POST /auth/did-wba`: DID WBA initial authentication
- `GET /auth/verify`: Verify Bearer Token
- `GET /wba/test`: Test DID WBA authentication
- `POST /wba/anp-nlp`: ANP natural language communication interface
- `GET /wba/user/{user_id}/did.json`: Get user DID document
- `PUT /wba/user/{user_id}/did.json`: Save user DID document
Publisher API endpoint
- `GET /api/public/instances`: Get published local agent instances (provided by publisher)

## Workflow

### Agent Identity and Trust
- Each agent has a unique DID. Trustworthiness can be verified openly (such as domain, ad.json, authoritative signature, community endorsement, etc).

### Client Workflow
1. Start anp agent openchat, load bookmarks, discover and explore agents.
2. Recommend, explore, and chat with network agents via local AI agent.
3. Perform DID identity verification when needed.

### Publisher Workflow
1. Start anp agent openchat publisher, select and run local agents.
2. Monitor agent status in real time.
3. Publish available agent info externally via `/api/public/instances`.

## Authentication Description

This project implements two authentication methods:

1. **Initial DID WBA Authentication**: Signature verification according to DID WBA specification.
2. **Bearer Token Authentication**: JWT token for subsequent request authentication.

For detailed authentication process, please refer to the code implementation and [DID WBA Specification](https://github.com/agent-network-protocol/AgentNetworkProtocol/blob/main/chinese/03-did%3Awba%E6%96%B9%E6%B3%95%E8%A7%84%E8%8C%83.md)

For more information about anp agent openchat and its open interconnection capabilities, please refer to the code and documentation, or run it directly to experience.
