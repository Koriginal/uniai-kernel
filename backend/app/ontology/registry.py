from app.ontology.resolver import OntologyResolver
from app.ontology.policy import DelegationPolicy


class OntologyRegistry:
    """
    Central registry for ontology-related components.
    Keep this small and explicit so we can swap implementations later.
    """

    def __init__(self):
        self.resolver = OntologyResolver()
        self.delegation_policy = DelegationPolicy()

    @staticmethod
    def build_mode_contract(interaction_mode: str) -> str:
        mode = (interaction_mode or "chat").strip()
        if mode == "workflow":
            return (
                "Output contract:\n"
                "1. Give execution objective.\n"
                "2. Give step-by-step workflow.\n"
                "3. List artifacts and checkpoints.\n"
                "4. End with machine-actionable next action."
            )
        if mode == "builder":
            return (
                "Output contract:\n"
                "1. Define architecture target and boundaries.\n"
                "2. Provide implementation slices and dependencies.\n"
                "3. Include risks and rollback path.\n"
                "4. End with a build-ready task breakdown."
            )
        if mode == "analysis":
            return (
                "Output contract:\n"
                "1. State diagnosis scope.\n"
                "2. Provide evidence-based findings.\n"
                "3. Rank impact and confidence.\n"
                "4. End with remediation actions."
            )
        if mode == "delegated_app":
            return (
                "Output contract:\n"
                "1. Restate delegated subtask boundary.\n"
                "2. Execute with reusable, structured sub-result.\n"
                "3. Include assumptions and confidence.\n"
                "4. End with a handback-ready summary for caller orchestrator."
            )
        return (
            "Output contract:\n"
            "1. Answer concisely.\n"
            "2. Use tools/delegation only when necessary.\n"
            "3. End with clear actionable summary."
        )


ontology_registry = OntologyRegistry()
