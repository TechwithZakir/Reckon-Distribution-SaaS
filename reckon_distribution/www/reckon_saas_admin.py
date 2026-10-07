from importlib import import_module

reckon_saas_admin = import_module("reckon_saas_platform.www.reckon_saas_admin")


def get_context(context):
    return reckon_saas_admin.get_context(context)
