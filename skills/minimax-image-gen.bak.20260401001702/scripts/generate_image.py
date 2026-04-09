#!/usr/bin/env python3
"""
MiniMax Image Generation Script
Usage: python3 generate_image.py "prompt" [--aspect-ratio 16:9] [--output /path/to/output.png] [--n 1]
"""

import argparse
import urllib.request
import urllib.error
import json
import os
import sys

API_URL = "https://api.minimaxi.com/v1/image_generation"
API_KEY = os.environ.get("MINIMAX_API_KEY", "")

def generate_image(prompt: str, aspect_ratio: str = "1:1", output_path: str = None, n: int = 1, prompt_optimizer: bool = True):
    if not API_KEY:
        print("错误: 未设置 MINIMAX_API_KEY 环境变量")
        sys.exit(1)

    payload = {
        "model": "image-01",
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "response_format": "url",
        "n": n,
        "prompt_optimizer": prompt_optimizer
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"HTTP错误 {e.code}: {error_body}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"网络错误: {e.reason}")
        sys.exit(1)

    if "data" not in result or not result["data"]:
        print(f"API返回异常: {result}")
        sys.exit(1)

    # API 返回格式: { "data": { "image_urls": ["url1", ...] } }
    image_urls = result.get("data", {}).get("image_urls", [])
    if isinstance(image_urls, list):
        urls = image_urls
    else:
        urls = [image_urls] if image_urls else []
    print("generated_urls:" + "|".join(urls))

    if output_path and urls:
        import urllib.request as ur
        out_path = output_path
        for i, url in enumerate(urls):
            if len(urls) > 1:
                name, ext = os.path.splitext(out_path)
                out_path = f"{name}_{i}{ext}"
            try:
                ur.urlretrieve(url, out_path)
                print(f"图片已保存: {out_path}")
            except Exception as e:
                print(f"下载失败: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MiniMax Image Generation")
    parser.add_argument("prompt", help="图片描述文本")
    parser.add_argument("--aspect-ratio", "-r", default="1:1",
                        help="宽高比: 1:1, 16:9, 4:3, 3:2, 2:3, 3:4, 9:16, 21:9 (默认: 1:1)")
    parser.add_argument("--output", "-o", default=None, help="保存路径")
    parser.add_argument("--n", "-n", type=int, default=1, help="生成数量 1-9 (默认: 1)")
    parser.add_argument("--no-optimizer", action="store_true", help="禁用 prompt 优化")
    args = parser.parse_args()

    generate_image(
        prompt=args.prompt,
        aspect_ratio=args.aspect_ratio,
        output_path=args.output,
        n=args.n,
        prompt_optimizer=not args.no_optimizer
    )
