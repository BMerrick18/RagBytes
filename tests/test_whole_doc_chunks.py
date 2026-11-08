import base64

from ragbytes.chunk.semantic_whole_doc.chunk import chunk_whole_doc, records_from_chunks
from ragbytes.chunk.semantic_whole_doc.openAI_call import (
    ModelChunk,
    ModelReply,
    file_message,
    read_model_reply,
)


def _chunk(**overrides) -> ModelChunk:
    fields = dict(
        content="Count the float to fifty pounds.",
        topic="The till",
        title="Bakery",
        headings=["The till"],
        heading="The till",
        subheading="",
        heading_paths=[["The till"]],
        page=1,
        pages=[1],
        format="text",
    )
    fields.update(overrides)
    return ModelChunk(**fields)


def test_the_upload_is_attached_unchanged():
    data = b"%PDF-1.4 policy bytes"
    message = file_message(data, "policy.pdf")

    attached = message[0]
    assert attached["type"] == "input_file"
    assert attached["filename"] == "policy.pdf"
    assert attached["file_data"] == "data:application/pdf;base64," + base64.b64encode(data).decode("ascii")
    assert message[1] == {"type": "input_text", "text": "The file is attached in full. Chunk it."}


def test_a_follow_up_sends_the_same_file_and_the_last_chunk():
    data = b"plain policy"
    message = file_message(data, "policy.txt", after="Count the float.")

    assert message[0]["file_data"].endswith(base64.b64encode(data).decode("ascii"))
    assert message[0]["file_data"].startswith("data:text/plain;base64,")
    assert "Count the float." in message[1]["text"]
    assert "Do not repeat it." in message[1]["text"]


def test_a_reply_keeps_the_chunk_fields():
    reply = read_model_reply(
        """
        {
          "more": true,
          "chunks": [
            {
              "content": "  Count the float.  ",
              "topic": "The till",
              "title": "Bakery",
              "headings": ["The till"],
              "heading": "The till",
              "subheading": "",
              "heading_paths": [["The till"]],
              "page": 2,
              "pages": [2, 3],
              "format": "text"
            },
            {
              "content": "   ",
              "topic": "Blank",
              "title": "",
              "headings": [],
              "heading": "",
              "subheading": "",
              "heading_paths": [],
              "page": null,
              "pages": [],
              "format": "text"
            }
          ]
        }
        """
    )

    assert reply.more is True
    assert len(reply.chunks) == 1
    assert reply.chunks[0].content == "Count the float."
    assert reply.chunks[0].pages == [2, 3]


def test_model_fields_become_the_shared_chunk_record():
    chunks = records_from_chunks(
        [
            _chunk(),
            _chunk(
                content="Close the shop before you go home.",
                topic="Closing",
                headings=["Before you leave", "Lock up"],
                heading="",
                subheading="",
                heading_paths=[],
                page=None,
                pages=[2],
                format="list",
            ),
        ],
        filename="policy.docx",
        file_id="file-1",
    )

    assert chunks[0].content == "Count the float to fifty pounds."
    assert chunks[0].embed_text == "Bakery > The till\n\nCount the float to fifty pounds."
    assert chunks[0].metadata.filename == "policy.docx"
    assert chunks[0].metadata.file_id == "file-1"
    assert chunks[0].metadata.chunk_number == 0
    assert chunks[0].metadata.topic == "The till"
    assert chunks[0].metadata.title == "Bakery"
    assert chunks[0].metadata.headings == ["The till"]
    assert chunks[0].metadata.heading == "The till"
    assert chunks[0].metadata.subheading is None
    assert chunks[0].metadata.heading_paths == [["The till"]]
    assert chunks[0].metadata.page == 1
    assert chunks[0].metadata.pages == [1]
    assert chunks[0].metadata.format == "text"
    assert chunks[0].metadata.media_type is None
    assert chunks[0].metadata.details.start == 0
    assert chunks[0].metadata.details.end == len(chunks[0].content)
    assert chunks[1].metadata.chunk_number == 1
    assert chunks[1].metadata.heading == "Before you leave"
    assert chunks[1].metadata.subheading == "Lock up"
    assert chunks[1].metadata.heading_paths == [["Before you leave", "Lock up"]]
    assert chunks[1].metadata.page == 2
    assert chunks[1].metadata.format == "list"
    assert chunks[1].embed_text == (
        "Bakery > Before you leave > Lock up\n\nClose the shop before you go home."
    )
    assert chunks[1].metadata.details.start == len(chunks[0].content) + 2


def test_the_whole_upload_is_sent_again_until_the_file_is_covered(monkeypatch):
    data = b"the whole policy"
    sent: list[tuple[bytes, str, str | None]] = []

    def fake_ask(upload: bytes, *, filename: str, after: str | None = None, model: str = ""):
        sent.append((upload, filename, after))
        if after is None:
            return ModelReply(chunks=[_chunk(content="First subject.")], more=True)
        return ModelReply(
            chunks=[
                _chunk(content="First subject."),
                _chunk(content="Second subject.", topic="Closing", page=2, pages=[2]),
            ],
            more=False,
        )

    monkeypatch.setattr("ragbytes.chunk.semantic_whole_doc.chunk.ask_for_chunks", fake_ask)

    chunks = chunk_whole_doc(data, filename="policy.pdf", file_id="file-9")

    assert sent == [(data, "policy.pdf", None), (data, "policy.pdf", "First subject.")]
    assert [chunk.content for chunk in chunks] == ["First subject.", "Second subject."]
    assert [chunk.metadata.chunk_number for chunk in chunks] == [0, 1]
    assert chunks[1].metadata.file_id == "file-9"


def test_an_empty_upload_makes_no_request(monkeypatch):
    def fake_ask(*_args, **_kwargs):
        raise AssertionError("the model was called")

    monkeypatch.setattr("ragbytes.chunk.semantic_whole_doc.chunk.ask_for_chunks", fake_ask)

    assert chunk_whole_doc(b"", filename="policy.txt") == []
