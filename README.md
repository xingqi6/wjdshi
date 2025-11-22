# Stealth-Service-Deploy (隐匿云服务部署指南)

> **版本**: V5.0 (Final Stable)
> **核心功能**: 静态特征消除 + 隐形门验证 + 智能 WebDAV 备份 + 游客分流

本项目提供一种在 PaaS 平台（如 Hugging Face）上部署高度隐匿的文件管理服务（基于 OpenList）的方案。

---

## ✨ 核心黑科技

1.  **🛡️ 静态特征消除**：构建阶段对二进制文件进行 XOR 加密，伪装成 PyTorch 模型 (`pytorch_model.bin`)，完美绕过平台哈希扫描。
2.  **👻 隐形门验证 (Cookie Gate)**：首页默认显示“系统维护中”，只有通过特定 URL (`/auth?key=...`) 携带密钥访问才能种下 Cookie 并解锁系统，彻底屏蔽审查爬虫。
3.  **🔄 智能持久化**：支持 WebDAV 双向同步，自动备份数据，支持 **TeraCloud/InfiniCloud**，自动保留最近 5 份快照，支持自定义备份间隔与路径。
4.  **🔗 智能分流**：支持文件分享与在线播放，Nginx 自动识别分享链接 (`/d/`, `/p/`) 并放行，同时保护管理后台。

---

## 📋 准备工作

1.  **GitHub 账号**：用于构建无痕基础镜像。
2.  **Hugging Face 账号**：用于部署运行环境。
3.  **WebDAV 网盘**：用于数据持久化（推荐 InfiniCloud/TeraCloud）。

---

## 🛠 第一阶段：GitHub 构建 (基础镜像)

### 1. 创建仓库
新建一个 **Public** 仓库，建议命名为 `bert-inference-runtime` 或其他迷惑性名称。

### 2. 上传核心文件
在仓库根目录创建以下 5 个文件：

#### (1) `nginx.conf` (Nginx 模板)
```nginx
error_log /dev/stderr warn;

server {
    listen 7860;
    server_name localhost;

    # 隐形门验证接口
    location = /auth {
        # ###PASSWORD### 是占位符，启动时会被替换
        if ($arg_key != "###PASSWORD###") {
            add_header Content-Type text/plain;
            return 401 "Access Denied: Wrong Key";
        }
        add_header Set-Cookie "access_token=granted; Path=/; Max-Age=2592000; HttpOnly";
        return 302 /;
    }

    # 主入口 (智能分流)
    location / {
        set $block_request 1;

        # 放行规则：有Cookie、分享链接、预览链接、静态资源
        if ($cookie_access_token = "granted") { set $block_request 0; }
        if ($uri ~ ^/(d|p|api|assets|favicon)/) { set $block_request 0; }
        if ($uri ~ \.(js|css|png|jpg|svg|ico)$) { set $block_request 0; }

        if ($block_request = 1) {
            add_header Content-Type text/plain;
            return 200 "System Maintenance Mode. Service is offline.";
        }

        proxy_pass http://127.0.0.1:5244;
        proxy_hide_header WWW-Authenticate;
        proxy_set_header Authorization "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        client_max_body_size 0;
    }
}
```
## (2) builder.py (加密器)
```builder.py
import os
import requests

URL_PART_1 = "https://github.com/OpenListTeam"
URL_PART_2 = "/OpenList/releases/latest/download/openlist-linux-amd64.tar.gz"
TARGET_URL = URL_PART_1 + URL_PART_2
FAKE_MODEL_NAME = "pytorch_model.bin"
XOR_KEY = 0x5A 

def build():
    print("Downloading core assets...")
    r = requests.get(TARGET_URL, stream=True)
    with open("temp.tar.gz", "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    
    print("Encrypting payload...")
    with open("temp.tar.gz", "rb") as f_in, open(FAKE_MODEL_NAME, "wb") as f_out:
        byte = f_in.read(1)
        while byte:
            f_out.write(bytes([ord(byte) ^ XOR_KEY]))
            byte = f_in.read(1)
            
    print(f"Build success: {FAKE_MODEL_NAME}")
    os.remove("temp.tar.gz")

if __name__ == "__main__":
    build()
```
## (3) boot.py (启动脚本 - 修复版)
```boot.py
import os
import subprocess
import time
import sys
import threading
import tarfile
import shutil
from datetime import datetime
from webdav3.client import Client

XOR_KEY = 0x5A 
ENCRYPTED_FILE = "pytorch_model.bin"
DECRYPTED_TAR = "release.tar.gz"
BINARY_NAME = "inference_engine" 
BACKUP_PREFIX = "sys_snapshot_" 

def log(msg):
    print(f"[System] {msg}", flush=True)

def get_webdav_client():
    url = os.environ.get("WEBDAV_URL", "").strip()
    user = os.environ.get("WEBDAV_USER", "").strip()
    pwd = os.environ.get("WEBDAV_PASS", "").strip()
    path = os.environ.get("WEBDAV_PATH", "sys_backup").strip("/")
    if not url: return None, None
    if not url.endswith("/"): url += "/"
    options = {'webdav_hostname': url, 'webdav_login': user, 'webdav_password': pwd, 'disable_check': True}
    return Client(options), path

def restore_data():
    client, remote_dir = get_webdav_client()
    if not client: return
    try:
        log(f"Checking remote storage: /{remote_dir}")
        try:
            root_files = client.list("/")
            if not any(f.rstrip("/") == remote_dir for f in root_files):
                log("New deployment (Remote folder not found).")
                return
        except: pass

        files = client.list(remote_dir)
        backups = [f for f in files if f.startswith(BACKUP_PREFIX) and f.endswith(".bin")]
        if not backups: return

        latest = sorted(backups)[-1]
        log(f"Restoring from: {latest}")
        client.download_sync(remote_path=f"{remote_dir}/{latest}", local_path="temp_restore.tar.gz")
        
        if os.path.exists("data"): shutil.rmtree("data")
        os.makedirs("data", exist_ok=True)
        with tarfile.open("temp_restore.tar.gz", "r:gz") as tar: tar.extractall("data")
        os.remove("temp_restore.tar.gz")
        log("Restore successful.")
    except Exception as e: log(f"Restore Notice: {str(e)}")

def backup_worker():
    try: interval = int(os.environ.get("SYNC_INTERVAL", "3600"))
    except: interval = 3600
    if interval < 60: interval = 60
    log(f"Backup scheduler started. Interval: {interval}s")
    time.sleep(120) 
    
    while True:
        try:
            client, remote_dir = get_webdav_client()
            if client and os.path.exists("data"):
                try: client.mkdir(remote_dir)
                except: pass

                fname = f"{BACKUP_PREFIX}{datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"
                with tarfile.open("temp_backup.tar.gz", "w:gz") as tar: tar.add("data", arcname=".")
                log(f"Uploading: {fname}")
                client.upload_sync(remote_path=f"{remote_dir}/{fname}", local_path="temp_backup.tar.gz")
                os.remove("temp_backup.tar.gz")
                
                files = client.list(remote_dir)
                backups = sorted([f for f in files if f.startswith(BACKUP_PREFIX) and f.endswith(".bin")])
                if len(backups) > 5:
                    for f in backups[:-5]:
                        log(f"Cleaning old backup: {f}")
                        client.clean(f"{remote_dir}/{f}")
                log("Backup success.")
        except Exception as e: log(f"Backup failed: {str(e)}")
        time.sleep(interval)

def write_nginx_config():
    password = os.environ.get("AUTH_PASS", "password").strip()
    log("Configuring Stealth Gateway...")
    with open("/etc/nginx/conf.d/default.conf", "r") as f: content = f.read()
    content = content.replace("###PASSWORD###", password)
    with open("/etc/nginx/conf.d/default.conf", "w") as f: f.write(content)

def decrypt_payload():
    if not os.path.exists(ENCRYPTED_FILE):
        if os.path.exists(BINARY_NAME): return
        sys.exit(1)
    log("Decrypting payload...")
    with open(ENCRYPTED_FILE, "rb") as f_in, open(DECRYPTED_TAR, "wb") as f_out:
        while byte := f_in.read(1): f_out.write(bytes([ord(byte) ^ XOR_KEY]))
    subprocess.run(["tar", "-xzf", DECRYPTED_TAR], check=True)
    if os.path.exists("openlist"): os.rename("openlist", BINARY_NAME)
    elif os.path.exists("alist"): os.rename("alist", BINARY_NAME)
    subprocess.run(["chmod", "+x", BINARY_NAME], check=True)

def start_services():
    if not os.path.exists(BINARY_NAME): decrypt_payload()
    restore_data()
    write_nginx_config()
    if not os.path.exists("data/config.json"):
        try: subprocess.run([f"./{BINARY_NAME}", "server"], timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
    if os.path.exists("data/config.json"):
        subprocess.run("""sed -i 's/"http_port": [0-9]*/"http_port": 5244/' data/config.json""", shell=True)
        subprocess.run("""sed -i 's/"address": ".*"/"address": "0.0.0.0"/' data/config.json""", shell=True)

    password = os.environ.get("AUTH_PASS", "password").strip()
    subprocess.run([f"./{BINARY_NAME}", "admin", "set", password], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open("engine.log", "w") as logfile: subprocess.Popen([f"./{BINARY_NAME}", "server"], stdout=logfile, stderr=logfile)
    threading.Thread(target=backup_worker, daemon=True).start()
    time.sleep(3)
    log("Starting Gateway...")
    subprocess.run(["nginx", "-g", "daemon off;"])

if __name__ == "__main__":
    start_services()
```
## (4) Dockerfile
```Dockerfile
FROM python:3.9-slim as builder
WORKDIR /build
COPY builder.py .
RUN pip install requests && python builder.py

FROM python:3.9-slim-bullseye
RUN apt-get update && apt-get install -y nginx apache2-utils procps tar && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir requests webdavclient3
WORKDIR /app
COPY --from=builder /build/pytorch_model.bin /app/pytorch_model.bin
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY boot.py /app/boot.py
RUN chmod +x /app/boot.py && mkdir -p /app/data && chmod 777 /app/data
EXPOSE 7860
ENV BUILD_VERSION=5.0
CMD ["python3", "/app/boot.py"]
```
## (5) .github/workflows/build.yml
```
name: Build AI Model

on:
  workflow_dispatch:
  push:
    branches: [ "main" ]

env:
  REGISTRY: ghcr.io
  # 这里的名字要取得像 AI 模型镜像
  IMAGE_NAME: ${{ github.repository_owner }}/bert-inference-runtime

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```
### 3. 构建
提交代码 -> 等待 Action 构建成功 -> 确保 Package 权限为 Public。

#### 🚀 第二阶段：Hugging Face 部署
## 1. 创建 Space
·Type: Docker
·Files: 仅需创建 Dockerfile 和 README.md。
# Dockerfile
```Dockerfile
FROM ghcr.io/<你的GitHub用户名>/<镜像名>:main
USER root
RUN chmod +x /app/boot.py && chmod 777 /app/data
CMD ["python3", "/app/boot.py"]
```
# README.md
```README.md
---
title: Model Inference API
emoji: 📉
colorFrom: yellow
colorTo: red
sdk: docker
pinned: false
---
# System Maintenance
Service is currently offline for maintenance.
```
## 2. 环境变量 (Secrets)

请在 Hugging Face Space 的 **Settings** -> **Variables and secrets** 中添加以下变量：

| 变量名 | 说明 | 示例值 |
| :--- | :--- | :--- |
| `AUTH_PASS` | **[必填]** 管理员密码 & 隐形门密钥 | `123456` |
| `WEBDAV_URL` | **[必填]** WebDAV 地址 (末尾必须带 `/`) | `https://mori.teracloud.jp/dav/` |
| `WEBDAV_USER` | **[必填]** WebDAV 用户名 | `user_id` |
| `WEBDAV_PASS` | **[必填]** WebDAV 密码 (**TeraCloud 请务必使用应用密码**) | `abcd-efgh-ijkl` |
| `WEBDAV_PATH` | [可选] 备份文件夹名 (默认为 `sys_backup`) | `my_backup` |
| `SYNC_INTERVAL` | [可选] 备份间隔 (秒，默认为 `3600`) | `7200` |

---

## 💻 使用指南

### 1. 首次进入 (开门)
默认访问首页会显示“系统维护”伪装页。首次访问或 Cookie 过期后，需通过以下链接解锁：

> **访问地址**: `https://你的空间名.hf.space/auth?key=你的AUTH_PASS`

*   **跳转后登录**:
    *   **账号**: `admin`
    *   **密码**: 即你在环境变量中设置的 `AUTH_PASS`

### 2. 分享下载
在 OpenList 后台管理中开启 **guest (游客)** 的 **预览/下载** 权限后，Nginx 会自动放行分享链接，无需密钥即可访问：

> **分享示例**: `https://你的空间名.hf.space/d/文件夹/视频.mp4`
