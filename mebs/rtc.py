"""DS3231 calendar validation with injected clock setting; no host clock changes."""
import calendar
from datetime import datetime, timezone


def bcd(value, limit):
    if value & 15 > 9 or value >> 4 > 9:
        raise ValueError('invalid RTC BCD')
    result = (value >> 4) * 10 + (value & 15)
    if result > limit:
        raise ValueError('invalid RTC field')
    return result


class DS3231:
    def __init__(self, bus):
        self.bus = bus

    def read(self):
        if self.bus.register(0x0f, 1)[0] & 0x80:
            raise ValueError('RTC oscillator stopped; set time explicitly')
        values = self.bus.register(0, 7)
        seconds, minutes = bcd(values[0], 59), bcd(values[1], 59)
        hour = values[2]
        if hour & 0x40:
            h = bcd(hour & 0x1f, 12)
            if h == 0:
                raise ValueError('invalid 12-hour clock')
            hour = h % 12 + (12 if hour & 0x20 else 0)
        else:
            hour = bcd(hour, 23)
        year = 2000 + bcd(values[6], 99) + (100 if values[5] & 0x80 else 0)
        if not 2020 <= year <= 2099:
            raise ValueError('RTC year outside supported deployment range')
        return datetime(year, bcd(values[5] & 0x1f, 12), bcd(values[4], 31), hour, minutes, seconds, tzinfo=timezone.utc)

    def restore(self, set_clock):
        dt = self.read()
        set_clock(calendar.timegm(dt.utctimetuple()))
        return dt

    def set(self, dt):
        if dt.tzinfo is None:
            raise ValueError('explicit timezone required')
        dt = dt.astimezone(timezone.utc)
        if not 2020 <= dt.year <= 2099:
            raise ValueError('unsupported year')
        def encode(n):
            return (n // 10 << 4) | n % 10
        values = [dt.second, dt.minute, dt.hour, dt.isoweekday(), dt.day, dt.month, dt.year - 2000]
        self.bus.write(bytes([0, *map(encode, values)]))
        status = self.bus.register(0x0f, 1)[0]
        self.bus.write(bytes([0x0f, status & ~0x80]))
