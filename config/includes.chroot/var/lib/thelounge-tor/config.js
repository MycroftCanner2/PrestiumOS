"use strict";
// The Lounge configuration for Prestium's second instance, "IRC (Tor)"
// (https://thelounge.chat/docs/configuration). Same as the I2P instance (/var/lib/thelounge/config.js)
// except the port, the network presets and the proxy:
// - private mode, one pre-provisioned user "prestium" (per-boot random password and one-use
//   login token, see /usr/local/sbin/prestium-thelounge-setup tor)
// - web UI on 127.0.0.1:9010 only
// - IRC only through Tor's SOCKS port 127.0.0.1:9050, host names resolved by Tor (SOCKS5 with the
//   name, never a local DNS lookup). thelounge-tor.service sets PRESTIUM_LOUNGE_TOR=1, and The Lounge
//   (patched in hook 0200) then sends every network through 127.0.0.1:9050 whatever its proxy
//   settings say, each with its own SOCKS username (Tor isolates circuits by it). The firewall lets
//   the "thelounge-tor" user reach nothing but 127.0.0.1:9050.
// - no link previews / prefetch, no uploads, no logs on disk, no identd/LDAP/WEBIRC
module.exports = {
	public: false,
	host: "127.0.0.1",
	port: 9010,
	bind: undefined,
	reverseProxy: false,
	maxHistory: 10000,
	https: {enable: false, key: "", certificate: "", ca: ""},
	// Tech Innovation, one of the 10 Theme Factory themes (a root-owned copy of the I2P instance's
	// packages, made in hook 0500). Users can still pick another theme in Settings.
	theme: "thelounge-theme-tech-innovation",
	prefetch: false,
	disableMediaPreview: true,
	prefetchStorage: false,
	prefetchMaxImageSize: 2048,
	prefetchMaxSearchSize: 50,
	prefetchTimeout: 5000,
	fileUpload: {enable: false, maxFileSize: 10240, baseUrl: null},
	transports: ["websocket", "polling"],
	leaveMessage: "",
	// "defaults" is the form behind "Connect to a network" (The Lounge 4.5 allows only one): OFTC,
	// which needs no registration. The user "prestium" already has one network per preset
	// (see /usr/local/share/prestium-thelounge-tor/prestium.json), those without an account first:
	// OFTC, Ergo, DarkScience, IRCNow, then Libera.Chat, hackint, AlphaChat (SASL; Libera.Chat and
	// AlphaChat don't connect until their sign-in is filled in, see hook 0200). No default channels.
	// OFTC's certificate is for irc.oftc.net (Let's Encrypt), not for its onion address; the onion
	// address itself authenticates the server, so certificate checking is off for it only.
	defaults: {
		name: "OFTC",
		host: "oftcnet6xg6roj6d7id4y4cu6dchysacqj2ldgea73qzdagufflqxrid.onion",
		port: 6697,
		password: "",
		tls: true,
		rejectUnauthorized: false,
		nick: "anon%%%%",
		username: "user",
		realname: "anon",
		join: "",
		leaveMessage: "",
		proxyEnabled: true,
		proxyHost: "127.0.0.1",
		proxyPort: 9050,
		proxyUsername: "",
		proxyPassword: "",
	},
	lockNetwork: false,
	messageStorage: [],
	storagePolicy: {enabled: false, maxAgeDays: 7, deletionPolicy: "statusOnly"},
	useHexIp: false,
	webirc: null,
	identd: {enable: false, port: 113},
	oidentd: null,
	ldap: {enable: false},
	debug: {ircFramework: false, raw: false},
};
