// DOM元素
const serverStatusEl = document.getElementById('server-status');
const chatStatusEl = document.getElementById('chat-status');
const toggleServerBtn = document.getElementById('toggle-server');
const toggleChatBtn = document.getElementById('toggle-chat');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const recommendButton = document.getElementById('recommend-button');
const chatMessages = document.getElementById('chat-messages');
const bookmarksList = document.getElementById('bookmarks-list');
const agentNameInput = document.getElementById('agent-name');
const loadBookmarksLocalBtn = document.getElementById('load-bookmarks-local');
const loadBookmarksUrlBtn = document.getElementById('load-bookmarks-url');
const clearHistoryBtn = document.getElementById('clear-history');

// 状态变量
let serverRunning = false;
let chatRunning = false;
let bookmarks = [];

// API端点
const API_BASE = '';
const API_ENDPOINTS = {
    serverStart: '/api/server/start',
    serverStop: '/api/server/stop',
    serverStatus: '/api/server/status',
    chatStart: '/api/chat/start',
    chatStop: '/api/chat/stop',
    chatStatus: '/api/chat/status',
    sendMessage: '/api/chat/send',
    getBookmarks: '/api/bookmarks',
    addBookmark: '/api/bookmarks/add',
    discoverAgent: '/api/discoveragent/'
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 检查服务器和聊天状态
    checkServerStatus();
    loadBookmarks();
    loadChatHistory(); // 加载聊天历史
    
    // 事件监听器
    toggleServerBtn.addEventListener('click', toggleServer);
    toggleChatBtn.addEventListener('click', toggleChat);
    sendButton.addEventListener('click', sendMessage);
    recommendButton.addEventListener('click', recommendAgent);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
    loadBookmarksLocalBtn.addEventListener('click', () => {
        loadBookmarks(); // 本地加载，不传URL参数
    });
    
    loadBookmarksUrlBtn.addEventListener('click', () => {
        const url = agentNameInput.value.trim() || 'http://localhost:8080/api/public/instances';
        loadBookmarks(url); // 网络加载，传入URL参数
    });
    clearHistoryBtn.addEventListener('click', clearChatHistory);
});

// 加载聊天历史
async function loadChatHistory() {
    try {
        const response = await fetch('/api/chat/history');
        const data = await response.json();
        
        if (data.success && data.history && data.history.length > 0) {
            // 清空当前消息区域
            chatMessages.innerHTML = '';
            
            // 添加历史消息
            data.history.forEach(item => {
                if (item.type === 'user') {
                    addUserMessage(item.message);
                } else if (item.type === 'assistant') {
                    addAssistantMessage(item.message);
                } else if (item.type === 'anp_nlp') {
                    // 添加智能体消息，使用与助手消息相同的样式但添加特殊标记
                    const messageEl = document.createElement('div');
                    messageEl.className = 'message assistant-message agent-response';
                    if (item.timestamp) {
                        messageEl.setAttribute('data-timestamp', item.timestamp);
                    }
                    messageEl.textContent = item.message;
                    chatMessages.appendChild(messageEl);
                } else if (item.type === 'system') {
                    addSystemMessage(item.message);
                }
            });
            
            // 滚动到底部
            scrollToBottom();
        }
    } catch (error) {
        console.error('加载聊天历史出错:', error);
    }
}

// 清除聊天历史
async function clearChatHistory() {
    try {
        const response = await fetch('/api/chat/clear-history', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            // 清空当前消息区域
            chatMessages.innerHTML = '';
            // 不添加系统消息，保持界面完全清空
        }
    } catch (error) {
        console.error('清除聊天历史出错:', error);
    }
}

// 检查服务器状态
async function checkServerStatus() {
    try {
        const response = await fetch(API_ENDPOINTS.serverStatus);
        const data = await response.json();
        
        serverRunning = data.running;
        updateServerStatus();
        
        // 如果服务器在运行 检查聊天状态
        if (serverRunning) {
            // 如果有DID信息，显示它
            if (data.did_id && data.did_document_path) {
                addSystemMessage(`DID ID: ${data.did_id}\nDID文档路径: ${data.did_document_path}`);
            }
            checkChatStatus();
        }
    } catch (error) {
        console.error('检查服务器状态出错:', error);
        serverRunning = false;
        updateServerStatus();
    }
}

// 检查聊天状态
async function checkChatStatus() {
    try {
        const response = await fetch(API_ENDPOINTS.chatStatus);
        const data = await response.json();
        
        chatRunning = data.running;
        updateChatStatus();
    } catch (error) {
        console.error('检查聊天状态出错:', error);
        chatRunning = false;
        updateChatStatus();
    }
}

// 更新服务器状态UI
function updateServerStatus() {
    if (serverRunning) {
        serverStatusEl.textContent = '在线';
        serverStatusEl.className = 'status-badge status-online';
        toggleServerBtn.textContent = '停止服务器';
        toggleChatBtn.disabled = false;
    } else {
        serverStatusEl.textContent = '离线';
        serverStatusEl.className = 'status-badge status-offline';
        toggleServerBtn.textContent = '启动服务器';
        toggleChatBtn.disabled = true;
        
        // 如果服务器离线，聊天也必须离线
        chatRunning = false;
        updateChatStatus();
    }
}

// 更新聊天状态UI
function updateChatStatus() {
    if (chatRunning) {
        chatStatusEl.textContent = '在线';
        chatStatusEl.className = 'status-badge status-online';
        toggleChatBtn.textContent = '停止聊天';
        messageInput.disabled = false;
        sendButton.disabled = false;
        recommendButton.disabled = false;
    } else {
        chatStatusEl.textContent = '离线';
        chatStatusEl.className = 'status-badge status-offline';
        toggleChatBtn.textContent = '启动聊天';
        messageInput.disabled = true;
        sendButton.disabled = true;
        recommendButton.disabled = true;
    }
}

// 推荐智能体
async function recommendAgent() {
    const message = messageInput.value.trim();
    if (!message) {
        addSystemMessage('请先输入您的需求描述');
        return;
    }
    
    if (!chatRunning) {
        addSystemMessage('请先启动聊天');
        return;
    }
    
    // 添加用户消息到UI
    addUserMessage(`需求: ${message}`);
    
    // 添加等待提示
    const waitingMsg = document.createElement('div');
    waitingMsg.className = 'system-message waiting-message recommend-waiting';
    waitingMsg.textContent = '正在分析您的需求并推荐合适的智能体...';
    chatMessages.appendChild(waitingMsg);
    scrollToBottom();
    
    try {
        // 准备请求数据 - 包含用户消息和所有可用的智能体信息
        const requestData = {
            message: `用户需求："${message}"，\n智能体描述：${JSON.stringify(bookmarks)}`,
            isRecommendation: true
        };
        
        const response = await fetch(API_ENDPOINTS.sendMessage, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });
        
        const data = await response.json();
        
        // 移除等待提示
        const waitingElement = document.querySelector('.recommend-waiting');
        if (waitingElement) {
            waitingElement.remove();
        }
        console.log(data.response);
        if (data.success) {
            // 解析大模型的推荐结果，查找以@开头的智能体名称
            let recommendedAgentName = data.response.trim();
            
            // 查找@开头的名称并去掉@符号
            const atMatch = recommendedAgentName.match(/@([^\s]+)/);
            if (atMatch && atMatch[1]) {
                recommendedAgentName = atMatch[1];
            }
            
            // 查找推荐的智能体
            const recommendedAgent = bookmarks.find(b => 
                b.name.toLowerCase() === recommendedAgentName.toLowerCase() ||
                recommendedAgentName.toLowerCase().includes(b.name.toLowerCase())
            );

            if (recommendedAgent) {
                // 添加推荐消息
                addSystemMessage(`基于给出的信息：${message}，\n分析如下: ${data.response}，\n推荐智能体: ${recommendedAgent.name}`);
                
                // 自动选择该智能体
                useBookmark(recommendedAgent);
            } else {
                addSystemMessage(`未找到匹配的智能体: ${recommendedAgentName}`);
            }
        } else {
            addSystemMessage(`推荐失败: ${data.message}`);
        }
    } catch (error) {
        // 移除等待提示
        const waitingElement = document.querySelector('.recommend-waiting');
        if (waitingElement) {
            waitingElement.remove();
        }
        
        console.error('推荐智能体出错:', error);
        addSystemMessage('推荐智能体失败，请检查控制台获取详细信息');
    }
}

// 切换服务器状态
async function toggleServer() {
    try {
        const endpoint = serverRunning ? API_ENDPOINTS.serverStop : API_ENDPOINTS.serverStart;
        const response = await fetch(endpoint, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            serverRunning = !serverRunning;
            updateServerStatus();
            
            // 添加系统消息
            if (serverRunning) {
                // 如果有DID信息，显示它
                if (data.did_id && data.did_document_path) {
                    addSystemMessage(`服务器已启动\nDID ID: ${data.did_id}\nDID文档路径: ${data.did_document_path}`);
                } else {
                    addSystemMessage('服务器已启动');
                }
                // 检查聊天状态
                checkChatStatus();
            } else {
                addSystemMessage('服务器已停止');
            }
        } else {
            addSystemMessage(`服务器操作失败: ${data.message}`);
        }
    } catch (error) {
        console.error('切换服务器状态出错:', error);
        addSystemMessage('服务器操作失败，请检查控制台获取详细信息');
    }
}

// 切换聊天状态
async function toggleChat() {
    if (!serverRunning) {
        addSystemMessage('请先启动服务器');
        return;
    }
    
    try {
        const endpoint = chatRunning ? API_ENDPOINTS.chatStop : API_ENDPOINTS.chatStart;
        const response = await fetch(endpoint, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            chatRunning = !chatRunning;
            updateChatStatus();
            console.log('成功', chatRunning);
            // 添加系统消息
            addSystemMessage(chatRunning ? '聊天已启动' : '聊天已停止');
        } else {
            addSystemMessage(`聊天操作失败: ${data.message}`);
        }
    } catch (error) {
        console.error('切换聊天状态出错:', error);
        addSystemMessage('聊天操作失败，请检查控制台获取详细信息');
    }
}

// 发送消息
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;
    
    if (!chatRunning) {
        addSystemMessage('请先启动聊天');
        return;
    }
    
    // 检查是否是智能体命令
    if (message.startsWith('@') && message.includes(' ')) {
        sendAgentMessage(message);
    } else {
        sendRegularMessage(message);
    }
    
    // 清空输入框
    messageInput.value = '';
}

// 发送普通消息
async function sendRegularMessage(message) {
    // 添加用户消息到UI
    addUserMessage(message);
    
    // 添加等待提示
    const waitingMsg = document.createElement('div');
    waitingMsg.className = 'system-message waiting-message local-waiting';
    waitingMsg.textContent = '正在等待本地智能体回复...';
    chatMessages.appendChild(waitingMsg);
    scrollToBottom();
    
    try {
        const response = await fetch(API_ENDPOINTS.sendMessage, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message })
        });
        
        const data = await response.json();
        
        // 移除等待提示
        const waitingElement = document.querySelector('.local-waiting');
        if (waitingElement) {
            waitingElement.remove();
        }
        
        if (data.success) {
            // 添加助手回复到UI
            addAssistantMessage(data.response);
        } else {
            addSystemMessage(`发送消息失败: ${data.message}`);
        }
    } catch (error) {
        // 移除等待提示
        const waitingElement = document.querySelector('.local-waiting');
        if (waitingElement) {
            waitingElement.remove();
        }
        
        console.error('发送消息出错:', error);
        addSystemMessage('发送消息失败，请检查控制台获取详细信息');
    }
}

// 使用智能体书签
function useBookmark(bookmark) {
    if (!chatRunning) {
        addSystemMessage('请先启动聊天');
        return;
    }
    
    // 在输入框中填入智能体命令
    messageInput.value = `@${bookmark.name} `;
    messageInput.focus();
    
    // 存储当前选中的智能体信息
    window.selectedAgent = {
        name: bookmark.name,
        did: bookmark.did,
        url: bookmark.url,
        port: bookmark.port
    };
}

// 发送智能体消息
async function sendAgentMessage(message) {
    // 添加用户消息到UI
    addUserMessage(message);
    
    try {
        // 解析消息格式 @agentname message
        const parts = message.trim().split(' ', 1);
        const agentName = parts[0].substring(1); // 去掉@符号
        const agentMessage = message.substring(parts[0].length).trim();
        
        // 准备请求数据
        let requestData = { 
            message, 
            isAgentCommand: true 
        };
        
        // 如果有选中的智能体信息，直接传递给后端
        if (window.selectedAgent && window.selectedAgent.name === agentName) {
            requestData.agentInfo = window.selectedAgent;
        }
        
        const response = await fetch(API_ENDPOINTS.sendMessage, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            // 添加助手回复到UI
            addAssistantMessage(data.response);
            
            // 启动轮询，检查智能体回复
            startPollingForAgentResponse();
        } else {
            addSystemMessage(`发送智能体消息失败: ${data.message}`);
        }
    } catch (error) {
        console.error('发送智能体消息出错:', error);
        addSystemMessage('发送智能体消息失败，请检查控制台获取详细信息');
    }
}

// 轮询检查智能体回复
let pollingInterval = null;
function startPollingForAgentResponse() {
    // 清除之前的轮询
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }
    
    // 记录当前消息数量
    const initialMessageCount = chatMessages.childElementCount;
    
    // 添加等待提示
    const waitingMsg = document.createElement('div');
    waitingMsg.className = 'system-message waiting-message';
    waitingMsg.textContent = '正在等待智能体回复...';
    chatMessages.appendChild(waitingMsg);
    scrollToBottom();
    
    // 设置轮询间隔
    let pollCount = 0;
    pollingInterval = setInterval(async () => {
        try {
            // 获取最新的聊天历史
            const response = await fetch('/api/chat/history');
            const data = await response.json();
            
            if (data.success && data.history) {
                // 检查是否有新消息
                const newMessages = data.history.filter(msg => 
                    msg.type === 'anp_nlp' && 
                    !document.querySelector(`.agent-response[data-timestamp="${msg.timestamp}"]`)
                );
                
                if (newMessages.length > 0) {
                    // 移除等待提示
                    const waitingElement = document.querySelector('.waiting-message');
                    if (waitingElement) {
                        waitingElement.remove();
                    }
                    
                    // 添加新消息到UI
                    newMessages.forEach(msg => {
                        const messageEl = document.createElement('div');
                        messageEl.className = 'message assistant-message agent-response';
                        messageEl.setAttribute('data-timestamp', msg.timestamp);
                        messageEl.textContent = msg.message;
                        chatMessages.appendChild(messageEl);
                    });
                    
                    scrollToBottom();
                    
                    // 停止轮询
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                    
                    // 添加成功提示
                    addSystemMessage('已收到智能体回复');
                } else {
                    // 超过30秒（15次轮询）后停止
                    pollCount++;
                    if (pollCount >= 15) {
                        // 移除等待提示
                        const waitingElement = document.querySelector('.waiting-message');
                        if (waitingElement) {
                            waitingElement.remove();
                        }
                        
                        // 添加超时提示
                        addSystemMessage('智能体回复超时，请稍后刷新页面查看');
                        
                        // 停止轮询
                        clearInterval(pollingInterval);
                        pollingInterval = null;
                    }
                }
            }
        } catch (error) {
            console.error('轮询智能体回复出错:', error);
        }
    }, 2000); // 每2秒检查一次
}

// 添加用户消息到UI
function addUserMessage(message) {
    const messageEl = document.createElement('div');
    messageEl.className = 'message user-message';
    messageEl.textContent = message;
    chatMessages.appendChild(messageEl);
    scrollToBottom();
}

// 添加助手消息到UI
function addAssistantMessage(message) {
    const messageEl = document.createElement('div');
    messageEl.className = 'message assistant-message';
    messageEl.textContent = message;
    chatMessages.appendChild(messageEl);
    scrollToBottom();
}

// 添加系统消息到UI
function addSystemMessage(message) {
    const messageEl = document.createElement('div');
    messageEl.className = 'system-message';
    messageEl.textContent = message;
    chatMessages.appendChild(messageEl);
    scrollToBottom();
}

// 滚动到聊天底部
function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 加载书签
async function loadBookmarks(url) {
    try {
        let response;
        let loadingMessage;
        
        if (url) {
            // 网络加载
            loadingMessage = '正在从网络加载智能体书签...';
            response = await fetch(`${API_ENDPOINTS.getBookmarks}/load-from-url`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: url })
            });
        } else {
            // 本地加载
            loadingMessage = '正在加载本地智能体书签...';
            response = await fetch(API_ENDPOINTS.getBookmarks);
        }
        
        // 添加加载提示
        const loadingEl = document.createElement('div');
        loadingEl.className = 'system-message';
        loadingEl.textContent = loadingMessage;
        chatMessages.appendChild(loadingEl);
        scrollToBottom();
        
        const data = await response.json();
        
        // 移除加载提示
        const loadingElements = document.querySelectorAll('.system-message');
        if (loadingElements.length > 0) {
            loadingElements[loadingElements.length - 1].remove();
        }
        
        if (data.success && data.bookmarks) {
            bookmarks = data.bookmarks;
            renderBookmarks();
            
            // 添加成功提示
            const sourceType = url ? '网络' : '本地';
            addSystemMessage(`已成功从${sourceType}加载 ${bookmarks.length} 个智能体书签`);
        } else {
            console.error('加载书签失败:', data.message);
            const sourceType = url ? '网络' : '本地';
            addSystemMessage(`从${sourceType}加载书签失败: ${data.message || '未知错误'}`);
        }
    } catch (error) {
        console.error('加载书签出错:', error);
        const sourceType = url ? '网络' : '本地';
        addSystemMessage(`从${sourceType}加载书签失败，请检查网络连接或URL格式`);
    }
}

// 渲染书签列表
function renderBookmarks() {
    if (bookmarks.length === 0) {
        bookmarksList.innerHTML = '<div class="no-bookmarks">暂无智能体书签</div>';
        return;
    }
    
    bookmarksList.innerHTML = '';
    
    bookmarks.forEach(bookmark => {
        const bookmarkEl = document.createElement('div');
        bookmarkEl.className = 'bookmark-item';
        bookmarkEl.dataset.id = bookmark.id;
        
        const bookmarkInfo = document.createElement('div');
        bookmarkInfo.className = 'bookmark-info';
        
        const nameEl = document.createElement('div');
        nameEl.className = 'bookmark-name';
        nameEl.textContent = bookmark.name;
        
        // 显示简化的详情信息
        const detailsEl = document.createElement('div');
        detailsEl.className = 'bookmark-details';
        
        if (bookmark.did || bookmark.url || bookmark.port) {
            detailsEl.textContent = '已配置连接信息';
        } else {
            detailsEl.textContent = '未设置详细信息';
            detailsEl.classList.add('no-details');
        }
        
        bookmarkInfo.appendChild(nameEl);
        bookmarkInfo.appendChild(detailsEl);
        
        // 创建详情容器（包含DID、URL、端口和探索信息）
        if ((bookmark.did || bookmark.url || bookmark.port) || bookmark.discovery) {
            const discoveryContainer = document.createElement('div');
            discoveryContainer.className = 'discovery-container';
            
            const discoveryToggle = document.createElement('button');
            discoveryToggle.className = 'btn btn-sm btn-outline-secondary discovery-toggle';
            discoveryToggle.textContent = '显示详情';
            discoveryToggle.onclick = function() {
                const discoveryContent = this.nextElementSibling;
                if (discoveryContent.style.display === 'none') {
                    discoveryContent.style.display = 'block';
                    this.textContent = '隐藏详情';
                } else {
                    discoveryContent.style.display = 'none';
                    this.textContent = '显示详情';
                }
            };
            
            const discoveryContent = document.createElement('div');
            discoveryContent.className = 'discovery-content';
            discoveryContent.style.display = 'none';
            
            // 添加DID、URL和端口信息（如果有）
            if (bookmark.did || bookmark.url || bookmark.port) {
                const connectionInfoEl = document.createElement('div');
                connectionInfoEl.className = 'connection-info';
                
                const detailsText = [];
                if (bookmark.did) detailsText.push(`DID: ${bookmark.did}`);
                if (bookmark.url) detailsText.push(`URL: ${bookmark.url}`);
                if (bookmark.port) detailsText.push(`端口: ${bookmark.port}`);
                
                connectionInfoEl.innerHTML = `<strong>连接信息:</strong><br>${detailsText.join('<br>')}`;
                discoveryContent.appendChild(connectionInfoEl);
                
                // 如果同时有探索信息，添加分隔线
                if (bookmark.discovery) {
                    const divider = document.createElement('hr');
                    divider.className = 'details-divider';
                    discoveryContent.appendChild(divider);
                }
            }
            
            // 添加探索信息（如果有）
            if (bookmark.discovery) {
                const discoveryInfoEl = document.createElement('pre');
                discoveryInfoEl.className = 'discovery-info';
                discoveryInfoEl.textContent = bookmark.discovery;
                discoveryContent.appendChild(discoveryInfoEl);
            }
            
            discoveryContainer.appendChild(discoveryToggle);
            discoveryContainer.appendChild(discoveryContent);
            bookmarkInfo.appendChild(discoveryContainer);
        }
        
        const actionsEl = document.createElement('div');
        actionsEl.className = 'bookmark-actions';
        
        const useBtn = document.createElement('button');
        useBtn.className = 'btn btn-sm btn-outline-primary use-btn';
        useBtn.textContent = '使用';
        useBtn.onclick = () => useBookmark(bookmark);
        
        const discoverBtn = document.createElement('button');
        discoverBtn.className = 'btn btn-sm btn-outline-info discover-btn';
        discoverBtn.textContent = '探索';
        discoverBtn.onclick = () => discoverAgent(bookmark);
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-sm btn-outline-danger delete-btn';
        deleteBtn.textContent = '删除';
        deleteBtn.onclick = () => deleteBookmark(bookmark.id);
        
        actionsEl.appendChild(useBtn);
        actionsEl.appendChild(discoverBtn);
        actionsEl.appendChild(deleteBtn);
        
        bookmarkEl.appendChild(bookmarkInfo);
        bookmarkEl.appendChild(actionsEl);
        
        bookmarksList.appendChild(bookmarkEl);
    });
}

// 探索智能体
async function discoverAgent(bookmark) {
    if (!chatRunning) {
        addSystemMessage('请先启动聊天');
        return;
    }
    
    if (!bookmark.url) {
        addSystemMessage('该智能体没有URL信息，无法进行探索');
        return;
    }
    console.error('探索智能体:', bookmark);


    // 添加等待提示
    const waitingMsg = document.createElement('div');
    console.info('探索智能体:', bookmark);
    waitingMsg.className = 'system-message waiting-message discover-waiting';
    waitingMsg.textContent = '正在探索智能体...';
    chatMessages.appendChild(waitingMsg);
    scrollToBottom();
    
    try {
        const response = await fetch(API_ENDPOINTS.discoverAgent, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                bookmark_id: bookmark.id,
                url: bookmark.url,
                port: bookmark.port
            })          
        });
        
        const data = await response.json();
        
        console.log('探索智能体:', data);
        // 移除等待提示
        const waitingElement = document.querySelector('.discover-waiting');
        if (waitingElement) {
            waitingElement.remove();
        }
        
        if (data.success) {
            // 更新书签的discovery字段
            bookmark.discovery = data.discovery.summary;
            console.log('探索智能体:', bookmark.discovery);
            // 重新渲染书签列表
            renderBookmarks();
            
            // 添加成功消息
            addSystemMessage(`智能体探索成功: ${data.message}`);
        } else {
            addSystemMessage(`智能体探索失败: ${data.message}`);
        }
    } catch (error) {
        // 移除等待提示
        const waitingElement = document.querySelector('.discover-waiting');
        if (waitingElement) {
            waitingElement.remove();
        }
        
        console.error('探索智能体出错:', error);
        addSystemMessage('探索智能体失败，请检查控制台获取详细信息');
    }
}

// 使用智能体书签
function useBookmark(bookmark) {
    if (!chatRunning) {
        addSystemMessage('请先启动聊天');
        return;
    }
    
    // 在输入框中填入智能体命令
    messageInput.value = `@${bookmark.name} `;
    messageInput.focus();
    
    // 存储当前选中的智能体信息
    window.selectedAgent = {
        name: bookmark.name,
        did: bookmark.did,
        url: bookmark.url,
        port: bookmark.port
    };
}

// 发送智能体消息
async function sendAgentMessage(message) {
    // 添加用户消息到UI
    addUserMessage(message);
    
    try {
        // 解析消息格式 @agentname message
        const parts = message.trim().split(' ', 1);
        const agentName = parts[0].substring(1); // 去掉@符号
        const agentMessage = message.substring(parts[0].length).trim();
        
        // 准备请求数据
        let requestData = { 
            message, 
            isAgentCommand: true 
        };
        
        // 如果有选中的智能体信息，直接传递给后端
        if (window.selectedAgent && window.selectedAgent.name === agentName) {
            requestData.agentInfo = window.selectedAgent;
        }
        
        const response = await fetch(API_ENDPOINTS.sendMessage, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            // 添加助手回复到UI
            addAssistantMessage(data.response);
            
            // 启动轮询，检查智能体回复
            startPollingForAgentResponse();
        } else {
            addSystemMessage(`发送智能体消息失败: ${data.message}`);
        }
    } catch (error) {
        console.error('发送智能体消息出错:', error);
        addSystemMessage('发送智能体消息失败，请检查控制台获取详细信息');
    }
}

// 添加智能体书签
async function addBookmark() {
    const name = agentNameInput.value.trim();
    if (!name) return;
    
    try {
        const response = await fetch(API_ENDPOINTS.addBookmark, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name })
        });
        
        const data = await response.json();
        
        if (data.success) {
            bookmarks.push(data.bookmark);
            renderBookmarks();
            agentNameInput.value = '';
            addSystemMessage(`已添加智能体书签: ${name}`);
        } else {
            addSystemMessage(`添加书签失败: ${data.message}`);
        }
    } catch (error) {
        console.error('添加书签出错:', error);
        addSystemMessage('添加书签失败，请检查控制台获取详细信息');
    }
}

// 删除智能体书签
async function deleteBookmark(id) {
    try {
        const response = await fetch(`${API_ENDPOINTS.getBookmarks}/${id}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            bookmarks = bookmarks.filter(b => b.id !== id);
            renderBookmarks();
            addSystemMessage('已删除智能体书签');
        } else {
            addSystemMessage(`删除书签失败: ${data.message}`);
        }
    } catch (error) {
        console.error('删除书签出错:', error);
        addSystemMessage('删除书签失败，请检查控制台获取详细信息');
    }
}