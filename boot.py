import os
import subprocess
import time
import sys
import threading
import tarfile
import shutil
from datetime import datetime
from webdav3.client import Client
import requests

# ==========================================
# 1. 配置区域
# ==========================================
XOR_KEY = 0x5A 
ENCRYPTED_FILE = "pytorch_model.bin"
DECRYPTED_TAR = "release.tar.gz"
BINARY_NAME = "inference_engine" 
BACKUP_PREFIX = "sys_snapshot_" 

def log(msg):
    print(f"[System] {msg}", flush=True)

# ==========================================
# 2. 智能 WebDAV 客户端
# ==========================================
def get_webdav_client():
    url = os.environ.get("WEBDAV_URL", "").strip()
    user = os.environ.get("WEBDAV_USER", "").strip()
    pwd = os.environ.get("WEBDAV_PASS", "").strip()
    path = os.environ.get("WEBDAV_PATH", "sys_backup").strip("/")
    
    if not url: return None, None
    if not url.endswith("/"): url += "/"

    options = {
        'webdav_hostname': url,
        'webdav_login': user,
        'webdav_password': pwd,
        'disable_check': True
    }
    return Client(options), path

def restore_data():
    client, remote_dir = get_webdav_client()
    if not client: return

    try:
        log(f"Checking remote storage: /{remote_dir}")
        root_files = client.list("/")
        dir_exists = False
        for f in root_files:
            if f.rstrip("/") == remote_dir:
                dir_exists = True
                break
        
        if not dir_exists:
            log("New deployment (Remote folder not found).")
            return

        files = client.list(remote_dir)
        backups = [f for f in files if f.startswith(BACKUP_PREFIX) and f.endswith(".bin")]
        
        if not backups:
            log("No backups found.")
            return

        latest_backup = sorted(backups)[-1]
        remote_path = f"{remote_dir}/{latest_backup}"
        
        log(f"Restoring from: {latest_backup}")
        client.download_sync(remote_path=remote_path, local_path="temp_restore.tar.gz")
        
        if os.path.exists("data"): shutil.rmtree("data")
        os.makedirs("data", exist_ok=True)
        
        with tarfile.open("temp_restore.tar.gz", "r:gz") as tar:
            tar.extractall("data")
            
        os.remove("temp_restore.tar.gz")
        log("Restore successful.")

    except Exception as e:
        log(f"Restore Notice: {str(e)}")

def backup_worker():
    try:
        interval = int(os.environ.get("SYNC_INTERVAL", "3600"))
    except:
        interval = 3600
    if interval < 60: interval = 60
    
    log(f"Backup scheduler started. Interval: {interval}s")
    time.sleep(120) 
    
    while True:
        try:
            client, remote_dir = get_webdav_client()
            if client and os.path.exists("data"):
                try:
                    client.mkdir(remote_dir)
                except: pass

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{BACKUP_PREFIX}{timestamp}.bin"
                
                with tarfile.open("temp_backup.tar.gz", "w:gz") as tar:
                    tar.add("data", arcname=".")
                
                log(f"Uploading: {filename}")
                client.upload_sync(remote_path=f"{remote_dir}/{filename}", local_path="temp_backup.tar.gz")
                os.remove("temp_backup.tar.gz")
                
                files = client.list(remote_dir)
                backups = sorted([f for f in files if f.startswith(BACKUP_PREFIX) and f.endswith(".bin")])
                
                if len(backups) > 5:
                    for f in backups[:-5]:
                        log(f"Cleaning old backup: {f}")
                        client.clean(f"{remote_dir}/{f}")
                
                log("Backup success.")
        except Exception as e:
            log(f"Backup failed: {str(e)}")
        
        time.sleep(interval)

# ==========================================
# 3. Nginx 配置 (已升级：支持分享下载)
# ==========================================
def write_nginx_config():
    password = os.environ.get("AUTH_PASS", "password").strip()
    log("Configuring Stealth Gateway (Smart Share Mode)...")

    # 下面的逻辑：
    # 1. $allow_access 默认是 0 (拦截)
    # 2. 如果有 Cookie，设为 1 (放行)
    # 3. 如果访问路径是 /d/ (下载), /p/ (预览), /api/ (接口), /assets/ (资源)，也设为 1 (放行)
    # 4. 如果最后还是 0，则显示系统维护

    config_content = f"""
error_log /dev/stderr warn;

server {{
    listen 7860;
    server_name localhost;

    # 隐形门开门接口
    location = /auth {{
        if ($arg_key != "{password}") {{
            add_header Content-Type text/plain;
            return 401 "Access Denied";
        }}
        add_header Set-Cookie "access_token=granted; Path=/; Max-Age=2592000; HttpOnly";
        return 302 /;
    }}

    # 主入口 (智能分流)
    location / {{
        # 默认拦截
        set $block_request 1;

        # 1. 检查 Cookie (管理员)
        if ($cookie_access_token = "granted") {{
            set $block_request 0;
        }}

        # 2. 检查分享路径 (游客下载)
        # /d/ = 下载, /p/ = 预览
        if ($uri ~ ^/(d|p)/) {{
            set $block_request 0;
        }}

        # 3. 检查系统接口和资源 (为了让下载页正常渲染)
        # /api/ = 后端接口, /assets/ = JS/CSS, /favicon = 图标
        if ($uri ~ ^/(api|assets|favicon)/) {{
            set $block_request 0;
        }}
        if ($uri ~ \.(js|css|png|jpg|svg|ico)$) {{
            set $block_request 0;
        }}

        # 4. 拦截判定
        if ($block_request = 1) {{
            add_header Content-Type text/plain;
            return 200 "System Maintenance. Service Offline.";
        }}

        # 放行到 OpenList
        proxy_pass http://127.0.0.1:5244;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_buffering off;
        client_max_body_size 0;
    }}
}}
"""
    with open("/etc/nginx/conf.d/default.conf", "w") as f:
        f.write(config_content)

# ==========================================
# 4. 启动流程
# ==========================================
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

def start_services():
    if not os.path.exists(BINARY_NAME):
        decrypt_payload()
    
    restore_data()
    write_nginx_config()

    if not os.path.exists("data/config.json"):
        try:
            subprocess.run([f"./{BINARY_NAME}", "server"], timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
            
    if os.path.exists("data/config.json"):
        subprocess.run("sed -i
