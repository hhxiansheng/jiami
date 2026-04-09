---
name: minimax-image-gen
description: 使用 MiniMax Image-01 模型生成图片。触发词：生成图片、生成一张图、帮我画、画一个、生成海报、生成头像、生成封面、生成 UI 图。当用户发送这些指令时触发。
---

# MiniMax 图片生成

## 快速使用

```bash
python3 scripts/generate_image.py "A cute Ragdoll cat" --aspect-ratio 16:9 --n 1
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `prompt` | (必填) | 图片描述文本，最长 1500 字符 |
| `--aspect-ratio` / `-r` | `1:1` | 宽高比 |
| `--output` / `-o` | (不下载) | 保存路径，不指定则只输出 URL |
| `--n` | `1` | 生成数量 1-9 |
| `--no-optimizer` | false | 禁用 prompt 自动优化 |

## 宽高比可选值

- `1:1` (1024x1024)
- `16:9` (1280x720)
- `4:3` (1152x864)
- `3:2` (1248x832)
- `2:3` (832x1248)
- `3:4` (864x1152)
- `9:16` (720x1280)
- `21:9` (1344x576) — 仅 image-01

## 环境变量

需要设置 `MINIMAX_API_KEY`，当前值：
```
echo $MINIMAX_API_KEY
```

## 输出格式

脚本输出 `generated_urls:<url1|url2|...>` 格式，多个 URL 用 `|` 分隔。

## 流程

1. 检查 `MINIMAX_API_KEY` 是否设置
2. 调用 `https://api.minimaxi.com/v1/image_generation`
3. 解析返回的 URL
4. 如指定 `--output` 则下载图片到本地
