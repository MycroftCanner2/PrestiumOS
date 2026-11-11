# Prestium (hook 0460): do not load the per-user site-packages
# (~/.local/lib/python3.X/site-packages). Python 3.11+ loads site as a frozen
# module, so a patch to site.py on disk never runs. This file is installed as
# sitecustomize, which site.execsitecustomize() imports after the system
# site-packages are set up. Setting ENABLE_USER_SITE to False here also stops
# usercustomize.py. Any user-site directories already on sys.path (if the
# directory existed at startup) are removed.
#
# sitecustomize runs after site.addusersitepackages(), so a .pth file in an
# already-existing user-site directory can still run first. Session processes
# also get PYTHONNOUSERSITE=1 from /etc/environment, which disables that path
# at interpreter start. onion-grater allows that variable (it does not point
# the interpreter at other code).

import os
import sys
import site

site.ENABLE_USER_SITE = False


def _drop_user_site_paths():
    user_site = getattr(site, "USER_SITE", None)
    if not user_site:
        return
    root = os.path.abspath(user_site)
    prefix = root + os.sep
    sys.path[:] = [
        p for p in sys.path
        if os.path.abspath(p) != root and not os.path.abspath(p).startswith(prefix)
    ]


_drop_user_site_paths()

# Debian's sitecustomize (the apport hook), diverted to sitecustomize.py.debian
_ver = "python%d.%d" % (sys.version_info[0], sys.version_info[1])
for _debian in (
    "/etc/%s/sitecustomize.py.debian" % _ver,
    "/usr/lib/%s/sitecustomize.py.debian" % _ver,
):
    if os.path.isfile(_debian):
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "_prestium_debian_sitecustomize", _debian
        )
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
        break
