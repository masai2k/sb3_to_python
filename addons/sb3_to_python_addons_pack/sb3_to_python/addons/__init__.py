
from .official import OfficialExtensionsAddon
from .custom_generic import GenericCustomExtensionAddon

def load_addons():
    return [
        OfficialExtensionsAddon(),
        GenericCustomExtensionAddon(),
    ]
