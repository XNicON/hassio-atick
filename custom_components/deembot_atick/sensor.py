from __future__ import annotations

import logging

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ATickDataUpdateCoordinator
from .base_entity import BaseEntity

_LOGGER = logging.getLogger(__name__)

TYPE_COUNTER_A = "counter_a_value"
TYPE_COUNTER_B = "counter_b_value"

ENTITIES: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key=TYPE_COUNTER_A,
        translation_key=TYPE_COUNTER_A,
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key=TYPE_COUNTER_B,
        translation_key=TYPE_COUNTER_B,
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ATickDataUpdateCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator = entry.runtime_data

    sensors: list[SensorEntity] = [ATickRSSISensor(coordinator)]
    sensors.extend(ATickWaterCounterSensor(coordinator, description) for description in ENTITIES)

    async_add_entities(sensors)


class ATickWaterCounterSensor(BaseEntity, SensorEntity, RestoreEntity):
    """aTick water counter sensor."""

    def __init__(
        self,
        coordinator: ATickDataUpdateCoordinator,
        sensor_description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)

        self.entity_description = sensor_description

        self._attr_unique_id = f"{self._device.base_unique_id}-{self.entity_description.key}"
        self._attr_translation_key = self.entity_description.translation_key
        self._attr_icon = "mdi:counter"
        self._attr_device_class = self.entity_description.device_class
        self._attr_native_unit_of_measurement = (
            self.entity_description.native_unit_of_measurement
        )
        self._attr_state_class = self.entity_description.state_class
        self._attr_suggested_display_precision = (
            self.entity_description.suggested_display_precision
        )

    async def async_added_to_hass(self) -> None:
        """Restore last counter value if the device has not advertised yet."""
        if self._device.data[self.entity_description.key] is None:
            last_state = await self.async_get_last_state()
            if last_state is not None and last_state.state not in {"unknown", "unavailable"}:
                try:
                    self._device.data[self.entity_description.key] = float(last_state.state)
                except ValueError:
                    _LOGGER.debug(
                        "Cannot restore %s from state %r",
                        self.entity_description.key,
                        last_state.state,
                    )

        await super().async_added_to_hass()

    @property
    def native_value(self) -> float | None:
        """Return the native value."""
        value = self._device.data[self.entity_description.key]
        return float(value) if value is not None else None


class ATickRSSISensor(BaseEntity, SensorEntity):
    """Bluetooth signal sensor."""

    def __init__(self, coordinator: ATickDataUpdateCoordinator) -> None:
        super().__init__(coordinator)

        self.entity_description = SensorEntityDescription(
            key="rssi",
            translation_key="bluetooth_signal",
            native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

        self._attr_unique_id = f"{self._device.base_unique_id}-{self.entity_description.key}"
        self._attr_translation_key = self.entity_description.translation_key

    @property
    def native_value(self) -> int | None:
        """Return the RSSI from the last Bluetooth service info."""
        if service_info := async_last_service_info(self.hass, self._address, False):
            return service_info.rssi

        return None
