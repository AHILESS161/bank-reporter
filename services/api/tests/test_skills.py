from typing import Any

import pytest
from pydantic import BaseModel

from app.main import app
from app.skills.catalog import FINANCE_MODEL, ORCHESTRATOR_MODEL, build_skill_registry
from app.skills.contracts import MCPBinding, SkillManifest, SkillTransport, WorkflowManifest, WorkflowNode
from app.skills.registry import SkillInputError, SkillRegistry
from app.skills.workflows import WorkflowRegistry, WorkflowValidationError, build_workflow_registry
from fastapi.testclient import TestClient


class Host:
    def __getattr__(self, name: str):
        def execute(**arguments):
            return {"method": name, "arguments": arguments}

        return execute


def test_skill_catalog_generates_tool_schemas_and_model_policy():
    registry = build_skill_registry(Host())
    ids = {manifest.id for manifest in registry.manifests()}
    assert {
        "resolve_bank",
        "discover_documents",
        "search_professional_reports",
        "create_report",
    } <= ids
    report = registry.get("create_report").manifest
    assert report.model_policy is not None
    assert report.model_policy.primary == FINANCE_MODEL
    assert report.model_policy.fallback == ORCHESTRATOR_MODEL
    tool = next(item for item in registry.tool_specs() if item["function"]["name"] == "resolve_bank")
    assert tool["function"]["parameters"]["required"] == ["query"]
    restricted = registry.tool_specs({"resolve_bank", "list_documents"})
    assert {item["function"]["name"] for item in restricted} == {
        "resolve_bank",
        "list_documents",
    }


def test_skill_runtime_validates_before_execution():
    registry = build_skill_registry(Host())
    result = registry.execute("resolve_bank", {"query": "Сбер"})
    assert result["method"] == "tool_resolve_bank"
    with pytest.raises(SkillInputError):
        registry.execute("fetch_cbr_form", {"bank_reg_number": "1481", "form": 999})


class EchoInput(BaseModel):
    value: str


class FakeMCP:
    def invoke(self, binding: MCPBinding, arguments: dict[str, Any]) -> Any:
        return {"server": binding.server, "tool": binding.tool, **arguments}


def test_mcp_skill_uses_the_same_registry_contract():
    registry = SkillRegistry()
    manifest = SkillManifest(
        id="external_search",
        title="External search",
        description="Search through MCP",
        category="research",
        transport=SkillTransport.MCP,
        mcp=MCPBinding(server="research", tool="search"),
    )
    registry.register(manifest, EchoInput, mcp_invoker=FakeMCP())
    assert registry.execute("external_search", {"value": "МКБ"}) == {
        "server": "research",
        "tool": "search",
        "value": "МКБ",
    }


def test_workflow_registry_routes_and_rejects_cycles():
    skills = build_skill_registry(Host())
    workflows = build_workflow_registry(skills)
    assert workflows.route("Найди МСФО").id == "document_discovery"
    assert workflows.route("Сравни два периода", analysis_requested=True).id == "financial_analysis"
    financial = workflows.get("financial_analysis")
    assert any(node.skill_id == "search_professional_reports" for node in financial.nodes)
    cyclic = WorkflowManifest(
        id="cyclic_flow",
        title="Cycle",
        description="Invalid",
        nodes=[
            WorkflowNode(id="first", skill_id="resolve_bank", depends_on=["second"]),
            WorkflowNode(id="second", skill_id="list_documents", depends_on=["first"]),
        ],
    )
    with pytest.raises(WorkflowValidationError):
        WorkflowRegistry(skills).register(cyclic)


def test_constructor_api_lists_and_validates_catalog():
    client = TestClient(app)
    skills = client.get("/api/skills")
    workflows = client.get("/api/workflows")
    assert skills.status_code == 200
    assert workflows.status_code == 200
    assert any(item["id"] == "create_report" for item in skills.json())
    assert any(item["id"] == "financial_analysis" for item in workflows.json())
    payload = {
        "id": "custom_test_flow",
        "title": "Тестовая схема",
        "description": "Проверка",
        "trigger_hints": ["тестовая схема"],
        "nodes": [
            {"id": "bank", "skill_id": "resolve_bank", "depends_on": []},
            {"id": "docs", "skill_id": "discover_documents", "depends_on": ["bank"]},
        ],
    }
    validated = client.post("/api/workflows/validate", json=payload)
    assert validated.status_code == 200
    assert validated.json()["order"] == ["bank", "docs"]


def test_custom_workflow_can_be_saved_and_removed():
    client = TestClient(app)
    payload = {
        "id": "custom_saved_flow",
        "title": "Сохранённая схема",
        "description": "Проверка хранения",
        "trigger_hints": ["запусти сохранённую схему"],
        "nodes": [
            {"id": "search", "skill_id": "search_articles", "depends_on": []},
            {"id": "read", "skill_id": "read_article", "depends_on": ["search"]},
        ],
        "editable": True,
    }
    saved = client.put("/api/workflows/custom_saved_flow", json=payload)
    assert saved.status_code == 200
    assert saved.json()["editable"] is True
    listed = client.get("/api/workflows").json()
    assert any(item["id"] == "custom_saved_flow" for item in listed)
    removed = client.delete("/api/workflows/custom_saved_flow")
    assert removed.status_code == 204
    assert not any(item["id"] == "custom_saved_flow" for item in client.get("/api/workflows").json())
