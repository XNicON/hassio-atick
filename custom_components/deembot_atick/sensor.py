from __future__ import annotations

import logging
from decimal import Decimal

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
        name="Counter A"
    ),
    SensorEntityDescription(
        key=TYPE_COUNTER_B,
        translation_key=TYPE_COUNTER_B,
        name="Counter B"
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

class ATickWaterCounterSensor(BaseEntity, SensorEntity):
    def __init__(self, coordinator: ATickDataUpdateCoordinator, sensor_description: SensorEntityDescription) -> None:
        super().__init__(coordinator)

        self._attr_unique_id = f"{self._device.base_unique_id}-{sensor_description.key}"
        self._attr_name = self._device.name + ' ' + sensor_description.name
        self._attr_icon = "mdi:counter"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_suggested_display_precision = 2

        self.entity_description = sensor_description

    @property
    def native_value(self) -> Decimal:
        return self._device.data[self.entity_description.key]


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

    @property
    def native_value(self) -> str | int | None:
        if service_info := async_last_service_info(self.hass, self._address):
            return service_info.rssi

        return None
