import os
import importlib

module_names = [
    i.rsplit(".", 1)[0]
    for i in os.listdir(os.path.dirname(__file__))
    if not i.startswith("__")
]

modules = [importlib.import_module("packages." + module) for module in module_names]


def reload_modules():
    for module in modules:
        importlib.reload(module)
