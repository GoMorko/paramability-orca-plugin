"""A stand-in for OrcaSlicer's embedded `orca` module: just enough for the plugin to import and run."""
import sys
import types


class PagesPluginCapabilityBase:
    """Records what the plugin sends to the page; the saved config is whatever a test sets."""

    config_json = "{}"

    def __init__(self):
        self.posted = []

    def post_message(self, data):
        self.posted.append(data)

    def get_config(self):
        return self.config_json


class Base:
    pass


class Calls:
    capabilities = []
    permissions = []
    notifications = []
    notification_error = None


def install():
    """Put a fake `orca` into sys.modules and return its recorded calls."""
    calls = Calls()
    calls.capabilities = []
    calls.permissions = []
    calls.notifications = []

    module = types.ModuleType("orca")
    module.pages = types.SimpleNamespace(PagesPluginCapabilityBase=PagesPluginCapabilityBase)
    module.base = Base
    module.plugin = lambda cls: cls
    module.register_capability = calls.capabilities.append
    module.request_permissions = lambda **kwargs: calls.permissions.append(kwargs)

    def push_notification(level, text, hyper_text="", on_click=None):
        if calls.notification_error is not None:
            raise calls.notification_error
        calls.notifications.append((level, text))

    level = types.SimpleNamespace(RegularNotificationLevel="regular")
    module.host = types.SimpleNamespace(
        ui=types.SimpleNamespace(NotificationLevel=level, push_notification=push_notification)
    )
    sys.modules["orca"] = module
    return calls
