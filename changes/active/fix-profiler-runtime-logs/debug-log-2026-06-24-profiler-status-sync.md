# 采样状态与日志同步问题排查记录

## 症状

- 点击“开始采样”后后台能看到 Arthas 连接日志，但任务未真正开始时前端仍可能显示运行中。
- 采样日志停在第一行，前端按本地时间制造进度，和后台实际执行时间不一致。
- 点击“探测 GC”后，因为前端日志渲染函数写库，触发大量 `POST /api/profile/logs`。

## 根因

- async-profiler 启动只看 `profiler start` 返回，没有再用 `profiler status` 校验真实运行态。
- 服务层只在任务结束时落库，运行中的 workflow 日志没有同步到 `profiler_tasks.message/updated_at/progress`。
- 服务层无条件把 `workflow.run()` 的结果写成 `completed`，即使 workflow 已返回 `failed`。
- 前端轮询存在重复定时器风险，且 `pfLog()` 每渲染一行日志都会 POST 保存。
- 前端进度由本地 elapsed/duration 估算，可能出现“前端到 1 分钟，后台仍在采样”的错觉。

## 修复

- `backend/core/profiler.py`：启动 profiler 后追加 `profiler status` 校验，失败时直接返回 `failed`。
- `services/profiler_service.py`：增加 workflow 进度回调，运行中同步后端真实日志时间；最终状态按 workflow 返回值写入，失败不再误标完成。
- `server.py`：`/api/profile/start` 使用 `_ensure_connection()` 返回的真实 `connection_id`，状态接口返回顶层 `message/updated_at`。
- `static/js/app-ui.js`：采样请求携带当前连接 ID；轮询定时器单例化；进度改用后端 `progress`；`pfLog()` 只渲染不写库。
- `tests/test_profiler_runtime_logs.py`：增加状态同步、启动校验、轮询单例、GC 探测不触发采样轮询、日志不 POST 的回归断言。

## 验证

- `node --check static\js\app-ui.js`
- `python -m py_compile server.py services\profiler_service.py backend\core\profiler.py tests\test_profiler_runtime_logs.py`
- 本地未安装 `pytest`，使用内置 Python 手动执行 `tests/test_profiler_runtime_logs.py` 中 11 条断言，全部通过。
