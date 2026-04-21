# app/utils/hash_utils.py
import hashlib
from pathlib import Path

def calculate_file_hash(file_path: Path) -> str:
    """计算文件的 MD5 哈希值，用于检测内容变化"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        # 分块读取，防止大文件撑爆内存
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()