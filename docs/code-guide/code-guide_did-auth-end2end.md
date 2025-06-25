# WBA (Web-based Authentication) 端到端认证系统说明

## 目录
- [1. 系统概述](#1-系统概述)
- [2. 架构设计](#2-架构设计)
- [3. 核心组件](#3-核心组件)
- [4. 认证流程](#4-认证流程)
- [5. 安全机制](#5-安全机制)
- [6. 使用指南](#6-使用指南)
- [7. 配置说明](#7-配置说明)
- [8. 故障排除](#8-故障排除)

## 1. 系统概述

WBA认证系统是基于DID（去中心化身份标识）的Web认证解决方案，支持单向和双向认证模式，提供强大的安全保障和灵活的token管理机制。

### 1.1 主要特性

- **双向认证**：客户端和服务端相互验证身份
- **防重放攻击**：基于时间戳和nonce的防重放机制
- **智能token管理**：自动缓存、更新和验证JWT token
- **多层安全防护**：密码学签名、域名绑定、时间窗口控制
- **高性能优化**：token缓存、快速验证路径
- **灵活配置**：支持多种认证模式和自定义配置

### 1.2 认证模式

- **单向认证**：客户端 → 服务端
- **双向认证**：客户端 ↔ 服务端（相互验证）

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Client Side   │    │   Auth Client    │    │   Auth Server   │
│                 │    │  (DIDWbaAuth     │    │  (AgentAuth     │
│ - DID Credentials│    │   Header)        │    │   Server)       │
│ - Auth Context  │    │ - Header Builder │    │ - Request       │
│ - HTTP Client   │    │ - Token Manager  │    │   Verifier      │
│                 │    │ - Signature Gen  │    │ - Response Gen  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### 2.2 模块关系

```
anp_open_sdk/auth/
├── schemas.py              # 数据结构定义
├── did_auth_base.py        # 认证基础抽象类
├── did_auth_wba.py         # WBA认证实现
├── auth_server.py          # 服务端认证逻辑
└── agent_connect_hotpatch/
    └── authentication/
        ├── did_wba.py      # WBA核心功能
        └── did_wba_auth_header.py  # 认证头客户端
```

## 3. 核心组件

### 3.1 Auth Client (DIDWbaAuthHeader)

负责客户端认证头生成和token管理。

#### 主要功能
- **认证头生成**：生成DID认证头或Bearer token头
- **Token缓存**：按域名缓存和管理token
- **签名处理**：使用私钥进行数字签名
- **响应处理**：解析服务端响应并更新token

#### 核心方法

```python
class DIDWbaAuthHeader:
    def __init__(self, did_document_path: str, private_key_path: str)

    def get_auth_header_two_way(self, server_url: str, resp_did: str, force_new: bool = False) -> Dict[str, str]
    """获取认证头（优先使用缓存token，否则生成DID认证头）"""

    def update_token(self, server_url: str, headers: Dict[str, str]) -> Optional[str]
    """从响应头更新token并验证服务端认证头"""

    def clear_token(self, server_url: str) -> None
    """清除指定域名的token"""
```

### 3.2 Auth Server (AgentAuthServer)

负责服务端请求验证和响应生成。

#### 主要功能

- **请求验证**：验证DID认证头或Bearer token
- **双向认证**：生成服务端认证头
- **Token管理**：生成、存储和验证JWT token
- **安全检查**：时间戳、nonce、签名验证

#### 核心方法

```python
class AgentAuthServer:
    def __init__(self, authenticator: BaseDIDAuthenticator)

    async def verify_request(self, request: Request) -> (bool, str, Dict[str, Any])
    """验证请求认证信息"""

    async def handle_bearer_auth(self, token: str, req_did, resp_did) -> Dict
    """处理Bearer token认证"""
```

### 3.3 WBA认证器 (WBADIDAuthenticator)

实现完整的WBA认证流程。

#### 组件构成

- **WBADIDResolver**：DID文档解析器
- **WBADIDSigner**：数字签名器
- **WBAAuthHeaderBuilder**：认证头构建器
- **WBAAuth**：认证头解析器

## 4. 认证流程

### 4.1 首次认证流程（DID认证）

```mermaid
sequenceDiagram
    participant C as Client
    participant AC as Auth Client
    participant AS as Auth Server
    participant S as Server

    C->>AC: 初始化认证客户端
    C->>AC: get_auth_header_two_way(url, resp_did)
    AC->>AC: 生成DID认证头
    Note over AC: 包含did, nonce, timestamp, resp_did, signature

    C->>S: HTTP请求 + DID认证头
    S->>AS: 验证认证头
    AS->>AS: 解析认证头
    AS->>AS: 验证时间戳和nonce
    AS->>AS: 解析DID文档
    AS->>AS: 验证签名
    AS->>AS: 生成JWT token
    AS->>AS: 生成服务端认证头
    S->>C: 响应 + token + 服务端认证头

    C->>AC: update_token(url, response_headers)
    AC->>AC: 验证服务端认证头
    AC->>AC: 缓存token
```

### 4.2 后续请求流程（Token认证）

```mermaid
sequenceDiagram
    participant C as Client
    participant AC as Auth Client
    participant AS as Auth Server
    participant S as Server

    C->>AC: get_auth_header_two_way(url, resp_did)
    AC->>AC: 检查缓存token
    AC->>C: 返回Bearer token头

    C->>S: HTTP请求 + Bearer token
    S->>AS: 验证token
    AS->>AS: 检查LocalAgent缓存
    alt Token在缓存中且有效
        AS->>AS: 快速验证
    else Token不在缓存或无效
        AS->>AS: JWT公钥验证
    end
    S->>C: 响应数据
```

### 4.3 详细认证步骤

#### 步骤1：客户端生成认证头

```python
# 1. 初始化认证客户端
auth_client = DIDWbaAuthHeader(
    did_document_path="path/to/did.json",
    private_key_path="path/to/private.pem"
)

# 2. 生成认证头
headers = auth_client.get_auth_header_two_way(server_url, resp_did)

# 生成的认证头格式：
# {
#   "Authorization": "DIDWba did=\"did:wba:client.com:user:alice\",
#                            nonce=\"abc123\",
#                            timestamp=\"2024-01-01T12:00:00Z\",
#                            resp_did=\"did:wba:server.com:api:service\",
#                            verification_method=\"key-1\",
#                            signature=\"base64_signature\""
# }
```

#### 步骤2：签名生成过程

```python
def generate_auth_header_two_way():
    # 1. 构造签名数据
    data_to_sign = {
        "nonce": nonce,           # 16字节随机数
        "timestamp": timestamp,    # ISO 8601 UTC时间戳
        "service": service_domain, # 目标域名
        "did": caller_did,        # 调用方DID
        "resp_did": target_did    # 响应方DID
    }

    # 2. JSON规范化 (JCS)
    canonical_json = jcs.canonicalize(data_to_sign)

    # 3. SHA256哈希
    content_hash = hashlib.sha256(canonical_json).digest()

    # 4. 数字签名（secp256k1 ECDSA）
    signature_bytes = private_key.sign(content_hash, ec.ECDSA(hashes.SHA256()))
    signature = base64.b64encode(signature_bytes).decode('utf-8')
```

#### 步骤3：服务端验证

```python
async def verify_response(auth_header, context):
    # 1. 解析认证头
    did, nonce, timestamp, resp_did, keyid, signature = extract_auth_header_parts_two_way(auth_header)

    # 2. 时间戳验证（默认5分钟窗口）
    request_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    current_time = datetime.now(timezone.utc)
    time_diff = abs((current_time - request_time).total_seconds() / 60)
    if time_diff > nonce_expire_minutes:
        return False, "Timestamp expired"

    # 3. Nonce防重放验证
    if not is_valid_server_nonce(nonce):
        return False, "Invalid nonce"

    # 4. DID文档解析（本地优先，远程回退）
    did_document = await resolve_local_did_document(did)
    if not did_document:
        did_document = await resolve_did_wba_document(did)

    # 5. 签名验证
    is_valid, message = verify_auth_header_signature_two_way(
        auth_header, did_document, context.domain
    )

    # 6. 生成响应
    if is_valid:
        response_data = await generate_auth_response(did, True, resp_did)
        return True, response_data
```

#### 步骤4：服务端响应生成

```python
async def generate_auth_response(did, is_two_way_auth, resp_did):
    # 1. 生成JWT访问令牌
    access_token = create_access_token(
        private_key_path=resp_did_agent.jwt_private_key_path,
        data={"req_did": did, "resp_did": resp_did},
        expires_delta=expiration_time
    )

    # 2. 存储token到LocalAgent
    resp_did_agent.contact_manager.store_token_to_remote(did, access_token, expiration_time)

    # 3. 生成服务端认证头（双向认证）
    if is_two_way_auth and resp_did:
        resp_auth_client = DIDWbaAuthHeader(
            did_document_path=resp_did_agent.did_document_path,
            private_key_path=resp_did_agent.private_key_path
        )
        resp_did_auth_header = resp_auth_client.get_auth_header_two_way(target_url, did)

    # 4. 返回响应
    return [{
        "access_token": access_token,
        "token_type": "bearer",
        "req_did": did,
        "resp_did": resp_did,
        "resp_did_auth_header": resp_did_auth_header
    }]
```

#### 步骤5：客户端验证服务端响应

```python
def update_token(self, server_url: str, headers: Dict[str, str]):
    auth_data = headers.get("Authorization")

    try:
        # 解析双向认证响应
        auth_data = json.loads(auth_data)
        token = auth_data[0].get("access_token")
        did_auth_header = auth_data[0].get("resp_did_auth_header", {}).get("Authorization")

        if did_auth_header and token:
            # 验证服务端认证头
            is_valid = await check_response_DIDAtuhHeader(did_auth_header)
            if is_valid:
                domain = self._get_domain(server_url)
                self.tokens[domain] = token
                return token
            else:
                logger.error("服务端认证头验证失败")
                return None

    except Exception as e:
        logger.error(f"处理响应认证头失败: {e}")
        return None
```

## 5. 安全机制

### 5.1 防重放攻击

#### Nonce机制

```python
# 生成16字节随机nonce
nonce = secrets.token_hex(16)

# 服务端nonce管理
VALID_SERVER_NONCES: Dict[str, datetime] = {}

def is_valid_server_nonce(nonce: str) -> bool:
    # 1. 清理过期nonce
    expired_nonces = [n for n, t in VALID_SERVER_NONCES.items()
                     if current_time - t > timedelta(minutes=5)]

    # 2. 检查nonce是否已使用
    if nonce in VALID_SERVER_NONCES:
        return False  # 已使用，拒绝

    # 3. 标记为已使用
    VALID_SERVER_NONCES[nonce] = current_time
    return True
```

#### 时间戳验证

```python
# 生成ISO 8601格式UTC时间戳
timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

# 验证时间窗口（默认5分钟）
request_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
time_diff = abs((current_time - request_time).total_seconds() / 60)
if time_diff > nonce_expire_minutes:
    return False, "Timestamp expired"
```

### 5.2 密码学安全

#### 数字签名

```python
# 支持secp256k1椭圆曲线
# 使用ECDSA-SHA256签名算法
signature = private_key.sign(
    content_hash,
    ec.ECDSA(hashes.SHA256())
)

# JSON规范化签名（JCS）确保一致性
canonical_json = jcs.canonicalize(data_to_sign)
content_hash = hashlib.sha256(canonical_json).digest()
```

#### JWT Token安全

```python
# 使用非对称算法（RS256/ES256）
jwt_algorithm = "RS256"  # 或 ES256

# Token包含必要字段
payload = {
    "req_did": caller_did,
    "resp_did": target_did,
    "exp": expiration_timestamp,
    "iat": issued_at_timestamp
}

# 公钥验证
public_key = get_jwt_public_key(public_key_path)
decoded_payload = jwt.decode(token, public_key, algorithms=[jwt_algorithm])
```

### 5.3 域名绑定

```python
# 签名数据包含目标域名
data_to_sign = {
    "service": service_domain,  # 绑定到特定域名
    # ... 其他字段
}

# 防止跨域重放攻击
# 签名只对特定域名有效
```

### 5.4 双向认证

```python
# 客户端验证服务端
async def check_response_DIDAtuhHeader(auth_value: str) -> bool:
    # 1. 解析服务端认证头
    header_parts = extract_auth_header_parts_two_way(auth_value)

    # 2. 验证时间戳
    if not verify_timestamp(timestamp):
        return False

    # 3. 解析服务端DID文档
    did_document = await resolve_did_document(server_did)

    # 4. 验证服务端签名
    is_valid, message = verify_auth_header_signature_two_way(
        auth_header, did_document, service_domain
    )

    return is_valid
```

### 5.5 Token管理安全

#### 缓存策略

```python
# LocalAgent中的token存储
token_info = {
    "token": access_token,
    "expires_at": expiration_datetime,
    "is_revoked": False,
    "created_at": creation_datetime
}

# 快速验证路径
if token_info and not token_info["is_revoked"]:
    if datetime.now(timezone.utc) <= token_info["expires_at"]:
        if token == token_info["token"]:
            return True  # 快速通过
```

#### 撤销机制

```python
# Token撤销
token_info["is_revoked"] = True

# 验证时检查撤销状态
if token_info["is_revoked"]:
    raise HTTPException(status_code=401, detail="Token has been revoked")
```

## 6. 使用指南

### 6.1 客户端使用

#### 基本使用

```python
import asyncio
import aiohttp
from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba_auth_header import DIDWbaAuthHeader

async def client_example():
    # 1. 初始化认证客户端
    auth_client = DIDWbaAuthHeader(
        did_document_path="path/to/client_did.json",
        private_key_path="path/to/client_private.pem"
    )

    server_url = "https://api.example.com"
    resp_did = "did:wba:api.example.com:service"

    # 2. 发起认证请求
    headers = auth_client.get_auth_header_two_way(server_url, resp_did)

    async with aiohttp.ClientSession() as session:
        # 3. 发送请求
        async with session.get(f"{server_url}/api/data", headers=headers) as response:
            if response.status == 200:
                # 4. 处理响应并更新token
                token = auth_client.update_token(server_url, dict(response.headers))
                print(f"认证成功，获得token: {token[:20]}...")

                # 5. 后续请求自动使用token
                token_headers = auth_client.get_auth_header_two_way(server_url, resp_did)
                async with session.get(f"{server_url}/api/user", headers=token_headers) as resp:
                    data = await resp.json()
                    print(f"用户数据: {data}")

            elif response.status == 401:
                # 6. 处理认证失败
                print("认证失败，检查DID文档和私钥")

# 运行示例
asyncio.run(client_example())
```

#### 错误处理

```python
async def robust_client_example():
    auth_client = DIDWbaAuthHeader(did_doc_path, private_key_path)

    async with aiohttp.ClientSession() as session:
        for attempt in range(3):  # 最多重试3次
            try:
                headers = auth_client.get_auth_header_two_way(server_url, resp_did)
                async with session.get(api_url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 401:
                        # Token失效，清除并重试
                        auth_client.clear_token(server_url)
                        if attempt < 2:  # 不是最后一次尝试
                            continue
                    else:
                        response.raise_for_status()
            except Exception as e:
                if attempt == 2:  # 最后一次尝试
                    raise
                await asyncio.sleep(1)  # 等待1秒后重试
```

### 6.2 服务端使用

#### FastAPI集成

```python
from fastapi import FastAPI, Request
from anp_open_sdk.auth.auth_server import auth_middleware

app = FastAPI()

# 添加认证中间件
@app.middleware("http")
async def add_auth_middleware(request: Request, call_next):
    return await auth_middleware(request, call_next, auth_method="wba")

# 认证端点
@app.get("/wba/auth")
async def auth_endpoint(request: Request):
    return {"status": "success", "message": "Authentication successful"}

# 受保护的API端点
@app.get("/api/data")
async def get_data(request: Request):
    # 认证信息在中间件中验证
    # 可以从request.state.headers获取认证信息
    return {"data": "sensitive information"}

# 豁免认证的端点
@app.get("/public/info")
async def public_info():
    return {"info": "public information"}
```

#### 自定义认证逻辑

```python
from anp_open_sdk.auth.auth_server import AgentAuthServer, create_authenticator

async def custom_auth_handler(request: Request):
    # 创建认证服务器
    auth_server = AgentAuthServer(create_authenticator("wba"))

    try:
        # 验证请求
        success, msg, auth_data = await auth_server.verify_request(request)

        if success:
            # 认证成功，提取用户信息
            if isinstance(auth_data, dict):
                user_did = auth_data.get("req_did")
                print(f"用户 {user_did} 认证成功")
            return {"authenticated": True, "user": user_did}
        else:
            return {"authenticated": False, "error": msg}

    except Exception as e:
        return {"authenticated": False, "error": str(e)}
```

### 6.3 DID文档配置

#### 客户端DID文档示例

```json
{
  "@context": [
    "https://www.w3.org/ns/did/v1",
    "https://w3id.org/security/suites/jws-2020/v1",
    "https://w3id.org/security/suites/secp256k1-2019/v1"
  ],
  "id": "did:wba:client.example.com:user:alice",
  "verificationMethod": [
    {
      "id": "did:wba:client.example.com:user:alice#key-1",
      "type": "EcdsaSecp256k1VerificationKey2019",
      "controller": "did:wba:client.example.com:user:alice",
      "publicKeyJwk": {
        "kty": "EC",
        "crv": "secp256k1",
        "x": "base64url_encoded_x_coordinate",
        "y": "base64url_encoded_y_coordinate",
        "kid": "key_identifier"
      }
    }
  ],
  "authentication": [
    "did:wba:client.example.com:user:alice#key-1"
  ],
  "service": [
    {
      "id": "did:wba:client.example.com:user:alice#ad",
      "type": "AgentDescription",
      "serviceEndpoint": "https://client.example.com/agent/description"
    }
  ]
}
```

#### 私钥文件格式

```
-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg...
-----END PRIVATE KEY-----
```

## 7. 配置说明

### 7.1 全局配置

```yaml
# 配置文件示例
anp_sdk:
  jwt_algorithm: "RS256"           # JWT签名算法
  token_expire_time: 3600          # Token过期时间（秒）
  nonce_expire_minutes: 5          # Nonce过期时间（分钟）

# 环境变量
ANP_USER_HOSTED_PATH: "anp_open_sdk/anp_users_hosted"  # DID托管目录
HOST_DID_PORT: "9527"                                  # 主机DID端口
HOST_DID_DOMAIN: "localhost"                           # 主机DID域名
```

### 7.2 路径豁免配置

```python
# 豁免认证的路径
EXEMPT_PATHS = [
    "/docs",                    # API文档
    "/anp-nlp/",               # NLP服务
    "/ws/",                    # WebSocket
    "/publisher/agents",        # 代理发布
    "/agent/group/*",          # 代理组（通配符）
    "/redoc",                  # ReDoc文档
    "/openapi.json",           # OpenAPI规范
    "/wba/hostuser/*",         # WBA托管用户
    "/wba/user/*",             # WBA用户
    "/",                       # 根路径
    "/favicon.ico",            # 图标
    "/agents/example/ad.json"  # 示例代理描述
]
```

### 7.3 DID解析配置

```yaml
# 本地DID解析器配置
local_did_resolver:
  enabled: true
  cache_ttl: 300              # 缓存时间（秒）

# 远程DID解析器配置
remote_did_resolver:
  timeout: 10                 # 请求超时（秒）
  retry_count: 3              # 重试次数
  dns_servers:                # DNS服务器
    - "8.8.8.8"
    - "1.1.1.1"
```

## 8. 故障排除

### 8.1 常见错误

#### 认证失败

```
错误：Authentication failed: Invalid signature
原因：签名验证失败
解决：
1. 检查私钥文件是否正确
2. 确认DID文档中的公钥与私钥匹配
3. 验证时间戳是否在有效窗口内
```

#### Token过期

```
错误：Token has expired
原因：JWT token已过期
解决：
1. 客户端调用 clear_token() 清除缓存
2. 重新发起DID认证获取新token
3. 检查服务端时间同步
```

#### Nonce重复

```
错误：Invalid nonce: nonce already used
原因：Nonce被重复使用
解决：
1. 确保客户端生成唯一nonce
2. 检查是否有请求重放
3. 验证时间戳是否正确
```

#### DID解析失败

```
错误：Failed to resolve DID document
原因：无法解析DID文档
解决：
1. 检查DID格式是否正确
2. 确认DID文档可访问
3. 验证网络连接
4. 检查本地DID解析器配置
```

### 8.2 调试技巧

#### 启用详细日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 或者针对特定模块
logger = logging.getLogger("anp_open_sdk.auth")
logger.setLevel(logging.DEBUG)
```

#### 验证DID文档

```python
from anp_open_sdk.auth.did_auth_wba import resolve_local_did_document

async def test_did_resolution():
    did = "did:wba:example.com:user:alice"
    doc = await resolve_local_did_document(did)
    if doc:
        print(f"DID文档解析成功: {doc['id']}")
    else:
        print("DID文档解析失败")
```

#### 测试签名

```python
from anp_open_sdk.auth.schemas import DIDKeyPair

def test_signature():
    key_pair = DIDKeyPair.from_file_path("path/to/private.pem")
    test_data = b"test message"

    # 这里需要实现签名测试逻辑
    print("签名测试完成")
```

### 8.3 性能优化

#### Token缓存优化

```python
# 预热token缓存
async def warmup_tokens():
    auth_client = DIDWbaAuthHeader(did_doc_path, private_key_path)

    # 为常用服务预先获取token
    common_services = [
        "https://api1.example.com",
        "https://api2.example.com"
    ]

    for service_url in common_services:
        headers = auth_client.get_auth_header_two_way(service_url, resp_did)
        # 发送预热请求...
```

#### 连接池配置

```python
# 配置HTTP连接池
connector = aiohttp.TCPConnector(
    limit=100,              # 总连接数限制
    limit_per_host=30,      # 每个主机连接数限制
    ttl_dns_cache=300,      # DNS缓存时间
    use_dns_cache=True,     # 启用DNS缓存
)

async with aiohttp.ClientSession(connector=connector) as session:
    # 使用配置的连接池
    pass
```

### 8.4 监控和指标

#### 认证指标

```python
# 认证成功率
auth_success_rate = successful_auths / total_auth_attempts

# 平均认证时间
avg_auth_time = total_auth
