# write_memory 技能

## 触发条件
- 每轮对话结束时
- 任务完成时
- 发现重要信息时
- 用户要求记录时

## 执行步骤

### 1. 写入每日日志
```python
from memory_manager import write_log

write_log(
    message="用户要求实现XXX功能",
    metadata={"任务": "功能开发", "状态": "进行中", "结论": "待完成"}
)
```

### 2. 追加长期事实
```python
from memory_manager import append_fact

append_fact(
    category="项目信息",
    fact="用户正在开发XX项目，使用XX技术栈"
)
```

### 3. 生成每日总结（可选，手动触发）
```python
from memory_manager import generate_daily_summary

generate_daily_summary()  # 今天
generate_daily_summary("2026-03-28")  # 指定日期
```

## 日志格式
```
## 2026-03-29 10:30:00

**消息**: 用户要求实现XXX功能

**元数据**: {"任务": "功能开发", "状态": "进行中"}

---
```

## 规则
1. 每轮对话至少写入一条日志
2. 重要结论必须追加到 facts
3. 写入失败重试3次
4. 失败记录到 errors/error.log

## 快捷命令
- `/log 消息` - 快速写入日志
- `/fact 类别 内容` - 快速追加事实
- `/summary` - 生成今日总结
