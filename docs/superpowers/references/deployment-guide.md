# 部署指南

| 项目 | 内容 |
|---|---|
| 文档状态 | K8s Arthas 智能诊断平台部署指南 |
| 创建日期 | 2026-05-22 |
| 版本 | v1.0 |
| 状态 | 参考文档 |

## 1. 环境要求

### 1.1 服务器要求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 20 GB | 50 GB |
| 操作系统 | CentOS 7+ / Ubuntu 18.04+ | CentOS 7+ / Ubuntu 20.04+ |

### 1.2 软件依赖

| 软件 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.10+ | 运行环境 |
| pip | 20.0+ | 包管理 |
| kubectl | 1.20+ | Kubernetes 命令行工具 |
| Docker | 20.10+ | 容器运行时（可选） |
| Git | 2.20+ | 版本控制 |

### 1.3 Kubernetes 要求

| 组件 | 要求 |
|------|------|
| Kubernetes 集群 | 1.18+ |
| kubeconfig | 有效的集群配置文件 |
| 权限 | 至少需要 Pod 读取、执行权限 |
| 网络 | 能够访问 Kubernetes API Server |

## 2. 安装部署

### 2.1 源码部署

#### 步骤 1：克隆代码

```bash
git clone https://github.com/your-repo/k8s-arthas-tool.git
cd k8s-arthas-tool
```

#### 步骤 2：创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows
```

#### 步骤 3：安装依赖

```bash
pip install -r requirements.txt
```

#### 步骤 4：配置集群

```bash
# 复制集群配置模板
cp config/clusters.json.example config/clusters.json

# 编辑集群配置
vim config/clusters.json
```

集群配置示例：

```json
[
  {
    "id": "prod-cluster",
    "name": "生产集群",
    "kubeconfig": "/path/to/kubeconfig",
    "context": "production"
  },
  {
    "id": "dev-cluster",
    "name": "开发集群",
    "kubeconfig": "/path/to/kubeconfig",
    "context": "development"
  }
]
```

#### 步骤 5：初始化数据库

```bash
# 数据库会在首次启动时自动初始化
python server.py
```

#### 步骤 6：启动服务

```bash
# 前台启动
python server.py

# 后台启动
nohup python server.py > server.log 2>&1 &
```

### 2.2 Docker 部署

#### 步骤 1：构建镜像

```bash
docker build -t k8s-arthas-tool:latest .
```

#### 步骤 2：运行容器

```bash
docker run -d \
  --name k8s-arthas-tool \
  -p 5000:5000 \
  -v /path/to/kubeconfig:/app/config/kubeconfig \
  -v /path/to/clusters.json:/app/config/clusters.json \
  k8s-arthas-tool:latest
```

### 2.3 Kubernetes 部署

#### 步骤 1：创建配置

```bash
# 创建 ConfigMap
kubectl create configmap arthas-config \
  --from-file=config/clusters.json

# 创建 Secret（可选）
kubectl create secret generic arthas-secret \
  --from-literal=admin-password=admin123
```

#### 步骤 2：部署应用

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k8s-arthas-tool
spec:
  replicas: 1
  selector:
    matchLabels:
      app: k8s-arthas-tool
  template:
    metadata:
      labels:
        app: k8s-arthas-tool
    spec:
      containers:
      - name: arthas-tool
        image: k8s-arthas-tool:latest
        ports:
        - containerPort: 5000
        volumeMounts:
        - name: config
          mountPath: /app/config
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: config
        configMap:
          name: arthas-config
```

```bash
kubectl apply -f k8s-deployment.yaml
```

#### 步骤 3：创建服务

```yaml
# k8s-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: k8s-arthas-tool
spec:
  selector:
    app: k8s-arthas-tool
  ports:
  - port: 80
    targetPort: 5000
  type: LoadBalancer
```

```bash
kubectl apply -f k8s-service.yaml
```

## 3. 配置说明

### 3.1 集群配置

`config/clusters.json` 配置项：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 集群唯一标识 |
| `name` | string | 是 | 集群显示名称 |
| `kubeconfig` | string | 是 | kubeconfig 文件路径 |
| `context` | string | 否 | kubectl context |

### 3.2 服务配置

`server.py` 支持的环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `5000` | 监听端口 |
| `DEBUG` | `False` | 调试模式 |
| `SECRET_KEY` | 随机生成 | Flask Secret Key |
| `DATABASE_URL` | `arthas.db` | 数据库路径 |

### 3.3 安全配置

#### 用户管理

- 默认管理员：`admin` / `admin123`
- 首次登录后建议修改密码
- 支持 RBAC 角色控制（admin/user）

#### 审计日志

- 所有操作自动记录审计日志
- 支持查询操作历史
- 日志保留 90 天

## 4. 功能验证

### 4.1 基础功能测试

```bash
# 1. 访问主页
curl http://localhost:5000/

# 2. 登录测试
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# 3. 集群列表
curl http://localhost:5000/api/clusters

# 4. Pod 列表
curl http://localhost:5000/api/clusters/prod-cluster/namespaces/default/pods
```

### 4.2 连接测试

```bash
# 1. 连接 Pod
curl -X POST http://localhost:5000/api/pod/connect \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "prod-cluster",
    "namespace": "default",
    "pod_name": "my-pod",
    "container": "my-container",
    "java_pid": "1"
  }'

# 2. 连接列表
curl http://localhost:5000/api/pod/connections

# 3. 连接健康检查
curl http://localhost:5000/api/arthas/connections/<connection_id>/ping
```

### 4.3 诊断测试

```bash
# 1. 执行 Arthas 命令
curl -X POST http://localhost:5000/api/arthas/exec \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": "<connection_id>",
    "command": "thread -n 3"
  }'

# 2. 执行诊断模板
curl -X POST http://localhost:5000/api/diagnosis/execute \
  -H "Content-Type: application/json" \
  -d '{
    "capability_id": 1,
    "connection_id": "<connection_id>",
    "params": {}
  }'
```

## 5. 运维管理

### 5.1 日志查看

```bash
# 查看服务日志
tail -f server.log

# 查看审计日志
curl http://localhost:5000/api/audit-logs

# 查看任务日志
curl http://localhost:5000/api/tasks/<task_id>/logs
```

### 5.2 数据库维护

```bash
# 备份数据库
cp arthas.db arthas.db.backup.$(date +%Y%m%d)

# 清理历史数据
sqlite3 arthas.db "
DELETE FROM arthas_commands WHERE timestamp < datetime('now', '-30 days');
DELETE FROM profiler_tasks WHERE created_at < datetime('now', '-30 days');
DELETE FROM audit_logs WHERE timestamp < datetime('now', '-90 days');
"
```

### 5.3 性能监控

```bash
# 查看系统资源
top -p $(pgrep -f "python server.py")

# 查看网络连接
netstat -tlnp | grep 5000

# 查看磁盘使用
df -h
du -sh arthas.db
```

## 6. 故障排除

### 6.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 服务启动失败 | 端口被占用 | 修改端口或停止占用进程 |
| 连接集群失败 | kubeconfig 无效 | 检查 kubeconfig 配置 |
| Pod 连接失败 | 网络不通 | 检查网络和防火墙 |
| Arthas 启动失败 | JDK 版本不兼容 | 检查 JDK 版本 |
| 数据库错误 | 文件权限问题 | 检查文件权限 |

### 6.2 日志分析

```bash
# 查看错误日志
grep -i error server.log

# 查看访问日志
grep -i "POST\|GET" server.log | tail -20

# 查看慢查询
grep -i "slow\|timeout" server.log
```

### 6.3 性能优化

1. **数据库优化**
   - 启用 WAL 模式
   - 添加必要索引
   - 定期清理历史数据

2. **内存优化**
   - 限制并发连接数
   - 及时释放资源
   - 监控内存使用

3. **网络优化**
   - 使用本地 kubeconfig
   - 配置合理的超时时间
   - 使用连接池

## 7. 安全建议

### 7.1 网络安全

- 使用 HTTPS 加密传输
- 限制访问 IP 范围
- 配置防火墙规则

### 7.2 认证授权

- 修改默认管理员密码
- 使用强密码策略
- 定期更换密码
- 配置多因素认证（可选）

### 7.3 数据安全

- 定期备份数据库
- 加密敏感数据
- 限制日志保留时间
- 监控异常操作

## 8. 升级指南

### 8.1 版本升级

```bash
# 1. 备份数据
cp arthas.db arthas.db.backup

# 2. 拉取最新代码
git pull origin main

# 3. 更新依赖
pip install -r requirements.txt

# 4. 重启服务
# 如果使用 systemd
sudo systemctl restart arthas-tool

# 如果使用 Docker
docker restart k8s-arthas-tool
```

### 8.2 数据库迁移

```bash
# 数据库迁移会在启动时自动执行
python server.py

# 检查迁移状态
sqlite3 arthas.db "SELECT * FROM schema_version;"
```

## 9. 回滚指南

### 9.1 代码回滚

```bash
# 1. 停止服务
# 2. 切换到旧版本
git checkout <old-version>
# 3. 重启服务
python server.py
```

### 9.2 数据库回滚

```bash
# 1. 停止服务
# 2. 恢复数据库备份
cp arthas.db.backup arthas.db
# 3. 重启服务
python server.py
```

## 10. 联系支持

### 10.1 问题反馈

- GitHub Issues: https://github.com/your-repo/k8s-arthas-tool/issues
- 邮件支持: support@yourcompany.com

### 10.2 文档更新

- 文档仓库: https://github.com/your-repo/k8s-arthas-tool/docs
- 更新日志: CHANGELOG.md