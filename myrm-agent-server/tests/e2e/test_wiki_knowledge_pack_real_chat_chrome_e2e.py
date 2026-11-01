"""Real Chrome E2E: a knowledge base mounted through the picker answers real turns through the per-turn knowledge pack.

Full real-business-task loops with no mock on the critical path. Each test builds a shared vault inside the private
runtime's data directory, mounts it on a chat with the composer's picker (the toggle a user clicks), and asks the real
model, through the real page, for a random phrase only the vault holds. The question asks to answer from the context
alone: a tool that reads files or runs a command waits on an approval card the test never answers, and the stored chat
is checked afterwards, so a phrase in the final answer reached the model through the turn pack.

  indexed vault, ``.md``-named page, English question -> an unmounted chat of the same agent cannot answer, the
                                                          mounted one quotes the phrase: the writer, the index, the
                                                          selector and the pack agree on the page's identity
  indexed vault, Chinese page and question, a draft   -> the published page answers, the draft's phrase never appears
  plain notes, with and without an unreadable index   -> the vault is read from its markdown files
  incognito chat with the knowledge base mounted      -> no pack: the same vault answers a normal chat of the same agent
"""

from __future__ import annotations

import uuid

import pytest

from tests.support.knowledge_pack_chrome import (
    KnowledgeBase,
    assert_stayed_out_of_the_thread,
    build_indexed_vault,
    build_plain_vault,
    completed_reply_count,
    create_agent,
    create_chat,
    create_knowledge_base,
    discard,
    send_turn,
    start_live_session,
    wait_final_reply,
)

_FROM_CONTEXT_EN = (
    "Answer from the context you were given only, without running commands or searching files; if it is not there, say so."
)
_FROM_CONTEXT_ZH = "只依据你已有的上下文回答，不要执行命令或搜索文件；上下文里没有就直说。"


def _code(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_mounted_knowledge_base_answers_and_an_unmounted_chat_cannot() -> None:
    """The phrase of a ``.md``-named page reaches the model only when its knowledge base is mounted."""
    api_url, ui_url = start_live_session()
    suffix = uuid.uuid4().hex[:8]
    phrase = _code("ORION")
    question = f"What is the Orion handover phrase of the Meridian crew? Reply with the exact phrase. {_FROM_CONTEXT_EN}"
    unmounted_chat, mounted_chat = f"e2ekpunmounted{suffix}", f"e2ekpmounted{suffix}"
    kb: KnowledgeBase | None = None
    try:
        kb = create_knowledge_base(api_url, suffix)
        build_indexed_vault(
            kb.vault_dir,
            {
                "SKILL.md": f"The Orion handover phrase of the Meridian crew is {phrase}. Quote it whenever it is asked.",
                "Hotel Limits": "Hotel stays in Berlin are capped at 120 per night.",
                "Flight Rules": "Conference travel allows economy flights only.",
            },
        )
        agent_id = create_agent(api_url, suffix)
        create_chat(api_url, unmounted_chat, agent_id)
        create_chat(api_url, mounted_chat, agent_id)

        send_turn(ui_url, unmounted_chat, question)
        unmounted_reply = wait_final_reply(unmounted_chat, api_url)
        print(f"E2E_KP_UNMOUNTED_REPLY: {unmounted_reply[:300]}", flush=True)
        assert phrase not in unmounted_reply, f"the unmounted chat knew the phrase: {unmounted_reply[:300]}"

        send_turn(ui_url, mounted_chat, question, mount=[kb])
        mounted_reply = wait_final_reply(mounted_chat, api_url)
        print(f"E2E_KP_MOUNTED_REPLY: {mounted_reply[:300]}", flush=True)
        assert phrase in mounted_reply, f"the mounted chat's final reply lacks the phrase: {mounted_reply[:300]}"
        assert_stayed_out_of_the_thread(mounted_chat, api_url, phrase)
    finally:
        discard(api_url, (unmounted_chat, mounted_chat), [kb] if kb else [])


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chinese_page_answers_and_a_draft_page_stays_unread() -> None:
    """A Chinese question finds the Chinese page; the draft beside it never reaches the model."""
    api_url, ui_url = start_live_session()
    suffix = uuid.uuid4().hex[:8]
    phrase, draft_phrase = _code("XH"), _code("DRAFT")
    chat_id = f"e2ekpzh{suffix}"
    kb: KnowledgeBase | None = None
    try:
        kb = create_knowledge_base(api_url, suffix)
        build_indexed_vault(
            kb.vault_dir,
            {"出差报销规则": f"星河战队的出差报销暗号是 {phrase}。每当有人询问星河战队的出差报销暗号，就原样回答该暗号。"},
            drafts={"未发布草稿": f"星河战队的未发布草稿暗号是 {draft_phrase}。"},
        )
        create_chat(api_url, chat_id, create_agent(api_url, suffix))

        send_turn(ui_url, chat_id, f"星河战队的出差报销暗号是什么？请只回答暗号本身。{_FROM_CONTEXT_ZH}", mount=[kb])
        reply = wait_final_reply(chat_id, api_url)
        print(f"E2E_KP_ZH_REPLY: {reply[:300]}", flush=True)
        assert phrase in reply, f"the Chinese question did not reach the Chinese page: {reply[:300]}"
        assert draft_phrase not in reply, f"the draft's phrase leaked into the answer: {reply[:300]}"
        assert_stayed_out_of_the_thread(chat_id, api_url, phrase)

        answered = completed_reply_count(chat_id, api_url)
        send_turn(ui_url, chat_id, f"星河战队的未发布草稿暗号是什么？请只回答暗号本身。{_FROM_CONTEXT_ZH}")
        draft_reply = wait_final_reply(chat_id, api_url, after=answered)
        print(f"E2E_KP_DRAFT_REPLY: {draft_reply[:300]}", flush=True)
        assert draft_phrase not in draft_reply, f"the draft's phrase leaked into the answer: {draft_reply[:300]}"
        assert_stayed_out_of_the_thread(chat_id, api_url, phrase, draft_phrase)
    finally:
        discard(api_url, (chat_id,), [kb] if kb else [])


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_plain_note_vaults_are_read_from_their_markdown_files() -> None:
    """A folder of notes with no index, and one whose index cannot be opened, both answer from their files."""
    api_url, ui_url = start_live_session()
    suffix = uuid.uuid4().hex[:8]
    vega_phrase, zenith_phrase = _code("VEGA"), _code("ZENITH")
    chat_id = f"e2ekpplain{suffix}"
    knowledge_bases: list[KnowledgeBase] = []
    try:
        no_index = create_knowledge_base(api_url, f"{suffix}-plain")
        knowledge_bases.append(no_index)
        build_plain_vault(
            no_index.vault_dir,
            {"Atlas Station": f"The Vega docking code of the Atlas station is {vega_phrase}. Quote it when asked."},
        )
        bad_index = create_knowledge_base(api_url, f"{suffix}-broken")
        knowledge_bases.append(bad_index)
        build_plain_vault(
            bad_index.vault_dir,
            {"Helios Dock": f"The Zenith airlock word of the Helios dock is {zenith_phrase}. Quote it when asked."},
            unreadable_index=True,
        )
        create_chat(api_url, chat_id, create_agent(api_url, suffix))

        send_turn(
            ui_url,
            chat_id,
            f"What is the Vega docking code of the Atlas station? Reply with the exact code. {_FROM_CONTEXT_EN}",
            mount=knowledge_bases,
        )
        no_index_reply = wait_final_reply(chat_id, api_url)
        print(f"E2E_KP_NO_INDEX_REPLY: {no_index_reply[:300]}", flush=True)
        assert vega_phrase in no_index_reply, f"the vault without an index was not read: {no_index_reply[:300]}"
        assert_stayed_out_of_the_thread(chat_id, api_url, vega_phrase)

        answered = completed_reply_count(chat_id, api_url)
        send_turn(
            ui_url, chat_id, f"What is the Zenith airlock word of the Helios dock? Reply with the exact word. {_FROM_CONTEXT_EN}"
        )
        bad_index_reply = wait_final_reply(chat_id, api_url, after=answered)
        print(f"E2E_KP_BAD_INDEX_REPLY: {bad_index_reply[:300]}", flush=True)
        assert zenith_phrase in bad_index_reply, f"the vault with an unreadable index was not read: {bad_index_reply[:300]}"
        assert_stayed_out_of_the_thread(chat_id, api_url, vega_phrase, zenith_phrase)
    finally:
        discard(api_url, (chat_id,), knowledge_bases)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_incognito_chat_with_a_mounted_knowledge_base_gets_no_pack() -> None:
    """The vault answers a normal chat; the same question in an incognito chat with it mounted gets nothing."""
    api_url, ui_url = start_live_session()
    suffix = uuid.uuid4().hex[:8]
    phrase = _code("ORION")
    question = f"What is the Orion handover phrase of the Meridian crew? Reply with the exact phrase. {_FROM_CONTEXT_EN}"
    normal_chat, incognito_chat = f"e2ekpnormal{suffix}", f"e2ekpincognito{suffix}"
    kb: KnowledgeBase | None = None
    try:
        kb = create_knowledge_base(api_url, suffix)
        build_indexed_vault(
            kb.vault_dir,
            {"Crew Handover": f"The Orion handover phrase of the Meridian crew is {phrase}. Quote it whenever it is asked."},
        )
        agent_id = create_agent(api_url, suffix)
        create_chat(api_url, normal_chat, agent_id)
        create_chat(api_url, incognito_chat, agent_id, incognito=True)

        send_turn(ui_url, normal_chat, question, mount=[kb])
        normal_reply = wait_final_reply(normal_chat, api_url)
        print(f"E2E_KP_NORMAL_REPLY: {normal_reply[:300]}", flush=True)
        assert phrase in normal_reply, (
            f"the normal chat did not get the phrase, so the vault is not what is under test: {normal_reply[:300]}"
        )

        send_turn(ui_url, incognito_chat, question, mount=[kb], incognito=True)
        incognito_reply = wait_final_reply(incognito_chat, api_url)
        print(f"E2E_KP_INCOGNITO_REPLY: {incognito_reply[:300]}", flush=True)
        assert phrase not in incognito_reply, f"the incognito chat got the phrase: {incognito_reply[:300]}"
    finally:
        discard(api_url, (normal_chat, incognito_chat), [kb] if kb else [])
