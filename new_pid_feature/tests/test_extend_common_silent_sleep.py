"""Tests for the 静眠 (silentSleepStatus) PID extension demo.

Covers the two things a new attribute extension has to get right: the
registry resolves the subclass for its pid, and the added preset reads and
writes the underlying boolean attribute.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.components.climate import (
    PRESET_NONE,
    PRESET_SLEEP,
    ClimateEntityFeature,
)

from custom_components.haier_home import climate as climate_mod
from custom_components.haier_home import extend as _extend
from custom_components.haier_home.const import DOMAIN
from custom_components.haier_home.device import Attribute, DataListItem, ValueRange
from custom_components.haier_home.extend.common_silent_sleep import (
    ATTR_SILENT_SLEEP,
    PIDS_COMMON_SILENT_SLEEP,
    CommonSilentSleepClimateEntity,
)
from tests.mock_data import MockClient, create_mock_ac_device, create_mock_coordinator

_extend.load_extensions()


def _silent_sleep_attribute(*, value: str = "false", writable: bool = True) -> Attribute:
    """Build the digital-model attribute as the cloud publishes it."""
    return Attribute(
        name=ATTR_SILENT_SLEEP,
        desc="静眠",
        readable=True,
        writable=writable,
        default_value="false",
        current_value=value,
        value_range=ValueRange(
            type="LIST",
            data_list=[
                DataListItem(data="false", desc="关"),
                DataListItem(data="true", desc="开"),
            ],
        ),
    )


def _make_setup_args(coordinator):
    hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"coordinator": coordinator, "client": MockClient()}}},
        bus=SimpleNamespace(async_fire=lambda *_args: None),
    )
    return hass, SimpleNamespace(entry_id="entry_1")


async def _setup_entity(*, value: str = "false", writable: bool = True, with_attr: bool = True):
    """Run the climate platform for a device in the extension's pid group."""
    device = create_mock_ac_device(pid=PIDS_COMMON_SILENT_SLEEP[0])
    if with_attr:
        device.attributes[ATTR_SILENT_SLEEP] = _silent_sleep_attribute(
            value=value, writable=writable
        )

    coordinator = create_mock_coordinator()
    coordinator._devices = {device.device_id: device}

    sent: list[tuple[str, dict]] = []

    async def _capture_send(device_id, commands):
        sent.append((device_id, commands))

    coordinator.async_send_command = _capture_send

    hass, entry = _make_setup_args(coordinator)
    captured: list = []
    await climate_mod.async_setup_entry(hass, entry, captured.extend)
    assert len(captured) == 1

    entity = captured[0]
    entity.hass = hass
    return entity, sent


@pytest.mark.asyncio
async def test_registry_resolves_extension_for_pid():
    """The pid list in the extension wins over the platform fallback."""
    entity, _ = await _setup_entity()
    assert type(entity) is CommonSilentSleepClimateEntity


@pytest.mark.asyncio
async def test_preset_feature_and_state_reflect_attribute():
    entity, _ = await _setup_entity(value="true")

    assert ClimateEntityFeature.PRESET_MODE in entity.supported_features
    assert entity.preset_modes == [PRESET_NONE, PRESET_SLEEP]
    assert entity.preset_mode == PRESET_SLEEP

    # Inherited climate behavior is untouched.
    assert entity.target_temperature == 24.0
    assert entity.fan_mode == "auto"


@pytest.mark.asyncio
async def test_preset_none_when_silent_sleep_off():
    entity, _ = await _setup_entity(value="false")
    assert entity.preset_mode == PRESET_NONE


@pytest.mark.asyncio
async def test_preset_unknown_when_no_value_reported():
    entity, _ = await _setup_entity(value="")
    assert entity.preset_mode is None


@pytest.mark.asyncio
async def test_feature_absent_when_attribute_missing_or_readonly():
    entity, _ = await _setup_entity(with_attr=False)
    assert ClimateEntityFeature.PRESET_MODE not in entity.supported_features
    assert entity.preset_mode is None

    entity, _ = await _setup_entity(writable=False)
    assert ClimateEntityFeature.PRESET_MODE not in entity.supported_features


@pytest.mark.asyncio
async def test_set_preset_mode_sends_device_token_style():
    entity, sent = await _setup_entity()

    await entity.async_set_preset_mode(PRESET_SLEEP)
    await entity.async_set_preset_mode(PRESET_NONE)

    payloads = [commands for _, commands in sent]
    assert payloads == [{ATTR_SILENT_SLEEP: "true"}, {ATTR_SILENT_SLEEP: "false"}]


@pytest.mark.asyncio
async def test_set_preset_mode_ignores_unknown_preset():
    entity, sent = await _setup_entity()
    await entity.async_set_preset_mode("boost")
    assert sent == []
