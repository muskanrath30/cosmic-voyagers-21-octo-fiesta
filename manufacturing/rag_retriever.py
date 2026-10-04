from pathlib import Path


ROOT = Path(__file__).resolve().parent

KNOWLEDGE_FILE = (
    ROOT
    / "knowledge"
    / "maintenance_manual.txt"
)


def load_knowledge() -> str:
    """
    Load the local maintenance knowledge base.
    """

    with open(
        KNOWLEDGE_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return file.read()


def retrieve_knowledge(
    reason_codes: list[str],
) -> str:
    """
    Retrieve relevant maintenance knowledge
    for the supplied reason codes.

    This is our first simple local RAG implementation.
    """

    knowledge = load_knowledge()

    sections = knowledge.split("\n\n")

    matched_sections = []

    keyword_map = {
        "HIGH_TOOL_WEAR": [
            "HIGH TOOL WEAR",
        ],
        "HIGH_TORQUE": [
            "HIGH TORQUE",
        ],
        "HIGH_PROCESS_TEMPERATURE": [
            "HIGH PROCESS TEMPERATURE",
        ],
        "HIGH_AIR_TEMPERATURE": [
            "HIGH AIR TEMPERATURE",
        ],
        "LOW_ROTATIONAL_SPEED": [
            "LOW ROTATIONAL SPEED",
        ],
        "HIGH_MECHANICAL_LOAD": [
            "HIGH MECHANICAL LOAD",
        ],
    }

    for reason_code in reason_codes:

        keywords = keyword_map.get(
            reason_code,
            [],
        )

        for section in sections:

            section_upper = section.upper()

            if any(
                keyword in section_upper
                for keyword in keywords
            ):
                if section not in matched_sections:
                    matched_sections.append(
                        section
                    )

    # Add general principles
    for section in sections:

        if (
            "GENERAL PRINCIPLES"
            in section.upper()
            or "MAINTENANCE DECISION PRINCIPLES"
            in section.upper()
        ):
            if section not in matched_sections:
                matched_sections.append(
                    section
                )

    return "\n\n".join(
        matched_sections
    )


if __name__ == "__main__":

    test_reason_codes = [
        "HIGH_TOOL_WEAR",
        "HIGH_TORQUE",
        "HIGH_MECHANICAL_LOAD",
    ]

    result = retrieve_knowledge(
        test_reason_codes
    )

    print()
    print("=" * 80)
    print("LOCAL RAG RETRIEVAL TEST")
    print("=" * 80)
    print()
    print(result)