// Prestium 1.9.1 (Tails-style): Tor Browser downloads and uploads use ~/Tor Browser,
// the only folder of your home the browser may access (AppArmor).
user_pref("browser.download.dir", "@DOWNLOADS@");
user_pref("browser.download.folderList", 2);
user_pref("browser.download.useDownloadDir", true);
user_pref("browser.download.lastDir", "@DOWNLOADS@");
user_pref("browser.download.start_downloads_in_tmp_dir", false);
user_pref("app.update.auto", false);
user_pref("app.update.enabled", false);
// Prestium 1.9.1: use the profile's certificate database (in RAM, like the whole
// home) so the explicit distrust of the eMudhra (emSign) roots seeded by the
// launcher overrides Tor Browser's built-in root list. Firefox no longer stores
// intermediate certificates there.
user_pref("security.nocertdb", false);
// Prestium 2.0 r19: no tabs in the title bar; the compositor draws the frame (minimise, maximise, close)
user_pref("browser.tabs.inTitlebar", 0);
