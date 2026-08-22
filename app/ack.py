"""ack.py - Confirmation phrase pool."""
import random

CONFIRMATIONS = [
    "Of course.",
    "My wish is your command.",
    "On it.",
    "Captured.",
    "Got you.",
    "Consider it queued.",
    "With pleasure.",
    "Absolutely.",
    "Handled.",
    "Done.",
]


def random_ack() -> str:
    return random.choice(CONFIRMATIONS)
