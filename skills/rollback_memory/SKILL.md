# rollback_memory 技能

## 触发条件
- 记忆文件损坏时
- 误写需要恢复时
- 用户主动要求回滚时

## 执行步骤

### 1. 导入模块
```python
import sys
sys.path.insert(0, '/home/hhxs/.openclaw/workspace/custom_memory')
from version_manager import rollback_single, rollback_memory, get_version_info
```

### 2. 查看可用版本
```python
# 查看 facts 的所有版本
versions = list_versions("facts")
for v in versions:
    print(f"v{v['version']} - {v['timestamp']} - {v['reason']}")
```

### 3. 执行回滚
```python
# 回滚到 v1
result = rollback_single("facts", 1)

# 或使用完整回滚函数
result = rollback_memory(target_file="facts", target_version=1)
```

### 4. 验证恢复
```python
if result["success"]:
    print(f"✔ 已回滚到 v{result['version']}")
    print(f"✔ 文件已恢复: {result['restored_from']}")
```

## 回滚单个文件
```python
rollback_single(file_name="facts", target_version=1)
```

## 回滚整个系统
```python
from version_manager import restore_snapshot

# 列出可用快照
snapshots = list_snapshots()

# 恢复指定快照
restore_snapshot("snapshot-2026-03-29.zip")
```

## 规则
1. 回滚前自动创建紧急备份
2. 所有操作记录到 index.json
3. 紧急情况可用 restore_snapshot 恢复整个系统
