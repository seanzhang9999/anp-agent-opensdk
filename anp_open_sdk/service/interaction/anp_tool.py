import asyncio
import json
import yaml
import aiohttp
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from agent_connect.authentication import DIDWbaAuthHeader


class ANPTool:
    name: str = "anp_tool"
    description: str = """使用代理网络协议（ANP）与其他智能体进行交互。
1. 使用时需要输入文档 URL 和 HTTP 方法。
2. 在工具内部，URL 将被解析，并根据解析结果调用相应的 API。
3. 注意：任何使用 ANPTool 获取的 URL 都必须使用 ANPTool 调用，不要直接调用。
"""
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "(必填) 代理描述文件或 API 端点的 URL",
            },
            "method": {
                "type": "string",
                "description": "(可选) HTTP 方法，如 GET、POST、PUT 等，默认为 GET",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "(可选) HTTP 请求头",
                "default": {},
            },
            "params": {
                "type": "object",
                "description": "(可选) URL 查询参数",
                "default": {},
            },
            "body": {
                "type": "object",
                "description": "(可选) POST/PUT 请求的请求体",
            },
        },
        "required": ["url"],
    }

    # 声明 auth_client 字段
    auth_client: Optional[DIDWbaAuthHeader] = None

    def __init__(
        self,
        did_document_path: Optional[str] = None,
        private_key_path: Optional[str] = None,
        **data,
    ):
        """
        使用 DID 认证初始化 ANPTool

        参数:
            did_document_path (str, 可选): DID 文档文件路径。如果为 None，则使用默认路径。
            private_key_path (str, 可选): 私钥文件路径。如果为 None，则使用默认路径。
        """
        super().__init__(**data)

        # 获取当前脚本目录
        current_dir = Path(__file__).parent
        # 获取项目根目录
        base_dir = current_dir.parent

        # 使用提供的路径或默认路径
        if did_document_path is None:
            # 首先尝试从环境变量中获取
            did_document_path = os.environ.get("DID_DOCUMENT_PATH")
            if did_document_path is None:
                # 使用默认路径
                did_document_path = str(base_dir / "use_did_test_public/coder.json")

        if private_key_path is None:
            # 首先尝试从环境变量中获取
            private_key_path = os.environ.get("DID_PRIVATE_KEY_PATH")
            if private_key_path is None:
                # 使用默认路径
                private_key_path = str(
                    base_dir / "use_did_test_public/key-1_private.pem"
                )

        logging.info(
            f"ANPTool 初始化 - DID 路径: {did_document_path}, 私钥路径: {private_key_path}"
        )

        self.auth_client = DIDWbaAuthHeader(
            did_document_path=did_document_path, private_key_path=private_key_path
        )

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Dict[str, str] = None,
        params: Dict[str, Any] = None,
        body: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        执行 HTTP 请求以与其他代理交互

        参数:
            url (str): 代理描述文件或 API 端点的 URL
            method (str, 可选): HTTP 方法，默认为 "GET"
            headers (Dict[str, str], 可选): HTTP 请求头
            params (Dict[str, Any], 可选): URL 查询参数
            body (Dict[str, Any], 可选): POST/PUT 请求的请求体

        返回:
            Dict[str, Any]: 响应内容
        """

        if headers is None:
            headers = {}
        if params is None:
            params = {}

        logging.info(f"ANP 请求: {method} {url}")

        # 添加基本请求头
        if "Content-Type" not in headers and method in ["POST", "PUT", "PATCH"]:
            headers["Content-Type"] = "application/json"

        # 添加 DID 认证
        if self.auth_client:
            try:
                auth_headers = self.auth_client.get_auth_header(url)
                headers.update(auth_headers)
            except Exception as e:
                logging.error(f"获取认证头失败: {str(e)}")

        async with aiohttp.ClientSession() as session:
            # 准备请求参数
            request_kwargs = {
                "url": url,
                "headers": headers,
                "params": params,
            }

            # 如果有请求体且方法支持，添加请求体
            if body is not None and method in ["POST", "PUT", "PATCH"]:
                request_kwargs["json"] = body

            # 执行请求
            http_method = getattr(session, method.lower())

            try:
                async with http_method(**request_kwargs) as response:
                    logging.info(f"ANP 响应: 状态码 {response.status}")

                    # 检查响应状态
                    if (
                        response.status == 401
                        and "Authorization" in headers
                        and self.auth_client
                    ):
                        logging.warning(
                            "认证失败 (401)，尝试重新获取认证"
                        )
                        # 如果认证失败且使用了 token，清除 token 并重试
                        self.auth_client.clear_token(url)
                        # 重新获取认证头
                        headers.update(
                            self.auth_client.get_auth_header(url, force_new=True)
                        )
                        # 重新执行请求
                        request_kwargs["headers"] = headers
                        async with http_method(**request_kwargs) as retry_response:
                            logging.info(
                                f"ANP 重试响应: 状态码 {retry_response.status}"
                            )
                            return await self._process_response(retry_response, url)

                    return await self._process_response(response, url)
            except aiohttp.ClientError as e:
                logging.error(f"HTTP 请求失败: {str(e)}")
                return {"error": f"HTTP 请求失败: {str(e)}", "status_code": 500}

    async def _process_response(self, response, url):
        """处理 HTTP 响应"""
        # 如果认证成功，更新 token
        if response.status == 200 and self.auth_client:
            try:
                self.auth_client.update_token(url, dict(response.headers))
            except Exception as e:
                logging.error(f"更新 token 失败: {str(e)}")

        # 获取响应内容类型
        content_type = response.headers.get("Content-Type", "").lower()

        # 获取响应文本
        text = await response.text()

        # 根据内容类型处理响应
        if "application/json" in content_type:
            # 处理 JSON 响应
            try:
                result = json.loads(text)
                logging.info("成功解析 JSON 响应")
            except json.JSONDecodeError:
                logging.warning(
                    "Content-Type 声明为 JSON 但解析失败，返回原始文本"
                )
                result = {"text": text, "format": "text", "content_type": content_type}
        elif "application/yaml" in content_type or "application/x-yaml" in content_type:
            # 处理 YAML 响应
            try:
                result = yaml.safe_load(text)
                logging.info("成功解析 YAML 响应")
                result = {
                    "data": result,
                    "format": "yaml",
                    "content_type": content_type,
                }
            except yaml.YAMLError:
                logging.warning(
                    "Content-Type 声明为 YAML 但解析失败，返回原始文本"
                )
                result = {"text": text, "format": "text", "content_type": content_type}
        else:
            # 默认返回文本
            result = {"text": text, "format": "text", "content_type": content_type}

        # 添加状态码到结果
        if isinstance(result, dict):
            result["status_code"] = response.status
        else:
            result = {
                "data": result,
                "status_code": response.status,
                "format": "unknown",
                "content_type": content_type,
            }

        # 添加 URL 到结果以便跟踪
        result["url"] = str(url)

        return result

    async def execute_with_two_way_auth(
            self,
            url: str,
            method: str = "GET",
            headers: Dict[str, str] = None,
            params: Dict[str, Any] = None,
            body: Dict[str, Any] = None,
            anpsdk=None,  # 添加 anpsdk 参数
            caller_agent: str = None,  # 添加发起 agent 参数
            target_agent: str = None,  # 添加目标 agent 参数
            use_two_way_auth: bool = False  # 是否使用双向认证
    ) -> Dict[str, Any]:
        """
        使用双向认证执行 HTTP 请求以与其他代理交互

        参数:
            url (str): 代理描述文件或 API 端点的 URL
            method (str, 可选): HTTP 方法，默认为 "GET"
            headers (Dict[str, str], 可选): HTTP 请求头（将传递给 agent_auth_two_way 处理）
            params (Dict[str, Any], 可选): URL 查询参数
            body (Dict[str, Any], 可选): POST/PUT 请求的请求体

        返回:
            Dict[str, Any]: 响应内容
        """

        if headers is None:
            headers = {}
        if params is None:
            params = {}

        logging.info(f"ANP 双向认证请求: {method} {url}")

        try:
            # 1. 准备完整的 URL（包含查询参数）
            final_url = url
            if params:
                from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
                parsed_url = urlparse(url)
                existing_params = parse_qs(parsed_url.query)

                # 合并现有参数和新参数
                for key, value in params.items():
                    existing_params[key] = [str(value)]

                # 重新构建 URL
                new_query = urlencode(existing_params, doseq=True)
                final_url = urlunparse((
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    new_query,
                    parsed_url.fragment
                ))

            # 2. 准备请求体数据
            request_data = None
            if body is not None and method.upper() in ["POST", "PUT", "PATCH"]:
                request_data = body

            # 3. 调用 agent_auth_two_way（需要传入必要的参数）
            # 注意：这里暂时使用占位符，后续需要根据实际情况调整
            from ..auth.auth_client import agent_auth_request
            status, response, info, is_auth_pass = await agent_auth_request(
                caller_agent=caller_agent,  # 需要传入调用方智能体ID
                target_agent=target_agent,  # 需要传入目标方智能体ID，如果对方没有ID，可以随便写，因为对方不会响应这个信息
                request_url=final_url,
                method=method.upper(),
                json_data=request_data,
                custom_headers=headers,  # 传递自定义头部给 agent_auth_two_way 处理
                use_two_way_auth= use_two_way_auth
            )

            logging.info(f"ANP 双向认证响应: 状态码 {status}")

            # 4. 处理响应，保持与原 execute 方法相同的响应格式
            result = await self._process_two_way_response(response, final_url, status, info, is_auth_pass)

            return result

        except Exception as e:
            logging.error(f"双向认证请求失败: {str(e)}")
            return {
                "error": f"双向认证请求失败: {str(e)}",
                "status_code": 500,
                "url": url
            }

    async def _process_two_way_response(self, response, url, status, info, is_auth_pass):
        """处理双向认证的 HTTP 响应"""

        # 如果 response 已经是处理过的字典格式
        if isinstance(response, dict):
            result = response
        elif isinstance(response, str):
            # 尝试解析为 JSON
            try:
                result = json.loads(response)
                logging.info("成功解析 JSON 响应")
            except json.JSONDecodeError:
                # 如果不是 JSON，作为文本处理
                result = {
                    "text": response,
                    "format": "text",
                    "content_type": "text/plain"
                }
        else:
            # 其他类型的响应
            result = {
                "data": response,
                "format": "unknown",
                "content_type": "unknown"
            }

        # 添加状态码和其他信息
        if isinstance(result, dict):
            result["status_code"] = status
            result["url"] = str(url)
            result["auth_info"] = info
            result["is_auth_pass"] = is_auth_pass
        else:
            result = {
                "data": result,
                "status_code": status,
                "url": str(url),
                "auth_info": info,
                "is_auth_pass": is_auth_pass,
                "format": "unknown"
            }

        return result