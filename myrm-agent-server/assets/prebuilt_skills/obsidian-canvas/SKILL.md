---
name: obsidian-canvas
description: >-
  Create and edit JSON Canvas files (.canvas) in Obsidian vaults — mind maps,
  flowcharts, project boards, and visual knowledge graphs following the
  JSON Canvas Spec 1.0.
version: 1.0.0
category: productivity
tags:
  - obsidian
  - canvas
  - mind-map
  - flowchart
  - visual-thinking
allowed-tools: file_write_tool file_read_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Locate — find the Obsidian vault and target folder for the .canvas file"
    - "Phase 2: Design — plan nodes (text/file/link/group) and edges for the canvas"
    - "Phase 3: Build — generate valid JSON with unique 16-char hex IDs and proper layout"
    - "Phase 4: Validate — verify all IDs are unique and all edge references resolve"
  potential_traps:
    - description: "Using literal \\n instead of JSON newline in text node content"
      mitigation: "Always use \\n for line breaks in JSON strings, never literal backslash-n"
      severity: high
    - description: "Dangling edge references — fromNode/toNode pointing to non-existent node IDs"
      mitigation: "After building edges, verify every fromNode/toNode exists in the nodes array"
      severity: high
    - description: "Duplicate IDs across nodes and edges"
      mitigation: "Generate fresh 16-char hex IDs; check uniqueness across both nodes AND edges arrays"
      severity: high
    - description: "Using color names instead of preset numbers"
      mitigation: "Color presets are '1' through '6', not 'red'/'blue'; hex like '#FF0000' also works"
      severity: medium
    - description: "Overlapping nodes making the canvas unreadable"
      mitigation: "Space nodes 50-100px apart; use grid alignment (multiples of 20)"
      severity: medium
  verification_steps:
    - step_id: vault_found
      description: "Obsidian vault directory located and accessible"
      validation_method: "Directory contains .obsidian/ subfolder"
      is_required: true
    - step_id: json_valid
      description: "Generated .canvas file is valid JSON"
      validation_method: "Parse the JSON without errors"
      is_required: true
    - step_id: ids_unique
      description: "All node and edge IDs are unique"
      validation_method: "Collect all IDs; set size equals list size"
      is_required: true
    - step_id: edges_resolve
      description: "All edge fromNode/toNode reference existing node IDs"
      validation_method: "Every fromNode/toNode value exists in the nodes ID set"
      is_required: true
  success_criteria: "A .canvas file that opens correctly in Obsidian with all nodes visible and edges connected"
  estimated_duration_seconds: 300
---

# JSON Canvas

Create and edit `.canvas` files following the [JSON Canvas Spec 1.0](https://jsoncanvas.org/spec/1.0/).

## File Structure

```json
{
  "nodes": [],
  "edges": []
}
```

Both arrays are optional but should always be present for clarity.

## ID Generation

Every node and edge needs a unique 16-character lowercase hexadecimal string:

```
"6f0ad84f44ce9c17"
"a3b2c1d0e9f8a7b6"
```

IDs must be unique across **both** the nodes and edges arrays.

## Nodes

Array order determines z-index: first = bottom layer, last = top layer.

### Required Attributes (All Nodes)

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | string | Unique 16-char hex |
| `type` | string | `text`, `file`, `link`, or `group` |
| `x` | integer | X position (pixels) |
| `y` | integer | Y position (pixels) |
| `width` | integer | Width (pixels) |
| `height` | integer | Height (pixels) |

Optional: `color` — preset `"1"`–`"6"` or hex (e.g., `"#FF0000"`).

| Preset | Color |
|--------|-------|
| `"1"` | Red |
| `"2"` | Orange |
| `"3"` | Yellow |
| `"4"` | Green |
| `"5"` | Cyan |
| `"6"` | Purple |

### Text Node

Requires `text` (Markdown content). Use `\n` for line breaks in the JSON string.

```json
{
  "id": "6f0ad84f44ce9c17",
  "type": "text",
  "x": 0, "y": 0,
  "width": 400, "height": 200,
  "text": "# Topic\n\nKey insight about **this concept**."
}
```

### File Node

Requires `file` (vault-relative path). Optional `subpath` for heading/block links.

```json
{
  "id": "a1b2c3d4e5f67890",
  "type": "file",
  "x": 500, "y": 0,
  "width": 400, "height": 300,
  "file": "Research/Paper.md"
}
```

### Link Node

Requires `url` (external URL).

```json
{
  "id": "c3d4e5f678901234",
  "type": "link",
  "x": 1000, "y": 0,
  "width": 400, "height": 200,
  "url": "https://obsidian.md"
}
```

### Group Node

Visual container. Optional `label`, `background` (image path), `backgroundStyle` (`cover`/`ratio`/`repeat`). Position child nodes inside the group bounds.

```json
{
  "id": "d4e5f6789012345a",
  "type": "group",
  "x": -50, "y": -50,
  "width": 1000, "height": 600,
  "label": "Project Overview",
  "color": "4"
}
```

## Edges

Connect nodes via `fromNode` and `toNode` IDs.

| Attribute | Required | Default | Values |
|-----------|----------|---------|--------|
| `id` | yes | — | Unique hex string |
| `fromNode` | yes | — | Source node ID |
| `toNode` | yes | — | Target node ID |
| `fromSide` | no | — | `top`, `right`, `bottom`, `left` |
| `toSide` | no | — | `top`, `right`, `bottom`, `left` |
| `fromEnd` | no | `none` | `none`, `arrow` |
| `toEnd` | no | `arrow` | `none`, `arrow` |
| `color` | no | — | Preset or hex |
| `label` | no | — | Text on the edge |

```json
{
  "id": "0123456789abcdef",
  "fromNode": "6f0ad84f44ce9c17",
  "fromSide": "right",
  "toNode": "a1b2c3d4e5f67890",
  "toSide": "left",
  "toEnd": "arrow",
  "label": "leads to"
}
```

## Layout Guidelines

- Coordinates can be negative (infinite canvas)
- `x` increases right, `y` increases down; position is the top-left corner
- Space nodes 50–100px apart
- Leave 20–50px padding inside groups
- Align to multiples of 20 for clean layouts

| Node Type | Width | Height |
|-----------|-------|--------|
| Small text | 200–300 | 80–150 |
| Medium text | 300–450 | 150–300 |
| Large text | 400–600 | 300–500 |
| File preview | 300–500 | 200–400 |
| Link preview | 250–400 | 100–200 |

## Workflows

### Create a New Canvas

1. Create a `.canvas` file with `{"nodes": [], "edges": []}`
2. Generate unique 16-char hex IDs for each node
3. Add nodes with all required fields
4. Add edges referencing valid node IDs
5. Validate: parse JSON, check ID uniqueness, verify edge references

### Edit an Existing Canvas

1. Read and parse the `.canvas` file
2. Locate the target node or edge by ID
3. Modify attributes
4. Write updated JSON back
5. Re-validate all ID uniqueness and edge integrity

### Add Nodes to an Existing Canvas

1. Read and parse the existing file
2. Generate IDs that don't collide with existing ones
3. Choose positions that avoid overlap (check existing node bounds)
4. Append to the nodes array; add edges if needed
5. Validate

## Validation Checklist

After creating or editing, verify:

1. All `id` values are unique across both nodes and edges
2. Every `fromNode`/`toNode` references an existing node ID
3. Required fields present per node type (`text` for text, `file` for file, `url` for link)
4. `type` is one of: `text`, `file`, `link`, `group`
5. `fromSide`/`toSide` are one of: `top`, `right`, `bottom`, `left`
6. `fromEnd`/`toEnd` are one of: `none`, `arrow`
7. Color values are `"1"`–`"6"` or valid hex
8. JSON is valid and parseable
