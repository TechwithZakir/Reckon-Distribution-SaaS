from importlib import import_module

reckonerp_subscription = import_module("reckon_saas_platform.www.reckonerp_subscription")


def get_context(context):
    return reckonerp_subscription.get_context(context)
