// Prestium 2.1: Prestium Translate's engine. A small front end to bergamot-translator (Bergamot, the
// engine of Firefox Translations): it loads Mozilla's en->ru and ru->en models once and translates the
// text it is given on stdin, so the app pays the model load once per session, not per translation.
// Built by hook 0210-prestium-translate from the pinned bergamot-translator source (thirdparty/versions.sh);
// the app starts it in bubblewrap (no network, no home, read-only models, private /tmp) under the
// AppArmor child profile prestium_translate//engine.
//
//   prestium-translate-engine MODELDIR      MODELDIR/enru/ and MODELDIR/ruen/ hold Mozilla's three files each
//
// Protocol (binary-safe, one request at a time):
//   request:  "<en-ru|ru-en> <nbytes>\n" followed by nbytes of UTF-8 text
//             "ping 0\n" (loads nothing, answers OK 0) and "load <en-ru|ru-en> 0\n" (loads that model now)
//   answer:   "OK <nbytes>\n<translation>" or "ERR <nbytes>\n<message>"
// EOF on stdin ends the engine. Nothing is written to disk, nothing is cached between requests
// (bergamot's translation cache is off), and the engine never opens a socket.
#include <cstdio>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "translator/parser.h"
#include "translator/response.h"
#include "translator/response_options.h"
#include "translator/service.h"

using namespace marian::bergamot;

static const size_t MAX_REQUEST = 1u << 20;  // 1 MiB of text per request

static std::string modelConfig(const std::string &dir, const std::string &pair) {
  // Firefox Translations' settings for these models (int8, shifted alphas, shortlist, greedy search)
  const std::string d = dir + "/" + pair + "/";
  std::ostringstream c;
  c << "models:\n  - " << d << "model." << pair << ".intgemm.alphas.bin\n"
    << "vocabs:\n  - " << d << "vocab." << pair << ".spm\n  - " << d << "vocab." << pair << ".spm\n"
    << "shortlist:\n  - " << d << "lex.50.50." << pair << ".s2t.bin\n  - false\n"
    << "beam-size: 1\nnormalize: 1.0\nword-penalty: 0\nmax-length-break: 128\nmini-batch-words: 1024\n"
    << "workspace: 128\nmax-length-factor: 2.0\nskip-cost: true\ncpu-threads: 0\nquiet: true\n"
    << "quiet-translation: true\ngemm-precision: int8shiftAlphaAll\n";
  return c.str();
}

static void answer(const char *status, const std::string &body) {
  std::cout << status << " " << body.size() << "\n" << body;
  std::cout.flush();
}

int main(int argc, char *argv[]) {
  if (argc != 2) {
    std::cerr << "usage: prestium-translate-engine MODELDIR" << std::endl;
    return 2;
  }
  const std::string dir = argv[1];
  std::ios::sync_with_stdio(false);
  BlockingService::Config config;
  config.cacheSize = 0;           // no translation cache: nothing is kept between requests
  config.logger.level = "off";
  BlockingService service(config);
  std::map<std::string, std::shared_ptr<TranslationModel>> models;

  auto model = [&](const std::string &pair) -> std::shared_ptr<TranslationModel> {
    auto it = models.find(pair);
    if (it != models.end()) return it->second;
    auto options = parseOptionsFromString(modelConfig(dir, pair), /*validate=*/false);
    auto m = std::make_shared<TranslationModel>(options);
    models[pair] = m;
    return m;
  };

  std::string line;
  while (std::getline(std::cin, line)) {
    std::istringstream head(line);
    std::string cmd, arg;
    size_t n = 0;
    head >> cmd;
    if (cmd == "load") head >> arg;
    if (!(head >> n) || n > MAX_REQUEST) {
      answer("ERR", "bad request");
      return 1;  // the stream is out of step: stop rather than guess
    }
    std::string text(n, '\0');
    if (n && !std::cin.read(&text[0], static_cast<std::streamsize>(n))) return 1;
    try {
      if (cmd == "ping") {
        answer("OK", "");
      } else if (cmd == "load" && (arg == "en-ru" || arg == "ru-en")) {
        model(arg == "en-ru" ? "enru" : "ruen");
        answer("OK", "");
      } else if (cmd == "en-ru" || cmd == "ru-en") {
        const std::string pair = cmd == "en-ru" ? "enru" : "ruen";
        ResponseOptions ro;
        std::vector<std::string> in{std::move(text)};
        std::vector<ResponseOptions> opts{ro};
        std::vector<Response> out = service.translateMultiple(model(pair), std::move(in), opts);
        answer("OK", out.empty() ? std::string() : out.front().target.text);
      } else {
        answer("ERR", "unknown request");
      }
    } catch (const std::exception &e) {
      answer("ERR", e.what());
    }
  }
  return 0;
}
