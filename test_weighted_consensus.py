"""Sandbox tester for Apex Institutional weighted voting consensus.

This file is intentionally isolated from the live engine. It validates the
weighted math before any changes are made to core/brain.py or server.py.
"""

AGENT_WEIGHTS = {
    "macro": 0.40,
    "claw": 0.35,
    "scalper": 0.25,
}

DIRECTION_MAP = {
    "BUY": 1,
    "LONG": 1,
    "BULLISH": 1,
    "SELL": -1,
    "SHORT": -1,
    "BEARISH": -1,
    "HOLD": 0,
    "NEUTRAL": 0,
}

BUY_THRESHOLD = 0.40
SELL_THRESHOLD = -0.40


def normalize_confidence(confidence):
    """Convert 85 or 0.85 style confidence values to 0.85."""
    value = float(confidence)
    if value > 1:
        return value / 100
    return value


def calculate_consensus(decisions):
    contributions = []
    directional_score = 0.0
    hold_penalty = 0.0

    for agent, decision in decisions.items():
        direction = str(decision["direction"]).upper()
        confidence = normalize_confidence(decision["confidence"])
        weight = AGENT_WEIGHTS[agent]
        direction_int = DIRECTION_MAP[direction]
        contribution = direction_int * confidence * weight
        if direction_int == 0:
            hold_penalty += confidence * weight
        else:
            directional_score += contribution

        contributions.append(
            {
                "agent": agent,
                "direction": direction,
                "direction_int": direction_int,
                "confidence": confidence,
                "weight": weight,
                "contribution": contribution,
            }
        )

    if directional_score > 0:
        final_score = max(0, directional_score - hold_penalty)
    else:
        final_score = min(0, directional_score + hold_penalty)

    if final_score >= BUY_THRESHOLD:
        execution = "BUY"
    elif final_score <= SELL_THRESHOLD:
        execution = "SELL"
    else:
        execution = "HOLD"

    return {
        "directional_score": directional_score,
        "hold_penalty": hold_penalty,
        "final_score": final_score,
        "execution": execution,
        "contributions": contributions,
    }


TEST_SCENARIOS = [
    {
        "name": "Macro bullish vs bearish CLAW and Scalper",
        "decisions": {
            "macro": {"direction": "BUY", "confidence": 85},
            "claw": {"direction": "BEARISH", "confidence": 72},
            "scalper": {"direction": "SELL", "confidence": 85},
        },
    },
    {
        "name": "Macro and CLAW bullish, Scalper bearish",
        "decisions": {
            "macro": {"direction": "BULLISH", "confidence": 90},
            "claw": {"direction": "LONG", "confidence": 80},
            "scalper": {"direction": "SHORT", "confidence": 95},
        },
    },
    {
        "name": "Macro bearish, CLAW bullish, Scalper neutral",
        "decisions": {
            "macro": {"direction": "SELL", "confidence": 88},
            "claw": {"direction": "BUY", "confidence": 74},
            "scalper": {"direction": "NEUTRAL", "confidence": 60},
        },
    },
    {
        "name": "Macro hold, CLAW and Scalper bearish",
        "decisions": {
            "macro": {"direction": "HOLD", "confidence": 95},
            "claw": {"direction": "BEARISH", "confidence": 92},
            "scalper": {"direction": "SELL", "confidence": 84},
        },
    },
    {
        "name": "All bullish but mixed confidence",
        "decisions": {
            "macro": {"direction": "BUY", "confidence": 65},
            "claw": {"direction": "BULLISH", "confidence": 55},
            "scalper": {"direction": "LONG", "confidence": 70},
        },
    },
    {
        "name": "High-confidence Macro hold suppresses lower-weight bullish agents",
        "decisions": {
            "macro": {"direction": "HOLD", "confidence": 95},
            "claw": {"direction": "BULLISH", "confidence": 72},
            "scalper": {"direction": "BUY", "confidence": 88},
        },
    },
]


def print_scenario(scenario_number, scenario):
    print(f"\nScenario {scenario_number}: {scenario['name']}")
    print("-" * 72)
    result = calculate_consensus(scenario["decisions"])

    for item in result["contributions"]:
        confidence_pct = item["confidence"] * 100
        print(
            f"{item['agent'].upper():<8} "
            f"direction={item['direction']:<8} "
            f"dir_int={item['direction_int']:>2} "
            f"confidence={confidence_pct:>5.1f}% "
            f"weight={item['weight']:.2f} "
            f"contribution={item['contribution']:+.4f}"
        )

    print(f"Directional Score: {result['directional_score']:+.4f}")
    print(f"Hold Gravity:      {result['hold_penalty']:.4f}")
    print(f"Final Score:       {result['final_score']:+.4f}")
    print(f"Execution:   {result['execution']}")


if __name__ == "__main__":
    print("Apex Institutional - Weighted Voting Engine Sandbox")
    print("Thresholds: BUY >= +0.40 | SELL <= -0.40 | otherwise HOLD")

    for index, scenario in enumerate(TEST_SCENARIOS, start=1):
        print_scenario(index, scenario)

    print("\nValidation Instruction:")
    print("Run `python test_weighted_consensus.py` to audit consensus gravity outputs.")
