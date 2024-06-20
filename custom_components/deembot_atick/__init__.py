import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import ATickDataUpdateCoordinator
from .device import ATickBTDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    assert entry.unique_id is not None
    hass.data.setdefault(DOMAIN, {})
    address: str = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(hass, address.upper(), False)

    if not ble_device:
        raise ConfigEntryNotReady(f"Could not find BT Device with address {address}")

    coordinator = ATickDataUpdateCoordinator(
        hass=hass,
        entry=entry,
        logger=_LOGGER,
        ble_device=ble_device,
        device=ATickBTDevice(ble_device),
        connectable=True
    )

    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(coordinator.async_start())
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
            name=entry.title,
            model=device_info.get('model'),
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
