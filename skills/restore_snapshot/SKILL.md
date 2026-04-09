# restore_snapshot 技能

## 触发条件
- 系统严重损坏时
- 需要完整恢复时
- 灾难恢复场景

## 执行步骤

### 1. 导入模块
```python
import sys
sys.path.insert(0, '/home/hhxs/.openclaw/workspace/custom_memory')
from version_manager import restore_snapshot, list_snapshots, create_full_snapshot
```

### 2. 查看可用快照
```python
snapshots = list_snapshots()
for s in snapshots:
    print(f"{s['name']} - {s['created']}")
```

### 3. 执行恢复
```python
result = restore_snapshot("snapshot-2026-03-29.zip")
if result["success"]:
    print(f"✔ 已恢复")
    print(f"✔ 备份已创建: {result['backup_created']}")
```

### 4. 创建新快照
```python
# 创建当前系统快照
snapshot_path = create_full_snapshot()
print(f"快照已创建: {snapshot_path}")
```

## 自动恢复机制
当检测到文件损坏时：

```python
from version_manager import self_check, restore_snapshot

check = self_check()
if check["status"] == "error":
    # 找到最近快照
    snapshots = list_snapshots()
    if snapshots:
        latest = max(snapshots, key=lambda x: x['created'])
        restore_snapshot(latest['name'])
```

## 规则
1. 回滚前自动创建紧急备份
2. 不删除任何历史版本
3. 恢复后记录到错误日志
