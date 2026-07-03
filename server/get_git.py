"""
Git 版本历史查询工具
用于查看 web_server.py 在 Git 仓库中的历史版本内容
"""
import subprocess

def run():
    """从 Git 仓库中查询 web_server.py 的历史版本"""

    try:
        # 从 Git 仓库获取 web_server.py 在 HEAD 版本的内容
        output = subprocess.check_output(["git", "show", "HEAD:server/web_server.py"], cwd="/home/value/Keshe/fire").decode('utf-8')
        # 查看最近的 Git 提交记录
        log = subprocess.check_output(["git", "log", "-n", "10", "--oneline"], cwd="/home/value/Keshe/fire").decode('utf-8')
        print("GIT LOG:")
        print(log)
        
        # 查看 web_server.py 文件的所有历史提交记录
        commits = subprocess.check_output(["git", "log", "--follow", "--oneline", "server/web_server.py"], cwd="/home/value/Keshe/fire").decode('utf-8')
        print("COMMITS FOR web_server.py:")
        print(commits)
        
        # 查看 HEAD~4（当前版本往前 4 个提交的版本）中的 web_server.py 内容
        # 用于对比当前版本与历史版本的差异
        original_content = subprocess.check_output(["git", "show", "HEAD~4:server/web_server.py"], cwd="/home/value/Keshe/fire").decode('utf-8')
        # 在历史版本中查找 DASHBOARD_TEMPLATE 模板，以便恢复或对比
        start_idx = original_content.find("DASHBOARD_TEMPLATE")
        if start_idx != -1:
            print("\nORIGINAL DASHBOARD_TEMPLATE FOUND:")
            print(original_content[start_idx:start_idx+1500])
        else:
            print("\nDASHBOARD_TEMPLATE not found in HEAD~4")
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    run()
