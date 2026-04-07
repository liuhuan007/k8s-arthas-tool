FROM python:3.11

WORKDIR /app

# 安装 kubectl
RUN apt-get update && apt-get install -y curl && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && mv kubectl /usr/local/bin/ && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件（新的目录结构）
COPY server.py ./
COPY api ./api
COPY models ./models
COPY services ./services
COPY backend ./backend
COPY static ./static
COPY openspec ./openspec
COPY clusters.json ./
COPY rbac.yaml ./

# 创建输出目录
RUN mkdir -p profiler_output

ENV ARTHAS_HOST=0.0.0.0
ENV ARTHAS_PORT=5001

EXPOSE 5001

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:5001/api/health || exit 1

# 服务端同时 serve 静态文件
CMD python server.py --host ${ARTHAS_HOST} --port ${ARTHAS_PORT}
