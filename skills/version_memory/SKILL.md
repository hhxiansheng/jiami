# version_memory 技能

## 触发条件
修改任何 memory 文件前**必须**执行

## 执行步骤

### 1. 导入模块
```python
import sys
sys.path.insert(0, '/home/hhxs/.openclaw/workspace/custom_memory')
from version_manager import create_version, safe_write, detect_anomaly
```

### 2. 创建版本快照
```python
# 为 facts 文件创建版本
version_file = create_version("facts", "修改用户信息")

# 为 system_prompt 创建版本
version_file = create_version("system_prompt", "更新系统规则")
```

### 3. 安全写入
```python
result = safe_write(
    file_name="facts",
    content=new_content,
    reason="更新用户偏好"
)
```

## 规则（强制）
1. ⚠️ 禁止直接写入，必须先创建版本
2. 所有写入必须通过 safe_write
3. 写入前必须通过异常检测
4. 操作必须可追溯

## 示例
```python
# 错误做法 ❌
with open("facts.md", 'w') as f:
    f.write(content)

# 正确做法 ✔️
from version_manager import safe_write
safe_write("facts", content, "更新信息")
```
