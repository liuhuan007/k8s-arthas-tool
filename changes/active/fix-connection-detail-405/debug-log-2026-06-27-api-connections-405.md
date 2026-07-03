# `/api/connections/{id}` 405 排查记录

## 症状

- 浏览器访问 `http://127.0.0.1:5005/api/connections/%E5%86%85%E9%83%A8%E7%8E%AF%E5%A2%83%2Fseeyon-test106%2Fapp-approval-68f5b5d47-57nl7` 返回 `405`。

## 根因

- 连接 ID 格式是 `cluster/namespace/pod`，URL 编码后仍会在 Flask 路由匹配阶段作为路径分段处理。
- 原详情接口只有 `/api/connections/<connection_id>/detail`，默认转换器不匹配包含 `/` 的连接 ID。
- 裸路径 `/api/connections/<id>` 只有 `DELETE` 路由可匹配，浏览器 `GET` 因此返回 `405 Method Not Allowed`。

## 修复

- 为连接详情增加 `GET /api/connections/<path:connection_id>` 兼容入口。
- 将详情、健康、TTL、运行任务、切换、重连等连接详情子路由统一改为 `<path:connection_id>`，支持包含 `/` 的连接 ID。
- 增加静态回归断言，防止后续把 `path` 转换器改回普通转换器。

## 验证

- `python -m py_compile api\connection_detail.py tests\test_connection_detail_path_routes.py`
- 手动执行 `tests/test_connection_detail_path_routes.py` 中 2 条断言，全部通过。
- `git diff --check -- api/connection_detail.py tests/test_connection_detail_path_routes.py`
