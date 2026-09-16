from jira_dash.adf import adf_to_text, mention_tokens, text_to_adf


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


def test_mentions_become_nodes_and_unknown_stay_text():
    text = 'hi @ann, see @"Bob Cee" and @ghost'
    assert mention_tokens(text) == ["ann", "Bob Cee", "ghost"]
    doc = text_to_adf(text, {"ann": ("a1", "Ann Bee"), "Bob Cee": ("b1", "Bob Cee")})
    para = doc["content"][0]["content"]
    assert para[0] == {"type": "text", "text": "hi "}
    assert para[1] == {"type": "mention", "attrs": {"id": "a1", "text": "@Ann Bee"}}
    assert para[3] == {"type": "mention", "attrs": {"id": "b1", "text": "@Bob Cee"}}
    assert para[-1]["text"] == " and @ghost"
    assert adf_to_text(doc).strip() == "hi @Ann Bee, see @Bob Cee and @ghost"


def test_emails_are_not_mentions():
    assert mention_tokens("mail me@example.com or @ann") == ["ann"]
