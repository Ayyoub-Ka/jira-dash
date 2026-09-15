from __future__ import annotations


def adf_to_text(node) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    t = node.get("type")
    kids = node.get("content", []) or []
    if t == "text":
        s = node.get("text", "")
        for m in node.get("marks", []) or []:
            if m.get("type") == "code":
                s = f"`{s}`"
            elif m.get("type") == "strong":
                s = f"**{s}**"
            elif m.get("type") == "link":
                s = f"[{s}]({m.get('attrs', {}).get('href', '')})"
        return s
    if t == "hardBreak":
        return "\n"
    if t == "mention":
        return "@" + node.get("attrs", {}).get("text", "").lstrip("@")
    if t == "emoji":
        return node.get("attrs", {}).get("text", "")
    if t == "media":
        a = node.get("attrs", {})
        return f"[{'image' if a.get('type') == 'file' else 'media'}: {a.get('alt') or a.get('id', '')}]"
    if t in ("mediaSingle", "mediaGroup"):
        return "".join(adf_to_text(k) for k in kids) + "\n\n"
    if t == "inlineCard":
        return node.get("attrs", {}).get("url", "")
    if t == "codeBlock":
        return "```\n" + "".join(adf_to_text(k) for k in kids) + "\n```\n"
    if t == "heading":
        return "#" * node.get("attrs", {}).get("level", 1) + " " + "".join(adf_to_text(k) for k in kids) + "\n\n"
    if t == "listItem":
        return "- " + "".join(adf_to_text(k) for k in kids).strip() + "\n"
    if t in ("bulletList", "orderedList"):
        return "".join(adf_to_text(k) for k in kids) + "\n"
    if t == "rule":
        return "\n---\n"
    if t in ("paragraph", "blockquote", "panel"):
        return "".join(adf_to_text(k) for k in kids) + "\n\n"
    if t in ("table", "tableRow"):
        return "".join(adf_to_text(k) for k in kids) + ("\n" if t == "tableRow" else "")
    if t in ("tableCell", "tableHeader"):
        return "| " + "".join(adf_to_text(k) for k in kids).strip() + " "
    return "".join(adf_to_text(k) for k in kids)


def text_to_adf(text: str) -> dict:
    content = []
    for para in text.split("\n\n"):
        inline: list[dict] = []
        for i, line in enumerate(para.split("\n")):
            if i:
                inline.append({"type": "hardBreak"})
            if line:
                inline.append({"type": "text", "text": line})
        content.append({"type": "paragraph", "content": inline or [{"type": "text", "text": " "}]})
    return {"type": "doc", "version": 1, "content": content}
