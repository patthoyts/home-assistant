"""
Integrate TiVo Digital Video Recorders using the TiVo TCP Remote Protocol.
"""

import logging
import socket
from datetime import timedelta
from tivoctl import Remote
import voluptuous as vol

from homeassistant.components.media_player import (
    MEDIA_TYPE_CHANNEL,
    SUPPORT_PAUSE, SUPPORT_PLAY, SUPPORT_TURN_ON, SUPPORT_TURN_OFF,
    SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_STEP, SUPPORT_SELECT_SOURCE,
    MediaPlayerDevice, PLATFORM_SCHEMA)
from homeassistant.const import (
    CONF_HOST, CONF_NAME, CONF_PORT, CONF_MAC,
    STATE_OFF, STATE_ON, STATE_UNKNOWN)
from tivoctl import (
    SCREEN_TIVO, SCREEN_GUIDE, SCREEN_LIVETV, SCREEN_NOWPLAYING)

import homeassistant.helpers.config_validation as cv
from homeassistant.util import dt as dt_util

REQUIREMENTS = ['tivoctl==0.0.1', 'wakeonlan==0.2.2']

_LOGGER = logging.getLogger(__name__)

CONF_TIMEOUT = 'timeout'

DEFAULT_NAME = 'TiVo Remote'
DEFAULT_PORT = 31339
DEFAULT_TIMEOUT = 100

KNOWN_DEVICES_KEY = 'tivo_known_devices'

SUPPORT_TIVODVR = SUPPORT_PAUSE | SUPPORT_PLAY | SUPPORT_SELECT_SOURCE | \
                  SUPPORT_TURN_ON | SUPPORT_TURN_OFF | \
                  SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_STEP

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the TiVo DVR remote platform"""
    known_devices = hass.data.get(KNOWN_DEVICES_KEY)
    if known_devices is None:
        known_devices = set()
        hass.data[KNOWN_DEVICES_KEY] = known_devices

    if config.get(CONF_HOST) is not None:
        host = config.get(CONF_HOST)
        port = config.get(CONF_PORT)
        name = config.get(CONF_NAME)
        mac = config.get(CONF_MAC)
        timeout = config.get(CONF_TIMEOUT)
    elif discovery_info is not None:
        _LOGGER.info(discovery_info)
        host = discovery_info.get('host')
        port = discovery_info.get('port')
        name = "TiVo {0}".format(discovery_info.get('hostname').split('.')[0])
        mac = None
        timeout = DEFAULT_TIMEOUT
    else:
        _LOGGER.warning("Cannot determine device")
        return

    ip_addr = socket.gethostbyname(host)
    if ip_addr not in known_devices:
        known_devices.add(ip_addr)
        add_devices([TivoDevice(host, port, name, timeout, mac)])
        _LOGGER.info("TiVo DVR '%s' found at %s:%d", name, host, port)
    else:
        _LOGGER.info("Ignoring duplicate TiVO DVR %s:%d", host, port)

class TivoDevice(MediaPlayerDevice):
    """Representation of a TiVo DVR device."""

    def __init__(self, host, port, name, timeout, mac):
        """Initialize the TiVo device"""
        self._remote_class = Remote
        self._name = name
        self._mac = mac
        self._muted = False
        self._channel = None
        self._playing = False
        self._state = STATE_UNKNOWN
        self._remote = None
        self._config = {
            'name': 'HomeAssistant',
            'description': name,
            'id': 'ha.component.tivo',
            'port': port,
            'host': host,
            'timeout': timeout/1000,
        }
        self.update()

    def update(self):
        """Update state of device"""
        try:
            self._channel = self.get_remote().channel
            self._state = STATE_ON
        except:
            self._state = STATE_OFF

    def get_remote(self):
        """Get the remote control instance."""
        if self._remote is None:
            self._remote = self._remote_class(self._config)
        return self._remote

    def send_key(self, key):
        self.get_remote().send_keyboard(key)
        self.update()

    def set_channel(self, channel):
        self.get_remote().set_channel(channel)
        self.update()

    def set_source(self, source):
        self.get_remote().teleport(source)
        self.update()

    @property
    def state(self):
        """State of the player."""
        return self._state
    @property
    def should_poll(self):
        """Device should be polled."""
        return True
    @property
    def name(self):
        return self._name
    @property
    def media_channel(self):
        """Channel currently playing."""
        if self._channel is None:
            self.update()
        return self._channel
    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._muted
    @property
    def supported_features(self):
        return SUPPORT_TIVODVR
    @property
    def source(self):
        """Return the current input source."""
        return self.get_remote().screen
    @property
    def source_list(self):
        """List of available input sources."""
        return [SCREEN_LIVETV, SCREEN_GUIDE, SCREEN_TIVO, SCREEN_NOWPLAYING]

    def volume_up(self):
        self.send_key('VOLUMEUP')
    def volume_down(self):
        self.send_key('VOLUMEDOWN')
    def mute_volume(self, is_volume_muted):
        self.send_key('MUTE')
        self._muted = not is_volume_muted
    def media_play_pause(self):
        if self._playing:
            self.media_pause()
        else:
            self.media_play()
    def media_play(self):
        self._playing = True
        self.send_key('PLAY')
    def media_play(self):
        self._playing = False
        self.send_key('PAUSE')
    def turn_on(self):
        """Turn the device on from standby."""
        self.send_key('STANDBY')
    def turn_off(self):
        """Put the device into standby mode."""
        self.send_key('STANDBY')
        self.send_key('STANDBY')
    def select_source(self, source):
        self.set_source(source)
