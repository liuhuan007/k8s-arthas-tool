"""三个专业 Agent — Arthas / K8s / Ops"""
from __future__ import annotations
from .base import Agent, Tool


def _make_empty_executor(tool_name):
    async def executor(**kwargs):
        return f"[{tool_name}] 工具未连接，请确保已建立连接"
    return executor


def create_arthas_agent(llm_client, arthas_connection=None) -> Agent:
    """Arthas 诊断 Agent — Java 性能专家"""

    def _make_exec(method_name):
        async def executor(**kwargs):
            if arthas_connection and hasattr(arthas_connection, method_name):
                return getattr(arthas_connection, method_name)(**kwargs)
            return f"[arthas] 未连接到 Arthas Agent，请先建立连接"
        return executor

    tools = [
        Tool(
            name="arthas_thread",
            description="查看 JVM 线程堆栈，用于诊断死锁、CPU 热点、线程阻塞",
            parameters={
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "显示 top N 个最忙线程"},
                    "state": {"type": "string", "description": "按线程状态过滤: RUNNABLE/BLOCKED/WAITING"},
                },
            },
            executor=_make_exec("thread"),
        ),
        Tool(
            name="arthas_profiler",
            description="async-profiler 采样，生成 CPU/内存/锁的火焰图",
            parameters={
                "type": "object",
                "properties": {
                    "event": {"type": "string", "enum": ["cpu", "alloc", "lock", "wall"], "description": "采样事件类型"},
                    "duration": {"type": "integer", "description": "采样时长（秒），默认 10"},
                },
            },
            executor=_make_exec("profiler_start"),
            risk_level="medium",
        ),
        Tool(
            name="arthas_heap_dump",
            description="生成堆转储文件，用于分析内存泄漏",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "输出文件名"},
                },
            },
            executor=_make_exec("heapdump"),
            risk_level="high",
        ),
        Tool(
            name="arthas_jfr",
            description="Java Flight Recorder 采样，生成 .jfr 文件",
            parameters={
                "type": "object",
                "properties": {
                    "duration": {"type": "integer", "description": "采样时长（秒），默认 60"},
                },
            },
            executor=_make_exec("jfr_start"),
            risk_level="medium",
        ),
        Tool(
            name="gc_analyze",
            description="分析 GC 日志，找出 GC 问题和优化建议",
            parameters={
                "type": "object",
                "properties": {
                    "log_path": {"type": "string", "description": "GC 日志文件路径"},
                },
            },
            executor=_make_empty_executor("gc_analyze"),
        ),
        Tool(
            name="arthas_dashboard",
            description="查看 JVM 实时概览: 内存、线程、GC、类加载",
            parameters={"type": "object", "properties": {}},
            executor=_make_exec("dashboard"),
        ),
        Tool(
            name="arthas_classloader",
            description="查看类加载器树，诊断类加载冲突",
            parameters={"type": "object", "properties": {}},
            executor=_make_exec("classloader"),
        ),
        Tool(
            name="arthas_watch",
            description="观察方法执行，捕获入参、返回值、异常",
            parameters={
                "type": "object",
                "properties": {
                    "class_pattern": {"type": "string", "description": "类名匹配模式"},
                    "method_pattern": {"type": "string", "description": "方法名匹配模式"},
                    "express": {"type": "string", "description": "观察表达式，如 params[0]"},
                },
                "required": ["class_pattern", "method_pattern"],
            },
            executor=_make_exec("watch"),
            risk_level="medium",
        ),
        Tool(
            name="arthas_trace",
            description="追踪方法调用链路，找出慢方法",
            parameters={
                "type": "object",
                "properties": {
                    "class_pattern": {"type": "string", "description": "类名匹配模式"},
                    "method_pattern": {"type": "string", "description": "方法名匹配模式"},
                },
                "required": ["class_pattern", "method_pattern"],
            },
            executor=_make_exec("trace"),
        ),
    ]

    return Agent(
        name="arthas",
        display_name="Arthas 诊断专家",
        system_prompt="""你是 Java 性能诊断专家，精通 Arthas 和 async-profiler。

你的专长：
- CPU 高：用 thread 查看热点线程，用 profiler 采样分析
- 内存问题：用 dashboard 查看内存概况，用 heapdump 分析泄漏
- 死锁：用 thread -b 检测死锁
- GC 问题：用 dashboard 观察 GC 频率，分析 GC 日志
- 方法诊断：用 watch 观察方法执行，用 trace 追踪调用链

工作流程：
1. 先用 dashboard 获取 JVM 概览
2. 根据问题类型选择合适的工具
3. 分析工具输出，找出根因
4. 给出具体的优化建议

注意事项：
- profiler 采样会短暂影响性能，duration 不要太长
- heapdump 会暂停 JVM，需要用户确认
- watch/trace 有性能开销，用完记得关闭""",
        tools=tools,
        llm_client=llm_client,
    )


def create_k8s_agent(llm_client, kubectl_executor=None) -> Agent:
    """K8s 运维 Agent — 集群运维专家"""

    def _make_exec(method_name):
        async def executor(**kwargs):
            if kubectl_executor and hasattr(kubectl_executor, method_name):
                return getattr(kubectl_executor, method_name)(**kwargs)
            return f"[kubectl] 未连接到集群"
        return executor

    tools = [
        Tool(
            name="kubectl_exec",
            description="在 K8s Pod 中执行 shell 命令",
            parameters={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Pod 所在 namespace"},
                    "pod": {"type": "string", "description": "Pod 名称"},
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "container": {"type": "string", "description": "容器名称（多容器 Pod 时指定）"},
                },
                "required": ["namespace", "pod", "command"],
            },
            executor=_make_exec("exec_pod"),
            risk_level="medium",
        ),
        Tool(
            name="kubectl_get_pods",
            description="获取 Pod 列表和状态",
            parameters={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "namespace，默认 default"},
                },
            },
            executor=_make_exec("get_pods"),
        ),
        Tool(
            name="kubectl_get_events",
            description="获取集群事件，排查调度、启动、OOM 等问题",
            parameters={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "namespace"},
                    "pod": {"type": "string", "description": "过滤特定 Pod"},
                },
            },
            executor=_make_exec("get_events"),
        ),
        Tool(
            name="kubectl_get_logs",
            description="获取 Pod 日志",
            parameters={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "namespace"},
                    "pod": {"type": "string", "description": "Pod 名称"},
                    "container": {"type": "string", "description": "容器名称"},
                    "tail": {"type": "integer", "description": "显示最后 N 行，默认 100"},
                },
                "required": ["namespace", "pod"],
            },
            executor=_make_exec("get_logs"),
        ),
        Tool(
            name="kubectl_top_pods",
            description="查看 Pod 资源使用（CPU/Memory）",
            parameters={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "namespace"},
                },
            },
            executor=_make_exec("top_pods"),
        ),
        Tool(
            name="kubectl_cp",
            description="复制文件到 Pod 或从 Pod 复制文件",
            parameters={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "pod": {"type": "string"},
                    "container": {"type": "string"},
                    "local_path": {"type": "string", "description": "本地文件路径"},
                    "remote_path": {"type": "string", "description": "Pod 内路径"},
                },
                "required": ["namespace", "pod", "local_path", "remote_path"],
            },
            executor=_make_exec("cp_to_pod"),
            risk_level="medium",
        ),
    ]

    return Agent(
        name="k8s",
        display_name="K8s 运维专家",
        system_prompt="""你是 Kubernetes 运维专家。

你的专长：
- Pod 问题排查：OOMKilled、CrashLoopBackOff、Pending
- 资源分析：CPU/内存使用、资源配额、limits/requests
- 事件分析：调度失败、镜像拉取失败、探针失败
- 日志分析：应用日志、容器日志
- 文件操作：上传工具到 Pod、下载日志

工作流程：
1. 先用 kubectl_get_pods 了解整体状态
2. 用 kubectl_get_events 查看异常事件
3. 用 kubectl_get_logs 查看应用日志
4. 用 kubectl_top_pods 查看资源使用
5. 综合分析，给出结论和建议""",
        tools=tools,
        llm_client=llm_client,
    )


def create_ops_agent(llm_client, arthas_connection=None, kubectl_executor=None) -> Agent:
    """Ops Agent — 通用运维 + 方案生成"""

    arthas_agent = create_arthas_agent(llm_client, arthas_connection)
    k8s_agent = create_k8s_agent(llm_client, kubectl_executor)

    # 合并所有工具
    all_tools = list(arthas_agent.tools.values()) + list(k8s_agent.tools.values())

    # 加上独有的工具
    all_tools.append(Tool(
        name="generate_script",
        description="根据需求描述生成 Python/Shell/Arthas 脚本",
        parameters={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "脚本功能描述"},
                "runtime": {"type": "string", "enum": ["python", "shell", "arthas"], "description": "脚本类型"},
            },
            "required": ["description"],
        },
        executor=_make_empty_executor("generate_script"),
    ))

    all_tools.append(Tool(
        name="generate_report",
        description="根据诊断数据生成分析报告",
        parameters={
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "诊断数据或问题描述"},
                "format": {"type": "string", "enum": ["markdown", "text"], "description": "输出格式"},
            },
            "required": ["data"],
        },
        executor=_make_empty_executor("generate_report"),
    ))

    return Agent(
        name="ops",
        display_name="SRE 运维助手",
        system_prompt="""你是 SRE 运维专家，能处理各种运维场景。

你的能力：
- Java 性能诊断（通过 Arthas 工具链）
- K8s 集群运维（通过 kubectl 工具链）
- 脚本生成（根据需求自动编写诊断脚本）
- 方案生成（根据症状描述给出排查方案）
- 报告生成（将诊断过程整理为报告）

工作原则：
1. 先理解问题全貌，再选择合适的工具
2. 每步操作都要解释目的
3. 给出可执行的建议，而不是泛泛而谈
4. 考虑操作风险，高风险操作需要确认""",
        tools=all_tools,
        llm_client=llm_client,
    )
