# ani-talent

Read the Ani talent database with your own account. One tool, two forms: a command
for a terminal and an MCP server for an Agent (Claude Code, Codex, Cursor and others).

You need an account. An admin of the database invites your email address and gives you
a role. With no account, the tool reads nothing.

## Install

The tool needs [uv](https://docs.astral.sh/uv/) and Python 3.9 or later.

```bash
uv tool install git+https://github.com/Aniverso/ani-talent
ani-talent login you@example.com      # A code comes to your mailbox.
ani-talent verify you@example.com 123456
ani-talent guide                      # The commands, the roles and the rules.
```

Get a new version with `uv tool upgrade ani-talent`.

## Add it to an Agent

Sign in one time in a terminal (the commands above, or with `uvx`):

```bash
uvx --from git+https://github.com/Aniverso/ani-talent ani-talent login you@example.com
uvx --from git+https://github.com/Aniverso/ani-talent ani-talent verify you@example.com 123456
```

Claude Code:

```bash
claude mcp add ani-talent -- uvx --from git+https://github.com/Aniverso/ani-talent ani-talent mcp
```

Codex, in `~/.codex/config.toml`:

```toml
[mcp_servers.ani-talent]
command = "uvx"
args = ["--from", "git+https://github.com/Aniverso/ani-talent", "ani-talent", "mcp"]
```

The Agent then has the tools `search`, `candidate`, `jobs`, `match-job` and the others.
The tool `guide` tells the Agent how to use them. For an Agent that reads skill files,
[SKILL.md](SKILL.md) has the same text.

## What to know

- Each read is recorded with your account. Your role has a limit for each day.
- The session is a file in `~/.config/ani-talent/` on your computer. Do not give it to
  another person or Agent: each one has its own account.
- The publishable key in the source is not a secret. It identifies the project; the
  database gives data only to a signed-in account with a role.
- The tool has no export and no write command.

## License

PolyForm Noncommercial 1.0.0. See [LICENSE](LICENSE).
