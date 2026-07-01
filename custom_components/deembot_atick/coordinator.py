from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import ActiveBluetoothDataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PIN
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers.update_coordinator import UpdateFailed

from .device import ATickBTDevice

_LOGGER = logging.getLogger(__name__)


class ATickDataUpdateCoordinator(ActiveBluetoothDataUpdateCoordinator[None]):
    """Bluetooth coordinator for aTick devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        logger: logging.Logger,
        address: str,
        device: ATickBTDevice,
        device_seen: bool,
    ) -> None:
        super().__init__(
            hass=hass,
            logger=logger,
            address=address,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_update,
            connectable=True,
        )
        self.device = device
        self._config = entry.data
        self._device_seen = device_seen
        self._was_unavailable = not device_seen

    @property
    def device_seen(self) -> bool:
        """Return whether the device is currently known to the Bluetooth stack."""
        return self._device_seen

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        """Return if an active poll should be performed."""
        is_needed = (
            self.hass.state is CoreState.running
            and self.device.active_poll_needed(seconds_since_last_poll)
            and bluetooth.async_ble_device_from_address(
                self.hass, service_info.device.address, True
            )
            is not None
        )

        _LOGGER.debug("%s: needs active BLE poll: %s", self.address, is_needed)
        return is_needed

    async def _async_update(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Poll the device."""
        self._device_seen = True
        self.device.set_ble_device(service_info.device)

        try:
            await self.device.active_full_update()
        except Exception as ex:
            raise UpdateFailed(str(ex)) from ex

    @callback
    def _async_handle_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Handle the device going unavailable."""
        self._device_seen = False
        self._was_unavailable = True
        _LOGGER.debug("%s: Bluetooth device is unavailable", self.address)
        super()._async_handle_unavailable(service_info)

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle a Bluetooth event."""
        self._device_seen = True
        self.device.set_ble_device(service_info.device)

        parsed_adv = self.device.parse_advertisement_data(
            self._config[CONF_PIN], service_info.advertisement
        )

        _LOGGER.debug("%s: advertisement raw data: %s", self.address, service_info.advertisement)
        _LOGGER.debug("%s: advertisement data: %s", self.address, parsed_adv)

        if parsed_adv is not None and (
            self.device.is_advertisement_changed(parsed_adv) or self._was_unavailable
        ):
            self._was_unavailable = False
            self.device.update_from_advertisement(parsed_adv)

        super()._async_handle_bluetooth_event(service_info, change)
