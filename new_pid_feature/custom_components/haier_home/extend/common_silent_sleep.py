"""Shared PID-group extension: expose 静眠 (silentSleepStatus) as a climate preset.

Covers every pid listed in ``PIDS_COMMON_SILENT_SLEEP``.

Attribute exposed on top of the platform defaults:

===================  ======  ==============  ====================
name                 type    writable        values
===================  ======  ==============  ====================
silentSleepStatus    bool    可读/组可写      "true" 开 / "false" 关（默认 false）
===================  ======  ==============  ====================

静眠 maps onto HA's standard ``PRESET_SLEEP``/``PRESET_NONE`` keys, so the
frontend supplies the localized labels and icon and no ``translations/*.json``
or ``icons.json`` change is needed.

See ``docs/device-pid-extension.md`` (场景三) for the conventions this file
follows.
"""

from __future__ import annotations

import logging

from homeassistant.components.climate import (
    PRESET_NONE,
    PRESET_SLEEP,
    ClimateEntityFeature,
)

from ..climate import HaierClimateEntity
from ..entity import HaierDeviceEntity

_LOGGER = logging.getLogger(__name__)

# Digital-model attribute name for 静眠. Boolean LIST ("true"/"false").
ATTR_SILENT_SLEEP = "silentSleepStatus"

# PIDs that support 静眠 (新增 PID 只改这里). Demo values — replace with the
# real pids (形如 "PID_AACPBR000").
PIDS_COMMON_SILENT_SLEEP: list[str] = ["PID_AABMZ0001", "PID_AAABTT00M", "PID_AABMZGU00"]


@HaierDeviceEntity.register(PIDS_COMMON_SILENT_SLEEP, "climate")
class CommonSilentSleepClimateEntity(HaierClimateEntity):
    """Climate entity that adds the 静眠 preset to the platform defaults.

    Everything else (modes, temperature, fan speed) is inherited unchanged
    from :class:`~..climate.HaierClimateEntity`.
    """

    # ClimateEntity.preset_modes reads this attribute. PRESET_NONE is the
    # required "off" member of any preset list.
    _attr_preset_modes = [PRESET_NONE, PRESET_SLEEP]

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Add PRESET_MODE only when the device really accepts 静眠 writes.

        The flag is capability-gated instead of hardcoded so a unit in this
        pid group that omits the attribute (or reports it read-only) does not
        advertise a control that would fail on use.
        """
        features = super().supported_features
        if self.is_writable(ATTR_SILENT_SLEEP):
            features |= ClimateEntityFeature.PRESET_MODE
        return features

    @property
    def preset_mode(self) -> str | None:
        """Return PRESET_SLEEP while 静眠 is on, else PRESET_NONE.

        ``None`` is returned when the attribute has not reported a value yet,
        which HA renders as unknown rather than as "静眠关闭".
        """
        value = self.get_bool_value(ATTR_SILENT_SLEEP)
        if value is None:
            return None
        return PRESET_SLEEP if value else PRESET_NONE

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Turn 静眠 on/off.

        ``async_set_bool`` picks the device's own token style ("true"/"false"
        vs "1"/"0") from the attribute's enum, so no per-model formatting is
        needed here.
        """
        if preset_mode not in (self.preset_modes or []):
            _LOGGER.warning(
                "Unsupported preset mode %s for device %s",
                preset_mode,
                self._device.device_id,
            )
            return

        _LOGGER.debug(
            "Setting preset mode to %s (%s) for device %s",
            preset_mode,
            ATTR_SILENT_SLEEP,
            self._device.device_id,
        )
        await self.async_set_bool(ATTR_SILENT_SLEEP, preset_mode == PRESET_SLEEP)
