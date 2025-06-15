# 统一配置系统设计方案
## 1. 设计目标
### 核心目标
  - 根目录定位：通过anp_open_sdk自动检测项目根目录，任何层级的代码使用{APP_ROOT}占位符，能正确定位项目根目录和资源文件
  - YAML多级编辑：充分发挥YAML的层次结构和可读性可注释优势
  - 环境变量统一管理：避免密钥泄露，统一管理env和系统环境变量映射
  - 属性访问：支持 config.anp_sdk.port 风格访问，提供代码提示

## 2. 架构设计
  ### 2.1 文件结构

  ```
  anp_open_sdk/config/
  ├── __init__.py
  ├── unified_config.py          # 核心配置管理器
  ├── config_types.py           # 类型定义和协议
  ├── path_resolver.py          # 路径解析器（保留兼容）
  ├── unified_config.yaml       # 主配置文件
  ├── unified_config.yaml.template  # 配置模板
  └── legacy/                   # 旧配置文件（逐步迁移）
      ├── dynamic_config.py
      ├── config.py
      └── *.yaml
  ```
  ### 2.2 核心组件
#### A. UnifiedConfig（主配置管理器）
  ```
class UnifiedConfig:
    """统一配置管理器"""
    - 自动检测项目根目录
    - 加载YAML配置文件
    - 创建配置树支持属性访问
    - 环境变量映射和类型转换
    - 路径占位符解析
  ```
#### B. ConfigNode（配置节点）

  ```
class ConfigNode:
    """配置节点，支持属性访问和代码提示"""
    - 动态属性创建
    - 嵌套配置支持
    - 运行时配置更新
   ```
#### C. EnvConfig（环境变量配置）

  ```
class EnvConfig:
    """环境变量配置节点"""
    - 预定义环境变量映射
    - 动态环境变量访问
    - 类型转换（boolean、integer、path_list等）
    - 敏感信息保护
  ```
## 3. 配置文件设计
### 3.1 主配置文件（unified_config.yaml）

```yaml
# ANP SDK 统一配置文件
# 项目根目录自动检测，支持 {APP_ROOT} 占位符

# 应用核心配置
anp_sdk:
  debug_mode: true
  host: localhost
  port: 9527
  user_did_path: "{APP_ROOT}/anp_open_sdk/anp_users"
  user_hosted_path: "{APP_ROOT}/anp_open_sdk/anp_users_hosted"
  auth_virtual_dir: "wba/auth"
  msg_virtual_dir: "/agent/message"
  token_expire_time: 3600
  
  agent:
    demo_agent1: "本田"
    demo_agent2: "雅马哈" 
    demo_agent3: "铃木"

# LLM 配置
llm:
  api_url: "api.302ai.cn"
  default_model: "deepseek/deepseek-chat-v3"
  max_tokens: 512
  system_prompt: "你是一个智能助手"

# 邮件配置
mail:
  use_local_backend: true
  local_backend_path: "{APP_ROOT}/anp_open_sdk/simulate/mail_local_backend"
  smtp_server: "smtp.gmail.com"
  smtp_port: 587

# 环境变量映射定义
env_mapping:
  # 应用配置
  debug_mode: ANP_DEBUG
  host: ANP_HOST
  port: ANP_PORT
  
  # 系统环境变量
  system_path: PATH
  home_dir: HOME
  user_name: USER
  python_path: PYTHONPATH
  
  # API 密钥
  openai_api_key: OPENAI_API_KEY
  anthropic_api_key: ANTHROPIC_API_KEY
  
  # 数据库和服务
  database_url: DATABASE_URL
  redis_url: REDIS_URL
  mail_password: MAIL_PASSWORD

# 敏感信息列表（不缓存，每次从环境变量读取）
secrets:
  - openai_api_key
  - anthropic_api_key
  - mail_password
  - database_url

# 环境变量类型转换
env_types:
  debug_mode: boolean
  port: integer
  smtp_port: integer
  system_path: path_list
  python_path: path_list
  home_dir: path
  timeout: float

# 路径处理配置
path_config:
  path_separator: ":"  # Linux/macOS: ":", Windows: ";"
  resolve_paths: true
  validate_existence: false
  ```

### 3.2 配置注释
```
# 这是行注释
anp_sdk:
  port: 9527          # 行尾注释
  # debug_mode: true  # 注释掉的配置（暂时不用）
  host: localhost
  
  # 多行注释说明
  # 这个配置用于设置用户DID路径
  # 支持 {APP_ROOT} 占位符自动替换
  user_did_path: "{APP_ROOT}/anp_open_sdk/anp_users"
  
  # TODO: 这个功能还在开发中，暂时注释
  # experimental_feature: true
  
  # DEPRECATED: 这个配置已废弃，将在下个版本移除
  # old_config: "legacy_value"

# ==========================================
# 环境变量配置区域
# ==========================================
env_mapping:
  openai_api_key: OPENAI_API_KEY    # OpenAI API密钥
  # anthropic_api_key: ANTHROPIC_API_KEY  # 暂时不用Anthropic
  ```


## 4. 使用说明
### 4.1 基本使用
#### 导入配置

```Python
from anp_open_sdk.config import config

# 或者显式导入
from anp_open_sdk.config.unified_config import config
  ```
#### 配置文件访问（支持代码提示）
  
```
# 应用配置
port = config.anp_sdk.port                    # 9527
host = config.anp_sdk.host                    # "localhost"
user_path = config.anp_sdk.user_did_path      # 自动解析 {APP_ROOT}

# LLM 配置
model = config.llm.default_model              # "deepseek/deepseek-chat-v3"
max_tokens = config.llm.max_tokens            # 512

# 邮件配置
smtp_port = config.mail.smtp_port             # 587
  ```

#### 环境变量访问

```
# 预定义环境变量（有代码提示）
api_key = config.env.openai_api_key           # 读取 OPENAI_API_KEY
debug = config.env.debug_mode                 # 读取 ANP_DEBUG，自动转换为 boolean

# 系统环境变量
home = config.env.home_dir                    # 读取 HOME，返回 Path 对象
paths = config.env.system_path                # 读取 PATH，返回 List[Path]

# 动态环境变量
custom = config.env.my_custom_var             # 读取 MY_CUSTOM_VAR
  ```
#### 敏感信息访问

  ```
# 敏感信息（不缓存，每次重新读取）
api_key = config.secrets.openai_api_key
db_url = config.secrets.database_url
mail_pwd = config.secrets.mail_password
  ```

### 4.2 路径操作
#### 路径解析
  ```
# 自动解析占位符和相对路径
user_path = config.resolve_path(config.anp_sdk.user_did_path)
# 返回: PosixPath('/absolute/path/to/anp_open_sdk/anp_users')

# 手动路径解析
log_path = config.resolve_path("{APP_ROOT}/logs/app.log")
relative_path = config.resolve_path("data/config.json")  # 相对于项目根目录
  ```

#### 路径工具

  ```
# 查找可执行文件
python_exe = config.find_in_path("python3")
git_exe = config.find_in_path("git")

# 添加路径到 PATH
config.add_to_path("/usr/local/custom/bin")

# 获取路径信息
path_info = config.get_path_info()
print(f"PATH 中有 {path_info['path_count']} 个目录")
  ```

### 4.3 配置更新
#### 运行时更新

  ```
# 更新配置值
config.anp_sdk.port = 8080
config.llm.max_tokens = 1024

# 保存到文件
config.save()

# 重新加载配置
config.reload()

# 重新加载环境变量
config.env.reload()
  ```
#### 批量更新

  ```
# 批量更新配置
config.update({
    "anp_sdk": {
        "port": 8080,
        "debug_mode": False
    },
    "llm": {
        "max_tokens": 1024
    }
})
  ```

### 4.4 高级功能
#### 配置验证

  ```
# 检查必需的环境变量
missing = config.validate_required_env([
    'openai_api_key', 
    'database_url'
])
if missing:
    raise RuntimeError(f"缺少环境变量: {missing}")
  ```
#### 开发环境检查

  ```
# 检查开发工具
dev_status = config.check_dev_environment()
for tool, status in dev_status.items():
    print(f"{tool}: {'✓' if status else '✗'}")
  ```
#### 配置导出

  ```
# 导出当前配置
config_dict = config.to_dict()

# 导出环境变量配置
env_dict = config.env.to_dict()

# 生成配置文档
config.generate_docs("config_reference.md")
  ```

## 5. 类型提示支持
### 5.1 配置协议定义

  ```
# anp_open_sdk/config/config_types.py
from typing import Protocol, List
from pathlib import Path

class AnpSdkConfig(Protocol):
    debug_mode: bool
    host: str
    port: int
    user_did_path: str
    token_expire_time: int

class LlmConfig(Protocol):
    api_url: str
    default_model: str
    max_tokens: int

class EnvConfig(Protocol):
    openai_api_key: str
    debug_mode: bool
    system_path: List[Path]
    home_dir: Path

class UnifiedConfigProtocol(Protocol):
    anp_sdk: AnpSdkConfig
    llm: LlmConfig
    env: EnvConfig
  ```

### 5.2 IDE 支持
 - PyCharm/VSCode：完整的代码提示和自动补全
 - 类型检查：mypy/pylance 支持
 - 重构安全：重命名配置项时自动更新引用
## 6. 迁移计划
### 6.1 向后兼容

  ```
# 保持旧接口兼容
from anp_open_sdk.config.dynamic_config import dynamic_config  # 仍然可用
from anp_open_sdk.config.path_resolver import path_resolver    # 仍然可用

# 新接口
from anp_open_sdk.config import config  # 推荐使用
  ```
### 6.2 迁移步骤
 - 阶段1：实现 unified_config.py，保持旧接口兼容
 - 阶段2：迁移现有配置到 unified_config.yaml
 - 阶段3：更新代码使用新接口
 - 阶段4：移除旧配置文件和接口

### 6.3 自动迁移工具

  ```
# 配置迁移脚本
python -m anp_open_sdk.config.migrate_config
  ```
# 7.部署和环境配置
## 7.1 开发环境
  ```
# .env 文件
ANP_DEBUG=true
ANP_PORT=9527
OPENAI_API_KEY=sk-xxx
DATABASE_URL=sqlite:///dev.db
  ```
## 7.2 生产环境

  ```
# 环境变量
export ANP_DEBUG=false
export ANP_PORT=80
export OPENAI_API_KEY=sk-prod-xxx
export DATABASE_URL=postgresql://prod-server/db
  ```
## 7.3 Docker 支持

  ```
# Dockerfile
ENV ANP_DEBUG=false
ENV ANP_PORT=8080
COPY unified_config.yaml /app/anp_open_sdk/config/
  ```


# 8 附录
## 8.1 注释展示
```yaml
# 这是行注释
port: 9527          # 行尾注释

# debug_mode: true  # 注释掉的配置（暂时不用）

# TODO: 添加更多LLM提供商支持
# openai_api_url: "https://api.openai.com/v1"

# DEPRECATED: 这个配置已废弃
# old_config: "legacy_value"
```
### 8.2 使用方法
```python
from anp_open_sdk.config import config

# 配置文件访问（有代码提示）
port = config.anp_sdk.port                    # 9527
user_path = config.anp_sdk.user_did_path      # 自动解析路径

# 环境变量访问
api_key = config.env.openai_api_key           # 读取 OPENAI_API_KEY
debug = config.env.debug_mode                 # 读取 ANP_DEBUG，转换为 boolean

# 敏感信息访问
secret_key = config.secrets.openai_api_key    # 不缓存，每次重新读取

# 路径操作
abs_path = config.resolve_path("{APP_ROOT}/logs/app.log")
python_exe = config.find_in_path("python3")
```
### 8.3 VS Code配置
在你的项目根目录创建 .vscode/settings.json：

```
{
    "python.analysis.typeCheckingMode": "basic",
    "python.analysis.autoImportCompletions": true,
    "python.analysis.completeFunctionParens": true,
    "python.analysis.autoSearchPaths": true,
    "python.analysis.extraPaths": ["./anp_open_sdk"],
    "python.languageServer": "Pylance"
}
```

### 8.4 添加新配置的方法

#### 8.4.1 在默认配置中添加新的顶级配置项

```
def _get_default_config(self) -> dict:
    """获取默认配置"""
    return {
        "# ANP SDK 统一配置文件": None,
        "# 项目根目录自动检测，支持 {APP_ROOT} 占位符": None,

        "anp_sdk": {
            # ... 现有配置 ...
        },

        "llm": {
            # ... 现有配置 ...
        },

        "mail": {
            # ... 现有配置 ...
        },

        # 🔥 新增顶级配置项
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "anp_db",
            "pool_size": 10,
            "timeout": 30
        },

        "cache": {
            "type": "redis",
            "host": "localhost", 
            "port": 6379,
            "expire_time": 3600
        },

        # ... 其他现有配置 ...
    }
```
#### 8.4.2 在 UnifiedConfig 的 __annotations__ 中声明

```
class UnifiedConfig:
    def __init__(self, config_file: Optional[str] = None):
        """初始化统一配置管理器"""
        self.logger = logging.getLogger(__name__)
        
        # 🔥 在这里添加新的顶级配置项的类型提示
        self.__annotations__ = {
            'anp_sdk': 'ConfigNode',
            'llm': 'ConfigNode', 
            'mail': 'ConfigNode',
            'database': 'ConfigNode',  # 🔥 新增
            'cache': 'ConfigNode',     # 🔥 新增
            'env': 'EnvConfig',
            'secrets': 'SecretsConfig',
        }
        
        # ... 其余初始化代码 ...
```
#### 8.4.3 在 __dir__ 方法中添加（可选，用于更好的IDE支持）

```
def __dir__(self) -> List[str]:
    """支持 IDE 的自动完成"""
    config_attrs = [
        'anp_sdk', 'llm', 'mail', 
        'database', 'cache',  # 🔥 新增
        'env', 'secrets'
    ]
    method_attrs = [
        'resolve_path', 'get_app_root', 'find_in_path', 'get_path_info', 'add_to_path',
        'load', 'save', 'reload', 'to_dict'
    ]
    return config_attrs + method_attrs
```
#### 8.4.4. 如果需要环境变量映射，在相应配置中添加

```
def _get_default_config(self) -> dict:
    return {
        # ... 其他配置 ...
        
        "env_mapping": {
            # ... 现有映射 ...
            
            # 🔥 如果新配置项需要环境变量支持
            "database_host": "DATABASE_HOST",
            "database_port": "DATABASE_PORT", 
            "database_name": "DATABASE_NAME",
            "cache_host": "CACHE_HOST",
            "cache_port": "CACHE_PORT",
        },

        "env_types": {
            # ... 现有类型 ...
            
            # 🔥 新增环境变量的类型
            "database_port": "integer",
            "cache_port": "integer",
        },

        # 🔥 如果有敏感信息，添加到 secrets 列表
        "secrets": [
            "openai_api_key",
            "anthropic_api_key", 
            "mail_password",
            "hoster_mail_password",
            "sender_mail_password",
            "database_url",
            "database_password",  # 🔥 新增
            "cache_password",     # 🔥 新增
        ],
    }
```
#### 8.4.5. 完整示例：添加一个新的 monitoring 配置项

```
class UnifiedConfig:
    def __init__(self, config_file: Optional[str] = None):
        # 🔥 步骤1：添加类型提示
        self.__annotations__ = {
            'anp_sdk': 'ConfigNode',
            'llm': 'ConfigNode', 
            'mail': 'ConfigNode',
            'monitoring': 'ConfigNode',  # 🔥 新增
            'env': 'EnvConfig',
            'secrets': 'SecretsConfig',
        }
        
        # ... 其余代码 ...

    def _get_default_config(self) -> dict:
        return {
            # ... 现有配置 ...
            
            # 🔥 步骤2：添加默认配置
            "monitoring": {
                "enabled": True,
                "metrics_port": 8080,
                "log_level": "INFO",
                "export_interval": 60,
                "endpoints": {
                    "health": "/health",
                    "metrics": "/metrics",
                    "status": "/status"
                }
            },

            "env_mapping": {
                # ... 现有映射 ...
                # 🔥 步骤3：添加环境变量映射（如果需要）
                "monitoring_enabled": "MONITORING_ENABLED",
                "monitoring_port": "MONITORING_PORT",
                "monitoring_log_level": "MONITORING_LOG_LEVEL",
            },

            "env_types": {
                # ... 现有类型 ...
                # 🔥 步骤4：添加环境变量类型
                "monitoring_enabled": "boolean",
                "monitoring_port": "integer",
            },

            # ... 其他配置 ...
        }

    def __dir__(self) -> List[str]:
        # 🔥 步骤5：添加到自动完成列表
        config_attrs = [
            'anp_sdk', 'llm', 'mail', 'monitoring',  # 🔥 新增
            'env', 'secrets'
        ]
        # ... 其余代码 ...
```
#### 8.4.6. 使用新的配置项
添加完成后，你就可以这样使用：


```
from anp_open_sdk.config import config

# 🔥 新的顶级配置项现在可以使用了
print(config.monitoring.enabled)           # True
print(config.monitoring.metrics_port)      # 8080
print(config.monitoring.log_level)         # "INFO"
print(config.monitoring.endpoints.health)  # "/health"

# 🔥 IDE 会提供完整的自动完成和类型提示
config.monitoring.  # 自动完成：enabled, metrics_port, log_level, export_interval, endpoints
```
#### 8.4.7. 配置文件也会自动更新
当你第一次运行时，新的配置会自动写入到 unified_config.yaml 文件中：

```
anp_sdk:
  # ... 现有配置 ...

llm:
  # ... 现有配置 ...

mail:
  # ... 现有配置 ...

# 🔥 新增的配置项会自动出现
monitoring:
  enabled: true
  metrics_port: 8080
  log_level: INFO
  export_interval: 60
  endpoints:
    health: /health
    metrics: /metrics
    status: /status
```
#### 8.4.8 总结
要添加新的顶级配置项，你需要：

 - ✅_get_default_config() - 添加默认配置数据
 - ✅ __annotations__ - 添加类型提示（必需，用于IDE支持）
 - ✅ __dir__() - 添加到自动完成列表（可选，但推荐）
 - ✅ 环境变量映射 - 如果需要环境变量支持
 - ✅ 敏感信息列表 - 如果包含敏感信息