# app-confine fragment: register a tray icon with the panel (waybar's StatusNotifierWatcher); the panel
# calls back into the application's own item, which needs no rule. Qt 5 applications (VLC, KeePassXC)
# first take the name org.kde.StatusNotifierItem-<their pid>-<n> (tray-items: for their own pid only),
# without which they show no tray icon (compatibility audit).
talk org.kde.StatusNotifierWatcher
tray-items
