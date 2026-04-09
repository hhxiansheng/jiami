# read_memory 技能

## 触发条件
每次对话开始时自动执行，读取长期记忆系统中的数据。

## 执行步骤

### 1. 读取最近3天总结
```
文件路径: custom_memory/summaries/summary-YYYY-MM-DD.md
```

### 2. 读取长期事实
```
文件路径: custom_memory/facts/facts.md
```

### 3. 读取系统规则
```
文件路径: custom_memory/system/system_prompt.md
```

### 4. 读取最近日志
```
文件路径: custom_memory/logs/YYYY-MM-DD.md
```

## 输出格式
必须输出加载了哪些记忆，格式：
```
【记忆加载完成】
- 最近总结: 已加载X天
- 长期事实: 已加载
- 系统规则: 已加载
- 最近日志: 已加载
```

## 核心代码 (Python)
```python
import sys
sys.path.insert(0, '/home/hhxs/.openclaw/workspace/custom_memory')
from memory_manager import read_recent_summaries, read_facts, read_system_prompt, read_logs, self_check

def read_all_memory():
    result = self_check()
    summaries = read_recent_summaries(3)
    facts = read_facts()
    system = read_system_prompt()
    logs = read_logs(3)
    
    return {
        "自检": result,
        "最近总结": summaries,
        "长期事实": facts,
        "系统规则": system,
        "最近日志": logs
    }
```

## 规则
1. 必须读取真实文件，不允许返回虚假数据
2. 文件不存在时返回"（无记录）"
3. 异常时记录到 errors/error.log
