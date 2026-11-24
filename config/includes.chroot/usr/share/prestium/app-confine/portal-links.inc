# app-confine fragment: open a link (OpenURI.OpenURI only). The portal runs Prestium's link handler
# (/usr/local/lib/prestium/portal-open): http and https open in Tor Browser, mailto in Claws Mail,
# anything else is refused. Not OpenFile or OpenDirectory (a file handed to whatever program the portal
# would pick).
include portal-base
call org.freedesktop.portal.Desktop org.freedesktop.portal.OpenURI.OpenURI@/org/freedesktop/portal/desktop
call org.freedesktop.portal.Desktop org.freedesktop.portal.OpenURI.SchemeSupported@/org/freedesktop/portal/desktop
