from __future__ import annotations

from collections import deque

from .contracts import WorkflowManifest, WorkflowNode
from .registry import SkillRegistry


class WorkflowValidationError(ValueError):
    pass


class WorkflowRegistry:
    def __init__(self, skills: SkillRegistry) -> None:
        self.skills = skills
        self._workflows: dict[str, WorkflowManifest] = {}

    def register(self, workflow: WorkflowManifest) -> None:
        if workflow.id in self._workflows:
            raise ValueError(f"Workflow already registered: {workflow.id}")
        self.validate(workflow)
        self._workflows[workflow.id] = workflow

    def validate(self, workflow: WorkflowManifest) -> list[str]:
        node_ids = {node.id for node in workflow.nodes}
        errors: list[str] = []
        for node in workflow.nodes:
            if node.skill_id not in self.skills:
                errors.append(f"Неизвестный skill: {node.skill_id}")
            for dependency in node.depends_on:
                if dependency not in node_ids:
                    errors.append(f"Узел {node.id} зависит от отсутствующего узла {dependency}")
                if dependency == node.id:
                    errors.append(f"Узел {node.id} не может зависеть от себя")
        if errors:
            raise WorkflowValidationError("; ".join(errors))
        self._topological_nodes(workflow)
        return []

    def _topological_nodes(self, workflow: WorkflowManifest) -> list[WorkflowNode]:
        by_id = {node.id: node for node in workflow.nodes}
        outgoing: dict[str, list[str]] = {node.id: [] for node in workflow.nodes}
        indegree = {node.id: len(node.depends_on) for node in workflow.nodes}
        for node in workflow.nodes:
            for dependency in node.depends_on:
                outgoing[dependency].append(node.id)
        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        ordered: list[WorkflowNode] = []
        while queue:
            node_id = queue.popleft()
            ordered.append(by_id[node_id])
            for child in outgoing[node_id]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(ordered) != len(workflow.nodes):
            raise WorkflowValidationError("Workflow содержит циклическую зависимость")
        return ordered

    def get(self, workflow_id: str) -> WorkflowManifest:
        try:
            return self._workflows[workflow_id]
        except KeyError as exc:
            raise LookupError(f"Неизвестный workflow: {workflow_id}") from exc

    def ordered_nodes(self, workflow_id: str) -> list[WorkflowNode]:
        return self._topological_nodes(self.get(workflow_id))

    def catalog(self) -> list[dict]:
        return [workflow.model_dump(mode="json") for workflow in self._workflows.values()]

    def route(self, request: str, *, analysis_requested: bool = False) -> WorkflowManifest:
        text = request.casefold()
        for workflow in self._workflows.values():
            if workflow.editable and any(hint.casefold() in text for hint in workflow.trigger_hints):
                return workflow
        if analysis_requested:
            return self.get("financial_analysis")
        if any(token in text for token in ("стать", "новост", "публикац", "сми", "пресс-релиз")):
            return self.get("article_research")
        return self.get("document_discovery")

    def prompt_for(self, workflow: WorkflowManifest) -> str:
        nodes = self._topological_nodes(workflow)
        steps = " → ".join(
            f"{node.skill_id}{' (при необходимости)' if node.optional else ''}" for node in nodes
        )
        return (
            f"Рекомендуемый workflow для этого запроса: {workflow.title}. "
            f"Допустимая последовательность: {steps}. Пропускай необязательные шаги, "
            "если уже есть достаточные проверяемые данные."
        )


DEFAULT_WORKFLOWS = (
    WorkflowManifest(
        id="document_discovery",
        title="Поиск банковской отчётности",
        description="Устанавливает банк, проверяет официальный раздел, скачивает и сохраняет оригинал.",
        trigger_hints=["найди отчёт", "скачай МСФО", "форма 101", "форма 102"],
        nodes=[
            WorkflowNode(id="bank", skill_id="resolve_bank"),
            WorkflowNode(id="library", skill_id="list_documents", depends_on=["bank"], optional=True),
            WorkflowNode(id="discover", skill_id="discover_documents", depends_on=["bank"]),
            WorkflowNode(id="download", skill_id="download_document", depends_on=["discover"]),
            WorkflowNode(
                id="cbr_form",
                skill_id="fetch_cbr_form",
                depends_on=["bank"],
                optional=True,
                note="Используется только для формы 101/102.",
            ),
            WorkflowNode(
                id="fallback_search",
                skill_id="search_articles",
                depends_on=["discover"],
                optional=True,
                note="Fallback, если официальный документ недоступен.",
            ),
            WorkflowNode(
                id="fallback_read",
                skill_id="read_article",
                depends_on=["fallback_search"],
                optional=True,
            ),
        ],
    ),
    WorkflowManifest(
        id="article_research",
        title="Поиск публикаций и статей",
        description="Ищет официальный контекст и профильные публикации, затем читает релевантные страницы.",
        trigger_hints=["найди статьи", "новости банка", "публикации по теме"],
        nodes=[
            WorkflowNode(id="bank", skill_id="resolve_bank", optional=True),
            WorkflowNode(id="search", skill_id="search_articles", depends_on=["bank"]),
            WorkflowNode(id="read", skill_id="read_article", depends_on=["search"]),
        ],
    ),
    WorkflowManifest(
        id="financial_analysis",
        title="Проверяемый финансовый анализ",
        description="Собирает документы и факты, читает первоисточник и формирует подходящий тип отчёта.",
        trigger_hints=["проанализируй", "сравни периоды", "построй график", "создай отчёт"],
        nodes=[
            WorkflowNode(id="bank", skill_id="resolve_bank", optional=True),
            WorkflowNode(id="library", skill_id="list_documents", depends_on=["bank"]),
            WorkflowNode(id="discover", skill_id="discover_documents", depends_on=["bank"], optional=True),
            WorkflowNode(id="download", skill_id="download_document", depends_on=["discover"], optional=True),
            WorkflowNode(id="facts", skill_id="query_financial_facts", depends_on=["library"]),
            WorkflowNode(id="document", skill_id="read_document", depends_on=["library"], optional=True),
            WorkflowNode(
                id="professional_context",
                skill_id="search_professional_reports",
                depends_on=["bank"],
                optional=True,
                note="Публичные рейтинговые и отраслевые обзоры используются только для контекста.",
            ),
            WorkflowNode(
                id="fallback_search",
                skill_id="search_articles",
                depends_on=["discover"],
                optional=True,
            ),
            WorkflowNode(
                id="fallback_read",
                skill_id="read_article",
                depends_on=["fallback_search"],
                optional=True,
            ),
            WorkflowNode(
                id="report",
                skill_id="create_report",
                depends_on=["facts", "document", "download", "professional_context"],
            ),
        ],
    ),
)


def build_workflow_registry(
    skills: SkillRegistry, custom_workflows: list[dict] | None = None
) -> WorkflowRegistry:
    registry = WorkflowRegistry(skills)
    for workflow in DEFAULT_WORKFLOWS:
        registry.register(workflow)
    for payload in custom_workflows or []:
        try:
            workflow = WorkflowManifest.model_validate(payload).model_copy(update={"editable": True})
            if workflow.id not in registry._workflows:
                registry.register(workflow)
        except (ValueError, WorkflowValidationError):
            continue
    return registry
