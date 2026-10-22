DETECT_PROMPT = """You are a figure detector for academic paper pages.
Find all scientific data visualizations in the input image, even when a chart is small or surrounded by dense text: line charts, bar charts, combo charts (such as bars plus a line), heatmaps, scatter plots, and 3D plots showing data points, spatial distributions, or trajectories.
Do NOT include: photos, diagrams, flowcharts, pie charts, logos, tables, equations.
For a 3D plot or scatter plot, use type "line" so it can be selected and inspected with the supported chart tools.
For each chart output one object:
{"bbox_2d": [x0, y0, x1, y1], "type": "line" | "bar" | "combo" | "heatmap", "caption": "figure caption text or empty"}
bbox_2d are integers in 0-1000 normalized coordinates of the input image, order [left, top, right, bottom]. Include the full plotting area, not its surrounding paragraph or caption.
Output ONLY a JSON array. If none found output [].
"""

CLASSIFY_PROMPT = """Classify this image cropped from a paper page.
Answer ONLY a JSON object: {"type": "line" | "bar" | "combo" | "heatmap" | "other"}
Treat scatter plots and 3D scientific plots showing data points, spatial distributions, or trajectories as "line".
Use "other" for photos, diagrams, flowcharts, pie charts, logos, equations, tables, screenshots.
"""

PARSE_PROMPT = """You are a chart data extraction expert. Extract the data from this chart image.
Output ONLY a JSON object with exactly these keys:
{"chart_type": "line"|"bar"|"combo"|"heatmap",
 "title": string,
 "x_axis": {"label": string|null, "unit": string|null},
 "y_axis": {"label": string|null, "unit": string|null},
 "y_axis_right": {"label": string|null, "unit": string|null} | null,
 "legend": [string],
 "series": [{"name": string, "x": [numbers or strings], "y": [numbers], "kind": "line"|"bar", "axis": "left"|"right"}],
 "heatmap": {"x_labels": [string], "y_labels": [string], "matrix": [[number]], "colormap_hint": string|null} | null,
 "warnings": []}
Rules:
- For line and bar charts: fill "series", set "heatmap" and "y_axis_right" to null. Use numbers for x when the axis is numeric, otherwise category label strings. All y must be numbers.
- For combo charts: keep each plotted series separate. Include "kind" (line or bar) and "axis" (left or right) on every series. Put the secondary vertical axis label/unit in "y_axis_right". Do not combine the two axes or merge values from different series.
- For charts with two vertical axes, use the tick labels on the corresponding side for each series and preserve the left/right mapping.
- A series is one metric/legend entry; x values are the categories shared across series. Do not create one series per x category.
- Select "combo" whenever the plot mixes bars and connected lines/markers or has two vertical axes. Do not label it "line" merely because one series is a line.
- For heatmaps: fill "heatmap", set "series" to [].
- Estimate values from plotted marks and axis ticks; do not substitute values from nearby body text or tables.
- If exact values cannot be read reliably, describe the uncertainty in "warnings" rather than implying precision.
- All numbers must be finite (no NaN, Infinity, or expressions).
- No markdown, no comments, JSON only.
"""
