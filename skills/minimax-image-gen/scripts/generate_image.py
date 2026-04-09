#!/usr/bin/env python3
"""
MiniMax Image Generation Script
Usage: python3 generate_image.py "prompt" [--aspect-ratio 16:9] [--output /path/to/output.png] [--n 1]
       python3 generate_image.py "prompt" --feishu <receive_id> [--aspect-ratio 16:9]
"""

import argparse
import urllib.request
import urllib.error
import urllib.parse
import json
import os
import sys
import tempfile
import shutil


# ============ MiniMax API ============
API_URL = "https://api.minimaxi.com/v1/image_generation"

def get_minimax_api_key():
    """从环境变量或配置文件读取 MiniMax API Key"""
    key = os.environ.get("MINIMAX_API_KEY")
    if key:
        return key
    
    # 尝试从 openclaw.json 读取
    config_path = os.path.expanduser("~/.openclaw/openclaw.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                data = json.load(f)
                providers = data.get("models", {}).get("providers", {})
                # 优先从 minimax-portal 获取
                if "minimax-portal" in providers:
                    prov = providers["minimax-portal"]
                    if isinstance(prov, dict) and "apiKey" in prov:
                        return prov["apiKey"]
                # Fallback: 遍历找第一个 apiKey
                for prov in providers.values():
                    if isinstance(prov, dict) and "apiKey" in prov:
                        return prov["apiKey"]
        except Exception:
            pass
    return None


def generate_image(prompt: str, aspect_ratio: str = "1:1", n: int = 1, prompt_optimizer: bool = True):
    api_key = get_minimax_api_key()
    if not api_key:
        raise Exception("未找到 MINIMAX_API_KEY，请设置环境变量")

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
        "Authorization": f"Bearer {api_key}"
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        raise Exception(f"HTTP {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"网络错误: {e.reason}")

    if "data" not in result or not result["data"]:
        raise Exception(f"API返回异常: {result}")

    image_urls = result.get("data", {}).get("image_urls", [])
    if isinstance(image_urls, str):
        urls = [image_urls] if image_urls else []
    elif isinstance(image_urls, list):
        urls = image_urls
    else:
        urls = []
    
    if not urls:
        raise Exception(f"未获取到图片URL: {result}")
    
    return urls


def download_image(url: str, temp_dir: str) -> str:
    """下载图片到临时目录"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "png" in content_type:
                ext = ".png"
            elif "gif" in content_type:
                ext = ".gif"
            else:
                ext = ".jpg"
            
            filename = f"img_{os.getpid()}{ext}"
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, "wb") as f:
                f.write(resp.read())
            return filepath
    except Exception as e:
        raise Exception(f"下载图片失败: {e}")


# ============ 飞书 API ============

def get_feishu_config():
    """读取飞书配置"""
    config_path = os.path.expanduser("~/.openclaw/openclaw.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            data = json.load(f)
            feishu = data.get("channels", {}).get("feishu", {})
            return feishu.get("appId"), feishu.get("appSecret")
    return None, None


def get_feishu_token(app_id: str, app_secret: str) -> str:
    """获取飞书 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.load(resp)
            if result.get("code") == 0:
                return result.get("tenant_access_token", "")
    except Exception as e:
        print(f"[WARN] 获取飞书token失败: {e}", file=sys.stderr)
    return ""


def upload_to_feishu(image_path: str, token: str) -> str:
    """上传图片到飞书，返回 image_key"""
    url = "https://open.feishu.cn/open-apis/im/v1/images"
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    filename = os.path.basename(image_path)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image_type"\r\n\r\n'
        f"message\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + image_data + f"\r\n--{boundary}--\r\n".encode()
    
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.load(resp)
            if result.get("code") == 0:
                return result.get("data", {}).get("image_key", "")
            else:
                print(f"[WARN] 飞书上传统败: {result.get('msg')}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] 飞书上传统败: {e}", file=sys.stderr)
    return ""


def send_feishu_image(image_key: str, receive_id: str, token: str) -> dict:
    """发送图片消息"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    payload = {
        "receive_id": receive_id,
        "msg_type": "image",
        "content": json.dumps({"image_key": image_key})
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.load(resp)
            return result
    except Exception as e:
        print(f"[WARN] 飞书发消息失败: {e}", file=sys.stderr)
        return {"code": -1, "msg": str(e)}


def feishu_send(prompt: str, receive_id: str, aspect_ratio: str = "16:9") -> dict:
    """全自动流程：生成+下载+上传+发送+清理"""
    temp_dir = tempfile.mkdtemp(prefix="minimax_img_")
    local_path = None
    
    try:
        # 1. 生成图片
        print(f"[INFO] 生成图片: {prompt}", file=sys.stderr)
        urls = generate_image(prompt, aspect_ratio)
        image_url = urls[0]
        print(f"[INFO] 图片URL: {image_url}", file=sys.stderr)
        
        # 2. 下载
        print(f"[INFO] 下载图片...", file=sys.stderr)
        local_path = download_image(image_url, temp_dir)
        print(f"[INFO] 本地路径: {local_path}", file=sys.stderr)
        
        # 3. 飞书上传统获取 token
        app_id, app_secret = get_feishu_config()
        if not app_id or not app_secret:
            return {"success": False, "error": "未找到飞书配置", "image_url": image_url}
        
        token = get_feishu_token(app_id, app_secret)
        if not token:
            return {"success": False, "error": "获取飞书token失败", "image_url": image_url}
        
        # 4. 上传
        print(f"[INFO] 上传到飞书...", file=sys.stderr)
        image_key = upload_to_feishu(local_path, token)
        if not image_key:
            return {"success": False, "error": "上传飞书失败", "image_url": image_url}
        print(f"[INFO] image_key: {image_key}", file=sys.stderr)
        
        # 5. 发送
        print(f"[INFO] 发送图片消息...", file=sys.stderr)
        result = send_feishu_image(image_key, receive_id, token)
        
        if result.get("code") == 0:
            return {
                "success": True,
                "image_key": image_key,
                "image_url": image_url,
                "message_id": result.get("data", {}).get("message_id", "")
            }
        else:
            return {
                "success": False,
                "error": f"发送失败: {result.get('msg')}",
                "image_url": image_url
            }
            
    finally:
        # 6. 清理
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                print(f"[INFO] 已清理临时目录", file=sys.stderr)
            except Exception as e:
                print(f"[WARN] 清理失败: {e}", file=sys.stderr)


# ============ 主入口 ============

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MiniMax 图片生成 + 飞书发送")
    parser.add_argument("prompt", help="图片描述文本")
    parser.add_argument("--aspect-ratio", "-r", default="1:1",
                        help="宽高比: 1:1, 16:9, 4:3, 3:2, 2:3, 3:4, 9:16, 21:9 (默认: 1:1)")
    parser.add_argument("--output", "-o", default=None, help="保存路径（不指定则只输出URL）")
    parser.add_argument("--n", type=int, default=1, help="生成数量 1-9 (默认: 1)")
    parser.add_argument("--no-optimizer", action="store_true", help="禁用 prompt 优化")
    parser.add_argument("--feishu", metavar="RECEIVE_ID", default=None,
                        help="飞书接收者 open_id，指定后自动发送图片到飞书")
    
    args = parser.parse_args()
    
    # 飞书模式
    if args.feishu:
        result = feishu_send(args.prompt, args.feishu, args.aspect_ratio)
        print("---RESULT---")
        print(json.dumps(result, ensure_ascii=False))
        print("---RESULT---")
        sys.exit(0 if result.get("success") else 1)
    
    # 普通模式：只生成+下载
    api_key = get_minimax_api_key()
    if not api_key:
        print("错误: 未设置 MINIMAX_API_KEY 环境变量")
        sys.exit(1)
    
    urls = generate_image(
        args.prompt,
        args.aspect_ratio,
        args.n,
        not args.no_optimizer
    )
    print("generated_urls:" + "|".join(urls))
    
    if args.output:
        temp_dir = tempfile.mkdtemp(prefix="minimax_img_")
        try:
            for i, url in enumerate(urls):
                path = args.output
                if len(urls) > 1:
                    name, ext = os.path.splitext(args.output)
                    path = f"{name}_{i}{ext}"
                downloaded = download_image(url, temp_dir)
                shutil.move(downloaded, path)
                print(f"图片已保存: {path}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
