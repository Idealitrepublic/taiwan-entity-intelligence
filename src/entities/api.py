"""Read-only Entity API with bounded search and lazy graph expansion."""
import os
from .contracts import response
from .models import uuid_string
from .repository import EntityRepository, EntityStoreUnavailable
from .search import parse_search_request
from src.relationships.models import RELATIONSHIP_TYPES


def dispatch_entity_api(path, query, repository=None):
    if path.rstrip("/") == "/api/v1/search":
        try:
            request = parse_search_request(query)
        except (TypeError, ValueError):
            return 400, {"error": "請輸入 2–100 個字並使用有效的類型與筆數 / Invalid search query, type or limit"}, None
        if os.environ.get("TEI_ENTITY_API_ENABLED") == "0":
            return 503, {"status": "not_enabled", "error": "Entity API 尚未啟用 / Entity API not enabled"}, None
        repository = repository or EntityRepository()
        try:
            result = repository.search(request.term, entity_type=request.entity_type,
                                       limit=request.limit)
        except EntityStoreUnavailable:
            return 503, {"status": "unavailable", "error": "搜尋資料庫暫時無法使用 / Search store unavailable"}, None
        return 200, response(result), None
    if path.rstrip("/") == "/api/v1/paths":
        try:
            source_id = uuid_string(query.get("source", [None])[0])
            target_id = uuid_string(query.get("target", [None])[0])
            max_depth = int(query.get("max_depth", ["3"])[0])
            if source_id == target_id or not 1 <= max_depth <= 3:
                raise ValueError("Invalid path bounds")
        except (TypeError, ValueError):
            return 400, {"error": "請提供不同的 Entity UUID，max depth 須為 1–3 / Invalid path parameters"}, None
        if os.environ.get("TEI_ENTITY_API_ENABLED") == "0":
            return 503, {"status": "not_enabled", "error": "Entity API 尚未啟用 / Entity API not enabled"}, None
        repository = repository or EntityRepository()
        try:
            result = repository.relationship_path(source_id, target_id, max_depth=max_depth)
        except EntityStoreUnavailable:
            return 503, {"status": "unavailable", "error": "關係路徑資料暫時無法使用 / Path store unavailable"}, None
        if result is None:
            return 404, {"error": "找不到已公開的起點或終點實體 / Published path endpoint not found"}, None
        return 200, response(result), None
    parts = path.strip("/").split("/")
    if len(parts) == 4 and parts[2] == "politicians":
        try:
            entity_id = uuid_string(parts[3])
            limit = int(query.get("limit", ["25"])[0])
            if not 1 <= limit <= 25:
                raise ValueError("Invalid politician relationship limit")
        except (TypeError, ValueError):
            return 400, {"error": "Politician UUID 或 limit（1–25）錯誤 / Invalid parameters"}, None
        if os.environ.get("TEI_ENTITY_API_ENABLED") == "0":
            return 503, {"status": "not_enabled", "error": "Entity API 尚未啟用 / Entity API not enabled"}, None
        repository = repository or EntityRepository()
        try:
            result = repository.politician_profile(entity_id, relationship_limit=limit)
        except EntityStoreUnavailable:
            return 503, {"status": "unavailable", "error": "立委資料暫時無法使用 / Politician data unavailable"}, None
        if result is None:
            return 404, {"error": "找不到已公開立委實體 / Published politician not found"}, None
        return 200, response(result), None
    if len(parts) == 4 and parts[2] == "graph":
        try:
            entity_id = uuid_string(parts[3])
            limit = int(query.get("limit", ["12"])[0])
            if not 1 <= limit <= 25:
                raise ValueError("Invalid graph limit")
            after = query.get("after", [None])[0]
            if after:
                uuid_string(after)
            relationship_type = query.get("relationship_type", [None])[0]
            if relationship_type and relationship_type not in RELATIONSHIP_TYPES:
                raise ValueError("Unknown relationship type")
        except (TypeError, ValueError):
            return 400, {"error": "Graph UUID、limit（1–25）或關係類型錯誤 / Invalid graph parameters"}, None
        if os.environ.get("TEI_ENTITY_API_ENABLED") == "0":
            return 503, {"status": "not_enabled", "error": "Entity API 尚未啟用 / Entity API not enabled"}, None
        repository = repository or EntityRepository()
        try:
            result = repository.graph_neighbors(entity_id, limit=limit, after=after,
                                                relationship_type=relationship_type)
        except EntityStoreUnavailable:
            return 503, {"status": "unavailable", "error": "關係圖資料暫時無法使用 / Graph store unavailable"}, None
        if result is None:
            return 404, {"error": "找不到已公開實體 / Published entity not found"}, None
        return 200, response(result), None
    if len(parts) == 5 and parts[2] == "entities" and parts[4] == "political-contributions":
        try:
            entity_id = uuid_string(parts[3])
            limit = int(query.get("limit", ["25"])[0])
            if not 1 <= limit <= 25:
                raise ValueError("Invalid contribution limit")
            after = query.get("after", [None])[0]
            if after:
                uuid_string(after)
        except (TypeError, ValueError):
            return 400, {"error": "Entity UUID 或 limit（1–25）錯誤 / Invalid parameters"}, None
        if os.environ.get("TEI_ENTITY_API_ENABLED") == "0":
            return 503, {"status": "not_enabled", "error": "Entity API 尚未啟用 / Entity API not enabled"}, None
        repository = repository or EntityRepository()
        try:
            result = repository.political_contributions(entity_id, limit=limit, after=after)
        except EntityStoreUnavailable:
            return 503, {"status": "unavailable", "error": "政治獻金資料暫時無法使用 / Contribution data unavailable"}, None
        if result is None:
            return 404, {"error": "找不到已公開公司或政治人物 / Published entity not found"}, None
        return 200, response(result), None
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
    # Schema is additive and read-only to public clients. Keep an emergency kill
    # switch instead of requiring an environment mutation for every deployment.
    if os.environ.get("TEI_ENTITY_API_ENABLED") == "0":
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
    return 200, response(result), None
