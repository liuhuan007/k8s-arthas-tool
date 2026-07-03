# 新工作区连接 / 采样回归收口排查记录

## 排查步骤 todoList
- [x] 检查连接池、工作区、两步连接三条重连链路是否一致。
- [x] 检查工作区 tab 与 body 是否共用同一层级判定。
- [x] 检查采样启动是否仍以当前焦点连接为真实来源。
- [x] 先补失败中的回归测试，再实现共享重连编排。
- [x] 修复连接池重连、工作区 tab 解析、Arthas 恢复失败回退逻辑。
- [x] 输出 legacy 兼容层清单，保留旧页面和旧路由但标记为兼容层。

## 假设与验证
1. 假设：连接池重连回归，是因为它绕开了工作区现有的 Pod-first / Arthas-restore 编排。
   - 验证：`static/js/components/connection-pool.js` 原先直接调用 `/api/pod/connect`，手工把卡片改成 `connected/pod`。
   - 结果：成立，这会跳过当前连接焦点同步、旧运行态清理和 Arthas 自动恢复。
2. 假设：采样看起来能点但不真正起任务，是因为工作区 tab 隐藏了 Arthas-only 标签，但 body 仍可能挂着旧 `panel-profiler`。
   - 验证：`renderTabs()` 与 `renderBody()` 原先分别读 `vm.level` 与 `c.tab`，没有共享解析。
   - 结果：成立，出现“tab 已隐藏但 profiler 面板还在”的分裂状态。
3. 假设：Arthas 恢复失败后仍停在采样页，是因为重连链路没有统一处理失败后的 tab 回退。
   - 验证：旧的一键重连只看 `podConnect()`，`upgradeToArthas()` 失败后只 toast，不把工作区退回监控页。
   - 结果：成立。

## 根因链路
- `ConnectionPool.reconnect(id)` 自己维护了一套“直连 Pod 就算成功”的语义。
- `reconnectCurrentConnection()` 依赖不存在的旧断开链路，且没有共享给连接池使用。
- `ConnectionWorkspace` 只在 tab 渲染时判断 Arthas 层级，body 仍信任旧 `c.tab`。

最终导致三个表象同时出现：
- 点击重连后卡片可能卡在 `connecting`；
- 页面仍停在采样面板，但真实连接层级已掉到 Pod；
- 采样入口继续吃旧面板状态，看起来可点，实际上没走到正确连接。

## 最终修复方案
- `static/js/app-ui.js`
  - 新增共享入口 `reconnectConnectionById(connId, options = {})`。
  - 重连固定流程改为：聚焦目标 → 同步 Pod 表单 → 清旧运行态 → 恢复 Pod → 按原层级恢复 Arthas。
  - Arthas 恢复失败时，把工作区 tab 强制退回 `monitor` 并给出一次明确提示。
- `static/js/components/two-step-connection.js`
  - `podConnect(options)` / `upgradeToArthas(options)` 支持静默失败返回值，供共享重连入口统一处理提示与回退。
- `static/js/components/connection-pool.js`
  - `reconnect(id)` 不再直调 `/api/pod/connect`，只委托共享重连入口。
- `static/js/components/connection-workspace.js`
  - 新增 `resolveWorkspaceTab(...)`，由 `render()`、`renderTabs()`、`renderBody()`、`switchTab()` 共用。
  - 非 Arthas 状态下，`sampling / console / hotfix / diag` 一律回退到 `monitor`。
- `changes/active/fix-workspace-reconnect-regression/legacy-compat-inventory.md`
  - 记录仍在新工作区挂载的旧面板，以及仍暴露的独立旧页面 / 旧路由。
