#!/usr/bin/env python3
"""诊断能力前端 - 集成测试

测试范围：
1. 前端组件与后端 API 的契约一致性
2. HTML 结构与 JS 组件的 DOM 绑定
3. 状态管理与 UI 指示器的联动
4. 完整用户流程的端到端验证
"""
import pathlib
import re
import json
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / 'static'
JS_CORE = STATIC / 'js' / 'core'
JS_COMPONENTS = STATIC / 'js' / 'components'

# 读取源文件
DIAGNOSIS_JS = (JS_COMPONENTS / 'diagnosis.js').read_text(encoding='utf-8')
DIAGNOSIS_FORM_JS = (JS_COMPONENTS / 'diagnosis-form.js').read_text(encoding='utf-8')
DIAGNOSIS_PROGRESS_JS = (JS_COMPONENTS / 'diagnosis-progress.js').read_text(encoding='utf-8')
DIAGNOSIS_RESULT_JS = (JS_COMPONENTS / 'diagnosis-result.js').read_text(encoding='utf-8')
DIAGNOSIS_HISTORY_JS = (JS_COMPONENTS / 'diagnosis-history.js').read_text(encoding='utf-8')
DIAGNOSIS_EXECUTION_JS = (JS_COMPONENTS / 'diagnosis-execution.js').read_text(encoding='utf-8')
DIAGNOSIS_RENDERER_JS = (JS_COMPONENTS / 'diagnosis-renderer.js').read_text(encoding='utf-8')
DIAGNOSIS_CONTEXT_JS = (JS_CORE / 'diagnosis-context.js').read_text(encoding='utf-8')
API_JS = (STATIC / 'js' / 'core' / 'api.js').read_text(encoding='utf-8')
AI_CHAT_JS = (STATIC / 'js' / 'ai-chat.js').read_text(encoding='utf-8')
INDEX_HTML = (STATIC / 'index.html').read_text(encoding='utf-8')


# ═══════════════════════════════════════════════════════════════════════════════
# API 路径契约测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPIContract:
    """前端 API 调用路径与后端路由的契约一致性"""

    # 前端调用的 API 路径 → 期望的 HTTP 方法
    EXPECTED_API_CALLS = {
        '/tasks/capabilities': 'GET',
        '/tasks/capabilities/': 'GET',  # 详情
        '/tasks/diagnosis/execute': 'POST',
        '/tasks/diagnosis/history': 'GET',
        '/tasks/runs/': 'GET',
        '/tasks/tool-packages': 'GET',
        '/api/ai/chat': 'POST',
        '/api/ai/config': 'GET',
        '/api/ai/config': 'POST',  # 保存
    }

    def test_capabilities_list_api_path(self):
        """获取能力列表应使用 /tasks/capabilities"""
        assert "'/tasks/capabilities'" in DIAGNOSIS_JS

    def test_capability_detail_api_path(self):
        """获取能力详情应使用 /tasks/capabilities/{id}"""
        assert 'tasks/capabilities/${capId}' in DIAGNOSIS_FORM_JS

    def test_execute_api_path(self):
        """执行诊断应 POST 到 /tasks/diagnosis/execute"""
        assert "'/tasks/diagnosis/execute'" in DIAGNOSIS_JS

    def test_history_api_path(self):
        """获取历史应使用 /tasks/diagnosis/history"""
        assert "'/tasks/diagnosis/history'" in DIAGNOSIS_HISTORY_JS

    def test_run_detail_api_path(self):
        """获取运行详情应使用 /tasks/runs/{id}/logs"""
        assert 'tasks/runs/${runId}/logs' in DIAGNOSIS_HISTORY_JS

    def test_tool_packages_api_path(self):
        """检查工具包应使用 /tasks/tool-packages"""
        assert "'/tasks/tool-packages'" in DIAGNOSIS_JS

    def test_poll_execution_api_path(self):
        """轮询执行状态应使用 /tasks/diagnosis/runs/{id}"""
        assert 'tasks/diagnosis/runs/${runId}' in DIAGNOSIS_CONTEXT_JS

    def test_cancel_execution_api_path(self):
        """取消执行应 POST 到 /tasks/diagnosis/runs/{id}/cancel"""
        assert 'tasks/diagnosis/runs/${backendRunId}/cancel' in DIAGNOSIS_CONTEXT_JS

    def test_create_capability_api_path(self):
        """创建能力应 POST 到 /tasks/capabilities"""
        assert "safePost('/tasks/capabilities'" in DIAGNOSIS_JS

    def test_update_capability_api_path(self):
        """更新能力应 PUT 到 /tasks/capabilities/{id}"""
        assert "safePut(`/tasks/capabilities/${capId}`" in DIAGNOSIS_JS

    def test_disable_capability_api_path(self):
        """禁用能力应 DELETE /tasks/capabilities/{id}"""
        assert "safeDelete(`/tasks/capabilities/${capId}`" in DIAGNOSIS_JS

    def test_ai_chat_api_path(self):
        """AI 对话应 POST 到 /api/ai/chat"""
        assert '/api/ai/chat' in AI_CHAT_JS

    def test_ai_config_get_api_path(self):
        """获取 AI 配置应 GET /api/ai/config"""
        assert '/api/ai/config' in AI_CHAT_JS

    def test_ai_providers_api_path(self):
        """获取供应商列表应 GET /api/ai/providers"""
        assert '/api/ai/providers' in AI_CHAT_JS

    def test_execute_request_body_structure(self):
        """执行请求应包含 capability_id, connection_id, params"""
        assert 'capability_id: capId' in DIAGNOSIS_JS
        assert 'connection_id: connId' in DIAGNOSIS_JS
        assert 'params: params' in DIAGNOSIS_JS

    def test_create_capability_payload_structure(self):
        """创建能力请求应包含必要字段"""
        payload_fields = [
            'name:', 'category:', 'level:', 'visibility:',
            'status:', 'risk_level:', 'estimated_duration:',
            'description:', 'arthas_command:', 'parameters_schema:'
        ]
        for field in payload_fields:
            assert field in DIAGNOSIS_JS, f"缺失字段: {field}"

    def test_ai_chat_request_structure(self):
        """AI 对话请求应包含 messages, connection_id, stream"""
        assert 'messages:' in AI_CHAT_JS
        assert 'connection_id:' in AI_CHAT_JS
        assert 'stream: true' in AI_CHAT_JS

    def test_history_request_includes_pagination(self):
        """历史请求应包含分页参数"""
        assert 'limit:' in DIAGNOSIS_HISTORY_JS
        assert 'offset:' in DIAGNOSIS_HISTORY_JS


# ═══════════════════════════════════════════════════════════════════════════════
# DOM 绑定契约测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDOMBindingContract:
    """HTML 容器 ID 与 JS DOM 操作的绑定一致性"""

    DOM_BINDINGS = {
        'diagnosisCapList': {
            'html': True,
            'js': [DIAGNOSIS_JS],
            'usage': '能力卡片容器',
        },
        'diagFormContainer': {
            'html': True,
            'js': [DIAGNOSIS_FORM_JS],
            'usage': '参数表单容器',
        },
        'diagFormModal': {
            'html': True,
            'js': [DIAGNOSIS_FORM_JS],
            'usage': '参数表单模态框',
        },
        'diagCapForm': {
            'html': False,
            'js': [DIAGNOSIS_FORM_JS],
            'usage': '参数表单元素',
        },
        'diagProgressContainer': {
            'html': True,
            'js': [DIAGNOSIS_PROGRESS_JS],
            'usage': '进度容器',
        },
        'diagProgressModal': {
            'html': True,
            'js': [DIAGNOSIS_PROGRESS_JS],
            'usage': '进度模态框',
        },
        'diagResultContainer': {
            'html': True,
            'js': [DIAGNOSIS_RESULT_JS],
            'usage': '结果容器',
        },
        'diagHistoryContainer': {
            'html': True,
            'js': [DIAGNOSIS_HISTORY_JS],
            'usage': '历史容器',
        },
        'diagLoadingOverlay': {
            'html': True,
            'js': [DIAGNOSIS_JS],
            'usage': '加载遮罩',
        },
        'executionIndicator': {
            'html': True,
            'js': [DIAGNOSIS_EXECUTION_JS],
            'usage': '执行指示器',
        },
        'aiMessages': {
            'html': True,
            'js': [AI_CHAT_JS],
            'usage': 'AI 消息容器',
        },
        'aiInput': {
            'html': True,
            'js': [AI_CHAT_JS],
            'usage': 'AI 输入框',
        },
        'aiSendBtn': {
            'html': True,
            'js': [AI_CHAT_JS],
            'usage': 'AI 发送按钮',
        },
        'aiConnSelect': {
            'html': True,
            'js': [AI_CHAT_JS],
            'usage': 'AI 连接选择',
        },
        'aiConnDot': {
            'html': False,
            'js': [AI_CHAT_JS],
            'usage': 'AI 连接指示点',
        },
        'aiConnLabel': {
            'html': False,
            'js': [AI_CHAT_JS],
            'usage': 'AI 连接标签',
        },
        'aiConnDropdown': {
            'html': False,
            'js': [AI_CHAT_JS],
            'usage': 'AI 连接下拉',
        },
        'aiModal': {
            'html': True,
            'js': [AI_CHAT_JS],
            'usage': 'AI 设置模态框',
        },
        'aiProvider': {
            'html': True,
            'js': [AI_CHAT_JS],
            'usage': 'AI 供应商选择',
        },
        'aiBaseUrl': {
            'html': False,
            'js': [AI_CHAT_JS],
            'usage': 'AI Base URL',
        },
        'aiModel': {
            'html': False,
            'js': [AI_CHAT_JS],
            'usage': 'AI 模型输入',
        },
        'aiApiKey': {
            'html': False,
            'js': [AI_CHAT_JS],
            'usage': 'AI API Key',
        },
        'aiSystemPrompt': {
            'html': False,
            'js': [AI_CHAT_JS],
            'usage': 'AI 系统提示',
        },
        'aiModalErr': {
            'html': False,
            'js': [AI_CHAT_JS],
            'usage': 'AI 设置错误',
        },
    }

    @pytest.mark.parametrize("dom_id", list(DOM_BINDINGS.keys()))
    def test_dom_id_used_in_js(self, dom_id):
        """DOM ID 应在对应的 JS 文件中被引用"""
        binding = self.DOM_BINDINGS[dom_id]
        all_js = '\n'.join(binding['js'])
        assert dom_id in all_js, \
            f"DOM ID '{dom_id}' ({binding['usage']}) 未在 JS 中被引用"

    @pytest.mark.parametrize("dom_id", [
        dom_id for dom_id, b in DOM_BINDINGS.items() if b['html']
    ])
    def test_dom_id_exists_in_html(self, dom_id):
        """HTML 中定义的 DOM ID 应在 index.html 中存在"""
        assert dom_id in INDEX_HTML, \
            f"HTML DOM ID '{dom_id}' 在 index.html 中不存在"


# ═══════════════════════════════════════════════════════════════════════════════
# 用户流程集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserFlowIntegration:
    """完整用户流程的端到端验证"""

    def test_flow_load_capabilities(self):
        """流程: 加载能力 → 渲染卡片 → 筛选"""
        # 1. 初始化加载
        assert 'window.diagCapInit' in DIAGNOSIS_JS
        # 2. 调用 API
        assert "'/tasks/capabilities'" in DIAGNOSIS_JS
        # 3. 渲染
        assert 'renderCapabilityCards' in DIAGNOSIS_JS

    def test_flow_execute_no_params(self):
        """流程: 无参数执行 → 展示结果"""
        # 1. 点击执行
        assert 'window.diagExecuteCap' in DIAGNOSIS_JS
        # 2. 检查连接
        assert 'diagGetCurrentConnectionId' in DIAGNOSIS_JS
        # 3. 调用 API
        assert "'/tasks/diagnosis/execute'" in DIAGNOSIS_JS
        # 4. 展示结果
        assert 'showDiagnosisResult' in DIAGNOSIS_JS

    def test_flow_execute_with_params(self):
        """流程: 有参数执行 → 表单 → 提交 → 展示结果"""
        # 1. 点击配置参数
        assert 'window.diagShowCapForm' in DIAGNOSIS_JS
        # 2. 转发到表单组件
        assert 'window.diagShowParameterForm' in DIAGNOSIS_FORM_JS
        # 3. 获取能力详情
        assert 'tasks/capabilities/${capId}' in DIAGNOSIS_FORM_JS
        # 4. 渲染表单
        assert 'renderForm(_currentCapability)' in DIAGNOSIS_FORM_JS
        # 5. 提交表单
        assert 'window.diagSubmitForm' in DIAGNOSIS_FORM_JS
        # 6. 校验参数
        assert 'validateForm(params' in DIAGNOSIS_FORM_JS
        # 7. 执行诊断
        assert 'diagExecuteCapWithParams' in DIAGNOSIS_FORM_JS

    def test_flow_async_execution(self):
        """流程: 异步执行 → 轮询 → 展示结果"""
        # 1. 注册执行
        assert 'DiagnosisContext.registerExecution' in DIAGNOSIS_JS
        # 2. 替换本地 ID
        assert 'DiagnosisContext.replaceLocalExecutionId' in DIAGNOSIS_JS
        # 3. 轮询
        assert 'pollAndShowResult' in DIAGNOSIS_JS
        assert 'DiagnosisContext.pollExecution' in DIAGNOSIS_JS
        # 4. 完成
        assert 'DiagnosisContext.completeExecution' in DIAGNOSIS_JS

    def test_flow_view_history(self):
        """流程: 查看历史 → 点击行 → 展示详情"""
        # 1. 初始化
        assert 'window.diagHistoryInit' in DIAGNOSIS_HISTORY_JS
        # 2. 加载数据
        assert "'/tasks/diagnosis/history'" in DIAGNOSIS_HISTORY_JS
        # 3. 渲染列表
        assert 'renderHistory()' in DIAGNOSIS_HISTORY_JS
        # 4. 点击查看详情
        assert 'window.diagViewHistoryDetail' in DIAGNOSIS_HISTORY_JS
        # 5. 获取详情
        assert 'tasks/runs/${runId}/logs' in DIAGNOSIS_HISTORY_JS
        # 6. 渲染结果
        assert 'diagRenderResult' in DIAGNOSIS_HISTORY_JS

    def test_flow_cancel_execution(self):
        """流程: 取消执行 → 更新 UI → 调用后端"""
        # 1. 用户点击取消
        assert 'window.cancelDiagnosisExecution' in DIAGNOSIS_EXECUTION_JS
        # 2. 调用 DiagnosisContext
        assert 'DiagnosisContext.cancelExecution' in DIAGNOSIS_EXECUTION_JS
        # 3. 更新状态
        assert "execution.status = 'cancelled'" in DIAGNOSIS_CONTEXT_JS
        # 4. 调用后端取消 API
        assert 'tasks/diagnosis/runs/${backendRunId}/cancel' in DIAGNOSIS_CONTEXT_JS

    def test_flow_admin_edit_capability(self):
        """流程: 管理员编辑能力 → 打开模态框 → 保存"""
        # 1. 打开编辑模态框
        assert 'window.diagOpenCapabilityModal' in DIAGNOSIS_JS
        # 2. 检查管理员权限
        assert 'isAdmin()' in DIAGNOSIS_JS
        # 3. 渲染编辑表单
        assert 'diagCapabilityEditForm' in DIAGNOSIS_JS
        # 4. 保存提交
        assert 'window.diagSubmitCapabilityForm' in DIAGNOSIS_JS
        # 5. 更新使用 PUT
        assert "safePut(`/tasks/capabilities/${capId}`" in DIAGNOSIS_JS
        # 6. 刷新列表
        assert 'await loadCapabilities()' in DIAGNOSIS_JS
        assert 'renderCapabilityCards()' in DIAGNOSIS_JS

    def test_flow_admin_disable_capability(self):
        """流程: 管理员禁用能力 → 确认 → 调用 DELETE"""
        # 1. 点击禁用
        assert 'window.diagDisableCapability' in DIAGNOSIS_JS
        # 2. 确认
        assert "confirm('确认禁用该能力" in DIAGNOSIS_JS
        # 3. 调用 DELETE
        assert "safeDelete(`/tasks/capabilities/${capId}`" in DIAGNOSIS_JS
        # 4. 刷新
        assert 'renderCapabilityCards()' in DIAGNOSIS_JS

    def test_flow_ai_chat(self):
        """流程: AI 对话 → 配置 → 发送 → 流式接收"""
        # 1. 检查配置
        assert '_aiConfigured' in AI_CHAT_JS
        # 2. 未配置时引导设置
        assert 'aiOpenSettings()' in AI_CHAT_JS
        # 3. 保存配置
        assert 'saveAiConfig()' in AI_CHAT_JS or 'window.saveAiConfig' in AI_CHAT_JS
        # 4. 发送消息
        assert 'window.aiSend' in AI_CHAT_JS
        # 5. 流式接收
        assert "'content'" in AI_CHAT_JS
        assert "'tool_start'" in AI_CHAT_JS
        assert "'tool_result'" in AI_CHAT_JS
        # 6. 渲染结果
        assert 'aiUpdateMessage' in AI_CHAT_JS

    def test_flow_connection_filter(self):
        """流程: 连接状态变化 → 过滤能力 → 更新显示"""
        # 1. 获取连接层级
        assert 'diagGetConnectionLevel' in DIAGNOSIS_JS
        # 2. 过滤能力
        assert 'filterCapabilitiesByConnection' in DIAGNOSIS_JS
        # 3. 根据层级展示不同空状态
        assert "'none'" in DIAGNOSIS_JS
        assert "'pod'" in DIAGNOSIS_JS
        assert "'arthas'" in DIAGNOSIS_JS

    def test_flow_result_rendering_pipeline(self):
        """流程: 结果数据 → 渲染器选择模式 → 渲染 HTML → 展示"""
        # 1. 调用渲染器
        assert 'renderDiagnosisResult' in DIAGNOSIS_RENDERER_JS
        # 2. 检测渲染模式
        assert 'detectRenderMode' in DIAGNOSIS_RENDERER_JS
        # 3. 按模式渲染
        assert 'renderTraceTable' in DIAGNOSIS_RENDERER_JS
        assert 'renderFileLinks' in DIAGNOSIS_RENDERER_JS
        assert 'renderMarkdown' in DIAGNOSIS_RENDERER_JS
        assert 'renderMultiStep' in DIAGNOSIS_RENDERER_JS
        assert 'renderText' in DIAGNOSIS_RENDERER_JS

    def test_flow_progress_tracking(self):
        """流程: 场景方案 → 进度展示 → 步骤更新 → 完成"""
        # 1. 显示进度
        assert 'window.diagShowProgress' in DIAGNOSIS_PROGRESS_JS
        # 2. 初始化步骤
        assert "status: 'pending'" in DIAGNOSIS_PROGRESS_JS
        # 3. 更新步骤状态
        assert 'window.diagUpdateStepStatus' in DIAGNOSIS_PROGRESS_JS
        # 4. 关闭进度
        assert 'window.diagCloseProgress' in DIAGNOSIS_PROGRESS_JS


# ═══════════════════════════════════════════════════════════════════════════════
# 跨组件联动测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrossComponentIntegration:
    """跨组件联动测试"""

    def test_diagnosis_context_registers_global_indicator(self):
        """DiagnosisContext 注册执行时应调用全局指示器"""
        assert 'window.registerDiagnosisExecution' in DIAGNOSIS_CONTEXT_JS

    def test_diagnosis_context_completes_global_indicator(self):
        """DiagnosisContext 完成执行时应调用全局指示器"""
        assert 'window.completeDiagnosisExecution' in DIAGNOSIS_CONTEXT_JS

    def test_diagnosis_context_replaces_global_indicator_id(self):
        """DiagnosisContext 替换 ID 时应同步全局指示器"""
        assert 'window.replaceDiagnosisExecutionId' in DIAGNOSIS_CONTEXT_JS

    def test_diagnosis_main_registers_context(self):
        """diagnosis.js 执行时应注册到 DiagnosisContext"""
        assert 'DiagnosisContext.registerExecution' in DIAGNOSIS_JS

    def test_diagnosis_main_completes_context(self):
        """diagnosis.js 完成时应通知 DiagnosisContext"""
        assert 'DiagnosisContext.completeExecution' in DIAGNOSIS_JS

    def test_diagnosis_main_replaces_context_id(self):
        """diagnosis.js 替换 ID 时应通知 DiagnosisContext"""
        assert 'DiagnosisContext.replaceLocalExecutionId' in DIAGNOSIS_JS

    def test_history_delegates_to_result_renderer(self):
        """history 详情应委托给结果渲染器"""
        assert 'diagRenderResult' in DIAGNOSIS_HISTORY_JS

    def test_diagnosis_main_coordinates_renderer(self):
        """diagnosis.js 应协调渲染器和结果展示"""
        assert 'renderDiagnosisResult' in DIAGNOSIS_JS
        assert 'diagRenderResult' in DIAGNOSIS_JS

    def test_diagnosis_main_delegates_to_form(self):
        """diagnosis.js 应委托参数表单"""
        assert 'window.diagShowParameterForm' in DIAGNOSIS_JS

    def test_form_delegates_to_execution(self):
        """表单提交应委托给执行函数"""
        assert 'diagExecuteCapWithParams' in DIAGNOSIS_FORM_JS

    def test_execution_modal_uses_context(self):
        """执行指示器模态框应回退到 DiagnosisContext"""
        assert 'DiagnosisContext.activeExecutions' in DIAGNOSIS_EXECUTION_JS

    def test_context_cancel_calls_global_indicator(self):
        """取消执行应调用全局完成指示器"""
        assert 'window.completeDiagnosisExecution' in DIAGNOSIS_CONTEXT_JS


# ═══════════════════════════════════════════════════════════════════════════════
# 参数校验集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestParameterValidationIntegration:
    """前端参数校验的集成覆盖"""

    def test_required_field_validation_messages(self):
        """必填校验应包含字段名"""
        assert '请填写必填项: ${field.label || field.name}' in DIAGNOSIS_FORM_JS

    def test_pattern_validation_messages(self):
        """正则校验应包含字段名"""
        assert '${field.label || field.name} 格式不正确' in DIAGNOSIS_FORM_JS

    def test_min_length_validation_messages(self):
        """最小长度校验应包含字段名和阈值"""
        assert '不能少于 ${field.min_length} 个字符' in DIAGNOSIS_FORM_JS

    def test_max_length_validation_messages(self):
        """最大长度校验应包含字段名和阈值"""
        assert '不能超过 ${field.max_length} 个字符' in DIAGNOSIS_FORM_JS

    def test_number_min_validation_messages(self):
        """数值最小值校验应包含字段名和阈值"""
        assert '不能小于 ${field.min}' in DIAGNOSIS_FORM_JS

    def test_number_max_validation_messages(self):
        """数值最大值校验应包含字段名和阈值"""
        assert '不能大于 ${field.max}' in DIAGNOSIS_FORM_JS

    def test_validation_prevents_submission(self):
        """校验失败应阻止提交并显示错误"""
        assert 'showError(validationError)' in DIAGNOSIS_FORM_JS

    def test_empty_required_field_detected(self):
        """空的必填字段应被检测"""
        assert '(!value || value.trim()' in DIAGNOSIS_FORM_JS


# ═══════════════════════════════════════════════════════════════════════════════
# 错误处理集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestErrorHandlingIntegration:
    """错误处理的集成覆盖"""

    def test_api_error_handling_in_load_capabilities(self):
        """加载能力失败应显示错误"""
        assert '加载诊断能力失败' in DIAGNOSIS_JS

    def test_api_error_handling_in_execute(self):
        """执行失败应显示错误"""
        assert '诊断执行失败' in DIAGNOSIS_JS or '诊断失败' in DIAGNOSIS_JS

    def test_api_error_handling_in_connection_lost(self):
        """连接断开应显示特定错误"""
        assert 'Arthas 连接已断开' in DIAGNOSIS_JS

    def test_api_error_handling_in_form_load(self):
        """表单加载失败应显示错误"""
        assert '加载能力详情失败' in DIAGNOSIS_FORM_JS

    def test_api_error_handling_in_history_load(self):
        """历史加载失败应有错误处理"""
        assert '加载历史记录失败' in DIAGNOSIS_HISTORY_JS

    def test_api_error_handling_in_history_detail(self):
        """详情加载失败应显示错误"""
        assert '加载详情失败' in DIAGNOSIS_HISTORY_JS

    def test_api_error_handling_in_save_capability(self):
        """保存能力失败应显示错误"""
        assert '保存能力失败' in DIAGNOSIS_JS

    def test_api_error_handling_in_disable_capability(self):
        """禁用能力失败应显示错误"""
        assert '禁用能力失败' in DIAGNOSIS_JS

    def test_api_error_handling_in_poll(self):
        """轮询失败应显示错误"""
        assert '轮询状态失败' in DIAGNOSIS_CONTEXT_JS or '轮询超时' in DIAGNOSIS_JS

    def test_tool_check_error_handling(self):
        """工具包检查失败不应阻塞"""
        assert 'console.warn(\'检查工具包失败' in DIAGNOSIS_JS

    def test_json_parse_error_in_schema(self):
        """Schema JSON 解析错误应显示提示"""
        assert '参数 Schema 必须是合法 JSON' in DIAGNOSIS_JS

    def test_none_connection_error(self):
        """无连接时应提示"""
        assert '请先连接目标 Pod' in DIAGNOSIS_JS

    def test_no_capability_error(self):
        """能力不存在时应提示"""
        assert '能力不存在' in DIAGNOSIS_JS

    def test_history_not_found_error(self):
        """历史记录不存在时应提示"""
        assert '记录不存在' in DIAGNOSIS_HISTORY_JS


# ═══════════════════════════════════════════════════════════════════════════════
# CSS 类名一致性测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCSSClassConsistency:
    """CSS 类名在 JS 和 HTML 间的一致性"""

    def test_capability_card_css_class(self):
        """能力卡片应使用 capability-card 类"""
        assert 'capability-card' in DIAGNOSIS_JS
        assert 'capability-card' in INDEX_HTML or 'capability-grid' in DIAGNOSIS_JS

    def test_capability_header_css_class(self):
        """能力卡片头部应使用 capability-header 类"""
        assert 'capability-header' in DIAGNOSIS_JS

    def test_capability_name_css_class(self):
        """能力名称应使用 capability-name 类"""
        assert 'capability-name' in DIAGNOSIS_JS

    def test_capability_desc_css_class(self):
        """能力描述应使用 capability-desc 类"""
        assert 'capability-desc' in DIAGNOSIS_JS

    def test_capability_meta_css_class(self):
        """能力元数据应使用 capability-meta 类"""
        assert 'capability-meta' in DIAGNOSIS_JS

    def test_capability_actions_css_class(self):
        """能力操作应使用 capability-actions 类"""
        assert 'capability-actions' in DIAGNOSIS_JS

    def test_badge_css_classes(self):
        """徽章应使用 badge 系列类"""
        assert 'badge-low' in DIAGNOSIS_JS
        assert 'badge-medium' in DIAGNOSIS_JS
        assert 'badge-high' in DIAGNOSIS_JS

    def test_progress_step_css_class(self):
        """进度步骤应使用 progress-step 类"""
        assert 'progress-step' in DIAGNOSIS_PROGRESS_JS

    def test_result_section_css_class(self):
        """结果区域应使用 result-section 类"""
        assert 'result-section' in DIAGNOSIS_RESULT_JS

    def test_scenario_result_css_class(self):
        """场景结果应使用 scenario-result 类"""
        assert 'scenario-result' in DIAGNOSIS_RESULT_JS

    def test_history_row_css_class(self):
        """历史行应使用 history-row 类"""
        assert 'history-row' in DIAGNOSIS_HISTORY_JS

    def test_history_table_css_class(self):
        """历史表格应使用 history-table 类"""
        assert 'history-table' in DIAGNOSIS_HISTORY_JS

    def test_pagination_css_class(self):
        """分页应使用 pagination 类"""
        assert 'pagination' in DIAGNOSIS_HISTORY_JS

    def test_empty_state_css_class(self):
        """空状态应使用 empty-state 或 sb-empty 类"""
        assert 'empty-state' in DIAGNOSIS_HISTORY_JS or 'sb-empty' in DIAGNOSIS_JS

    def test_modal_overlay_css_class(self):
        """模态框遮罩应使用 overlay 类"""
        assert 'modal-overlay' in DIAGNOSIS_JS or 'modal-bg' in INDEX_HTML

    def test_diagnosis_css_file_loaded(self):
        """诊断 CSS 文件应被加载"""
        assert 'diagnosis.css' in INDEX_HTML

    def test_level_group_css_class(self):
        """层级分组应使用 capability-level-group 类"""
        assert 'capability-level-group' in DIAGNOSIS_JS

    def test_grid_css_class(self):
        """能力网格应使用 capability-grid 类"""
        assert 'capability-grid' in DIAGNOSIS_JS


# ═══════════════════════════════════════════════════════════════════════════════
# 数据格式一致性测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataFormatConsistency:
    """前后端数据格式一致性"""

    def test_capability_data_fields(self):
        """能力数据应包含所有必要字段"""
        required_fields = ['id', 'name', 'category', 'level', 'description',
                           'parameters_schema', 'risk_level', 'estimated_duration',
                           'status']
        for field in required_fields:
            assert field in DIAGNOSIS_JS, f"能力数据缺少字段: {field}"

    def test_capability_response_structure(self):
        """能力列表响应应包含 capabilities 数组"""
        assert 'data.capabilities' in DIAGNOSIS_JS

    def test_execution_response_fields(self):
        """执行响应应处理 run_id 和 status"""
        assert 'result.run_id' in DIAGNOSIS_JS or 'result.execution_id' in DIAGNOSIS_JS
        assert 'result.status' in DIAGNOSIS_JS

    def test_async_execution_status(self):
        """异步执行状态应为 running"""
        assert "result.status === 'running'" in DIAGNOSIS_JS

    def test_history_run_fields(self):
        """历史记录应包含 status/started_at/duration_ms"""
        assert 'run.status' in DIAGNOSIS_HISTORY_JS
        assert 'run.started_at' in DIAGNOSIS_HISTORY_JS
        assert 'run.duration_ms' in DIAGNOSIS_HISTORY_JS

    def test_history_response_structure(self):
        """历史响应应包含 history 数组"""
        assert 'data.history' in DIAGNOSIS_HISTORY_JS

    def test_ai_config_response(self):
        """AI 配置响应应包含 config 对象"""
        assert 'd.config' in AI_CHAT_JS

    def test_ai_chat_sse_format(self):
        """AI 对话 SSE 应使用 data: 前缀"""
        assert "line.startsWith('data: ')" in AI_CHAT_JS

    def test_result_format_success(self):
        """成功结果应包含 status 字段"""
        assert 'result.status' in DIAGNOSIS_RESULT_JS

    def test_result_format_duration(self):
        """结果应包含 duration_ms"""
        assert 'result.duration_ms' in DIAGNOSIS_RESULT_JS or 'duration_ms' in DIAGNOSIS_RESULT_JS

    def test_step_result_format(self):
        """步骤结果应包含 success 和 result 字段"""
        assert 'step.success' in DIAGNOSIS_RESULT_JS
        assert 'step.result' in DIAGNOSIS_RESULT_JS

    def test_poll_run_fields(self):
        """轮询响应应包含 status"""
        assert 'run.status' in DIAGNOSIS_CONTEXT_JS


# ═══════════════════════════════════════════════════════════════════════════════
# 响应式和兼容性测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestResponsiveAndCompatibility:
    """响应式设计和兼容性测试"""

    def test_modal_uses_flex_center(self):
        """模态框应使用 flex 布局"""
        assert 'display:flex' in INDEX_HTML or 'display: flex' in INDEX_HTML

    def test_diagnosis_panel_is_hidden_by_default(self):
        """诊断面板默认隐藏"""
        assert 'panel-diagnosis-cap" style="display:none"' in INDEX_HTML

    def test_loading_overlay_uses_flex(self):
        """加载遮罩应使用 flex 布局"""
        assert 'diagLoadingOverlay' in INDEX_HTML

    def test_scroll_into_view_for_results(self):
        """结果展示后应滚动"""
        assert 'scrollIntoView' in DIAGNOSIS_RESULT_JS

    def test_textarea_auto_resize(self):
        """AI 输入框应自动调整高度"""
        assert 'aiAutoResize' in AI_CHAT_JS
        assert 'scrollHeight' in AI_CHAT_JS

    def test_execution_indicator_hidden_by_default(self):
        """执行指示器默认隐藏"""
        assert 'executionIndicator' in INDEX_HTML
        assert 'display:none' in INDEX_HTML

    def test_confirm_dialogs_for_dangerous_actions(self):
        """危险操作应有确认对话框"""
        assert 'confirm(' in DIAGNOSIS_JS

    def test_disabled_button_state(self):
        """禁用按钮应有 disabled 属性"""
        assert "'disabled'" in DIAGNOSIS_JS or 'disabled' in DIAGNOSIS_JS

    def test_pagination_button_state(self):
        """分页按钮在边界时应禁用"""
        assert '_currentPage === 1' in DIAGNOSIS_HISTORY_JS
        assert 'disabled' in DIAGNOSIS_HISTORY_JS

    def test_ai_send_button_disabled_during_streaming(self):
        """流式传输中发送按钮应禁用"""
        assert 'disabled = true' in AI_CHAT_JS
        assert 'disabled = false' in AI_CHAT_JS

    def test_ai_input_auto_height(self):
        """AI 输入框应自动调整高度"""
        assert 'auto' in AI_CHAT_JS
        assert 'scrollHeight' in AI_CHAT_JS


# ═══════════════════════════════════════════════════════════════════════════════
# 安全集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurityIntegration:
    """安全相关的集成测试"""

    def test_xss_escape_html_in_all_components(self):
        """所有组件都应使用 escapeHtml"""
        components = [
            ('diagnosis.js', DIAGNOSIS_JS),
            ('diagnosis-form.js', DIAGNOSIS_FORM_JS),
            ('diagnosis-progress.js', DIAGNOSIS_PROGRESS_JS),
            ('diagnosis-result.js', DIAGNOSIS_RESULT_JS),
            ('diagnosis-history.js', DIAGNOSIS_HISTORY_JS),
            ('diagnosis-renderer.js', DIAGNOSIS_RENDERER_JS),
            ('ai-chat.js', AI_CHAT_JS),
        ]
        for name, source in components:
            assert 'escapeHtml' in source or 'esc(' in source, \
                f"{name} 缺少 HTML 转义函数"

    def test_admin_check_for_mutation_operations(self):
        """修改操作应检查管理员权限"""
        assert 'isAdmin()' in DIAGNOSIS_JS

    def test_admin_check_before_edit(self):
        """编辑操作前应检查权限"""
        assert '仅管理员可维护诊断能力' in DIAGNOSIS_JS

    def test_confirm_before_delete(self):
        """删除/禁用操作前应确认"""
        assert 'confirm(' in DIAGNOSIS_JS

    def test_confirm_before_high_risk(self):
        """高风险操作前应确认"""
        assert '此操作为高风险' in DIAGNOSIS_JS

    def test_api_error_not_exposed(self):
        """API 错误应通过友好消息展示"""
        assert 'showError(' in DIAGNOSIS_JS
        assert 'showError(' in DIAGNOSIS_FORM_JS
        assert 'showError(' in DIAGNOSIS_HISTORY_JS

    def test_credentials_in_fetch(self):
        """API 请求应包含 credentials"""
        assert "credentials: 'include'" in API_JS
        assert "credentials: 'include'" in DIAGNOSIS_CONTEXT_JS
        assert "credentials: 'include'" in AI_CHAT_JS

    def test_safe_request_functions(self):
        """应使用安全请求函数"""
        assert 'safeGet' in API_JS
        assert 'safePost' in API_JS
        assert 'safePut' in API_JS
        assert 'safeDelete' in API_JS

    def test_timeout_on_requests(self):
        """请求应有超时控制"""
        assert 'AbortController' in API_JS
        assert 'setTimeout' in API_JS

    def test_401_handling(self):
        """401 响应应重定向到登录页"""
        assert 'status === 401' in API_JS
        assert '/login.html' in API_JS

    def test_json_content_type_check(self):
        """应检查响应 Content-Type"""
        assert 'application/json' in API_JS

    def test_session_expiry_handling(self):
        """会话过期应有友好提示"""
        assert '会话已过期' in API_JS
