# claude-plugins

A personal [Claude Code](https://claude.com/claude-code) plugin marketplace.
Add it once, then install any plugin listed below.

## Add the marketplace

```
/plugin marketplace add austin-tildei/claude-plugins
```

## Plugins

| Plugin                    | Description                          | Install                                |
| ------------------------- | ------------------------------------ | -------------------------------------- |
| [austin](plugins/austin/) | Austin's personal toolbox of skills. | `/plugin install austin@austin-tildei` |

**`austin` skills:** `/austin:share-transcript` — render the current session to
shareable Markdown and copy it to the clipboard.

## Adding a skill

Most additions are a new skill inside the `austin` namespace plugin:

1. Create `plugins/austin/skills/<skill-name>/SKILL.md` (plus any helper files).
2. Run `claude plugin validate .` and add it to the skills list above.

It's invoked as `/austin:<skill-name>`.

## Adding a new plugin

For a distinct, separately-installable plugin:

1. Create `plugins/<name>/` with its own `.claude-plugin/plugin.json` and any
   `skills/`, `agents/`, `hooks/`, etc.
2. Add an entry to `.claude-plugin/marketplace.json` with
   `"source": "./plugins/<name>"`.
3. Run `claude plugin validate .` and add a row to the plugins table above.
