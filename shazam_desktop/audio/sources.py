"""Audio sources and the catalog the source menu is built from."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

DEFAULT_MIC_KEY = "mic:default"
SYSTEM_KEY = "system"

_DEFAULT_MIC_LABEL = "Microphone"
_SYSTEM_LABEL = "System Audio"


class SourceKind(Enum):
    MICROPHONE = "microphone"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class AudioSource:
    """One entry of the source menu.

    ``key`` is the stable identifier persisted in the settings; ``device`` is an
    opaque handle owned by the backend that produced the source.
    """

    key: str
    label: str
    kind: SourceKind
    available: bool = True
    hint: str | None = None
    device: int | None = None


@dataclass(frozen=True, slots=True)
class InputDevice:
    """A raw input device as reported by an audio backend."""

    index: int
    name: str


@dataclass(frozen=True, slots=True)
class SourceCatalog:
    sources: tuple[AudioSource, ...]

    def find(self, key: str) -> AudioSource | None:
        return next((source for source in self.sources if source.key == key), None)

    def resolve(self, key: str) -> AudioSource | None:
        """Return the source for ``key``, falling back to the default microphone."""
        return self.find(key) or self.find(DEFAULT_MIC_KEY)

    @property
    def microphones(self) -> tuple[AudioSource, ...]:
        return tuple(s for s in self.sources if s.kind is SourceKind.MICROPHONE)

    @property
    def system(self) -> AudioSource | None:
        return next((s for s in self.sources if s.kind is SourceKind.SYSTEM), None)


def build_catalog(
    microphones: Sequence[InputDevice],
    default_index: int | None,
    loopback: InputDevice | None,
    system_hint: str,
) -> SourceCatalog:
    """Assemble the catalog: default microphone, every input device, system audio."""
    has_default = default_index is not None
    sources = [
        AudioSource(
            key=DEFAULT_MIC_KEY,
            label=_DEFAULT_MIC_LABEL,
            kind=SourceKind.MICROPHONE,
            available=has_default,
            hint=None if has_default else "No input device found.",
            device=default_index,
        )
    ]
    seen: dict[str, int] = {}
    for device in microphones:
        seen[device.name] = seen.get(device.name, 0) + 1
        label = device.name if seen[device.name] == 1 else f"{device.name} ({seen[device.name]})"
        sources.append(
            AudioSource(
                key=f"mic:{label}",
                label=label,
                kind=SourceKind.MICROPHONE,
                device=device.index,
            )
        )
    sources.append(
        AudioSource(
            key=SYSTEM_KEY,
            label=_SYSTEM_LABEL,
            kind=SourceKind.SYSTEM,
            available=loopback is not None,
            hint=None if loopback is not None else system_hint,
            device=loopback.index if loopback is not None else None,
        )
    )
    return SourceCatalog(tuple(sources))


def unavailable_catalog(reason: str) -> SourceCatalog:
    """Catalog for a platform where no audio backend could be initialized."""
    return build_catalog((), None, None, reason)
