如果你是小白，可以通过如下方式从零开始运行

# poetry 安装
> poetry 是 Python 依赖管理和打包工具，可以帮助你管理 Python 项目的依赖关系，并生成虚拟环境。
> 
> 官方文档：https://python-poetry.org/docs/


安装前 可以查看项目中的 `pyproject.toml` 文件

```sh
[tool.poetry.dependencies]
python = ">=3.10,<4.0"
```

这里需要python>=3.10, 建议安装poetry前先查看python的版本是否符合这里的需求

命令行执行以下命令 查看版本

```sh
python --version
```

如果你有多个python版本，安装poetry后，可以通过命令指定使用python版本进行构建虚拟环境（创建.venv文件夹）

```sh
poetry env use "C:\YouPath\To\Python310\python.exe"
```

#### Windows

* **安装**
  将以下指令复制并运行在powershell

  ```powershell
  (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
  ```
  > 注：如果系统识别不了该指令，可以把指令中的py替换成python
  ```powershell
    (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
  ```

* **配置环境变量**
  将以下指令复制并运行在powershell

  ```powershell
  # 将 Poetry 的 bin 目录添加到用户环境变量 PATH 中
  [Environment]::SetEnvironmentVariable("PATH", "$env:PATH;$env:APPDATA\Python\Scripts", "User")
  # 刷新当前会话的 PATH 环境变量
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
  ```
  重启 PowerShell 或命令提示符以确保环境变量生效。

* **验证安装**
  将以下指令复制并运行在powershell

  ```powershell
  poetry --version
  ```

  如果输出了 Poetry 的版本号，则表示安装成功。

#### Linux

* **安装**
  bash复制

  ```bash
  curl -sSL https://install.python-poetry.org | python3 -
  ```

  在运行此命令之前，请确保已安装 `curl` 和 `python3`。
* **配置环境变量（如果需要）** 
  bash复制

  ```bash
  # 将 Poetry 的 bin 目录添加到 PATH 中
  export PATH="$HOME/.local/bin:$PATH"
  # 将上述命令添加到 shell 配置文件中，以永久生效
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  ```
* **验证安装**
  bash复制

  ```bash
  poetry --version
  ```

  如果输出了 Poetry 的版本号，则表示安装成功。


# Windows 开发
#### **配置 Poetry 使用项目目录**

```powershell
# 设置虚拟环境创建在项目目录中
poetry config virtualenvs.in-project true
```

#### **指定 Python 版本并安装依赖**

```powershell
# 指定 Python 3.9  
poetry env use 3.9

# 或者使用绝对路径 
poetry env use "C:\YouPath\To\Python310\python.exe"
```

```sh
# 安装依赖（此时会自动创建 .venv）
poetry install
```

#### **验证环境位置**

```powershell
poetry env info
```

如果输出中的 `Path` 显示为项目目录下的 `.venv`（如 `D:\github\did-wba-example\.venv`），则配置成功。

#### 激活环境
```sh
poetry shell
```

#### 删除旧环境
```sh
poetry env remove --all
```


通过这种方式，你可以确保全局工具的独立性和项目依赖的隔离性，避免不同项目之间的依赖冲突。

## 运行项目 
1. 克隆项目
2. 创建环境配置文件
   ```
   cp .env.example .env
   ```
3. 编辑.env文件，设置必要的配置项
4. 启动服务器
   ```bash
   python did_server.py
   ```
5. 启动客户端
   ```bash
     # 在第二个终端窗口启动客户端，指定不同端口
   python did_server.py --client --port 8001
   ```


# Mac 开发

本项目要求 python 版本在 3.10 以上。

在设置Python开发环境时，通常会有一些工具需要全局安装，而其他工具则适合在项目的虚拟环境中安装。以下是一个理想的安装顺序和建议：

## 全局安装
1. pip : 通常已经随Python安装一起提供，用于安装和管理Python包。
2. pipx : 用于全局安装和管理独立的Python应用程序。适合安装像 poetry 这样的工具。
   
   ```bash
   pip install pipx
   pipx ensurepath
    ```
3. poetry : 用于依赖管理和打包的工具，建议通过 pipx 全局安装，以便在多个项目中使用。
   
   ```bash
   pipx install poetry
   pipx ensurepath
    ```
## 虚拟环境安装
1. .venv : 在项目目录下创建虚拟环境，用于隔离项目的依赖。（也可以跳过此步，poetry install 会自动创建）
   
   ```bash
   python3 -m venv .venv
    ```
2. 项目依赖 : 在激活虚拟环境后，检查python是否在虚拟环境中，通过 poetry 安装项目的依赖。
   
   ```bash
   source .venv/bin/activate
   where python
   poetry install
    ```
3. 等实验结束后可退出虚拟环境:

   ```bash
   deactivate
    ```
通过这种方式，你可以确保全局工具的独立性和项目依赖的隔离性，避免不同项目之间的依赖冲突。

## 运行项目 
1. 克隆项目
2. 创建环境配置文件
   ```
   cp .env.example .env
   ```
3. 编辑 .env 文件，设置必要的配置项，如 OPENROUTER_API_KEY，可到 [open router 官网](https://openrouter.ai/) 生成 API key，本 demo 使用免费模型，无需充值。
4. 启动服务器。初次启动可能要创建 logs 目录，使用了 sudo 命令，需要输入管理员密码。
   ```bash
   python did_server.py
   # 启动成功后执行
   start server
   ```
5. 启动客户端
   ```bash
     # 在第二个终端窗口启动客户端，指定不同端口
   python did_server.py --client --port 8001
   ```

启动客户端后会自动连接 server 并发送问候信息，如果发送成功会看到提示。然后就可以根据 help 命令中的提示进一步探索与其他 agent 交互的场景。


# 安装依赖意外情况
一般可以通过删除虚拟环境，重新安装解决
#### 删除旧环境

```sh
poetry env remove --all
```

#### 重新安装

```sh
poetry config virtualenvs.in-project true
poetry env use "C:\YouPath\To\Python310\python.exe"
poetry install
poetry shell
```


## 常见问题

### Run `poetry lock [--no-update]` to fix the lock file.

由于 pyproject.toml 文件发生了变化， 与 poetry.lock 不匹配
重新生成poetry.lock
```sh
poetry lock --no-update
```
重新安装
```sh
poetry install
```

### ImportError: DLL load failed while importing _rust: 找不到指定的程序
优先尝试卸载当前虚拟环境，然后重新创建
```sh
poetry env remove --all 
poetry install
```
如果还是不行，尝试安装 Visual C++ Redistributable
- `cryptography` 的 Rust 扩展需要 VC++ 运行时支持。
- **解决方案**：
  - 安装最新版 [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)（根据系统架构选择 x86/x64）。


