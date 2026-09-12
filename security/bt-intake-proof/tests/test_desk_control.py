import unittest

from bt_intake_proof.cases import APPROVAL_APPROVED
from bt_intake_proof.constants import MAILBOX
from bt_intake_proof.desk_control import (
    INTENT_AMBIGUOUS,
    INTENT_APPROVE_SEND,
    INTENT_CONDITIONAL,
    INTENT_HOLD,
    INTENT_OFFICE,
    INTENT_NO_RESPONSE,
    INTENT_REVISE,
    OFFICE_STAFF,
    QUESTION_OFFER_SEND,
    QUESTION_REVIEW_WORDING,
    SOURCE_CHATGPT,
    SOURCE_FALLBACK,
    authorize_desk_intent,
    normalize_desk_intent,
    structured_action,
    submit_desk_action,
)
from bt_intake_proof.phasee_constants import PHASEE_BODY, PHASEE_FROM, PHASEE_SUBJECT, PHASEE_TO


def _ctx(**extra):
    ctx = {
        "displayed_case": True,
        "displayed_draft": True,
        "owner": "daniel",
        "last_question_kind": None,
    }
    ctx.update(extra)
    return ctx


def _binding(**extra):
    packet = {
        "case_id": "BTC-demo",
        "draft_version": 1,
        "mailbox": MAILBOX,
        "from_addr": PHASEE_FROM,
        "to_addr": PHASEE_TO,
        "cc": [],
        "bcc": [],
        "thread_id": "thr-1",
        "subject": PHASEE_SUBJECT,
        "body": PHASEE_BODY,
        "attachments": [],
        "latest_inbound_message_id": "in-1",
        "send_timing": "immediate_supervised",
    }
    packet.update(extra)
    return packet


class DeskIntentTests(unittest.TestCase):
    def test_offer_send_yeah_looks_good(self) -> None:
        result = normalize_desk_intent(
            "Yeah, looks good",
            _ctx(last_question_kind=QUESTION_OFFER_SEND),
        )
        self.assertEqual(result["intent"], INTENT_APPROVE_SEND)
        self.assertEqual(result["source"], SOURCE_FALLBACK)
        self.assertTrue(result["execute_send"])
        self.assertFalse(result["requires_magic_phrase"])
        self.assertFalse(result["requires_case_id_from_daniel"])

    def test_looks_good_while_reviewing_wording_is_not_send(self) -> None:
        result = normalize_desk_intent(
            "Looks good",
            _ctx(last_question_kind=QUESTION_REVIEW_WORDING),
        )
        self.assertEqual(result["intent"], INTENT_AMBIGUOUS)
        self.assertFalse(result["execute_send"])
        self.assertIn("send this version", result["clarification"] or "")

    def test_send_then_wait_make_it_shorter(self) -> None:
        result = normalize_desk_intent(
            "Send that - actually wait, make it shorter first",
            _ctx(last_question_kind=QUESTION_OFFER_SEND),
        )
        self.assertEqual(result["intent"], INTENT_REVISE)
        self.assertFalse(result["execute_send"])

    def test_conditional_if_she_confirms(self) -> None:
        result = normalize_desk_intent("If she confirms the address, send it", _ctx())
        self.assertEqual(result["intent"], INTENT_CONDITIONAL)
        self.assertFalse(result["execute_send"])

    def test_dont_send_overrides_the_word_send(self) -> None:
        result = normalize_desk_intent("Don't send that", _ctx(last_question_kind=QUESTION_OFFER_SEND))
        self.assertNotEqual(result["intent"], INTENT_APPROVE_SEND)
        self.assertFalse(result["execute_send"])

    def test_office_phrases(self) -> None:
        leave = normalize_desk_intent("Leave this with Brenda", _ctx())
        self.assertEqual(leave["intent"], INTENT_OFFICE)
        self.assertEqual(leave["owner"], "brenda")
        self.assertFalse(leave["execute_send"])
        ally = normalize_desk_intent("Ally is handling this", _ctx())
        self.assertEqual(ally["intent"], INTENT_OFFICE)
        self.assertEqual(ally["owner"], "ally")
        either = normalize_desk_intent("Give this one to Brenda or Ally", _ctx())
        self.assertEqual(either["intent"], INTENT_OFFICE)
        self.assertIsNone(either["owner"])
        self.assertEqual(either["clarification"], "Brenda or Ally?")
        office = normalize_desk_intent("The office has this", _ctx())
        self.assertEqual(office["intent"], INTENT_OFFICE)
        self.assertFalse(office["execute_send"])

    def test_natural_variants_are_not_an_exact_phrase_list(self) -> None:
        for spoken in ("send", "do it", "go ahead", "that works, send that", "yeah, that's fine"):
            result = normalize_desk_intent(spoken, _ctx(last_question_kind=QUESTION_OFFER_SEND))
            self.assertEqual(result["intent"], INTENT_APPROVE_SEND, spoken)
        self.assertIn("brenda", OFFICE_STAFF)
        self.assertIn("ally", OFFICE_STAFF)

    def test_office_owner_is_preserved_and_blocks_ai_send(self) -> None:
        result = normalize_desk_intent(
            "Yeah, looks good",
            _ctx(last_question_kind=QUESTION_OFFER_SEND, owner="brenda"),
        )
        self.assertEqual(result["intent"], INTENT_OFFICE)
        self.assertTrue(result["preserve_existing_office_owner"])
        self.assertFalse(result["execute_send"])


class DeskAuthorizeTests(unittest.TestCase):
    def test_inferred_send_still_needs_phase_e_binding(self) -> None:
        inferred = normalize_desk_intent("go ahead", _ctx(last_question_kind=QUESTION_OFFER_SEND))
        case = {
            "approval_state": APPROVAL_APPROVED,
            "draft_version": 1,
            "latest_inbound_message_id": "in-1",
            "thread_id": "thr-1",
        }
        draft = {"proposed_response": PHASEE_BODY}
        allowed = authorize_desk_intent(inferred, binding=_binding(), case=case, draft=draft)
        self.assertTrue(allowed["ok"])
        self.assertTrue(allowed["execute_send"])
        stale = authorize_desk_intent(
            inferred,
            binding=_binding(),
            case={**case, "latest_inbound_message_id": "in-NEWER"},
            draft=draft,
            latest_inbound_message_id="in-NEWER",
        )
        self.assertFalse(stale["ok"])
        self.assertFalse(stale["execute_send"])
        self.assertIn("inbound_changed", stale["blocks"])
        changed = authorize_desk_intent(
            inferred,
            binding=_binding(),
            case=case,
            draft={"proposed_response": PHASEE_BODY + "\nchanged"},
        )
        self.assertFalse(changed["execute_send"])
        self.assertIn("body_changed", changed["blocks"])

    def test_hold_and_office_block_send_regardless_of_model(self) -> None:
        inferred = {"intent": INTENT_APPROVE_SEND, "execute_send": True}
        case = {
            "approval_state": APPROVAL_APPROVED,
            "draft_version": 1,
            "latest_inbound_message_id": "in-1",
            "thread_id": "thr-1",
        }
        draft = {"proposed_response": PHASEE_BODY}
        held = authorize_desk_intent(inferred, binding=_binding(), case=case, draft=draft, hold=True)
        self.assertFalse(held["execute_send"])
        office = authorize_desk_intent(inferred, binding=_binding(), case=case, draft=draft, owner="ally")
        self.assertFalse(office["execute_send"])
        self.assertIn("office_owned", office["blocks"])

    def test_non_send_intents_never_authorize_send(self) -> None:
        for intent in (INTENT_REVISE, INTENT_CONDITIONAL, INTENT_OFFICE, INTENT_NO_RESPONSE, INTENT_AMBIGUOUS):
            result = authorize_desk_intent({"intent": intent}, binding=_binding())
            self.assertFalse(result["execute_send"], intent)

    def test_stale_displayed_context_blocks(self) -> None:
        inferred = {"intent": INTENT_APPROVE_SEND}
        case = {
            "approval_state": APPROVAL_APPROVED,
            "draft_version": 1,
            "latest_inbound_message_id": "in-1",
            "thread_id": "thr-1",
        }
        result = authorize_desk_intent(
            inferred,
            binding=_binding(draft_version=2),
            case={**case, "draft_version": 2},
            draft={"proposed_response": PHASEE_BODY},
            displayed_binding=_binding(draft_version=1),
        )
        self.assertFalse(result["execute_send"])
        self.assertIn("stale_displayed_context", result["blocks"])


class DeskStructuredActionTests(unittest.TestCase):
    """ChatGPT submits a small action. Python does not interpret speech here."""

    def _case(self) -> dict:
        return {
            "approval_state": APPROVAL_APPROVED,
            "draft_version": 1,
            "latest_inbound_message_id": "in-1",
            "thread_id": "thr-1",
        }

    def test_structured_send_still_needs_phase_e_binding(self) -> None:
        action = structured_action(INTENT_APPROVE_SEND)
        self.assertEqual(action["source"], SOURCE_CHATGPT)
        self.assertTrue(action["ok"])
        allowed = submit_desk_action(
            action,
            binding=_binding(),
            case=self._case(),
            draft={"proposed_response": PHASEE_BODY},
        )
        self.assertTrue(allowed["ok"])
        self.assertTrue(allowed["execute_send"])
        self.assertEqual(allowed["source"], SOURCE_CHATGPT)
        self.assertEqual(allowed["reason"], "bound_current_packet")

        missing = submit_desk_action(action)
        self.assertFalse(missing["execute_send"])
        self.assertIn("missing_current_packet", missing["blocks"])

        stale = submit_desk_action(
            action,
            binding=_binding(),
            case={**self._case(), "latest_inbound_message_id": "in-NEWER"},
            draft={"proposed_response": PHASEE_BODY},
            latest_inbound_message_id="in-NEWER",
        )
        self.assertFalse(stale["ok"])
        self.assertFalse(stale["execute_send"])
        self.assertIn("inbound_changed", stale["blocks"])

        changed = submit_desk_action(
            action,
            binding=_binding(),
            case=self._case(),
            draft={"proposed_response": PHASEE_BODY + "\nchanged"},
        )
        self.assertFalse(changed["execute_send"])
        self.assertIn("body_changed", changed["blocks"])

    def test_unknown_or_missing_intent_is_rejected(self) -> None:
        unknown = structured_action("please_send_it")
        self.assertFalse(unknown["ok"])
        self.assertEqual(unknown["reason"], "unknown_intent")
        self.assertFalse(unknown["execute_send"])
        self.assertEqual(unknown["source"], SOURCE_CHATGPT)

        missing = submit_desk_action({})
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["reason"], "missing_structured_intent")
        self.assertFalse(missing["execute_send"])

        from_mapping = structured_action({"intent": "not_a_real_intent", "owner": "brenda"})
        self.assertFalse(from_mapping["ok"])
        self.assertEqual(from_mapping["reason"], "unknown_intent")

    def test_office_and_hold_block_chatgpt_send(self) -> None:
        action = structured_action(INTENT_APPROVE_SEND)
        held = submit_desk_action(
            action,
            binding=_binding(),
            case=self._case(),
            draft={"proposed_response": PHASEE_BODY},
            hold=True,
        )
        self.assertFalse(held["execute_send"])
        self.assertIn("hold", held["blocks"])

        office = submit_desk_action(
            action,
            binding=_binding(),
            case=self._case(),
            draft={"proposed_response": PHASEE_BODY},
            owner="ally",
        )
        self.assertFalse(office["execute_send"])
        self.assertIn("office_owned", office["blocks"])

    def test_non_send_structured_intents_never_authorize_send(self) -> None:
        for intent in (INTENT_HOLD, INTENT_REVISE, INTENT_OFFICE, INTENT_NO_RESPONSE, INTENT_AMBIGUOUS):
            result = submit_desk_action({"intent": intent}, binding=_binding())
            self.assertEqual(result["source"], SOURCE_CHATGPT)
            self.assertFalse(result["execute_send"], intent)
            self.assertTrue(result["ok"], intent)

    def test_fallback_utterance_path_stays_available(self) -> None:
        inferred = normalize_desk_intent("go ahead", _ctx(last_question_kind=QUESTION_OFFER_SEND))
        self.assertEqual(inferred["source"], SOURCE_FALLBACK)
        allowed = authorize_desk_intent(
            inferred,
            binding=_binding(),
            case=self._case(),
            draft={"proposed_response": PHASEE_BODY},
        )
        self.assertEqual(allowed["source"], SOURCE_FALLBACK)
        self.assertTrue(allowed["execute_send"])


if __name__ == "__main__":
    unittest.main()
