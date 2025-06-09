/**
 * Content Script for MCP Chat Extension - 修复版本
 */

// 检查是否已经注入
if (!window.mcpChatInjected) {
  window.mcpChatInjected = true;

  console.log('MCP Chat Extension content script loaded');

  // 检查扩展上下文是否有效
  function isExtensionContextValid() {
    try {
      chrome.runtime.getURL('');
      return true;
    } catch (error) {
      console.log('Extension context is invalid:', error.message);
      return false;
    }
  }

  // 安全的消息发送函数
  function sendMessageSafely(message, callback) {
    if (!isExtensionContextValid()) {
      console.log('Extension context invalid, cannot send message');
      if (callback) callback({ error: 'Extension context invalid' });
      return;
    }

    try {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          console.log('Runtime error:', chrome.runtime.lastError.message);
          if (callback) callback({ error: chrome.runtime.lastError.message });
        } else {
          if (callback) callback(response);
        }
      });
    } catch (error) {
      console.log('Failed to send message:', error.message);
      if (callback) callback({ error: error.message });
    }
  }

  // 创建浮动按钮
  function createFloatingButton() {
    const button = document.createElement('div');
    button.id = 'mcp-chat-float-btn';
    button.innerHTML = '💬';
    button.title = 'Open MCP Chat (Ctrl+Shift+M)';
    
    // 设置样式
    Object.assign(button.style, {
      position: 'fixed',
      top: '20px',
      right: '20px',
      width: '50px',
      height: '50px',
      background: '#2196F3',
      color: 'white',
      borderRadius: '50%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: '20px',
      cursor: 'pointer',
      zIndex: '10000',
      boxShadow: '0 2px 10px rgba(0,0,0,0.2)',
      transition: 'all 0.3s ease',
      fontFamily: 'Arial, sans-serif'
    });

    // 添加事件监听
    button.addEventListener('click', openMCPChat);
    button.addEventListener('mouseenter', () => {
      button.style.transform = 'scale(1.1)';
    });
    button.addEventListener('mouseleave', () => {
      button.style.transform = 'scale(1)';
    });

    document.body.appendChild(button);
    return button;
  }

  // 打开MCP Chat
  function openMCPChat() {
    console.log('Opening MCP Chat...');
    
    // 方法1：尝试通过消息通信
    sendMessageSafely({ 
      type: 'open_popup',
      source: 'content_script' 
    }, (response) => {
      if (response && response.error) {
        console.log('Failed to open via message:', response.error);
        // 方法2：尝试直接操作
        openPopupDirectly();
      } else {
        console.log('Open popup message sent successfully');
      }
    });
  }

  // 直接打开弹窗的备用方法
  function openPopupDirectly() {
    // 显示提示信息
    showNotification('请点击浏览器右上角的MCP Chat扩展图标');
  }

  // 显示通知
  function showNotification(message) {
    const notification = document.createElement('div');
    notification.style.cssText = `
      position: fixed;
      top: 80px;
      right: 20px;
      background: #2196F3;
      color: white;
      padding: 12px 16px;
      border-radius: 8px;
      font-size: 14px;
      font-family: Arial, sans-serif;
      z-index: 10001;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      max-width: 300px;
      animation: slideIn 0.3s ease-out;
    `;

    notification.textContent = message;

    // 添加关闭按钮
    const closeBtn = document.createElement('span');
    closeBtn.style.cssText = `
      position: absolute;
      top: 4px;
      right: 8px;
      cursor: pointer;
      font-size: 16px;
      font-weight: bold;
    `;
    closeBtn.textContent = '×';
    closeBtn.addEventListener('click', () => {
      notification.remove();
    });

    notification.appendChild(closeBtn);
    document.body.appendChild(notification);

    // 3秒后自动移除
    setTimeout(() => {
      if (notification.parentElement) {
        notification.remove();
      }
    }, 3000);

    // 添加CSS动画
    if (!document.getElementById('mcp-chat-animations')) {
      const style = document.createElement('style');
      style.id = 'mcp-chat-animations';
      style.textContent = `
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `;
      document.head.appendChild(style);
    }
  }

  // 设置键盘快捷键
  function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Ctrl+Shift+M 打开MCP Chat
      if (e.ctrlKey && e.shiftKey && e.key === 'M') {
        e.preventDefault();
        openMCPChat();
      }
    });
  }

  // 监听来自background的消息
  function setupMessageListener() {
    if (!isExtensionContextValid()) {
      console.log('Cannot setup message listener: extension context invalid');
      return;
    }

    try {
      chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        console.log('Content script received message:', message);

        try {
          switch (message.type) {
            case 'get_page_info':
              const pageInfo = {
                url: window.location.href,
                title: document.title,
                selectedText: window.getSelection().toString().trim()
              };
              console.log('Sending page info:', pageInfo);
              sendResponse(pageInfo);
              break;
            
            case 'inject_result':
              if (message.data) {
                showResult(message.data);
              }
              sendResponse({ success: true });
              break;
            
            case 'ping':
              sendResponse({ type: 'pong', timestamp: Date.now() });
              break;
            
            default:
              console.log('Unknown message type:', message.type);
              sendResponse({ error: 'Unknown message type' });
          }
        } catch (error) {
          console.error('Error handling message:', error);
          sendResponse({ error: error.message });
        }

        // 对于异步响应，返回true
        return true;
      });
    } catch (error) {
      console.error('Failed to setup message listener:', error);
    }
  }

  // 显示结果
  function showResult(data) {
    const resultDiv = document.createElement('div');
    resultDiv.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: white;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 20px;
      max-width: 400px;
      max-height: 300px;
      overflow: auto;
      z-index: 10001;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
      font-family: Arial, sans-serif;
    `;

    const content = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
    
    resultDiv.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <h3 style="margin: 0; color: #333;">MCP Result</h3>
        <button onclick="this.parentElement.parentElement.remove()" 
                style="background: none; border: none; font-size: 18px; cursor: pointer;">×</button>
      </div>
      <div style="color: #666; line-height: 1.4; white-space: pre-wrap;">
        ${content}
      </div>
    `;

    document.body.appendChild(resultDiv);

    // 5秒后自动移除
    setTimeout(() => {
      if (resultDiv.parentElement) {
        resultDiv.remove();
      }
    }, 5000);
  }

  // 初始化函数
  function initialize() {
    try {
      // 检查扩展上下文
      if (!isExtensionContextValid()) {
        console.log('Extension context invalid during initialization');
        return;
      }

      createFloatingButton();
      setupKeyboardShortcuts();
      setupMessageListener();
      console.log('MCP Chat content script initialized successfully');
    } catch (error) {
      console.error('Failed to initialize MCP Chat content script:', error);
    }
  }

  // 等待DOM加载完成后初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
  } else {
    initialize();
  }

  // 监听扩展上下文变化
  const checkContextInterval = setInterval(() => {
    if (!isExtensionContextValid()) {
      console.log('Extension context lost, cleaning up...');
      clearInterval(checkContextInterval);
      
      // 移除创建的元素
      const floatBtn = document.getElementById('mcp-chat-float-btn');
      if (floatBtn) {
        floatBtn.remove();
      }
      
      // 标记为未注入，允许重新注入
      window.mcpChatInjected = false;
    }
  }, 5000); // 每5秒检查一次
}