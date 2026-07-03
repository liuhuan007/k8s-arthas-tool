# 重连失败无交互提示排查记录

## 排查步骤 todoList
- [x] 搜索所有“重连”前端入口和后端接口。
- [x] 检查连接池 `ConnectionPool.reconnect()` 的错误处理。
- [x] 检查一键重连 `reconnectCurrentConnection()` 与 `podConnect()` 的调用关系。
- [x] 检查 `showPodError()` / `toast()` 的触发链路。
- [x] 修复连接池与一键重连的错误反馈。
- [x] 补充回归测试并运行 `unittest` 与 `node --check`。

## 假设与验证
1. 假设：连接池重连失败时没有提示，是因为只处理 `d.ok === false`，没有兼容 `HTTP 4xx`。
   - 验证：`ConnectionPool.reconnect()` 原逻辑先 `await r.json()`，只判断 `!d.ok`。
   - 结果：成立，接口异常时提示链不够稳。
2. 假设：一键重连没有稳定提示，是因为 `podConnect()` 在内部吞掉错误，外层无法知道失败。
   - 验证：`reconnectCurrentConnection()` 直接 `await podConnect()`，而 `podConnect()` catch 后只做 UI 提示、不返回失败信号。
   - 结果：成立，外层会继续后续流程。
3. 假设：已有结构化错误组件，但不是所有重连入口都在调用。
   - 验证：`two-step-connection.js` 会调 `showPodError()`，`connection-pool.js` 原先只 toast。
   - 结果：成立。

## 根因链路
后端已返回 `{"ok": false, "error": "Pod 不存在或无法访问"}`，但前端两条重连路径不一致：
- 连接池重连只做了较脆弱的 `toast` 分支；
- 一键重连调用 `podConnect()` 后拿不到明确失败结果。

这导致接口明明报错，界面提示却不稳定，用户感知像是“没反应”。

## 最终修复方案
- `static/js/components/connection-pool.js`
  - 兼容 `HTTP 非 2xx` 与 `JSON ok=false` 两种失败形式。
  - 失败时同时触发 `showPodError()` 和 `toast()`。
- `static/js/components/two-step-connection.js`
  - `podConnect()` 成功返回 `true`，失败返回 `false`。
  - 记录 `window._lastPodConnectError` 供外层重连流程复用。
- `static/js/app-ui.js`
  - 一键重连检查 `podConnect()` 返回值，失败时使用原始错误信息中断流程。
- `tests/test_reconnect_error_feedback.py`
  - 新增回归断言，保护错误提示链路。

## 验证记录
- `python -m unittest tests.test_reconnect_error_feedback tests.test_connection_pool_reconnect_fixes tests.test_two_step_connection_fixes`
  - 17 tests, `OK`
- `node --check static/js/components/connection-pool.js`
  - 通过
- `node --check static/js/components/two-step-connection.js`
  - 通过
- `node --check static/js/app-ui.js`
  - 通过
