#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置使用示例

展示如何使用 dynamic_config 替代 .env 文件和 os.environ.get
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from anp_open_sdk.config.dynamic_config import dynamic_config, get_config_value

def example_old_way():
    """旧的方式：使用 os.environ.get"""
    import os
    
    print("=== 旧的方式 (os.environ.get) ===")
    
    # 旧的代码
    use_local = os.environ.get('USE_LOCAL_MAIL', 'false').lower() == 'true'
    mail_user = os.environ.get('HOSTER_MAIL_USER')
    debug_mode = os.environ.get('ANP_DEBUG', 'false').lower() == 'true'
    
    print(f"USE_LOCAL_MAIL: {use_local}")
    print(f"HOSTER_MAIL_USER: {mail_user}")
    print(f"ANP_DEBUG: {debug_mode}")

def example_new_way():
    """新的方式：使用 dynamic_config"""
    print("\n=== 新的方式 (dynamic_config) ===")
    
    # 方式1: 直接使用 dynamic_config.get
    use_local = dynamic_config.get('mail.use_local_backend', False)
    mail_user = dynamic_config.get('mail.hoster_mail_user')
    debug_mode = dynamic_config.get('anp_sdk.debug_mode', False)
    
    print(f"mail.use_local_backend: {use_local}")
    print(f"mail.hoster_mail_user: {mail_user}")
    print(f"anp_sdk.debug_mode: {debug_mode}")
    
    # 方式2: 使用兼容函数 (推荐用于迁移期间)
    print("\n--- 使用兼容函数 ---")
    use_local_compat = get_config_value('USE_LOCAL_MAIL', False)
    mail_user_compat = get_config_value('HOSTER_MAIL_USER')
    debug_mode_compat = get_config_value('ANP_DEBUG', False)
    
    print(f"USE_LOCAL_MAIL (兼容): {use_local_compat}")
    print(f"HOSTER_MAIL_USER (兼容): {mail_user_compat}")
    print(f"ANP_DEBUG (兼容): {debug_mode_compat}")

def example_config_management():
    """配置管理示例"""
    print("\n=== 配置管理示例 ===")
    
    # 设置配置
    dynamic_config.set('mail.use_local_backend', True, save=False)
    dynamic_config.set('acceleration.enable_local', True, save=False)
    
    # 批量更新配置
    new_config = {
        'mail': {
            'register_mail_user': 'test@example.com',
            'smtp_port': 587
        },
        'acceleration': {
            'cache_size': 2000
        }
    }
    dynamic_config.update(new_config, save=False)
    
    # 读取配置
    print(f"邮件本地后端: {dynamic_config.get('mail.use_local_backend')}")
    print(f"本地加速: {dynamic_config.get('acceleration.enable_local')}")
    print(f"注册邮箱: {dynamic_config.get('mail.register_mail_user')}")
    print(f"缓存大小: {dynamic_config.get('acceleration.cache_size')}")
    
    print("\n注意: 以上修改未保存到文件 (save=False)")

def example_migration_guide():
    """迁移指南"""
    print("\n=== 代码迁移指南 ===")
    
    migration_examples = [
        {
            'old': "os.environ.get('USE_LOCAL_MAIL', 'false').lower() == 'true'",
            'new': "dynamic_config.get('mail.use_local_backend', False)",
            'compat': "get_config_value('USE_LOCAL_MAIL', False)"
        },
        {
            'old': "os.environ.get('HOSTER_MAIL_USER')",
            'new': "dynamic_config.get('mail.hoster_mail_user')",
            'compat': "get_config_value('HOSTER_MAIL_USER')"
        },
        {
            'old': "os.environ.get('ENABLE_LOCAL_ACCELERATION', 'false').lower() == 'true'",
            'new': "dynamic_config.get('acceleration.enable_local', False)",
            'compat': "get_config_value('ENABLE_LOCAL_ACCELERATION', False)"
        }
    ]
    
    for i, example in enumerate(migration_examples, 1):
        print(f"\n示例 {i}:")
        print(f"  旧代码: {example['old']}")
        print(f"  新代码: {example['new']}")
        print(f"  兼容代码: {example['compat']}")

def main():
    """主函数"""
    print("ANP SDK 配置使用示例")
    print("=" * 40)
    
    # 显示当前配置文件路径
    print(f"配置文件路径: {dynamic_config.config_file}")
    
    # 运行示例
    example_old_way()
    example_new_way()
    example_config_management()
    example_migration_guide()
    
    print("\n=== 总结 ===")
    print("1. 使用 dynamic_config.get() 直接获取配置")
    print("2. 使用 get_config_value() 进行兼容性迁移")
    print("3. 使用 dynamic_config.set() 动态设置配置")
    print("4. 配置会自动保存到 dynamic_config.yaml")
    print("5. 支持嵌套配置和类型转换")

if __name__ == '__main__':
    main()