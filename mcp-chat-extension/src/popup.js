/**
 * MCP Chat Extension Popup Script
 */
class MCPChatPopup {
  constructor() {
    this.isConnected = false;
    this.initialize();
  }

  initialize() {
    this.bindEvents();
    this.loadStatus();
  }

  bindEvents() {
    // 连接按钮
    const connectBtn = document.getElementById('connect-btn');
    if (connectBtn) {
      connectBtn.addEventListener('click', () => this.connect());
    }

    // 测试连接按钮
    const testBtn = document.getElementById('test-connection-btn');
    if (testBtn) {
      testBtn.addEventListener('click', () => this.testConnection());
    }

    // 发送消息
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) {
      sendBtn.addEventListener('click', () => this.sendMessage());
    }

    // 回车发送
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
      messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          this.sendMessage();
        }
      });
    }
  }

  async loadStatus() {
    try {
      const response = await this.sendToBackground({ type: 'mcp.status' });
      this.updateStatus(response.status || 'disconnected');
    } catch (error) {
      console.error('Failed to load status:', error);
      this.updateStatus('error');
    }
  }

  updateStatus(status) {
    const indicator = document.getElementById('status-indicator');
    const text = document.getElementById('status-text');
    
    if (indicator) {
      indicator.className = `status-indicator ${status}`;
    }
    
    if (text) {
      text.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    }
    
    this.isConnected = status === 'connected';
  }

  async connect() {
    try {
      this.setStatusMessage('Connecting...');
      
      const serverUrl = document.getElementById('server-url')?.value || 'http://localhost:8000';
      const didProviderUrl = document.getElementById('did-provider-url')?.value || 'http://localhost:9511';
      
      const response = await this.sendToBackground({
        type: 'mcp.init',
        config: { serverUrl, didProviderUrl }
      });

      if (response.success) {
        this.updateStatus('connected');
        this.setStatusMessage('Connected successfully');
        this.loadTools();
      } else {
        this.updateStatus('error');
        this.setStatusMessage(`Connection failed: ${response.error}`);
      }
    } catch (error) {
      this.updateStatus('error');
      this.setStatusMessage(`Connection error: ${error.message}`);
    }
  }

  async testConnection() {
    try {
      this.setStatusMessage('Testing connection...');
      
      const serverUrl = document.getElementById('server-url')?.value || 'http://localhost:8000';
      
      const response = await fetch(`${serverUrl}/mcp/capabilities`);
      if (response.ok) {
        this.setStatusMessage('Server is reachable');
      } else {
        this.setStatusMessage(`Server error: ${response.status}`);
      }
    } catch (error) {
      this.setStatusMessage(`Test failed: ${error.message}`);
    }
  }

  async loadTools() {
    try {
      const response = await this.sendToBackground({
        type: 'mcp.rpc',
        method: 'tools/list',
        params: {}
      });

      if (response.success) {
        this.displayTools(response.data);
        document.getElementById('tools-panel')?.classList.remove('hidden');
      }
    } catch (error) {
      console.error('Failed to load tools:', error);
    }
  }

  displayTools(data) {
    const toolsList = document.getElementById('tools-list');
    if (!toolsList) return;

    const tools = data.result?.tools || data.tools || ['echo', 'time'];
    
    if (tools.length === 0) {
      toolsList.innerHTML = '<div class="loading">No tools available</div>';
      return;
    }

    toolsList.innerHTML = tools.map(tool => `
      <div class="tool-item">
        <span>${tool}</span>
        <button onclick="window.mcpChat.callTool('${tool}')" class="btn btn-primary">Call</button>
      </div>
    `).join('');
  }
// 在 callTool 方法中也需要对应修改
async callTool(toolName) {
  try {
    this.setStatusMessage(`调用工具 ${toolName}...`);
    this.addMessage('user', `🔧 调用工具: ${toolName}`);
    
    const response = await this.sendToBackground({
      type: 'mcp.rpc',
      method: 'tools/call',
      params: {
        name: toolName,
        arguments: toolName === 'echo' ? { message: 'Hello from extension!' } : {}  // 这里作为属性名是安全的
      }
    });

    console.log('🔧 Tool call response:', response);

    if (response.success) {
      const result = response.data;
      let content = '';
      
      if (result.result?.content?.[0]?.text) {
        content = result.result.content[0].text;
      } else if (result.content?.[0]?.text) {
        content = result.content[0].text;
      } else {
        content = JSON.stringify(result, null, 2);
      }
      
      this.addMessage('assistant', content);
      this.setStatusMessage(`✅ 工具 ${toolName} 执行完成`);
    } else {
      this.addMessage('error', `❌ 工具 ${toolName} 失败: ${response.error}`);
      this.setStatusMessage(`❌ 工具 ${toolName} 失败`);
    }
  } catch (error) {
    console.error('❌ Tool call error:', error);
    this.addMessage('error', `❌ 工具 ${toolName} 错误: ${error.message}`);
    this.setStatusMessage(`❌ 工具 ${toolName} 错误`);
  }
}

// 在 sendMessage 方法中也需要修改
async sendMessage() {
  const input = document.getElementById('message-input');
  if (!input) return;
  
  const message = input.value.trim();
  if (!message) return;

  input.value = '';
  this.addMessage('user', message);

  if (message.startsWith('/')) {
    this.handleCommand(message);
    return;
  }

  try {
    const response = await this.sendToBackground({
      type: 'mcp.rpc',
      method: 'tools/call',
      params: {
        name: 'echo',
        arguments: { message }  // 这里作为属性名是安全的
      }
    });

    if (response.success) {
      const result = response.data;
      const content = result.result?.content?.[0]?.text || result.content?.[0]?.text || JSON.stringify(result);
      this.addMessage('assistant', content);
    } else {
      this.addMessage('error', `❌ 发送失败: ${response.error}`);
    }
  } catch (error) {
    this.addMessage('error', `❌ 发送错误: ${error.message}`);
  }
}
  addMessage(role, content) {
    const messages = document.getElementById('messages');
    if (!messages) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.textContent = content;

    messages.appendChild(messageDiv);
    messages.scrollTop = messages.scrollHeight;
  }

  setStatusMessage(message) {
    const statusMessage = document.getElementById('status-message');
    if (statusMessage) {
      statusMessage.textContent = message;
    }
  }

  sendToBackground(message) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(message, resolve);
    });
  }
}

// 初始化
const mcpChat = new MCPChatPopup();
window.mcpChat = mcpChat;