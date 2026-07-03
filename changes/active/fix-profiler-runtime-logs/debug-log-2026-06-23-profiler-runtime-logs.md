# 采样任务未真实开始与日志轮询异常排查记录

## 排查步骤 todoList

- [x] 搜索 `/api/profile/start`、`/api/profile/logs`、`/api/gc/info` 和前端采样轮询入口。
- [x] 阅读 `server.py` 旧采样 API、`services/profiler_service.py` 后台任务服务、`backend/core/profiler.py` 实际工作流。
- [x] 阅读 `static/js/app-ui.js` 中 `pfStart`、`pfPoll`、`pfLog`、`pfRunGcLog`。
- [x] 增加回归测试覆盖后台真实日志同步和前端请求风暴风险。
- [x] 修复后台工作流日志回写、状态接口 message 返回、前端无效日志 POST。
- [x] 运行回归测试验证。

## 假设与验证结果

### 假设 1：后台任务线程没有启动

验证：`/api/profile/start` 会调用 `ProfilerService.create_task()` 后立即调用 `start_task()`，`start_task()` 创建 daemon 线程执行 `workflow.run()`。

结果：假设不成立。线程会启动，但前端只能看到数据库中初始 message，无法观察工作流内部日志。

### 假设 2：前端日志停在第一行是因为状态接口没有返回 message

验证：`server.py` 的 `/api/profile/<task_id>` 原先只返回 `logs`，没有返回顶层 `message`；而 `pfPoll()` 读取的是 `d.message`。

结果：成立。前端轮询拿不到后台任务最新 message，自然只停留在本地提交任务日志。

### 假设 3：后台工作流日志没有同步到数据库

验证：`ProfilerWorkflow._log()` 只写入内存 `self.logs` 和 Python logger；`ProfilerService.get_task_status()` 只读 `profiler_tasks.message`，而该字段在任务完成前没有被工作流更新。

结果：成立。真实执行进度无法被 `/api/profile/<task_id>` 读取。

### 假设 4：点击 GC 探测导致 `/api/profile/logs` 请求很多次

验证：`pfLog()` 每打印一行日志都会 POST `/api/profile/logs`，GC 探测会连续打印 PID、参数、路径、预览内容等多行日志。

结果：成立。GC 探测本身没有启动 `pfPoll()`，请求风暴来自日志渲染函数每行持久化。

## 根因定位链

用户点击开始采样后，后端确实进入 `ProfilerWorkflow.run()` 并在后台 logger 中输出 Arthas 连接和采样步骤；但这些日志只保存在工作流实例内存中，没有同步到 `profiler_tasks.message`。前端 `pfPoll()` 又依赖 `/api/profile/<task_id>` 的顶层 `message` 字段输出日志，而接口未返回该字段，所以界面只显示启动时本地产生的第一批日志。

同时，`pfLog()` 将所有 UI 日志行都 POST 到 `/api/profile/logs`，且传的是 `connection_id` 而非任务 ID，会对 `profiler_tasks` 做无意义更新。GC 探测会输出多行日志，因此一次探测会触发多次 `/api/profile/logs`。

## 最终修复方案和理由

1. `backend/core/profiler.py`
   - `ProfilerWorkflow` 增加 `progress_callback`。
   - `_log()` 每次生成后台日志时调用回调。
   - 理由：日志源应来自真实后台执行，而不是前端本地估算或重复保存。

2. `services/profiler_service.py`
   - 增加 `_sync_workflow_progress()`，将 Workflow 最新日志同步到 `profiler_tasks.message/updated_at`，并按后端真实 `进度 N/Ms` 更新 progress。
   - 创建 `ProfilerWorkflow` 时注入回调。
   - 理由：状态接口读取数据库即可拿到后台最新执行点，前后端时间线一致。

3. `server.py`
   - `/api/profile/<task_id>` 返回 `message` 和 `updated_at`。
   - 理由：满足前端 `pfPoll()` 的实际消费字段，避免只返回兼容 logs 导致消息丢失。

4. `static/js/app-ui.js`
   - `pfLog()` 不再 POST `/api/profile/logs`，只负责渲染 UI。
   - `pfPoll()` 使用后端 `updated_at` 格式化日志时间。
   - 新增 `formatProfilerLogTime()`。
   - 理由：消除 GC 探测造成的 `/api/profile/logs` 请求风暴，并让日志时间尽量对齐后台执行更新时间。

## 验证

- `python -m pytest tests/test_profiler_runtime_logs.py tests/test_profiler_migration.py`
- 结果：42 passed。

## 后续测试建议

- 使用真实 Pod 执行 30 秒 CPU 采样，确认界面出现 “检查 Pod 状态 / 连接 Arthas / 启动 async-profiler / 进度 10/30s” 等后台日志。
- 点击一次 GC 探测，浏览器 Network 中应只看到一次 `/api/gc/info`，不再出现多次 `/api/profile/logs`。
- 采样 60 秒时，以后端日志和前端日志时间对比，确认前端日志时间使用后端 `updated_at`，不会提前宣布采样完成。
