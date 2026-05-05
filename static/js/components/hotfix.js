/**
 * 热修复工作台 - P1b-1
 * 
 * 完整链路: jad → 编辑/上传 → mc 编译 → redefine → 验证报告
 */

// 全局状态
let _hfState = {
  connectionId: null,
  className: null,
  sourceCode: null,
  uploadedFile: null,
  compiledClass: null,
  redefineResult: null,
  artifactPath: null
};

/**
 * 步骤 1: 查看源码 (jad)
 */
async function hotfixJad() {
  const className = document.getElementById('hfClassName').value.trim();
  let connId = getCurrentConnectionId();
  
  console.log('[Hotfix] 初始 connId:', connId);
  console.log('[Hotfix] window._currentConnId:', window._currentConnId);
  console.log('[Hotfix] _hfState.connectionId:', _hfState.connectionId);
  
  // 如果没有连接,弹出多连接选择器
  if (!connId) {
    await showConnectionSelectorForHotfix();
    connId = getCurrentConnectionId();
    if (!connId) return; // 用户取消选择
  }
  
  console.log('[Hotfix] 最终 connId:', connId);
  
  if (!className) {
    alert('请输入类名');
    return;
  }

  const btn = document.getElementById('btnJad');
  btn.disabled = true;
  btn.textContent = '⏳ 查看中...';

  try {
    console.log('[Hotfix] 请求参数:', { connection_id: connId, class_name: className });
    
    const resp = await fetch('/api/hotfix/jad', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        connection_id: connId,
        class_name: className
      })
    });

    const data = await resp.json();
    console.log('[Hotfix] 响应:', data);
    
    if (data.ok) {
      _hfState.connectionId = connId;
      _hfState.className = className;
      _hfState.sourceCode = data.source_code;
      _hfState.artifactPath = data.artifact_path;
      _hfState.uploadedFile = data.artifact_path;  // ✅ 保存文件路径,供 MC 编译使用

      // 显示源码
      document.getElementById('hfSourceCode').textContent = data.source_code;
      document.getElementById('hfSourceView').style.display = 'block';
      
      // 启用编辑按钮
      document.getElementById('btnEditJava').disabled = false;
      
      // ✅ 启用编译按钮 (JAD 后可以直接编译)
      document.getElementById('btnCompile').disabled = false;
      
      log('✅ 源码查看成功: ' + (data.artifact_path || '未知路径'));
    } else {
      alert('查看源码失败: ' + data.error);
    }
  } catch (err) {
    console.error('[Hotfix] 请求异常:', err);
    alert('请求失败: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 查看源码';
  }
}

/**
 * 步骤 2: 在线编辑
 */
function hotfixEnableEdit() {
  const editor = document.getElementById('hfEditor');
  const saveBtn = document.getElementById('btnSaveEdit');
  const editStatus = document.getElementById('hfEditStatus');
  
  // ✅ 安全检查: 确保元素存在
  if (!editor) {
    console.error('[Hotfix] hfEditor 元素不存在');
    alert('编辑器未找到，请刷新页面重试');
    return;
  }
  
  if (!saveBtn) {
    console.error('[Hotfix] btnSaveEdit 元素不存在');
    alert('保存按钮未找到，请刷新页面重试');
    return;
  }
  
  if (!editStatus) {
    console.error('[Hotfix] hfEditStatus 元素不存在');
    return;
  }
  
  console.log('[Hotfix EnableEdit] 开始启用编辑模式');
  console.log('[Hotfix EnableEdit] saveBtn 当前 display:', saveBtn.style.display);
  
  // ✅ 确保步骤 2 区域可见 (如果父容器被隐藏)
  const step2Container = editor.closest('.hotfix-step');
  if (step2Container && step2Container.style.display === 'none') {
    console.log('[Hotfix EnableEdit] 步骤 2 区域被隐藏，显示它');
    step2Container.style.display = '';
  }
  
  editor.value = _hfState.sourceCode || '';
  editor.style.display = 'block';
  
  // ✅ 显示保存按钮
  saveBtn.style.display = 'inline-block';
  console.log('[Hotfix EnableEdit] 保存按钮已显示');
  
  editStatus.style.display = 'block';
  editStatus.textContent = '️ 编辑模式：修改后请点击"保存修改"按钮';
  editor.focus();
  
  // ✅ 滚动到步骤 2 区域
  if (step2Container) {
    step2Container.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  
  // ✅ 监听修改，标记未保存状态
  editor.addEventListener('input', () => {
    _hfState.hasUnsavedChanges = true;
    editStatus.textContent = '️ 有未保存的修改，请点击"保存修改"';
    editStatus.style.color = '#f59e0b';
  });
}

function hotfixEditJava() {
  hotfixEnableEdit();
}

/**
 * 步骤 2: 保存编辑内容
 */
async function hotfixSaveEdit() {
  const editor = document.getElementById('hfEditor');
  const saveBtn = document.getElementById('btnSaveEdit');
  const editStatus = document.getElementById('hfEditStatus');
  
  const newSource = editor.value.trim();
  if (!newSource) {
    alert('源码不能为空');
    return;
  }

  const connId = getCurrentConnectionId();
  if (!connId) {
    alert('请先建立连接');
    return;
  }

  if (!_hfState.artifactPath) {
    alert('未找到文件路径，请先查看源码');
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = '⏳ 保存中...';
  editStatus.textContent = '⏳ 正在保存修改...';
  editStatus.style.color = 'var(--tx3)';

  try {
    // 将修改后的源码写入文件
    const formData = new FormData();
    formData.append('connection_id', connId);
    formData.append('file_path', _hfState.artifactPath);
    formData.append('content', newSource);

    const resp = await fetch('/api/hotfix/save-edit', {
      method: 'POST',
      credentials: 'include',
      body: formData
    });

    const data = await resp.json();
    
    if (data.ok) {
      _hfState.sourceCode = newSource;
      _hfState.hasUnsavedChanges = false;
      
      editStatus.textContent = '✅ 保存成功！现在可以执行编译';
      editStatus.style.color = 'var(--a3)';
      
      // 3秒后隐藏状态
      setTimeout(() => {
        editStatus.style.display = 'none';
      }, 3000);
      
      console.log('[Hotfix Save] 保存成功:', data);
    } else {
      editStatus.textContent = '❌ 保存失败: ' + data.error;
      editStatus.style.color = '#f56565';
    }
  } catch (err) {
    editStatus.textContent = '❌ 请求失败: ' + err.message;
    editStatus.style.color = '#f56565';
    console.error('[Hotfix Save] 请求异常:', err);
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 保存修改';
  }
}

/**
 * 步骤 2: 上传文件
 */
async function hotfixUploadFile(input) {
  const file = input.files[0];
  if (!file) return;

  console.log('[Hotfix Upload] 开始上传文件:', file.name, '大小:', file.size);

  const connId = getCurrentConnectionId();
  if (!connId) {
    alert('请先建立连接');
    return;
  }

  const status = document.getElementById('hfUploadStatus');
  status.textContent = '⏳ 上传中...';

  const formData = new FormData();
  formData.append('file', file);
  formData.append('connection_id', connId);

  try {
    console.log('[Hotfix Upload] 发送请求到 /api/hotfix/upload');
    const resp = await fetch('/api/hotfix/upload', {
      method: 'POST',
      credentials: 'include',
      body: formData
    });

    console.log('[Hotfix Upload] 响应状态:', resp.status);
    const data = await resp.json();
    console.log('[Hotfix Upload] 响应数据:', data);
    
    if (data.ok) {
      _hfState.uploadedFile = data.file_path;
      _hfState.artifactPath = data.artifact_path;
      
      status.textContent = `✅ 上传成功: ${data.file_name} (${data.file_size} bytes, SHA256: ${data.sha256.substring(0, 16)}...)`;
      console.log('[Hotfix Upload] 上传成功');
      
      // 如果是 .java 文件,启用编译按钮
      if (file.name.endsWith('.java')) {
        document.getElementById('btnCompile').disabled = false;
      }
      
      // 如果是 .class 文件,启用 redefine 按钮
      if (file.name.endsWith('.class')) {
        document.getElementById('btnRedefine').disabled = false;
      }
    } else {
      status.textContent = '❌ 上传失败: ' + data.error;
      console.error('[Hotfix Upload] 上传失败:', data.error);
    }
  } catch (err) {
    status.textContent = '❌ 请求失败: ' + err.message;
    console.error('[Hotfix Upload] 请求异常:', err);
  }
}

/**
 * 步骤 3: 编译 (mc)
 */
async function hotfixCompile() {
  const connId = getCurrentConnectionId();
  if (!connId) {
    alert('请先建立连接');
    return;
  }

  // ✅ 检查是否有未保存的修改
  if (_hfState.hasUnsavedChanges) {
    const confirmed = confirm('⚠️ 检测到未保存的修改！\n\n请先点击“保存修改”按钮，否则编译的将是旧文件。\n\n是否继续编译旧文件？');
    if (!confirmed) {
      console.log('[Hotfix MC] 用户取消编译，先保存修改');
      return;
    }
    console.log('[Hotfix MC] 用户确认编译旧文件');
  }

  if (!_hfState.uploadedFile) {
    alert('请先查看源码或上传 Java 文件');
    console.error('[Hotfix MC] _hfState.uploadedFile 为空:', _hfState);
    return;
  }

  console.log('[Hotfix MC] 开始编译:', {
    connection_id: connId,
    java_file_path: _hfState.uploadedFile,
    _hfState: _hfState
  });

  const btn = document.getElementById('btnCompile');
  btn.disabled = true;
  btn.textContent = '⏳ 编译中...';

  const output = document.getElementById('hfCompileOutput');
  output.style.display = 'block';
  output.textContent = '⏳ 执行 mc 编译...';

  try {
    const resp = await fetch('/api/hotfix/compile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        connection_id: connId,
        java_file_path: _hfState.uploadedFile  // ✅ 修复: 使用正确的字段名
      })
    });

    const data = await resp.json();
    console.log('[Hotfix MC] 响应:', data);
    
    if (data.ok) {
      _hfState.compiledClass = data.class_file;
      
      // ✅ 改进: 检查是否有编译输出
      if (!data.class_file && !data.output) {
        output.textContent = '⚠️ 编译成功,但未生成 .class 文件\n\n可能原因:\n1. 源码有语法错误\n2. 缺少依赖类\n3. 文件路径不正确\n\n请检查输出日志或重新保存修改';
        output.style.color = '#f59e0b';
        console.warn('[Hotfix MC] 编译成功但无输出:', data);
      } else {
        output.textContent = data.output || '编译成功: ' + (data.class_file || '未知');
        output.style.color = 'var(--tx)';
        
        // 启用 redefine 按钮
        document.getElementById('btnRedefine').disabled = false;
      }
      
      log('✅ 编译成功: ' + (data.class_file || '未知'));
    } else {
      output.textContent = '❌ 编译失败: ' + (data.error || '未知错误');
      output.style.color = '#f56565';
      console.error('[Hotfix MC] 编译失败:', data);
    }
  } catch (err) {
    output.textContent = '❌ 请求失败: ' + err.message;
    output.style.color = '#f56565';
    console.error('[Hotfix MC] 请求异常:', err);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔨 执行 mc 编译';
  }
}

function hotfixSkipCompile() {
  log('⏭️ 跳过编译,可直接执行 redefine');
  document.getElementById('btnRedefine').disabled = false;
}

/**
 * 步骤 4: 执行 redefine
 */
async function hotfixRedefine() {
  // ✅ 去掉 CONFIRM 验证,直接执行
  const connId = getCurrentConnectionId();
  if (!connId) {
    alert('请先建立连接');
    return;
  }

  const btn = document.getElementById('btnRedefine');
  btn.disabled = true;
  btn.textContent = '⏳ 执行中...';

  const output = document.getElementById('hfRedefineOutput');
  output.style.display = 'block';
  output.textContent = '⏳ 执行 redefine...';

  try {
    const resp = await fetch('/api/hotfix/redefine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        connection_id: connId,
        class_file: _hfState.compiledClass || _hfState.uploadedFile,
        confirmed: true
      })
    });

    const data = await resp.json();
    
    if (data.ok) {
      _hfState.redefineResult = data;
      // ✅ 增强展示: 使用 pre 标签格式化输出
      output.style.display = 'block';
      output.style.color = '#10b981';  // 绿色
      output.textContent = '✅ redefine 成功!\n\n' + (data.output || '无输出');
      
      // 启用验证按钮
      document.getElementById('btnVerify').disabled = false;
      
      log('✅ redefine 成功');
    } else {
      // ✅ 增强展示: 详细错误信息
      output.style.display = 'block';
      output.style.color = '#f56565';  // 红色
      output.textContent = '❌ redefine 失败:\n\n' + (data.error || '未知错误');
      console.error('[Hotfix Redefine] 失败:', data);
    }
  } catch (err) {
    output.textContent = '❌ 请求失败: ' + err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ 执行 redefine';
  }
}

/**
 * 步骤 5: 生成验证报告
 */
async function hotfixVerify() {
  const connId = getCurrentConnectionId();
  if (!connId) {
    alert('请先建立连接');
    return;
  }

  const btn = document.getElementById('btnVerify');
  btn.disabled = true;
  btn.textContent = '⏳ 生成中...';

  try {
    const resp = await fetch('/api/hotfix/verification', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        connection_id: connId,
        class_name: _hfState.className,
        redefine_output: _hfState.redefineResult?.output || '',
        old_source: _hfState.sourceCode || '',
        new_source: document.getElementById('hfEditor').value || _hfState.sourceCode || '',
        timestamp: new Date().toISOString()
      })
    });

    const data = await resp.json();
    
    if (data.ok) {
      document.getElementById('hfReportContent').textContent = data.report_content;
      document.getElementById('hfVerificationReport').style.display = 'block';
      
      log('✅ 验证报告生成成功');
    } else {
      alert('生成验证报告失败: ' + data.error);
    }
  } catch (err) {
    alert('请求失败: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 生成验证报告';
  }
}

/**
 * 显示 redefine 技术限制
 */
async function hotfixShowLimitations() {
  try {
    const resp = await fetch('/api/hotfix/limitations', {
      credentials: 'include'
    });
    const data = await resp.json();
    
    if (data.ok) {
      let msg = '⚠️ redefine 8 项技术限制:\n\n';
      data.limitations.forEach((lim, idx) => {
        msg += `${idx + 1}. ${lim.title}
   ${lim.description}
   ${lim.action}

`;
      });
      alert(msg);
    }
  } catch (err) {
    alert('获取限制信息失败: ' + err.message);
  }
}

/**
 * 显示回滚指引
 */
function hotfixShowRollbackGuide() {
  alert(`🔄 回滚指引:

1. 准备旧版本 .class 文件
   - 从发布包或备份中获取
   
2. 上传旧版本
   - 点击"本地上传"按钮
   - 选择旧版本 .class 文件
   
3. 执行 redefine
   - 点击"执行 redefine" 按钮
   
4. 验证回滚
   - 生成验证报告
   - 确认功能已恢复

注意: redefine 只影响当前 JVM,Pod 重启后将回到镜像中的代码`);
}

/**
 * 获取当前连接 ID
 */
function getCurrentConnectionId() {
  // 优先从全局状态获取(正确的连接ID)
  if (window._currentConnId) {
    return window._currentConnId;
  }
  
  // 兼容: 从热修复本地状态获取
  if (_hfState.connectionId) {
    return _hfState.connectionId;
  }
  
  return null;
}

/**
 * 显示连接选择器(当没有当前连接时)
 */
async function showConnectionSelectorForHotfix() {
  // 获取所有活跃连接
  try {
    const resp = await fetch('/api/pod/connections', {
      credentials: 'include'
    });
    const data = await resp.json();
    
    if (!data.ok || !data.connections || data.connections.length === 0) {
      alert('没有活跃的连接,请先建立 Pod 连接');
      return;
    }
    
    // 过滤出活跃的连接
    const activeConns = data.connections.filter(c => {
      return c.id && (c.level === 'arthas' || c.level === 'pod' || c.local_port || c.runtime_type);
    });
    
    if (activeConns.length === 0) {
      alert('没有活跃的连接,请先建立 Pod 连接');
      return;
    }
    
    // 弹出多连接选择器
    return new Promise((resolve) => {
      MultiConnSelector.show(activeConns, (connId) => {
        // 用户选择后,切换到该连接
        if (typeof switchConnection === 'function') {
          switchConnection(connId);
        }
        _hfState.connectionId = connId;
        resolve();
      });
    });
  } catch (e) {
    console.error('获取连接列表失败:', e);
    alert('获取连接列表失败: ' + e.message);
  }
}

/**
 * 日志输出
 */
function log(msg) {
  console.log('[Hotfix]', msg);
}
