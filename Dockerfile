# ... 前面的内容不变 ...

WORKDIR /app

# 复制文件
COPY --from=builder /build/pytorch_model.bin /app/pytorch_model.bin
# 注意：虽然这里 copy 了 nginx.conf，但 boot.py 会把它覆盖掉，所以无所谓了
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY boot.py /app/boot.py

# 权限
RUN chmod +x /app/boot.py && \
    mkdir -p /app/data && \
    chmod 777 /app/data

# 暴露 HF 端口
EXPOSE 7860

# 【新增】修改这里！每次构建改一下这个数字，强制刷新缓存
ENV BUILD_VERSION=2.0

CMD ["python3", "/app/boot.py"]
