FROM debian:bullseye-slim

# 安装基础工具 -> 下载 OpenList -> 重命名为 sys_core_logic -> 清理痕迹
RUN apt-get update && \
    apt-get install -y curl tar ca-certificates && \
    curl -L https://github.com/OpenListTeam/OpenList/releases/latest/download/openlist-linux-amd64.tar.gz -o temp.tar.gz && \
    tar -xzf temp.tar.gz && \
    mv openlist /usr/local/bin/sys_core_logic && \
    chmod +x /usr/local/bin/sys_core_logic && \
    rm temp.tar.gz && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 设置默认入口（后续会被覆盖，这里只是占位）
ENTRYPOINT [ "sys_core_logic" ]
