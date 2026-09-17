# chelout-plugins

Personal Claude Code plugin marketplace.

## Plugins

| Plugin | Skills | What it does |
|---|---|---|
| [`drawing-diagrams`](plugins/drawing-diagrams) | `drawing-diagrams` | ERD, flowchart, swimlane, state machine, timeline and blocks diagrams rendered from a small JSON model |

## Install

```bash
claude plugin marketplace add chelout/plugins-marketplace
claude plugin install drawing-diagrams@chelout-plugins
```

From a local checkout:

```bash
claude plugin marketplace add /path/to/plugins-marketplace
claude plugin install drawing-diagrams@chelout-plugins
```

## Layout

```
.claude-plugin/marketplace.json      marketplace catalog
plugins/<plugin>/.claude-plugin/plugin.json
plugins/<plugin>/skills/<skill>/SKILL.md
```

Plugins carry no `version`: Claude Code uses the git commit SHA, so every pushed commit is an update.

Check before committing (the only expected warning is the missing `version`, which is intentional):

```bash
claude plugin validate .
claude plugin validate plugins/drawing-diagrams
```
