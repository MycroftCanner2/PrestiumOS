"use strict";
// Prestium: serves /packages/thelounge-prestium-autologin/autologin.{html,js}
// (same origin as The Lounge, so the page can store the login token for it).
module.exports = {
	onServerStart(api) {
		api.PublicFiles.add("autologin.html");
		api.PublicFiles.add("autologin.js");
	},
};
