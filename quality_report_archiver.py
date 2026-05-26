#!/usr/bin/env python3
"""
质量日报自动归档工具 v2.0
每天处理3张质量日报图片，自动识别标题、提取日期、分类归档。

默认使用 MinerU 在线API（高精度），也可切换为 Qwen3-VL（低成本快响应）。

用法:
    python3 quality_report_archiver.py 图片1.png 图片2.png 图片3.png
    python3 quality_report_archiver.py --mode qwen 图片1.png 图片2.png 图片3.png
    python3 quality_report_archiver.py --dir D:\质量日报\
    python3 quality_report_archiver.py --mode qwen --dir D:\质量日报\

配置:
    在 .env 文件中设置 MINERU_TOKEN 和 SILICONFLOW_API_KEY
    参考 .env.template 文件格式
"""

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from PIL import Image

# ============ 配置加载 ============

def load_env():
    """从 .env 文件加载环境变量"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

load_env()

# MinerU Token（从环境变量或.env文件读取）
MINERU_TOKEN = os.environ.get("MINERU_TOKEN", "")

# SiliconFlow API Key（Qwen回退用，从环境变量或.env文件读取）
SILICONFLOW_KEY = os.environ.get("SILICONFLOW_API_KEY", "")

# 默认引擎: mineru（高精度）/ qwen（快速低成本）
DEFAULT_MODE = "mineru"

# ============ MinerU 引擎 ============

# 归档根目录
ARCHIVE_ROOT = Path.home() / "质量日报归档"

# ============ MinerU 引擎 ============

MINERU_BASE = "https://mineru.net"

def mineru_process(image_path: Path) -> tuple:
    """
    使用 MinerU 在线API提取标题
    返回: (标题文字, 耗时秒)
    """
    print(f"  📄 正在处理: {image_path.name} [引擎: MinerU]")
    headers = {"Authorization": f"Bearer {MINERU_TOKEN}"}

    try:
        # Step 1: 创建解析任务
        t0 = time.time()
        resp = urllib.request.Request(
            f"{MINERU_BASE}/api/v1/agent/parse/file",
            data=json.dumps({"file_name": image_path.name}).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(resp, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        
        if data.get("code") != 0:
            print(f"  ❌ 创建任务失败: {data.get('msg', '未知错误')}")
            return None, time.time() - t0

        task_id = data["data"]["task_id"]
        upload_url = data["data"]["file_url"]

        # Step 2: 上传文件（使用requests库直接PUT二进制）
        try:
            import requests as req_lib
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"],
                         capture_output=True, timeout=30)
            import requests as req_lib
        
        with open(image_path, "rb") as f:
            upload_resp = req_lib.put(upload_url, data=f, timeout=60)
        if upload_resp.status_code != 200:
            detail = upload_resp.text[:200]
            print(f"  ❌ 文件上传失败: HTTP {upload_resp.status_code} - {detail}")
            return None, time.time() - t0

        # Step 3: 轮询结果
        for i in range(60):
            time.sleep(3)
            poll_req = urllib.request.Request(
                f"{MINERU_BASE}/api/v1/agent/parse/{task_id}",
                headers=headers
            )
            with urllib.request.urlopen(poll_req, timeout=15) as r:
                result = json.loads(r.read().decode("utf-8"))
            
            state = result.get("data", {}).get("state", "unknown")
            if state == "done":
                elapsed = time.time() - t0
                md_url = result.get("data", {}).get("markdown_url", "")

                if md_url:
                    # 下载Markdown，提取标题
                    md_req = urllib.request.Request(md_url)
                    with urllib.request.urlopen(md_req, timeout=30) as r:
                        md_content = r.read().decode("utf-8")
                    
                    # 策略1: 取第一行（不含HTML标签）
                    first_line = re.sub(r'<[^>]+>', '', md_content.strip().split("\n")[0]).strip()
                    first_line = re.sub(r'^#+\s*', '', first_line).strip()
                    
                    # 策略2: 如果第一行不含日期，在全文搜索标题模式
                    if not re.search(r'\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日', first_line):
                        # 搜索 Markdown 标题行
                        title_match = re.search(
                            r'(?:^|\n)#{1,3}\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日.+?(?:质量报表|质检报表|日报))',
                            md_content
                        )
                        if title_match:
                            title = title_match.group(1).strip()
                        else:
                            # 搜索纯文本中的日期+报表模式
                            plain = re.sub(r'<[^>]+>', '', md_content)
                            title_match = re.search(
                                r'(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日.+?(?:质量报表|质检报表|日报))',
                                plain
                            )
                            title = title_match.group(1).strip() if title_match else first_line
                    else:
                        title = first_line
                    print(f"  ✅ 识别结果: {title}")
                    print(f"     (耗时{elapsed:.1f}s, MinerU全文提取)")
                    # 校验标题有效性：必须包含日期模式或少于50个中文字符
                    if not re.search(r'\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日', title) \
                       and len(title) > 50:
                        print(f"  ⚠️ 提取内容非有效标题(长度{len(title)}字符)，回退到Qwen...")
                        title_q, elapsed_q = qwen_process(image_path)
                        if title_q:
                            return title_q, elapsed + elapsed_q
                    return title, elapsed
                else:
                    # MinerU完成但未找到标题行，回退到Qwen
                    print(f"  ⚠️ MinerU未找到独立标题，回退到Qwen...")
                    title_q, elapsed_q = qwen_process(image_path)
                    if title_q:
                        return title_q, elapsed + elapsed_q
                    print(f"  ❌ 标题提取失败")
                    return None, elapsed

            elif state == "failed":
                err = result.get("data", {}).get("err_msg", "未知错误")
                print(f"  ❌ 解析失败: {err}")
                return None, time.time() - t0
            elif state == "running":
                progress = result.get("data", {}).get("extract_progress", {})
                if progress:
                    p = progress
                    print(f"  ⏳ 解析中... ({p.get('extracted_pages',0)}/{p.get('total_pages','?')}页)", end="\r")
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')[:200]
        print(f"  ❌ API错误 {e.code}: {body}")
        return None, time.time() - t0
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return None, time.time() - t0
    
    print(f"  ⏰ 轮询超时")
    return None, time.time() - t0


# ============ Qwen3-VL 引擎 ============

QWEN_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
QWEN_PROMPT = (
    "这张图片是一份质量日报报表的截图。"
    "请只提取并输出这个报表的完整标题，"
    "例如格式为'2026年05月16日一期中控质量报表'、'2026年05月16日MHP中控质量报表'、'2026年05月16日1.5期黑粉线钻控质量报表'。"
    "只输出标题本身，不要有其他内容。"
)

def qwen_process(image_path: Path) -> tuple:
    """
    使用 Qwen3-VL-8B-Instruct 提取标题
    返回: (标题文字, 耗时秒)
    """
    print(f"  📄 正在处理: {image_path.name} [引擎: Qwen3-VL-8B]")

    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"  ❌ 无法打开图片: {e}")
        return None, 0

    w, h = img.size
    if max(w, h) > 2000:
        scale = 2000 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    if img.mode == 'RGBA':
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=92)
    data_url = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"

    t0 = time.time()
    payload = {
        "model": QWEN_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": QWEN_PROMPT}
            ]
        }]
    }

    req = urllib.request.Request(
        "https://api.siliconflow.cn/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {SILICONFLOW_KEY}",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"].strip()
            usage = result.get("usage", {})
            elapsed = time.time() - t0
            cost = (usage.get("prompt_tokens", 0) * 0.5 +
                    usage.get("completion_tokens", 0) * 2) / 1_000_000
            print(f"  ✅ 识别结果: {content}")
            print(f"     (耗时{elapsed:.1f}s, 费用¥{cost:.6f})")
            return content, elapsed
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')[:200]
        print(f"  ❌ API错误 {e.code}: {body}")
        return None, time.time() - t0
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return None, time.time() - t0


# ============ 标题解析与归档 ============

def parse_title(title: str) -> dict:
    """从标题中提取日期和报表类型"""
    result = {
        'raw': title,
        'date': None, 'year': None, 'month': None, 'day': None,
        'type_name': None, 'type_category': None,
    }

    date_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", title)
    if date_match:
        y, m, d = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
        result.update(year=y, month=m, day=d, date=f"{y:04d}-{m:02d}-{d:02d}")

    type_lower = title.lower()
    if "一期" in title and ("中控" in title or "质量" in title):
        result['type_name'] = "一期中控"
        result['type_category'] = "一期中控质量报表"
    elif "mhp" in type_lower and ("中控" in title or "质量" in title):
        result['type_name'] = "MHP中控"
        result['type_category'] = "MHP中控质量报表"
    elif "1.5期" in title or "1.5" in title:
        if "黑粉" in title:
            result['type_name'] = "1.5期黑粉线钻控"
            result['type_category'] = "1.5期黑粉线钻控质量报表"
        elif "mhp" in type_lower:
            result['type_name'] = "1.5期MHP中控"
            result['type_category'] = "1.5期MHP中控质量报表"
        else:
            result['type_name'] = "1.5期"
            result['type_category'] = "1.5期质量报表"
    elif "二期" in title:
        result['type_name'] = "二期"
        result['type_category'] = "二期质量报表"
    else:
        if date_match:
            after_date = re.sub(r'质量报表$|质检报表$|日报$', '',
                                title[date_match.end():]).strip()
            result['type_name'] = after_date or "未知类型"
            result['type_category'] = (after_date + "质量报表") if after_date else "其他"
        else:
            result['type_name'] = "未知类型"
            result['type_category'] = "其他"

    return result


def archive_file(image_path: Path, info: dict) -> Path:
    """归档图片到分类目录"""
    category = info['type_category']
    date_str = info['date'] or "未知日期"
    type_name = info['type_name'] or "未知"

    dest_dir = ARCHIVE_ROOT / category
    dest_dir.mkdir(parents=True, exist_ok=True)

    suffix = image_path.suffix
    new_name = f"{date_str}_{type_name}{suffix}"
    dest_path = dest_dir / new_name

    counter = 1
    while dest_path.exists():
        new_name = f"{date_str}_{type_name}_{counter}{suffix}"
        dest_path = dest_dir / new_name
        counter += 1

    shutil.copy2(image_path, dest_path)
    print(f"  📁 已归档 -> {dest_path}")
    return dest_path


def print_summary(results):
    """打印处理汇总"""
    print(f"\n{'='*60}")
    print(f"  📊 处理汇总")
    print(f"{'='*60}")
    success = [r for r in results if r['title']]
    failed = [r for r in results if not r['title']]
    for r in success:
        print(f"  ✅ {r['file'].name}")
        print(f"     标题: {r['title']}")
        print(f"     日期: {r['info']['date']}  |  类型: {r['info']['type_name']}")
        print(f"     归档: {r['dest']}")
    for r in failed:
        print(f"  ❌ {r['file'].name}  - 识别失败")
    print(f"\n  成功: {len(success)} / 总数: {len(results)}")
    print(f"  归档目录: {ARCHIVE_ROOT}")


# ============ 主入口 ============

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return

    # 解析 --mode 参数
    mode = DEFAULT_MODE
    filtered_args = []
    i = 0
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1].lower()
            i += 2
        else:
            filtered_args.append(args[i])
            i += 1
    args = filtered_args

    if mode not in ("mineru", "qwen"):
        print(f"❌ 未知模式: {mode}，可选: mineru / qwen")
        return

    # 收集图片路径
    image_paths = []
    if args and args[0] == "--dir" and len(args) >= 2:
        img_dir = Path(args[1])
        if not img_dir.exists():
            print(f"❌ 目录不存在: {img_dir}")
            return
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"):
            image_paths.extend(sorted(img_dir.glob(ext)))
        if not image_paths:
            print(f"❌ 目录中没有图片: {img_dir}")
            return
        print(f"📂 从目录 {img_dir} 找到 {len(image_paths)} 张图片")
    else:
        for p in args:
            path = Path(p)
            if path.exists():
                image_paths.append(path)
            else:
                # Windows路径转换
                win = p.replace("D:\\", "/mnt/d/").replace("\\", "/")
                path = Path(win)
                if path.exists():
                    image_paths.append(path)
                else:
                    print(f"⚠️ 文件不存在: {p}")

    if not image_paths:
        print("❌ 没有找到有效的图片文件")
        return

    engine_name = "MinerU" if mode == "mineru" else "Qwen3-VL-8B"
    print(f"\n{'='*60}")
    print(f"  📋 质量日报归档工具 v2.0")
    print(f"  引擎: {engine_name} (默认)")
    print(f"  待处理: {len(image_paths)} 张图片")
    print(f"{'='*60}\n")

    results = []
    process_fn = mineru_process if mode == "mineru" else qwen_process

    for img_path in image_paths:
        title, elapsed = process_fn(img_path)
        info = parse_title(title) if title else {}
        dest = None
        if title and info.get('date'):
            dest = archive_file(img_path, info)
        results.append({
            'file': img_path, 'title': title,
            'info': info, 'dest': dest,
        })
        print()

    print_summary(results)


if __name__ == "__main__":
    main()
