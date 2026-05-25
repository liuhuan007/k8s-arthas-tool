# Arthas 命令速查表

| 项目 | 内容 |
|---|---|
| 文档状态 | Arthas 常用命令速查 |
| 创建日期 | 2026-05-22 |
| 版本 | v1.0 |
| 状态 | 参考文档 |

## 1. 基础命令

### 1.1 基础信息

| 命令 | 说明 | 示例 |
|------|------|------|
| `version` | 查看 Arthas 版本 | `version` |
| `help` | 帮助信息 | `help` |
| `cls` | 清空屏幕 | `cls` |
| `session` | 当前会话信息 | `session` |
| `reset` | 重置增强类 | `reset` |
| `quit` | 退出 Arthas | `quit` |
| `stop` | 关闭 Arthas Server | `stop` |
| `keymap` | 快捷键列表 | `keymap` |

### 1.2 JVM 信息

| 命令 | 说明 | 示例 |
|------|------|------|
| `jvm` | JVM 信息 | `jvm` |
| `sysprop` | 系统属性 | `sysprop` |
| `sysenv` | 系统环境变量 | `sysenv` |
| `vmoption` | JVM 选项 | `vmoption` |
| `perfcounter` | 性能计数器 | `perfcounter` |
| `logger` | 日志信息 | `logger` |
| `heapdump` | 堆转储 | `heapdump /tmp/dump.hprof` |
| `vmtool` | JVM 工具 | `vmtool --action getInstances --className java.lang.String` |

## 2. 类与方法

### 2.1 类搜索

| 命令 | 说明 | 示例 |
|------|------|------|
| `sc` | 搜索类 | `sc -d *OrderService*` |
| `sm` | 搜索方法 | `sm *OrderService* *` |

### 2.2 类反编译

| 命令 | 说明 | 示例 |
|------|------|------|
| `jad` | 反编译类 | `jad com.example.OrderService` |
| `jad --source-only` | 只反编译源码 | `jad --source-only com.example.OrderService` |

### 2.3 类加载器

| 命令 | 说明 | 示例 |
|------|------|------|
| `classloader` | 类加载器信息 | `classloader` |
| `classloader -t` | 类加载器树 | `classloader -t` |

## 3. 线程分析

### 3.1 线程信息

| 命令 | 说明 | 示例 |
|------|------|------|
| `thread` | 线程列表 | `thread` |
| `thread -n 3` | 最忙的 3 个线程 | `thread -n 3` |
| `thread -b` | 死锁检测 | `thread -b` |
| `thread <id>` | 指定线程详情 | `thread 1` |
| `thread -a` | 所有线程 | `thread -a` |
| `thread --state RUNNABLE` | 指定状态线程 | `thread --state RUNNABLE` |

## 4. 性能诊断

### 4.1 仪表盘

| 命令 | 说明 | 示例 |
|------|------|------|
| `dashboard` | 实时仪表盘 | `dashboard` |
| `dashboard -n 1` | 只刷新一次 | `dashboard -n 1` |

### 4.2 方法追踪

| 命令 | 说明 | 示例 |
|------|------|------|
| `trace` | 方法调用链追踪 | `trace com.example.OrderService createOrder` |
| `trace -n 5` | 最多追踪 5 次 | `trace -n 5 com.example.OrderService createOrder` |
| `trace #cost > 100` | 过滤耗时 > 100ms | `trace #cost > 100 com.example.OrderService createOrder` |

### 4.3 方法观测

| 命令 | 说明 | 示例 |
|------|------|------|
| `watch` | 方法执行观测 | `watch com.example.OrderService createOrder params` |
| `watch -x 2` | 展开 2 层 | `watch -x 2 com.example.OrderService createOrder params` |
| `watch -n 3` | 最多观测 3 次 | `watch -n 3 com.example.OrderService createOrder params` |
| `watch returnObj` | 观测返回值 | `watch com.example.OrderService createOrder returnObj` |
| `watch throwExp` | 观测异常 | `watch com.example.OrderService createOrder throwExp` |

### 4.4 方法调用栈

| 命令 | 说明 | 示例 |
|------|------|------|
| `stack` | 方法调用栈 | `stack com.example.OrderService createOrder` |
| `stack -n 3` | 最多记录 3 次 | `stack -n 3 com.example.OrderService createOrder` |

### 4.5 方法统计

| 命令 | 说明 | 示例 |
|------|------|------|
| `monitor` | 方法执行统计 | `monitor -c 10 com.example.OrderService createOrder` |
| `monitor -c 5` | 每 5 秒统计一次 | `monitor -c 5 com.example.OrderService createOrder` |

## 5. 代码增强

### 5.1 类重转换

| 命令 | 说明 | 示例 |
|------|------|------|
| `retransform` | 重转换类 | `retransform /path/to/OrderService.class` |
| `retransform --classOnly` | 只重转换指定类 | `retransform --classOnly com.example.OrderService` |

### 5.2 类重定义

| 命令 | 说明 | 示例 |
|------|------|------|
| `redefine` | 重定义类 | `redefine /path/to/OrderService.class` |

**注意**：`redefine` 有技术限制：
- 不能修改方法签名
- 不能添加/删除字段
- 不能修改父类/接口
- 不能修改注解
- 对 Spring Bean 有限制
- JDK 版本有要求
- 自定义类加载器有限制
- 静态初始化块有限制

## 6. 日志管理

### 6.1 日志信息

| 命令 | 说明 | 示例 |
|------|------|------|
| `logger` | 查看日志 | `logger` |
| `logger --name ROOT` | 指定 logger | `logger --name ROOT` |

### 6.2 日志级别

| 命令 | 说明 | 示例 |
|------|------|------|
| `logger --level DEBUG` | 设置日志级别 | `logger --level DEBUG` |
| `logger --level INFO` | 设置 INFO 级别 | `logger --level INFO` |

## 7. 诊断工具

### 7.1 性能采样

| 命令 | 说明 | 示例 |
|------|------|------|
| `profiler` | 性能采样 | `profiler start` |
| `profiler start --duration 30` | 采样 30 秒 | `profiler start --duration 30` |
| `profiler getFlatMap` | 获取采样结果 | `profiler getFlatMap` |
| `profiler stop` | 停止采样 | `profiler stop` |

### 7.2 火焰图

| 命令 | 说明 | 示例 |
|------|------|------|
| `profiler start --event cpu` | CPU 采样 | `profiler start --event cpu` |
| `profiler start --event wall` | Wall Clock 采样 | `profiler start --event wall` |
| `profiler start --event itimer` | CPU 时间采样 | `profiler start --event itimer` |

## 8. 常用组合

### 8.1 性能诊断流程

```bash
# 1. 查看仪表盘
dashboard -n 1

# 2. 查看线程
thread -n 3

# 3. 追踪方法
trace com.example.OrderService createOrder

# 4. 观测方法
watch com.example.OrderService createOrder params returnObj

# 5. 性能采样
profiler start --duration 30
profiler stop
```

### 8.2 问题排查流程

```bash
# 1. 查看 JVM 信息
jvm

# 2. 查看系统属性
sysprop

# 3. 查看日志
logger

# 4. 查找类
sc -d *OrderService*

# 5. 查看方法
sm *OrderService* *
```

### 8.3 线程分析流程

```bash
# 1. 查看线程列表
thread

# 2. 查看最忙线程
thread -n 3

# 3. 死锁检测
thread -b

# 4. 指定线程详情
thread 1

# 5. 指定状态线程
thread --state RUNNABLE
```

## 9. 安全注意事项

### 9.1 高危命令

以下命令需要二次确认：

- `retransform` - 类重转换
- `redefine` - 类重定义
- `heapdump` - 堆转储
- `profiler` - 性能采样
- `logger` - 日志级别修改
- `vmoption` - JVM 选项修改

### 9.2 生产环境建议

1. **避免长时间采样**：性能采样建议 30 秒以内
2. **避免频繁重转换**：类重转换可能影响性能
3. **避免修改日志级别**：生产环境谨慎修改日志级别
4. **避免修改 JVM 选项**：生产环境谨慎修改 JVM 选项
5. **及时清理增强**：诊断完成后执行 `reset` 清理增强

## 10. 故障排除

### 10.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 连接失败 | 网络不通 | 检查网络连接和端口 |
| 权限不足 | 用户权限不够 | 检查用户权限 |
| 类找不到 | 类名错误 | 使用 `sc` 搜索类 |
| 方法找不到 | 方法名错误 | 使用 `sm` 搜索方法 |
| 采样失败 | JDK 版本不兼容 | 检查 JDK 版本 |
| 堆转储失败 | 磁盘空间不足 | 检查磁盘空间 |

### 10.2 日志查看

```bash
# 查看 Arthas 日志
logger

# 查看指定 logger
logger --name ROOT

# 设置日志级别
logger --level DEBUG
```