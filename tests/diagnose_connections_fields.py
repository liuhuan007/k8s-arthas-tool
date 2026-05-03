#!/usr/bin/env python3
"""
数据库 connections 表字段完整性诊断和修复

诊断所有字段是否有值,修复缺失字段
"""
import sqlite3
from pathlib import Path

def diagnose_and_fix():
    db_path = Path(__file__).parents[1] / 'arthas.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 80)
    print("connections 表字段完整性诊断")
    print("=" * 80)
    
    # 1. 获取表结构
    cursor.execute('PRAGMA table_info(connections)')
    columns = cursor.fetchall()
    col_names = [c[1] for c in columns]
    
    print(f"\n表结构 ({len(columns)} 个字段):")
    for c in columns:
        print(f"  {c[0]:2d}. {c[1]:20s} {c[2]:12s} nullable={c[3]==0} default={c[4]}")
    
    # 2. 获取总记录数
    cursor.execute('SELECT COUNT(*) FROM connections')
    total = cursor.fetchone()[0]
    print(f"\n总记录数: {total}")
    
    # 3. 检查每个字段的空值情况
    print("\n字段空值统计:")
    empty_fields = {}
    for col in col_names:
        cursor.execute(f'SELECT COUNT(*) FROM connections WHERE {col} IS NULL')
        null_count = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(*) FROM connections WHERE {col} = ?', ('',))
        empty_count = cursor.fetchone()[0]
        
        total_empty = null_count + empty_count
        if total_empty > 0:
            empty_fields[col] = {'null': null_count, 'empty': empty_count, 'total': total_empty}
            print(f"  ❌ {col:20s}: {total_empty}/{total} 为空 (NULL={null_count}, 空字符串={empty_count})")
        else:
            print(f"  ✅ {col:20s}: {total}/{total} 有值")
    
    # 4. 显示示例数据
    print("\n示例数据 (前 3 条):")
    cursor.execute('SELECT * FROM connections LIMIT 3')
    rows = cursor.fetchall()
    for i, row in enumerate(rows, 1):
        print(f"\n  记录 {i}:")
        for col, val in zip(col_names, row):
            status = "❌ NULL" if val is None else ("❌ 空" if val == '' else "✅")
            print(f"    {col:20s}: {status} {val}")
    
    # 5. 修复建议
    print("\n" + "=" * 80)
    print("修复建议")
    print("=" * 80)
    
    fixes = []
    
    # 修复 java_pid
    if 'java_pid' in empty_fields:
        fixes.append({
            'field': 'java_pid',
            'issue': 'Arthas 连接应该有 java_pid',
            'fix': '从 _connections 内存中同步',
            'sql': '''
UPDATE connections 
SET java_pid = (
    SELECT json_extract(conn_json, '$.java_pid')
    FROM (SELECT id, conn_json FROM _connections_backup) AS backup
    WHERE backup.id = connections.id
)
WHERE level = 'arthas' AND java_pid IS NULL
'''
        })
    
    # 修复 arthas_version
    if 'arthas_version' in empty_fields:
        fixes.append({
            'field': 'arthas_version',
            'issue': 'Arthas 连接应该有版本号',
            'fix': '需要重新连接获取',
            'sql': '-- 无法自动修复,需要重新建立连接'
        })
    
    # 修复 last_ping_at
    if 'last_ping_at' in empty_fields:
        fixes.append({
            'field': 'last_ping_at',
            'issue': '活跃连接应该有 last_ping_at',
            'fix': '设置为 updated_at',
            'sql': '''
UPDATE connections 
SET last_ping_at = updated_at 
WHERE last_ping_at IS NULL AND level IN ('arthas', 'pod')
'''
        })
    
    # 修复 status
    if 'status' in empty_fields:
        fixes.append({
            'field': 'status',
            'issue': '连接应该有状态',
            'fix': '根据 level 设置默认状态',
            'sql': '''
UPDATE connections 
SET status = CASE 
    WHEN level = 'arthas' THEN 'ready'
    WHEN level = 'pod' THEN 'pod_connected'
    ELSE 'disconnected'
END
WHERE status IS NULL OR status = 'disconnected'
'''
        })
    
    # 修复 container_name
    if 'container_name' in empty_fields:
        fixes.append({
            'field': 'container_name',
            'issue': '容器名不应为空字符串',
            'fix': '设置为默认值',
            'sql': '''
UPDATE connections 
SET container_name = 'default' 
WHERE container_name = '' OR container_name IS NULL
'''
        })
    
    # 清理 owner_user_id (冗余字段)
    if 'owner_user_id' in columns:
        fixes.append({
            'field': 'owner_user_id',
            'issue': '冗余字段,应使用 user_id',
            'fix': '同步 user_id 后忽略此字段',
            'sql': '''
-- 同步 owner_user_id = user_id (如果不同)
UPDATE connections 
SET owner_user_id = user_id 
WHERE owner_user_id IS NULL AND user_id IS NOT NULL

-- 注意: 不要删除此字段,因为 SQLite 旧版本不支持 DROP COLUMN
'''
        })
    
    if fixes:
        print(f"\n发现 {len(fixes)} 个需要修复的问题:\n")
        for i, fix in enumerate(fixes, 1):
            print(f"  {i}. {fix['field']}: {fix['issue']}")
            print(f"     修复方案: {fix['fix']}")
            print(f"     SQL: {fix['sql'][:80]}...")
            print()
    else:
        print("\n✅ 所有字段都有值,无需修复")
    
    # 6. 执行修复
    print("=" * 80)
    print("执行修复")
    print("=" * 80)
    
    for fix in fixes:
        print(f"\n修复 {fix['field']}...")
        try:
            # 分割多条 SQL
            sqls = [s.strip() for s in fix['sql'].split(';') if s.strip() and not s.strip().startswith('--')]
            for sql in sqls:
                if sql:
                    cursor.execute(sql)
                    print(f"  ✅ 执行: {sql[:80]}...")
            
            conn.commit()
            print(f"  ✅ {fix['field']} 修复成功")
        except Exception as e:
            print(f"  ❌ {fix['field']} 修复失败: {e}")
            conn.rollback()
    
    # 7. 验证修复结果
    print("\n" + "=" * 80)
    print("验证修复结果")
    print("=" * 80)
    
    for col in col_names:
        cursor.execute(f'SELECT COUNT(*) FROM connections WHERE {col} IS NULL')
        null_count = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(*) FROM connections WHERE {col} = ?', ('',))
        empty_count = cursor.fetchone()[0]
        
        total_empty = null_count + empty_count
        if total_empty > 0:
            print(f"  ⚠️  {col:20s}: 仍有 {total_empty}/{total} 为空")
        else:
            print(f"  ✅ {col:20s}: 全部有值")
    
    conn.close()
    print("\n" + "=" * 80)
    print("诊断完成")
    print("=" * 80)


if __name__ == '__main__':
    diagnose_and_fix()
