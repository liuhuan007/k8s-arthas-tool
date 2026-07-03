# 连接池重连误判与弱状态文案排查记录

## 排查步骤 todoList
- [x] 搜索连接池 `重连` 前端入口与后端 API。
- [x] 检查 `api/pod_apis.py` 中 Pod 连接复用逻辑。
- [x] 检查连接池 `warn` 状态的徽标与健康文案映射。
- [x] 修复复用前的真实验活逻辑。
- [x] 调整连接池 `warn` 状态文案，避免使用含义不清的“弱”。
- [x] 补充回归测试并运行 `unittest` 与 `node --check`。

## 假设与验证
1. 假设：连接池点击重连不报错，是因为 `/api/pod/connect` 复用了旧内存连接。
   - 验证：`api/pod_apis.py` 复用判断只看 `_healthy`，没有调用 `is_alive()`。
   - 结果：成立。
2. 假设：Pod 已断开但仍可能被当成可复用，是因为 `_healthy` 没有随着 Pod 消失即时置为 `False`。
   - 验证：`PodConnection.is_alive()` 会主动查 Pod phase，但复用逻辑之前没有调用它。
   - 结果：成立。
3. 假设：“⚠ 弱”是连接池 `warn` 健康态的展示文案。
   - 验证：`static/js/components/connection-pool.js` 中 `getBadgeText()` 对 `health === 'warn'` 返回 `⚠ 弱`。
   - 结果：成立。

## 根因链路
连接池点击“重连” -> 前端调用 `/api/pod/connect` -> 后端发现统一连接池里已有同 `conn_id` 的旧连接 -> 仅凭 `_healthy` 直接复用 -> 实际 Pod 已断开但旧连接仍返回 `ok/reused` -> 前端把这次操作当成“已重连”成功。

同时，连接池对 `warn` 健康态使用了 `⚠ 弱` 这个过于简写的文案，用户无法直观看出它表达的是“连接不稳定/健康检查连续失败”。

## 最终修复方案
- `api/pod_apis.py`
  - 复用旧 Pod 连接前调用 `is_alive()` 做真实验活。
  - 验活失败时先清理旧连接，再走新连接流程，让前端收到真实失败或真正重建成功。
- `static/js/components/connection-pool.js`
  - 将 `warn` 徽标从 `⚠ 弱` 改为 `⚠ 不稳`。
  - 将详情健康文案从“响应缓慢”改为“连接不稳定”。
- `tests/test_connection_pool_reconnect_fixes.py`
  - 新增回归断言，保护“复用前验活”和“warn 文案清晰化”。

## 验证记录
- `python -m unittest tests.test_connection_pool_reconnect_fixes tests.test_two_step_connection_fixes`
  - 14 tests, `OK`
- `node --check static/js/components/connection-pool.js`
  - 通过
