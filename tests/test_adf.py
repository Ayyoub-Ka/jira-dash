from jira_dash.adf import adf_to_text, text_to_adf


def test_roundtrip_paragraphs():
    doc = text_to_adf("a\nb\n\nc")
    assert doc["type"] == "doc"
    assert len(doc["content"]) == 2
    assert adf_to_text(doc).strip() == "a\nb\n\nc"


def test_marks_lists_and_media():
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "x", "marks": [{"type": "strong"}]}]},
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "item"}]}],
                    }
                ],
            },
            {"type": "mediaSingle", "content": [{"type": "media", "attrs": {"type": "file", "alt": "shot.png"}}]},
            {"type": "mention", "attrs": {"text": "@Ann"}},
        ],
    }
    out = adf_to_text(doc)
    assert "**x**" in out
    assert "- item" in out
    assert "[image: shot.png]" in out
    assert "@Ann" in out
