from __future__ import annotations

import logging

from homeassistant.components.bluetooth.passive_update_coordinator import PassiveBluetoothCoordinatorEntity
from homeassistant.helpers import device_registry as dr

from . import ATickDataUpdateCoordinator
from .const import DOMAIN
from .device import ATickBTDevice

_LOGGER = logging.getLogger(__name__)

class BaseEntity(PassiveBluetoothCoordinatorEntity[ATickDataUpdateCoordinator]):
    _device: ATickBTDevice

    def __init__(self, coordinator: ATickDataUpdateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

        self._device = coordinator.device
        self._address = coordinator.address

        self._attr_device_info = dr.DeviceInfo(
            identifiers={
                (DOMAIN, self._device.base_unique_id)
            },
            connections={
                (dr.CONNECTION_BLUETOOTH, self._address)
            },
            name=self._device.name,
            model=self._device.model,
            manufacturer=self._device.manufacturer,
            sw_version=self._device.firmware_version,
        )
