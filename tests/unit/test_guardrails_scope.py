import pytest

from app.guardrails.scope import is_action_request

ACTION_REQUESTS = [
    "Can you cancel my order for me?",
    "Please cancel order #123",
    "I'd like a refund on my order",
    "Can you modify my order to add an item?",
    "Please stop my order before it ships",
    "Can you change my order's shipping address?",
]

NOT_ACTION_REQUESTS = [
    "What's your return policy?",
    "Do you offer refunds on damaged items?",
    "Why was my order cancelled?",
    "It's been 2 days and my order still shows pending, is that normal?",
    "What does CANCELLED mean?",
    "How do I check my order status?",
]


@pytest.mark.parametrize("text", ACTION_REQUESTS)
def test_detects_action_requests(text: str) -> None:
    assert is_action_request(text) is True


@pytest.mark.parametrize("text", NOT_ACTION_REQUESTS)
def test_does_not_flag_informational_questions(text: str) -> None:
    assert is_action_request(text) is False
