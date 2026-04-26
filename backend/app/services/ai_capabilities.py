"""Data-driven AI provider/model reasoning capability registry."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatchcase
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logger import get_logger

logger = get_logger(__name__)


class ReasoningIntensity(str, Enum):
    """Normalized internal reasoning intensity contract."""

    AUTO = "auto"
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAXIMUM = "maximum"


NORMALIZED_REASONING_INTENSITIES = tuple(item.value for item in ReasoningIntensity)


class UnsupportedReasoningIntensityError(ValueError):
    """Raised when a known provider/model rejects an explicit reasoning intensity."""


@dataclass(frozen=True)
class ReasoningCapability:
    provider: str
    model_pattern: str
    supported_intensities: tuple[ReasoningIntensity, ...]
    default_intensity: ReasoningIntensity
    provider_native: str
    provider_payload_mappings: Dict[str, Dict[str, Any]]
    last_verified_date: str
    notes: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model_pattern": self.model_pattern,
            "supported_intensities": [item.value for item in self.supported_intensities],
            "default_intensity": self.default_intensity.value,
            "provider_native": self.provider_native,
            "provider_payload_mappings": deepcopy(self.provider_payload_mappings),
            "last_verified_date": self.last_verified_date,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ReasoningConfig:
    """Resolved normalized reasoning config passed across AI service/provider boundaries."""

    intensity: ReasoningIntensity
    provider_payload: Dict[str, Any]
    provider: str
    model: str
    capability: Optional[ReasoningCapability] = None
    warning: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "intensity": self.intensity.value,
            "provider_payload": deepcopy(self.provider_payload),
            "provider": self.provider,
            "model": self.model,
            "capability": self.capability.as_dict() if self.capability else None,
            "warning": self.warning,
        }


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "reasoning_capabilities.json"
_registry_cache: Optional[List[ReasoningCapability]] = None


def normalize_provider_name(provider: Optional[str]) -> str:
    normalized = (provider or "").strip().lower()
    if normalized == "mumu":
        return "openai"
    return normalized


def normalize_reasoning_intensity(value: Optional[str | ReasoningIntensity]) -> ReasoningIntensity:
    if value is None or value == "":
        return ReasoningIntensity.AUTO
    if isinstance(value, ReasoningIntensity):
        return value
    normalized = str(value).strip().lower()
    try:
        return ReasoningIntensity(normalized)
    except ValueError as exc:
        allowed = ", ".join(NORMALIZED_REASONING_INTENSITIES)
        raise UnsupportedReasoningIntensityError(f"不支持的推理强度: {value}。允许值: {allowed}") from exc


def _parse_capability(raw: Dict[str, Any], index: int) -> ReasoningCapability:
    required = {
        "provider",
        "model_pattern",
        "supported_intensities",
        "default_intensity",
        "provider_native",
        "provider_payload_mappings",
        "last_verified_date",
        "notes",
    }
    missing = sorted(required.difference(raw))
    if missing:
        raise ValueError(f"reasoning capability entry #{index} 缺少字段: {', '.join(missing)}")

    supported = tuple(normalize_reasoning_intensity(item) for item in raw["supported_intensities"])
    if not supported:
        raise ValueError(f"reasoning capability entry #{index} supported_intensities 不能为空")
    default_intensity = normalize_reasoning_intensity(raw["default_intensity"])
    if default_intensity not in supported:
        raise ValueError(f"reasoning capability entry #{index} default_intensity 必须在 supported_intensities 中")

    mappings = raw["provider_payload_mappings"]
    if not isinstance(mappings, dict):
        raise ValueError(f"reasoning capability entry #{index} provider_payload_mappings 必须是对象")
    missing_mappings = [item.value for item in supported if item.value not in mappings]
    if missing_mappings:
        raise ValueError(f"reasoning capability entry #{index} 缺少 provider payload 映射: {', '.join(missing_mappings)}")

    return ReasoningCapability(
        provider=normalize_provider_name(raw["provider"]),
        model_pattern=str(raw["model_pattern"]).strip().lower(),
        supported_intensities=supported,
        default_intensity=default_intensity,
        provider_native=str(raw["provider_native"]),
        provider_payload_mappings=deepcopy(mappings),
        last_verified_date=str(raw["last_verified_date"]),
        notes=str(raw["notes"]),
    )


def load_reasoning_capabilities(*, force_reload: bool = False) -> List[ReasoningCapability]:
    """Load and validate the JSON capability registry."""

    global _registry_cache
    if _registry_cache is not None and not force_reload:
        return list(_registry_cache)

    with REGISTRY_PATH.open("r", encoding="utf-8") as registry_file:
        data = json.load(registry_file)

    declared_intensities = tuple(data.get("intensities", []))
    if declared_intensities != NORMALIZED_REASONING_INTENSITIES:
        raise ValueError("reasoning registry intensities must exactly match normalized contract")

    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("reasoning registry entries must be a list")

    _registry_cache = [_parse_capability(entry, index) for index, entry in enumerate(entries)]
    return list(_registry_cache)


def get_reasoning_registry_metadata() -> Dict[str, Any]:
    """Return API-safe registry metadata for settings/frontends."""

    return {
        "intensities": list(NORMALIZED_REASONING_INTENSITIES),
        "capabilities": [capability.as_dict() for capability in load_reasoning_capabilities()],
    }


def find_reasoning_capability(provider: str, model: str) -> Optional[ReasoningCapability]:
    provider_name = normalize_provider_name(provider)
    model_name = (model or "").strip().lower()
    for capability in load_reasoning_capabilities():
        if capability.provider == provider_name and fnmatchcase(model_name, capability.model_pattern):
            return capability
    return None


def build_reasoning_config(
    *,
    provider: str,
    model: str,
    intensity: Optional[str | ReasoningIntensity] = None,
) -> ReasoningConfig:
    """Resolve and preflight a reasoning selection before any provider HTTP work."""

    provider_name = normalize_provider_name(provider)
    model_name = model or ""
    requested = normalize_reasoning_intensity(intensity)
    capability = find_reasoning_capability(provider_name, model_name)

    if capability is None:
        warning = (
            f"未知模型推理能力: provider={provider_name}, model={model_name}; "
            "使用 auto 并跳过 provider-native reasoning 参数"
        )
        logger.warning(warning)
        return ReasoningConfig(
            intensity=ReasoningIntensity.AUTO,
            provider_payload={},
            provider=provider_name,
            model=model_name,
            capability=None,
            warning=warning,
        )

    resolved = requested if intensity is not None and str(intensity).strip() != "" else capability.default_intensity
    if resolved not in capability.supported_intensities:
        supported = ", ".join(item.value for item in capability.supported_intensities)
        raise UnsupportedReasoningIntensityError(
            f"模型 {provider_name}/{model_name} 不支持推理强度 {resolved.value}；支持: {supported}"
        )

    provider_payload = deepcopy(capability.provider_payload_mappings.get(resolved.value, {}))
    return ReasoningConfig(
        intensity=resolved,
        provider_payload=provider_payload,
        provider=provider_name,
        model=model_name,
        capability=capability,
    )
