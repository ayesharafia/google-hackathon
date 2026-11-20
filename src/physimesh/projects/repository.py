"""Project persistence boundary. No HTTP or solver behavior belongs here."""
from __future__ import annotations

from typing import Protocol

from .contracts import DesignRevisionV1


class ProjectMissing(Exception):
    """The requested local project or revision does not exist."""


class DraftConflict(Exception):
    """A save/freeze used a version that is no longer current."""

    def __init__(self, current_version: int):
        super().__init__('draft changed; reload before applying your edits')
        self.current_version = current_version


class ProjectRepository(Protocol):
    def create(self, title: str, snapshot: str) -> dict: ...
    def list_projects(self) -> list[dict]: ...
    def get(self, project_id: str) -> dict: ...
    def save(self, project_id: str, expected_version: int, snapshot: str) -> dict: ...
    def freeze(self, project_id: str, expected_version: int, revision: DesignRevisionV1) -> dict: ...
    def revision(self, project_id: str, digest: str) -> DesignRevisionV1: ...
    def retain_study(self, project_id: str, revision: str, study: str, result: str) -> str: ...
    def study_digest(self, project_id: str, study: str) -> str: ...
