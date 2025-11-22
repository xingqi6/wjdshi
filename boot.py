import os
import subprocess
import time
import sys

# 配置
XOR_KEY = 0x5A 
ENCRYPTED_FILE = "pytorch_model.bin"
DECRYPTED_TAR = "release.tar.gz"
BINARY_NAME = "inference_engine" 

def log(msg):
    print(f"[System] {msg}", flush=True)

def decrypt_payload():
    if not os.path.exists(ENCRYPTED_FILE):
        if os.path.exists(BINARY_NAME): return
        log("Error: Model file missing.")
        sys.exit(1)
    
    log("Decrypting payload...")
    with open(ENCRYPTED_FILE, "rb") as f_in, open(DECRYPTED_TAR, "wb") as f_out:
        byte = f_in.read(1)
        while byte:
            f_out.write(bytes([ord(byte) ^ XOR_KEY]))
            byte = f_in.read(1)
            
    subprocess.run(["tar", "-xzf", DECRYPTED_TAR], check=True)
    
    if os.path.exists("openlist"):
        os.rename("openlist", BINARY_NAME)
    elif os.path.exists("alist"):
        os.rename("alist", BINARY_NAME)
        
    subprocess.run(["chmod", "+x", BINARY_NAME], check=True)

def configure_nginx():
    # 获取密码
    password = os.environ.get("AUTH_PASS", "password").strip()
    log(f"Configuring Gateway with password: {password}")
    
    # 【核心】使用 sed 替换 nginx.conf 里的占位符
    # 这样既保留了文件结构，又注入了动态密码
    cmd = f"sed -i 's/###PASSWORD###/{password}/g' /etc/nginx/conf.d/default.conf"
    subprocess.run(cmd, shell=True, check=True)

def start_services():
    if not os.path.exists(BINARY_NAME):
        decrypt_payload()
    
    # 配置 Nginx
    configure_nginx()

    # 初始化 OpenList 配置
    if not os.path.exists("data/config.json"):
        try:
            subprocess.run([f"./{BINARY_NAME}", "server"], timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
            
    # 修改 OpenList 端口
    if os.path.exists("data/config.json"):
        subprocess.run("sed -i 's/\"http_port\": [0-9]*/\"http_port\": 5244/' data/config.json", shell=True)
        subprocess.run("sed -i 's/\"address\": \".*\"/\"address\": \"0.0.0.0\"/' data/config.json", shell=True)

    # 设置 OpenList 内部密码
    password = os.environ.get("AUTH_PASS", "password").strip()
    subprocess.run([f"./{BINARY_NAME}", "admin", "set", password], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 后台启动 OpenList
    with open("engine.log", "w") as logfile:
        subprocess.Popen([f"./{BINARY_NAME}", "server"], stdout=logfile, stderr=logfile)
    
    time.sleep(3)
    
    # 启动 Nginx
    log("Starting Nginx Gateway...")
    subprocess.run(["nginx", "-g", "daemon off;"])

if __name__ == "__main__":
    start_services()
