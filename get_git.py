#!/usr/bin/env python3
"""
Git 版本历史查询工具
用于查看 web_server.py 在 Git 仓库中的历史版本内容
该工具通过调用 Git 命令行，获取特定文件在不同提交版本中的内容，
便于对比和恢复历史模板代码。
"""

import subprocess  # 导入 subprocess 模块，用于执行外部 Git 命令

def run():
    """
    从 Git 仓库中查询 web_server.py 的历史版本。
    功能包括：
        1. 显示当前 HEAD 版本的 web_server.py 内容
        2. 显示最近的 10 条提交记录
        3. 显示 web_server.py 文件的所有历史提交记录（带 --follow 跟踪重命名）
        4. 显示 HEAD~4（当前版本往前 4 个提交的版本）中的 web_server.py 内容，
           并尝试提取 DASHBOARD_TEMPLATE 模板片段以供参考
    """
    try:
        # ---------- 1. 获取当前 HEAD 版本中 web_server.py 的完整内容 ----------
        # 执行 `git show HEAD:server/web_server.py`，输出文件内容，cwd 指定仓库根目录
        output = subprocess.check_output(
            ["git", "show", "HEAD:server/web_server.py"],
            cwd="/home/value/Keshe/fire"
        ).decode('utf-8')

        # ---------- 2. 查看最近的提交记录（10 条，简洁格式） ----------
        log = subprocess.check_output(
            ["git", "log", "-n", "10", "--oneline"],
            cwd="/home/value/Keshe/fire"
        ).decode('utf-8')
        print("GIT LOG:")
        print(log)  # 打印提交历史

        # ---------- 3. 查看 web_server.py 文件的所有历史提交记录 ----------
        # `--follow` 选项可以跟踪文件的重命名历史
        commits = subprocess.check_output(
            ["git", "log", "--follow", "--oneline", "server/web_server.py"],
            cwd="/home/value/Keshe/fire"
        ).decode('utf-8')
        print("COMMITS FOR web_server.py:")
        print(commits)  # 打印该文件的历史提交摘要

        # ---------- 4. 获取 HEAD~4 版本（当前提交往前数 4 个提交）中的 web_server.py 内容 ----------
        # 用于对比当前版本与更早历史版本的差异，便于恢复被修改或删除的模板代码
        original_content = subprocess.check_output(
            ["git", "show", "HEAD~4:server/web_server.py"],
            cwd="/home/value/Keshe/fire"
        ).decode('utf-8')

        # ---------- 在历史版本中查找 DASHBOARD_TEMPLATE 模板字符串 ----------
        # 如果存在，则打印模板的开头 1500 个字符，以便查看或恢复
        start_idx = original_content.find("DASHBOARD_TEMPLATE")
        if start_idx != -1:
            print("\nORIGINAL DASHBOARD_TEMPLATE FOUND:")
            print(original_content[start_idx:start_idx+1500])  # 只显示前 1500 字符防止过长
        else:
            print("\nDASHBOARD_TEMPLATE not found in HEAD~4")

    except Exception as e:
        # 如果执行 Git 命令出错（如文件不存在、仓库路径错误、HEAD~4 不存在等），打印错误信息
        print("Error:", e)


if __name__ == "__main__":
    # 当脚本作为主程序运行时，调用 run 函数执行查询
    run()