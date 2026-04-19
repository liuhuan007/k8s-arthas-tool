/**
 * 精准错误提示组件
 * 
 * 支持 10+ 种连接失败场景的结构化错误提示
 * 包括：错误码、消息、解决建议
 */

// ── 错误码定义 ──────────────────────────────────────────────────────────────

const ErrorCodes = {
  // Pod 连接相关
  POD_NOT_FOUND: 'POD_NOT_FOUND',
  POD_NOT_RUNNING: 'POD_NOT_RUNNING',
  POD_PERMISSION_DENIED: 'POD_PERMISSION_DENIED',
  POD_NETWORK_ERROR: 'POD_NETWORK_ERROR',
  POD_EXEC_FAILED: 'POD_EXEC_FAILED',
  
  // Arthas 相关
  ARTHAS_START_FAILED: 'ARTHAS_START_FAILED',
  ARTHAS_PORT_FORWARD_FAILED: 'ARTHAS_PORT_FORWARD_FAILED',
  ARTHAS_HTTP_TIMEOUT: 'ARTHAS_HTTP_TIMEOUT',
  ARTHAS_NOT_JAVA: 'ARTHAS_NOT_JAVA',
  
  // 连接管理
  CONNECTION_EXPIRED: 'CONNECTION_EXPIRED',
  CONNECTION_NOT_OWNER: 'CONNECTION_NOT_OWNER',
  
  // 通用
  UNKNOWN_ERROR: 'UNKNOWN_ERROR'
};

// ── 错误信息映射 ──────────────────────────────────────────────────────────────

const ErrorMessages = {
  [ErrorCodes.POD_NOT_FOUND]: {
    title: 'Pod 不存在',
    message: '指定的 Pod 在集群中不存在',
    suggestion: '请检查 Pod 名称和命名空间是否正确，或刷新 Pod 列表',
    icon: '❌',
    type: 'error'
  },
  
  [ErrorCodes.POD_NOT_RUNNING]: {
    title: 'Pod 未运行',
    message: (phase) => `Pod 当前状态为: ${phase}`,
    suggestion: (phase) => {
      const suggestions = {
        'Pending': 'Pod 正在调度中，请等待片刻或检查集群资源是否充足',
        'Failed': 'Pod 启动失败，请查看 Pod 事件和日志排查问题',
        'CrashLoopBackOff': 'Pod 持续崩溃重启，请检查应用配置和依赖',
        'Error': 'Pod 发生错误，请查看详细信息',
        'Terminating': 'Pod 正在终止，无法建立连接'
      };
      return suggestions[phase] || 'Pod 状态异常，请稍后重试';
    },
    icon: '⚠️',
    type: 'warning'
  },
  
  [ErrorCodes.POD_PERMISSION_DENIED]: {
    title: '权限不足',
    message: '没有 kubectl exec 权限',
    suggestion: '请联系集群管理员授予 Pod exec 权限，或检查 ServiceAccount 配置',
    icon: '🔒',
    type: 'error'
  },
  
  [ErrorCodes.POD_NETWORK_ERROR]: {
    title: '网络连接失败',
    message: '无法连接到 Kubernetes API Server',
    suggestion: '请检查网络连接和 kubeconfig 配置，确认集群是否可达',
    icon: '🌐',
    type: 'error'
  },
  
  [ErrorCodes.POD_EXEC_FAILED]: {
    title: 'Exec 执行失败',
    message: '在 Pod 内执行命令失败',
    suggestion: '请检查容器是否正常运行，或尝试手动执行 kubectl exec 测试',
    icon: '⚙️',
    type: 'error'
  },
  
  [ErrorCodes.ARTHAS_START_FAILED]: {
    title: 'Arthas 启动失败',
    message: '无法在 Pod 内启动 Arthas Agent',
    suggestion: '请检查 Java 进程是否运行，或查看 Arthas 启动日志排查问题',
    icon: '🚀',
    type: 'error'
  },
  
  [ErrorCodes.ARTHAS_PORT_FORWARD_FAILED]: {
    title: '端口转发失败',
    message: '无法建立 kubectl port-forward 连接',
    suggestion: '请检查本地端口是否被占用，或尝试重新连接',
    icon: '🔌',
    type: 'error'
  },
  
  [ErrorCodes.ARTHAS_HTTP_TIMEOUT]: {
    title: 'Arthas HTTP 超时',
    message: 'Arthas HTTP API 未响应',
    suggestion: 'Arthas 可能正在启动，请等待片刻后重试，或检查 Pod 资源是否充足',
    icon: '⏱️',
    type: 'warning'
  },
  
  [ErrorCodes.ARTHAS_NOT_JAVA]: {
    title: '非 Java 应用',
    message: (runtime) => `当前应用运行时为: ${runtime}，无法启动 Arthas`,
    suggestion: 'Arthas 仅支持 Java 应用。您可以使用 Pod 连接进行基础运维（监控、文件、日志等）',
    icon: '☕',
    type: 'info'
  },
  
  [ErrorCodes.CONNECTION_EXPIRED]: {
    title: '连接已过期',
    message: 'Pod 连接已失效',
    suggestion: '请重新建立 Pod 连接',
    icon: '⌛',
    type: 'warning'
  },
  
  [ErrorCodes.CONNECTION_NOT_OWNER]: {
    title: '无权操作',
    message: '您无权操作此连接',
    suggestion: '只能操作自己创建的连接，或联系管理员',
    icon: '🚫',
    type: 'error'
  },
  
  [ErrorCodes.UNKNOWN_ERROR]: {
    title: '未知错误',
    message: '发生未知错误',
    suggestion: '请查看控制台日志或联系管理员',
    icon: '❓',
    type: 'error'
  }
};

// ── 错误检测函数 ──────────────────────────────────────────────────────────────

/**
 * 从错误消息中检测错误码
 */
function detectErrorCode(errorMessage) {
  if (!errorMessage) return ErrorCodes.UNKNOWN_ERROR;
  
  const msg = errorMessage.toLowerCase();
  
  // Pod 相关
  if (msg.includes('not found') || msg.includes('不存在')) {
    return ErrorCodes.POD_NOT_FOUND;
  }
  if (msg.includes('pending') || msg.includes('failed') || msg.includes('crashloop') || 
      msg.includes(' terminating') || msg.includes('未运行')) {
    return ErrorCodes.POD_NOT_RUNNING;
  }
  if (msg.includes('permission') || msg.includes('forbidden') || msg.includes('权限')) {
    return ErrorCodes.POD_PERMISSION_DENIED;
  }
  if (msg.includes('network') || msg.includes('networkerror') || msg.includes('连接') || 
      msg.includes('timeout')) {
    return ErrorCodes.POD_NETWORK_ERROR;
  }
  if (msg.includes('exec') && msg.includes('fail')) {
    return ErrorCodes.POD_EXEC_FAILED;
  }
  
  // Arthas 相关
  if (msg.includes('arthas') && msg.includes('start')) {
    return ErrorCodes.ARTHAS_START_FAILED;
  }
  if (msg.includes('port-forward') || msg.includes('port_forward') || msg.includes('端口')) {
    return ErrorCodes.ARTHAS_PORT_FORWARD_FAILED;
  }
  if (msg.includes('http') && msg.includes('timeout')) {
    return ErrorCodes.ARTHAS_HTTP_TIMEOUT;
  }
  if (msg.includes('非 java') || msg.includes('not java') || msg.includes('无法启动 arthas')) {
    return ErrorCodes.ARTHAS_NOT_JAVA;
  }
  
  // 连接管理
  if (msg.includes('expired') || msg.includes('失效')) {
    return ErrorCodes.CONNECTION_EXPIRED;
  }
  if (msg.includes('无权') || msg.includes('not owner') || msg.includes('permission')) {
    return ErrorCodes.CONNECTION_NOT_OWNER;
  }
  
  return ErrorCodes.UNKNOWN_ERROR;
}

/**
 * 提取 Pod 阶段信息
 */
function extractPodPhase(errorMessage) {
  const patterns = [
    /pod\s+状态[：:]\s*(\w+)/i,
    /phase[：:]\s*(\w+)/i,
    /(Pending|Failed|CrashLoopBackOff|Error|Terminating)/i
  ];
  
  for (const pattern of patterns) {
    const match = errorMessage.match(pattern);
    if (match) return match[1];
  }
  
  return 'Unknown';
}

/**
 * 提取运行时信息
 */
function extractRuntime(errorMessage) {
  const patterns = [
    /运行时[：:]\s*(\w+)/i,
    /runtime[：:]\s*(\w+)/i,
    /(java|node|python|go|unknown)/i
  ];
  
  for (const pattern of patterns) {
    const match = errorMessage.match(pattern);
    if (match) return match[1];
  }
  
  return 'unknown';
}

// ── 错误提示 UI ──────────────────────────────────────────────────────────────

/**
 * 显示结构化错误提示
 */
function showErrorNotification(errorCode, context = {}) {
  const errorInfo = ErrorMessages[errorCode] || ErrorMessages[ErrorCodes.UNKNOWN_ERROR];
  
  // 动态生成消息和建议
  const message = typeof errorInfo.message === 'function' 
    ? errorInfo.message(context.phase || context.runtime || '')
    : errorInfo.message;
  
  const suggestion = typeof errorInfo.suggestion === 'function'
    ? errorInfo.suggestion(context.phase || context.runtime || '')
    : errorInfo.suggestion;
  
  // 创建通知元素
  const notification = document.createElement('div');
  notification.className = `error-notification error-${errorInfo.type}`;
  notification.innerHTML = `
    <div class="error-notification-header">
      <span class="error-icon">${errorInfo.icon}</span>
      <span class="error-title">${errorInfo.title}</span>
      <button class="error-close" onclick="this.parentElement.parentElement.remove()">×</button>
    </div>
    <div class="error-notification-body">
      <div class="error-message">${message}</div>
      <div class="error-suggestion">
        <strong>💡 建议：</strong>${suggestion}
      </div>
      ${context.details ? `<div class="error-details"><strong>详情：</strong>${context.details}</div>` : ''}
    </div>
  `;
  
  // 添加到页面
  const container = document.getElementById('errorNotificationContainer') || createErrorContainer();
  container.appendChild(notification);
  
  // 自动消失（error 类型不自动消失）
  if (errorInfo.type !== 'error') {
    setTimeout(() => {
      if (notification.parentElement) {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => notification.remove(), 300);
      }
    }, 8000);
  }
  
  // 同时显示 toast
  toast(`${errorInfo.icon} ${message}`, errorInfo.type);
  
  return notification;
}

/**
 * 创建错误通知容器
 */
function createErrorContainer() {
  const container = document.createElement('div');
  container.id = 'errorNotificationContainer';
  container.className = 'error-notification-container';
  document.body.appendChild(container);
  return container;
}

/**
 * 从 API 响应中显示错误
 */
function showApiError(response, context = {}) {
  const errorMessage = response.error || response.message || '未知错误';
  const errorCode = detectErrorCode(errorMessage);
  
  // 提取上下文信息
  const phase = extractPodPhase(errorMessage);
  const runtime = extractRuntime(errorMessage);
  
  return showErrorNotification(errorCode, {
    ...context,
    phase,
    runtime,
    details: errorMessage
  });
}

// ── 便捷函数 ──────────────────────────────────────────────────────────────────

/**
 * 显示 Pod 连接错误
 */
function showPodError(errorMessage, context = {}) {
  const errorCode = detectErrorCode(errorMessage);
  const phase = extractPodPhase(errorMessage);
  
  return showErrorNotification(errorCode, {
    ...context,
    phase,
    details: errorMessage
  });
}

/**
 * 显示 Arthas 启动错误
 */
function showArthasError(errorMessage, context = {}) {
  const errorCode = detectErrorCode(errorMessage);
  const runtime = extractRuntime(errorMessage);
  
  return showErrorNotification(errorCode, {
    ...context,
    runtime,
    details: errorMessage
  });
}

// ── 初始化 ────────────────────────────────────────────────────────────────────

/**
 * 初始化错误提示系统
 */
function initErrorNotification() {
  console.log('精准错误提示系统已初始化');
  
  // 创建容器
  createErrorContainer();
}

// 自动初始化
if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', initErrorNotification);
}
