# 工具分发交互重设计

> **日期**: 2026-06-19
> **状态**: 设计完成
> **范围**: 单工具分发交互优化（Modal + 智能目标选择）

---

## [S1] 问题定义

### 现状问题

当前单工具分发采用**卡片内联表单**方式：
- 点击"分发"按钮 → 卡片下方展开内联表单
- 表单包含 4 个级联下拉框：集群 → Namespace → Pod → 容器
- 内联空间有限，表单拥挤，操作不便

**具体痛点**：
1. **空间受限** — 内联表单在卡片内，宽度和高度都受限
2. **级联下拉繁琐** — 需要 4 次点击 + 等待加载才能选择目标
3. **无快速选择** — 每次都要从头选择，无法复用上次目标
4. **无能力感知** — 不知道 Pod 是否兼容当前工具

### 设计目标

- **Modal 弹窗** — 提供充足的操作空间
- **智能目标选择** — 一键选择最近使用的目标
- **能力感知** — 显示 Pod 能力状态，避免无效分发
- **减少操作步骤** — 从 4+ 次点击减少到 1-2 次

---

## [S2] 交互设计

### 触发方式

点击工具卡片上的 **[分发]** 按钮 → 打开 Modal 弹窗

### Modal 布局

```
┌─────────────────────────────────────────────────────────────┐
│  分发工具: arthas-boot.jar                          [✕]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ 快速选择 ─────────────────────────────────────────────┐ │
│  │ ⭐ 最近使用                                            │ │
│  │ ┌─────────────────────────────────────────────────┐   │ │
│  │ │ prod / default / pod-a-7cc5f (app)      [选择] │   │ │
│  │ │ prod / default / pod-b-8d2e1 (app)      [选择] │   │ │
│  │ │ staging / dev / pod-c-3f4a2 (main)      [选择] │   │ │
│  │ └─────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ── 或手动选择目标 ──────────────────────────────────────── │
│                                                             │
│  目标类型: [Pod ▾]  (Pod / Node)                           │
│                                                             │
│  集群:     [prod ▾]                                         │
│  Namespace:[default ▾]                                      │
│  Pod:      [pod-a-7cc5f ▾]  ✅ Java 11 + Arthas            │
│  容器:     [app ▾]                                         │
│                                                             │
│  安装路径: [/app/arthas/arthas-boot.jar]                    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                       [取消]  [确认分发]    │
└─────────────────────────────────────────────────────────────┘
```

### 交互流程

1. **点击分发** → 打开 Modal
2. **快速选择**（可选）：
   - 显示最近 3-5 个使用过的目标
   - 点击 [选择] → 自动填充所有字段
3. **手动选择**（如果快速选择不适用）：
   - 选择集群 → 自动加载 Namespace
   - 选择 Namespace → 自动加载 Pod 列表
   - 选择 Pod → 显示能力状态 + 自动填充容器
4. **确认分发** → 显示进度 → 完成后关闭 Modal

### Pod 能力显示

选择 Pod 后，显示能力状态标签：
- ✅ `Java 11 + Arthas` — 可直接使用
- ⚠️ `Java 8 (需升级 Arthas)` — 可分发，但需升级
- ❌ `Go 1.21 (不兼容)` — 不可分发

---

## [S3] 数据结构

### 最近目标存储

在 `localStorage` 中存储最近使用的目标：

```javascript
// Key: toolbox-recent-targets
// Value: Array<{ cluster, namespace, pod, container, last_used }>
[
  {
    "cluster": "prod",
    "namespace": "default",
    "pod": "pod-a-7cc5f",
    "container": "app",
    "last_used": "2026-06-19T10:30:00Z"
  },
  // ... 最多 10 条
]
```

### Pod 能力检测

复用现有 API：
```
POST /api/tasks/detect-capability
{
  "cluster": "prod",
  "namespace": "default",
  "pod": "pod-a-7cc5f",
  "container": "app"
}
```

---

## [S4] 组件结构

### 新增组件

```
toolbox.js
├── openDistributeModal(toolId, toolType, defaultPath)  -- 打开分发 Modal
├── renderRecentTargets(toolId)                         -- 渲染快速选择
├── saveRecentTarget(target)                            -- 保存到最近使用
└── loadRecentTargets()                                 -- 加载最近使用
```

### Modal DOM 结构

```html
<div class="dist-modal-overlay" id="distModal-${toolId}">
  <div class="dist-modal">
    <div class="dist-modal-header">
      <h3>分发工具: ${toolName}</h3>
      <button class="btn-close" onclick="closeDistributeModal(${toolId})">✕</button>
    </div>
    
    <div class="dist-modal-body">
      <!-- 快速选择区域 -->
      <div class="dist-recent-section" id="distRecent-${toolId}">
        <div class="dist-section-title">⭐ 最近使用</div>
        <div class="dist-recent-list" id="distRecentList-${toolId}">
          <!-- 动态渲染 -->
        </div>
      </div>
      
      <div class="dist-divider">或手动选择目标</div>
      
      <!-- 手动选择表单 -->
      <div class="dist-form">
        <!-- 表单内容 -->
      </div>
    </div>
    
    <div class="dist-modal-footer">
      <button class="btn btn-g" onclick="closeDistributeModal(${toolId})">取消</button>
      <button class="btn btn-p" onclick="confirmDistribute(${toolId})">确认分发</button>
    </div>
  </div>
</div>
```

---

## [S5] CSS 样式

### Modal 样式

```css
.dist-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn .2s ease;
}

.dist-modal {
  width: 520px;
  max-height: 80vh;
  background: var(--bg2);
  border: 1px solid rgba(40,61,90,.6);
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
  display: flex;
  flex-direction: column;
  animation: slideUp .25s ease;
}

.dist-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(40,61,90,.4);
}

.dist-modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.dist-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid rgba(40,61,90,.4);
}
```

### 快速选择样式

```css
.dist-recent-section {
  margin-bottom: 16px;
}

.dist-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--tx2);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: .5px;
}

.dist-recent-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: rgba(0,0,0,.2);
  border: 1px solid rgba(40,61,90,.4);
  border-radius: 8px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all .15s;
}

.dist-recent-item:hover {
  border-color: rgba(0,122,255,.4);
  background: rgba(0,122,255,.05);
}

.dist-recent-target {
  font-size: 13px;
  color: var(--tx);
}

.dist-recent-target .ns {
  color: var(--tx2);
}

.dist-recent-select {
  font-size: 12px;
  color: var(--a);
  font-weight: 600;
}
```

---

## [S6] 实现要点

### 1. 替换内联表单为 Modal

- 删除 `toolboxSingleDistribute` 中的内联表单逻辑
- 新增 `openDistributeModal` 函数
- 修改卡片按钮的 `onclick` 调用

### 2. 实现快速选择

- `loadRecentTargets()` — 从 localStorage 加载
- `saveRecentTarget(target)` — 保存到 localStorage（去重，最多 10 条）
- `renderRecentTargets()` — 渲染快速选择列表

### 3. 优化级联选择

- 保持现有级联逻辑（集群 → Namespace → Pod）
- 选择 Pod 后调用 `detect-capability` API
- 显示能力状态标签

### 4. 分发成功后

- 保存目标到最近使用
- 关闭 Modal
- 显示成功 toast

---

## [S7] 测试用例

1. **快速选择** — 点击最近使用的目标，验证表单自动填充
2. **手动选择** — 从头选择集群/Namespace/Pod，验证级联加载
3. **能力检测** — 选择 Pod 后，验证能力状态显示
4. **分发执行** — 确认分发，验证进度显示和成功反馈
5. **最近使用** — 分发成功后，验证目标保存到快速选择列表
6. **Modal 关闭** — 点击取消/关闭按钮，验证 Modal 正确关闭

---

## [S8] 与现有设计的关系

本设计是 `2026-06-15-toolbox-redesign-design.md` 的**补充**，专注于单工具分发交互优化：

- **保留**：批量分发浮层设计不变
- **改进**：单工具分发从内联表单改为 Modal
- **新增**：快速选择（最近使用）功能
- **新增**：Pod 能力感知显示

---

## [S9] 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `static/js/components/toolbox.js` | 修改 | 新增 Modal 相关函数，替换内联表单逻辑 |
| `static/css/app.css` | 修改 | 新增 Modal 和快速选择样式 |
| `tests/test_toolbox.py` | 修改 | 新增 Modal 交互测试用例 |
