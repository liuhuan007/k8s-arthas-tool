# 数据库迁移规范

## 概述

本文档定义 K8s Arthas Tool 项目的数据库迁移规范，确保 SQLite 数据库 schema 变更可追溯、可回滚。

---

## 1. 迁移策略

| 阶段 | 策略 | 说明 |
|------|------|------|
| P0（当前） | 应用层自动迁移 | 启动时检测并执行 `ALTER TABLE` |
| P1（后续） | 版本化迁移脚本 | 独立迁移文件，支持回滚 |

---

## 2. 版本追踪

### 2.1 schema_version 表

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    description TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 版本号规则

| 版本格式 | 说明 | 示例 |
|---------|------|------|
| `N` | 整数递增 | 1, 2, 3... |
| 每次迁移 | 插入新版本号 | `INSERT INTO schema_version (version, description) VALUES (2, 'add progress column')` |

---

## 3. 迁移脚本命名

### 3.1 命名规范

```
migrations/
├── 001_initial_schema.sql
├── 002_add_task_logs_columns.sql
├── 003_add_anomaly_events.sql
└── ...
```

格式：`{序号}_{描述}.sql`

### 3.2 序号规则

- 三位数字，零填充（001, 002, 003...）
- 严格递增，不可重用
- 每个迁移一个文件

---

## 4. 迁移执行

### 4.1 自动迁移（P0）

```python
class DatabaseMigrator:
    """数据库迁移器"""
    
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self._ensure_version_table()
    
    def _ensure_version_table(self):
        """确保 schema_version 表存在"""
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                description TEXT,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.db.commit()
    
    def get_current_version(self) -> int:
        """获取当前版本"""
        cursor = self.db.execute(
            'SELECT MAX(version) FROM schema_version'
        )
        result = cursor.fetchone()
        return result[0] if result[0] else 0
    
    def migrate(self):
        """执行所有待执行的迁移"""
        current = self.get_current_version()
        migrations = self._get_pending_migrations(current)
        
        for migration in migrations:
            try:
                self._execute_migration(migration)
                self._record_version(migration)
                print(f"Applied migration {migration['version']}")
            except Exception as e:
                print(f"Migration {migration['version']} failed: {e}")
                raise
    
    def _execute_migration(self, migration: dict):
        """执行单个迁移"""
        with open(f"migrations/{migration['file']}") as f:
            sql = f.read()
        self.db.executescript(sql)
        self.db.commit()
    
    def _record_version(self, migration: dict):
        """记录迁移版本"""
        self.db.execute(
            'INSERT INTO schema_version (version, description) VALUES (?, ?)',
            (migration['version'], migration['description'])
        )
        self.db.commit()
```

### 4.2 启动时自动检查

```python
# server.py 启动时
def init_database():
    """初始化数据库并执行迁移"""
    migrator = DatabaseMigrator('arthas.db')
    migrator.migrate()
```

---

## 5. 迁移文件编写规范

### 5.1 基本结构

```sql
-- Migration: 002_add_task_logs_columns.sql
-- Description: 为 task_logs 表添加 progress 和 current_step 字段
-- Author: admin
-- Date: 2026-06-07

-- UP
ALTER TABLE task_logs ADD COLUMN progress REAL DEFAULT 0.0;
ALTER TABLE task_logs ADD COLUMN current_step INTEGER;

-- DOWN (可选，用于回滚)
-- ALTER TABLE task_logs DROP COLUMN progress;
-- ALTER TABLE task_logs DROP COLUMN current_step;
```

### 5.2 注意事项

| 规则 | 说明 |
|------|------|
| **幂等性** | 同一迁移可重复执行，不报错 |
| **原子性** | 一个迁移文件要么全部成功，要么全部失败 |
| **向前兼容** | 只添加新列，不删除旧列（P0 阶段） |
| **默认值** | 新列必须有默认值，避免破坏现有数据 |
| **索引** | 大表添加索引需评估性能影响 |

---

## 6. 回滚策略

### 6.1 P0 阶段（简化）

- 不支持自动回滚
- 回滚需手动操作：
  1. 停止服务
  2. 恢复数据库备份
  3. 重启服务

### 6.2 P1 阶段（完整）

```python
def rollback(self, target_version: int):
    """回滚到指定版本"""
    current = self.get_current_version()
    migrations = self._get_migrations_between(target_version, current)
    
    for migration in reversed(migrations):
        if 'down_sql' in migration:
            self._execute_sql(migration['down_sql'])
            self._remove_version(migration['version'])
```

---

## 7. 备份策略

### 7.1 迁移前自动备份

```python
def backup_before_migration(self):
    """迁移前备份数据库"""
    import shutil
    backup_path = f"arthas.db.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    shutil.copy2('arthas.db', backup_path)
    return backup_path
```

### 7.2 备份保留策略

| 类型 | 保留时间 | 说明 |
|------|---------|------|
| 迁移备份 | 30 天 | 每次迁移前自动备份 |
| 日常备份 | 7 天 | 每日定时备份 |

---

## 8. 当前迁移清单

| 版本 | 文件 | 说明 | 状态 |
|------|------|------|------|
| 1 | 001_initial_schema.sql | 初始表结构 | 已应用 |
| 2 | 002_add_task_logs_columns.sql | task_logs 添加 progress, current_step | 待应用 |
| 3 | 003_add_anomaly_events.sql | 异常事件表 | 待应用 |

---

## 9. 常见问题

### Q: 如何添加新字段？

1. 创建迁移文件 `migrations/003_xxx.sql`
2. 使用 `ALTER TABLE` 添加字段
3. 设置默认值
4. 重启服务自动应用

### Q: 如何处理数据迁移？

```sql
-- 数据迁移示例：将旧字段值复制到新字段
UPDATE task_logs 
SET execution_type = 'diagnosis' 
WHERE execution_type IS NULL AND capability_id IS NOT NULL;
```

### Q: SQLite 不支持 DROP COLUMN 怎么办？

P0 阶段不删除列。如需删除：
1. 创建新表
2. 复制数据
3. 删除旧表
4. 重命名新表

```sql
-- P1 阶段处理方式
CREATE TABLE task_logs_new AS SELECT id, task_id, ... FROM task_logs;
DROP TABLE task_logs;
ALTER TABLE task_logs_new RENAME TO task_logs;
```
