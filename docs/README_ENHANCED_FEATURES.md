# ANP SDK 增强功能说明

本文档介绍了 ANP SDK 的两个主要增强功能：
1. 增强邮件管理系统
2. 本地智能体加速器

## 1. 增强邮件管理系统

### 功能概述

增强邮件管理系统将原本分散在 `anp_sdk.py` 和 `agent_types.py` 中的邮件功能集中到 `mail_manager_enhanced.py` 中，并提供了本地测试方案。

### 主要特性

- **统一邮件接口**: 所有邮件操作通过 `EnhancedMailManager` 统一管理
- **多后端支持**: 支持 Gmail 和本地文件两种后端
- **本地测试**: 提供基于文件系统的邮件模拟，方便开发测试
- **DID托管支持**: 专门的 DID 托管请求处理功能

### 使用方法

#### 基本使用

```python
from anp_open_sdk.anp_sdk_publisher_mail_backend import EnhancedMailManager

# 使用 Gmail 后端（生产环境）
mail_manager = EnhancedMailManager(use_local_backend=False)

# 使用本地文件后端（测试环境）
mail_manager = EnhancedMailManager(use_local_backend=True)
```

#### 环境变量配置

```bash
# 启用本地邮件后端
export USE_LOCAL_MAIL=true

# Gmail 配置（生产环境）
export GMAIL_USER=your_email@gmail.com
export GMAIL_PASSWORD=your_app_password
export IMAP_SERVER=imap.gmail.com
export SMTP_SERVER=smtp.gmail.com
```

#### 发送邮件

```python
# 发送普通邮件
success = mail_manager.send_email(
    to_address="recipient@example.com",
    subject="测试邮件",
    body="邮件内容"
)

# 发送 DID 托管请求
did_document = {
    "id": "did:anp:example123",
    "@context": "https://www.w3.org/ns/did/v1",
    # ... 其他 DID 文档内容
}

success = mail_manager.send_did_hosting_request(
    to_address="hosting@anp.com",
    did_document=did_document
)
```

#### 接收邮件

```python
# 获取未读邮件
unread_emails = mail_manager.get_unread_emails()

# 获取 DID 托管请求
did_requests = mail_manager.get_unread_did_requests()

# 标记邮件为已读
mail_manager.mark_message_as_read(message_id)
```

### 本地测试方案

本地文件后端将邮件存储在以下目录结构中：

```
~/.anp_mail/
├── inbox/          # 收件箱
├── sent/           # 已发送
└── drafts/         # 草稿箱
```

每封邮件以 JSON 格式存储，包含完整的邮件元数据和内容。

## 2. 本地智能体加速器

### 功能概述

本地智能体加速器通过直接内存调用替代网络请求，显著提升本地智能体间的通信性能。

### 主要特性

- **零网络延迟**: 本地智能体间通信不经过网络栈
- **性能监控**: 内置性能统计和监控
- **透明集成**: 与现有 API 完全兼容
- **智能路由**: 自动识别本地和远程智能体

### 支持的操作类型

1. **API 调用**: `call_api()` 方法的本地加速
2. **点对点消息**: `send_message()` 方法的本地加速
3. **群组操作**: 群组消息和成员管理的本地加速

### 使用方法

#### 启用加速器

```bash
# 启用本地加速
export ENABLE_LOCAL_ACCELERATION=true
```

#### 在代码中使用

```python
from anp_open_sdk.anp_sdk import ANPSDK

# SDK 会自动检测环境变量并启用加速
sdk = ANPSDK()

# 正常使用 API，加速器会自动工作
response = sdk.call_api(
    target_did="did:anp:local_agent",
    api_path="/test/endpoint",
    method="POST",
    data={"key": "value"}
)

# 发送消息也会自动加速
success = sdk.send_message(
    target_did="did:anp:local_agent",
    message="Hello from accelerated communication!"
)
```

#### 性能监控

```python
from anp_open_sdk.service.local_agent_accelerator import LocalAgentAccelerator

# 获取性能统计
stats = accelerator.get_performance_stats()
print(f"API调用次数: {stats['api_calls']}")
print(f"平均响应时间: {stats['avg_api_response_time']:.2f}ms")
```

### 性能优势

| 操作类型 | 网络调用 | 本地加速 | 性能提升 |
|---------|---------|---------|----------|
| API调用 | 10-50ms | <1ms | 10-50x |
| 消息发送 | 5-20ms | <0.5ms | 10-40x |
| 群组操作 | 20-100ms | <2ms | 10-50x |

## 3. 集成使用

### 完整配置示例

```bash
# .env 文件
USE_LOCAL_MAIL=true
ENABLE_LOCAL_ACCELERATION=true

# Gmail 配置（可选，用于生产环境）
GMAIL_USER=your_email@gmail.com
GMAIL_PASSWORD=your_app_password
IMAP_SERVER=imap.gmail.com
SMTP_SERVER=smtp.gmail.com
```

### 测试脚本

运行提供的测试脚本来验证功能：

```bash
python3 test_enhanced_features.py
```

### 在现有项目中集成

1. **更新导入**: 将 `mail_manager` 替换为 `mail_manager_enhanced`
2. **设置环境变量**: 根据需要配置本地测试或生产环境
3. **启用加速**: 设置 `ENABLE_LOCAL_ACCELERATION=true`
4. **测试验证**: 运行测试确保功能正常

## 4. 故障排除

### 常见问题

1. **邮件发送失败**
   - 检查 Gmail 应用密码配置
   - 确认 SMTP 服务器设置
   - 验证网络连接

2. **本地加速不生效**
   - 确认环境变量 `ENABLE_LOCAL_ACCELERATION=true`
   - 检查智能体是否正确注册到加速器
   - 验证目标智能体是否为本地智能体

3. **本地邮件测试问题**
   - 检查 `~/.anp_mail/` 目录权限
   - 确认环境变量 `USE_LOCAL_MAIL=true`
   - 验证文件系统可写性

### 调试模式

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 启用详细日志
os.environ['ANP_DEBUG'] = 'true'
```

## 5. 架构说明

### 邮件管理架构

```
EnhancedMailManager
├── MailBackend (抽象基类)
│   ├── LocalFileMailBackend (本地文件)
│   └── GmailBackend (Gmail)
└── 统一接口层
```

### 加速器架构

```
LocalAgentAccelerator
├── 本地智能体注册表
├── 性能监控器
├── 路由决策器
└── 直接调用处理器
```

这些增强功能显著提升了 ANP SDK 的开发体验和运行性能，特别是在本地开发和测试环境中。