# mcp-packaging Specification

## Purpose

Defines how the MCP server ships and how a host launches it. The server is optional, so a CLI-only install never pulls in an MCP SDK.

## Requirements

### Requirement: MCP support is an optional extra
The MCP server SHALL use the official `mcp` Python SDK, which is asyncio-based, and SHALL be packaged as the optional extra `corvee[mcp]`, not as a hard dependency of the base install.

#### Scenario: Base install
- **WHEN** corvee is installed without the `mcp` extra
- **THEN** every `task`, `fact`, and top-level command works without the `mcp` package installed

### Requirement: `mcp serve` is a subcommand
`corvee mcp serve` SHALL be a subcommand of the existing `corvee` console script and SHALL NOT be a second console-script entry point, so one installed binary serves both shell and MCP hosts.

#### Scenario: One binary
- **WHEN** a host spawns `corvee mcp serve`
- **THEN** it launches the same installed `corvee` the shell uses

### Requirement: `mcp serve` is always visible
`corvee mcp serve` SHALL be registered whether or not the `mcp` extra is installed, appearing in `--help` and in the scripts from `corvee completion`. It SHALL follow the same leaf-command rules as every other command, including a `--help` epilog with at least three runnable examples and a one-character alias on every option.

#### Scenario: Discoverable without the extra
- **WHEN** `corvee --help` runs on an install without the extra
- **THEN** `mcp` is listed

### Requirement: Running without the extra fails cleanly
Running `corvee mcp serve` without the extra installed SHALL fail with exit 6 and a message naming the install command (`pip install 'corvee[mcp]'` or equivalent), never a raw `ImportError` traceback.

#### Scenario: Missing SDK
- **WHEN** `corvee mcp serve` runs where the `mcp` package is not importable
- **THEN** the exit code is 6 and the message names `corvee[mcp]`
