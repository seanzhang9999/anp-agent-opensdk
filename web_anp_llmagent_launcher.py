#!/usr/bin/env python3
"""
DID WBA 管理界面

这个模块提供了一个Web界面，用于管理多个anp_llmagent.py实例，
包括启动、监控和关闭功能。
"""
import os
import sys
import json
import time
import argparse
import subprocess
import threading
import uuid
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# 设置日志目录
user_dir = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(user_dir, "logs")
os.makedirs(log_dir, exist_ok=True)

# 创建FastAPI应用
app = FastAPI(title="DID WBA 管理界面")

# 设置静态文件目录
static_dir = os.path.join(user_dir, "static", "manager")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 设置模板目录
templates_dir = os.path.join(user_dir, "static", "manager","templates")
os.makedirs(templates_dir, exist_ok=True)
templates = Jinja2Templates(directory=templates_dir)

# 存储所有运行中的实例
instances: Dict[str, Dict[str, Any]] = {}

# 创建事件循环
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# WebSocket连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# 数据模型
class InstanceCreate(BaseModel):
    command: str
    name: Optional[str] = None
    port: Optional[int] = None
    did: Optional[str] = None
    url: Optional[str] = None

class InstanceInfo(BaseModel):
    id: str
    command: str
    name: Optional[str] = None
    port: Optional[int] = None
    did: Optional[str] = None
    url: Optional[str] = None
    status: str
    start_time: str
    output: List[str] = []

# 启动一个新的anp_llmagent.py实例
def start_instance(command: str, instance_id: str, name: Optional[str] = None, port: Optional[int] = None, did: Optional[str] = None, url: Optional[str] = None) -> bool:
    # 如果指定了端口，先检查并清理该端口
    if port:
        print(f"检查端口 {port} 是否被占用")
        # 尝试终止使用该端口的进程
        if not kill_processes_by_port(port):
            print(f"无法清理端口 {port}，启动实例可能会失败")
    
    cmd = [sys.executable, os.path.join(user_dir, "anp_llmagent.py"), command]
    
    if command == "agent" and name:
        # 修正：使用-u参数传递智能体名称
        cmd.extend(["-u", name])
    
    if port:
        cmd.extend(["-p", str(port)])
    
    try:
        # 创建日志文件
        log_file = os.path.join(log_dir, f"instance_{instance_id}.log")
        log_fd = open(log_file, "w", encoding="utf-8")
        
        # 启动进程
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # 记录实例信息
        instances[instance_id] = {
            "id": instance_id,
            "command": command,
            "name": name,
            "port": port,
            "did": did,
            "url": url,
            "process": process,
            "status": "running",
            "start_time": datetime.now().isoformat(),
            "output": [],
            "log_file": log_file,
            "log_fd": log_fd
        }
        
        # 启动线程读取输出
        threading.Thread(
            target=read_output,
            args=(instance_id, process),
            daemon=True
        ).start()
        
        return True
    except Exception as e:
        print(f"启动实例失败: {e}")
        return False

# 读取进程输出
def read_output(instance_id: str, process: subprocess.Popen):
    try:
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
                
            line = line.rstrip()
            if instance_id in instances:
                # 添加到输出缓存
                instances[instance_id]["output"].append(line)
                # 限制输出行数
                if len(instances[instance_id]["output"]) > 1000:
                    instances[instance_id]["output"] = instances[instance_id]["output"][-1000:]
                
                # 写入日志文件
                log_fd = instances[instance_id]["log_fd"]
                log_fd.write(f"{line}\n")
                log_fd.flush()
                
                # 广播消息
                message = json.dumps({
                    "type": "output",
                    "instance_id": instance_id,
                    "line": line
                })
                try:
                    # 使用事件循环广播消息
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast(message),
                        loop
                    )
                    # 添加调试日志
                    print(f"广播输出消息: {instance_id} - {line[:50]}...")
                except Exception as e:
                    print(f"广播消息失败: {e}")
    except Exception as e:
        print(f"读取输出错误: {e}")
    finally:
        # 进程结束后更新状态
        if instance_id in instances:
            instances[instance_id]["status"] = "stopped"
            if instances[instance_id]["log_fd"]:
                instances[instance_id]["log_fd"].close()
            
            # 广播状态变更
            message = json.dumps({
                "type": "status",
                "instance_id": instance_id,
                "status": "stopped"
            })
            try:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(message),
                    loop
                )
                print(f"广播状态变更: {instance_id} - stopped")
            except Exception as e:
                print(f"广播状态变更失败: {e}")

# 根据端口查询并终止进程
def kill_processes_by_port(port: int) -> bool:
    try:
        # 查找使用指定端口的进程
        cmd = ["lsof", "-i", f":{port}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0 or not result.stdout.strip():
            print(f"端口 {port} 没有被占用")
            return True
        
        # 解析输出，提取PID
        lines = result.stdout.strip().split('\n')
        if len(lines) <= 1:  # 只有标题行，没有实际进程
            return True
        
        # 从第二行开始解析（跳过标题行）
        pids = set()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) > 1:
                pids.add(parts[1])  # PID通常在第二列
        
        # 终止所有找到的进程
        for pid in pids:
            try:
                # 先尝试正常终止
                kill_cmd = ["kill", pid]
                subprocess.run(kill_cmd, check=False)
                print(f"已发送终止信号到进程 {pid}")
                
                # 检查进程是否仍在运行
                time.sleep(0.5)
                check_cmd = ["ps", "-p", pid]
                check_result = subprocess.run(check_cmd, capture_output=True, text=True)
                
                # 如果进程仍在运行，强制终止
                if check_result.returncode == 0:
                    force_kill_cmd = ["kill", "-9", pid]
                    subprocess.run(force_kill_cmd, check=False)
                    print(f"已强制终止进程 {pid}")
            except Exception as e:
                print(f"终止进程 {pid} 时出错: {e}")
        
        return True
    except Exception as e:
        print(f"根据端口终止进程时出错: {e}")
        return False

# 停止实例
def stop_instance(instance_id: str) -> bool:
    if instance_id not in instances:
        return False
    
    try:
        process = instances[instance_id]["process"]
        if process.poll() is None:  # 进程仍在运行
            process.terminate()
            # 等待进程结束
            for _ in range(5):
                if process.poll() is not None:
                    break
                time.sleep(0.5)
            
            # 如果进程仍未结束，强制结束
            if process.poll() is None:
                process.kill()
        
        # 如果实例有端口，确保该端口上的所有进程都被终止
        port = instances[instance_id].get("port")
        if port:
            kill_processes_by_port(port)
        
        # 关闭日志文件
        if instances[instance_id]["log_fd"]:
            instances[instance_id]["log_fd"].close()
        
        # 更新状态
        instances[instance_id]["status"] = "stopped"
        return True
    except Exception as e:
        print(f"停止实例失败: {e}")
        return False

# 路由
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(
        "manager.html",
        {"request": request}
    )

# WebSocket连接
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # 发送当前所有实例状态
        instances_info = []
        for instance_id, instance in instances.items():
            instances_info.append({
                "id": instance_id,
                "command": instance["command"],
                "name": instance["name"],
                "port": instance["port"],
                "did": instance.get("did"),
                "url": instance.get("url"),
                "status": instance["status"],
                "start_time": instance["start_time"],
                "output": instance["output"]
            })
        
        await websocket.send_json({
            "type": "init",
            "instances": instances_info
        })
        
        # 处理客户端消息
        while True:
            try:
                # 添加超时处理，避免永久阻塞
                data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                try:
                    message = json.loads(data)
                    if message["type"] == "start":
                        # 启动新实例
                        instance_id = str(uuid.uuid4())
                        success = start_instance(
                            command=message["command"],
                            instance_id=instance_id,
                            name=message.get("name"),
                            port=message.get("port"),
                            did=message.get("did"),
                            url=message.get("url")
                        )
                        
                        if success:
                            # 向请求客户端发送成功消息
                            await websocket.send_json({
                                "type": "start_result",
                                "success": True,
                                "instance_id": instance_id
                            })
                            
                            # 向所有客户端广播新实例信息
                            instance_info = {
                                "id": instance_id,
                                "command": message["command"],
                                "name": message.get("name"),
                                "port": message.get("port"),
                                "did": message.get("did"),
                                "url": message.get("url"),
                                "status": "running",
                                "start_time": instances[instance_id]["start_time"],
                                "output": []
                            }
                            
                            await manager.broadcast(json.dumps({
                                "type": "instance_added",
                                "instance": instance_info
                            }))
                            print(f"广播新实例: {instance_id}")
                        else:
                            await websocket.send_json({
                                "type": "start_result",
                                "success": False,
                                "error": "启动实例失败"
                            })
                    
                    elif message["type"] == "stop":
                        # 停止实例
                        instance_id = message["instance_id"]
                        success = stop_instance(instance_id)
                        
                        await websocket.send_json({
                            "type": "stop_result",
                            "success": success,
                            "instance_id": instance_id
                        })
                    
                    elif message["type"] == "get_output":
                        # 获取实例输出
                        instance_id = message["instance_id"]
                        if instance_id in instances:
                            # 修改为使用output类型，保持与实时输出格式一致
                            for line in instances[instance_id]["output"]:
                                await websocket.send_json({
                                    "type": "output",
                                    "instance_id": instance_id,
                                    "line": line
                                })
                            # 发送一个完成标记
                            await websocket.send_json({
                                "type": "output_complete",
                                "instance_id": instance_id
                            })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "实例不存在",
                                "instance_id": instance_id
                            })
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "无效的JSON格式"
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })
            except asyncio.TimeoutError:
                # 超时后继续循环，不会阻塞
                continue
            except WebSocketDisconnect:
                manager.disconnect(websocket)
                break
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# REST API
@app.post("/api/instances", response_model=InstanceInfo)
async def create_instance(instance: InstanceCreate):
    instance_id = str(uuid.uuid4())
    success = start_instance(
        command=instance.command,
        instance_id=instance_id,
        name=instance.name,
        port=instance.port,
        did=instance.did,
        url=instance.url
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="启动实例失败")
    
    return InstanceInfo(
        id=instance_id,
        command=instance.command,
        name=instance.name,
        port=instance.port,
        did=instance.did,
        url=instance.url,
        status="running",
        start_time=instances[instance_id]["start_time"],
        output=[]
    )

@app.get("/api/instances", response_model=List[InstanceInfo])
async def list_instances():
    result = []
    for instance_id, instance in instances.items():
        result.append(InstanceInfo(
            id=instance_id,
            command=instance["command"],
            name=instance.get("name"),
            port=instance.get("port"),
            did=instance.get("did"),
            url=instance.get("url"),
            status=instance["status"],
            start_time=instance["start_time"],
            output=instance["output"]
        ))
    return result

@app.get("/api/instances/{instance_id}", response_model=InstanceInfo)
async def get_instance(instance_id: str):
    if instance_id not in instances:
        raise HTTPException(status_code=404, detail="实例不存在")
    
    instance = instances[instance_id]
    return InstanceInfo(
        id=instance_id,
        command=instance["command"],
        name=instance.get("name"),
        port=instance.get("port"),
        did=instance.get("did"),
        url=instance.get("url"),
        status=instance["status"],
        start_time=instance["start_time"],
        output=instance["output"]
    )

@app.delete("/api/instances/{instance_id}")
async def delete_instance(instance_id: str):
    if instance_id not in instances:
        raise HTTPException(status_code=404, detail="实例不存在")
    
    success = stop_instance(instance_id)
    if not success:
        raise HTTPException(status_code=500, detail="停止实例失败")
    
    return {"success": True}

# 添加获取智能体列表的API端点
@app.get("/api/agents")
async def get_agents():
    agents_dir = os.path.join(user_dir, "anp_core", "anp_agents")
    agents = []
    
    try:
        # 获取目录中的所有js文件
        for file in os.listdir(agents_dir):
            if file.endswith(".js"):
                file_path = os.path.join(agents_dir, file)
                # 读取JS文件内容
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        # 解析JSON内容
                        agent_data = json.loads(f.read())
                        # 添加完整的智能体信息
                        agents.append(agent_data)
                    except json.JSONDecodeError as e:
                        print(f"解析智能体文件 {file} 失败: {e}")
    except Exception as e:
        print(f"获取智能体列表失败: {e}")
    
    return {"agents": agents}

@app.get("/api/instances/{instance_id}", response_model=InstanceInfo)
async def get_instance(instance_id: str):
    if instance_id not in instances:
        raise HTTPException(status_code=404, detail="实例不存在")
    
    instance = instances[instance_id]
    return InstanceInfo(
        id=instance_id,
        command=instance["command"],
        name=instance.get("name"),
        port=instance.get("port"),
        did=instance.get("did"),
        url=instance.get("url"),
        status=instance["status"],
        start_time=instance["start_time"],
        output=instance["output"]
    )

@app.delete("/api/instances/{instance_id}")
async def delete_instance(instance_id: str):
    if instance_id not in instances:
        raise HTTPException(status_code=404, detail="实例不存在")
    
    success = stop_instance(instance_id)
    if not success:
        raise HTTPException(status_code=500, detail="停止实例失败")
    
    return {"success": True}

# 添加新的数据模型用于公开实例信息
class PublicInstanceInfo(BaseModel):
    name: str
    url: str
    port: Optional[int] = None
    did: Optional[str] = None

# 添加新的API端点，对外公布运行中的实例信息
@app.get("/api/public/instances", response_model=List[PublicInstanceInfo])
async def list_public_instances():
    result = []    
    for instance_id, instance in instances.items():
        # 只包含运行中的实例
        if instance["status"] == "running":
            # 直接从实例数据结构中获取所有信息
            name = instance.get("name", "未命名实例")
            port = instance.get("port")
            did = instance.get("did")
            
            # 优先使用实例中存储的URL，如果没有则构建一个
            url = instance.get("url")

            
            # 添加到结果列表
            result.append(PublicInstanceInfo(
                name=name,
                url=url,
                port=port,
                did=did
            ))
    return result


@app.delete("/api/instances/{instance_id}")
async def delete_instance(instance_id: str):
    if instance_id not in instances:
        raise HTTPException(status_code=404, detail="实例不存在")
    
    success = stop_instance(instance_id)
    if not success:
        raise HTTPException(status_code=500, detail="停止实例失败")
    
    return {"success": True}

# 主函数
def main():
    parser = argparse.ArgumentParser(description="DID WBA 管理界面")
    parser.add_argument("-p", "--port", type=int, default=8080, help="Web服务器端口号")
    args = parser.parse_args()
    
    # 启动Web服务器
    uvicorn.run(app, host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    main()