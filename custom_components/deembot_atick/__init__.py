import logging

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, config_validation as cv

from .const import DOMAIN
from .coordinator import ATickDataUpdateCoordinator
from .device import ATickBTDevice

_LOGGER = logging.getLogger(__name__)

# Константы для сервиса
SERVICE_SET_INITIAL_VALUES = "set_initial_values"
ATTR_COUNTER_A = "counter_a"
ATTR_COUNTER_B = "counter_b"

# Схема сервиса
SERVICE_SET_INITIAL_VALUES_SCHEMA = vol.Schema({
    vol.Required(CONF_DEVICE_ID): cv.string,
    vol.Optional(ATTR_COUNTER_A): vol.Coerce(float),
    vol.Optional(ATTR_COUNTER_B): vol.Coerce(float),
})

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

    # Регистрируем сервис для установки начальных показаний
    async def async_set_initial_values(call: ServiceCall) -> None:
        """Обработчик сервиса установки начальных показаний счетчиков."""
        device_id = call.data[CONF_DEVICE_ID]
        counter_a = call.data.get(ATTR_COUNTER_A)
        counter_b = call.data.get(ATTR_COUNTER_B)

        # Находим coordinator по device_id
        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get(device_id)

        if not device_entry:
            _LOGGER.error("Device %s not found", device_id)
            return

        # Находим entry для этого устройства
        for entry_id in device_entry.config_entries:
            if entry_id in hass.data.get(DOMAIN, {}):
                coordinator: ATickDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
                try:
                    await coordinator.device.set_counter_values(counter_a, counter_b)
                    # Обновляем данные координатора
                    await coordinator.async_request_refresh()
                    _LOGGER.info("Successfully set initial values for device %s", device_id)
                except Exception as err:
                    _LOGGER.error("Failed to set initial values: %s", err)
                return

        _LOGGER.error("Coordinator not found for device %s", device_id)

    # Регистрируем сервис только один раз для всего домена
    if not hass.services.has_service(DOMAIN, SERVICE_SET_INITIAL_VALUES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_INITIAL_VALUES,
            async_set_initial_values,
            schema=SERVICE_SET_INITIAL_VALUES_SCHEMA,
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
