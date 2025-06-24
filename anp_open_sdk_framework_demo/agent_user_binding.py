import logging
import os
import yaml
from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager, did_create_user
import glob

from anp_open_sdk.config import UnifiedConfig, set_global_config
from anp_open_sdk.utils.log_base import setup_logging

app_config = UnifiedConfig(config_file='anp_open_sdk_framework_demo_agent_unified_config.yaml')
set_global_config(app_config)
setup_logging() # 假设 setup_logging 内部也改用 get_global_config()
logger = logging.getLogger(__name__)



AGENT_YAML_PATTERN = "data_user/localhost_9527/agents_config/*/agent_mappings.yaml"

def get_all_agent_yaml_files():
    return glob.glob(AGENT_YAML_PATTERN)

def get_all_used_dids(agent_yaml_files):
    dids = {}
    for yaml_path in agent_yaml_files:
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            did = cfg.get("did")
            if did:
                if did in dids:
                    dids[did].append(yaml_path)
                else:
                    dids[did] = [yaml_path]
    return dids

def get_all_user_dids():
    manager = LocalUserDataManager()
    users = manager.get_all_users()
    return {user.did: user.name for user in users if user.did}

def main():
    agent_yaml_files = get_all_agent_yaml_files()
    used_dids = get_all_used_dids(agent_yaml_files)
    user_dids = get_all_user_dids()

    # 检查重复
    has_duplicates = False
    for did, files in used_dids.items():
        if len(files) > 1:
            has_duplicates = True
            print(f"❌ DID重复: {did} 被以下多个agent使用：")
            for f in files:
                print(f"  - {f}")

    # 检查未绑定或不存在的did
    has_unbinded = False
    for yaml_path in agent_yaml_files:
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        did = cfg.get("did")
        if not did or did not in user_dids:
            has_unbinded = True
            print(f"\n⚠️  {yaml_path} 未绑定有效DID。")
            print("可用用户DID如下：")
            unused_dids = {k: v for k, v in user_dids.items() if k not in used_dids}
            for idx, (udid, uname) in enumerate(unused_dids.items(), 1):
                print(f"  [{idx}] {uname} ({udid})")
            print(f"  [N] 新建用户DID")
            choice = input("请选择要绑定的DID编号，或输入N新建：").strip()
            if choice.upper() == "N":
                # 新建用户流程
                print("请输入新用户信息：")
                name = input("用户名: ")
                host = input("主机名: ")
                port = input("端口号: ")
                host_dir = input("主机路径: ")
                agent_type = input("用户类型: ")
                params = {
                    'name': name,
                    'host': host,
                    'port': int(port),
                    'dir': host_dir,
                    'type': agent_type,
                }
                did_doc = did_create_user(params)
                if did_doc and "id" in did_doc:
                    new_did = did_doc["id"]
                    print(f"新用户DID创建成功: {new_did}")
                    cfg["did"] = new_did
                else:
                    print("新建DID失败，跳过。")
                    continue
            else:
                try:
                    idx = int(choice) - 1
                    new_did = list(unused_dids.keys())[idx]
                    cfg["did"] = new_did
                    print(f"已绑定DID: {new_did}")
                    del unused_dids[new_did]
                except Exception as e:
                    print("无效选择，跳过。")
                    continue
            # 写回yaml
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
            print(f"已更新 {yaml_path} 的DID。")

    # 如果没有重复和未绑定不存在，列出yaml文件里的name、did和对应的users_data里的yaml里的name
    if not has_duplicates and not has_unbinded:
        print("\n当前Agent与用户绑定关系:")
        print("=" * 80)
        print(f"{'Agent名称':<20} {'Agent DID':<45} {'绑定用户':<20}\n")
        print("-" * 80)
        i = 1
        for yaml_path in agent_yaml_files:
            with open(yaml_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)

            agent_name = cfg.get("name", "未命名")
            agent_did = cfg.get("did", "无DID")

            # 查找对应的用户名
            user_name = user_dids.get(agent_did, "未绑定")

            print(f"{i}:{agent_name:<20} {agent_did:<45} {user_name:<20}\n")
            i += 1

        print("=" * 80)

if __name__ == "__main__":
    main()