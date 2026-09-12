from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from .contracts import MCPBinding, SkillManifest, SkillTransport


class MCPInvoker(Protocol):
    def invoke(self, binding: MCPBinding, arguments: dict[str, Any]) -> Any: ...


SkillHandler = Callable[[BaseModel], Any]


class SkillNotFoundError(LookupError):
    pass


class SkillInputError(ValueError):
    pass


@dataclass(frozen=True)
class RegisteredSkill:
    manifest: SkillManifest
    input_model: type[BaseModel]
    handler: SkillHandler | None = None
    mcp_invoker: MCPInvoker | None = None

    def execute(self, arguments: dict[str, Any]) -> Any:
        try:
            payload = self.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise SkillInputError(f"Некорректные параметры skill {self.manifest.id}: {exc}") from exc
        if self.manifest.transport == SkillTransport.MCP:
            if not self.mcp_invoker or not self.manifest.mcp:
                raise RuntimeError(f"MCP skill {self.manifest.id} не подключен")
            return self.mcp_invoker.invoke(self.manifest.mcp, payload.model_dump(exclude_none=True))
        if not self.handler:
            raise RuntimeError(f"Skill {self.manifest.id} доступен только как описание")
        return self.handler(payload)


class SkillRegistry:
    """Versioned registry for local, service-backed and MCP capabilities."""

    def __init__(self) -> None:
        self._skills: dict[str, RegisteredSkill] = {}

    def register(
        self,
        manifest: SkillManifest,
        input_model: type[BaseModel],
        handler: SkillHandler | None = None,
        *,
        mcp_invoker: MCPInvoker | None = None,
    ) -> None:
        if manifest.id in self._skills:
            raise ValueError(f"Skill already registered: {manifest.id}")
        schema = input_model.model_json_schema()
        schema.pop("title", None)
        registered_manifest = manifest.model_copy(update={"input_schema": schema})
        self._skills[manifest.id] = RegisteredSkill(
            registered_manifest, input_model, handler, mcp_invoker
        )

    def get(self, skill_id: str) -> RegisteredSkill:
        try:
            return self._skills[skill_id]
        except KeyError as exc:
            raise SkillNotFoundError(f"Неизвестный skill: {skill_id}") from exc

    def execute(self, skill_id: str, arguments: dict[str, Any]) -> Any:
        return self.get(skill_id).execute(arguments)

    def tool_specs(self, skill_ids: set[str] | None = None) -> list[dict[str, Any]]:
        return [
            item.manifest.as_openai_tool()
            for item in self._skills.values()
            if item.manifest.exposed_to_agent
            and (skill_ids is None or item.manifest.id in skill_ids)
        ]

    def manifests(self) -> list[SkillManifest]:
        return [item.manifest for item in self._skills.values()]

    def catalog(self) -> list[dict[str, Any]]:
        return [manifest.model_dump(mode="json") for manifest in self.manifests()]

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self._skills
