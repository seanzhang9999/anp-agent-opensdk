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
  local_backend_path: "{APP_ROOT}/data_demo_simulate/mail_local_backend"
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
logger.debug(f"PATH 中有 {path_info['path_count']} 个目录")
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

#### 配置导出

```
# 导出当前配置
config_dict = config.to_dict()

# 导出环境变量配置
env_dict = config.env.to_dict()

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


# 6.部署和环境配置
统一加载环境变量，支持.evn /  export / dockerfile不同配置的统一读取

## 6.1 开发环境

```
# .env 文件
ANP_DEBUG=true
ANP_PORT=9527
OPENAI_API_KEY=sk-xxx
DATABASE_URL=sqlite:///dev.db
```

## 6.2 生产环境

```
# 环境变量
export ANP_DEBUG=false
export ANP_PORT=80
export OPENAI_API_KEY=sk-prod-xxx
export DATABASE_URL=postgresql://prod-server/db
```

## 6.3 Docker 支持

```
# Dockerfile
ENV ANP_DEBUG=false
ENV ANP_PORT=8080
COPY unified_config.yaml /app/anp_open_sdk/config/
```

# 7 附录

## 7.1 注释展示

```yaml
# 这是行注释
port: 9527          # 行尾注释

# debug_mode: true  # 注释掉的配置（暂时不用）

# TODO: 添加更多LLM提供商支持
# openai_api_url: "https://api.openai.com/v1"

# DEPRECATED: 这个配置已废弃
# old_config: "legacy_value"
```

### 7.2 使用方法

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

### 7.3 VS Code配置

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

### 7.4 使用方式
```
from anp_open_sdk.config import config

logger.debug(config.anp_sdk.debug_mode)
logger.debug(config.llm.default_model)
logger.debug(config.mail.smtp_server)
logger.debug(config.secrets.openai_api_key)  # 只从环境变量读取
logger.debug(config.to_dict())  # 导出全部配置（敏感信息自动隐藏）



from anp_open_sdk.config import config

# 访问配置
logger.debug(config.anp_sdk.debug_mode)
logger.debug(config.llm.default_model)
logger.debug(config.mail.smtp_server)
logger.debug(config.secrets.openai_api_key)

# 热加载
config.reload()

# 保存配置
config.save()

# 路径相关
logger.debug(config.resolve_path("{APP_ROOT}/some/dir"))
logger.debug(config.get_app_root())
logger.debug(config.find_in_path("python"))
logger.debug(config.get_path_info())

# 导出全部配置
logger.debug(config.to_dict())
```
### 7.5 添加删除
 - 添加删除配置项，只需要在unified_config.yaml中添加删除即可
 - 如果删除的在_get_default_config中存在，可以考虑也删除，否则会有默认值
 - 如果想IDE自动提示可选（避免出错），要在 config_types.py中添加对应的提示类

一处编辑，反复使用，还是比较值的
可以多层级

```python

class LogConfig(Protocol):
    """日志配置协议"""
    log_level: Optional[str]
    detail: LogDetailConfig
class LogConfig(Protocol): #配置类及属性
    """日志配置协议"""
    log_level: Optional[str]

class UnifiedConfigProtocol(Protocol):
    """统一配置协议"""
    # 主要配置节点
    logger: LogConfig # 增加配置项名称 和对应类

```

```python
# IDE 会自动提示 logger、log_level、detail、file、max_size
print(config.logger.log_level)
print(config.logger.detail.file)
print(config.logger.detail.max_size)
```

```yaml
logger:
  log_level: DEBUG
  detail:
    file: "/tmp/app.log"
    max_size: 100
```