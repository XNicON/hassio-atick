import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from bleak import BleakError, BLEDevice
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_SECONDS
from .device import ATickBTDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR
]

@dataclass
class BLEData:
    ble_device: BLEDevice
    device: ATickBTDevice
    coordinator: DataUpdateCoordinator[None]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    assert entry.unique_id is not None
    hass.data.setdefault(DOMAIN, {})
    address: str = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(hass, address.upper(), True)

    if not ble_device:
        raise ConfigEntryNotReady(f"Could not find BT Device with address {address}")

    atick_device = ATickBTDevice(ble_device)

    async def _async_update() -> None:
        """Update the device state."""
        try:
            await atick_device.update()
        except (BleakError, asyncio.TimeoutError) as ex:
            await atick_device.stop()

            raise UpdateFailed(str(ex)) from ex

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=entry.title,
        update_method=_async_update,
        update_interval=timedelta(seconds=UPDATE_SECONDS),
    )

    hass.data[DOMAIN][entry.entry_id] = BLEData(
        ble_device=ble_device,
        device=atick_device,
        coordinator=coordinator
    )

    await coordinator.async_config_entry_first_refresh()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    device_info = entry.data.get('device_info')

    if device_info:
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={
                (DOMAIN, entry.unique_id)
            },
            connections={
                (dr.CONNECTION_BLUETOOTH, address)
            },
            model=entry.title,
            name=entry.title,
            manufacturer=device_info.get('manufacturer'),
            sw_version=device_info.get('firmware_version')
        )

    return True

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.config_entries.async_entries(DOMAIN):
            hass.data.pop(DOMAIN)

    return unload_ok
