/**
 * 简化版 MCP 客户端 - 不使用 DID 认证
 */
class SimpleMCPClient {
  constructor(options = {}) {
    this.serverUrl = options.serverUrl || 'http://localhost:8000';
    this.timeout = options.timeout || 30000;
    this.isInitialized = false;
    
    console.log('SimpleMCPClient constructed with options:', options);
  }

  /**
   * 初始化客户端
   */
  async initialize() {
    console.log('SimpleMCPClient.initialize() called');
    
    try {
      // 测试服务器连接
      await this.getCapabilities();
      this.isInitialized = true;
      console.log('Simple MCP Client 初始化完成');
      return true;
    } catch (error) {
      console.error('Simple MCP Client 初始化失败:', error);
      this.isInitialized = false;
      throw error;
    }
  }

  /**
   * 发送简单的 RPC 请求（不使用 DID 认证）
   */
  async rpc(method, params = {}) {
    console.log('SimpleMCPClient.rpc called:', { method, params });
    
    if (!this.isInitialized) {
      throw new Error('Simple MCP Client not initialized');
    }

    const requestData = {
      jsonrpc: '2.0',
      method: method,
      params: params,
      id: `req_${Date.now()}`
    };

    console.log('Simple request data:', requestData);

    try {
      const response = await fetch(`${this.serverUrl}/mcp/rpc`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(requestData),
        mode: 'cors'
      });

      console.log('Simple MCP RPC response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Simple MCP RPC error response:', errorText);
        throw new Error(`Simple MCP RPC 调用失败: ${response.status} - ${errorText}`);
      }

      const result = await response.json();
      console.log('Simple MCP RPC response:', result);
      
      return result;
    } catch (error) {
      console.error('Simple rpc error:', error);
      throw new Error(`简单 RPC 请求失败: ${error.message}`);
    }
  }

  /**
   * 调用工具
   */
  async callTool(toolName, arguments = {}) {
    console.log('SimpleMCPClient.callTool called:', { toolName, arguments });
    return await this.rpc('tools/call', {
      name: toolName,
      arguments: arguments
    });
  }

  /**
   * 列出可用工具
   */
  async listTools() {
    console.log('SimpleMCPClient.listTools called');
    return await this.rpc('tools/list', {});
  }

  /**
   * 获取 MCP 服务能力
   */
  async getCapabilities() {
    console.log('SimpleMCPClient.getCapabilities called');
    
    try {
      const response = await fetch(`${this.serverUrl}/mcp/capabilities`, {
        method: 'GET',
        headers: { 
          'Accept': 'application/json'
        },
        mode: 'cors'
      });
      
      if (!response.ok) {
        throw new Error(`Failed to get capabilities: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('getCapabilities error:', error);
      throw error;
    }
  }
}

// 导出类
if (typeof module !== 'undefined' && module.exports) {
  module.exports = SimpleMCPClient;
} else {
  window.SimpleMCPClient = SimpleMCPClient;
}