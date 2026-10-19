DETECT_PROMPT = """You are a figure detector for academic paper pages.
Find all data charts in the page image: line charts, bar charts, heatmaps.
Do NOT include: photos, diagrams, flowcharts, pie charts, logos, tables, equations.
For each chart output one object:
{"bbox_2d": [x0, y0, x1, y1], "type": "line" | "bar" | "heatmap", "caption": "figure caption text or empty"}
bbox_2d are integers in 0-1000 normalized coordinates of the whole page, order [left, top, right, bottom].
Output ONLY a JSON array. If none found output [].
"""

CLASSIFY_PROMPT = """Classify this image cropped from a paper page.
Answer ONLY a JSON object: {"type": "line" | "bar" | "heatmap" | "other"}
Use "other" for photos, diagrams, flowcharts, pie charts, logos, equations, tables, screenshots.
"""

PARSE_PROMPT = """You are a chart data extraction expert. Extract the data from this chart image.
Output ONLY a JSON object with exactly these keys:
{"chart_type": "line"|"bar"|"heatmap",
 "title": string,
 "x_axis": {"label": string|null, "unit": string|null},
 "y_axis": {"label": string|null, "unit": string|null},
 "legend": [string],
 "series": [{"name": string, "x": [numbers or strings], "y": [numbers]}],
 "heatmap": {"x_labels": [string], "y_labels": [string], "matrix": [[number]], "colormap_hint": string|null} | null,
 "warnings": []}
Rules:
- For line and bar charts: fill "series", set "heatmap" to null. Use numbers for x when the axis is numeric, otherwise category label strings. All y must be numbers.
- For heatmaps: fill "heatmap", set "series" to [].
- Estimate values from pixel positions as accurately as possible.
- All numbers must be finite (no NaN, Infinity, or expressions).
- No markdown, no comments, JSON only.
"""
