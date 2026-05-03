#!/usr/bin/env python3
"""
修复 connections 表历史数据

注意: java_pid 和 arthas_version 需要重新连接才能获取真实值
这里只是设置合理的默认值
"""
import sqlite3
from pathlib import Path

def fix_historical_data():
    db_path = Path(__file__).parents[1] / 'arthas.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("修复 connections 表历史数据")
    print("=" * 60)
    
    # 1. 修复 java_pid (Arthas 连接应该有 PID)
    print("\n1. 修复 java_pid...")
    cursor.execute("""
        UPDATE connections 
        SET java_pid = 1
        WHERE level = 'arthas' AND java_pid IS NULL
    """)
    print(f"   更新了 {cursor.rowcount} 条记录")
    
    # 2. 修复 arthas_version (设置为 unknown)
    print("\n2. 修复 arthas_version...")
    cursor.execute("""
        UPDATE connections 
        SET arthas_version = 'unknown'
        WHERE level = 'arthas' AND arthas_version IS NULL
    """)
    print(f"   更新了 {cursor.rowcount} 条记录")
    
    # 3. 修复 owner_user_id (同步 user_id)
    print("\n3. 修复 owner_user_id...")
    cursor.execute("""
        UPDATE connections 
        SET owner_user_id = user_id 
        WHERE owner_user_id IS NULL AND user_id IS NOT NULL
    """)
    print(f"   更新了 {cursor.rowcount} 条记录")
    
    # 4. 验证结果
    print("\n" + "=" * 60)
    print("验证结果")
    print("=" * 60)
    
    cols = ['java_pid', 'arthas_version', 'last_ping_at', 'status', 'container_name', 'owner_user_id']
    for col in cols:
        null_count = cursor.execute(f"SELECT COUNT(*) FROM connections WHERE {col} IS NULL").fetchone()[0]
        total = cursor.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
        status = "OK" if null_count == 0 else f"仍有 {null_count}/{total} NULL"
        print(f"  {col:20s}: {status}")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 60)
    print("修复完成")
    print("=" * 60)
    print("\n注意:")
    print("  - java_pid=1 是占位值,重新连接后会自动更新")
    print("  - arthas_version='unknown' 是占位值,重新连接后会自动更新")
    print("  - 建议重新建立 Arthas 连接以获取真实值")


if __name__ == '__main__':
    fix_historical_data()
