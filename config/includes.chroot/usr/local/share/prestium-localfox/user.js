// Prestium local-only Firefox (copied into the profile on every launch).
// Firefox defaults otherwise; the firewall is what keeps this browser local.
user_pref("browser.startup.homepage", "http://127.0.0.1:7070/");
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("startup.homepage_welcome_url", "");
user_pref("startup.homepage_welcome_url.additional", "");
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.newtabpage.enabled", false);
user_pref("browser.search.update", false);
user_pref("browser.urlbar.suggest.searches", false);
user_pref("network.captive-portal-service.enabled", false);
user_pref("network.predictor.enabled", false);
user_pref("network.http.speculative-parallel-limit", 0);
user_pref("services.settings.server", "http://127.0.0.1:9/");
user_pref("media.gmp-manager.url", "http://127.0.0.1:9/");
user_pref("extensions.update.enabled", false);
user_pref("extensions.systemAddon.update.enabled", false);
user_pref("app.normandy.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("signon.rememberSignons", false);
// 2.0 r4: no first-run screens. The profile lives in the live session, so every boot was a "first
// run": Terms of Use / privacy notice (also the SkipTermsOfUse policy), data-reporting notice,
// welcome (trailhead) pages, What's New.
user_pref("termsofuse.bypassNotification", true);
user_pref("termsofuse.acceptedVersion", 999);
user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);
user_pref("datareporting.policy.firstRunURL", "");
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("browser.startup.firstrunSkipsHomepage", false);
user_pref("browser.uitour.enabled", false);
user_pref("browser.newtabpage.activity-stream.asrouter.providers.onboarding", "{\"id\":\"onboarding\",\"type\":\"local\",\"localProvider\":\"OnboardingMessageProvider\",\"enabled\":false,\"exclude\":[]}");
user_pref("browser.newtabpage.activity-stream.asrouter.userprefs.cfr.addons", false);
user_pref("browser.newtabpage.activity-stream.asrouter.userprefs.cfr.features", false);
user_pref("browser.messaging-system.whatsNewPanel.enabled", false);
// Prestium 2.0 r19: no tabs in the title bar; the compositor draws the frame (minimise, maximise, close)
user_pref("browser.tabs.inTitlebar", 0);
// 2.1 (L-5): its own download folder, the only one in the home it may write (AppArmor)
user_pref("browser.download.dir", "/home/user/Downloads/Local Firefox");
user_pref("browser.download.lastDir", "/home/user/Downloads/Local Firefox");
user_pref("browser.download.folderList", 2);
user_pref("browser.download.useDownloadDir", true);
