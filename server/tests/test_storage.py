"""Storage layer: tenant scoping on every read/update (AC 2)."""

from pt_agent.storage import MemoryStore
from pt_agent.storage.supabase import _merge, _split


def test_memory_store_scopes_by_org():
    s = MemoryStore()
    s.insert("projects", {"id": "p1", "organization_id": "org_a", "name": "A"})
    assert s.get("projects", "p1", organization_id="org_a")["name"] == "A"
    assert s.get("projects", "p1", organization_id="org_b") is None
    assert s.update("projects", "p1", organization_id="org_b", patch={"name": "X"}) is None
    assert s.list("projects", organization_id="org_b") == []


def test_supabase_row_split_and_merge_roundtrip():
    row = {
        "id": "scope_1", "organization_id": "org_a", "project_id": "p1",
        "version": 1, "status": "draft", "authorization_id": "auth_1",
        "targets": [{"scheme": "https", "host": "a.example"}], "budget": {"max_requests": 5},
    }
    split = _split("scope_versions", row)
    assert "targets" not in split and split["data"]["targets"] == row["targets"]
    assert _merge(dict(split)) == row
