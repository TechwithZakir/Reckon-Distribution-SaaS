from importlib import import_module

reckonerp_signup = import_module("reckon_saas_platform.www.reckonerp_signup")


def get_context(context):
    return reckonerp_signup.get_context(context)
