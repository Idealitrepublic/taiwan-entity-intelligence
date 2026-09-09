"""Phase 1 read contract. No global search or multi-hop traversal."""
import os
from .models import uuid_string
from .repository import EntityRepository, EntityStoreUnavailable
from src.relationships.models import RELATIONSHIP_TYPES


def dispatch_entity_api(path, query, repository=None):
    parts = path.strip("/").split("/")
    valid = (len(parts) == 4 and parts[2] in ("entities", "relationships", "evidence")) or (
        len(parts) == 5 and parts[2] == "entities" and parts[4] == "relationships")
    if not valid:
        return 404, {"error": "Not found / 找不到端點"}, None
    try:
        record_id = uuid_string(parts[3])
        limit = int(query.get("limit", ["25"])[0])
        if not 1 <= limit <= 50:
            raise ValueError("Invalid limit")
        after = query.get("after", [None])[0]
        if after:
            uuid_string(after)
        relationship_type = query.get("relationship_type", [None])[0]
        if relationship_type and relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError("Unknown relationship type")
    except (ValueError, TypeError):
        return 400, {"error": "Invalid UUID, limit (1–50) or relationship type / 查詢參數錯誤"}, None
    if os.environ.get("TEI_ENTITY_API_ENABLED") != "1":
        return 503, {"status": "not_enabled", "error": "Entity API 尚未啟用 / Entity API not enabled"}, None
    repository = repository or EntityRepository()
    try:
        if len(parts) == 5:
            if not repository.entity(record_id):
                result = None
            else:
                result = repository.relationships(record_id, limit=limit, after=after,
                                                  relationship_type=relationship_type)
        else:
            method = {"entities": "entity", "relationships": "relationship", "evidence": "evidence"}[parts[2]]
            result = getattr(repository, method)(record_id)
    except EntityStoreUnavailable:
        return 503, {"status": "unavailable", "error": "實體資料庫暫時無法使用 / Entity store unavailable"}, None
    if result is None:
        return 404, {"error": "找不到已公開紀錄 / Published record not found"}, None
    return 200, {"api_version": "1", "data": result}, None
