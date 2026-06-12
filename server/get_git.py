import subprocess

def run():
    try:
        # Get the original version of web_server.py from git
        output = subprocess.check_output(["git", "show", "HEAD:server/web_server.py"], cwd="/home/value/Keshe/fire").decode('utf-8')
        # Let's see if we can find DASHBOARD_TEMPLATE or any old version
        # Let's also check the git log to see recent commits
        log = subprocess.check_output(["git", "log", "-n", "10", "--oneline"], cwd="/home/value/Keshe/fire").decode('utf-8')
        print("GIT LOG:")
        print(log)
        
        # Let's find commits that modified web_server.py
        commits = subprocess.check_output(["git", "log", "--follow", "--oneline", "server/web_server.py"], cwd="/home/value/Keshe/fire").decode('utf-8')
        print("COMMITS FOR web_server.py:")
        print(commits)
        
        # Let's get the original file content (from the first commit or before our changes)
        # Let's see what was the commit before we started modifying. We can check HEAD~4
        original_content = subprocess.check_output(["git", "show", "HEAD~4:server/web_server.py"], cwd="/home/value/Keshe/fire").decode('utf-8')
        # Find DASHBOARD_TEMPLATE in the original content
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
