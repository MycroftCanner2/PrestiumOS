# app-confine fragment: what every portal user needs. The toolkits read each portal's "version" (and
# so only use the portals they may call), the desktop settings (colour scheme, fonts, cursor) and the
# answers, which come as a Response signal on a Request object. No Properties.Set, no other portal.
call org.freedesktop.portal.Desktop org.freedesktop.DBus.Properties.Get@/org/freedesktop/portal/desktop
call org.freedesktop.portal.Desktop org.freedesktop.DBus.Properties.GetAll@/org/freedesktop/portal/desktop
call org.freedesktop.portal.Desktop org.freedesktop.portal.Settings.Read@/org/freedesktop/portal/desktop
call org.freedesktop.portal.Desktop org.freedesktop.portal.Settings.ReadAll@/org/freedesktop/portal/desktop
call org.freedesktop.portal.Desktop org.freedesktop.portal.Settings.ReadOne@/org/freedesktop/portal/desktop
broadcast org.freedesktop.portal.Desktop org.freedesktop.portal.Settings.SettingChanged@/org/freedesktop/portal/desktop
call org.freedesktop.portal.Desktop org.freedesktop.portal.Request.Close@/org/freedesktop/portal/desktop/request/*
broadcast org.freedesktop.portal.Desktop org.freedesktop.portal.Request.Response@/org/freedesktop/portal/desktop/request/*
