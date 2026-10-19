"""Gradio 前端：论文模式（页面预览+高亮+点击联动）与单图模式。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 支持脚本直启

import gradio as gr
from PIL import Image, ImageDraw

from chart_sdk.cache.store import PaperStore
from chart_sdk.config import Config
from chart_sdk.inference.client import VLClient
from chart_sdk.pipeline.paper import PaperPipeline
from chart_sdk.pipeline.single import run_single

CONFIG = Config.from_env()
_CLIENT: VLClient | None = None

BBOX_PAD = 25  # 点击命中容差（px）


def get_client() -> VLClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = VLClient(CONFIG)
    return _CLIENT


def draw_page_annotations(page_png: Path, figures: list) -> Image.Image:
    """页面上画高亮框与编号（设计文档 6.3）。"""
    im = Image.open(page_png).convert("RGB")
    draw = ImageDraw.Draw(im)
    for i, fig in enumerate(figures, 1):
        x0, y0, x1, y1 = fig["bbox_px"]
        draw.rectangle([x0, y0, x1, y1], outline=(230, 30, 30), width=4)
        draw.rectangle([x0, y0 - 26, x0 + 56, y0], fill=(230, 30, 30))
        draw.text((x0 + 8, y0 - 22), f"[{i}]", fill=(255, 255, 255))
    return im


def hit_test(figures: list, x: float, y: float) -> str | None:
    """命中最小包含 bbox（含容差）；无命中返回 None。"""
    hits = []
    for fig in figures:
        x0, y0, x1, y1 = fig["bbox_px"]
        if (x0 - BBOX_PAD) <= x <= (x1 + BBOX_PAD) and (y0 - BBOX_PAD) <= y <= (y1 + BBOX_PAD):
            hits.append(((x1 - x0) * (y1 - y0), fig["id"]))
    return min(hits)[1] if hits else None


def chart_to_dataframe(chart: dict):
    """chart JSON → (headers, rows) 供 gr.Dataframe 展示。"""
    if chart["chart_type"] == "heatmap":
        hm = chart["heatmap"]
        headers = [""] + (hm["x_labels"] or [f"c{i+1}" for i in range(len(hm["matrix"][0]))])
        rows = []
        for j, row in enumerate(hm["matrix"]):
            ylab = hm["y_labels"][j] if j < len(hm["y_labels"]) else f"r{j+1}"
            rows.append([ylab] + list(row))
        return headers, rows
    series = chart["series"]
    n = max(len(s["x"]) for s in series) if series else 0
    headers = ["x"] + [s["name"] for s in series]
    rows = []
    for i in range(n):
        row = [series[0]["x"][i] if i < len(series[0]["x"]) else ""]
        for s in series:
            row.append(s["y"][i] if i < len(s["y"]) else "")
        rows.append(row)
    return headers, rows


def _figure_outputs(root: Path, fig: dict):
    """由 figure 条目产出右栏四标签内容。"""
    crop = root / fig["crop_path"] if fig.get("crop_path") else None
    render = root / fig["render_path"] if fig.get("render_path") else None
    chart = None
    if fig.get("chart_json_path"):
        chart = json.loads((root / fig["chart_json_path"]).read_text(encoding="utf-8"))
    code = (root / fig["code_path"]).read_text(encoding="utf-8") if fig.get("code_path") else ""
    headers, rows = ("无数据", []) if chart is None else chart_to_dataframe(chart)
    status = f'{fig["id"]} | 解析: {fig.get("parse_status")} | 渲染: {fig.get("render_status")}'
    if fig.get("error"):
        status += f' | 错误: {fig["error"][:200]}'
    return (
        crop if crop and crop.exists() else None,
        gr.update(value=rows, headers=headers) if rows else gr.update(value=[], headers=["无数据"]),
        render if render and render.exists() else None,
        code,
        status,
    )


def upload_paper(pdf_file, progress=gr.Progress()):
    """论文模式：上传 → 阻塞跑流水线（实时进度）→ 返回页面导航与首屏。"""
    if not pdf_file:
        raise gr.Error("请先上传 PDF")
    try:
        get_client().health()
    except Exception:
        raise gr.Error(f"Ollama 不可达（{CONFIG.base_url}）。请运行: ollama pull {CONFIG.model} 并确认服务已启动")
    pdf_path = Path(pdf_file)

    def cb(stage, done, total, msg):
        frac = done / total if total else None
        progress(frac, desc=msg)

    session = PaperPipeline(CONFIG, get_client()).run(pdf_path, progress=cb)
    store = PaperStore(CONFIG.cache_dir, pdf_path.read_bytes(), pdf_path.name)

    pages = [p["page"] for p in session["pages"]]
    first = pages[0] if pages else 1
    img, radio, count = page_panel(store, session, first)
    return (
        gr.update(choices=[f"第 {p} 页" for p in pages], value=f"第 {first} 页", visible=True),
        img, radio, count, session,
    )


def page_panel(store: PaperStore, session: dict, page_no: int):
    """某页的：高亮大图 + 图表单选列表 + 数量提示。"""
    figs = [f for f in session["figures"] if f["page"] == page_no]
    png = store.page_png(page_no)
    img = draw_page_annotations(png, figs) if figs else Image.open(png)
    choices = [f'[{i}] {f["type"]} ({f["id"]})' for i, f in enumerate(figs, 1)]
    count = f"本页检测到 {len(figs)} 个图表" if figs else "本页未检测到目标类型图表"
    return img, gr.update(choices=choices, value=choices[0] if choices else None), count


def select_page(page_label, session):
    store = _store_of(session)
    page_no = int(str(page_label).replace("第", "").replace("页", "").strip())
    img, radio, count = page_panel(store, session, page_no)
    return img, radio, count, None, None, None, "", ""


def on_image_select(evt: gr.SelectData, session, page_label):
    """页面图点击 → 命中 bbox → 联动右栏（设计文档 6.3）。"""
    if not session:
        return None, None, None, None, "", ""
    store = _store_of(session)
    page_no = int(str(page_label).replace("第", "").replace("页", "").strip())
    figs = [f for f in session["figures"] if f["page"] == page_no]
    fig_id = hit_test(figs, evt.index[0], evt.index[1])
    if fig_id is None:
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
    fig = next(f for f in figs if f["id"] == fig_id)
    label = f'[{figs.index(fig) + 1}] {fig["type"]} ({fig["id"]})'
    outputs = _figure_outputs(store.root, fig)
    return gr.update(value=label), *outputs


def on_radio_change(label, session):
    if not label or not session:
        return None, None, None, "", ""
    store = _store_of(session)
    fig_id = label.rsplit("(", 1)[-1].rstrip(")")
    fig = next((f for f in session["figures"] if f["id"] == fig_id), None)
    if fig is None:
        return None, None, None, "", ""
    return _figure_outputs(store.root, fig)


def _store_of(session: dict) -> PaperStore:
    pdf_bytes = (Path(CONFIG.cache_dir) / "papers" / session["pdf_hash"] / "source.pdf").read_bytes()
    return PaperStore(CONFIG.cache_dir, pdf_bytes, session["file_name"])


def run_single_ui(image, progress=gr.Progress()):
    if image is None:
        raise gr.Error("请先上传图片")
    try:
        get_client().health()
    except Exception:
        raise gr.Error(f"Ollama 不可达（{CONFIG.base_url}）。请运行: ollama pull {CONFIG.model}")
    path = Path(image) if isinstance(image, str) else Path(image.name) if hasattr(image, "name") else None
    if path is None or not path.exists():
        raise gr.Error("图片读取失败")
    result = run_single(CONFIG, get_client(), path)
    if result["status"] == "error":
        raise gr.Error(f"解析失败: {result.get('error')}")
    root = Path(CONFIG.cache_dir) / "singles" / result["image_hash"]
    chart = result.get("chart")
    headers, rows = chart_to_dataframe(chart) if chart else ("无数据", [])
    code = (root / result["code_path"]).read_text(encoding="utf-8") if result.get("code_path") else ""
    render = root / result["render_path"] if result.get("render_path") and (root / result["render_path"]).exists() else None
    status = f"状态: {result['status']}" + (f" | {result.get('error', '')[:200]}" if result.get("error") else "")
    return root / "input.png", gr.update(value=rows, headers=headers), render, code, status


def build_ui():
    with gr.Blocks(title="论文图表复刻") as demo:
        gr.Markdown("# 论文图表复刻系统\n上传论文 PDF 或单张图表图片，本地解析并复刻 Matplotlib 代码。")
        with gr.Tabs():
            with gr.Tab("论文模式"):
                with gr.Row():
                    with gr.Column(scale=1):
                        pdf_in = gr.File(label="上传论文 PDF", file_types=[".pdf"])
                        upload_btn = gr.Button("解析论文", variant="primary")
                        page_dd = gr.Dropdown(label="页码", visible=False)
                        page_img = gr.Image(label="页面预览（红色框为图表，可点击）", interactive=False)
                        fig_radio = gr.Radio(label="图表列表（点击页面或选择）", visible=False)
                        fig_count = gr.Markdown("")
                    with gr.Column(scale=1):
                        with gr.Tabs():
                            with gr.Tab("原图"):
                                f_crop = gr.Image(label="图表原图", interactive=False)
                            with gr.Tab("数据表"):
                                f_table = gr.Dataframe(interactive=False)
                            with gr.Tab("复刻图"):
                                f_render = gr.Image(label="Matplotlib 复刻图", interactive=False)
                            with gr.Tab("代码"):
                                f_code = gr.Code(label="Matplotlib 代码（可复制）", language="python", interactive=False)
                        f_status = gr.Markdown("")
                session_state = gr.State()
                upload_btn.click(upload_paper, inputs=[pdf_in], outputs=[page_dd, page_img, fig_radio, fig_count, session_state])
                page_dd.select(select_page, inputs=[page_dd, session_state], outputs=[page_img, fig_radio, fig_count, f_crop, f_table, f_render, f_code, f_status])
                page_img.select(on_image_select, inputs=[session_state, page_dd], outputs=[fig_radio, f_crop, f_table, f_render, f_code, f_status])
                fig_radio.change(on_radio_change, inputs=[fig_radio, session_state], outputs=[f_crop, f_table, f_render, f_code, f_status])
            with gr.Tab("单图模式"):
                with gr.Row():
                    with gr.Column():
                        img_in = gr.Image(label="上传图表图片", type="filepath")
                        run_btn = gr.Button("解析图片", variant="primary")
                    with gr.Column():
                        with gr.Tabs():
                            with gr.Tab("原图"):
                                s_crop = gr.Image(interactive=False)
                            with gr.Tab("数据表"):
                                s_table = gr.Dataframe(interactive=False)
                            with gr.Tab("复刻图"):
                                s_render = gr.Image(interactive=False)
                            with gr.Tab("代码"):
                                s_code = gr.Code(label="Matplotlib 代码（可复制）", language="python", interactive=False)
                        s_status = gr.Markdown("")
                run_btn.click(run_single_ui, inputs=[img_in], outputs=[s_crop, s_table, s_render, s_code, s_status])
    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="127.0.0.1", server_port=7860)
