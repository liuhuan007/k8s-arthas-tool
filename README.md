# Arthas K8s 诊断台

> 针对 Kubernetes Pod 的一站式 Java 性能诊断平台。  
> 基于 **Alibaba Arthas + async-profiler**，通过 `kubectl` 实现零侵入诊断，无需修改代码或重启服务。

---

## 目录

- [功能概览](#功能概览)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [部署说明](#部署说明)
- [Arthas 命令参考](#arthas-命令参考)
- [性能分析指南](#性能分析指南)
- [文件命名规则](#文件命名规则)
- [项目文件说明](#项目文件说明)
- [常见问题](#常见问题)
- [参考资料](#参考资料)

---

## 功能概览

| 模块 | 功能描述 |
|------|---------|
| ⚡ **Arthas 诊断** | 46 条命令 / 7 个分组，可折叠面板，参数构建器，持续输出 Session |
| 🔥 **性能分析** | async-profiler (cpu/alloc/lock/wall) · JDK JFR · 线程 Dump · Heap Dump |
| 📊 **Pod 监控** | CPU/内存仪表盘、进程列表、网络流量、K8s 事件、容器日志下载 |
| 📑 **GC 日志** | 自动探测 JVM GC 日志路径（JDK 8/9+），预览末尾内容、一键下载 |
| 📂 **文件浏览器** | Pod 内文件浏览，`kubectl cp` 三级降级下载，文本预览 |
| 🖥️ **Pod 终端** | 内嵌 Shell 终端，Tab 补全浮层、命令历史、`cd` 目录跟踪 |
| 🔧 **集群管理** | 多集群 / 多 Context 切换，Namespace 自动加载，连接状态检测 |

---

## 系统架构

```
┌───────────────────────────────────────────────────────────────┐
│                    浏览器  (index.html)                        │
│   app-ui.js (集群/诊断/监控/分析)  app-terminal.js (终端)      │
│   app.css                                                      │
└──────────────────────────┬────────────────────────────────────┘
                           │  HTTP REST  POST /api/*
┌──────────────────────────▼────────────────────────────────────┐
│                  server.py  (Flask 3.x)                        │
│                                                                │
│  /api/clusters/*     集群管理                                  │
│  /api/arthas/*       Arthas HTTP API 代理                      │
│  /api/profile/*      性能分析任务（异步）                       │
│  /api/monitor/*      Pod 指标采集                              │
│  /api/pod/*          exec / files / terminal                   │
│  /api/gc/*           GC 日志探测 & 下载                        │
│  /api/files          本地采样文件列表                           │
└──────────┬───────────────────────────────────────────────────┘
           │
  ┌────────┴──────────────┐     ┌────────────────────────────┐
  │  profiler_backend.py  │     │       pod_monitor.py        │
  │                       │     │                             │
  │  Layer 0: 数据模型    │     │  KubectlRunner              │
  │  Layer 1: Kubectl执行 │     │  collect_pod_snapshot()     │
  │  Layer 2: Agent管理   │     │  start_metrics_polling()    │
  │  Layer 3: HTTP客户端  │     │                             │
  │  Layer 4: 连接管理    │     │  采集项:                    │
  │  Layer 5: 任务编排    │     │  · CPU/内存 (cgroup)        │
  └────────┬──────────────┘     │  · 进程列表 (ps)           │
           │                    │  · 网络流量 (proc/net)      │
           └──────────┬─────────┘  · Pod 状态 (kubectl)      │
                      │            └────────────────────────────┘
                      │ subprocess
┌─────────────────────▼─────────────────────────────────────────┐
│                      kubectl  CLI                               │
│   exec  ·  port-forward  ·  cp  ·  logs  ·  top  ·  get      │
└─────────────────────────────┬─────────────────────────────────┘
                              │ Kubernetes API Server
┌─────────────────────────────▼─────────────────────────────────┐
│                    Kubernetes  Pod                              │
│                                                                │
│   Java 应用进程                                                 │
│       ↕  attach                                                 │
│   Arthas Agent  :8563 (HTTP)  :3658 (telnet)                   │
│                                                                │
│   /proc/PID/cmdline    →  GC 参数探测                          │
│   /sys/fs/cgroup/*     →  CPU / 内存指标                       │
│   /proc/net/*          →  网络流量                             │
└────────────────────────────────────────────────────────────────┘
```

### profiler_backend.py — 五层架构

| 层 | 类名 | 职责 |
|----|------|------|
| Layer 0 | `ClusterConfig` `PodTarget` | 数据模型，不含逻辑 |
| Layer 1 | `KubectlExecutor` | kubectl 原语（exec/cp/port-forward），不含业务逻辑 |
| Layer 2 | `ArthasAgentManager` | Pod 内 Agent 生命周期：检测 → 清理残留 → 启动 → 等待就绪 |
| Layer 3 | `ArthasHttpClient` | Arthas HTTP API 封装：ping / exec / session / pull |
| Layer 4 | `ArthasConnection` | 连接编排：agent + port-forward + ping，支持短路复用 |
| Layer 5 | `ProfilerWorkflow` | 性能分析任务：profiler / jfr / threaddump / heapdump |

**ArthasConnection 短路复用规则：**

```
① HTTP 可达 → 直接复用，不重建 port-forward
② Agent 已运行 → 只建立 port-forward
③ 全新连接 → agent + port-forward + HTTP ping
```

---

## 快速开始

### 前置条件

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.10 | 服务端运行环境 |
| kubectl | 1.20 | 需配置好 kubeconfig 并有对应权限 |
| 目标 Pod | Java 8+ | 需能执行 `kubectl exec`，推荐预置 Arthas JAR |
| Arthas JAR | 3.7+ | 部署到 Pod 内（见下方安装方法） |

### 3 步启动

```bash
# 1. 进入项目目录
cd k8s-arthas-tool

# 2. 一键启动（自动安装依赖 + 打开浏览器）
./deploy/start.sh

# 3. 在浏览器左侧添加集群配置，选择 Pod 开始诊断
```

### 手动启动

```bash
# 1. 创建并激活 conda 环境
conda create -n arthas python=3.10 -y
conda activate arthas

# 2. 安装依赖并启动服务
pip install -r requirements.txt
python server.py                     # 默认 127.0.0.1:5005
python server.py --port 8080         # 自定义端口
python server.py --host 0.0.0.0      # 允许外部访问（跳板机场景）
```

### 向 Pod 安装 Arthas JAR

工具按优先级自动探测以下路径（优先 /app/arthas/）：

```
/app/arthas/arthas-boot.jar     ← 推荐位置
/opt/arthas/arthas-boot.jar
/arthas/arthas-boot.jar
/home/admin/arthas-boot.jar
```

**安装方式：**

```bash
# 脚本一键安装
./deploy/install-arthas.sh <namespace> <pod-name>

# 手动安装
kubectl exec -n <ns> <pod> -- bash -c "
  mkdir -p /app/arthas
  curl -Lo /app/arthas/arthas-boot.jar \
    https://arthas.aliyun.com/arthas-boot.jar"

# Dockerfile 预置（推荐生产环境，避免每次下载）
RUN mkdir -p /app/arthas && \
    curl -Lo /app/arthas/arthas-boot.jar \
      https://arthas.aliyun.com/arthas-boot.jar
```

---

## 部署说明

### 场景一：本地桌面（默认）

kubectl 在本机可用，最简方式：

```bash
./deploy/start.sh
# 自动检查依赖 → 启动服务 → 打开浏览器
```

### 场景二：跳板机 / 远程服务器

kubectl 只能在特定服务器执行时：

```bash
# 上传项目到跳板机
scp -r k8s-arthas-tool/ user@jump-server:/opt/arthas-tool/

# 在跳板机启动，监听所有网卡
ssh user@jump-server "cd /opt/arthas-tool && nohup python server.py \
  --host 0.0.0.0 --port 5005 > arthas-tool.log 2>&1 &"

# 修改 index.html 第一行的 API 地址
# const API = 'http://jump-server-ip:5005/api';

# 浏览器访问
open http://jump-server-ip:5005/
```

**推荐：SSH 隧道（无需暴露端口）**

```bash
ssh -L 5005:localhost:5005 user@jump-server \
  "cd /opt/arthas-tool && python server.py"
# 本地浏览器直接打开 index.html（API 保持默认 127.0.0.1:5005）
```

### 场景三：Docker 部署

```bash
# 构建镜像
docker build -f deploy/Dockerfile -t arthas-k8s-tool:latest .

# 运行（挂载 kubeconfig 和输出目录）
docker run -d \
  --name arthas-tool \
  -p 5005:5005 \
  -v ~/.kube:/root/.kube:ro \
  -v $(pwd)/data/profiler:/app/data/profiler \
  arthas-k8s-tool:latest

# 查看日志
docker logs -f arthas-tool

# 浏览器访问
open http://localhost:5005/
```

### 场景四：Docker Compose

```bash
# 编辑 deploy/docker-compose.yml，修改 kubeconfig 路径
vim deploy/docker-compose.yml

# 启动
docker compose -f deploy/docker-compose.yml up -d

# 查看日志
docker compose -f deploy/docker-compose.yml logs -f
```

### 场景五：systemd 服务（长期运行）

```bash
# 安装为系统服务（需 root）
sudo ./deploy.sh --systemd --host 0.0.0.0 --port 5005

# 服务管理命令
sudo systemctl start  arthas-tool
sudo systemctl stop   arthas-tool
sudo systemctl status arthas-tool
sudo journalctl -u arthas-tool -f
```

### deploy.sh 完整参数

```bash
./deploy.sh                                    # 前台运行，默认 127.0.0.1:5005
./deploy.sh --host 0.0.0.0                     # 监听所有网卡
./deploy.sh --port 8080                        # 自定义端口
./deploy.sh --daemon                           # 后台运行（nohup）
./deploy.sh --systemd                          # 安装为 systemd 服务
./deploy.sh --stop                             # 停止后台运行的实例
./deploy.sh --status                           # 查看运行状态
./deploy.sh --install-arthas <ns> <pod>        # 向 Pod 内安装 Arthas
```

### kubectl RBAC 权限

```yaml
# 最小权限集（deploy/rbac.yaml）
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["pods/exec"]
  verbs: ["create"]
- apiGroups: [""]
  resources: ["pods/portforward"]
  verbs: ["create"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]
- apiGroups: [""]
  resources: ["namespaces"]
  verbs: ["list"]
```

---

## Arthas 命令参考

> 官方文档：https://arthas.aliyun.com/en/doc/  
> 命令面板支持折叠分组，点击命令后弹出参数构建器。

---

### 🖥️ JVM 基础信息

#### `dashboard` — 实时仪表板

```
官方文档：https://arthas.aliyun.com/en/doc/dashboard.html
用途：问题排查第一步，快速获取 JVM 全局状态

输出内容：
  · 线程列表（ID/名称/CPU占用%/状态）
  · 内存各区域（heap/eden/survivor/old/metaspace）used/total/max
  · GC 统计（次数/耗时）
  · 系统信息（CPU/内存/OS/JDK版本）

用法：
  dashboard           # 默认 5s 刷新，持续输出（Ctrl+C 停止）
  dashboard -i 2000   # 每 2000ms 刷新一次
  dashboard -n 3      # 输出 3 次后自动退出
```

#### `jvm` — JVM 详细信息

```
官方文档：https://arthas.aliyun.com/en/doc/jvm.html
用途：确认生产环境 JVM 配置，排查 JVM 参数问题

输出内容：
  · RUNTIME：JDK 版本、JVM 名称、启动时间、classpath
  · CLASS-LOADING：已加载类数量、总加载次数
  · COMPILATION：JIT 编译时间
  · GARBAGE-COLLECTORS：GC 算法名称、次数、耗时
  · MEMORY-MANAGERS：内存管理器列表
  · MEMORY：各内存池详情
  · OPERATING-SYSTEM：CPU 核心数、系统负载、内存
  · THREAD：线程数峰值、当前线程数

用法：jvm   （无参数）
```

#### `memory` — 内存用量

```
官方文档：https://arthas.aliyun.com/en/doc/memory.html
用途：快速查看内存各区域使用情况，定位内存泄漏区域

输出分类：
  heap      堆内存（eden/survivor/old）
  nonheap   非堆（metaspace/compressed class space）
  buffer    堆外内存（direct/mapped）

用法：memory   （无参数）
```

#### `thread` — 线程分析

```
官方文档：https://arthas.aliyun.com/en/doc/thread.html
用途：CPU 飙高排查、死锁检测、线程状态分析——最常用的基础命令

参数说明：
  （无参数）          列出所有线程及 CPU 占用（按 CPU 排序）
  -n <N>              只显示 CPU 最高的 N 个线程
  <tid>               查看指定线程 ID 的完整堆栈
  -b                  检测死锁和持锁阻塞（BLOCKED）
  --state <STATE>     按状态过滤：RUNNABLE / BLOCKED / WAITING / TIMED_WAITING
  -all                输出所有线程完整堆栈（等价 jstack）
  -i <ms>             采样间隔（默认 200ms，影响 CPU 统计精度）

典型用法：
  thread -n 3                      # CPU 最高的 3 个线程 → CPU 飙高排查首选
  thread -b                        # 死锁检测 → 接口无响应、请求堆积
  thread --state BLOCKED           # 所有阻塞线程
  thread 42                        # 查看线程 ID=42 的堆栈
  thread -all                      # 完整线程快照（导出 jstack 等价内容）
```

#### `sysprop` — 系统属性

```
官方文档：https://arthas.aliyun.com/en/doc/sysprop.html
用途：查看 / 动态修改 System.getProperties()

用法：
  sysprop                          # 列出所有系统属性
  sysprop java.version             # 查看指定属性值
  sysprop file.encoding            # 查看字符编码
  sysprop file.encoding UTF-8      # 动态修改（立即生效，无需重启）
```

#### `vmoption` — JVM 运行期参数

```
官方文档：https://arthas.aliyun.com/en/doc/vmoption.html
用途：动态查看/修改 JVM 运行期参数，不需要重启 JVM

用法：
  vmoption                                        # 列出所有可修改参数
  vmoption PrintGC                                # 查看当前值
  vmoption HeapDumpOnOutOfMemoryError true        # OOM 时自动 dump
  vmoption HeapDumpPath /tmp/oom.hprof            # 指定 dump 路径
  vmoption PrintGCDetails true                    # 开启 GC 详细日志

常用参数：
  HeapDumpOnOutOfMemoryError   OOM 时自动 HeapDump
  HeapDumpPath                 HeapDump 保存路径
  PrintGC / PrintGCDetails     开启 GC 日志输出
```

---

### 🔍 类与类加载器

#### `sc` — 搜索已加载的类（Search Class）

```
官方文档：https://arthas.aliyun.com/en/doc/sc.html
用途：排查 JAR 冲突（同名类被哪个 JAR 加载）、确认类是否已加载

参数：
  <pattern>   类名，支持通配符 *（如 *UserService*）
  -d          显示类详情：ClassLoader / 来源 JAR / 父类 / 接口 / 注解
  -f          同时显示字段信息
  -x <N>      字段值展开层级

用法：
  sc *UserService*                 # 模糊搜索
  sc com.example.UserServiceImpl   # 精确搜索
  sc -d com.example.UserServiceImpl  # 查看来源 JAR（排查版本冲突）
  sc -d -f com.example.Config      # 显示所有字段
```

#### `sm` — 搜索方法（Search Method）

```
官方文档：https://arthas.aliyun.com/en/doc/sm.html
用途：watch/trace 命令执行前，确认方法名、参数类型是否正确

参数：
  <class>   类名
  <method>  方法名（可选，支持通配符）
  -d        显示方法详情（参数类型/返回类型/修饰符/注解）
  -E        使用正则表达式匹配

用法：
  sm com.example.UserService          # 列出所有方法
  sm com.example.UserService login    # 搜索 login 方法
  sm -d com.example.UserService login # 完整方法签名
```

#### `classloader` — 类加载器

```
官方文档：https://arthas.aliyun.com/en/doc/classloader.html
用途：排查 ClassLoader 问题（Spring Boot fat jar、Tomcat 类隔离等）

参数：
  -t          树形展示 ClassLoader 继承关系
  -l          列出所有 ClassLoader 及各自加载的类数量
  -c <hash>   查看指定 ClassLoader（hash 值）加载了哪些类
  -a          列出所有 ClassLoader 加载的类（数量很多慎用）

用法：
  classloader -t               # 查看 ClassLoader 树
  classloader -l               # 统计各 ClassLoader 加载类数量
```

#### `jad` — 反编译类

```
官方文档：https://arthas.aliyun.com/en/doc/jad.html
用途：确认生产环境运行的是哪个版本的代码，排查热修复是否生效

参数：
  <class>    全限定类名（必填）
  [method]   方法名（可选，只反编译指定方法）

用法：
  jad com.example.UserService              # 反编译整个类
  jad com.example.UserService login        # 只看 login 方法
```

#### `mc` + `retransform` — 热修复

```
官方文档：
  mc:          https://arthas.aliyun.com/en/doc/mc.html
  retransform: https://arthas.aliyun.com/en/doc/retransform.html

用途：无需重启 JVM 修复线上 bug（生产热修复）

完整流程：
  # Step 1: 反编译获取源码
  jad com.example.BugClass > /tmp/BugClass.java

  # Step 2: 编辑修复 bug
  # （在 Pod 终端内用 vi 或 sed 修改 /tmp/BugClass.java）

  # Step 3: 内存编译
  mc /tmp/BugClass.java -d /tmp

  # Step 4: 热重载
  retransform /tmp/com/example/BugClass.class

  # Step 5: 验证修复
  watch com.example.BugClass bugMethod "{params,returnObj}" -n 3

限制：
  · 不能新增/删除方法或字段
  · 不能修改方法签名
  · 不能修改继承关系
  · 修改在 JVM 重启后失效
```

---

### 👁 方法监控与追踪

#### `watch` — 观察方法调用

```
官方文档：https://arthas.aliyun.com/en/doc/watch.html
用途：最常用的诊断命令，实时观察入参/返回值/异常，无需改代码加日志

参数：
  <class>   类名（支持通配符）
  <method>  方法名（支持通配符）
  <expr>    OGNL 表达式（观察哪些内容）
  -x <N>    对象展开层级（默认 1，建议 2-3）
  -n <N>    最多触发 N 次（重要！避免无限输出）
  -b        在方法调用前触发（before）
  -e        仅在方法抛出异常时触发（exception）
  -s        在方法正常返回时触发（success）
  <cond>    条件表达式（OGNL，返回 true 才触发）
  -f        在方法 finally 时触发（before + after）

典型用法：
  # 最常用：入参+返回值+异常
  watch com.example.UserService login "{params,returnObj,throwExp}" -x 2 -n 5

  # 只看异常（适合偶发异常排查）
  watch com.example.UserService * "{throwExp}" -e -n 10

  # 按条件过滤（只有 userId=123 时才触发）
  watch com.example.UserService login "{params,returnObj}" \
    "params[0].userId == '123'" -n 5

  # 查看耗时
  watch com.example.UserService login "{cost}" -n 5

  # 只看慢调用（>500ms）
  watch com.example.UserService login "{params,returnObj}" \
    "#cost > 500" -n 10
```

**OGNL 表达式速查：**

| 表达式 | 含义 |
|--------|------|
| `"{params}"` | 入参数组（数组形式） |
| `"{returnObj}"` | 返回值 |
| `"{throwExp}"` | 异常对象 |
| `"{params,returnObj,throwExp}"` | 全部（推荐） |
| `"{params[0]}"` | 第一个参数 |
| `"{params[0].userId}"` | 第一个参数的 userId 字段 |
| `"{cost}"` | 方法耗时（毫秒） |
| `"params[0] != null"` | 条件：第一个参数不为 null |
| `"#cost > 100"` | 条件：耗时超过 100ms |

#### `trace` — 追踪方法调用树

```
官方文档：https://arthas.aliyun.com/en/doc/trace.html
用途：展示方法调用树及各节点耗时，精准定位性能瓶颈在哪个子调用

参数：
  <class>   类名
  <method>  方法名
  -n <N>    追踪次数（必填，避免无限输出）
  --skipJDKMethod  跳过 JDK 内部方法调用（减少噪音，默认 true）
  <cond>    条件（如 '#cost > 100' 只追踪慢调用）

用法：
  trace com.example.UserService login -n 5

  # 只追踪慢调用（耗时 > 200ms）
  trace com.example.UserService login '#cost > 200' -n 10

  # 多级追踪（先追踪 A 发现慢在 B，再追踪 B）
  trace com.example.serviceA methodA -n 3
  trace com.example.serviceB methodB -n 5

输出格式：
  +--- login() time=456ms
  |  +--- 0.1ms -> checkPermission()
  |  +--- 3.5ms -> getUser()
  |  +--- 450ms -> queryOrderList()   ← 慢在这里！
  |  `+-- 2.1ms -> buildResponse()
```

#### `monitor` — 统计方法调用指标

```
官方文档：https://arthas.aliyun.com/en/doc/monitor.html
用途：持续统计方法的 QPS/RT/成功率，适合接口压测时监控

参数：
  -c <N>  统计周期（秒，默认 60）
  -n <N>  统计轮次
  -b      在方法调用前统计（统计入参维度）

用法：
  monitor com.example.UserService login -c 5 -n 12

输出列：
  timestamp / class / method / total（调用次数）/
  success（成功次数）/ fail（失败次数）/
  avg（平均RT ms）/ fail-rate（失败率）
```

#### `stack` — 查看调用栈

```
官方文档：https://arthas.aliyun.com/en/doc/stack.html
用途：定位某个方法被谁调用的（调用链溯源）

用法：
  stack com.example.UserService login -n 5
  # 每次有调用时，输出完整的调用者堆栈
```

#### `tt` — 时间隧道

```
官方文档：https://arthas.aliyun.com/en/doc/tt.html
用途：记录方法调用历史，事后查看入参/返回值，可重放请求

参数：
  -t <class> <method>   开始记录（-n 指定记录次数）
  -l                    列出所有历史记录
  -i <index>            查看指定记录的入参/返回值
  -p -i <index>         重放指定次的调用
  -s <expr>             搜索记录（按条件过滤）

用法：
  tt -t com.example.UserService login -n 20      # 记录 20 次调用
  tt -l                                          # 列出所有记录
  tt -i 1003                                     # 查看 index=1003 的详情
  tt -p -i 1003                                  # 重放 index=1003 的调用

  # 搜索入参中 userId=123 的记录
  tt -s "params[0].userId == '123'"
```

---

### 🧮 OGNL & 变量操作

#### `ognl` — 执行 OGNL 表达式

```
官方文档：https://arthas.aliyun.com/en/doc/ognl.html
用途：读写静态变量、调用方法、动态修改配置，功能极其强大

参数：
  <expr>    OGNL 表达式（字符串，用引号括起）
  -x <N>    结果展开层级
  -c <hash> 指定 ClassLoader（多 ClassLoader 场景）

典型用法：
  # 执行系统方法
  ognl "@java.lang.System@currentTimeMillis()"

  # 读取静态变量
  ognl "@com.example.Config@INSTANCE.timeout"

  # 修改静态变量（⚠ 谨慎操作！）
  ognl "@com.example.Config@INSTANCE.timeout = 5000"

  # 调用 Spring Bean 方法（通过 ApplicationContext）
  ognl "@org.springframework.boot.SpringApplication@context.getBean('userService').getUserCount()"

  # 创建对象
  ognl "new java.util.ArrayList()"

  # 格式化日期
  ognl "new java.text.SimpleDateFormat('yyyy-MM-dd').format(new java.util.Date())"
```

#### `vmtool` — 堆内对象工具

```
官方文档：https://arthas.aliyun.com/en/doc/vmtool.html
用途：直接获取堆中运行的对象实例，比 heapdump 轻量，不触发 STW

参数：
  --action getInstances   获取堆中实例
  --action forceGc        强制 Full GC
  --className <class>     目标类全限定名
  -l <N>                  最多获取 N 个实例（默认 10）
  -x <N>                  对象展开层级

典型用法：
  # 查看 Cache 对象内部数据
  vmtool --action getInstances \
    --className com.example.LocalCache -l 1 -x 3

  # 统计某类实例数量（排查内存泄漏）
  vmtool --action getInstances \
    --className com.example.Connection -l 200 -x 1

  # 强制 Full GC（触发内存回收，观察是否有对象未释放）
  vmtool --action forceGc
```

#### `logger` — 动态修改日志级别

```
官方文档：https://arthas.aliyun.com/en/doc/logger.html
用途：运行时按需开启 DEBUG 日志，排查完后恢复，无需重启

用法：
  logger                                       # 列出所有 Logger 及当前级别
  logger --name com.example                    # 查看指定 Logger
  logger --name com.example --level DEBUG      # 开启 DEBUG（立即生效）
  logger --name com.example.dao --level TRACE  # 开启 SQL 日志
  logger --name ROOT --level INFO              # 排查完后恢复

注意：修改后对所有新日志立即生效，但 JVM 重启后恢复配置文件设置。
```

---

### 🔥 性能分析工具选型

| 工具 | JDK 版本 | 使用场景 | 开销 |
|------|---------|---------|------|
| async-profiler cpu | 全部 | CPU 热点，函数级分析 | 低 |
| async-profiler alloc | 全部 | 对象分配热点，GC 压力分析 | 低 |
| async-profiler lock | 全部 | 锁竞争分析 | 低 |
| async-profiler wall | 全部 | IO 密集型，含等待时间 | 低 |
| JDK JFR | 11+ | 全面事件录制，长期监控 | 极低 |
| 线程 Dump | 全部 | 死锁/卡顿，一次性快照 | 极低 |
| Heap Dump | 全部 | OOM/内存泄漏深度分析 | **高（触发 STW）** |
| GC 日志分析 | 全部 | GC 停顿优化 | 无（读已有文件）|

---

## 性能分析指南

### 场景一：CPU 飙高排查

```
Step 1  dashboard                        全局概览，确认是 CPU 还是 GC 问题
Step 2  thread -n 5                      找 CPU 最高的 5 个线程及堆栈
Step 3  thread <tid>                     深入查看最忙线程堆栈
Step 4  trace com.xx.Svc *               追踪方法耗时，找热点调用
Step 5  面板 → 🔥 async-profiler → cpu  火焰图采样（60-300s），直观展示调用热点
```

### 场景二：内存泄漏 / OOM

```
Step 1  memory                           查看各内存区域，确认哪块持续增长
Step 2  vmtool --action getInstances     直接查看堆中疑似泄漏对象数量
         --className 疑似泄漏类
Step 3  面板 → 🔥 async-profiler → alloc 内存分配火焰图，找对象创建热点
Step 4  面板 → 💾 Dump → Heap Dump      导出 .hprof，用 MAT 做 Dominator Tree
Step 5  jad 泄漏类                       反编译确认是否有引用未释放
```

### 场景三：接口超时 / 请求堆积

```
Step 1  thread -b                        首先检测死锁
Step 2  thread --state BLOCKED           查看所有阻塞线程
Step 3  watch com.xx.Svc method \
          "{params,returnObj,throwExp}"  观察是否有异常或超大入参
Step 4  trace com.xx.Svc method \
          '#cost > 500' -n 10            追踪慢调用链
Step 5  面板 → 🔥 async-profiler → wall  Wall-clock 采样（含 IO 等待时间）
```

### 场景四：GC 问题分析

```
Step 1  面板 → 📑 GC 日志 → 探测        自动找到 GC 日志文件，查看 GC 停顿
Step 2  jvm                             确认 GC 算法（G1/CMS/ZGC/Parallel）
Step 3  memory                          对比 old gen / metaspace 增长趋势
Step 4  面板 → 🔥 async-profiler → alloc 分析对象分配压力
Step 5  vmoption HeapDumpOnOutOfMemoryError true
                                        预防：OOM 时自动 dump
```

### 场景五：生产热修复流程

```
Step 1  jad com.example.BugClass > /tmp/BugClass.java
Step 2  # 在 Pod 终端内修改 /tmp/BugClass.java
Step 3  mc /tmp/BugClass.java -d /tmp
Step 4  retransform /tmp/com/example/BugClass.class
Step 5  watch com.example.BugClass method "{params,returnObj}" -n 3
```

---

## 文件命名规则

格式：`{类型}-{标识}-{podName}-{YYYYMMDDHHmmss}.{后缀}`

| 类型 | 格式 | 示例 |
|------|------|------|
| async-profiler CPU | `profiler-cpu-{pod}-{ts}.html` | `profiler-cpu-udc-7cc5-20260322153847.html` |
| async-profiler 内存 | `profiler-alloc-{pod}-{ts}.html` | `profiler-alloc-udc-7cc5-20260322153847.html` |
| async-profiler JFR | `profiler-wall-{pod}-{ts}.jfr` | `profiler-wall-udc-7cc5-20260322153847.jfr` |
| JDK JFR | `jfr-{name}-{pod}-{ts}.jfr` | `jfr-arthas-jfr-udc-7cc5-20260322153847.jfr` |
| Heap Dump | `heap-{pod}-{ts}.hprof` | `heap-udc-7cc5-20260322153847.hprof` |
| Thread Dump | `threaddump-{pod}-{ts}.txt` | `threaddump-udc-7cc5-20260322153847.txt` |
| GC 日志 | `gc-{pod}-{ts}.log` | `gc-udc-7cc5-20260322153847.log` |
| 容器日志 | `logs-{pod}-{ctr}-{ts}.log` | `logs-udc-7cc5-app-20260322153847.log` |

所有文件保存在 `data/profiler/` 目录，「历史记录」标签可查看和下载。

---

## 项目文件说明

```
k8s-arthas-tool/
├── index.html                  前端入口（引用 static/ 目录）
├── static/
│   ├── css/app.css             全部样式（暗色主题，约 340 行）
│   └── js/
│       ├── app-ui.js           主功能（1600+ 行）
│       │                       · 集群管理 / Arthas 命令面板（46 条/7 组/折叠）
│       │                       · 性能分析（profiler/jfr/dump/gclog 4 种模式）
│       │                       · Pod 监控（概览/指标/进程/网络/事件/日志）
│       │                       · 文件浏览器 / 历史记录
│       └── app-terminal.js     Pod 终端（490 行）
│                               · kubectl exec 交互 / Tab 补全 / 命令历史
├── server.py                   Flask REST API（850+ 行）
│                               · /api/clusters/* · /api/arthas/*
│                               · /api/profile/*  · /api/monitor/*
│                               · /api/pod/*      · /api/gc/*
├── profiler_backend.py         核心后端（1050+ 行）
│                               · 五层架构（L0~L5）
│                               · ProfilerWorkflow 四种模式
├── pod_monitor.py              Pod 指标采集（580 行）
├── requirements.txt            Python 依赖（flask / flask-cors）
├── clusters.json               集群配置（自动生成）
├── data/profiler/              采样文件（自动创建）
├── deploy.sh                   主部署脚本（全功能，含 daemon/systemd/stop）
└── deploy/
    ├── start.sh                快速启动（Linux/macOS）
    ├── start.bat               快速启动（Windows）
    ├── Dockerfile              Docker 镜像
    ├── docker-compose.yml      Docker Compose
    ├── k8s-deployment.yaml     K8s 部署清单
    ├── install-arthas.sh       向 Pod 安装 Arthas JAR
    └── rbac.yaml               kubectl 最小 RBAC 权限
```

---

## API 接口说明

### 集群管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/clusters` | 列出集群 |
| POST | `/api/clusters` | 添加集群 |
| PUT | `/api/clusters/<n>` | 更新集群 |
| DELETE | `/api/clusters/<n>` | 删除集群 |
| POST | `/api/clusters/<n>/test` | 测试连接 |
| GET | `/api/clusters/<n>/namespaces` | Namespace 列表 |
| GET | `/api/clusters/<n>/pods` | Pod 列表 |

### 诊断 & 分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/arthas/connect` | 建立 Arthas 连接 |
| POST | `/api/arthas/exec` | 同步执行命令 |
| POST | `/api/arthas/session/create` | 创建 Session |
| POST | `/api/arthas/session/exec` | Session 异步执行 |
| POST | `/api/arthas/session/pull` | 拉取输出 |
| POST | `/api/profile/start` | 启动分析任务 |
| GET | `/api/profile/<id>` | 任务状态 + 日志 |
| GET | `/api/profile/<id>/download` | 下载结果 |
| POST | `/api/gc/info` | GC 日志探测 |
| POST | `/api/gc/download` | GC 日志下载 |

---

## 常见问题

### Arthas 连接超时

```bash
# 查看启动日志
kubectl exec -n <ns> <pod> -- tail -30 /tmp/arthas_start.log

# 确认 JAR 存在
kubectl exec -n <ns> <pod> -- ls -la /app/arthas/

# 确认 Java 版本
kubectl exec -n <ns> <pod> -- java -version

# 确认端口未占用
kubectl exec -n <ns> <pod> -- ss -tlnp | grep 8563
```

### profiler stop 文件找不到

某些 Arthas 版本会忽略 `--file` 参数，直接写到 `arthas-output/`，工具已自动扫描：

```
/tmp/*.{ext}
/arthas-output/*.{ext}
/home/admin/arthas-output/*.{ext}
/root/arthas-output/*.{ext}
```

### JFR 报错不可用

JDK JFR 需要 JDK 11+，请用 async-profiler 替代：

```bash
kubectl exec -n <ns> <pod> -- java -version
# Java 1.8.x → 使用 async-profiler 模式
```

### GC 日志未找到

JVM 默认不开 GC 日志，需加启动参数并重启：

```bash
# JDK 8
-Xloggc:/app/logs/gc.log -XX:+PrintGCDetails -XX:+PrintGCDateStamps

# JDK 9+（推荐）
-Xlog:gc*:file=/app/logs/gc.log:time,tags:filecount=5,filesize=20m
```

### Failed to fetch

1. 确认服务运行：`curl http://127.0.0.1:5005/api/health`
2. 检查 `index.html` 第一行：`const API = 'http://127.0.0.1:5005/api'`
3. 跨机访问：修改 API 地址并开放 5005 端口

### kubectl 权限不足

```bash
kubectl auth can-i create pods/exec        -n <namespace>
kubectl auth can-i create pods/portforward -n <namespace>
kubectl auth can-i get    pods             -n <namespace>
```

---

## 参考资料

| 资源 | 链接 |
|------|------|
| Arthas 官方文档 | https://arthas.aliyun.com/en/doc/ |
| Arthas 命令列表 | https://arthas.aliyun.com/en/doc/commands.html |
| Arthas HTTP API | https://arthas.aliyun.com/en/doc/http-api.html |
| Arthas profiler 命令 | https://arthas.aliyun.com/en/doc/profiler.html |
| Arthas JFR 命令 | https://arthas.aliyun.com/en/doc/jfr.html |
| Arthas 在线教程 | https://arthas.aliyun.com/doc/arthas-tutorials.html |
| async-profiler GitHub | https://github.com/async-profiler/async-profiler |
| JDK Mission Control | https://adoptium.net/jmc/ |
| Eclipse MAT | https://eclipse.dev/mat/ |
