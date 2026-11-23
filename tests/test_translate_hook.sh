#!/bin/bash
# Prestium 2.1: Prestium Translate's build path. fetch-thirdparty.sh pins the engine source (bergamot-translator
# at BERGAMOT_COMMIT with its submodules, one tar, BERGAMOT_TAR_SHA256) and Mozilla's six model files (signed
# Remote Settings records, then TR_*_SHA256); hook 0210 refuses a staging tree that is not exactly those files
# with those hashes. Here: the pins and the fetch steps (static), then hook 0210 on fake staging trees
# (PRESTIUM_HOOK_ROOT, PRESTIUM_TRANSLATE_VERIFY_ONLY=1: nothing is built or installed): a good tree passes, a
# changed, missing or extra file, an extra or missing SHA256SUMS line and a symlink each stop it. Also the
# signature checker's own refusals (scripts/translate-models.py, offline).
set -u; R=$(cd "$(dirname "$0")/.." && pwd); fail=0
ok(){ echo "OK   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
F=$R/scripts/fetch-thirdparty.sh; V=$R/thirdparty/versions.sh; H=$R/config/hooks/live/0210-prestium-translate.hook.chroot
M=$R/scripts/translate-models.py
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

## pins
# shellcheck source=../thirdparty/versions.sh
. "$V"
[[ $BERGAMOT_COMMIT =~ ^[0-9a-f]{40}$ ]] && ok "bergamot-translator pinned to a full commit" || bad "BERGAMOT_COMMIT"
for v in BERGAMOT_TAR_SHA256 TR_ENRU_MODEL_SHA256 TR_ENRU_LEX_SHA256 TR_ENRU_VOCAB_SHA256 TR_RUEN_MODEL_SHA256 TR_RUEN_LEX_SHA256 TR_RUEN_VOCAB_SHA256; do
  [[ ${!v} =~ ^[0-9a-f]{64}$ ]] && ok "$v pinned" || bad "$v not a SHA-256"
done
[[ $TR_ENRU_VERSION =~ ^[0-9]+\.[0-9]+$ && $TR_RUEN_VERSION =~ ^[0-9]+\.[0-9]+$ ]] && ok "model versions pinned" || bad "model versions"
[ "${BERGAMOT_MODULES%% *}" = . ] && grep -q 'marian-dev/src/3rd_party/intgemm' <<<"$BERGAMOT_MODULES" && ok "engine tar: superproject first, then the CPU build's submodules" || bad "BERGAMOT_MODULES"

## fetch steps
grep -qF 'pin BERGAMOT_TAR "$BT" "$BERGAMOT_TAR_SHA256"' "$F" && ok "fetch: the engine tar is checked against its pin" || bad "fetch: no engine pin check"
grep -qF 'git clone' "$F" && grep -q 'bergamot-translator' "$F" && ok "fetch: engine from the pinned git commit" || bad "fetch: engine source"
grep -q '"enru:$TR_ENRU_VERSION" "ruen:$TR_RUEN_VERSION"' "$F" && grep -qF 'pinhash "TR_$name"' "$F" \
  && ok "fetch: models from translate-models.py (signed records), then each SHA-256 against its pin" || bad "fetch: model checks"
grep -qF 'sha256sum --strict --quiet -c SHA256SUMS' "$F" && ok "fetch: the staged tree is checked again" || bad "fetch: staged check"
grep -q 'mozilla-amo-root.pem' "$M" && grep -q 'remote-settings.content-signature.mozilla.org' "$M" \
  && ok "models: Mozilla's content signature, chain to the pinned AMO root, signer name checked" || bad "models: signature check"
grep -q "https://" "$M" && ! grep -q '"http://' "$M" && grep -q -- '--proto' "$M" && ok "models: HTTPS only" || bad "models: transport"
python3 -I "$M" fetch "$T/x" "enru:2.1" "enru:2.1" >/dev/null 2>&1 && bad "models: a pair twice accepted" || ok "models: a pair named twice is refused"
python3 -I "$M" fetch "$T/x" "de-fr" >/dev/null 2>&1 && bad "models: a bad pair accepted" || ok "models: a malformed pair is refused"
grep -q '^def verify_collection' "$M" && grep -q 'Content-Signature:' "$M" && grep -q -- '-purpose' "$M" \
  && ok "models: the collection's signature is verified before any record is used" || bad "models: no signature check"
python3 -I "$M" frob >/dev/null 2>&1; [ $? = 2 ] && ok "models: usage on a bad command" || bad "models: usage"

## hook order and shape
[ -x "$H" ] && head -n1 "$H" | grep -qx '#!/bin/sh' && ok "hook 0210 executable, /bin/sh" || bad "hook 0210 shape"
ls "$R/config/hooks/live" | grep -q '^0200-' && ok "hook 0210 runs after 0200 (third-party) and before 0400/0500/0600" || bad "hook order"
grep -q 'apt-get purge' "$H" && grep -q 'comm -13' "$H" && ok "hook: only the build tools it installed are purged" || bad "hook: purge"
grep -qF 'ldd' "$H" && ok "hook: the engine may link the C/C++ runtime only" || bad "hook: no ldd check"
grep -q 'chmod -R go-w\|chmod 0644\|install -m 0644' "$H" && ok "hook: read-only install" || bad "hook: modes"
grep -q 'E: the translation engine does not translate' "$H" && ok "hook: smoke test both ways" || bad "hook: no smoke test"

## hook 0210 on fake staging trees
mk(){   # a good fake tree in $1
  local S=$1/usr/src/prestium-thirdparty/translate f
  rm -rf "$1"; mkdir -p "$S/models/enru" "$S/models/ruen"
  echo tar > "$S/bergamot-translator.tar"
  for p in enru ruen; do for f in "model.$p.intgemm.alphas.bin" "lex.50.50.$p.s2t.bin" "vocab.$p.spm"; do echo "$p $f" > "$S/models/$p/$f"; done; done
  echo '// engine' > "$S/prestium-translate-engine.cpp"; echo "$BERGAMOT_COMMIT enru:2.1 ruen:2.1" > "$S/translate.version"
  ( cd "$S" && sha256sum bergamot-translator.tar models/*/* > SHA256SUMS )
}
run(){ PRESTIUM_HOOK_ROOT=$1 PRESTIUM_TRANSLATE_VERIFY_ONLY=1 sh "$H" > "$T/out" 2>&1; }
S=usr/src/prestium-thirdparty/translate
mk "$T/g"; run "$T/g" && grep -q 'match their pins' "$T/out" && ok "a good staging tree passes" || bad "good tree refused: $(cat "$T/out")"
[ ! -e "$T/g/usr/share/prestium-translate" ] && ok "verify-only installs nothing" || bad "verify-only installed files"
case_(){ local name=$1; shift; mk "$T/b"; ( cd "$T/b/$S" && eval "$*" ); run "$T/b" && bad "hook accepts: $name" || ok "hook refuses: $name ($(grep '^E:' "$T/out" | head -n1 | cut -c1-70))"; }
case_ "a changed model" 'echo x >> models/enru/model.enru.intgemm.alphas.bin'
case_ "a changed engine tar" 'echo x >> bergamot-translator.tar'
case_ "a missing model" 'rm models/ruen/vocab.ruen.spm'
case_ "an extra file" 'echo x > models/ruen/extra.bin'
case_ "an extra model folder" 'mkdir models/deen && echo x > models/deen/model.bin'
case_ "a symlink in models" 'ln -s /etc/passwd models/enru/link'
case_ "an extra SHA256SUMS line" 'echo x > x && sha256sum x >> SHA256SUMS'
case_ "a missing SHA256SUMS line" 'sed -i "/vocab.enru/d" SHA256SUMS'
case_ "no SHA256SUMS" 'rm SHA256SUMS'
case_ "a changed file with its hash updated in SHA256SUMS but not the list" 'mv models/enru/vocab.enru.spm models/enru/vocab.spm && sha256sum bergamot-translator.tar models/*/* > SHA256SUMS'
case_ "no engine front end source" 'rm prestium-translate-engine.cpp'
exit $fail
