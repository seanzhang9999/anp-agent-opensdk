/**
 * MCP客户端 - 基于demo_mcp_anp_did_auth.py中的MCPClientWithDID类
 * 支持DID认证的MCP (Model Context Protocol) 客户端
 */
/**
 * MCP客户端 - 修复版本
 */
class MCPClient {
  constructor(options = {}) {
    this.serverUrl = options.serverUrl || 'http://localhost:8000';
    this.didProviderUrl = options.didProviderUrl || 'http://localhost:9511';
    this.timeout = options.timeout || 30000;
    this._did = null;
    this.isInitialized = false;
    
    console.log('MCPClient constructed with options:', options);
  }

  /**
   * 初始化客户端
   */
  async initialize() {
    console.log('MCPClient.initialize() called');
    
    try {
      // 从DID Provider获取DID
      console.log('Getting DID from provider...');
      this._did = await this.getDIDFromProvider();
      console.log('Got DID:', this._did);
      
      this.isInitialized = true;
      console.log(`MCP Client初始化完成，DID: ${this._did}`);
      return true;
    } catch (error) {
      console.error('MCP Client初始化失败:', error);
      this.isInitialized = false;
      throw error;
    }
  }

  /**
   * 从DID Provider获取DID
   */
  async getDIDFromProvider() {
    console.log('Getting DID from:', `${this.didProviderUrl}/did`);
    
    try {
      const response = await fetch(`${this.didProviderUrl}/did`, {
        method: 'GET',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        mode: 'cors'  // 明确指定CORS模式
      });

      console.log('DID Provider response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('DID Provider error response:', errorText);
        throw new Error(`Failed to get DID: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      console.log('DID Provider response data:', data);
      
      if (!data.did) {
        throw new Error('No DID in response');
      }
      
      return data.did;
    } catch (error) {
      console.error('getDIDFromProvider error:', error);
      throw new Error(`DID Provider连接失败: ${error.message}`);
    }
  }

  /**
   * 生成DID签名
   */
  async signPayload(payload) {
    console.log('Signing payload:', payload);
    
    try {
      const response = await fetch(`${this.didProviderUrl}/sign`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ payload }),
        mode: 'cors'
      });

      console.log('Sign response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Sign error response:', errorText);
        throw new Error(`Failed to sign payload: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      console.log('Sign response data:', data);
      
      return data.jws;
    } catch (error) {
      console.error('signPayload error:', error);
      throw new Error(`签名失败: ${error.message}`);
    }
  }

  /**
   * 发送RPC请求
   */
  async rpc(method, params = {}) {
    console.log('MCPClient.rpc called:', { method, params });
    
    if (!this.isInitialized) {
      throw new Error('MCP Client not initialized');
    }

    // 1. 构建请求数据
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

    console.log('Request data:', requestData);

    // 2. 生成认证签名
    const payloadData = {
      method: method,
      params: params,
      timestamp: timestamp
    };
    const payload = JSON.stringify(payloadData, Object.keys(payloadData).sort());
    console.log('Payload for signing:', payload);
    
    const signature = await this.signPayload(payload);
    console.log('Generated signature:', signature);

    // 3. 构建认证头
    const authToken = JSON.stringify({
      did: this._did,
      signature: signature
    });

    console.log('Auth token:', authToken);

    // 4. 发送请求
    try {
      const response = await fetch(`${this.serverUrl}/mcp/rpc`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(requestData),
        mode: 'cors'
      });

      console.log('MCP RPC response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('MCP RPC error response:', errorText);
        throw new Error(`MCP RPC调用失败: ${response.status} - ${errorText}`);
      }

      const result = await response.json();
      console.log('MCP RPC response:', result);
      
      return result;
    } catch (error) {
      console.error('rpc error:', error);
      throw new Error(`RPC请求失败: ${error.message}`);
    }
  }

  /**
   * 调用工具
   */
  async callTool(toolName, arguments = {}) {
    console.log('MCPClient.callTool called:', { toolName, arguments });
    return await this.rpc('tools/call', {
      name: toolName,
      arguments: arguments
    });
  }

  /**
   * 列出可用工具
   */
  async listTools() {
    console.log('MCPClient.listTools called');
    return await this.rpc('tools/list', {});
  }

  /**
   * 获取MCP服务能力
   */
  async getCapabilities() {
    console.log('MCPClient.getCapabilities called');
    
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

  /**
   * 检查连接状态
   */
  async checkConnection() {
    try {
      await this.getCapabilities();
      return true;
    } catch (error) {
      console.error('Connection check failed:', error);
      return false;
    }
  }
}

// 导出类
if (typeof module !== 'undefined' && module.exports) {
  module.exports = MCPClient;
} else {
  window.MCPClient = MCPClient;
}