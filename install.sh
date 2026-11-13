#!/bin/sh
# Installs the ani-talent command, signs you in and adds the MCP server to your Agents.
#
#   curl -fsSL https://raw.githubusercontent.com/Aniverso/ani-talent/main/install.sh | sh
#
# Settings (optional):
#   ANI_TALENT_EMAIL=you@example.com   Do not ask for the email address.
#   ANI_TALENT_NO_LOGIN=1              Do not sign in.
#   ANI_TALENT_NO_AGENT=1              Do not add the MCP server to Claude Code or Codex.
#   ANI_TALENT_SOURCE=<spec>           What uv installs. Default: ani-talent (from PyPI).
set -eu

say() { printf '%s\n' "$*"; }
fail() { printf 'ani-talent install: %s\n' "$*" >&2; exit 1; }

# Read one answer from the terminal. With `curl | sh`, stdin is the script, not the person.
ask() {
  printf '%s' "$1" >/dev/tty
  IFS= read -r answer </dev/tty || answer=''
  printf '%s' "$answer"
}

has_tty() { (: </dev/tty) 2>/dev/null; }

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi
  say 'Installing uv (https://docs.astral.sh/uv/) ...'
  command -v curl >/dev/null 2>&1 || fail 'curl is necessary to install uv.'
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  export PATH
  command -v uv >/dev/null 2>&1 || fail 'uv is not on PATH. Open a new terminal and run this again.'
}

install_tool() {
  source_spec=${ANI_TALENT_SOURCE:-ani-talent}
  say "Installing ani-talent from $source_spec ..."
  uv tool install --force "$source_spec" </dev/null
  bin_dir=$(uv tool dir --bin)
  PATH="$bin_dir:$PATH"
  export PATH
  tool="$bin_dir/ani-talent"
  [ -x "$tool" ] || fail "The command is not at $tool."
  say "Installed: $("$tool" version | tr -d '\n ')"
}

sign_in() {
  if [ -n "${ANI_TALENT_NO_LOGIN:-}" ]; then
    return
  fi
  if "$tool" status 2>/dev/null | grep -q '"signed_in": true'; then
    say 'You are already signed in.'
    return
  fi
  if ! has_tty; then
    say 'No terminal to ask for the email address. Sign in later:'
    say '  ani-talent login you@example.com'
    say '  ani-talent verify you@example.com 123456'
    return
  fi
  email=${ANI_TALENT_EMAIL:-}
  if [ -z "$email" ]; then
    email=$(ask 'Email address of your Ani talent account: ')
  fi
  [ -n "$email" ] || fail 'No email address.'
  "$tool" login "$email" >/dev/null
  say "A code went to $email."
  code=$(ask 'Code from the email: ')
  "$tool" verify "$email" "$code" >/dev/null
  say "Signed in as $email."
}

add_to_agents() {
  if [ -n "${ANI_TALENT_NO_AGENT:-}" ]; then
    return
  fi
  added=''
  if command -v claude >/dev/null 2>&1; then
    if claude mcp get ani-talent </dev/null >/dev/null 2>&1; then
      say 'Claude Code already has the MCP server ani-talent.'
    else
      claude mcp add --scope user ani-talent -- "$tool" mcp </dev/null >/dev/null
      say 'Added the MCP server ani-talent to Claude Code.'
    fi
    added=1
  fi
  if command -v codex >/dev/null 2>&1; then
    if codex mcp get ani-talent </dev/null >/dev/null 2>&1; then
      say 'Codex already has the MCP server ani-talent.'
    else
      codex mcp add ani-talent -- "$tool" mcp </dev/null >/dev/null
      say 'Added the MCP server ani-talent to Codex.'
    fi
    added=1
  fi
  if [ -z "$added" ]; then
    say "For another Agent, add an MCP server with the command: $tool mcp"
  fi
}

main() {
  install_uv
  install_tool
  sign_in
  add_to_agents
  say ''
  say 'Done. Run `ani-talent guide` for the commands. Get a new version with `uv tool upgrade ani-talent`.'
}

# The whole file is read before anything runs, so a broken download does nothing.
main "$@"
