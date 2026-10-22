# Design

Direction: Taste-skill app style **data-terminal** (seed 668252672, `.taste-skill/app/direction.json`) for dark, the same rules on the **achromatic-ledger** ground for light. Operate mode under Impeccable's craft floor. Tokens live in `src/app.css`, and metric colour logic lives in `src/lib/metrics.js`.

## The move

Every selection is the same 1px accent line, placed on the nearest edge: the active metric tab's underline, the active view on the rail's edge, and a selected list row's left edge. A selected zone on the map gets a 2px accent outline, because 1px vanishes on a map. Nothing else in the chrome carries colour.

## Colour

- Colour goes on data only: the zone choropleth and the swatch beside each list row, which is the exact mark on the map (`colorCss`).
- The travel-time ramp is one hue (`--ramp-1…6`), with more remote zones in more ink: darker on light, brighter on dark. Missing data is `--ramp-0`.
- Mean IPC blends the official IPC colours between phases, on the map and in the swatches alike.
- The selected country's zones are fully opaque. Neighbouring countries drop to 22% as context.
- Dark: ground `#171719`, cards darker (`#131217`), raised `#212023`. Two greys that read apart: `#9a9ca2` and `#8a8c92`.
- Light: ground `#f9fafb`, white cards, ink `#111214`, grey `#5d6066`, accent `#1d5fbf`.

## Type

Public Sans Variable, self-hosted (`@fontsource-variable`), with tabular figures everywhere. Sizes: title 26 (22 on the phone), section 16, finding 14, body 13, small 12, legend and meta 11. Weights 400, 500 and 600, in sentence case, with no tracked capitals and no monospace.

## Shell

- **Desktop:** an icon rail (56px) with the IPC-bar mark, Zones and Coverage, and the theme at the bottom.
- **Phone:** the rail becomes a labelled bottom bar.
- **Title row:** the noun h1 ("Kenya livelihood zones"), the computed finding under it, and the country switcher on the right.

## Zones view

- **Map and rail:** the map card sits beside a 360px rail. The rail holds the selected zone's or market's detail, then the zones ranked worst first by the active metric.
- **Map overlays:** the legend sits bottom-left with the metric's caveat. On a phone it moves under the map.
- **Layers:** secondary layers (WFP markets, FAO series, admin and district lines, Guatemala district IPC, the base map) live in a Layers menu, not on the screen.

## Coverage view

One table whose last column is the timeline: one cell per month, ink opacity rising with the log row count, and gaps in the rule colour. The finding names what is missing or thin.

## States

- **Loading:** skeleton bars at the size of the finding and the list.
- **Errors:** a load error names the script to run.
- **Base map unavailable:** the map falls back to boundaries only, with a note.
- **Keyboard:** Escape closes the Layers menu, then clears the selection.
- **Reduced motion:** transitions are removed.

## Checked with

`node ~/.claude/skills/taste-skill/scripts/lint.mjs --app web/src` and `inspect.mjs --app http://localhost:5173/`. The result is 0 FAIL. The remaining warnings are the colour share, which is the choropleth itself (data, not chrome), and missing-value dashes, which the app-screen rules require.
