# K8s Arthas 智能诊断平台 - 工具目录

## 目录结构

```
tools/
├── arthas/                          # Arthas工具包
│   ├── arthas-boot.jar              # Arthas主程序
│   └── arthas-tunnel-server.jar     # Tunnel Server（注册中心）
├── agent-sdk/                       # Agent SDK
│   ├── codebuddy-agent-sdk/         # CodeBuddy SDK（推荐）
│   ├── claude-agent-sdk/            # Claude SDK（备选）
│   └── venv/                        # Python虚拟环境
├── config/                          # 配置文件
│   └── agent-sdk-config.json        # Agent SDK配置
├── scripts/                         # 辅助脚本
│   ├── install-arthas.sh           # 安装Arthas到Pod
│   ├── start-tunnel-server.sh      # 启动Tunnel Server
│   ├── connect-tunnel.sh           # 连接到Tunnel Server
│   └── setup-agent-sdk.sh          # 安装Agent SDK
└── README.md                        # 本文件
```

## 工具说明

### 1. arthas-boot.jar

Arthas主程序，用于在Java应用中执行诊断命令。

**使用方式**：
```bash
# 在Pod中启动Arthas
java -jar arthas-boot.jar

# 连接到Tunnel Server
java -jar arthas-boot.jar --tunnel-server 'ws://127.0.0.1:7777/ws' --app-name <pod-name>
```

### 2. arthas-tunnel-server.jar

Tunnel Server，作为Arthas连接的注册中心，统一管理所有Pod的Arthas连接。

**启动方式**：
```bash
java -jar arthas-tunnel-server.jar --server.port 7777
```

**功能**：
- 监听WebSocket连接（默认端口7777）
- 统一管理所有Pod的Arthas连接
- 提供Web控制台查看连接状态
- 支持多用户同时访问

## 部署模式

### 模式1：离线环境（无网络）

当环境无法访问外网时，使用本地预制的工具包：

```bash
# 1. 将tools目录复制到部署服务器
scp -r tools/ user@server:/opt/arthas-k8s-tool/

# 2. 使用kubectl cp将arthas-boot.jar复制到Pod
kubectl cp tools/arthas/arthas-boot.jar <namespace>/<pod>:/tmp/arthas-boot.jar

# 3. 在Pod中启动Arthas
kubectl exec -it <pod> -- java -jar /tmp/arthas-boot.jar
```

### 模式2：在线环境（有网络）

当环境可以访问外网时，从阿里云下载最新版本：

```bash
# 1. 在Pod中直接下载并启动
kubectl exec -it <pod> --container <container> -- /bin/bash -c \
  "wget https://arthas.aliyun.com/arthas-boot.jar && java -jar arthas-boot.jar"

# 2. 或者连接到Tunnel Server
kubectl exec -it <pod> --container <container> -- /bin/bash -c \
  "wget https://arthas.aliyun.com/arthas-boot.jar && \
   java -jar arthas-boot.jar --tunnel-server 'ws://127.0.0.1:7777/ws' --app-name <pod-name>"
```

### 模式3：Tunnel Server统一管理（推荐）

启动Tunnel Server作为注册中心，所有Pod连接到这个中心：

```bash
# 1. 启动Tunnel Server（在部署服务器上）
java -jar arthas-tunnel-server.jar --server.port 7777

# 2. Pod连接到Tunnel Server
java -jar arthas-boot.jar --tunnel-server 'ws://<tunnel-server-ip>:7777/ws' --app-name <pod-name>

# 3. 通过Web控制台访问
# http://<tunnel-server-ip>:7777
```

## app-name命名规则

Tunnel Server使用`app-name`来标识每个Pod连接，建议使用Pod名称：

```bash
# 获取Pod名称
POD_NAME=$(kubectl get pod -n <namespace> -l app=<app-label> -o jsonpath='{.items[0].metadata.name}')

# 使用Pod名称作为app-name
java -jar arthas-boot.jar --tunnel-server 'ws://127.0.0.1:7777/ws' --app-name $POD_NAME
```

## 3. Agent SDK

Agent SDK用于实现智能诊断，支持自主决策和工具调用。

### 3.1 支持的SDK

| SDK | 提供商 | 特点 | 推荐场景 |
|-----|--------|------|---------|
| **CodeBuddy Agent SDK** | 腾讯 | 国内稳定、权限控制好 | 生产环境 |
| **Claude Agent SDK** | Anthropic | 功能强大、文档完善 | 开发测试 |

### 3.2 安装Agent SDK

```bash
# 安装CodeBuddy Agent SDK（推荐）
./tools/scripts/setup-agent-sdk.sh codebuddy

# 安装Claude Agent SDK（备选）
./tools/scripts/setup-agent-sdk.sh claude
```

### 3.3 配置Agent SDK

编辑配置文件：`tools/config/agent-sdk-config.json`

```json
{
    "sdk_type": "codebuddy",
    "model": "deepseek-v3.1",
    "permission_mode": "bypassPermissions",
    "api_key": "YOUR_API_KEY_HERE",
    "base_url": "YOUR_BASE_URL_HERE"
}
```

### 3.4 使用Agent SDK

```python
from codebuddy_agent_sdk import query, tool

# 定义诊断工具
@tool("execute_arthas", "Execute Arthas command", {"command": str})
async def execute_arthas(args):
    # 执行Arthas命令
    result = await run_arthas_command(args["command"])
    return {"output": result}

# 执行诊断
async for message in query(
    prompt="诊断CPU飙高问题",
    tools=[execute_arthas]
):
    print(message)
```

---

## 版本信息

| 工具 | 版本 | 说明 |
|------|------|------|
| arthas-boot.jar | 3.7.2 | Arthas主程序 |
| arthas-tunnel-server.jar | 4.1.7 | Tunnel Server |
| codebuddy-agent-sdk | 0.3.150 | CodeBuddy Agent SDK |
| claude-agent-sdk | 0.2.86 | Claude Agent SDK |

## 测试状态

| SDK | 状态 | 说明 |
|-----|------|------|
| CodeBuddy Agent SDK | ✅ 测试通过 | 工具定义、执行正常 |
| Claude Agent SDK | ✅ 测试通过 | 导入正常，需要API Key进行完整测试 |
| 诊断工具 | ✅ 测试通过 | kubectl、CPU分析、死锁分析工具正常 |

## 下载地址

- 官方文档：https://arthas.aliyun.com/
- GitHub：https://github.com/alibaba/arthas
- 下载页面：https://arthas.aliyun.com/download.html

## 注意事项

1. **版本兼容性**：确保arthas-boot.jar和arthas-tunnel-server.jar版本兼容
2. **网络配置**：Tunnel Server需要开放7777端口（WebSocket）
3. **权限要求**：Pod需要有Java进程权限
4. **资源占用**：Arthas会占用少量CPU和内存资源
