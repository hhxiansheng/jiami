# inject_memory 技能

## 触发条件
**每次调用大模型前必须执行**

## 核心目的
将记忆系统中的所有相关信息拼接后注入到模型 prompt 中，实现真正的跨模型记忆。

## 执行代码
```python
import sys
sys.path.insert(0, '/home/hhxs/.openclaw/workspace/custom_memory')
from memory_manager import inject_memory

# 在调用模型前获取注入内容
memory_injection = inject_memory()
print(memory_injection)
```

## 输出格式
```
==================================================
【长期记忆系统 - 记忆注入】
==================================================
## 最近3天总结:
[总结内容]

==================================================
## 长期事实:
[事实内容]

==================================================
## 系统规则:
[规则内容]

==================================================
【以上为长期记忆，请参考后再回答】
```

## 注入位置
将上述内容注入到 system prompt 的**最前面**（在 SOUL.md 和 IDENTITY.md 内容之后）。

## 示例注入
```python
full_system_prompt = f"""
[memory_injection]

[SOUL.md 内容]
[IDENTITY.md 内容]
[其他系统内容]
"""
```

## 规则（强制）
1. ⚠️ 不允许依赖模型"自己记住"
2. ⚠️ 必须在代码层实现记忆注入
3. 必须读取真实文件
4. 不允许返回虚假数据
5. 注入内容必须包含最近3天总结 + facts + system_rules

## 自检
```python
from memory_manager import self_check

result = self_check()
if result["status"] == "ok":
    print("✔ 记忆系统正常")
else:
    print("⚠ 异常:", result["errors"])
```
