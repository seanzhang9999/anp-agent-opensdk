# ANP Agent OpenSDK 线程问题修复方案

根据分析报告中发现的线程相关问题，以下是具体的修复方案和代码示例。

## 1. 守护线程和服务器关闭问题修复

### 修改 `anp_sdk.py` 中的服务器启动和关闭逻辑

```python
# 修改前
def start_server(self):
    # ...
    def run_server():
        uvicorn.run(self.app, host=host, port=int(port))
    
    # 在新线程中启动服务器
    self.server_thread = threading.Thread(target=run_server, daemon=True)
    self.server_thread.start()
    
    self.server_running = True
    self.logger.debug(f"服务器已在端口 {self.port} 启动")
    
    return True

def stop_server(self):
    # ...
    # 由于服务器在独立线程中运行，这里我们不需要显式停止它
    # 线程会在主程序退出时自动终止（因为是daemon线程）
    
    self.server_running = False
    self.logger.debug("服务器已停止")
    
    return True
```

```python
# 修改后
def start_server(self):
    # ...
    def run_server():
        # 保存uvicorn服务器实例以便后续关闭
        config = uvicorn.Config(self.app, host=host, port=int(port))
        self.uvicorn_server = uvicorn.Server(config)
        self.uvicorn_server.run()
    
    # 在新线程中启动服务器
    self.server_thread = threading.Thread(target=run_server)
    self.server_thread.daemon = True  # 显式设置为守护线程
    self.server_thread.start()
    
    self.server_running = True
    self.logger.debug(f"服务器已在端口 {self.port} 启动")
    
    return True

def stop_server(self):
    if not self.server_running:
        return True
    
    # 关闭所有WebSocket连接
    for ws in self.ws_connections.values():
        asyncio.create_task(ws.close())
    self.ws_connections.clear()
    
    # 清空SSE客户端
    self.sse_clients.clear()
    
    # 优雅关闭uvicorn服务器
    if hasattr(self, 'uvicorn_server'):
        self.uvicorn_server.should_exit = True
        self.logger.debug("已发送服务器关闭信号")
    
    self.server_running = False
    self.logger.debug("服务器已停止")
    
    return True

def __del__(self):
    """确保在对象销毁时释放资源"""
    try:
        if self.server_running:
            self.stop_server()
    except Exception as e:
        # 避免在解释器关闭时出现问题
        pass
```

## 2. 线程资源释放问题修复

### 修改 `anp_sdk_demo.py` 中的线程管理

```python
# 修改前
def start_server():
    sdk.start_server()
server_thread = threading.Thread(target=start_server)
server_thread.start()
import time
time.sleep(0.5)
```

```python
# 修改后
def start_server():
    try:
        sdk.start_server()
    except Exception as e:
        logger.error(f"服务器启动错误: {e}")

server_thread = threading.Thread(target=start_server)
server_thread.daemon = True  # 设置为守护线程，确保主程序退出时线程也会退出
server_thread.start()

# 等待服务器启动
import time
time.sleep(0.5)
```

```python
# 修改前 - run_demo线程
def run_demo():
    asyncio.run(demo(sdk, agent1, agent2, agent3, step_mode=step_mode))
thread = threading.Thread(target=run_demo)
thread.start()
thread.join()  # 等待线程完成
```

```python
# 修改后 - 添加异常处理
def run_demo():
    try:
        asyncio.run(demo(sdk, agent1, agent2, agent3, step_mode=step_mode))
    except Exception as e:
        logger.error(f"演示运行错误: {e}")

thread = threading.Thread(target=run_demo)
thread.start()
try:
    thread.join()  # 等待线程完成
except KeyboardInterrupt:
    logger.debug("用户中断演示")
    # 这里可以添加清理代码
```

## 3. RLock 使用问题修复

### 修改 `dynamic_config.py` 中的锁使用

```python
# 添加 __del__ 方法
def __del__(self):
    """析构函数，确保资源被正确释放"""
    try:
        self.logger.debug("DynamicConfig 实例被销毁，资源已释放")
    except:
        pass  # 忽略日志错误，防止在解释器关闭时出现问题
```

### 使用 contextlib 简化锁的使用（可选优化）

```python
import contextlib

@contextlib.contextmanager
def config_lock(self):
    """配置锁的上下文管理器"""
    self._config_lock.acquire()
    try:
        yield
    finally:
        self._config_lock.release()

# 然后在方法中使用
def get(self, key: str, default: Any = None) -> Any:
    """获取配置值"""
    with self.config_lock():
        # 处理多级键
        # ...
```

## 4. 异步任务取消处理修复

### 修改 `agent_message_group.py` 中的 `listen_group_messages` 函数

```python
# 修改前
except asyncio.CancelledError:
    logger.debug(f"{caller_agent} 的群聊监听已停止")
```

```python
# 修改后
except asyncio.CancelledError:
    logger.debug(f"{caller_agent} 的群聊监听已停止")
    # 添加资源清理代码
    try:
        # 清理会话资源
        if 'session' in locals() and session is not None:
            await session.close()
    except Exception as e:
        logger.error(f"清理资源时出错: {e}")
    # 重新抛出异常，让调用者知道任务已取消
    raise
```

### 修改 `anp_sdk_demo.py` 中的任务取消处理

```python
# 修改前
task.cancel()
try:
    await task
except asyncio.CancelledError:
    pass
```

```python
# 修改后
# 取消监听任务并确保资源被清理
task.cancel()
try:
    await task
except asyncio.CancelledError:
    logger.debug("群聊监听任务已取消")
except Exception as e:
    logger.error(f"取消群聊监听任务时出错: {e}")
finally:
    # 确保任何资源都被清理
    logger.debug("群聊监听资源已清理")
```

## 5. LocalAgent 类中添加资源清理

在 `anp_sdk.py` 的 `LocalAgent` 类中添加 `__del__` 方法：

```python
def __del__(self):
    """确保在对象销毁时释放资源"""
    try:
        # 清理WebSocket连接
        for ws in self._ws_connections.values():
            # 由于在析构函数中不能使用异步调用，记录日志提示可能的资源泄漏
            self.logger.debug(f"LocalAgent {self.id} 销毁时存在未关闭的WebSocket连接")
        
        # 清理其他资源
        self._ws_connections.clear()
        self._sse_clients.clear()
        self.token_to_remote_dict.clear()
        self.token_from_remote_dict.clear()
        
        self.logger.debug(f"LocalAgent {self.id} 资源已释放")
    except Exception:
        # 忽略错误，防止在解释器关闭时出现问题
        pass
```

## 实施建议

1. 按照上述修改逐一实施，优先修复守护线程和资源释放问题
2. 添加适当的日志记录，以便跟踪线程和资源的生命周期
3. 考虑使用线程池来管理线程资源，特别是对于需要频繁创建和销毁的短期任务
4. 实现更完善的异常处理机制，确保在异常情况下资源也能被正确释放
5. 添加单元测试，验证线程安全和资源管理的正确性

这些修改将显著提高代码的健壮性和可靠性，避免可能的资源泄漏和异常情况。