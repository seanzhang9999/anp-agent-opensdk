// 全局变量
let socket;
let currentInstanceId = null;
let autoScroll = true;
let instances = {};

// DOM元素
const terminalEl = document.getElementById('terminal');
const instancesList = document.getElementById('instances-list');
const clearTerminalBtn = document.getElementById('clear-terminal');
const autoScrollBtn = document.getElementById('auto-scroll');
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const serverForm = document.getElementById('server-form');
const clientForm = document.getElementById('client-form');
const agentForm = document.getElementById('agent-form');

// 初始化函数
function init() {
    // 连接WebSocket
    connectWebSocket();
    
    // 初始化事件监听器
    initEventListeners();
    
    // 加载智能体列表
    loadAgentsList();
}

// 初始化事件监听器
function initEventListeners() {
    // 表单提交事件
    if (serverForm) {
        serverForm.addEventListener('submit', function(e) {
            e.preventDefault();
            startInstance('server');
        });
    }
    
    if (clientForm) {
        clientForm.addEventListener('submit', function(e) {
            e.preventDefault();
            startInstance('client');
        });
    }
    
    if (agentForm) {
        agentForm.addEventListener('submit', function(e) {
            e.preventDefault();
            startInstance('agent');
        });
        
        // 添加智能体选择事件监听器
        const agentSelect = document.getElementById('agent-name');
        if (agentSelect) {
            agentSelect.addEventListener('change', function() {
                const selectedOption = this.options[this.selectedIndex];
                const didInput = document.getElementById('agent-did');
                const urlInput = document.getElementById('agent-url');
                const portInput = document.getElementById('agent-port');
                
                if (selectedOption && selectedOption.value) {
                    // 填充DID、URL和端口字段
                    if (didInput) didInput.value = selectedOption.dataset.did || '';
                    if (urlInput) urlInput.value = selectedOption.dataset.url || '';
                    if (portInput && selectedOption.dataset.port) {
                        portInput.value = selectedOption.dataset.port;
                        portInput.placeholder = `默认端口: ${selectedOption.dataset.port}`;
                    } else if (portInput) {
                        portInput.value = '';
                        portInput.placeholder = '可选，默认使用配置端口';
                    }
                } else {
                    // 清空字段
                    if (didInput) didInput.value = '';
                    if (urlInput) urlInput.value = '';
                    if (portInput) {
                        portInput.value = '';
                        portInput.placeholder = '可选，默认使用配置端口';
                    }
                }
            });
        }
    }
    
    // 标签切换事件
    if (tabBtns) {
        tabBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const tabId = this.dataset.tab;
                switchTab(tabId);
            });
        });
    }
    
    // 终端控制事件
    if (clearTerminalBtn) {
        clearTerminalBtn.addEventListener('click', clearTerminal);
    }
    
    if (autoScrollBtn) {
        autoScrollBtn.addEventListener('click', toggleAutoScroll);
    }
    
    // 实例操作事件委托
    if (instancesList) {
        instancesList.addEventListener('click', function(e) {
            const instanceItem = e.target.closest('.instance-item');
            if (!instanceItem) return;
            
            const instanceId = instanceItem.dataset.id;
            
            if (e.target.classList.contains('view-btn')) {
                viewInstance(instanceId);
            } else if (e.target.classList.contains('stop-btn')) {
                stopInstance(instanceId);
            }
        });
    }
}

// 连接WebSocket
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    socket = new WebSocket(wsUrl);
    
    socket.onopen = () => {
        console.log('WebSocket连接已建立');
        addTerminalLine('系统', '已连接到服务器');
    };
    
    socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleWebSocketMessage(message);
    };
    
    socket.onclose = () => {
        console.log('WebSocket连接已关闭');
        addTerminalLine('系统', '与服务器的连接已断开，5秒后尝试重新连接...');
        setTimeout(connectWebSocket, 5000);
    };
    
    socket.onerror = (error) => {
        console.error('WebSocket错误:', error);
        addTerminalLine('系统', '连接错误，请检查服务器状态');
    };
}

// 处理WebSocket消息
function handleWebSocketMessage(message) {
    console.log('收到WebSocket消息:', message);
    switch (message.type) {
        case 'init':
            // 初始化实例列表
            console.log('初始化实例列表:', message.instances);
            message.instances.forEach(instance => {
                instances[instance.id] = instance;
                renderInstance(instance);
            });
            updateEmptyMessage();
            break;
            
        case 'instance_added':
            // 处理新增实例
            console.log('新增实例:', message.instance);
            instances[message.instance.id] = message.instance;
            renderInstance(message.instance);
            updateEmptyMessage();
            break;
            
        case 'output':
            // 添加输出到终端
            console.log('收到输出:', message.instance_id, message.line);
            if (instances[message.instance_id]) {
                // 确保输出数组存在
                if (!instances[message.instance_id].output) {
                    instances[message.instance_id].output = [];
                }
                instances[message.instance_id].output.push(message.line);
                
                // 如果当前正在查看该实例，则更新终端
                if (currentInstanceId === message.instance_id) {
                    addTerminalLine('输出', message.line);
                    
                    // 添加自动滚动逻辑
                    if (autoScroll) {
                        const terminal = document.getElementById('terminal');
                        if (terminal) {
                            terminal.scrollTop = terminal.scrollHeight;
                        }
                    }
                }
            } else {
                console.error('收到未知实例的输出:', message.instance_id);
            }
            break;
            
        case 'output_complete':
            // 处理历史输出完成标记
            console.log('历史输出加载完成:', message.instance_id);
            if (currentInstanceId === message.instance_id) {
                addTerminalLine('系统', '历史输出加载完成');
            }
            break;
            
        case 'status':
            // 更新实例状态
            if (instances[message.instance_id]) {
                instances[message.instance_id].status = message.status;
                updateInstanceStatus(message.instance_id, message.status);
                
                if (currentInstanceId === message.instance_id) {
                    addTerminalLine('系统', `实例状态已更新为: ${message.status}`);
                }
            }
            break;
            
        case 'start_result':
            // 处理启动结果
            if (message.success) {
                addTerminalLine('系统', `实例已成功启动，ID: ${message.instance_id}`);
            } else {
                addTerminalLine('错误', `启动实例失败: ${message.error}`);
            }
            break;
            
        case 'stop_result':
            // 处理停止结果 
            if (message.success) {
                addTerminalLine('系统', `实例已成功停止，ID: ${message.instance_id}`);
                
                // 从实例列表中移除已停止的实例
                if (instances[message.instance_id]) {
                    // 从DOM中移除实例元素
                    const instanceEl = document.querySelector(`.instance-item[data-id="${message.instance_id}"]`);
                    if (instanceEl) {
                        instanceEl.remove();
                    }
                    
                    // 从实例对象中删除
                    delete instances[message.instance_id];
                    
                    // 更新空消息显示
                    updateEmptyMessage();
                    
                    // 如果当前正在查看该实例，清空终端
                    if (currentInstanceId === message.instance_id) {
                        currentInstanceId = null;
                        addTerminalLine('系统', '当前查看的实例已停止');
                    }
                }
            } else {
                addTerminalLine('错误', `停止实例失败: ${message.error}`);
            }
            break;
            
        case 'error':
            // 处理错误消息
            addTerminalLine('错误', message.message);
            break;
            
        case 'output_result':
            // 处理输出结果
            if (message.success) {
                clearTerminal();
                message.output.forEach(line => {
                    addTerminalLine('输出', line);
                });
            } else {
                addTerminalLine('错误', `获取输出失败: ${message.error}`);
            }
            break;
            
        default:
            console.log('未知消息类型:', message.type, message);
            break;
    }
}

// 渲染实例
function renderInstance(instance) {
    // 检查是否已存在
    const existingItem = document.querySelector(`.instance-item[data-id="${instance.id}"]`);
    if (existingItem) {
        // 更新现有实例
        const statusEl = existingItem.querySelector('.instance-status');
        statusEl.textContent = instance.status;
        statusEl.className = `instance-status ${instance.status}`;
        return;
    }
    
    console.log('渲染新实例:', instance.id, instance);
    
    // 创建新实例元素
    const templateEl = document.getElementById('instance-template');
    if (!templateEl) {
        console.error('错误: html中没有 instance-template 模版元素');
        addTerminalLine('错误', '无法渲染实例，模板元素不存在');
        return;
    }
    
    const template = templateEl.innerHTML;
    console.log('原始模板内容:', template);
    console.log('实例值:', {
        id: instance.id,
        command: instance.command,
        status: instance.status,
        time: formatDateTime(instance.start_time),
        name: instance.name || '-',
        port: instance.port || '-'
    });
    
    let html = template
        .replace(/\[\[id\]\]/g, instance.id)
        .replace(/\[\[command\]\]/g, instance.command)
        .replace(/\[\[status\]\]/g, instance.status)
        .replace(/\[\[time\]\]/g, formatDateTime(instance.start_time));
    
    // 替换可选字段
    html = html.replace(/\[\[name\]\]/g, instance.name || '-');
    html = html.replace(/\[\[port\]\]/g, instance.port || '-');
    
    console.log('替换后的HTML:', html);
    
    // 创建临时元素并获取内容
    const temp = document.createElement('div');
    temp.innerHTML = html;
    const instanceEl = temp.firstElementChild;
    
    if (!instanceEl) {
        console.error('错误: 无法创建实例元素');
        addTerminalLine('错误', '无法创建实例元素');
        return;
    }
    
    // 添加到列表
    instancesList.appendChild(instanceEl);
    console.log('实例已添加到DOM');
    updateEmptyMessage();
}

// 更新实例状态
function updateInstanceStatus(instanceId, status) {
    const instanceItem = document.querySelector(`.instance-item[data-id="${instanceId}"]`);
    if (instanceItem) {
        const statusEl = instanceItem.querySelector('.instance-status');
        statusEl.textContent = status;
        statusEl.className = `instance-status ${status}`;
    }
}

// 添加终端行
function addTerminalLine(prefix, text) {
    const terminal = document.getElementById('terminal');
    if (!terminal) return;
    
    // 移除欢迎消息
    const welcome = terminal.querySelector('.terminal-welcome');
    if (welcome) {
        welcome.remove();
    }
    
    // 创建新行
    const line = document.createElement('div');
    line.className = 'terminal-line';
    
    // 添加时间前缀
    const time = document.createElement('span');
    time.className = 'terminal-time';
    time.textContent = formatTime(new Date());
    line.appendChild(time);
    
    // 添加类型前缀
    const prefixSpan = document.createElement('span');
    prefixSpan.className = `terminal-prefix terminal-prefix-${prefix.toLowerCase()}`;
    prefixSpan.textContent = prefix;
    line.appendChild(prefixSpan);
    
    // 添加文本内容
    const content = document.createElement('span');
    content.className = 'terminal-content';
    content.textContent = text;
    line.appendChild(content);
    
    // 添加到终端
    terminal.appendChild(line);
    
    // 自动滚动
    if (autoScroll) {
        terminal.scrollTop = terminal.scrollHeight;
    }
}

// 清空终端
function clearTerminal() {
    const terminal = document.getElementById('terminal');
    if (terminal) {
        terminal.innerHTML = '';
    }
}

// 切换标签
function switchTab(tabId) {
    // 更新标签按钮状态
    tabBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    
    // 更新标签内容状态
    tabContents.forEach(content => {
        content.classList.toggle('hidden', content.id !== `${tabId}-tab`);
    });
}

// 切换自动滚动
function toggleAutoScroll() {
    const btn = document.getElementById('auto-scroll');
    autoScroll = !autoScroll;
    
    if (btn) {
        if (autoScroll) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    }
}

// 格式化日期时间
function formatDateTime(isoString) {
    try {
        const date = new Date(isoString);
        return `${date.getFullYear()}-${padZero(date.getMonth() + 1)}-${padZero(date.getDate())} ${padZero(date.getHours())}:${padZero(date.getMinutes())}:${padZero(date.getSeconds())}`;
    } catch (e) {
        return isoString || '-';
    }
}

// 格式化时间
function formatTime(date) {
    return `${padZero(date.getHours())}:${padZero(date.getMinutes())}:${padZero(date.getSeconds())}`;
}

// 补零
function padZero(num) {
    return num.toString().padStart(2, '0');
}

// 启动新实例
function startInstance(command) {
    // 获取表单数据
    let data = {
        type: 'start',
        command: command
    };
    
    // 根据命令类型获取不同的参数
    if (command === 'agent') {
        const nameSelect = document.getElementById('agent-name');
        const portInput = document.getElementById('agent-port');
        const didInput = document.getElementById('agent-did');
        const urlInput = document.getElementById('agent-url');
        
        if (nameSelect && nameSelect.value) {
            data.name = nameSelect.value;
            
            // 获取选中选项的数据
            const selectedOption = nameSelect.options[nameSelect.selectedIndex];
            if (selectedOption) {
                // 如果表单中没有填写端口，但选项中有端口，则使用选项中的端口
                if ((!portInput || !portInput.value) && selectedOption.dataset.port) {
                    data.port = parseInt(selectedOption.dataset.port, 10);
                }
                
                // 添加DID和URL信息（如果后端需要）
                if (selectedOption.dataset.did) {
                    data.did = selectedOption.dataset.did;
                }
                
                if (selectedOption.dataset.url) {
                    data.url = selectedOption.dataset.url;
                }
            }
        } else {
            addTerminalLine('错误', '请选择智能体名称');
            return;
        }
        
        // 如果用户在表单中填写了端口，则优先使用用户填写的
        if (portInput && portInput.value) {
            data.port = parseInt(portInput.value, 10);
        }
    } else if (command === 'server') {
        const portInput = document.getElementById('server-port');
        if (portInput && portInput.value) {
            data.port = parseInt(portInput.value, 10);
        }
    } else if (command === 'client') {
        const portInput = document.getElementById('client-port');
        const idInput = document.getElementById('client-id');
        const messageInput = document.getElementById('client-message');
        
        if (portInput && portInput.value) {
            data.port = parseInt(portInput.value, 10);
        }
        
        if (idInput && idInput.value) {
            data.name = idInput.value;
        }
        
        if (messageInput && messageInput.value) {
            data.message = messageInput.value;
        }
    }
    
    // 发送WebSocket消息
    socket.send(JSON.stringify(data));
    addTerminalLine('系统', `正在启动${command}实例...`);
}

// 停止实例
function stopInstance(instanceId) {
    if (!instanceId) return;
    
    const data = {
        type: 'stop',
        instance_id: instanceId
    };
    
    socket.send(JSON.stringify(data));
    addTerminalLine('系统', `正在停止实例 ${instanceId}...`);
}

// 查看实例输出
function viewInstance(instanceId) {
    if (!instanceId) return;
    
    // 更新当前查看的实例ID
    currentInstanceId = instanceId;
    
    // 清空终端
    clearTerminal();
    
    // 添加实例信息
    const instance = instances[instanceId];
    if (instance) {
        addTerminalLine('系统', `正在查看实例 ${instanceId}`);
        addTerminalLine('系统', `命令: ${instance.command}`);
        if (instance.name) {
            addTerminalLine('系统', `名称: ${instance.name}`);
        }
        if (instance.port) {
            addTerminalLine('系统', `端口: ${instance.port}`);
        }
        addTerminalLine('系统', `状态: ${instance.status}`);
        addTerminalLine('系统', `启动时间: ${formatDateTime(instance.start_time)}`);
        addTerminalLine('系统', '---输出开始---');
    }
    
    // 请求实例输出
    const data = {
        type: 'get_output',
        instance_id: instanceId
    };
    
    socket.send(JSON.stringify(data));
}

// 加载智能体列表
function loadAgentsList() {
    fetch('/api/agents')
        .then(response => response.json())
        .then(data => {
            const agentSelect = document.getElementById('agent-name');
            if (agentSelect && data.agents && data.agents.length > 0) {
                // 清空现有选项（保留第一个默认选项）
                while (agentSelect.options.length > 1) {
                    agentSelect.remove(1);
                }
                
                // 添加新选项
                data.agents.forEach(agent => {
                    const option = document.createElement('option');
                    option.value = agent.name;
                    option.textContent = agent.name;
                    // 存储完整的智能体信息作为自定义数据属性
                    option.dataset.did = agent.did || '';
                    option.dataset.url = agent.url || '';
                    option.dataset.port = agent.port || '';
                    agentSelect.appendChild(option);
                });
                
                // 触发change事件以更新表单中的其他字段
                agentSelect.dispatchEvent(new Event('change'));
            }
        })
        .catch(error => {
            console.error('获取智能体列表失败:', error);
            addTerminalLine('错误', `获取智能体列表失败: ${error.message}`);
        });
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', init);

// 更新空消息
function updateEmptyMessage() {
    const emptyMessage = document.querySelector('.empty-message');
    const hasInstances = instancesList.querySelectorAll('.instance-item').length > 0;
    
    if (emptyMessage) {
        emptyMessage.style.display = hasInstances ? 'none' : 'block';
    } else if (!hasInstances) {
        // 如果没有空消息元素且没有实例，则创建一个
        const div = document.createElement('div');
        div.className = 'empty-message';
        div.textContent = '暂无运行中的实例';
        instancesList.appendChild(div);
    }
}