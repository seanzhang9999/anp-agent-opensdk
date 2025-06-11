document.addEventListener('DOMContentLoaded', () => {
  // Views
  const loginView = document.getElementById('login-view');
  const mainView = document.getElementById('main-view');

  // Login Elements
  const loginForm = document.getElementById('login-form');
  const usernameInput = document.getElementById('username');
  const passwordInput = document.getElementById('password');
  const loginError = document.getElementById('login-error');

  // Main View Elements
  const settingsBtn = document.getElementById('settings-btn');
  const logoutBtn = document.getElementById('logout-btn');
  const configPanel = document.getElementById('config-panel');
  const configForm = document.getElementById('config-form');
  const messageForm = document.getElementById('message-form');
  const messageInput = document.getElementById('message-input');
  const messagesContainer = document.getElementById('messages');
  const userInfo = document.getElementById('user-info');
  const chatModeSwitcher = document.getElementById('chat-mode-switcher');

  // App State
  let currentUser = null;
  let chatMode = 'generic'; // 'generic' or 'agent'
  let llmConfig = {};

  // --- Initialization ---
  const init = async () => {
    // Load LLM config first
    llmConfig = await loadConfig();
    updateConfigForm(llmConfig);

    const closeConfigBtn = document.getElementById('close-config-btn');
    if (closeConfigBtn) {
      closeConfigBtn.addEventListener('click', toggleConfigPanel);
    }
    // Check for logged in user
    const storedUser = await getStoredUser();
    if (storedUser) {
      currentUser = storedUser;
      showMainView();
      await refreshUserDid(); // 加载时刷新did
    } else {
      showLoginView();
    }

    // Add all event listeners
    loginForm.addEventListener('submit', handleLogin);
    logoutBtn.addEventListener('click', handleLogout);
    settingsBtn.addEventListener('click', toggleConfigPanel);
    configForm.addEventListener('submit', handleConfigSave);
    messageForm.addEventListener('submit', handleSendMessage);
    chatModeSwitcher.addEventListener('click', handleModeSwitch);
  };

  // --- User & Auth ---
  const getStoredUser = () => {
    return new Promise(resolve => {
      chrome.storage.local.get(['currentUser'], result => resolve(result.currentUser));
    });
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    loginError.textContent = '';
    const username = usernameInput.value;
    const password = passwordInput.value;

    try {
      const response = await fetch('http://localhost:8000/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.detail || data.message || 'Login failed');
      }

      currentUser = data.user;
      chrome.storage.local.set({ currentUser: data.user }, () => {
        showMainView();
        refreshUserDid(); // 登录后刷新did
      });
    } catch (error) {
      loginError.textContent = error.message;
      console.error('Login error:', error);
    }
  };

  const handleLogout = () => {
    chrome.storage.local.remove('currentUser', () => {
      showLoginView();
    });
  };

  // 新增：刷新did信息
  const refreshUserDid = async () => {
    if (!currentUser || !currentUser.username) return;
    try {
      const response = await fetch('http://localhost:8000/auth/userinfo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: currentUser.username })
    });
    const data = await response.json();
      if (response.ok && data.did) {
        currentUser.did = data.did;
        chrome.storage.local.set({ currentUser });
        // 显示 did
        const didDisplay = document.getElementById('user-did');
        if (didDisplay) {
          didDisplay.textContent = `${data.did}`;
          didDisplay.style.display = 'block';
    }
      }
    } catch (error) {
      console.error('刷新DID失败:', error);
    }
  };

  // --- View Management ---
  const showLoginView = () => {
    currentUser = null;
    mainView.style.display = 'none';
    loginView.style.display = 'block';
    loginError.textContent = '';
  };

  const showMainView = () => {
    if (!currentUser) return;
    userInfo.textContent = `User: ${currentUser.username}`;
    loginView.style.display = 'none';
    mainView.style.display = 'block';
    refreshUserDid(); // 切换到主界面时也刷新did
  };

  // --- Chat Logic ---
  const handleModeSwitch = (e) => {
    if (e.target.classList.contains('chat-mode')) {
      chatMode = e.target.dataset.mode;
      document.querySelector('.chat-mode.active-mode').classList.remove('active-mode');
      e.target.classList.add('active-mode');
      // Optional: Clear chat history on mode switch
      messagesContainer.innerHTML = '';
      addMessage('system', `Switched to ${chatMode === 'generic' ? 'Generic LLM' : 'Personal Agent'} mode.`);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    const messageText = messageInput.value.trim();
    if (!messageText) return;

    addMessage('user', messageText);
    messageInput.value = '';
    addMessage('assistant', '...', true); // Show thinking indicator

    try {
      let reply;
      if (chatMode === 'agent') {
        if (!currentUser) throw new Error("Not logged in.");
        reply = await fetchAgentReply(messageText);
      } else {
        reply = await fetchGenericReply(messageText);
      }
      updateLastMessage('assistant', reply);
    } catch (error) {
      console.error('Error sending message:', error);
      updateLastMessage('system', `Error: ${error.message}`);
    }
    };

  const fetchAgentReply = async (message) => {
    const { username, did } = currentUser || {};
    if (!username && !did) {
      throw new Error('用户信息不完整，无法发送消息');
    }

    const body = {
      username,
      did,
      message
  };

    const response = await fetch('http://localhost:8000/agent/chat/agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.error || data.message || 'Agent request failed');
    }
    return data.reply;
  };

  const fetchGenericReply = async (message) => {
    if (!llmConfig.apiBase || !llmConfig.apiKey) {
      throw new Error('API Base URL or API Key is not configured.');
    }
    const response = await fetch(`${llmConfig.apiBase}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${llmConfig.apiKey}`
      },
      body: JSON.stringify({
        model: llmConfig.model,
        messages: [{ role: 'user', content: message }],
        stream: false
      })
    });
    const data = await response.json();
    if (!response.ok) {
      const errorMsg = data.error?.message || 'Failed to fetch response from LLM.';
      throw new Error(errorMsg);
    }
    return data.choices[0].message.content;
  };

  // --- UI & Config Helpers ---
  const addMessage = (role, content, isLoading = false) => {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.textContent = content;
    if (isLoading) {
      messageDiv.classList.add('loading');
    }
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  };

  const updateLastMessage = (role, content) => {
    const lastMessage = messagesContainer.querySelector('.message.loading');
    if (lastMessage) {
      lastMessage.textContent = content;
      lastMessage.classList.remove('loading');
      lastMessage.className = `message ${role}`;
    }
  };

  const toggleConfigPanel = () => {
    configPanel.style.display = configPanel.style.display === 'none' ? 'block' : 'none';
  };

  const handleConfigSave = async (e) => {
    e.preventDefault();
    const newConfig = {
      apiBase: document.getElementById('api-base').value,
      apiKey: document.getElementById('api-key').value,
      model: document.getElementById('model').value
    };
    await saveConfig(newConfig);
    llmConfig = newConfig;
    alert('Configuration saved!');
    toggleConfigPanel();
  };

  const saveConfig = (config) => {
    return new Promise(resolve => {
      chrome.storage.local.set({ llmConfig: config }, resolve);
});
  };

  const loadConfig = () => {
    return new Promise(resolve => {
      chrome.storage.local.get({
        llmConfig: { apiBase: '', apiKey: '', model: 'gpt-3.5-turbo' }
      }, result => resolve(result.llmConfig));
    });
  };

  const updateConfigForm = (config) => {
    const apiBaseInput = document.getElementById('api-base');
    const apiKeyInput = document.getElementById('api-key');
    const modelInput = document.getElementById('model');
    if (apiBaseInput) apiBaseInput.value = config.apiBase || '';
    if (apiKeyInput) apiKeyInput.value = config.apiKey || '';
    if (modelInput) modelInput.value = config.model || 'gpt-3.5-turbo';
  };

  // Start the application
  init();
});
