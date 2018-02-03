"""
Support for Nest devices.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/nest/
"""
import asyncio
import logging
import socket

import voluptuous as vol

from homeassistant import config_manager
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.const import (
    CONF_STRUCTURE, CONF_FILENAME, CONF_BINARY_SENSORS, CONF_SENSORS,
    CONF_MONITORED_CONDITIONS)

REQUIREMENTS = ['python-nest==3.1.0']

_CONFIGURING = {}
_LOGGER = logging.getLogger(__name__)

DOMAIN = 'nest'

DATA_NEST = 'nest'

NEST_CONFIG_FILE = 'nest.conf'
CONF_CLIENT_ID = 'client_id'
CONF_CLIENT_SECRET = 'client_secret'

ATTR_HOME_MODE = 'home_mode'
ATTR_STRUCTURE = 'structure'

SENSOR_SCHEMA = vol.Schema({
    vol.Optional(CONF_MONITORED_CONDITIONS): vol.All(cv.ensure_list)
})

AWAY_SCHEMA = vol.Schema({
    vol.Required(ATTR_HOME_MODE): cv.string,
    vol.Optional(ATTR_STRUCTURE): vol.All(cv.ensure_list, cv.string)
})

CONFIG_SCHEMA = vol.Schema({
    vol.Optional(DOMAIN): vol.Schema({
        vol.Required(CONF_CLIENT_ID): cv.string,
        vol.Required(CONF_CLIENT_SECRET): cv.string,
        vol.Optional(CONF_STRUCTURE): vol.All(cv.ensure_list, cv.string),
        vol.Optional(CONF_SENSORS): SENSOR_SCHEMA,
        vol.Optional(CONF_BINARY_SENSORS): SENSOR_SCHEMA
    })
}, extra=vol.ALLOW_EXTRA)


def request_configuration(nest, hass, config):
    """Request configuration steps from the user."""
    configurator = hass.components.configurator
    if 'nest' in _CONFIGURING:
        _LOGGER.debug("configurator failed")
        configurator.notify_errors(
            _CONFIGURING['nest'], "Failed to configure, please try again.")
        return

    def nest_configuration_callback(data):
        """Run when the configuration callback is called."""
        _LOGGER.debug("configurator callback")
        pin = data.get('pin')
        setup_nest(hass, nest, config, pin=pin)

    _CONFIGURING['nest'] = configurator.request_config(
        "Nest", nest_configuration_callback,
        description=('To configure Nest, click Request Authorization below, '
                     'log into your Nest account, '
                     'and then enter the resulting PIN'),
        link_name='Request Authorization',
        link_url=nest.authorize_url,
        submit_caption="Confirm",
        fields=[{'id': 'pin', 'name': 'Enter the PIN', 'type': ''}]
    )


def setup_nest(hass, nest, config, pin=None):
    """Set up the Nest devices."""
    if pin is not None:
        _LOGGER.debug("pin acquired, requesting access token")
        nest.request_token(pin)

    if nest.access_token is None:
        _LOGGER.debug("no access_token, requesting configuration")
        request_configuration(nest, hass, config)
        return

    if 'nest' in _CONFIGURING:
        _LOGGER.debug("configuration done")
        configurator = hass.components.configurator
        configurator.request_done(_CONFIGURING.pop('nest'))

    _LOGGER.debug("proceeding with setup")
    conf = config[DOMAIN]
    hass.data[DATA_NEST] = NestDevice(hass, conf, nest)

    _LOGGER.debug("proceeding with discovery")
    discovery.load_platform(hass, 'climate', DOMAIN, {}, config)
    discovery.load_platform(hass, 'camera', DOMAIN, {}, config)

    sensor_config = conf.get(CONF_SENSORS, {})
    discovery.load_platform(hass, 'sensor', DOMAIN, sensor_config, config)

    binary_sensor_config = conf.get(CONF_BINARY_SENSORS, {})
    discovery.load_platform(hass, 'binary_sensor', DOMAIN,
                            binary_sensor_config, config)

    _LOGGER.debug("setup done")

    return True


def setup(hass, config):
    """Set up the Nest thermostat component."""
    import nest

    if 'nest' in _CONFIGURING:
        return

    # Happens if we get set up for config entry.
    # TODO clean this up.
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    client_id = conf[CONF_CLIENT_ID]
    client_secret = conf[CONF_CLIENT_SECRET]
    filename = config.get(CONF_FILENAME, NEST_CONFIG_FILE)

    access_token_cache_file = hass.config.path(filename)

    nest = nest.Nest(
        access_token_cache_file=access_token_cache_file,
        client_id=client_id, client_secret=client_secret)
    setup_nest(hass, nest, config)

    def set_mode(service):
        """Set the home/away mode for a Nest structure."""
        if ATTR_STRUCTURE in service.data:
            structures = service.data[ATTR_STRUCTURE]
        else:
            structures = hass.data[DATA_NEST].local_structure

        for structure in nest.structures:
            if structure.name in structures:
                _LOGGER.info("Setting mode for %s", structure.name)
                structure.away = service.data[ATTR_HOME_MODE]
            else:
                _LOGGER.error("Invalid structure %s",
                              service.data[ATTR_STRUCTURE])

    hass.services.register(
        DOMAIN, 'set_mode', set_mode, schema=AWAY_SCHEMA)

    return True


class NestDevice(object):
    """Structure Nest functions for hass."""

    def __init__(self, hass, conf, nest):
        """Init Nest Devices."""
        self.hass = hass
        self.nest = nest

        if CONF_STRUCTURE not in conf:
            self.local_structure = [s.name for s in nest.structures]
        else:
            self.local_structure = conf[CONF_STRUCTURE]
        _LOGGER.debug("Structures to include: %s", self.local_structure)

    def thermostats(self):
        """Generate a list of thermostats and their location."""
        try:
            for structure in self.nest.structures:
                if structure.name in self.local_structure:
                    for device in structure.thermostats:
                        yield (structure, device)
                else:
                    _LOGGER.debug("Ignoring structure %s, not in %s",
                                  structure.name, self.local_structure)
        except socket.error:
            _LOGGER.error(
                "Connection error logging into the nest web service.")

    def smoke_co_alarms(self):
        """Generate a list of smoke co alarms."""
        try:
            for structure in self.nest.structures:
                if structure.name in self.local_structure:
                    for device in structure.smoke_co_alarms:
                        yield(structure, device)
                else:
                    _LOGGER.info("Ignoring structure %s, not in %s",
                                 structure.name, self.local_structure)
        except socket.error:
            _LOGGER.error(
                "Connection error logging into the nest web service.")

    def cameras(self):
        """Generate a list of cameras."""
        try:
            for structure in self.nest.structures:
                if structure.name in self.local_structure:
                    for device in structure.cameras:
                        yield(structure, device)
                else:
                    _LOGGER.info("Ignoring structure %s, not in %s",
                                 structure.name, self.local_structure)
        except socket.error:
            _LOGGER.error(
                "Connection error logging into the nest web service.")


@config_manager.HANDLERS.register(DOMAIN)
class NestConfigFlow(config_manager.ConfigFlowHandler):
    """Handle a configuration flow for Nest."""

    version = 1


@config_manager.HANDLERS.register(DOMAIN)
class NestConfig(config_manager.ConfigFlowHandler):
    # Future versions of config might require a migration
    VERSION = 1

    def __init__(self):
        # Data from step 0 that we'll store.
        self.client_data = None

    @asyncio.coroutine
    def async_step_init(self, user_input=None):
        """Start config flow."""
        if user_input is not None:
            self.client_data = user_input
            return (yield from self.async_step_authorize())

        return self.async_show_form(
            step_id='init',
            title='Client information',
            description='Some Markdown introduction',
            data_schema=vol.Schema({
                # Translation keys are:
                #   components.<comp name>.create_config.<step>.<key name>.caption
                #   components.<comp name>.create_config.<step>.<key name>.description
                # In this case: components.nest.create_config.0.client_id.caption
                vol.Required('client_id'): str,
                vol.Required('client_secret'): str,
            })
        )

    async def async_step_authorize(self, user_input=None):
        """Ask user to authorize."""
        if user_input is not None:
            # import nest
            # # Validate auth code and get access token
            # token_info = await nest.async_get_credentials(
            #     self.client_data['client_id'],
            #     self.client_data['client_secret'],
            #     user_input['auth_code'])
            # user = await nest.async_get_user(token_info['access_token'])
            return self.async_create_entry(
                title='Paulus Home',
                data={
                    'client_id': self.client_data['client_id'],
                    'client_secret': self.client_data['client_secret'],
                    'access_token': 'SOME ACCESS TOKEN',
                    'refresh_token': 'SOME REFRESH TOKEN'
                }
            )

        return self.async_show_form(
            step_id='authorize',
            title='Authorize account',
            description='''Next step is to authorize your account. Click the following link and put the auth code below.

[Authorize account](http://google.com)''',
            data_schema=vol.Schema({
                vol.Required('auth_code'): str
            })
        )


@asyncio.coroutine
def async_setup_entry(hass, entry):
    pass
