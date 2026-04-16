from __future__ import annotations
from dataclasses import dataclass, field
import yaml


@dataclass
class FilterConfig:
    types_allow: list[str]
    keywords_block: list[str]
    keywords_allow: list[str]


@dataclass
class PairMaskingConfig:
    a_to_b: dict[int, dict]
    b_to_a: dict[int, dict]


@dataclass
class PairConfig:
    name: str
    group_a_chat_id: int
    group_b_chat_id: int
    bidirectional: bool
    enabled: bool
    filters: FilterConfig
    masking: PairMaskingConfig


@dataclass
class GlobalMaskingConfig:
    users: dict[int, dict]


@dataclass
class MonitoringConfig:
    alert_chat_id: int


@dataclass
class Config:
    admins: list[int]
    masking: GlobalMaskingConfig
    pairs: list[PairConfig]
    recovery_window_minutes: int = 15
    monitoring: MonitoringConfig | None = None
    _raw: dict = field(default_factory=dict, repr=False)


def _parse_pair(raw: dict) -> PairConfig:
    filters_raw = raw.get("filters", {})
    types_raw = filters_raw.get("types", {})
    keywords_raw = filters_raw.get("keywords", {})
    masking_raw = raw.get("masking", {})

    return PairConfig(
        name=raw["name"],
        group_a_chat_id=raw["group_a_chat_id"],
        group_b_chat_id=raw["group_b_chat_id"],
        bidirectional=raw.get("bidirectional", True),
        enabled=raw.get("enabled", True),
        filters=FilterConfig(
            types_allow=types_raw.get("allow", ["text"]),
            keywords_block=keywords_raw.get("block", []),
            keywords_allow=keywords_raw.get("allow", []),
        ),
        masking=PairMaskingConfig(
            a_to_b={int(k): v for k, v in (masking_raw.get("a_to_b") or {}).items()},
            b_to_a={int(k): v for k, v in (masking_raw.get("b_to_a") or {}).items()},
        ),
    )


def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if "admins" not in raw or not raw["admins"]:
        raise ValueError("config.yaml must define at least one admin user ID under 'admins'")
    if "pairs" not in raw or not raw["pairs"]:
        raise ValueError("config.yaml must define at least one pair under 'pairs'")

    masking_raw = raw.get("masking", {})
    global_masking = GlobalMaskingConfig(
        users={int(k): v for k, v in (masking_raw.get("users") or {}).items()}
    )

    monitoring = None
    monitoring_raw = raw.get("monitoring")
    if monitoring_raw and monitoring_raw.get("alert_chat_id"):
        monitoring = MonitoringConfig(alert_chat_id=int(monitoring_raw["alert_chat_id"]))

    return Config(
        admins=[int(a) for a in raw["admins"]],
        masking=global_masking,
        pairs=[_parse_pair(p) for p in raw["pairs"]],
        recovery_window_minutes=int(raw.get("recovery_window_minutes", 15)),
        monitoring=monitoring,
        _raw=raw,
    )
