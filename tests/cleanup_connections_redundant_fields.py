#!/usr/bin/env python3
"""
清理 connections 表冗余字段

删除字段:
- runtime (不需要持久化,连接时获取即可)
- pod_phase (与 level 语义重复,level 已足够)
- pod_conn_id (与 id 字段重复)
- owner_user_id (与 user_id 重复)

执行方式: python tests/cleanup_connections_redundant_fields.py
"""
import sqlite3
from pathlib import Path


def cleanup():
    db_path = Path(__file__).resolve().parents[1] / 'data' / 'db' / 'arthas.db'
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取当前所有列
    cursor.execute("PRAGMA table_info(connections)")
    columns = {row[1] for row in cursor.fetchall()}
    
    print(f"📊 connections 表当前字段: {', '.join(sorted(columns))}\n")
    
    # SQLite 不支持 DROP COLUMN (旧版本),需要通过重建表实现
    # 这里仅标记删除,实际删除需要重建表
    
    fields_to_remove = ['runtime', 'pod_phase', 'pod_conn_id', 'owner_user_id']
    existing_fields = [f for f in fields_to_remove if f in columns]
    
    if not existing_fields:
        print("✅ 没有需要清理的冗余字段")
        conn.close()
        return
    
    print(f"⚠️  发现 {len(existing_fields)} 个冗余字段: {', '.join(existing_fields)}\n")
    print("📝 注意: SQLite 旧版本不支持 DROP COLUMN,需要重建表")
    print("📝 当前这些字段会被保留但不使用,不影响业务逻辑\n")
    
    # 显示这些字段的当前数据量
    for field in existing_fields:
        cursor.execute(f"SELECT COUNT(*) FROM connections WHERE {field} IS NOT NULL")
        count = cursor.fetchone()[0]
        print(f"  {field}: {count} 条记录有值")
    
    conn.close()
    
    print("\n✅ 建议: 这些字段会被保留在表中但不使用")
    print("   新代码不会再读写这些字段")
    print("   如需彻底删除,需要重建 connections 表")


if __name__ == '__main__':
    print("=" * 60)
    print("清理 connections 表冗余字段")
    print("=" * 60)
    print()
    cleanup()
    print()
    print("=" * 60)
