"""配置类型定义和协议

此模块提供配置项的类型提示和协议定义，支持IDE代码提示和类型检查。
"""

from typing import Protocol, List, Dict, Any, Optional
from pathlib import Path

class MultiAgentModeConfig(Protocol):
    agents_cfg_path: str


class AnpSdkAgentConfig(Protocol):
    """ANP SDK 智能体配置协议"""
    demo_agent1: str
    demo_agent2: str
    demo_agent3: str

class AnpSdkConfig(Protocol):
    """ANP SDK 配置协议"""
    debug_mode: bool
    host: str
    port: int
    user_did_path: str
    user_hosted_path: str
    auth_virtual_dir: str
    msg_virtual_dir: str
    token_expire_time: int
    nonce_expire_minutes: int
    jwt_algorithm: str
    user_did_key_id: str
    helper_lang: str
    agent: AnpSdkAgentConfig




class AnpSdkProxyConfig(Protocol):
    """ANP SDK 代理配置协议"""
    enabled: bool
    host: str
    port: int


class LlmConfig(Protocol):
    """LLM 配置协议"""
    api_url: str
    default_model: str
    max_tokens: int
    system_prompt: str


class MailConfig(Protocol):
    """邮件配置协议"""
    use_local_backend: bool
    local_backend_path: str
    smtp_server: str
    smtp_port: int
    imap_server: str
    imap_port: int
    hoster_mail_user: str
    sender_mail_user: str
    register_mail_user: str



class ChatConfig(Protocol):
    """聊天配置协议"""
    max_history_items: int
    max_process_count: int


class WebApiServerConfig(Protocol):
    """Web API 服务器配置协议"""
    generate_new_did_each_time: bool
    webui_host: str
    webui_port: int


class WebApiConfig(Protocol):
    """Web API 配置协议"""
    server: WebApiServerConfig


class AccelerationConfig(Protocol):
    """性能优化配置协议"""
    enable_local: bool
    performance_monitoring: bool
    cache_size: int


class EnvConfig(Protocol):
    """环境变量配置协议"""
    # 应用配置
    debug_mode: Optional[bool]
    host: Optional[str]
    port: Optional[int]

    # 系统环境变量
    system_path: Optional[List[Path]]
    home_dir: Optional[Path]
    user_name: Optional[str]
    shell: Optional[str]
    temp_dir: Optional[Path]
    python_path: Optional[List[Path]]
    python_home: Optional[str]
    virtual_env: Optional[str]

    # 开发工具
    java_home: Optional[str]
    node_path: Optional[str]
    go_path: Optional[str]

    # API 密钥
    openai_api_key: Optional[str]
    anthropic_api_key: Optional[str]

    # 邮件密码
    mail_password: Optional[str]
    hoster_mail_password: Optional[str]
    sender_mail_password: Optional[str]

    # 数据库和服务
    database_url: Optional[str]
    redis_url: Optional[str]

    # 其他配置
    use_local_mail: Optional[bool]
    enable_local_acceleration: Optional[bool]


class LogDetailConfig(Protocol):
    file: Optional[str]
    max_size: Optional[int]

class LogConfig(Protocol):
    """日志配置协议"""
    log_level: Optional[str]
    detail: LogDetailConfig




class SecretsConfig(Protocol):
    """敏感信息配置协议"""
    openai_api_key: Optional[str]
    anthropic_api_key: Optional[str]
    mail_password: Optional[str]
    hoster_mail_password: Optional[str]
    sender_mail_password: Optional[str]
    database_url: Optional[str]


class BaseUnifiedConfigProtocol(Protocol):
    """统一配置协议"""
    # 主要配置节点
    multi_agent_mode: MultiAgentModeConfig
    log_settings: LogConfig
    anp_sdk: AnpSdkConfig
    llm: LlmConfig
    mail: MailConfig
    chat: ChatConfig
    web_api: WebApiConfig
    acceleration: AccelerationConfig
    
    # 环境变量和敏感信息
    env: EnvConfig
    secrets: SecretsConfig
    
    # 方法
    def resolve_path(self, path: str) -> Path: ...
    def get_app_root(self) -> Path: ...
    def reload(self) -> None: ...
    def save(self) -> bool: ...
    def to_dict(self) -> Dict[str, Any]: ...
    def add_to_path(self, new_path: str) -> None: ...
    def find_in_path(self, filename: str) -> List[Path]: ...
    def get_path_info(self) -> Dict[str, Any]: ...