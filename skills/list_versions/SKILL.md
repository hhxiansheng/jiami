# list_versions 技能

## 触发条件
- 查看历史版本时
- 回滚前确认版本时
- 审计记忆变更时

## 执行步骤

### 1. 列出所有版本
```python
import sys
sys.path.insert(0, '/home/hhxs/.openclaw/workspace/custom_memory')
from version_manager import load_index, list_versions, list_snapshots

index = load_index()
print(f"总版本数: {index['version_count']}")
print(f"追踪文件: {list(index['files'].keys())}")
```

### 2. 列出特定文件版本
```python
versions = list_versions("facts")
for v in versions:
    print(f"v{v['version']}: {v['timestamp']} - {v['reason']}")
```

### 3. 列出快照
```python
snapshots = list_snapshots()
for s in snapshots:
    print(f"{s['name']} - {s['size']} bytes - {s['created']}")
```

## 输出格式
```
【版本历史】
文件: facts.md
- v1: 2026-03-29 10:00 - 系统初始化
- v2: 2026-03-29 11:00 - 更新用户信息
- v3: 2026-03-29 12:00 - 修改偏好设置

【快照备份】
- snapshot-2026-03-29.zip (15KB)
- snapshot-2026-03-28.zip (12KB)
```

## 用途
1. 审计追踪
2. 选择回滚点
3. 确认备份完整性
