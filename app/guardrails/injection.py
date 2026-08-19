from __future__ import annotations


def wrap_untrusted_content(label: str, content: str) -> str:
    """Delimit external content (retrieved docs, tool results) so it reads
    to the model as data to reference, not instructions to follow - even if
    the content itself contains something that looks like an instruction
    (a prompt-injection attempt embedded in a doc, or in principle a
    maliciously-crafted field coming back from a tool call).

    Delimiting alone isn't a complete defense - it's paired with an
    explicit line in the system prompts (prompts/answer.py,
    prompts/critique.py) telling the model never to follow directives found
    inside these tags. Verified live against the real model (see
    tests/llm/test_injection_resistance.py) rather than assumed to work
    from the delimiter alone.
    """
    return f'<untrusted_content source="{label}">\n{content}\n</untrusted_content>'
