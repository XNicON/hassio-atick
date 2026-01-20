from __future__ import annotations

import logging
from functools import cached_property

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ATickDataUpdateCoordinator
from .base_entity import BaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TYPE_COUNTER_A = "counter_a_value"
TYPE_COUNTER_B = "counter_b_value"

ENTITIES: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key=TYPE_COUNTER_A,
        translation_key=TYPE_COUNTER_A,
        name="Counter A",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class = SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2
    ),
    SensorEntityDescription(
        key=TYPE_COUNTER_B,
        translation_key=TYPE_COUNTER_B,
        name="Counter B",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2
    ),
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: ATickDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        ATickRSSISensor(coordinator)
    ]

    for description in ENTITIES:
        sensors.append(ATickWaterCounterSensor(coordinator, description))

    async_add_entities(sensors)


class ATickWaterCounterSensor(BaseEntity, SensorEntity, RestoreEntity):
    def __init__(self, coordinator: ATickDataUpdateCoordinator, sensor_description: SensorEntityDescription) -> None:
        super().__init__(coordinator)

        self.entity_description = sensor_description

        self._attr_unique_id = f"{self._device.base_unique_id}-{self.entity_description.key}"
        self._attr_name = self._device.name + ' ' + self.entity_description.name
        self._attr_icon = "mdi:counter"
        self._attr_device_class = self.entity_description.device_class
        self._attr_native_unit_of_measurement = self.entity_description.native_unit_of_measurement
        self._attr_state_class = self.entity_description.state_class
        self._attr_suggested_display_precision = self.entity_description.suggested_display_precision

    async def async_added_to_hass(self) -> None:
        if self._device.data[self.entity_description.key] is None:
            if last_state := await self.async_get_last_state():
                try:
                    self._device.data[self.entity_description.key] = float(last_state.state)
                except (ValueError, TypeError):
                    _LOGGER.warning("Could not restore last state for %s: %s", self._attr_unique_id, last_state.state)

        await super().async_added_to_hass()

    @property
    def native_value(self) -> float | None:
        value = self._device.data[self.entity_description.key]
        if value is None:
            return None

        # Применяем множитель (ratio) к показаниям
        ratio_key = self.entity_description.key.replace('_value', '_ratio')
        ratio = self._device.data.get(ratio_key, 1.0)
        return value * ratio


class ATickRSSISensor(BaseEntity, SensorEntity):
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
        self._attr_name = self._device.name + ' Bluetooth signal'

    @cached_property
    def native_value(self) -> str | int | None:
        if service_info := async_last_service_info(self.hass, self._address, False):
            return service_info.rssi

        return None
