import array
import asyncio
import dataclasses
import logging
import time
from contextlib import AsyncExitStack
from textwrap import wrap

from bleak import BleakClient, BLEDevice, AdvertisementData
from bleak.exc import BleakError

from .const import (UUID_ATTR_VERSION_FIRMWARE,
                    UUID_ATTR_MANUFACTURER,
                    UUID_SERVICE_AG,
                    UUID_AG_ATTR_VALUES,
                    UUID_AG_ATTR_RATIOS,
                    DEFAULT_PIN_DEVICE,
                    ACTIVE_POLL_INTERVAL,
                    UUID_ATTR_MODEL)

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
        self.data: dict[str, str | int | float | None] = {
            'model': None,
            'manufacturer': None,
            'firmware_version': None,

            'counter_a_value': None,
            'counter_b_value': None,
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

            # Требуется сопряжение устройства
            # await self.update_counters_value()

            # Чтение множителей счетчиков
            await self.update_counters_ratio()
        finally:
            await self.stop()

        self._last_active_update = time.monotonic()

        _LOGGER.debug('active update')

    async def device_info_update(self):
        await self.update_model_name()
        await self.update_manufacturer()
        await self.update_firmware_version()

        _LOGGER.debug('device info active update')

    def parse_advertisement_data(self, pin: None | str, adv: AdvertisementData) -> ATickParsedAdvertisementData | None:
        # Может и не быть
        if not adv.manufacturer_data:
            return None

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
                ((parsed_advertisement.counter_a_value + parsed_advertisement.counter_b_value) > 0)
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
            values = array.array('f', data).tolist()
            self.data['counter_a_value'] = self.truncate_float(values[0], 2)
            self.data['counter_b_value'] = self.truncate_float(values[1], 2)

    async def update_counters_ratio(self):
        if data := await self.read_gatt(UUID_AG_ATTR_RATIOS):
            values = array.array('f', data).tolist()
            self.data['counter_a_ratio'] = self.truncate_float(values[0], 2)
            self.data['counter_b_ratio'] = self.truncate_float(values[1], 2)

    async def set_counter_values(self, counter_a: float | None = None, counter_b: float | None = None):
        """Установить начальные показания счетчиков."""
        # Получаем текущие значения
        current_a = self.data['counter_a_value'] or 0.0
        current_b = self.data['counter_b_value'] or 0.0

        # Используем переданные значения или оставляем текущие
        new_a = counter_a if counter_a is not None else current_a
        new_b = counter_b if counter_b is not None else current_b

        # Формируем массив float и конвертируем в байты
        data = array.array('f', [new_a, new_b]).tobytes()

        # Записываем в устройство
        await self.write_gatt(UUID_AG_ATTR_VALUES, data.hex())

        # Обновляем локальные данные
        self.data['counter_a_value'] = self.truncate_float(new_a, 2)
        self.data['counter_b_value'] = self.truncate_float(new_b, 2)

        _LOGGER.info("Set counter values: A=%.2f, B=%.2f", new_a, new_b)

    async def update_model_name(self):
        if data := await self.read_gatt(UUID_ATTR_MODEL):
            self.data['model'] = data.decode("utf-8")

    @staticmethod
    def is_encrypted(data: bytes):
        return (int.from_bytes(data[7:8]) & 16) != 0

    @staticmethod
    def decToHex(num: int) -> str:
        return num.to_bytes((num.bit_length() + 7) // 8, 'little').hex() or '00'

    @staticmethod
    def truncate_float(n, places):
        return int(n * (10 ** places)) / 10 ** places

    @staticmethod
    def midLittleIndian(valueHex):
        arr = wrap(valueHex, 2)

        return arr[2] + arr[3] + arr[0] + arr[1]

    def parseAdvValuesCounters(self, data, KEY, MAC):
        if self.is_encrypted(data):
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

            floatValues = array.array(
                'f',
                bytes.fromhex(self.midLittleIndian(res[0:8]) + self.midLittleIndian(res[8:16]))
            ).tolist()
        else:
            floatValues = array.array('f', data[1:9]).tolist()

        return [
            self.truncate_float(floatValues[0], 2),
            self.truncate_float(floatValues[1], 2)
        ]

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
