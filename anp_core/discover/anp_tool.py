import asyncio
import json
import yaml
import aiohttp
import secrets
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from core.config import settings

from anp_core.auth.did_auth import generate_or_load_did

# 尝试导入DIDWbaAuthHeader，如果不可用则设置标志
try:
    from anp_core.agent_connect.authentication import DIDWbaAuthHeader
    HAS_AGENT_CONNECT = True
except ImportError:
    HAS_AGENT_CONNECT = False
    logging.warning("anp_core.agent_connect.authentication模块不可用，ANPTool将以有限功能运行")

class ANPTool:
    name: str = "anp_tool"
    description: str = """Interact with other agents using the Agent Network Protocol (ANP).
1. When using, you need to input a document URL and HTTP method.
2. Inside the tool, the URL will be parsed and corresponding APIs will be called based on the parsing results.
3. Note that any URL obtained using ANPTool must be called using ANPTool, do not call it directly yourself.
"""
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "(required) URL of the agent description file or API endpoint",
            },
            "method": {
                "type": "string",
                "description": "(optional) HTTP method, such as GET, POST, PUT, etc., default is GET",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "(optional) HTTP request headers",
                "default": {},
            },
            "params": {
                "type": "object",
                "description": "(optional) URL query parameters",
                "default": {},
            },
            "body": {
                "type": "object",
                "description": "(optional) Request body for POST/PUT requests",
            },
        },
        "required": ["url"],
    }

    # Declare auth_client field
    auth_client: Optional[DIDWbaAuthHeader] = None

    def __init__(
        self,
        did_document_path: Optional[str] = None,
        private_key_path: Optional[str] = None,
        **data,
    ):
        """
        Initialize ANPTool with DID authentication

        Args:
            did_document_path (str, optional): Path to DID document file. If None, will use default path.
            private_key_path (str, optional): Path to private key file. If None, will use default path.
        """
        # Get current script directory
        current_dir = Path(__file__).parent
        # Get project root directory
        base_dir = current_dir.parent

        # Use provided paths or default paths
        if did_document_path is None:
            # Try to get from environment variable first
            did_document_path = os.environ.get("DID_DOCUMENT_PATH")
            if did_document_path is None:
                # Use default path
                did_document_path = str(base_dir / "use_did_test_public/did.json")

        if private_key_path is None:
            # Try to get from environment variable first
            private_key_path = os.environ.get("DID_PRIVATE_KEY_PATH")
            if private_key_path is None:
                # Use default path
                private_key_path = str(
                    base_dir / "use_did_test_public/key-1_private.pem"
                )

        logging.info(
            f"ANPTool initialized - DID path: {did_document_path}, private key path: {private_key_path}"
        )

        # 只有在agent_connect模块可用时才初始化auth_client
        if HAS_AGENT_CONNECT:
            try:
                # 使用同步方式初始化DID认证
                unique_id = secrets.token_hex(8)
                logging.info(f"使用唯一ID: {unique_id}")
                
                # 使用提供的路径初始化DIDWbaAuthHeader
                self.auth_client = DIDWbaAuthHeader(
                    did_document_path=did_document_path,
                    private_key_path=private_key_path
                )
                logging.info("DIDWbaAuthHeader初始化成功")
            except Exception as e:
                logging.error(f"初始化DIDWbaAuthHeader失败: {e}")
                self.auth_client = None
        else:
            logging.warning("由于缺少必要模块，DID认证功能不可用")
            self.auth_client = None
            
    # 添加异步初始化方法
    @classmethod
    async def create_async(cls, 
                          did_document_path: Optional[str] = None,
                          private_key_path: Optional[str] = None,
                          **data):
        """异步创建ANPTool实例
        
        Args:
            did_document_path (str, optional): DID文档路径
            private_key_path (str, optional): 私钥路径
        
        Returns:
            ANPTool: 初始化好的ANPTool实例
        """
        instance = cls(did_document_path, private_key_path, **data)
        
        # 如果需要异步初始化DID
        if HAS_AGENT_CONNECT and instance.auth_client is not None:
            try:
                unique_id = secrets.token_hex(8)
                logging.info(f"异步初始化DID，使用唯一ID: {unique_id}")
                
                # 异步获取DID文档
                did_document, keys, user_dir = await generate_or_load_did(unique_id)
                os.environ['did-id'] = did_document.get('id')
                
                # 使用settings获取文件路径
                did_document_path = Path(user_dir) / settings.DID_DOCUMENT_FILENAME
                private_key_path = Path(user_dir) / settings.PRIVATE_KEY_FILENAME
                logging.info(f"DID文档路径: {did_document_path}")
                logging.info(f"私钥路径: {private_key_path}")
                
                # 重新初始化auth_client
                instance.auth_client = DIDWbaAuthHeader(
                    did_document_path=str(did_document_path),
                    private_key_path=str(private_key_path)
                )
                logging.info("异步DIDWbaAuthHeader初始化成功")
            except Exception as e:
                logging.error(f"异步初始化DIDWbaAuthHeader失败: {e}")
                instance.auth_client = None
        
        return instance

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Dict[str, str] = None,
        params: Dict[str, Any] = None,
        body: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute HTTP request to interact with other agents

        Args:
            url (str): URL of the agent description file or API endpoint
            method (str, optional): HTTP method, default is "GET"
            headers (Dict[str, str], optional): HTTP request headers
            params (Dict[str, Any], optional): URL query parameters
            body (Dict[str, Any], optional): Request body for POST/PUT requests

        Returns:
            Dict[str, Any]: Response content
        """

        if headers is None:
            headers = {}
        if params is None:
            params = {}

        logging.info(f"ANP请求: {method} {url}")

        # Add basic request headers
        if "Content-Type" not in headers and method in ["POST", "PUT", "PATCH"]:
            headers["Content-Type"] = "application/json"

        # Add DID authentication
        if self.auth_client:
            try:
                logging.info("尝试添加DID认证头")
                auth_headers = self.auth_client.get_auth_header(url)
                headers.update(auth_headers)
                logging.info("成功添加DID认证头")
            except Exception as e:
                logging.error(f"获取认证头失败: {str(e)}")
        else:
            logging.info("DID认证不可用，将使用无认证模式发送请求")

        try:
            async with aiohttp.ClientSession() as session:
                # Prepare request parameters
                request_kwargs = {
                    "url": url,
                    "headers": headers,
                    "params": params,
                }

                # If there is a request body and the method supports it, add the request body
                if body is not None and method in ["POST", "PUT", "PATCH"]:
                    request_kwargs["json"] = body

                # Execute request
                http_method = getattr(session, method.lower())

                try:
                    logging.info(f"发送HTTP请求: {method} {url}")
                    async with http_method(**request_kwargs) as response:
                        status_code = response.status
                        logging.info(f"收到HTTP响应: 状态码 {status_code}")

                        # 检查响应状态码
                        if status_code >= 400:
                            error_msg = f"HTTP请求失败: 状态码 {status_code}"
                            logging.error(error_msg)
                            return {"error": error_msg, "status_code": status_code}

                        # Check response status for authentication retry
                        if (
                            status_code == 401
                            and "Authorization" in headers
                            and self.auth_client
                        ):
                            logging.warning(
                                "认证失败(401)，尝试重新获取认证"
                            )
                            # If authentication fails and a token was used, clear the token and retry
                            self.auth_client.clear_token(url)
                            # Get authentication header again
                            headers.update(
                                self.auth_client.get_auth_header(url, force_new=True)
                            )
                            # Execute request again
                            request_kwargs["headers"] = headers
                            logging.info("使用新的认证头重试请求")
                            async with http_method(**request_kwargs) as retry_response:
                                retry_status = retry_response.status
                                logging.info(f"重试响应: 状态码 {retry_status}")
                                if retry_status >= 400:
                                    error_msg = f"重试请求失败: 状态码 {retry_status}"
                                    logging.error(error_msg)
                                    return {"error": error_msg, "status_code": retry_status}
                                return await self._process_response(retry_response, url)

                        return await self._process_response(response, url)
                except aiohttp.ClientError as e:
                    error_msg = f"HTTP请求失败: {str(e)}"
                    logging.error(error_msg)
                    return {"error": error_msg, "status_code": 500}
        except Exception as e:
            error_msg = f"执行请求时发生异常: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg, "status_code": 500}

    async def _process_response(self, response, url):
        """Process HTTP response"""
        try:
            logging.info(f"处理HTTP响应: URL={url}, 状态码={response.status}")
            
            # If authentication is successful, update the token
            if response.status == 200 and self.auth_client:
                try:
                    logging.info("尝试更新认证令牌")
                    self.auth_client.update_token(url, dict(response.headers))
                    logging.info("成功更新认证令牌")
                except Exception as e:
                    logging.error(f"更新令牌失败: {str(e)}")

            # Get response content type
            content_type = response.headers.get("Content-Type", "").lower()
            logging.info(f"响应内容类型: {content_type}")

            # Get response text
            try:
                text = await response.text()
                logging.info(f"成功获取响应文本，长度: {len(text)}字节")
            except Exception as e:
                error_msg = f"读取响应文本失败: {str(e)}"
                logging.error(error_msg)
                return {"error": error_msg, "status_code": response.status, "url": str(url)}

            # Process response based on content type
            if "application/json" in content_type:
                # Process JSON response
                try:
                    logging.info("尝试解析JSON响应")
                    result = json.loads(text)
                    logging.info("成功解析JSON响应")
                except json.JSONDecodeError as e:
                    logging.warning(
                        f"内容类型声明为JSON但解析失败: {str(e)}，返回原始文本"
                    )
                    result = {"text": text, "format": "text", "content_type": content_type, "parse_error": str(e)}
            elif "application/yaml" in content_type or "application/x-yaml" in content_type:
                # Process YAML response
                try:
                    logging.info("尝试解析YAML响应")
                    result = yaml.safe_load(text)
                    logging.info("成功解析YAML响应")
                    result = {
                        "data": result,
                        "format": "yaml",
                        "content_type": content_type,
                    }
                except yaml.YAMLError as e:
                    logging.warning(
                        f"内容类型声明为YAML但解析失败: {str(e)}，返回原始文本"
                    )
                    result = {"text": text, "format": "text", "content_type": content_type, "parse_error": str(e)}
            else:
                # Default to text
                logging.info(f"使用文本格式处理响应，内容类型: {content_type}")
                result = {"text": text, "format": "text", "content_type": content_type}

            # Add status code to result
            if isinstance(result, dict):
                result["status_code"] = response.status
            else:
                logging.warning(f"响应结果不是字典类型，将其包装为字典: {type(result)}")
                result = {
                    "data": result,
                    "status_code": response.status,
                    "format": "unknown",
                    "content_type": content_type,
                }

            # Add URL to result for tracking
            result["url"] = str(url)
            logging.info("响应处理完成")
            return result
            
        except Exception as e:
            error_msg = f"处理响应时发生异常: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg, "status_code": response.status if response else 500, "url": str(url)}