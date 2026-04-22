from app.ontology.schema import DelegationDecision, SemanticContext


class DelegationPolicy:
    """
    Policy engine for orchestrator-to-orchestrator delegation.
    """

    def evaluate_orchestrator_delegate(self, semantic: SemanticContext, requested_task: str = "") -> DelegationDecision:
        task = (requested_task or "").strip()
        mode = semantic.interaction_mode
        confidence = semantic.frame.confidence

        if task:
            return DelegationDecision(
                allow_delegate=True,
                reason="caller_provided_task",
                confidence=max(0.7, confidence),
                recommended_task=task,
            )

        if mode in {"workflow", "builder"} and confidence >= 0.6:
            generated_task = self._generate_task(semantic)
            return DelegationDecision(
                allow_delegate=True,
                reason="mode_and_confidence_match",
                confidence=confidence,
                recommended_task=generated_task,
            )
        if semantic.frame.intent in {"orchestrate", "design"} and confidence >= 0.58:
            generated_task = self._generate_task(semantic)
            return DelegationDecision(
                allow_delegate=True,
                reason="intent_and_confidence_match",
                confidence=confidence,
                recommended_task=generated_task,
            )

        return DelegationDecision(
            allow_delegate=False,
            reason="insufficient_signal_for_delegation",
            confidence=confidence,
            recommended_task=None,
        )

    @staticmethod
    def _generate_task(semantic: SemanticContext) -> str:
        intent = semantic.frame.intent
        domain = semantic.frame.domain
        query = semantic.slots.raw_query
        if intent == "orchestrate":
            return f"请作为子应用完成该任务的流程拆解与执行计划，领域={domain}。原始请求：{query}"
        if intent == "design":
            return f"请输出可执行的架构方案与实施步骤，领域={domain}。原始请求：{query}"
        return f"请在领域={domain}内完成子任务分析并返回结构化结果。原始请求：{query}"
