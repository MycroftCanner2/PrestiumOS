"use strict";
// Prestium: the launcher (prestium-irc) opens this page with the per-boot token in the
// URL fragment. Store it the way The Lounge stores a remembered sign-in, then open it.
(function () {
	var t = window.location.hash.slice(1);
	if (/^[0-9a-f]{128}$/.test(t)) {
		try {
			window.localStorage.setItem("user", "prestium");
			window.localStorage.setItem("token", t);
		} catch (e) {}
	}
	window.history.replaceState(null, "", window.location.pathname);
	window.location.replace("/");
})();
