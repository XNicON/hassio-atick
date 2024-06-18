from __future__ import annotations

import asyncio
import logging
from typing import Any
import voluptuous as vol
from bleak import BleakError

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, async_discovered_service_info
from homeassistant.const import CONF_ADDRESS, CONF_PIN
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, DEFAULT_PIN_DEVICE
from .device import ATickBTDevice

_LOGGER = logging.getLogger(__name__)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> FlowResult:
        """Handle the bluetooth discovery step."""

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        if not discovery_info.name.startswith('aTick'):
            return self.async_abort(reason="not_supported")

        self._discovery_info = discovery_info

        self.context["title_placeholders"] = {
            "name": discovery_info.name,
            "address": discovery_info.address
        }

        return await self.async_step_user()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the user step to pick discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            pin = user_input[CONF_PIN]
            discovery_info = self._discovered_devices[address]

            if not (len(pin) in (4, 6, 8) and pin.isdigit()):
                errors["base"] = "pin_invalid"

            if errors.get("base") is None:
                await self.async_set_unique_id(discovery_info.address, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                name = discovery_info.name
                device = ATickBTDevice(discovery_info.device)

                try:
                    await device.device_info_update()
                except (BleakError, asyncio.TimeoutError):
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error")
                    errors["base"] = "unknown"
                else:
                    await device.stop()

                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_ADDRESS: discovery_info.address,
                            CONF_PIN: pin,
                            "device_info": {
                                "model": device.model,
                                "manufacturer": device.manufacturer,
                                "firmware_version": device.firmware_version,
                            }
                        }
                    )

        if errors.get("base") is None:
            # Set mac in configuration.yaml or list mac addresses
            if discovery := self._discovery_info:
                self._discovered_devices[discovery.address] = discovery
            else:
                current_addresses = self._async_current_ids()

                for discovery in async_discovered_service_info(self.hass):
                    if discovery.address in current_addresses or discovery.address in self._discovered_devices:
                        continue

                    if discovery.name.startswith('aTick'):
                        self._discovered_devices[discovery.address] = discovery

            if not self._discovered_devices:
                return self.async_abort(reason="no_devices_found")

        current_value = user_input.get(CONF_PIN) if user_input is not None else ""

        data_schema = vol.Schema({
            vol.Required(CONF_ADDRESS): vol.In({
                service_info.address: f"{service_info.name} ({service_info.address})"
                for service_info in self._discovered_devices.values()
            }),
            vol.Required(CONF_PIN, default=current_value or DEFAULT_PIN_DEVICE): cv.string,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            pin = user_input[CONF_PIN]

            if not (len(pin) in (4, 6, 8) and pin.isdigit()):
                errors["base"] = "pin_invalid"

            if errors.get("base") is None:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data=entry.data | {
                        CONF_PIN: pin,
                    }
                )

                if await self.hass.config_entries.async_reload(entry.entry_id):
                    return self.async_abort(reason="reconfigure_successful")

        current_value = user_input.get(CONF_PIN) if user_input is not None else ""

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_PIN, default=current_value): cv.string,
            }),
            errors=errors
        )
