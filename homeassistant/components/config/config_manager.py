"""Http views to control the config manager."""
import asyncio

import voluptuous as vol

from homeassistant import config_manager
from homeassistant.components.http import (
    HomeAssistantView, RequestDataValidator)


# TEMP, to register Hue handler
from homeassistant.components import hue


# Will upload to PyPi when closer to merging.
REQUIREMENTS = ['https://github.com/balloob/voluptuous-json/archive/master.zip'
                '#voluptuous_json==0.1']


@asyncio.coroutine
def async_setup(hass):
    """Enable the Home Assistant views."""
    hass.http.register_view(ConfigManagerCreateView)
    hass.http.register_view(ConfigManagerProgressView)
    return True


def _prepare_json(result):
    """Convert result for JSON."""
    import voluptuous_json

    if result['type'] == config_manager.RESULT_TYPE_FORM:
        schema = result['data_schema']
        if schema is None:
            result['data_schema'] = []
        else:
            result['data_schema'] = voluptuous_json.convert(schema)


class ConfigManagerCreateView(HomeAssistantView):
    """View to create config flows."""

    url = '/api/config/config_manager/flow'
    name = 'api:config:config_manager:flow'

    @asyncio.coroutine
    @RequestDataValidator(vol.Schema({
        vol.Optional('domain'): str,
    }))
    def post(self, request, data):
        """Handle a POST request."""
        hass = request.app['hass']

        try:
            result = yield from hass.config_manager.async_init_flow(
                data['domain'])
        except config_manager.UnknownHandler:
            return self.json_message('Invalid handler specified', 404)
        except config_manager.UnknownStep:
            return self.json_message('Handler does not support init', 400)

        _prepare_json(result)

        return self.json(result)


class ConfigManagerProgressView(HomeAssistantView):
    """View to interact with the config manager."""

    url = '/api/config/config_manager/flow/{flow_id}'
    name = 'api:config:config_manager:flow:progress'

    @asyncio.coroutine
    @RequestDataValidator(vol.Schema(dict), allow_empty=True)
    def post(self, request, flow_id, data):
        """Handle a POST request."""
        hass = request.app['hass']

        try:
            result = yield from hass.config_manager.async_configure(
                flow_id, data)
        except config_manager.UnknownFlow:
            return self.json_message('Invalid flow specified', 404)
        except config_manager.UnknownStep:
            return self.json_message('Invalid step specified', 400)
        except vol.Invalid:
            return self.json_message('User input malformed', 400)

        _prepare_json(result)

        return self.json(result)
