"""Regenerate demo/fixtures/sample_book.pdf from demo_course.json.

    uv run python demo/build_sample_pdf.py

Needs reportlab (dev dependency). The PDF has two-level bookmarks, so the offline
fake LLM can rebuild the same index from it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer  # noqa: E402

from demo.course import SAMPLE_PDF, layout, load_course  # noqa: E402


class BookmarkedDoc(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        key = getattr(flowable, "_bookmark", None)
        if key:
            title, level = key
            self.canv.bookmarkPage(title)
            self.canv.addOutlineEntry(title, title, level=level)


def main():
    styles = getSampleStyleSheet()
    course = load_course()
    story = [
        Spacer(1, 200),
        Paragraph(course["book_title"], styles["Title"]),
        Paragraph("Sample book for the AIB Graph demo", styles["Italic"]),
        PageBreak(),
    ]
    for i, topic in enumerate(layout()):
        heading = Paragraph(topic["title"], styles["Heading1" if topic["level"] == 0 else "Heading2"])
        heading._bookmark = (topic["title"], topic["level"])
        story += [heading, Spacer(1, 8), Paragraph(topic["text"], styles["BodyText"])]
        if topic.get("key_ideas"):
            story.append(Spacer(1, 8))
            story += [Paragraph(f"• {k}", styles["BodyText"]) for k in topic["key_ideas"]]
        story.append(PageBreak())
    doc = BookmarkedDoc(str(SAMPLE_PDF), pagesize=A4, title=course["book_title"], author="AIB Graph")
    doc.build(story)
    print(f"Wrote {SAMPLE_PDF}")


if __name__ == "__main__":
    main()
