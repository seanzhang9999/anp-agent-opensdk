/**
 * MCP Chat Extension Background Script
 * 完全兼容Python DID认证的版本
 */

let mcpClient = null;
let connectionStatus = 'disconnected';
let keepAliveInterval = null;

console.log('Background script loaded at:', new Date().toISOString());

/**
 * 完全兼容的MCP客户端
 */
class ServiceWorkerMCPClient {
  constructor(options = {}) {
    this.serverUrl = options.serverUrl || 'http://localhost:8000';
    this.didProviderUrl = options.didProviderUrl || 'http://localhost:9511';
    this.timeout = options.timeout || 30000;
    this._did = null;
    this.isInitialized = false;
    
    console.log('ServiceWorkerMCPClient constructed with options:', options);
  }

  /**
   * 初始化客户端 - 必须获取DID才能工作
   */
  async initialize() {
    console.log('ServiceWorkerMCPClient.initialize() called');
    
    try {
      // 必须先获取DID，因为服务器要求认证
      console.log('Getting DID from provider...');
      
      // 测试DID Provider健康状态
      const didHealthResponse = await fetch(`${this.didProviderUrl}/health`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' }
      });
      
      if (!didHealthResponse.ok) {
        throw new Error(`DID Provider health check failed: ${didHealthResponse.status}`);
      }
      
      const healthData = await didHealthResponse.json();
      console.log('DID Provider health:', healthData);
      
      // 获取DID
      const didResponse = await fetch(`${this.didProviderUrl}/did`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' }
      });
      
      if (!didResponse.ok) {
        const errorText = await didResponse.text();
        throw new Error(`Failed to get DID: ${didResponse.status} - ${errorText}`);
      }
      
      const didData = await didResponse.json();
      this._did = didData.did;
      console.log('Got DID:', this._did);
      
      // 测试MCP服务器连接
      const capabilitiesResponse = await fetch(`${this.serverUrl}/mcp/capabilities`);
      if (!capabilitiesResponse.ok) {
        throw new Error(`MCP server not available: ${capabilitiesResponse.status}`);
      }
      
      // 测试签名功能
      console.log('Testing signature generation...');
      const testSignature = await this.signPayload('test_payload');
      console.log('Test signature successful:', testSignature);
      
      this.isInitialized = true;
      console.log('MCP Client初始化完成 (DID认证模式)');
      return true;
      
    } catch (error) {
      console.error('MCP Client初始化失败:', error);
      this.isInitialized = false;
      throw error;
    }
  }

  /**
   * 生成DID签名
   */
  async signPayload(payload) {
    console.log('Signing payload:', payload);
    
    const response = await fetch(`${this.didProviderUrl}/sign`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ payload })
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Sign error response:', errorText);
      throw new Error(`Failed to sign payload: ${response.status} - ${errorText}`);
    }

    const data = await response.json();
    console.log('Sign response:', data);
    
    if (!data.jws) {
      throw new Error('No JWS signature in response');
    }
    
    return data.jws;
  }

  /**
   * 发送RPC请求 - 严格按照Python版本实现
   */
  async rpc(method, params = {}) {
    console.log('ServiceWorkerMCPClient.rpc called:', { method, params });
    
    if (!this.isInitialized || !this._did) {
      throw new Error('MCP Client not initialized or DID not available');
    }

    // 1. 构建请求数据 - 完全按照Python版本
    const timestamp = Math.floor(Date.now() / 1000);
    const requestData = {
      jsonrpc: '2.0',
      method: method,
      params: params,
      id: `req_${timestamp}`,
      __meta: {
        ts: timestamp
      }
    };

    console.log('Request data structure:', requestData);

    // 2. 生成认证签名 - 与Python版本保持一致
    const payloadData = {
      method: method,
      params: params,
      timestamp: timestamp
    };
    
    // 关键：使用与Python完全相同的JSON序列化
    // Python: json.dumps(payload_data, sort_keys=True)
    const sortedKeys = Object.keys(payloadData).sort();
    const sortedPayloadData = {};
    sortedKeys.forEach(key => {
      sortedPayloadData[key] = payloadData[key];
    });
    
    const payload = JSON.stringify(sortedPayloadData);
    console.log('Payload for signing (Python compatible):', payload);
    console.log('Payload data keys order:', sortedKeys);
    
    let signature;
    try {
      signature = await this.signPayload(payload);
      console.log('Generated signature:', signature);
    } catch (signError) {
      console.error('Failed to generate signature:', signError);
      throw new Error(`DID signing failed: ${signError.message}`);
    }

    // 3. 构建认证头 - 按照Python版本格式
    const authTokenData = {
      did: this._did,
      signature: signature
    };
    const authToken = JSON.stringify(authTokenData);
    console.log('Auth token data:', authTokenData);

    const headers = {
      'Authorization': `Bearer ${authToken}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };

    console.log('Request headers:', headers);
    console.log('Final request body:', JSON.stringify(requestData));

    // 4. 发送请求
    try {
      const response = await fetch(`${this.serverUrl}/mcp/rpc`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(requestData)
      });

      console.log('MCP RPC response status:', response.status);
      console.log('MCP RPC response headers:', Object.fromEntries(response.headers.entries()));

      if (!response.ok) {
        const errorText = await response.text();
        console.error('MCP RPC error response:', errorText);
        
        // 详细的错误分析
        if (response.status === 401) {
          throw new Error(`DID认证失败: ${errorText}`);
        } else if (response.status === 403) {
          throw new Error(`访问被拒绝: ${errorText}`);
        } else {
          throw new Error(`MCP RPC调用失败: ${response.status} - ${errorText}`);
        }
      }

      const result = await response.json();
      console.log('MCP RPC response:', result);
      
      return result;
      
    } catch (fetchError) {
      console.error('Fetch error:', fetchError);
      throw new Error(`RPC请求失败: ${fetchError.message}`);
    }
  }

  /**
   * 调用工具
   */
  async callTool(toolName, toolArguments = {}) {
    console.log('ServiceWorkerMCPClient.callTool called:', { toolName, toolArguments });
    return await this.rpc('tools/call', {
      name: toolName,
      arguments: toolArguments
    });
  }

  /**
   * 列出可用工具
   */
  async listTools() {
    console.log('ServiceWorkerMCPClient.listTools called');
    return await this.rpc('tools/list', {});
  }

  /**
   * 获取MCP服务能力
   */
  async getCapabilities() {
    console.log('ServiceWorkerMCPClient.getCapabilities called');
    
    const response = await fetch(`${this.serverUrl}/mcp/capabilities`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    });
    
    if (!response.ok) {
      throw new Error(`Failed to get capabilities: ${response.status}`);
    }
    
    return await response.json();
  }
}

/**
 * 保活机制
 */
function setupKeepAlive() {
  if (keepAliveInterval) {
    clearInterval(keepAliveInterval);
  }
  
  keepAliveInterval = setInterval(() => {
    console.log('🔄 Service Worker keepalive ping:', new Date().toISOString());
    chrome.storage.local.set({ lastPing: Date.now() }).catch(console.error);
  }, 15000);
  
  console.log('✅ KeepAlive mechanism started');
}

/**
 * 初始化MCP客户端
 */
async function initializeMCP(config = {}) {
  console.log('🚀 Initializing MCP with config:', config);
  
  const defaultConfig = {
    serverUrl: 'http://localhost:8000',
    didProviderUrl: 'http://localhost:9511'
  };
  
  const mcpConfig = { ...defaultConfig, ...config };
  console.log('📋 Final MCP config:', mcpConfig);
  
  setupKeepAlive();
  
  try {
    console.log('🔧 Creating ServiceWorker MCP client...');
    mcpClient = new ServiceWorkerMCPClient(mcpConfig);
    
    console.log('⚡ Initializing ServiceWorker MCP client...');
    await mcpClient.initialize();
    
    connectionStatus = 'connected';
    
    console.log('🎉 MCP客户端初始化成功 (DID认证模式)');
    
    broadcastMessage({ 
      type: 'mcp.connected', 
      config: mcpConfig,
      mode: 'full',
      message: '完整DID认证模式连接成功',
      timestamp: Date.now()
    });
    
    return { success: true, status: connectionStatus, mode: 'full' };
    
  } catch (error) {
    console.error('❌ MCP initialization failed:', error);
    connectionStatus = 'error';
    
    // 提供更详细的错误信息
    let errorMessage = error.message;
    if (errorMessage.includes('DID Provider')) {
      errorMessage = 'DID认证服务不可用，请确保demo_mcp_anp_did_auth_fixed.py正在运行';
    } else if (errorMessage.includes('MCP server')) {
      errorMessage = 'MCP服务器不可用，请确保端口8000可访问';
    }
    
    broadcastMessage({ 
      type: 'mcp.error', 
      error: errorMessage,
      originalError: error.message,
      timestamp: Date.now()
    });
    
    return { success: false, error: errorMessage, status: connectionStatus };
  }
}

/**
 * 广播消息给popup
 */
function broadcastMessage(message) {
  console.log('📡 Broadcasting message:', message);
  chrome.storage.local.set({ 
    lastMessage: { ...message, timestamp: Date.now() } 
  }).then(() => {
    console.log('✅ Message broadcasted successfully');
  }).catch(error => {
    console.error('❌ Failed to broadcast message:', error);
  });
}

/**
 * 安全的响应发送
 */
function sendResponseSafely(sendResponse, data) {
  try {
    sendResponse(data);
    console.log('📤 Response sent:', data);
  } catch (error) {
    console.error('❌ Failed to send response:', error);
  }
}

/**
 * 处理来自popup和content script的消息
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('📨 Background received message:', message.type, 'from:', sender.tab ? 'content' : 'popup');

  const handleMessage = async () => {
    try {
      switch (message.type) {
        case 'mcp.init':
          console.log('🔄 Handling mcp.init...');
          const initResult = await initializeMCP(message.config);
          console.log('✅ Init result:', initResult);
          return initResult;

        case 'mcp.rpc':
          console.log('🔄 Handling mcp.rpc...');
          const rpcResult = await handleMCPRPC(message);
          console.log('✅ RPC result:', rpcResult);
          return rpcResult;

        case 'mcp.status':
          console.log('🔄 Handling mcp.status...');
          const statusResult = { 
            status: connectionStatus, 
            hasClient: !!mcpClient,
            isInitialized: mcpClient?.isInitialized || false,
            mode: 'full',
            timestamp: Date.now()
          };
          console.log('✅ Status result:', statusResult);
          return statusResult;

        case 'mcp.ping':
          console.log('🏓 Handling ping...');
          setupKeepAlive();
          return { 
            type: 'pong', 
            timestamp: Date.now(),
            message: 'Service Worker is active'
          };

        default:
          return { success: false, error: `Unknown message type: ${message.type}` };
      }
    } catch (error) {
      console.error('❌ Error handling message:', error);
      return { success: false, error: error.message };
    }
  };

  handleMessage()
    .then(result => sendResponseSafely(sendResponse, result))
    .catch(error => {
      console.error('❌ Message handler error:', error);
      sendResponseSafely(sendResponse, { success: false, error: error.message });
    });

  return true;
});

/**
 * 处理MCP RPC调用
 */
async function handleMCPRPC(message) {
  console.log('🔄 handleMCPRPC called with:', message);
  
  try {
    if (!mcpClient || !mcpClient.isInitialized) {
      throw new Error('MCP client not initialized');
    }

    let result;
    const startTime = Date.now();
    
    switch (message.method) {
      case 'tools/list':
        console.log('📋 Calling listTools...');
        result = await mcpClient.listTools();
        break;
      case 'tools/call':
        console.log('🔧 Calling callTool with:', message.params);
        result = await mcpClient.callTool(message.params.name, message.params.arguments);
        break;
      default:
        console.log('⚡ Calling generic rpc...');
        result = await mcpClient.rpc(message.method, message.params);
    }

    const duration = Date.now() - startTime;
    console.log(`✅ RPC completed in ${duration}ms:`, result);
    
    return { success: true, data: result, duration };
  } catch (error) {
    console.error('❌ MCP RPC error:', error);
    return { success: false, error: error.message };
  }
}

// 事件监听
chrome.runtime.onInstalled.addListener((details) => {
  console.log('🎉 MCP Chat Extension installed:', details.reason);
  setupKeepAlive();
});

chrome.runtime.onStartup.addListener(() => {
  console.log('🚀 MCP Chat Extension startup');
  setupKeepAlive();
});

setupKeepAlive();
console.log('✅ Background script setup complete at:', new Date().toISOString());