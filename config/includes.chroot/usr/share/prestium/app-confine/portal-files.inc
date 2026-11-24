# app-confine fragment: the portal's file chooser. The dialog is the portal's (outside the application);
# the file the user picks is handed over through the document portal (/run/user/<uid>/doc, only this
# application's documents), not by widening the application's AppArmor profile. Only GetMountPoint of
# the document portal itself: no Add (exporting files the application can already open), no
# FileTransfer (drag and drop between applications).
include portal-base
call org.freedesktop.portal.Desktop org.freedesktop.portal.FileChooser.OpenFile@/org/freedesktop/portal/desktop
call org.freedesktop.portal.Desktop org.freedesktop.portal.FileChooser.SaveFile@/org/freedesktop/portal/desktop
call org.freedesktop.portal.Desktop org.freedesktop.portal.FileChooser.SaveFiles@/org/freedesktop/portal/desktop
call org.freedesktop.portal.Documents org.freedesktop.portal.Documents.GetMountPoint@/org/freedesktop/portal/documents
documents
