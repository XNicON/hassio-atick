from __future__ import annotations

import logging
from decimal import Decimal

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BLEData
from .base_entity import BaseEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TYPE_COUNTER_A = "water_counter_a"
TYPE_COUNTER_B = "water_counter_b"

ENTITIES: dict[str, SensorEntityDescription] = {
    "counter_a": SensorEntityDescription(
        key=TYPE_COUNTER_A,
        name="Water Counter A",
        translation_key=TYPE_COUNTER_A
    ),
    "counter_b": SensorEntityDescription(
        key=TYPE_COUNTER_B,
        name="Water Counter B",
        translation_key=TYPE_COUNTER_B
    ),
}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    ble_data: BLEData = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        ATickRSSISensor(ble_data)
    ]

    for sensorId, description in ENTITIES.items():
        sensors.append(ATickWaterCounterSensor(ble_data, sensorId, description))

    async_add_entities(sensors)

class ATickWaterCounterSensor(BaseEntity, SensorEntity):
    def __init__(self, ble_data: BLEData, sensorId: str, sensor_description: SensorEntityDescription) -> None:
        super().__init__(ble_data)

        self._attr_unique_id = f"{self._device.base_unique_id}-{sensorId}"
        self._attr_name = self._device.name + ' ' + sensor_description.name
        self._attr_icon = "mdi:counter"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_suggested_display_precision = 2

        self.entity_description = sensor_description

    @property
    def native_value(self) -> Decimal:
        if self.entity_description.key == TYPE_COUNTER_A:
            return self._device.counter_a_value

        return self._device.counter_b_value

    def available(self) -> bool:
        return True

class ATickRSSISensor(BaseEntity, SensorEntity):
    def __init__(self, ble_data: BLEData, ) -> None:
        super().__init__(ble_data)

        self._attr_unique_id = f"{self._device.base_unique_id}-rssi"
        self._attr_name = self._device.name + ' Bluetooth signal'

        self.entity_description = SensorEntityDescription(
            key="rssi",
            translation_key="bluetooth_signal",
            native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> str | int | None:
        if service_info := async_last_service_info(self.hass, self._address):
            return service_info.rssi

        return None
