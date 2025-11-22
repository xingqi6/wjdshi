import os
import subprocess
import time
import sys

# ============================
# 配置区域
# ============================
XOR_KEY = 0x5A 
ENCRYPTED_FILE = "pytorch_model.bin"
DECRYPTED_TAR = "release.tar.gz"
BINARY_NAME = "inference_engine" 

def log(msg):
    print(f"[System] {msg}", flush=True)

# 解密模块
def decrypt_payload():
    if not os.path.exists(ENCRYPTED_FILE):
        # 如果是重启，可能文件已经被处理过
        if os.path.exists(BINARY_NAME):
             return
        log("Error: Model file missing.")
        sys.exit(1)
    
    log("Decrypting payload...")
    with open(ENCRYPTED_FILE, "rb") as f_in, open(DECRYPTED_TAR, "wb") as f_out:
        byte = f_in.read(1)
        while byte:
            f_out.write(bytes([ord(byte) ^ XOR_KEY]))
            byte = f_in.read(1)
            
    subprocess.run(["tar", "-xzf", DECRYPTED_TAR], check=True)
    
    # 智能重命名：不管解压出来叫 alist 还是 openlist，都重命名
    if os.path.exists("openlist"):
        os.rename("openlist", BINARY_NAME)
    elif os.path.exists("alist"):
        os.rename("alist", BINARY_NAME)
        
    subprocess.run(["chmod", "+x", BINARY_NAME], check=True)

# 【核心】生成“隐形门” Nginx 配置
def generate_nginx_config():
    # 获取你的密码 (环境变量)
    password = os.environ.get("AUTH_PASS", "password").strip()
    
    log(f"Generating Cookie-Gate for password: {password}")

    # Nginx 配置：默认返回 403，只有带 Cookie 才转发
    nginx_conf = f"""
error_log /dev/stderr warn;

server {{
    listen 7860;
    server_name localhost;

    # 1. 隐形门入口
    # 访问 https://xxx.hf.space/auth?key=你的密码
    location = /auth {{
        if ($arg_key != "{password}") {{
            return 401 "Wrong Password";
        }}
        # 密码正确，种植 Cookie，有效期 30 天
        add_header Set-Cookie "access_token=verif
