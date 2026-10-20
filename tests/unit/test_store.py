import json

from chart_sdk.cache.store import PaperStore, SingleStore, content_hash


def test_content_hash_stable():
    assert content_hash(b"abc") == content_hash(b"abc")
    assert content_hash(b"abc") != content_hash(b"abd")


def test_paper_store_creates_and_resumes(tmp_path):
    s1 = PaperStore(tmp_path, b"pdf-bytes", "a.pdf")
    assert s1.session["stage"] == "detecting"
    assert s1.session["file_name"] == "a.pdf"
    s1.session["stage"] = "done"
    s1.save()
    s2 = PaperStore(tmp_path, b"pdf-bytes", "a.pdf")
    assert s2.session["stage"] == "done"  # 断点续跑：读取已保存会话
    assert s2.root == s1.root


def test_paper_store_dirs(tmp_path):
    s = PaperStore(tmp_path, b"x", "a.pdf")
    assert (s.root / "pages").exists()
    assert (s.root / "figures").exists()
    assert (s.root / "source.pdf").exists()
    fd = s.figure_dir("p1-f1")
    assert fd.name == "p1-f1"


def test_single_store(tmp_path):
    s1 = SingleStore(tmp_path, b"img", "a.png")
    s1.record["status"] = "done"
    s1.save()
    s2 = SingleStore(tmp_path, b"img", "a.png")
    assert s2.record["status"] == "done"


def test_session_json_schema_fields(tmp_path):
    s = PaperStore(tmp_path, b"y", "b.pdf")
    for key in ("pdf_hash", "file_name", "n_pages", "dpi", "stage", "pages", "figures"):
        assert key in s.session


def test_paper_store_open(tmp_path):
    from chart_sdk.cache.store import PaperStore
    store = PaperStore(tmp_path / "cache", b"fake-pdf-bytes", "a.pdf")
    store.save()
    again = PaperStore.open(tmp_path / "cache", store.pdf_hash)
    assert again.pdf_hash == store.pdf_hash
    assert again.root == store.root
    assert again.session["file_name"] == "a.pdf"


def test_paper_store_open_missing(tmp_path):
    import pytest
    from chart_sdk.cache.store import PaperStore
    with pytest.raises(KeyError):
        PaperStore.open(tmp_path / "cache", "0" * 64)
