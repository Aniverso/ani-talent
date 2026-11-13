# ani-talent

Read the Ani talent database with your own account. One tool, two forms: a command
for a terminal and an MCP server for an Agent (Claude Code, Codex, Cursor and others).

You need an account. An admin of the database invites your email address and gives you
a role. With no account, the tool reads nothing.

## Install

One command installs the tool, signs you in and adds the MCP server to Claude Code and
Codex (when you have them):

```bash
curl -fsSL https://raw.githubusercontent.com/Aniverso/ani-talent/main/install.sh | sh
```

The script installs [uv](https://docs.astral.sh/uv/) if you do not have it. It asks for
your email address and the code that comes to your mailbox. Read
[install.sh](install.sh) for the settings that skip a step.

Get a new version with `uv tool upgrade ani-talent`. Run `ani-talent guide` for the
commands, the roles and the rules.

## Install by hand

The tool needs [uv](https://docs.astral.sh/uv/) and Python 3.9 or later.

```bash
uv tool install ani-talent
ani-talent login you@example.com      # A code comes to your mailbox.
ani-talent verify you@example.com 123456
```

Claude Code:

```bash
claude mcp add --scope user ani-talent -- uvx ani-talent mcp
```

Codex, in `~/.codex/config.toml`:

```toml
[mcp_servers.ani-talent]
command = "uvx"
args = ["ani-talent", "mcp"]
```

Another Agent: add an MCP server with the command `uvx ani-talent mcp`.

The Agent then has the tools `search`, `candidate`, `jobs`, `match-job` and the others.
The tool `guide` tells the Agent how to use them. For an Agent that reads skill files,
[SKILL.md](SKILL.md) has the same text.

## What to know

- Each read is recorded with your account. Your role has a limit for each day.
- The session is a file in `~/.config/ani-talent/` on your computer. Do not give it to
  another person or Agent: each one has its own account.
- The publishable key in the source is not a secret. It identifies the project; the
  database gives data only to a signed-in account with a role.
- The tool has no export. It does not write candidates, contacts or jobs. The company
  commands write company records; they need the role `company_agent`.

## Release

Set a new `VERSION` in `ani_talent/__init__.py` and merge it to `main`. The workflow
`.github/workflows/release.yml` then builds the package, publishes it to PyPI through
Trusted Publishing, and makes the tag `v<VERSION>` and a GitHub release. A merge that
does not change `VERSION` publishes nothing. PyPI accepts each version one time only.

## License

PolyForm Noncommercial 1.0.0. See [LICENSE](LICENSE).
