# Output: looking at a diagram, exports

Read this only to look at a rendered diagram outside the chat or to export it.

## Verifying the output

Page mode: open the HTML from any static server. Widget mode: render once
more with `--harness` for a standalone page around the fragment (the
harness is the only way to see a widget fragment outside the chat), open
it, then pass the plain fragment to `show_widget`. A harness page of a widget rendered with
`--assets cdn` needs jsDelivr; offline, render it with `--assets inline`. The in-app browser does not open `file://` and
`preview_start` needs a launch config in the project, so serve the folder
yourself: `python3 -m http.server 8768 -d <folder> &` and open
`http://localhost:8768/<file>`; stop it by its PID, never by `pkill` on the
process name, another server may be running. Both modes paint their own white ground. Check
three things: no line crosses a card, no name is cut, the legend lists
exactly the groups used. Click a toggle and confirm the lines follow.

## Exports

`--format ascii` prints the map with routed lines, the edge list and the
crossing count; `--check` prints the same to stdout (errors and warnings
stay on stderr), so a script can compare grid variants by their output.
`--format mermaid` writes `flowchart TD` (a `subgraph` per lane for a
swimlane) with the same nodes, labels and dashed edges, and the footnotes as
`%%` comments, for a markdown document; mermaid lays it out itself, so treat
it as the secondary rendering.

