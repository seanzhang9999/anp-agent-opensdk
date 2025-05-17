def generate_api_routes_html(api_routes_info):
    """生成API路由的HTML代码"""
    return ''.join([f'''
    <div class="card">
        <h3 class="path">{route['path']}</h3>
        <p><span class="method get">GET</span> <span class="method post">POST</span> {route['name']}() {'<span class="async">[异步]</span>' if route['is_async'] else ''}</p>
        {f'<p class="doc">{route["doc"]}</p>' if route['doc'] else ''}
    </div>''' for route in api_routes_info])

def generate_message_handlers_html(message_handlers_info):
    """生成消息处理器的HTML代码"""
    return ''.join([f'''
    <div class="card">
        <h3>类型: {handler['type']}</h3>
        <p>{handler['name']}() {'<span class="async">[异步]</span>' if handler['is_async'] else ''}</p>
        {f'<p class="doc">{handler["doc"]}</p>' if handler['doc'] else ''}
    </div>''' for handler in message_handlers_info])

def generate_default_routes_html(default_routes_info):
    """生成默认路由的HTML代码"""
    return ''.join([f'''
    <div class="card">
        <h3 class="path">{route['path']}</h3>
        <p><span class="method {'get' if route['method'] == 'GET' else 'post' if route['method'] == 'POST' else 'ws'}">{route['method']}</span> {route['description']}</p>
    </div>''' for route in default_routes_info])

def generate_visualization_html(api_routes_info, message_handlers_info, default_routes_info):
    """生成完整的可视化HTML页面"""
    with open('templates/visualize.html', 'r', encoding='utf-8') as f:
        template = f.read()
    
    api_routes_html = generate_api_routes_html(api_routes_info)
    message_handlers_html = generate_message_handlers_html(message_handlers_info)
    default_routes_html = generate_default_routes_html(default_routes_info)
    
    return template.format(
        api_routes_html=api_routes_html,
        message_handlers_html=message_handlers_html,
        default_routes_html=default_routes_html
    )