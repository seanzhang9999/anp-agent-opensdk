"""Setup script for MCP Server.

This script helps to install the necessary dependencies for the MCP server
and sets up the environment.
"""
import os
import sys
import subprocess
import argparse

def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 10):
        print("错误: 需要 Python 3.10 或更高版本")
        sys.exit(1)

def install_dependencies():
    """Install required dependencies."""
    print("安装 MCP 依赖...")
    try:
        # 确保安装完整的MCP包，包括CLI组件
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "mcp[cli]"])
        # 验证安装
        try:
            import mcp.cli.dev
            print("MCP 依赖安装成功")
        except ImportError:
            print("警告: MCP CLI 组件未正确安装，尝试直接安装dev模块...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "mcp-cli"])
            print("MCP CLI 组件安装完成")
    except subprocess.CalledProcessError as e:
        print(f"安装 MCP 依赖时出错: {e}")
        sys.exit(1)
    except ImportError as e:
        print(f"导入 MCP 模块时出错: {e}")
        print("请尝试手动安装: pip install --upgrade mcp[cli] mcp-cli")
        sys.exit(1)

def install_mcp_server():
    """Install MCP server to Claude Desktop."""
    print("安装 MCP 服务器到 Claude Desktop...")
    try:
        subprocess.check_call(["mcp", "install", "mcp_stdio_server.py"])
        print("MCP 服务器安装成功")
    except subprocess.CalledProcessError as e:
        print(f"安装 MCP 服务器时出错: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("错误: 找不到 mcp 命令。请确保 MCP 依赖已正确安装")
        sys.exit(1)

def run_mcp_server():
    """Run MCP server in development mode."""
    print("启动 MCP 服务器...")
    try:
        subprocess.check_call(["mcp", "dev", "mcp_stdio_server.py"])
    except subprocess.CalledProcessError as e:
        print(f"运行 MCP 服务器时出错: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("错误: 找不到 mcp 命令。请确保 MCP 依赖已正确安装")
        sys.exit(1)

def run_client_example():
    """Run the MCP client example."""
    print("运行 MCP 客户端示例...")
    try:
        subprocess.check_call([sys.executable, "mcp_client_example.py"])
    except subprocess.CalledProcessError as e:
        print(f"运行 MCP 客户端示例时出错: {e}")
        sys.exit(1)

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="MCP 服务器设置脚本")
    parser.add_argument("--install", action="store_true", help="安装 MCP 依赖")
    parser.add_argument("--install-claude", action="store_true", help="安装 MCP 服务器到 Claude Desktop")
    parser.add_argument("--run", action="store_true", help="运行 MCP 服务器")
    parser.add_argument("--example", action="store_true", help="运行 MCP 客户端示例")
    
    args = parser.parse_args()
    
    # 检查 Python 版本
    check_python_version()
    
    # 如果没有提供参数，显示帮助信息
    if not (args.install or args.install_claude or args.run or args.example):
        parser.print_help()
        return
    
    # 安装依赖
    if args.install:
        install_dependencies()
    
    # 安装 MCP 服务器到 Claude Desktop
    if args.install_claude:
        install_mcp_server()
    
    # 运行 MCP 服务器
    if args.run:
        run_mcp_server()
    
    # 运行 MCP 客户端示例
    if args.example:
        run_client_example()

if __name__ == "__main__":
    main()