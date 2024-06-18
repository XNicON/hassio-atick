from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PIN
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers.update_coordinator import UpdateFailed

from .device import ATickBTDevice

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

class ATickDataUpdateCoordinator(ActiveBluetoothDataUpdateCoordinator[None]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        logger: logging.Logger,
        ble_device: BLEDevice,
        device: ATickBTDevice,
        connectable: bool
    ) -> None:
        super().__init__(
            hass=hass,
            logger=logger,
            address=ble_device.address,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_update,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=connectable,
        )
        self.device = device
        self._config = entry.data
        self._was_unavailable = True

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        _LOGGER.debug("check needs_poll")

        # Only poll if hass is running, we need to poll,
        # and we actually have a way to connect to the device
        return (
            self.hass.state is CoreState.running
            and self.device.active_poll_needed(seconds_since_last_poll)
            and bool(bluetooth.async_ble_device_from_address(self.hass, service_info.device.address, connectable=True))
        )

    async def _async_update(self, service_info: bluetooth.BluetoothServiceInfoBleak) -> None:
        """Poll the device."""
        return

        # Требуется сопряжение устройства
        try:
            await self.device.active_full_update()
        except Exception as ex:
            raise UpdateFailed(str(ex)) from ex

    @callback
    def _async_handle_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Handle the device going unavailable."""
        super()._async_handle_unavailable(service_info)
        self._was_unavailable = True

        _LOGGER.debug("_was_unavailable = True")

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle a Bluetooth event."""

        parsed_adv = self.device.parse_advertisement_data(self._config[CONF_PIN], service_info.advertisement)

        _LOGGER.debug("%s: advertisement raw data: %s", self.address, service_info.advertisement)
        _LOGGER.debug("%s: advertisement data: %s", self.address, parsed_adv)

        if self.device.is_advertisement_changed(parsed_adv) or self._was_unavailable:
            self._was_unavailable = False
            self.device.update_from_advertisement(parsed_adv)

        super()._async_handle_bluetooth_event(service_info, change)
