"use strict";
const fs = require("fs");
const path = require("path");
const Module = require("module");

function loadAs(realPath, src) {
  const m = new Module(realPath);
  m.filename = realPath;
  m.paths = Module._nodeModulePaths(path.dirname(realPath));
  m._compile(src, realPath);
  return m.exports.default;
}

function texts(messages) {
  return messages.map((m) => (m && m.text) || String(m));
}

const connSrc = fs.readFileSync(process.argv[2], "utf8");
const connectSrc = fs.readFileSync(process.argv[3], "utf8");
const realConn = process.argv[4] || process.argv[2];
const realConnect = process.argv[5] || process.argv[3];

const plugin = loadAs(path.resolve(realConn), connSrc);

function runPlugin(userDisconnected) {
  const messages = [];
  const events = [];
  const network = {
    userDisconnected,
    host: "127.0.0.1",
    port: 6668,
    getLobby() {
      return {
        pushMessage(client, msg) {
          messages.push(msg);
        },
      };
    },
  };
  const irc = {
    on(ev) {
      events.push(ev);
    },
  };
  plugin.apply({}, [irc, network]);
  return { messages: texts(messages), events };
}

const idle = runPlugin(true);
if (idle.messages.some((t) => t.includes("Network created"))) {
  console.error("FAIL userDisconnected=true still pushed:", idle.messages);
  process.exit(1);
}
if (!idle.events.includes("reconnecting") || !idle.events.includes("socket connected")) {
  console.error("FAIL reconnect/connected handlers not registered:", idle.events);
  process.exit(1);
}

const going = runPlugin(false);
if (!going.messages.some((t) => t === "Network created, connecting to 127.0.0.1:6668...")) {
  console.error("FAIL userDisconnected=false missing connecting message:", going.messages);
  process.exit(1);
}

const input = loadAs(path.resolve(realConnect), connectSrc);
const messages = [];
const state = { called: false, connected: false };
const network = {
  userDisconnected: true,
  host: "127.0.0.1",
  port: 6668,
  irc: {
    get connected() {
      return state.connected;
    },
    connect() {
      state.called = true;
    },
  },
  getLobby() {
    return {
      pushMessage(client, msg) {
        messages.push(msg);
      },
    };
  },
};
const client = {
  saved: false,
  save() {
    this.saved = true;
  },
};
input.input.call(client, network, { pushMessage() {} }, "connect", []);
const got = texts(messages);
if (network.userDisconnected !== false || !client.saved || !state.called) {
  console.error("FAIL /connect did not start a connection", {
    userDisconnected: network.userDisconnected,
    saved: client.saved,
    called: state.called,
  });
  process.exit(1);
}
if (!got.includes("Connecting to 127.0.0.1:6668...")) {
  console.error("FAIL /connect missing Connecting to message:", got);
  process.exit(1);
}

// Already connected: error, no second connecting line, no connect()
messages.length = 0;
state.called = false;
state.connected = true;
network.userDisconnected = false;
input.input.call(client, network, {
  pushMessage(c, msg) {
    messages.push(msg);
  },
}, "connect", []);
if (state.called) {
  console.error("FAIL already-connected still called irc.connect()");
  process.exit(1);
}
if (texts(messages).some((t) => t.includes("Connecting to "))) {
  console.error("FAIL already-connected showed Connecting to:", texts(messages));
  process.exit(1);
}
if (!texts(messages).some((t) => t === "You are already connected.")) {
  console.error("FAIL already-connected missing error:", texts(messages));
  process.exit(1);
}
console.log("OK   behaviour");
