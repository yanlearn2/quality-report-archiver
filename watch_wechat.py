#!/usr/bin/env python3
"""
质量日报微信自动监控归档工具 v3.0
===================================
原理：监控微信临时缓存目录(RWTemp)，新图片出现时自动识别归档。
用文件哈希去重，避免重复处理。

原理：
  1. 在微信群里点开图片查看 → 微信生成临时缓存到 RWTemp
  2. 脚本检测到新文件 → OCR识别标题 → 归档到 ~/质量日报归档/
  3. 已处理的文件记录哈希，永不重复处理

用法:
  python3 watch_wechat.py                    # 启动监控（前台运行）
  python3 watch_wechat.py --once             # 只处理一次RWTemp中已有图片
  python3 watch_wechat.py --status           # 查看已处理的图片记录

Windows后台运行:
  start /B python D:\质量日报归档工具\watch_wechat.py
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

# ============ 配置 ============

# RWTemp 目录（微信图片临时缓存）
RW_TEMP = "/mnt/d/Users/l1711/xwechat_files/wxid_lc0np8uyxxug22_b710/temp/RWTemp"

# 归档脚本路径
ARCHIVER = "/mnt/d/质量日报归档工具/quality_report_archiver.py"

# 已处理记录数据库
DB_PATH = "/mnt/d/质量日报归档工具/processed_images.json"

# ============ 已处理记录管理 ============

def load_db():
    """加载已处理记录"""
    if os.path.exists(DB_PATH):
        with open(DB_PATH, 'r') as f:
            return json.load(f)
    return {"version": 3, "images": {}}

def save_db(db):
    """保存已处理记录"""
    with open(DB_PATH, 'w') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def file_hash(filepath: str) -> str:
    """计算文件MD5"""
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def is_processed(filename: str, filepath: str) -> tuple:
    """
    检查文件是否已处理
    返回: (是否已处理, 存档路径或None)
    """
    db = load_db()
    images = db.get("images", {})
    
    # 1. 按文件名检查
    if filename in images:
        return True, images[filename].get("archive_path")
    
    # 2. 按文件哈希检查
    try:
        h = file_hash(filepath)
        for fname, info in images.items():
            if info.get("hash") == h:
                return True, info.get("archive_path")
    except:
        pass
    
    return False, None

def mark_processed(filename: str, filepath: str, title: str, archive_path: str):
    """标记文件为已处理"""
    db = load_db()
    try:
        h = file_hash(filepath)
    except:
        h = ""
    
    db["images"][filename] = {
        "hash": h,
        "title": title,
        "archive_path": str(archive_path),
        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(filepath),
    }
    save_db(db)


# ============ 扫描与处理 ============

def scan_rwtemp():
    """扫描 RWTemp 目录，返回未处理的图片列表"""
    today = datetime.now().strftime("%Y-%m")
    results = []
    
    if not os.path.exists(RW_TEMP):
        return results
    
    # 扫描所有年月子目录
    for ym in os.listdir(RW_TEMP):
        ym_path = os.path.join(RW_TEMP, ym)
        if not os.path.isdir(ym_path):
            continue
        for f in sorted(os.listdir(ym_path)):
            if not f.endswith(('.png', '.jpg', '.jpeg', '.PNG', '.JPG')):
                continue
            full = os.path.join(ym_path, f)
            
            processed, _ = is_processed(f, full)
            if processed:
                continue
            
            results.append((ym_path, f, full))
    
    return results

def process_image(img_path: str) -> bool:
    """处理单张图片：用归档工具识别并归档"""
    print(f"  🔍 发现新图片: {os.path.basename(img_path)}")
    
    # 调用归档工具
    result = subprocess.run(
        [sys.executable, ARCHIVER, img_path],
        capture_output=True, text=True, timeout=120
    )
    
    output = result.stdout + result.stderr
    
    # 从输出中提取标题和归档路径
    title = None
    archive_path = None
    
    for line in output.split('\n'):
        m = re.search(r'✅ 识别结果:\s*(.+?)$', line)
        if m:
            title = m.group(1).strip()
        m = re.search(r'📁 已归档\s*->\s*(.+?)$', line)
        if m:
            archive_path = m.group(1).strip()
    
    if title and archive_path:
        filename = os.path.basename(img_path)
        mark_processed(filename, img_path, title, archive_path)
        print(f"  ✅ 已归档: {title}")
        return True
    else:
        print(f"  ❌ 识别失败")
        print(f"     输出: {output[:200]}")
        return False


# ============ 主逻辑 ============

def main():
    args = sys.argv[1:]
    
    if "--status" in args:
        db = load_db()
        images = db.get("images", {})
        print(f"📊 已处理图片: {len(images)} 张\n")
        for fname, info in sorted(images.items(), key=lambda x: x[1].get("processed_at", ""), reverse=True)[:20]:
            print(f"  ⏱ {info.get('processed_at', '?')}")
            print(f"     📄 {info.get('title', '?')}")
            print(f"     📁 {info.get('archive_path', '?')}")
            print()
        return
    
    if "--reset" in args:
        save_db({"version": 3, "images": {}})
        print("✅ 已清空处理记录")
        return
    
    once = "--once" in args
    
    print(f"{'='*60}")
    print(f"  质量日报微信监控工具 v3.0")
    print(f"  监控目录: {RW_TEMP}")
    print(f"  模式: {'一次性扫描' if once else '持续监控 (Ctrl+C停止)'}")
    print(f"{'='*60}\n")
    
    processed_count = 0
    
    if once:
        # 一次性扫描处理
        images = scan_rwtemp()
        if not images:
            print("📭 没有新的未处理图片")
        else:
            print(f"📸 找到 {len(images)} 张新图片\n")
            for ym_path, fname, full in images:
                if process_image(full):
                    processed_count += 1
                print()
        print(f"\n📊 本次处理: {processed_count} 张")
        return
    
    # 持续监控模式
    print("👀 正在监控，每30秒扫描一次...")
    print("   在微信群里打开图片即可自动归档\n")
    
    try:
        while True:
            images = scan_rwtemp()
            for ym_path, fname, full in images:
                if process_image(full):
                    processed_count += 1
                print()
            
            if images:
                print(f"📊 共处理: {processed_count} 张\n")
            
            time.sleep(30)
    except KeyboardInterrupt:
        print(f"\n👋 已停止。本次处理 {processed_count} 张图片")


if __name__ == "__main__":
    main() 
