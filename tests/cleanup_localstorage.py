#!/usr/bin/env python3
"""
清理冲突的 localStorage 数据

问题:
- arthas_connection_store 中的 connections:[] 覆盖了数据库数据
- arthas_connections / arthas_connections_admin / arthas_connections_{user} 多套存储共存

解决:
- 在浏览器控制台执行清理脚本
- 或手动清理浏览器开发者工具 -> Application -> Local Storage
"""

# 此脚本用于生成浏览器控制台执行的清理代码
CLEANUP_JS = """
// 在浏览器开发者工具控制台执行此脚本
(function() {
  console.log('=== 开始清理冲突的 localStorage 数据 ===');
  
  // 1. 清理旧的连接存储 key
  const oldKeys = [
    'arthas_connections',
    'arthas_connections_admin',
    'arthas_current_conn_id',
    'arthas_active_conn',
    'arthas_active_level',
  ];
  
  // 2. 清理按用户隔离的旧 key (常见用户名)
  const commonUsers = ['admin', 'user', 'test'];
  commonUsers.forEach(u => {
    oldKeys.push(`arthas_connections_${u}`);
    oldKeys.push(`arthas_active_conn_${u}`);
    oldKeys.push(`arthas_active_level_${u}`);
  });
  
  let cleaned = 0;
  oldKeys.forEach(key => {
    if (localStorage.getItem(key)) {
      console.log(`删除: ${key}`);
      localStorage.removeItem(key);
      cleaned++;
    }
  });
  
  // 3. 重置 arthas_connection_store 中的 connections 字段
  const storeKey = 'arthas_connection_store';
  const stored = localStorage.getItem(storeKey);
  if (stored) {
    try {
      const data = JSON.parse(stored);
      if (data.connections && data.connections.length === 0) {
        console.log('重置 arthas_connection_store.connections 为空 (将由数据库 API 填充)');
        data.connections = [];
        localStorage.setItem(storeKey, JSON.stringify(data));
      }
    } catch(e) {
      console.error('解析 arthas_connection_store 失败:', e);
    }
  }
  
  console.log(`=== 清理完成,共删除 ${cleaned} 个 key ===`);
  console.log('请刷新页面 (Ctrl+F5),连接列表将从数据库重新加载');
})();
"""

if __name__ == '__main__':
    print("=" * 60)
    print("localStorage 清理工具")
    print("=" * 60)
    print()
    print("请按以下步骤操作:")
    print()
    print("1. 打开浏览器开发者工具 (F12)")
    print("2. 切换到 Console (控制台) 标签")
    print("3. 复制以下代码并执行:")
    print()
    print("-" * 60)
    print(CLEANUP_JS)
    print("-" * 60)
    print()
    print("4. 刷新页面 (Ctrl+F5 强制刷新)")
    print("5. 检查连接中心是否正常显示数据库中的记录")
    print()
    print("=" * 60)

