#!/usr/bin/env python3
"""诊断能力前端组件 - 单元测试

测试范围：
1. 静态 HTML 文件的结构正确性
2. JavaScript 组件的 API 完整性
3. CSS 样式的引用完整性
4. 模块间依赖的正确性
5. 前端路由/URL 约定的正确性
"""
import os
import re
import sys
import pathlib
import json

import pytest

# 项目根目录
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / 'static'
JS_DIR = STATIC_DIR / 'js'
COMPONENTS_DIR = JS_DIR / 'components'


# ═══════════════════════════════════════════════════════════════════════════════
# HTML 文件测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiagnosisCenterHtml:
    """诊断中心 HTML 页面测试"""

    def test_html_exists(self):
        """诊断中心页面存在"""
        html_path = STATIC_DIR / 'diagnosis-center.html'
        assert html_path.exists(), f'文件不存在: {html_path}'

    def test_html_has_doctype(self):
        """HTML 包含 DOCTYPE"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert '<!DOCTYPE html>' in content

    def test_html_has_lang_attr(self):
        """HTML 包含 lang 属性"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'lang="zh-CN"' in content

    def test_html_has_meta_charset(self):
        """HTML 包含 charset meta"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'charset="UTF-8"' in content

    def test_html_references_app_css(self):
        """引用 app.css"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'app.css' in content

    def test_html_references_diagnosis_css(self):
        """引用 diagnosis.css"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'diagnosis.css' in content

    def test_html_references_api_js(self):
        """引用 api.js"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'api.js' in content

    def test_html_references_utils_js(self):
        """引用 utils.js"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'utils.js' in content

    def test_html_references_diagnosis_center_js(self):
        """引用 diagnosis-center.js"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'diagnosis-center.js' in content

    def test_html_references_parameter_form_js(self):
        """引用 parameter-form.js"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'parameter-form.js' in content

    def test_html_references_execution_progress_js(self):
        """引用 execution-progress.js"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'execution-progress.js' in content

    def test_html_references_execution_history_js(self):
        """引用 execution-history.js"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'execution-history.js' in content

    def test_html_references_diagnosis_report_js(self):
        """引用 diagnosis-report.js"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'diagnosis-report.js' in content

    def test_html_references_agent_chat_js(self):
        """引用 agent-chat.js"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'agent-chat.js' in content

    def test_html_has_capability_grid_container(self):
        """包含能力卡片网格容器"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'dcCapabilityGrid' in content

    def test_html_has_tab_panels(self):
        """包含三个 Tab 面板"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'dc-panel-capabilities' in content
        assert 'dc-panel-history' in content
        assert 'dc-panel-chat' in content

    def test_html_has_search_input(self):
        """包含搜索输入框"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'dcSearchInput' in content

    def test_html_has_filter_buttons(self):
        """包含层级筛选按钮"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'dc-filter-btn' in content

    def test_html_has_loading_overlay(self):
        """包含加载遮罩"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'diagLoadingOverlay' in content

    def test_html_has_form_modal(self):
        """包含参数表单弹窗"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'diagFormModal' in content

    def test_html_has_progress_modal(self):
        """包含进度弹窗"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'diagProgressModal' in content

    def test_html_has_chat_input(self):
        """包含 Agent 对话输入"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'dcChatInput' in content

    def test_html_has_chat_messages(self):
        """包含消息容器"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'dcChatMessages' in content

    def test_html_has_quick_actions(self):
        """包含快捷问题按钮"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')
        assert 'dcAgentQuickAsk' in content


# ═══════════════════════════════════════════════════════════════════════════════
# JavaScript 文件测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestJavaScriptFiles:
    """JavaScript 文件存在性和结构测试"""

    ALL_COMPONENTS = [
        'diagnosis-center.js',
        'parameter-form.js',
        'execution-progress.js',
        'execution-history.js',
        'diagnosis-report.js',
        'agent-chat.js',
    ]

    def test_all_component_files_exist(self):
        """所有组件文件存在"""
        for name in self.ALL_COMPONENTS:
            path = COMPONENTS_DIR / name
            assert path.exists(), f'组件文件不存在: {path}'

    def test_all_files_non_empty(self):
        """所有组件文件非空"""
        for name in self.ALL_COMPONENTS:
            path = COMPONENTS_DIR / name
            content = path.read_text(encoding='utf-8')
            assert len(content) > 100, f'文件内容过短: {name} ({len(content)} chars)'

    def test_all_files_use_strict_mode(self):
        """所有组件使用严格模式"""
        for name in self.ALL_COMPONENTS:
            path = COMPONENTS_DIR / name
            content = path.read_text(encoding='utf-8')
            assert "'use strict'" in content, f'文件未使用严格模式: {name}'

    def test_all_files_use_iife(self):
        """所有组件使用 IIFE 封装"""
        for name in self.ALL_COMPONENTS:
            path = COMPONENTS_DIR / name
            content = path.read_text(encoding='utf-8')
            assert '(function()' in content or '(function ()' in content, f'文件未使用 IIFE: {name}'


class TestDiagnosisCenterJs:
    """diagnosis-center.js 组件测试"""

    def _read(self):
        return (COMPONENTS_DIR / 'diagnosis-center.js').read_text(encoding='utf-8')

    def test_has_dc_init(self):
        """导出 dcInit 初始化函数"""
        content = self._read()
        assert 'window.dcInit' in content

    def test_has_dc_switch_tab(self):
        """导出 dcSwitchTab 函数"""
        content = self._read()
        assert 'window.dcSwitchTab' in content

    def test_has_dc_on_search(self):
        """导出 dcOnSearch 搜索函数"""
        content = self._read()
        assert 'window.dcOnSearch' in content

    def test_has_dc_filter_by_level(self):
        """导出 dcFilterByLevel 筛选函数"""
        content = self._read()
        assert 'window.dcFilterByLevel' in content

    def test_has_dc_execute(self):
        """导出 dcExecute 执行函数"""
        content = self._read()
        assert 'window.dcExecute' in content

    def test_has_dc_open_form(self):
        """导出 dcOpenForm 打开表单函数"""
        content = self._read()
        assert 'window.dcOpenForm' in content

    def test_has_dc_show_error(self):
        """导出 dcShowError 错误提示函数"""
        content = self._read()
        assert 'window.dcShowError' in content

    def test_has_dc_show_success(self):
        """导出 dcShowSuccess 成功提示函数"""
        content = self._read()
        assert 'window.dcShowSuccess' in content

    def test_has_dc_show_loading(self):
        """导出 dcShowLoading 加载提示函数"""
        content = self._read()
        assert 'window.dcShowLoading' in content

    def test_has_dc_hide_loading(self):
        """导出 dcHideLoading 隐藏加载函数"""
        content = self._read()
        assert 'window.dcHideLoading' in content

    def test_has_dc_load_history(self):
        """导出 dcLoadHistory 历史加载函数"""
        content = self._read()
        assert 'window.dcLoadHistory' in content

    def test_has_dc_view_history_detail(self):
        """导出 dcViewHistoryDetail 函数"""
        content = self._read()
        assert 'window.dcViewHistoryDetail' in content

    def test_has_dc_back_to_main(self):
        """导出 dcBackToMain 返回函数"""
        content = self._read()
        assert 'window.dcBackToMain' in content

    def test_references_safe_get(self):
        """使用 safeGet API"""
        content = self._read()
        assert 'safeGet' in content

    def test_references_safe_post(self):
        """使用 safePost API"""
        content = self._read()
        assert 'safePost' in content

    def test_references_debounce(self):
        """使用 debounce 工具函数"""
        content = self._read()
        assert 'debounce' in content

    def test_uses_capability_grid(self):
        """渲染到能力卡片网格容器"""
        content = self._read()
        assert 'dcCapabilityGrid' in content

    def test_uses_filter_level(self):
        """支持层级筛选"""
        content = self._read()
        assert '_currentLevel' in content

    def test_uses_search_text(self):
        """支持搜索"""
        content = self._read()
        assert '_searchText' in content

    def test_has_risk_badge_logic(self):
        """包含风险等级徽章逻辑"""
        content = self._read()
        assert 'badge-low' in content or 'badge-high' in content

    def test_has_category_label_logic(self):
        """包含分类标签逻辑"""
        content = self._read()
        assert 'getCategoryLabel' in content or '_getCategoryLabel' in content

    def test_has_empty_state(self):
        """包含空状态渲染"""
        content = self._read()
        assert '暂无' in content or 'empty' in content.lower()

    def test_has_dom_content_loaded(self):
        """在 DOMContentLoaded 后初始化"""
        content = self._read()
        assert 'DOMContentLoaded' in content


class TestParameterFormJs:
    """parameter-form.js 组件测试"""

    def _read(self):
        return (COMPONENTS_DIR / 'parameter-form.js').read_text(encoding='utf-8')

    def test_has_param_form_open(self):
        """导出 paramFormOpen"""
        content = self._read()
        assert 'window.paramFormOpen' in content

    def test_has_param_form_close(self):
        """导出 paramFormClose"""
        content = self._read()
        assert 'window.paramFormClose' in content

    def test_has_param_form_submit(self):
        """导出 paramFormSubmit"""
        content = self._read()
        assert 'window.paramFormSubmit' in content

    def test_has_param_form_open_by_id(self):
        """导出 paramFormOpenById"""
        content = self._read()
        assert 'window.paramFormOpenById' in content

    def test_supports_text_type(self):
        """支持 text 类型字段（通过 default 分支）"""
        content = self._read()
        assert "case 'text'" in content or "type === 'text'" in content or 'default: // text' in content

    def test_supports_number_type(self):
        """支持 number 类型字段"""
        content = self._read()
        assert "case 'number'" in content or "type === 'number'" in content

    def test_supports_select_type(self):
        """支持 select 类型字段"""
        content = self._read()
        assert "case 'select'" in content or "type === 'select'" in content

    def test_supports_textarea_type(self):
        """支持 textarea 类型字段"""
        content = self._read()
        assert "case 'textarea'" in content or "type === 'textarea'" in content

    def test_supports_boolean_type(self):
        """支持 boolean 类型字段"""
        content = self._read()
        assert "case 'boolean'" in content or "type === 'boolean'" in content

    def test_supports_password_type(self):
        """支持 password 类型字段"""
        content = self._read()
        assert "case 'password'" in content or "type === 'password'" in content

    def test_has_required_validation(self):
        """包含必填项校验"""
        content = self._read()
        assert 'required' in content

    def test_has_pattern_validation(self):
        """包含正则校验"""
        content = self._read()
        assert 'pattern' in content

    def test_has_min_max_validation(self):
        """包含范围校验"""
        content = self._read()
        assert 'min_length' in content or 'min' in content

    def test_has_schema_parsing(self):
        """包含 schema 解析逻辑"""
        content = self._read()
        assert 'parseSchema' in content or '_parseSchema' in content

    def test_uses_safe_get(self):
        """使用 safeGet 获取能力详情"""
        content = self._read()
        assert 'safeGet' in content

    def test_has_modal_control(self):
        """包含模态框控制"""
        content = self._read()
        assert 'diagFormModal' in content


class TestExecutionProgressJs:
    """execution-progress.js 组件测试"""

    def _read(self):
        return (COMPONENTS_DIR / 'execution-progress.js').read_text(encoding='utf-8')

    def test_has_exec_progress_start(self):
        """导出 execProgressStart"""
        content = self._read()
        assert 'window.execProgressStart' in content

    def test_has_exec_progress_cancel(self):
        """导出 execProgressCancel"""
        content = self._read()
        assert 'window.execProgressCancel' in content

    def test_has_exec_progress_close(self):
        """导出 execProgressClose"""
        content = self._read()
        assert 'window.execProgressClose' in content

    def test_has_exec_progress_update_step(self):
        """导出 execProgressUpdateStep"""
        content = self._read()
        assert 'window.execProgressUpdateStep' in content

    def test_has_polling_logic(self):
        """包含轮询逻辑"""
        content = self._read()
        assert 'setInterval' in content or '_startPolling' in content

    def test_has_poll_interval(self):
        """包含轮询间隔"""
        content = self._read()
        assert 'POLL_INTERVAL' in content or 'pollTimer' in content

    def test_has_max_poll_attempts(self):
        """包含最大轮询次数"""
        content = self._read()
        assert 'MAX_POLL' in content or '_MAX_POLL' in content

    def test_has_status_rendering(self):
        """包含各状态的渲染"""
        content = self._read()
        assert 'completed' in content
        assert 'failed' in content
        assert 'cancelled' in content

    def test_has_spinner_animation(self):
        """包含加载动画"""
        content = self._read()
        assert 'spinner' in content or 'spin' in content

    def test_uses_safe_get(self):
        """使用 safeGet 轮询"""
        content = self._read()
        assert 'safeGet' in content

    def test_uses_safe_post(self):
        """使用 safePost 取消"""
        content = self._read()
        assert 'safePost' in content

    def test_has_on_complete_callback(self):
        """支持完成回调"""
        content = self._read()
        assert '_onComplete' in content or 'onComplete' in content


class TestExecutionHistoryJs:
    """execution-history.js 组件测试"""

    def _read(self):
        return (COMPONENTS_DIR / 'execution-history.js').read_text(encoding='utf-8')

    def test_has_diag_history_init(self):
        """导出 diagHistoryInit"""
        content = self._read()
        assert 'window.diagHistoryInit' in content

    def test_has_diag_history_refresh(self):
        """导出 diagHistoryRefresh"""
        content = self._read()
        assert 'window.diagHistoryRefresh' in content

    def test_has_diag_history_filter(self):
        """导出 diagHistoryFilter"""
        content = self._read()
        assert 'window.diagHistoryFilter' in content

    def test_has_diag_history_search(self):
        """导出 diagHistorySearch"""
        content = self._read()
        assert 'window.diagHistorySearch' in content

    def test_has_pagination_prev(self):
        """导出上一页"""
        content = self._read()
        assert 'window.diagHistoryPrevPage' in content

    def test_has_pagination_next(self):
        """导出下一页"""
        content = self._read()
        assert 'window.diagHistoryNextPage' in content

    def test_has_pagination_go(self):
        """导出跳页"""
        content = self._read()
        assert 'window.diagHistoryGoPage' in content

    def test_has_view_detail(self):
        """导出查看详情"""
        content = self._read()
        assert 'window.diagViewHistoryDetail' in content

    def test_has_back_to_list(self):
        """导出返回列表"""
        content = self._read()
        assert 'window.diagHistoryBackToList' in content

    def test_uses_safe_get(self):
        """使用 safeGet"""
        content = self._read()
        assert 'safeGet' in content

    def test_has_page_size(self):
        """定义分页大小"""
        content = self._read()
        assert '_pageSize' in content

    def test_has_history_table_rendering(self):
        """包含历史表格渲染"""
        content = self._read()
        assert 'history-table' in content

    def test_has_status_filter(self):
        """包含状态筛选"""
        content = self._read()
        assert 'success' in content
        assert 'failed' in content

    def test_has_level_badge(self):
        """包含层级徽章"""
        content = self._read()
        assert 'getLevelBadge' in content or '_getLevelBadge' in content


class TestDiagnosisReportJs:
    """diagnosis-report.js 组件测试"""

    def _read(self):
        return (COMPONENTS_DIR / 'diagnosis-report.js').read_text(encoding='utf-8')

    def test_has_diag_report_show(self):
        """导出 diagReportShow"""
        content = self._read()
        assert 'window.diagReportShow' in content

    def test_has_diag_report_clear(self):
        """导出 diagReportClear"""
        content = self._read()
        assert 'window.diagReportClear' in content

    def test_has_diag_report_download(self):
        """导出 diagReportDownload"""
        content = self._read()
        assert 'window.diagReportDownload' in content

    def test_has_diag_report_copy(self):
        """导出 diagReportCopy"""
        content = self._read()
        assert 'window.diagReportCopy' in content

    def test_has_table_rendering(self):
        """包含表格渲染"""
        content = self._read()
        assert 'result-table' in content

    def test_has_markdown_rendering(self):
        """包含 Markdown 渲染"""
        content = self._read()
        assert 'renderMarkdown' in content or '_renderMarkdown' in content

    def test_has_multi_step_rendering(self):
        """包含多步骤渲染"""
        content = self._read()
        assert 'multi_step' in content or 'multi-step' in content

    def test_has_file_link_rendering(self):
        """包含文件链接渲染"""
        content = self._read()
        assert 'file_link' in content or 'file-link' in content

    def test_has_scenario_rendering(self):
        """包含场景方案渲染"""
        content = self._read()
        assert 'scenario' in content

    def test_has_text_rendering(self):
        """包含纯文本渲染"""
        content = self._read()
        assert 'result-text' in content or '_renderText' in content

    def test_has_render_mode_detection(self):
        """包含渲染模式检测"""
        content = self._read()
        assert 'render_mode' in content or '_detectMode' in content

    def test_has_download_via_blob(self):
        """下载使用 Blob"""
        content = self._read()
        assert 'Blob' in content

    def test_has_clipboard_copy(self):
        """复制使用 clipboard API"""
        content = self._read()
        assert 'clipboard' in content


class TestAgentChatJs:
    """agent-chat.js 组件测试"""

    def _read(self):
        return (COMPONENTS_DIR / 'agent-chat.js').read_text(encoding='utf-8')

    def test_has_dc_agent_send(self):
        """导出 dcAgentSend"""
        content = self._read()
        assert 'window.dcAgentSend' in content

    def test_has_dc_agent_quick_ask(self):
        """导出 dcAgentQuickAsk"""
        content = self._read()
        assert 'window.dcAgentQuickAsk' in content

    def test_has_dc_agent_clear_chat(self):
        """导出 dcAgentClearChat"""
        content = self._read()
        assert 'window.dcAgentClearChat' in content

    def test_has_dc_agent_stop(self):
        """导出 dcAgentStop"""
        content = self._read()
        assert 'window.dcAgentStop' in content

    def test_has_dc_agent_init(self):
        """导出 dcAgentInit"""
        content = self._read()
        assert 'window.dcAgentInit' in content

    def test_has_streaming_support(self):
        """支持流式响应"""
        content = self._read()
        assert 'getReader' in content or 'ReadableStream' in content or 'stream' in content

    def test_has_abort_controller(self):
        """支持请求取消"""
        content = self._read()
        assert 'AbortController' in content

    def test_has_markdown_rendering(self):
        """包含 Markdown 渲染"""
        content = self._read()
        assert '_renderMd' in content or 'renderMd' in content

    def test_has_local_storage_persistence(self):
        """对话历史持久化到 localStorage"""
        content = self._read()
        assert 'localStorage' in content

    def test_has_storage_key(self):
        """定义存储 key"""
        content = self._read()
        assert 'STORAGE_KEY' in content or '_STORAGE_KEY' in content

    def test_has_message_add(self):
        """包含消息添加方法"""
        content = self._read()
        assert '_addMessage' in content

    def test_has_message_update(self):
        """包含消息更新方法"""
        content = self._read()
        assert '_updateMessage' in content

    def test_has_tool_start_handling(self):
        """处理 tool_start 事件"""
        content = self._read()
        assert 'tool_start' in content

    def test_has_tool_result_handling(self):
        """处理 tool_result 事件"""
        content = self._read()
        assert 'tool_result' in content

    def test_has_welcome_page(self):
        """包含欢迎页"""
        content = self._read()
        assert 'dcChatWelcome' in content

    def test_has_dom_content_loaded(self):
        """在 DOMContentLoaded 后初始化"""
        content = self._read()
        assert 'DOMContentLoaded' in content


# ═══════════════════════════════════════════════════════════════════════════════
# CSS 测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiagnosisCss:
    """诊断 CSS 样式文件测试"""

    def test_app_css_exists(self):
        """app.css 存在"""
        assert (STATIC_DIR / 'css' / 'app.css').exists()

    def test_diagnosis_css_exists(self):
        """diagnosis.css 存在"""
        assert (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').exists()

    def test_diagnosis_css_has_capability_card(self):
        """包含能力卡片样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '.capability-card' in content

    def test_diagnosis_css_has_capability_grid(self):
        """包含卡片网格样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '.capability-grid' in content

    def test_diagnosis_css_has_form_modal(self):
        """包含表单弹窗样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '.diag-form-modal' in content

    def test_diagnosis_css_has_result_styles(self):
        """包含结果展示样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '.diag-result' in content

    def test_diagnosis_css_has_history_styles(self):
        """包含历史记录样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '.diag-history' in content

    def test_diagnosis_css_has_badge_styles(self):
        """包含徽章样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '.badge-low' in content
        assert '.badge-high' in content

    def test_diagnosis_css_has_spin_animation(self):
        """包含旋转动画"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '@keyframes spin' in content

    def test_diagnosis_css_has_modal_overlay(self):
        """包含模态框遮罩样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert 'modal-overlay' in content

    def test_diagnosis_css_has_loading_overlay(self):
        """包含加载遮罩样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert 'diagLoadingOverlay' in content

    def test_diagnosis_css_has_execution_indicator(self):
        """包含执行指示器样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert 'execution-indicator' in content

    def test_diagnosis_css_has_result_table(self):
        """包含结果表格样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '.result-table' in content

    def test_diagnosis_css_has_markdown_body(self):
        """包含 Markdown 渲染样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '.markdown-body' in content

    def test_diagnosis_css_has_multi_step(self):
        """包含多步骤样式"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '.multi-step-results' in content

    def test_diagnosis_css_has_responsive_rules(self):
        """包含响应式规则"""
        content = (STATIC_DIR / 'css' / 'components' / 'diagnosis.css').read_text(encoding='utf-8')
        assert '@media' in content


# ═══════════════════════════════════════════════════════════════════════════════
# 跨文件一致性测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrossFileConsistency:
    """跨文件一致性测试"""

    def test_all_js_files_export_to_window(self):
        """所有 JS 组件导出到 window"""
        for name in TestJavaScriptFiles.ALL_COMPONENTS:
            content = (COMPONENTS_DIR / name).read_text(encoding='utf-8')
            assert 'window.' in content, f'文件未导出到 window: {name}'

    def test_diagnosis_center_references_other_components(self):
        """diagnosis-center.js 引用了其他组件的 API"""
        content = (COMPONENTS_DIR / 'diagnosis-center.js').read_text(encoding='utf-8')
        # 引用了 parameter-form
        assert 'paramFormOpen' in content or 'diagShowParameterForm' in content
        # 引用了 execution-history
        assert 'diagHistoryInit' in content or 'dcLoadHistory' in content
        # 引用了 diagnosis-context
        assert 'DiagnosisContext' in content

    def test_no_circular_references(self):
        """无循环引用：diagnosis-center.js 不被其他组件引用"""
        center_content = (COMPONENTS_DIR / 'diagnosis-center.js').read_text(encoding='utf-8')
        for name in ['parameter-form.js', 'execution-progress.js', 'execution-history.js',
                      'diagnosis-report.js', 'agent-chat.js']:
            if name == 'diagnosis-center.js':
                continue
            content = (COMPONENTS_DIR / name).read_text(encoding='utf-8')
            assert 'diagnosis-center.js' not in content, f'{name} 不应引用 diagnosis-center.js'

    def test_api_util_usage_consistency(self):
        """API 工具使用一致性：所有需要网络请求的组件使用 safeGet/safePost"""
        files_that_need_api = [
            'diagnosis-center.js',
            'parameter-form.js',
            'execution-progress.js',
            'execution-history.js',
        ]
        for name in files_that_need_api:
            content = (COMPONENTS_DIR / name).read_text(encoding='utf-8')
            assert 'safeGet' in content or 'safePost' in content, \
                f'{name} 应使用 safeGet 或 safePost'

    def test_html_script_load_order(self):
        """HTML 中脚本加载顺序正确"""
        content = (STATIC_DIR / 'diagnosis-center.html').read_text(encoding='utf-8')

        # 基础依赖在前
        api_pos = content.find('api.js')
        utils_pos = content.find('utils.js')
        context_pos = content.find('diagnosis-context.js')

        # 组件在后
        center_pos = content.find('diagnosis-center.js')

        assert api_pos < center_pos, 'api.js 应在 diagnosis-center.js 之前加载'
        assert utils_pos < center_pos, 'utils.js 应在 diagnosis-center.js 之前加载'
        assert context_pos < center_pos, 'diagnosis-context.js 应在 diagnosis-center.js 之前加载'


# ═══════════════════════════════════════════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
