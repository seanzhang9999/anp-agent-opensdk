# ANP WebSocket 服务

## 功能介绍

本服务实现了基于WebSocket的多人实时通信功能，支持以下特性：

- 多客户端同时连接
- 消息广播（发送给所有人）
- 私聊消息（发送给特定用户）
- NLP请求处理（调用OpenRouter LLM）
- 服务端主动推送消息

## 使用方法

### 访问WebSocket客户端

启动服务后，可以通过以下URL访问WebSocket测试客户端：

```
http://localhost:端口号/ws-client/websocket_client.html
```

### WebSocket连接

客户端可以通过以下WebSocket URL连接到服务：

```
ws://localhost:端口号/ws/{client_id}
```

其中`{client_id}`是客户端的唯一标识符。

### 消息格式

#### 客户端发送消息格式

```json
{
  "type": "chat|nlp|system",
  "message": "消息内容",
  "recipient": "接收者ID（可选）"
}
```

- `type`: 消息类型
  - `chat`: 普通聊天消息
  - `nlp`: NLP请求（调用OpenRouter LLM）
  - `system`: 系统消息（如请求用户列表）
- `message`: 消息内容
- `recipient`: 接收者ID（可选，不指定则广播给所有人）

#### 服务端返回消息格式

```json
{
  "type": "chat|nlp_response|system|nlp_status|nlp_error",
  "message": "消息内容",
  "sender": "发送者ID",
  "timestamp": 1234567890.123,
  "recipient": "接收者ID（可选）",
  "active_clients": ["用户列表"]（仅系统消息）
}
```

### 服务端API

#### 广播消息

可以通过以下API向所有连接的客户端广播消息：

```
POST /broadcast-message/
```

请求体：

```json
{
  "message": "广播消息内容",
  "type": "消息类型（可选，默认为system）"
}
```

## 示例代码

### JavaScript客户端示例

```javascript
// 创建WebSocket连接
const socket = new WebSocket(`ws://localhost:端口号/ws/client123`);

// 连接打开时
socket.onopen = () => {
  console.log('已连接到服务器');
};

// 接收消息时
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('收到消息:', data);
};

// 发送消息
function sendMessage(message, type = 'chat', recipient = null) {
  const messageObj = {
    type: type,
    message: message
  };
  
  if (recipient) {
    messageObj.recipient = recipient;
  }
  
  socket.send(JSON.stringify(messageObj));
}
```

## 注意事项

1. 每个客户端必须使用唯一的`client_id`
2. 服务端会自动通知所有客户端用户的连接和断开事件
3. 可以通过系统消息类型请求用户列表
4. NLP请求会异步处理，处理结果通过WebSocket返回