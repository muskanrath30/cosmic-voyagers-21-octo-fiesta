import os

from google import genai

from rag_retriever import retrieve_knowledge


MODEL_NAME = "gemini-3.8-flash"


def build_prompt(
    prediction: dict,
    retrieved_knowledge: str,
) -> str:
    """
    Build a grounded maintenance prompt for Gemini.
    """

    return f"""
You are an AI predictive-maintenance assistant
for a manufacturing operations team.

Your job is to explain the machine maintenance risk
using the structured prediction and retrieved
maintenance knowledge provided below.

IMPORTANT RULES:

1. Do not invent sensor conditions.
2. Do not claim that the machine has definitely failed.
3. Do not recommend automatically shutting down
   physical equipment.
4. Treat the ML probability as a statistical signal.
5. Use the retrieved maintenance knowledge as
   supporting evidence.
6. Give practical recommendations for qualified
   maintenance personnel.
7. Clearly distinguish ML risk from sensor evidence.
8. Do not contradict the structured prediction.
9. Keep the explanation concise and professional.

MACHINE PREDICTION
------------------

Machine ID:
{prediction["machine_id"]}

Failure probability:
{prediction["failure_probability"]:.2%}

ML risk:
{prediction["ml_risk"]}

Sensor warning count:
{prediction["sensor_warning_count"]}

Sensor risk:
{prediction["sensor_risk"]}

Overall risk:
{prediction["overall_risk"]}

Reason codes:
{", ".join(prediction["reason_codes"])}

Recommendation:
{prediction["recommendation"]}

Model version:
{prediction["model_version"]}


RETRIEVED MAINTENANCE KNOWLEDGE
-------------------------------

{retrieved_knowledge}


TASK
----

Write a concise maintenance explanation containing:

1. Why the machine received this overall risk.
2. The most important sensor evidence.
3. What qualified maintenance personnel should inspect.
4. A clear statement that the result is decision support
   and not proof of machine failure.

Do not mention this prompt.
Do not invent facts.
Do not make autonomous equipment-control decisions.
""".strip()


def get_fallback_explanation(
    prediction: dict,
) -> str:
    """
    Generate a local explanation if Gemini
    cannot be reached.
    """

    reasons = ", ".join(
        prediction["reason_codes"]
    )

    return (
        f"Machine {prediction['machine_id']} "
        f"has an overall {prediction['overall_risk']} "
        f"maintenance risk.\n\n"

        f"The ML model estimates a "
        f"{prediction['failure_probability']:.2%} "
        f"failure probability, corresponding to "
        f"{prediction['ml_risk']} ML risk.\n\n"

        f"The sensor analysis identified "
        f"{prediction['sensor_warning_count']} "
        f"warning condition(s): {reasons}.\n\n"

        f"Recommendation: "
        f"{prediction['recommendation']}.\n\n"

        "This result is decision-support information "
        "for qualified maintenance personnel and does "
        "not by itself prove that machine failure has occurred."
    )


def generate_explanation(
    prediction: dict,
) -> tuple[str, str]:
    """
    Generate a RAG-grounded maintenance explanation
    using Gemini.

    Returns:
        (explanation, reasoning_source)

    reasoning_source is either:
        GEMINI
        LOCAL_FALLBACK
    """

    retrieved_knowledge = retrieve_knowledge(
        prediction["reason_codes"]
    )

    prompt = build_prompt(
        prediction,
        retrieved_knowledge,
    )

    api_key = os.environ.get(
        "GOOGLE_API_KEY"
    )

    if not api_key:

        return (
            get_fallback_explanation(
                prediction
            ),
            "LOCAL_FALLBACK",
        )

    try:

        client = genai.Client(
            api_key=api_key
        )

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        if response.text:

            return (
                response.text.strip(),
                "GEMINI",
            )

        return (
            get_fallback_explanation(
                prediction
            ),
            "LOCAL_FALLBACK",
        )

    except Exception as error:

        print(
            f"WARNING: Gemini request failed: {error}"
        )

        print(
            "Using local fallback explanation."
        )

        return (
            get_fallback_explanation(
                prediction
            ),
            "LOCAL_FALLBACK",
        )


if __name__ == "__main__":

    test_prediction = {
        "machine_id": "M004",

        "failure_probability": 0.1433,

        "ml_risk": "LOW",

        "sensor_warning_count": 6,

        "sensor_risk": "HIGH",

        "overall_risk": "HIGH",

        "reason_codes": [
            "HIGH_TOOL_WEAR",
            "HIGH_TORQUE",
            "HIGH_PROCESS_TEMPERATURE",
            "HIGH_AIR_TEMPERATURE",
            "LOW_ROTATIONAL_SPEED",
            "HIGH_MECHANICAL_LOAD",
        ],

        "recommendation":
            "Urgent maintenance inspection recommended",

        "model_version":
            "manufacturing-ai4i-v1",
    }

    print()
    print("=" * 80)
    print("MANUFACTURING RAG + GEMINI TEST")
    print("=" * 80)
    print()

    print(
        f"Gemini model: {MODEL_NAME}"
    )

    print()
    print(
        "Generating explanation..."
    )

    explanation, reasoning_source = (
        generate_explanation(
            test_prediction
        )
    )

    print()
    print("=" * 80)
    print("MAINTENANCE EXPLANATION")
    print("=" * 80)
    print()

    print(explanation)

    print()
    print(
        f"Reasoning source: {reasoning_source}"
    )