"""Reject active configurations that depend on unconfirmed electrical facts."""
import math
from .sensors import validate_addresses


def positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(name + ': positive confirmed number required')


def validate_runtime(config):
    validate_addresses(config)
    mode = config.get('sensor_mode', 'REAL')
    if mode not in ('REAL', 'SIMULATION') or mode == 'SIMULATION' and config.get('simulation_explicit') is not True:
        raise ValueError('SIMULATION requires explicit test configuration')
    monitors = [name for name in ('ina226', 'ina231') if config.get(name, {}).get('enabled')]
    if len(monitors) > 1:
        raise ValueError('Only one battery monitor may own the pack I2C role')
    devices = monitors + [name for name in ('ds3231',) if config.get(name,{}).get('enabled')]
    if config.get('bh1750', {}).get('enabled'):
        raise ValueError('BH1750 ambient sensor is not supported in V2')
    if devices and mode == 'REAL' and config.get('i2c_logic_3v3_confirmed') is not True:
        raise ValueError('Confirm 3.3V I2C supply/pullups before enabling sensors')
    if config.get('ina231', {}).get('enabled') and mode == 'REAL' and config['ina231'].get('model_confirmed') is not True:
        raise ValueError('INA231 package/model confirmation required; no device-ID register exists')
    ina = config.get(monitors[0], {}) if monitors else {}
    if ina.get('enabled') and ina.get('shunt_ohms') is not None:
        positive(ina['shunt_ohms'],'INA shunt')
        positive(ina.get('shunt_power_w'),'INA shunt rating')
        positive(ina.get('max_current_a'),'INA maximum current')
        if ina['max_current_a']**2*ina['shunt_ohms'] > ina['shunt_power_w']:
            raise ValueError('I squared R exceeds shunt rating')
        if ina['max_current_a']*ina['shunt_ohms'] > .08192:
            raise ValueError('Shunt voltage exceeds INA measurement range')
    thresholds = config.get('battery_thresholds',{})
    warn, block = thresholds.get('warn'), thresholds.get('block')
    if warn is not None or block is not None:
        if mode == 'REAL' and config.get('battery_bms_confirmed') is not True:
            raise ValueError('Battery/BMS specifications are required for protection thresholds')
        positive(block,'battery block')
        if warn is not None:
            positive(warn,'battery warning')
        if warn is not None and not block < warn:
            raise ValueError('battery block must be below warning')
        if not monitors or ina.get('shunt_ohms') is None:
            raise ValueError('Battery protection requires calibrated INA measurements')
        if mode == 'REAL' and config.get('battery_pack_vbus_confirmed') is not True:
            raise ValueError('Confirm that INA VBUS measures the 2S pack, not the 5V rail')
    display = config.get('display',{})
    if config.get('touch',{}).get('device') and display.get('touch_controller_confirmed') is not True:
        raise ValueError('Identify touch controller and evdev mapping before enabling touch')
    if config.get('drm_card') and display.get('panel_confirmed') is not True:
        raise ValueError('Confirm panel/controller/DRM mode before enabling DSI output')
    if config.get('power_cutoff',{}).get('gpio_enabled'):
        raise ValueError('GPIO battery cutoff is outside this hardware revision')
    preview = config.get('battery_display_simulation', {})
    if preview.get('enabled') is True:
        voltage, current = preview.get('voltage_v'), preview.get('current_a')
        if (type(voltage) not in (int,float) or not math.isfinite(voltage) or not 0 < voltage <= 36
                or type(current) not in (int,float) or not math.isfinite(current) or abs(current) > 8):
            raise ValueError('display simulation requires finite INA-range values')
    design = config.get('battery_design', {})
    if design.get('empty_v') is not None:
        positive(design['empty_v'], 'display 0% voltage')
        positive(design.get('full_v'), 'display 100% voltage')
        positive(design.get('capacity_ah_nominal'), 'nominal capacity')
        if not design['empty_v'] < design['full_v']:
            raise ValueError('display voltage endpoints must increase')
    return config
