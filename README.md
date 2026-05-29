# claude-plugins

A personal [Claude Code](https://claude.com/claude-code) plugin marketplace.
Add it once, then install any plugin listed below.

## Add the marketplace

```
/plugin marketplace add austin-tildei/claude-plugins
```

## Plugins

| Plugin                                        | Description                                                                             | Install                                          |
| --------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------ |
| [share-transcript](plugins/share-transcript/) | Render the current session into a shareable Markdown file and copy it to the clipboard. | `/plugin install share-transcript@austin-tildei` |

## Adding a new plugin

1. Create `plugins/<name>/` with its own `.claude-plugin/plugin.json` and any
   `skills/`, `agents/`, `hooks/`, etc.
2. Add an entry to `.claude-plugin/marketplace.json` with
   `"source": "./plugins/<name>"`.
3. Run `claude plugin validate .` and add a row to the table above.
