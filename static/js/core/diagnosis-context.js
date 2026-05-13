/**
 * 诊断上下文（全局状态管理）
 * 
 * 架构设计：
 * - 管理当前 Arthas 连接
 * - 追踪活跃执行任务
 * - 连接切换时自动取消正在执行的诊断
 * - 提供事件监听机制
 */

const DiagnosisContext = {
  // 当前连接
  currentConnection: null,
  
  // 活跃执行任务 Map<executionId, {status, capabilityId, startTime}>
  activeExecutions: new Map(),
  
  // 事件监听器集合
  listeners: new Set(),
  
  /** 将本地临时 ID 替换为后端真实 run_id，返回更新后的执行记录。 */
  replaceLocalExecutionId(localId, runId) {
    if (!localId || !runId || localId === runId) return null;
    const execution = this.activeExecutions.get(localId);
    if (!execution) return null;
    this.activeExecutions.delete(localId);
    execution.executionId = runId;
    execution.runId = runId;
    this.activeExecutions.set(runId, execution);
    return execution;
  },

  /**
   * 连接变化处理
   */
  onConnectionChange(newConn) {
    const oldConn = this.currentConnection;
    
    // 连接切换，取消所有正在执行的诊断
    if (newConn?.id !== oldConn?.id) {
      console.warn('[DiagnosisContext] 连接已切换，取消所有正在执行的诊断任务');
      
      this.activeExecutions.forEach((exec, id) => {
        if (exec.status === 'running') {
          this.cancelExecution(id);
        }
      });
      
      this.activeExecutions.clear();
    }
    
    this.currentConnection = newConn;
    
    // 通知所有监听器
    this._notifyListeners('connectionChange', {
      oldConnection: oldConn,
      newConnection: newConn,
    });
  },
  
  /**
   * 注册执行任务
   */
  registerExecution(executionId, capabilityId, capabilityName) {
    this.activeExecutions.set(executionId, {
      executionId,
      runId: executionId,
      capabilityId,
      capabilityName,
      status: 'running',
      startTime: Date.now(),
    });
    
    this._notifyListeners('executionRegistered', {
      executionId,
      capabilityId,
      capabilityName,
    });
  },
  
  /**
   * 完成执行任务
   */
  completeExecution(executionId, status = 'completed', result = null) {
    const execution = this.activeExecutions.get(executionId);
    
    if (execution) {
      execution.status = status;
      execution.endTime = Date.now();
      execution.result = result;
      
      this._notifyListeners('executionCompleted', {
        executionId,
        status,
        result,
      });
      
      // 3 秒后移除（保留历史记录）
      setTimeout(() => {
        this.activeExecutions.delete(executionId);
      }, 3000);
    }
  },
  
  /**
   * 轮询执行状态
   */
  async pollExecution(runId, interval = 2000) {
    const API = window.API || '/api';
    let attempts = 0;
    const maxAttempts = 150;
    while (attempts < maxAttempts) {
      try {
        const resp = await fetch(`${API}/tasks/diagnosis/runs/${runId}`, {
          credentials: 'include',
        });
        if (!resp.ok) return null;
        const data = await resp.json();
        if (!data.ok) return null;
        const run = data.run;
        if (run && run.status !== 'running' && run.status !== 'pending') {
          return run;
        }
      } catch (_) { /* ignore */ }
      await new Promise(r => setTimeout(r, interval));
      attempts++;
    }
    return null;
  },
  
  /**
   * 取消执行任务（使用后端真实 run_id）
   */
  cancelExecution(executionId) {
    const execution = this.activeExecutions.get(executionId);
    
    if (execution && execution.status === 'running') {
      execution.status = 'cancelled';
      execution.endTime = Date.now();
      
      // 使用后端真实 run_id（优先级：runId > executionId）
      const backendRunId = execution.runId || execution.executionId;
      
      this._notifyListeners('executionCancelled', {
        executionId: backendRunId,
        capabilityId: execution.capabilityId,
      });
      
      // 调用后端取消 API（非阻塞）
      try {
        const API = window.API || '/api';
        fetch(`${API}/tasks/diagnosis/runs/${backendRunId}/cancel`, {
          method: 'POST',
          credentials: 'include',
        }).then(r => r.json()).then(d => {
          if (d.ok) {
            console.log(`[DiagnosisContext] 后端取消成功: ${backendRunId}`);
          } else {
            console.warn(`[DiagnosisContext] 后端取消失败: ${d.error || 'unknown'}`);
          }
        }).catch(e => {
          console.warn(`[DiagnosisContext] 后端取消请求异常: ${e.message}`);
        });
      } catch (e) {
        console.warn(`[DiagnosisContext] 取消 API 调用异常: ${e.message}`);
      }
    }
  },
  
  /**
   * 获取活跃执行数
   */
  getActiveCount() {
    return Array.from(this.activeExecutions.values())
      .filter(e => e.status === 'running').length;
  },
  
  /**
   * 获取活跃执行列表
   */
  getActiveExecutions() {
    return Array.from(this.activeExecutions.values())
      .filter(e => e.status === 'running');
  },
  
  /**
   * 检查是否有正在执行的诊断
   */
  hasActiveExecutions() {
    return this.getActiveCount() > 0;
  },
  
  /**
   * 注册事件监听器（返回取消订阅函数，引用同一对象以便正确删除）
   */
  addEventListener(eventType, callback) {
    const entry = { eventType, callback };
    this.listeners.add(entry);
    
    return () => {
      this.listeners.delete(entry);
    };
  },
  
  /**
   * 通知所有监听器
   */
  _notifyListeners(eventType, data) {
    this.listeners.forEach(({ eventType: et, callback }) => {
      if (et === eventType || et === '*') {
        try {
          callback(data);
        } catch (e) {
          console.error('[DiagnosisContext] 监听器回调失败:', e);
        }
      }
    });
  },
  
  /**
   * 获取连接断开时的用户提示
   */
  getConnectionLostDialog() {
    return {
      title: 'Arthas 连接已断开',
      message: '诊断执行过程中连接中断，请重新建立连接后重试',
      action: '重新连接',
      onAction: () => {
        if (typeof switchTab === 'function') {
          switchTab('connections');
        }
      },
    };
  },
};

// 暴露到全局
window.DiagnosisContext = DiagnosisContext;

// 初始化时检查 URL 参数中的连接 ID
(function initConnectionFromURL() {
  const params = new URLSearchParams(window.location.search);
  const connId = params.get('connection');
  
  if (connId && window.currentConnection) {
    DiagnosisContext.onConnectionChange(window.currentConnection);
  }
})();
