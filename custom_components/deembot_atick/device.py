import asyncio
import binascii
import dataclasses
import logging
import struct
import time
from contextlib import AsyncExitStack
from textwrap import wrap

from bleak import BleakClient, BLEDevice, AdvertisementData
from bleak.exc import BleakError

from .const import (UUID_ATTR_VERSION_FIRMWARE,
                    UUID_ATTR_MANUFACTURER,
                    UUID_SERVICE_AG,
                    UUID_AG_ATTR_VALUES,
                    UUID_AG_ATTR_RATIOS, DEFAULT_PIN_DEVICE, ACTIVE_POLL_INTERVAL, UUID_ATTR_MODEL)

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class ATickParsedAdvertisementData:
    counter_a_value: None | float = None
    counter_b_value: None | float = None


class ATickBTDevice:
    def __init__(self, ble_device: BLEDevice):
        self._last_active_update = -ACTIVE_POLL_INTERVAL
        self._ble_device = ble_device
        self.base_unique_id: str = self._ble_device.address
        self._client: BleakClient | None = None
        self._client_stack = AsyncExitStack()
        self._lock = asyncio.Lock()
        self.data = {
            'model': 'ATick',
            'manufacturer': '',
            'firmware_version': '',

            'counter_a_value': 0.0,
            'counter_b_value': 0.0,
            'counter_a_ratio': 0.01,
            'counter_b_ratio': 0.01,
        }

    def active_poll_needed(self, seconds_since_last_poll: float | None) -> bool:
        if seconds_since_last_poll is not None and seconds_since_last_poll < ACTIVE_POLL_INTERVAL:
            return False

        return (time.monotonic() - self._last_active_update) > ACTIVE_POLL_INTERVAL

    async def active_full_update(self):
        try:
            await self.device_info_update()
            await self.update_counters_value()

            self._last_active_update = time.monotonic()
        finally:
            await self.stop()

        _LOGGER.debug('active update')

    async def device_info_update(self):
        await self.update_model_name()
        await self.update_manufacturer()
        await self.update_firmware_version()

        _LOGGER.debug('device info active update')

    def parse_advertisement_data(self, pin: None | str, adv: AdvertisementData):
        new_values = (0, 0)

        try:
            new_values = self.parseAdvValuesCounters(
                adv.manufacturer_data.get(list(adv.manufacturer_data.keys())[-1]),
                pin or DEFAULT_PIN_DEVICE,
                self._ble_device.address
            )
        except Exception:
            pass

        return ATickParsedAdvertisementData(
            counter_a_value=new_values[0],
            counter_b_value=new_values[1]
        )

    def is_advertisement_changed(self, parsed_advertisement: ATickParsedAdvertisementData) -> bool:
        return (
                (parsed_advertisement.counter_a_value + parsed_advertisement.counter_b_value > 0)
                and (parsed_advertisement.counter_a_value != self.data['counter_a_value']
                     or parsed_advertisement.counter_b_value != self.data['counter_b_value'])
                )

    def update_from_advertisement(self, parsed_advertisement: ATickParsedAdvertisementData):
        self.data['counter_a_value'] = parsed_advertisement.counter_a_value
        self.data['counter_b_value'] = parsed_advertisement.counter_b_value

        _LOGGER.debug('update from advertisement')

    async def stop(self):
        try:
            await self._client.disconnect()
        except Exception:
            pass

        self._client = None

    @property
    def connected(self):
        return self._client is not None and self._client.is_connected

    async def get_client(self) -> BleakClient:
        async with self._lock:
            if not self.connected:
                _LOGGER.debug("Connecting")

                try:
                    self._client = await self._client_stack.enter_async_context(BleakClient(self._ble_device, timeout=15))
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

        _LOGGER.debug("Read data: %s", data)

        return data

    async def update_firmware_version(self):
        if data := await self.read_gatt(UUID_ATTR_VERSION_FIRMWARE):
            self.data['firmware_version'] = data.decode("utf-8")

    async def update_manufacturer(self):
        if data := await self.read_gatt(UUID_ATTR_MANUFACTURER):
            self.data['manufacturer'] = data.decode("utf-8")

    async def update_counters_value(self):
        if data := await self.read_gatt(UUID_AG_ATTR_VALUES):
            values = struct.unpack('<ff', data)
            self.data['counter_a_value'] = round(values[0], 2)
            self.data['counter_b_value'] = round(values[1], 2)

    async def update_counters_ratio(self):
        if data := await self.read_gatt(UUID_AG_ATTR_RATIOS):
            values = struct.unpack('<ff', data)
            self.data['counter_a_ratio'] = round(values[0], 2)
            self.data['counter_b_ratio'] = round(values[1], 2)

    async def update_model_name(self):
        if data := await self.read_gatt(UUID_ATTR_MODEL):
            self.data['model'] = data.decode("utf-8")

    @staticmethod
    def decToHex(num: int) -> str:
        return num.to_bytes((num.bit_length() + 7) // 8, 'little').hex() or '00'

    @staticmethod
    def midLittleIndian(valueHex):
        arr = wrap(valueHex, 2)

        return arr[2] + arr[3] + arr[0] + arr[1]

    def parseAdvValuesCounters(self, data, KEY, MAC):
        res = ''
        i4 = 0

        for i in range(6):
            i2 = i * 3
            i4 += int(MAC[i2:i2 + 2], 16)

        for i3 in range(4):
            i4 += (int(KEY) >> (i3 * 8)) & 255

        i8 = ((i4 ^ 255) + 1) & 255

        for i5 in range(1, 9):
            res += (self.decToHex((data[i5] ^ i8) & 255))

        floatHex = wrap(res, 8)

        return (
            round(struct.unpack('<f', binascii.a2b_hex(self.midLittleIndian(floatHex[0])))[0], 2),
            round(struct.unpack('<f', binascii.a2b_hex(self.midLittleIndian(floatHex[1])))[0], 2)
        )

    @property
    def name(self):
        return self._ble_device.name

    @property
    def model(self):
        return self.data['model']

    @property
    def manufacturer(self):
        return self.data['manufacturer']

    @property
    def firmware_version(self):
        return self.data['firmware_version']

    @property
    def counter_a_value(self):
        return self.data['counter_a_value']

    @property
    def counter_b_value(self):
        return self.data['counter_b_value']
