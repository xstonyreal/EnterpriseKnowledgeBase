# app/services/domain_service.py

import os
import json
from datetime import datetime
from typing import List, Dict, Optional

from app.config import settings
from app.core.logger import logger

# ==========================================
# 常量定義
# ==========================================

MANIFEST_DIR = os.path.join(settings.DATA_DIR, "manifest")
DOMAINS_FILE = os.path.join(MANIFEST_DIR, "domains.json")


# ==========================================
# 內部輔助函數
# ==========================================

def _ensure_manifest_dir():
    """確保 manifest 目錄存在"""
    os.makedirs(MANIFEST_DIR, exist_ok=True)


def _load_domains_from_json() -> Dict:
    """從 JSON 文件加載域數據"""
    _ensure_manifest_dir()

    if not os.path.exists(DOMAINS_FILE):
        return {"version": "1.0", "domains": []}

    try:
        with open(DOMAINS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加載 domains.json 失敗: {e}")
        return {"version": "1.0", "domains": []}


def _save_domains_to_json(data: Dict) -> bool:
    """保存域數據到 JSON 文件"""
    _ensure_manifest_dir()

    try:
        with open(DOMAINS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存 domains.json 失敗: {e}")
        return False


def _scan_physical_folders() -> List[str]:
    """掃描物理文件夾，返回域名稱列表"""
    uploads_dir = settings.DATA_UPLOAD_DIR
    if not os.path.exists(uploads_dir):
        os.makedirs(uploads_dir, exist_ok=True)
        return []

    folders = []
    for item in os.listdir(uploads_dir):
        item_path = os.path.join(uploads_dir, item)
        if os.path.isdir(item_path) and not item.startswith(('.', '_')):
            folders.append(item)
    return folders


def _create_physical_folder(name: str) -> bool:
    """創建物理文件夾"""
    folder_path = os.path.join(settings.DATA_UPLOAD_DIR, name)
    try:
        os.makedirs(folder_path, exist_ok=True)
        logger.info(f"📁 已創建物理文件夾: {folder_path}")
        return True
    except Exception as e:
        logger.error(f"創建文件夾失敗: {e}")
        return False


def _rename_physical_folder(old_name: str, new_name: str) -> bool:
    """重命名物理文件夾"""
    old_path = os.path.join(settings.DATA_UPLOAD_DIR, old_name)
    new_path = os.path.join(settings.DATA_UPLOAD_DIR, new_name)

    if not os.path.exists(old_path):
        logger.error(f"源文件夾不存在: {old_path}")
        return False

    if os.path.exists(new_path):
        logger.error(f"目標文件夾已存在: {new_path}")
        return False

    try:
        os.rename(old_path, new_path)
        logger.info(f"📁 已重命名文件夾: {old_name} -> {new_name}")
        return True
    except Exception as e:
        logger.error(f"重命名文件夾失敗: {e}")
        return False


def _delete_physical_folder(name: str) -> bool:
    """刪除物理文件夾"""
    folder_path = os.path.join(settings.DATA_UPLOAD_DIR, name)

    if not os.path.exists(folder_path):
        logger.warning(f"文件夾不存在，跳過: {folder_path}")
        return True

    try:
        import shutil
        shutil.rmtree(folder_path)
        logger.info(f"📁 已刪除物理文件夾: {folder_path}")
        return True
    except Exception as e:
        logger.error(f"刪除文件夾失敗: {e}")
        return False


# ==========================================
# 公開 API
# ==========================================

def init_domains() -> None:
    """
    初始化域數據：掃描物理文件夾，同步到 JSON
    首次運行時自動將現有文件夾導入為域
    """
    logger.info("🔄 正在初始化域數據...")

    # 1. 讀取 JSON 中的域
    json_data = _load_domains_from_json()
    json_domains = {d["name"]: d for d in json_data.get("domains", [])}

    # 2. 掃描物理文件夾
    physical_folders = _scan_physical_folders()

    # 3. 同步：將物理文件夾中存在的域添加到 JSON
    changed = False
    for folder in physical_folders:
        if folder not in json_domains:
            json_domains[folder] = {
                "name": folder,
                "created_at": datetime.now().isoformat(),
                "description": "",
                "status": "active"
            }
            changed = True
            logger.info(f"✅ 發現物理文件夾，已同步: {folder}")

    # 4. 保存
    if changed:
        json_data["domains"] = list(json_domains.values())
        _save_domains_to_json(json_data)
        logger.info(f"✅ 域初始化完成，共 {len(json_domains)} 個域")
    else:
        logger.info(f"✅ 域初始化完成，共 {len(json_domains)} 個域（無變化）")


def get_all_domains() -> List[Dict]:
    """獲取所有域（含已刪除）"""
    json_data = _load_domains_from_json()
    return json_data.get("domains", [])


def get_active_domains() -> List[str]:
    """
    獲取啟用的域名稱列表（用於 UI 選擇）
    數據來源僅 JSON，無兜底
    """
    json_data = _load_domains_from_json()
    domains = [d["name"] for d in json_data.get("domains", []) if d.get("status") == "active"]
    return sorted(domains)


def get_domain_info(domain_name: str) -> Optional[Dict]:
    """獲取單個域的信息"""
    all_domains = get_all_domains()
    for d in all_domains:
        if d["name"] == domain_name:
            return d
    return None


def create_domain(name: str, description: str = "") -> bool:
    """
    創建新域
    1. 創建物理文件夾
    2. 更新 JSON
    """
    if not name or name.strip() == "":
        logger.error("域名稱不能為空")
        return False

    name = name.strip()

    # 檢查是否已存在（含已刪除）
    existing = get_domain_info(name)
    if existing:
        if existing.get("status") == "active":
            logger.warning(f"域已存在: {name}")
            return False
        else:
            # 軟刪除狀態，重新激活
            return update_domain(name, description=description, reactivate=True)

    # 1. 創建物理文件夾
    if not _create_physical_folder(name):
        return False

    # 2. 更新 JSON
    json_data = _load_domains_from_json()
    new_domain = {
        "name": name,
        "created_at": datetime.now().isoformat(),
        "description": description,
        "status": "active"
    }
    json_data["domains"].append(new_domain)
    success = _save_domains_to_json(json_data)

    if success:
        logger.info(f"✅ 已創建域: {name}")
    return success


def update_domain(
        old_name: str,
        new_name: str = None,
        description: str = None,
        reactivate: bool = False
) -> bool:
    """
    更新域信息（重命名、修改描述、重新激活）
    """
    domain_info = get_domain_info(old_name)
    if not domain_info:
        logger.error(f"域不存在: {old_name}")
        return False

    # 重新激活（從軟刪除恢復）
    if reactivate:
        json_data = _load_domains_from_json()
        for d in json_data.get("domains", []):
            if d["name"] == old_name:
                d["status"] = "active"
                d.pop("deleted_at", None)
                if description is not None:
                    d["description"] = description
                d["updated_at"] = datetime.now().isoformat()
                break
        return _save_domains_to_json(json_data)

    # 重命名物理文件夾
    if new_name and new_name != old_name:
        if get_domain_info(new_name):
            logger.error(f"目標域名稱已存在: {new_name}")
            return False

        if not _rename_physical_folder(old_name, new_name):
            return False

    # 更新 JSON
    json_data = _load_domains_from_json()
    for d in json_data.get("domains", []):
        if d["name"] == old_name:
            if new_name:
                d["name"] = new_name
            if description is not None:
                d["description"] = description
            d["updated_at"] = datetime.now().isoformat()
            break

    success = _save_domains_to_json(json_data)
    if success:
        logger.info(f"✅ 已更新域: {old_name} -> {new_name or old_name}")
    return success


def delete_domain(name: str, hard: bool = False) -> bool:
    """
    刪除域
    - soft: 僅標記 status = "deleted"，保留物理文件夾
    - hard: 刪除物理文件夾 + 從 JSON 移除
    """
    domain_info = get_domain_info(name)
    if not domain_info:
        logger.error(f"域不存在: {name}")
        return False

    if hard:
        # 硬刪除：刪除物理文件夾
        if not _delete_physical_folder(name):
            return False

        # 從 JSON 移除
        json_data = _load_domains_from_json()
        json_data["domains"] = [d for d in json_data.get("domains", []) if d["name"] != name]
        success = _save_domains_to_json(json_data)
    else:
        # 軟刪除：僅標記
        json_data = _load_domains_from_json()
        for d in json_data.get("domains", []):
            if d["name"] == name:
                d["status"] = "deleted"
                d["deleted_at"] = datetime.now().isoformat()
                break
        success = _save_domains_to_json(json_data)

    if success:
        logger.info(f"✅ 已{'硬' if hard else '軟'}刪除域: {name}")
    return success


def sync_physical_to_json() -> int:
    """
    手動同步：掃描物理文件夾，將新增文件夾同步到 JSON
    返回新增數量
    """
    physical_folders = set(_scan_physical_folders())
    json_data = _load_domains_from_json()
    existing_names = {d["name"] for d in json_data.get("domains", [])}

    new_count = 0
    for folder in physical_folders:
        if folder not in existing_names:
            json_data["domains"].append({
                "name": folder,
                "created_at": datetime.now().isoformat(),
                "description": "",
                "status": "active"
            })
            new_count += 1
            logger.info(f"✅ 同步物理文件夾: {folder}")

    if new_count > 0:
        _save_domains_to_json(json_data)

    return new_count