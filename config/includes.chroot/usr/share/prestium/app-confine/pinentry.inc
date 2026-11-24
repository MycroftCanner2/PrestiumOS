# Compatibility audit: GnuPG's passphrase prompt for an application with a gpg-agent of its own (F-02:
# Gajim and its keys tool). That agent runs in the application's namespace, and its pinentry
# (pinentry-gnome3) shows the dialog through GCR's system prompter (gcr-prompter, outside). Only that
# name: not the keyring (org.gnome.keyring, org.freedesktop.secrets), and the application can't own it.
talk org.gnome.keyring.SystemPrompter
