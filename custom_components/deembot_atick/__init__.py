from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import ATickDataUpdateCoordinator
from .device import ATickBTDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type ATickConfigEntry = ConfigEntry[ATickDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ATickConfigEntry) -> bool:
    """Set up Deembot aTick from a config entry."""
    assert entry.unique_id is not None

    address: str = entry.data[CONF_ADDRESS].upper()
    ble_device = bluetooth.async_ble_device_from_address(hass, address, False)

    if ble_device is None:
        _LOGGER.debug(
            "BT device %s is not in Home Assistant Bluetooth cache yet; "
            "loading entry in unavailable state",
            address,
        )

    coordinator = ATickDataUpdateCoordinator(
        hass=hass,
        entry=entry,
        logger=_LOGGER,
        address=address,
        device=ATickBTDevice(
            address=address,
            name=entry.title,
            ble_device=ble_device,
            device_info=entry.data.get("device_info"),
        ),
        device_seen=ble_device is not None,
    )

    entry.runtime_data = coordinator

    entry.async_on_unload(coordinator.async_start())
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    device_info = entry.data.get("device_info", {})
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        connections={(dr.CONNECTION_BLUETOOTH, address)},
        name=entry.title,
        model=device_info.get("model"),
        manufacturer=device_info.get("manufacturer"),
        sw_version=device_info.get("firmware_version"),
    )

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ATickConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ATickConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
