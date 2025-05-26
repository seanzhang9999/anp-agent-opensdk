# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import time
from typing import Dict, Any, Optional, List, Callable, Tuple
from urllib.parse import urlparse, parse_qs
from loguru import logger
from dataclasses import dataclass
from enum import Enum


class RouteType(Enum):
    """路由类型枚举"""
    API_CALL = "api_call"
    MESSAGE = "message"
    GROUP_MESSAGE = "group_message"
    GROUP_CONNECT = "group_connect"
    GROUP_MEMBERS = "group_members"


@dataclass
class LocalRoute:
    """本地路由信息"""
    source_did: str
    target_did: str
    route_type: RouteType
    path: str
    method: str = "POST"
    is_local: bool = True
    latency_ms: float = 0.0


class LocalAgentAccelerator:
    """本地智能体加速器
    
    负责检测和优化本地智能体间的通信，避免不必要的网络请求
    """
    
    def __init__(self, agent_router=None):
        self.agent_router = agent_router
        self.local_agents = {}  # did -> agent实例
        self.route_cache = {}  # (source, target, path) -> LocalRoute
        self.performance_stats = {}  # 性能统计
        self.group_local_members = {}  # group_id -> set(local_did)
        self.hosted_agent_mapping = {}  # hosted_did -> parent_did
        
        # 性能监控
        self.total_requests = 0
        self.local_requests = 0
        self.network_requests = 0
        self.avg_local_latency = 0.0
        self.avg_network_latency = 0.0
    
    def register_agent(self, agent):
        """注册本地智能体"""
        did = str(agent.id)
        self.local_agents[did] = agent
        
        # 检查是否为托管智能体
        if hasattr(agent, '_check_if_hosted_did') and agent._check_if_hosted_did():
            parent_did = agent._get_parent_did()
            if parent_did:
                self.hosted_agent_mapping[did] = parent_did
                logger.info(f"注册托管智能体: {did} -> 父DID: {parent_did}")
        
        logger.info(f"本地加速器已注册智能体: {did}")
        return agent
    
    def unregister_agent(self, did: str):
        """注销本地智能体"""
        did = str(did)
        if did in self.local_agents:
            del self.local_agents[did]
            
        # 清理托管映射
        if did in self.hosted_agent_mapping:
            del self.hosted_agent_mapping[did]
            
        # 清理路由缓存
        keys_to_remove = [k for k in self.route_cache.keys() if k[0] == did or k[1] == did]
        for key in keys_to_remove:
            del self.route_cache[key]
            
        logger.info(f"本地加速器已注销智能体: {did}")
    
    def is_local_agent(self, did: str) -> bool:
        """检查是否为本地智能体"""
        return str(did) in self.local_agents
    
    def get_local_agent(self, did: str):
        """获取本地智能体实例"""
        return self.local_agents.get(str(did))
    
    def can_accelerate(self, source_did: str, target_did: str, route_type: RouteType) -> bool:
        """检查是否可以加速（本地路由）"""
        source_did = str(source_did)
        target_did = str(target_did)
        
        # 检查目标是否为本地智能体
        if not self.is_local_agent(target_did):
            return False
        
        # 对于群组消息，检查是否有本地成员
        if route_type in [RouteType.GROUP_MESSAGE, RouteType.GROUP_CONNECT, RouteType.GROUP_MEMBERS]:
            return True  # 群组操作总是可以优化
        
        # API调用和点对点消息可以直接加速
        return True
    
    async def route_api_call(self, source_did: str, target_did: str, api_path: str, 
                           method: str = "GET", params: Dict[str, Any] = None) -> Dict[str, Any]:
        """路由API调用"""
        start_time = time.time()
        self.total_requests += 1
        
        source_did = str(source_did)
        target_did = str(target_did)
        
        try:
            if self.can_accelerate(source_did, target_did, RouteType.API_CALL):
                # 本地路由
                result = await self._local_api_call(source_did, target_did, api_path, method, params)
                self.local_requests += 1
                
                latency = (time.time() - start_time) * 1000
                self._update_local_latency(latency)
                
                logger.debug(f"本地API调用: {source_did} -> {target_did} {method} {api_path} ({latency:.2f}ms)")
                return result
            else:
                # 网络路由
                result = await self._network_api_call(source_did, target_did, api_path, method, params)
                self.network_requests += 1
                
                latency = (time.time() - start_time) * 1000
                self._update_network_latency(latency)
                
                logger.debug(f"网络API调用: {source_did} -> {target_did} {method} {api_path} ({latency:.2f}ms)")
                return result
                
        except Exception as e:
            logger.error(f"API调用失败: {source_did} -> {target_did} {api_path}: {e}")
            return {"status": "error", "message": str(e)}
    
    async def route_message(self, source_did: str, target_did: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """路由点对点消息"""
        start_time = time.time()
        self.total_requests += 1
        
        source_did = str(source_did)
        target_did = str(target_did)
        
        try:
            if self.can_accelerate(source_did, target_did, RouteType.MESSAGE):
                # 本地路由
                result = await self._local_message(source_did, target_did, message_data)
                self.local_requests += 1
                
                latency = (time.time() - start_time) * 1000
                self._update_local_latency(latency)
                
                logger.debug(f"本地消息: {source_did} -> {target_did} ({latency:.2f}ms)")
                return result
            else:
                # 网络路由
                result = await self._network_message(source_did, target_did, message_data)
                self.network_requests += 1
                
                latency = (time.time() - start_time) * 1000
                self._update_network_latency(latency)
                
                logger.debug(f"网络消息: {source_did} -> {target_did} ({latency:.2f}ms)")
                return result
                
        except Exception as e:
            logger.error(f"消息发送失败: {source_did} -> {target_did}: {e}")
            return {"status": "error", "message": str(e)}
    
    async def route_group_operation(self, source_did: str, group_hoster: str, group_id: str, 
                                  operation: RouteType, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """路由群组操作"""
        start_time = time.time()
        self.total_requests += 1
        
        source_did = str(source_did)
        group_hoster = str(group_hoster)
        
        try:
            # 检查群组主持者是否为本地智能体
            if self.is_local_agent(group_hoster):
                # 本地群组操作
                result = await self._local_group_operation(source_did, group_hoster, group_id, operation, data)
                self.local_requests += 1
                
                latency = (time.time() - start_time) * 1000
                self._update_local_latency(latency)
                
                logger.debug(f"本地群组操作: {source_did} -> {group_hoster}:{group_id} {operation.value} ({latency:.2f}ms)")
                return result
            else:
                # 网络群组操作
                result = await self._network_group_operation(source_did, group_hoster, group_id, operation, data)
                self.network_requests += 1
                
                latency = (time.time() - start_time) * 1000
                self._update_network_latency(latency)
                
                logger.debug(f"网络群组操作: {source_did} -> {group_hoster}:{group_id} {operation.value} ({latency:.2f}ms)")
                return result
                
        except Exception as e:
            logger.error(f"群组操作失败: {source_did} -> {group_hoster}:{group_id} {operation.value}: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _local_api_call(self, source_did: str, target_did: str, api_path: str, 
                            method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行本地API调用"""
        target_agent = self.get_local_agent(target_did)
        if not target_agent:
            raise ValueError(f"本地智能体不存在: {target_did}")
        
        # 构造请求数据
        request_data = {
            "type": "api_call",
            "api_path": api_path,
            "method": method,
            "params": params or {}
        }
        
        # 直接调用目标智能体的处理方法
        return target_agent.handle_request(source_did, request_data)
    
    async def _local_message(self, source_did: str, target_did: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行本地消息发送"""
        target_agent = self.get_local_agent(target_did)
        if not target_agent:
            raise ValueError(f"本地智能体不存在: {target_did}")
        
        # 构造请求数据
        request_data = {
            "type": "message",
            **message_data
        }
        
        # 直接调用目标智能体的处理方法
        return target_agent.handle_request(source_did, request_data)
    
    async def _local_group_operation(self, source_did: str, group_hoster: str, group_id: str, 
                                   operation: RouteType, data: Dict[str, Any]) -> Dict[str, Any]:
        """执行本地群组操作"""
        hoster_agent = self.get_local_agent(group_hoster)
        if not hoster_agent:
            raise ValueError(f"群组主持者不存在: {group_hoster}")
        
        # 构造请求数据
        request_data = {
            "type": operation.value,
            "group_id": group_id,
            **(data or {})
        }
        
        # 直接调用群组主持者的处理方法
        result = hoster_agent.handle_request(source_did, request_data)
        
        # 更新本地群组成员信息
        if operation == RouteType.GROUP_CONNECT:
            self.group_local_members.setdefault(group_id, set()).add(source_did)
        elif operation == RouteType.GROUP_MEMBERS and data and data.get("action") == "leave":
            if group_id in self.group_local_members:
                self.group_local_members[group_id].discard(source_did)
        
        return result
    
    async def _network_api_call(self, source_did: str, target_did: str, api_path: str, 
                              method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行网络API调用（回退到原始实现）"""
        # 这里应该调用原始的网络API调用逻辑
        # 为了简化，这里返回一个模拟结果
        logger.warning(f"网络API调用未实现: {source_did} -> {target_did} {api_path}")
        return {"status": "error", "message": "网络API调用未实现"}
    
    async def _network_message(self, source_did: str, target_did: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行网络消息发送（回退到原始实现）"""
        # 这里应该调用原始的网络消息发送逻辑
        logger.warning(f"网络消息发送未实现: {source_did} -> {target_did}")
        return {"status": "error", "message": "网络消息发送未实现"}
    
    async def _network_group_operation(self, source_did: str, group_hoster: str, group_id: str, 
                                     operation: RouteType, data: Dict[str, Any]) -> Dict[str, Any]:
        """执行网络群组操作（回退到原始实现）"""
        # 这里应该调用原始的网络群组操作逻辑
        logger.warning(f"网络群组操作未实现: {source_did} -> {group_hoster}:{group_id} {operation.value}")
        return {"status": "error", "message": "网络群组操作未实现"}
    
    def _update_local_latency(self, latency_ms: float):
        """更新本地延迟统计"""
        if self.local_requests == 1:
            self.avg_local_latency = latency_ms
        else:
            # 移动平均
            alpha = 0.1
            self.avg_local_latency = alpha * latency_ms + (1 - alpha) * self.avg_local_latency
    
    def _update_network_latency(self, latency_ms: float):
        """更新网络延迟统计"""
        if self.network_requests == 1:
            self.avg_network_latency = latency_ms
        else:
            # 移动平均
            alpha = 0.1
            self.avg_network_latency = alpha * latency_ms + (1 - alpha) * self.avg_network_latency
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        local_ratio = self.local_requests / self.total_requests if self.total_requests > 0 else 0
        network_ratio = self.network_requests / self.total_requests if self.total_requests > 0 else 0
        
        return {
            "total_requests": self.total_requests,
            "local_requests": self.local_requests,
            "network_requests": self.network_requests,
            "local_ratio": local_ratio,
            "network_ratio": network_ratio,
            "avg_local_latency_ms": round(self.avg_local_latency, 2),
            "avg_network_latency_ms": round(self.avg_network_latency, 2),
            "speedup_factor": round(self.avg_network_latency / self.avg_local_latency, 2) if self.avg_local_latency > 0 else 0,
            "registered_agents": len(self.local_agents),
            "hosted_agents": len(self.hosted_agent_mapping),
            "local_groups": len(self.group_local_members)
        }
    
    def get_local_agents_info(self) -> List[Dict[str, Any]]:
        """获取本地智能体信息"""
        agents_info = []
        
        for did, agent in self.local_agents.items():
            info = {
                "did": did,
                "type": "hosted" if did in self.hosted_agent_mapping else "normal",
                "parent_did": self.hosted_agent_mapping.get(did),
                "host": getattr(agent, 'host', 'localhost'),
                "port": getattr(agent, 'port', 'unknown')
            }
            
            # 获取托管信息
            if hasattr(agent, '_get_hosted_info'):
                hosted_info = agent._get_hosted_info()
                if hosted_info:
                    info.update(hosted_info)
            
            agents_info.append(info)
        
        return agents_info
    
    def optimize_group_routing(self, group_id: str) -> Dict[str, Any]:
        """优化群组路由"""
        local_members = self.group_local_members.get(group_id, set())
        total_members = len(local_members)  # 这里简化，实际应该获取完整成员列表
        
        optimization_info = {
            "group_id": group_id,
            "local_members": list(local_members),
            "local_member_count": len(local_members),
            "total_member_count": total_members,
            "local_ratio": len(local_members) / total_members if total_members > 0 else 0,
            "can_optimize": len(local_members) > 1
        }
        
        return optimization_info
    
    def clear_stats(self):
        """清空统计信息"""
        self.total_requests = 0
        self.local_requests = 0
        self.network_requests = 0
        self.avg_local_latency = 0.0
        self.avg_network_latency = 0.0
        self.route_cache.clear()
        logger.info("性能统计已清空")


class AcceleratedANPSDK:
    """带加速功能的ANP SDK包装器"""
    
    def __init__(self, original_sdk, accelerator: LocalAgentAccelerator = None):
        self.original_sdk = original_sdk
        self.accelerator = accelerator or LocalAgentAccelerator()
        
        # 将原始SDK的智能体注册到加速器
        if hasattr(original_sdk, 'local_agents'):
            for did, agent in original_sdk.local_agents.items():
                self.accelerator.register_agent(agent)
    
    async def call_api(self, source_did: str, target_did: str, api_path: str, 
                      method: str = "GET", params: Dict[str, Any] = None) -> Dict[str, Any]:
        """加速的API调用"""
        return await self.accelerator.route_api_call(source_did, target_did, api_path, method, params)
    
    async def send_message(self, source_did: str, target_did: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """加速的消息发送"""
        return await self.accelerator.route_message(source_did, target_did, message_data)
    
    async def group_message(self, source_did: str, group_hoster: str, group_id: str, 
                          message: str) -> Dict[str, Any]:
        """加速的群组消息"""
        data = {"content": message}
        return await self.accelerator.route_group_operation(
            source_did, group_hoster, group_id, RouteType.GROUP_MESSAGE, data
        )
    
    async def group_connect(self, source_did: str, group_hoster: str, group_id: str) -> Dict[str, Any]:
        """加速的群组连接"""
        return await self.accelerator.route_group_operation(
            source_did, group_hoster, group_id, RouteType.GROUP_CONNECT
        )
    
    async def group_members(self, source_did: str, group_hoster: str, group_id: str, 
                          action: str, member_did: str = None) -> Dict[str, Any]:
        """加速的群组成员管理"""
        data = {"action": action}
        if member_did:
            data["member_did"] = member_did
        
        return await self.accelerator.route_group_operation(
            source_did, group_hoster, group_id, RouteType.GROUP_MEMBERS, data
        )
    
    def get_performance_report(self) -> str:
        """获取性能报告"""
        stats = self.accelerator.get_performance_stats()
        agents_info = self.accelerator.get_local_agents_info()
        
        report = f"""
=== ANP SDK 本地加速性能报告 ===

总请求数: {stats['total_requests']}
本地请求: {stats['local_requests']} ({stats['local_ratio']:.1%})
网络请求: {stats['network_requests']} ({stats['network_ratio']:.1%})

平均延迟:
  本地: {stats['avg_local_latency_ms']}ms
  网络: {stats['avg_network_latency_ms']}ms
  加速倍数: {stats['speedup_factor']}x

注册智能体: {stats['registered_agents']}
托管智能体: {stats['hosted_agents']}
本地群组: {stats['local_groups']}

=== 本地智能体列表 ===
"""
        
        for agent_info in agents_info:
            report += f"\n- {agent_info['did']}"
            report += f" ({agent_info['type']})"
            if agent_info.get('parent_did'):
                report += f" -> {agent_info['parent_did']}"
            report += f" @ {agent_info['host']}:{agent_info['port']}"
        
        return report


if __name__ == "__main__":
    # 测试代码
    import asyncio
    
    async def test_accelerator():
        print("测试本地智能体加速器...")
        
        accelerator = LocalAgentAccelerator()
        
        # 模拟智能体
        class MockAgent:
            def __init__(self, did, host="localhost", port="9527"):
                self.id = did
                self.host = host
                self.port = port
            
            def handle_request(self, source_did, request_data):
                return {
                    "status": "success",
                    "message": f"Mock response from {self.id}",
                    "request_type": request_data.get("type"),
                    "source": source_did
                }
        
        # 注册测试智能体
        agent1 = MockAgent("did:wba:test:agent1")
        agent2 = MockAgent("did:wba:test:agent2")
        
        accelerator.register_agent(agent1)
        accelerator.register_agent(agent2)
        
        # 测试API调用
        result = await accelerator.route_api_call(
            "did:wba:test:agent1",
            "did:wba:test:agent2",
            "/test/api",
            "GET",
            {"param1": "value1"}
        )
        print(f"API调用结果: {result}")
        
        # 测试消息发送
        result = await accelerator.route_message(
            "did:wba:test:agent1",
            "did:wba:test:agent2",
            {"message_type": "text", "content": "Hello!"}
        )
        print(f"消息发送结果: {result}")
        
        # 获取性能统计
        stats = accelerator.get_performance_stats()
        print(f"性能统计: {stats}")
        
        print("测试完成")
    
    asyncio.run(test_accelerator())