# 第一阶段：构建加密载荷
FROM python:3.9-slim as builder
WORKDIR /build
COPY builder.py .
RUN pip install requests && python builder.py

# 第二阶段：生成最终镜像
FROM python:3.9-slim-bullseye

# 安装运行环境 (Nginx + Python)
RUN apt-get update && \
    apt-get install -y nginx apache2-utils procps && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制那个“假模型文件”
COPY --from=builder /build/pytorch_model.bin /app/pytorch_model.bin

# 复制 Nginx 配置和启动脚本 (稍后创建)
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY boot.py /app/boot.py

# 权限
RUN chmod +x /app/boot.py && \
    mkdir -p /app/data && \
    chmod 777 /app/data

# 暴露 HF 端口
EXPOSE 7860

CMD ["python3", "/app/boot.py"]
