from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


@dataclass(frozen=True)
class Anonymous:
    kind: Literal["anonymous"] = "anonymous"


@dataclass(frozen=True)
class Guest:
    session_id: str

    @property
    def kind(self) -> Literal["guest"]:
        return "guest"


@dataclass(frozen=True)
class Member:
    user_id: int
    username: str
    groups: tuple[str, ...] = ()

    @property
    def kind(self) -> Literal["member"]:
        return "member"


Principal = Union[Anonymous, Guest, Member]
