"""Reject active configurations that depend on unconfirmed electrical facts."""
import math
from .sensors import validate_addresses


def positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(name + ': positive confirmed number required')


def validate_runtime(config):
    validate_addresses(config)
    devices = [name for name in ('ina226','ds3231') if config.get(name,{}).get('enabled')]
    if config.get('bh1750', {}).get('enabled'):
        raise ValueError('BH1750 ambient sensor is not supported in V2')
    if devices and config.get('i2c_logic_3v3_confirmed') is not True:
        raise ValueError('Confirm 3.3V I2C supply/pullups before enabling sensors')
    ina = config.get('ina226',{})
    if ina.get('enabled') and ina.get('shunt_ohms') is not None:
        positive(ina['shunt_ohms'],'INA226 shunt')
        positive(ina.get('shunt_power_w'),'INA226 shunt rating')
        positive(ina.get('max_current_a'),'INA226 maximum current')
        if ina['max_current_a']**2*ina['shunt_ohms'] > ina['shunt_power_w']:
            raise ValueError('I squared R exceeds shunt rating')
        if ina['max_current_a']*ina['shunt_ohms'] > .08192:
            raise ValueError('Shunt voltage exceeds INA226 measurement range')
    thresholds = config.get('battery_thresholds',{})
    warn, block = thresholds.get('warn'), thresholds.get('block')
    if warn is not None or block is not None:
        if config.get('battery_bms_confirmed') is not True:
            raise ValueError('Battery/BMS specifications are required for protection thresholds')
        positive(warn,'battery warning');positive(block,'battery block')
        if not block < warn:
            raise ValueError('battery block must be below warning')
        if not ina.get('enabled'):
            raise ValueError('Battery protection requires INA226 measurements')
    display = config.get('display',{})
    if config.get('touch',{}).get('device') and display.get('touch_controller_confirmed') is not True:
        raise ValueError('Identify touch controller and evdev mapping before enabling touch')
    if config.get('drm_card') and display.get('panel_confirmed') is not True:
        raise ValueError('Confirm panel/controller/DRM mode before enabling DSI output')
    if config.get('power_cutoff',{}).get('gpio_enabled'):
        raise ValueError('GPIO battery cutoff is outside this hardware revision')
    return config
