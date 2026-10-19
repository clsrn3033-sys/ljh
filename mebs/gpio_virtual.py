"""Pi 4B 40-pin header design and isolated test bus; no GPIO device access."""
from dataclasses import asdict, dataclass

# Physical pin order, Raspberry Pi 4B 40-pin J8 header. GPIO numbers are BCM.
_PINS = (
    ('3V3',None),('5V',None),('SDA1',2),('5V',None),('SCL1',3),('GND',None),
    ('GPIO4',4),('TXD0',14),('GND',None),('RXD0',15),('GPIO17',17),('GPIO18',18),
    ('GPIO27',27),('GND',None),('GPIO22',22),('GPIO23',23),('3V3',None),('GPIO24',24),
    ('MOSI',10),('GND',None),('MISO',9),('GPIO25',25),('SCLK',11),('CE0',8),
    ('GND',None),('CE1',7),('ID_SD',0),('ID_SC',1),('GPIO5',5),('GND',None),
    ('GPIO6',6),('GPIO12',12),('GPIO13',13),('GND',None),('GPIO19',19),('GPIO16',16),
    ('GPIO26',26),('GPIO20',20),('GND',None),('GPIO21',21),
)


@dataclass(frozen=True)
class Pin:
    physical: int
    bcm: int | None
    default_function: str
    assignment: str
    component: str
    status: str
    config_location: str
    virtual_result: str = 'SIMULATION TESTED'
    hardware_result: str = 'HARDWARE NOT TESTED'


def pinmap():
    assigned = {1: ('INA226/INA231 VCC','battery monitor'),
                3: ('INA226/INA231 SDA1','battery monitor'),
                5: ('INA226/INA231 SCL1','battery monitor'),
                6: ('INA226/INA231 GND','battery monitor')}
    pins = []
    for number,(function,bcm) in enumerate(_PINS,1):
        allocation = assigned.get(number)
        reserved = number in (27,28)
        pins.append(Pin(number,bcm,function,allocation[0] if allocation else '미사용',
                        allocation[1] if allocation else 'N/A',
                        '설계 할당' if allocation else 'HAT ID 예약' if reserved else '미사용',
                        'buildroot/board/mebs-pi4-dsi/overlay/boot/config.txt; '
                        'buildroot/board/mebs-pi4-dsi/overlay/etc/mebs/hardware.json'
                        if number in (3,5) else 'mebs/gpio_virtual.py' if allocation else 'N/A'))
    validate(pins)
    return pins


def validate(pins):
    if len(pins) != 40 or {p.physical for p in pins} != set(range(1,41)):
        raise ValueError('header must contain physical pins 1..40 once')
    if len({p.bcm for p in pins if p.bcm is not None}) != 28:
        raise ValueError('BCM GPIO pin mapping collision')
    if {p.physical:p.bcm for p in pins if p.physical in (3,5,27,28)} != {3:2,5:3,27:0,28:1}:
        raise ValueError('I2C/HAT ID pin mapping mismatch')
    allocated = [p for p in pins if p.status == '설계 할당']
    if {p.physical for p in allocated} != {1,3,5,6}:
        raise ValueError('MEBS INA connector allocation conflict')
    if any(p.status == '설계 할당' for p in pins if p.physical in (27,28)):
        raise ValueError('HAT ID pins may not be assigned')
    return True


class VirtualI2CBus:
    """Addressed register devices, attached only by a test; never opens /dev."""
    simulation = True

    def __init__(self):
        self.devices = {}

    def attach(self,address,device):
        if not isinstance(address,int) or not 0x08 <= address <= 0x77:
            raise ValueError('invalid I2C address')
        if address in self.devices:
            raise ValueError('I2C address collision')
        if not getattr(device,'simulation',False):
            raise ValueError('virtual bus accepts simulated devices only')
        self.devices[address] = device

    def device(self,address):
        if address not in self.devices:
            raise OSError('virtual I2C NACK')
        return self.devices[address]


def json_data():
    return {'board':'Raspberry Pi 4 Model B', 'numbering':'physical + BCM',
            'mode':'SIMULATION DESIGN ONLY', 'pins':[asdict(p) for p in pinmap()]}
