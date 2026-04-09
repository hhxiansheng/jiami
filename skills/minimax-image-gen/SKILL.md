---
name: minimax-image-gen
description: 使用 MiniMax Image-01 模型生成图片。触发词：生成图片、生成一张图、帮我画、画一个、生成海报、生成头像、生成封面、生成 UI 图。当用户发送这些指令时触发。
---

# MiniMax 图片生成

## 全自动飞书模式（推荐）

```bash
python3 scripts/generate_image.py "描述" --feishu <receive_id> [--aspect-ratio 16:9]
```

自动完成：生成图片 → 下载 → 上传飞书 → 发送 → 清理临时文件

**示例：**
```bash
python3 scripts/generate_image.py "一只橘色小猫" --feishu ou_xxx --aspect-ratio 1:1
```

## 普通模式（只生成+下载）

```bash
python3 scripts/generate_image.py "A cute cat" --output /tmp/cat.png --aspect-ratio 16:9
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `prompt` | (必填) | 图片描述文本 |
| `--feishu` | - | 飞书接收者 open_id，指定后全自动发送图片 |
| `--aspect-ratio` / `-r` | `1:1` | 宽高比 |
| `--output` / `-o` | (不下载) | 保存路径 |
| `--n` | `1` | 生成数量 1-9 |
| `--no-optimizer` | false | 禁用 prompt 优化 |

## 宽高比

`1:1` `16:9` `4:3` `3:2` `2:3` `3:4` `9:16` `21:9`

## 输出格式

**全自动模式** 输出：
```
---RESULT---
{"success": true, "image_key": "img_v3_xxx", "image_url": "https://...", "message_id": "om_xxx"}
---RESULT---
```

**普通模式** 输出：
```
generated_urls:url1|url2|...
```

## 流程（全自动模式）

1. 调用 MiniMax `image-01` 模型生成图片
2. 下载图片到临时目录
3. 上传到飞书 `im/v1/images` 获取 `image_key`
4. 发送图片消息到指定用户
5. 自动清理临时文件
6. 失败时 fallback 为返回图片 URL
