from __future__ import annotations

import logging

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

from . import BLEData
from .const import DOMAIN
from .device import ATickBTDevice

_LOGGER = logging.getLogger(__name__)

class BaseEntity(CoordinatorEntity[DataUpdateCoordinator]):
    _device: ATickBTDevice

    def __init__(self, bte_data: BLEData) -> None:
        """Initialize the entity."""
        super().__init__(bte_data.coordinator)

        self._device = bte_data.device
        self._address = bte_data.ble_device.address

        self._attr_device_info = dr.DeviceInfo(
            identifiers={
                (DOMAIN, self._device.base_unique_id)
            },
            connections={
                (dr.CONNECTION_BLUETOOTH, self._address)
            },
            name=self._device.name,
            manufacturer=self._device.manufacturer,
            sw_version=self._device.firmware_version,
        )
