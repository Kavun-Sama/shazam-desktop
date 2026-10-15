"""macOS vibrancy: an ``NSVisualEffectView`` placed behind the Qt content view."""

from __future__ import annotations

import contextlib
import sys

from PySide6.QtWidgets import QWidget

if sys.platform != "darwin":
    raise ImportError("native_macos is macOS-only")

import objc
from AppKit import (
    NSAppearance,
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialPopover,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindowBelow,
)


class MacBackdrop:
    """Behind-window blur with the OS-drawn shadow following the rounded shape."""

    def __init__(self, widget: QWidget) -> None:
        view = objc.objc_object(c_void_p=int(widget.winId()))
        self._window = view.window()
        content = self._window.contentView()

        self._effect = NSVisualEffectView.alloc().initWithFrame_(content.frame())
        self._effect.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self._effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        self._effect.setMaterial_(NSVisualEffectMaterialPopover)
        self._effect.setState_(NSVisualEffectStateActive)
        self._effect.setWantsLayer_(True)
        self._effect.layer().setMasksToBounds_(True)
        with contextlib.suppress(AttributeError):  # pre-10.15: circular corners are fine
            self._effect.layer().setCornerCurve_("continuous")
        content.superview().addSubview_positioned_relativeTo_(self._effect, NSWindowBelow, content)

        self._window.setOpaque_(False)
        self._enabled = True

    def set_enabled(self, enabled: bool) -> bool:
        self._enabled = enabled
        self._effect.setHidden_(not enabled)
        self._window.setHasShadow_(enabled)
        self._window.invalidateShadow()
        return enabled

    def set_dark(self, dark: bool) -> None:
        name = NSAppearanceNameDarkAqua if dark else NSAppearanceNameAqua
        self._effect.setAppearance_(NSAppearance.appearanceNamed_(name))

    def update_shape(self, width: float, height: float, radius: float) -> None:
        if not self._enabled:
            return
        self._effect.layer().setCornerRadius_(radius)
        self._window.invalidateShadow()
