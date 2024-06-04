import asyncio
import binascii
import logging
import struct
import time
from contextlib import AsyncExitStack
from textwrap import wrap

from bleak import BleakClient, BLEDevice
from bleak.exc import BleakError

from .const import (UUID_ATTR_VERSION_FIRMWARE,
                    UUID_ATTR_MANUFACTURER,
                    UUID_SERVICE_AG,
                    UUID_AG_ATTR_VALUES,
                    UUID_AG_ATTR_RATIOS)

_LOGGER = logging.getLogger(__name__)

class ATickBTDevice:
    def __init__(self, ble_device: BLEDevice):
        self._ble_device = ble_device
        self.base_unique_id: str = self._ble_device.address
        self._client: BleakClient | None = None
        self._client_stack = AsyncExitStack()
        self._lock = asyncio.Lock()
        self._firmware_version: str | None = None
        self._manufacturer: str | None = None
        self._counter_a_value: float | None = None
        self._counter_a_ratio: float | None = None
        self._counter_b_value: float | None = None
        self._counter_b_ratio: float | None = None

    async def update(self):
        await self.update_manufacturer()
        await self.update_firmware_version()
        await self.update_counters_value()

    async def stop(self):
        self._client = None

    @property
    def connected(self):
        return self._client is not None and self._client.is_connected

    async def get_client(self) -> BleakClient:
        async with self._lock:
            if not self.connected:
                _LOGGER.debug("Connecting")

                try:
                    self._client = await self._client_stack.enter_async_context(BleakClient(self._ble_device, timeout=30))
                except asyncio.TimeoutError as exc:
                    _LOGGER.debug("Timeout on connect", exc_info=True)
                    raise asyncio.TimeoutError("Timeout on connect") from exc
                except BleakError as exc:
                    _LOGGER.debug("Error on connect", exc_info=True)
                    raise asyncio.TimeoutError("Error on connect") from exc
            else:
                _LOGGER.debug("Connection reused")

        return self._client

    async def write_gatt(self, uuid, data):
        client = await self.get_client()

        await client.write_gatt_char(uuid, bytearray.fromhex(data), True)

    async def read_gatt(self, uuid):
        client = await self.get_client()
        characteristic_value = (client
            .services.get_service(UUID_SERVICE_AG)
            .get_characteristic(uuid))

        data = await client.read_gatt_char(characteristic_value)

        _LOGGER.debug("Read data: %s", str(wrap(binascii.b2a_hex(data).decode("utf-8"), 2)))

        return data

    async def update_firmware_version(self):
        data = await self.read_gatt(UUID_ATTR_VERSION_FIRMWARE)
        self._firmware_version = data.decode("utf-8")

    async def update_manufacturer(self):
        data = await self.read_gatt(UUID_ATTR_MANUFACTURER)
        self._manufacturer = data.decode("utf-8")

    async def update_counters_value(self):
        if data := await self.read_gatt(UUID_AG_ATTR_VALUES):
            values = struct.unpack('<ff', data)
            self._counter_a_value = round(values[0], 2)
            self._counter_b_value = round(values[1], 2)

    async def update_counters_ratio(self):
        if data := await self.read_gatt(UUID_AG_ATTR_RATIOS):
            values = struct.unpack('<ff', data)
            self._counter_a_ratio = round(values[0], 2)
            self._counter_b_ratio = round(values[1], 2)

    @property
    def name(self):
        return self._ble_device.name

    @property
    def manufacturer(self):
        return self._manufacturer

    @property
    def firmware_version(self):
        return self._firmware_version

    @property
    def counter_a_value(self):
        return self._counter_a_value

    @property
    def counter_b_value(self):
        return self._counter_b_value
