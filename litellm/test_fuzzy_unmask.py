"""Unit tests for the tolerant un-masking of all three response shapes (no running stack)."""

from types import SimpleNamespace as NS

from fuzzy_unmask import restore, restore_chat_chunks, restore_response, restore_responses_events

TOKENS = {"<PERSON_1>": "Иван Петров", "<PHONE_NUMBER_2>": "+7 912 345-67-89"}


def test_restore_accepts_every_spelling_of_a_placeholder():
    text = "<PERSON_1>, [PERSON_1], {PERSON_1}, (PERSON_1), PERSON_1, <PHONE_NUMBER_2>"
    assert restore(text, TOKENS) == ", ".join(["Иван Петров"] * 5 + ["+7 912 345-67-89"])


def test_restore_leaves_unknown_placeholders_alone():
    assert restore("<EMAIL_ADDRESS_3> wrote", TOKENS) == "<EMAIL_ADDRESS_3> wrote"


def test_whole_chat_completion_text_and_tool_arguments():
    response = NS(choices=[NS(message=NS(content="Это [PERSON_1]",
                                         tool_calls=[NS(function=NS(arguments='{"to":"PHONE_NUMBER_2"}'))]))])
    restore_response(response, TOKENS)
    assert response.choices[0].message.content == "Это Иван Петров"
    assert response.choices[0].message.tool_calls[0].function.arguments == '{"to":"+7 912 345-67-89"}'


def test_whole_anthropic_message():
    response = {"type": "message", "content": [{"type": "text", "text": "Привет, {PERSON_1}"},
                                               {"type": "tool_use", "input": "call PHONE_NUMBER_2"}]}
    restore_response(response, TOKENS)
    assert response["content"][0]["text"] == "Привет, Иван Петров"
    assert response["content"][1]["input"] == "call +7 912 345-67-89"


def test_whole_responses_api_output():
    response = NS(output=[NS(type="message", content=[NS(type="output_text", text="Это [PERSON_1]")]),
                          NS(type="function_call", arguments='{"phone":"PHONE_NUMBER_2"}', content=None)])
    restore_response(response, TOKENS)
    assert response.output[0].content[0].text == "Это Иван Петров"
    assert response.output[1].arguments == '{"phone":"+7 912 345-67-89"}'


def test_chat_stream_restores_a_placeholder_split_across_chunks():
    chunks = [NS(choices=[NS(delta=NS(content=piece))]) for piece in ("Это <PERS", "ON_1>, тел. ", "[PHONE_", "NUMBER_2]")]
    restore_chat_chunks(chunks, TOKENS)
    assert chunks[0].choices[0].delta.content == "Это Иван Петров, тел. +7 912 345-67-89"
    assert all(c.choices[0].delta.content == "" for c in chunks[1:])


def _delta(piece: str, item_id: str = "msg_1", content_index: int = 0) -> NS:
    return NS(type="response.output_text.delta", item_id=item_id, output_index=0, content_index=content_index, delta=piece)


def test_responses_stream_restores_deltas_done_events_and_the_final_response():
    masked = "Меня зовут <PERSON_1>, тел. [PHONE_NUMBER_2]."
    events = [
        NS(type="response.created", response=NS(output=[])),
        *[_delta(p) for p in ("Меня зовут <PERS", "ON", "_1>, тел. [PHONE_NUMBER", "_2].")],
        NS(type="response.output_text.done", item_id="msg_1", output_index=0, content_index=0, text=masked),
        NS(type="response.content_part.done", item_id="msg_1", output_index=0, content_index=0,
           part=NS(type="output_text", text=masked)),
        NS(type="response.output_item.done", output_index=0, item=NS(type="message", content=[NS(text=masked)])),
        NS(type="response.completed", response=NS(output=[NS(type="message", content=[NS(text=masked)])])),
    ]
    restore_responses_events(events, TOKENS)
    plain = "Меня зовут Иван Петров, тел. +7 912 345-67-89."
    assert events[1].delta == plain
    assert all(e.delta == "" for e in events[2:5])
    assert events[5].text == plain
    assert events[6].part.text == plain
    assert events[7].item.content[0].text == plain
    assert events[8].response.output[0].content[0].text == plain


def test_responses_stream_keeps_separate_output_parts_apart():
    events = [_delta("<PERSON_1>", item_id="msg_1"), _delta("PHONE_NUMBER_2", item_id="msg_2")]
    restore_responses_events(events, TOKENS)
    assert [e.delta for e in events] == ["Иван Петров", "+7 912 345-67-89"]


def test_responses_stream_and_item_restore_reasoning_summaries():
    events = [
        NS(type="response.reasoning_summary_text.delta", item_id="rs_1", output_index=0, summary_index=0, delta="Зовут <PERS"),
        NS(type="response.reasoning_summary_text.delta", item_id="rs_1", output_index=0, summary_index=0, delta="ON_1>"),
        NS(type="response.reasoning_summary_text.done", item_id="rs_1", output_index=0, summary_index=0, text="Зовут <PERSON_1>"),
        NS(type="response.reasoning_summary_part.done", item_id="rs_1", output_index=0, summary_index=0,
           part=NS(type="summary_text", text="Зовут <PERSON_1>")),
        NS(type="response.output_item.done", output_index=0,
           item=NS(type="reasoning", summary=[NS(type="summary_text", text="Зовут <PERSON_1>")], content=None)),
    ]
    restore_responses_events(events, TOKENS)
    assert [events[0].delta, events[1].delta] == ["Зовут Иван Петров", ""]
    assert events[2].text == events[3].part.text == events[4].item.summary[0].text == "Зовут Иван Петров"


def test_responses_stream_restores_function_call_arguments():
    events = [
        NS(type="response.function_call_arguments.delta", item_id="fc_1", output_index=1, delta='{"to":"<PHONE_'),
        NS(type="response.function_call_arguments.delta", item_id="fc_1", output_index=1, delta='NUMBER_2>"}'),
        NS(type="response.function_call_arguments.done", item_id="fc_1", output_index=1, arguments='{"to":"<PHONE_NUMBER_2>"}'),
    ]
    restore_responses_events(events, TOKENS)
    assert events[0].delta == '{"to":"+7 912 345-67-89"}'
    assert events[1].delta == ""
    assert events[2].arguments == '{"to":"+7 912 345-67-89"}'
