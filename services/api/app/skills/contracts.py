from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SkillTransport(StrEnum):
    LOCAL = "local"
    SERVICE = "service"
    MCP = "mcp"


class SideEffects(StrEnum):
    READ_ONLY = "read_only"
    LOCAL_WRITE = "local_write"


class ModelPolicy(BaseModel):
    primary: str
    fallback: str | None = None
    max_attempts: int = Field(2, ge=1, le=5)


class MCPBinding(BaseModel):
    server: str
    tool: str


class SkillManifest(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    version: str = "1.0.0"
    title: str
    description: str
    category: str
    transport: SkillTransport = SkillTransport.LOCAL
    side_effects: SideEffects = SideEffects.READ_ONLY
    permissions: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(60, ge=1, le=900)
    exposed_to_agent: bool = True
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    model_policy: ModelPolicy | None = None
    mcp: MCPBinding | None = None

    @model_validator(mode="after")
    def validate_transport(self) -> SkillManifest:
        if self.transport == SkillTransport.MCP and not self.mcp:
            raise ValueError("MCP skill requires a server and tool binding")
        if self.transport != SkillTransport.MCP and self.mcp:
            raise ValueError("MCP binding is only valid for MCP skills")
        return self

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.id,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class WorkflowNode(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    skill_id: str
    depends_on: list[str] = Field(default_factory=list)
    optional: bool = False
    note: str = ""


class WorkflowManifest(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    version: str = "1.0.0"
    title: str
    description: str
    trigger_hints: list[str] = Field(default_factory=list)
    nodes: list[WorkflowNode]
    editable: bool = False

    @model_validator(mode="after")
    def unique_nodes(self) -> WorkflowManifest:
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Workflow node ids must be unique")
        return self
