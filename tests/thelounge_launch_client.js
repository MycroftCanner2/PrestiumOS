"use strict";
// Test client for tests/test_thelounge_launch_token.sh: one socket.io v4 sign-in to The Lounge
// over a WebSocket, with a token. Prints JSON {ok, initToken}.
const WebSocket = require(process.argv[2]);
const [port, user, token] = process.argv.slice(3);
const ws = new WebSocket(`ws://127.0.0.1:${port}/socket.io/?EIO=4&transport=websocket`);
let done = false;
const finish = (r) => { if (!done) { done = true; console.log(JSON.stringify(r)); ws.close(); setTimeout(() => process.exit(0), 50); } };
setTimeout(() => finish({ok: false, err: "timeout"}), 8000);
ws.on("message", (m) => {
	m = m.toString();
	if (m.startsWith("0")) ws.send("40");
	else if (m === "2") ws.send("3");
	else if (m.startsWith("42")) {
		const [ev, data] = JSON.parse(m.slice(2));
		if (ev === "auth:start") ws.send("42" + JSON.stringify(["auth:perform", {user, token, lastMessage: -1, openChannel: -1, hasConfig: true}]));
		else if (ev === "auth:failed") finish({ok: false});
		else if (ev === "init") finish({ok: true, initToken: data && data.token || null});
	}
});
ws.on("error", (e) => finish({ok: false, err: e.message}));
