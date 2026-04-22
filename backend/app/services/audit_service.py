from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.models.audit import ActionLog
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

class AuditService:
    async def get_usage_stats(
        self,
        db: AsyncSession,
        days: int = 7,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取过去 N 天的使用统计概览"""
        since = datetime.now() - timedelta(days=days)
        base_filters = [ActionLog.created_at >= since]
        if user_id:
            base_filters.append(ActionLog.user_id == user_id)
        
        # 1. 总体概览
        query = select(
            func.count(ActionLog.id).label("total_calls"),
            func.sum(ActionLog.total_tokens).label("total_tokens"),
            func.sum(ActionLog.cost).label("total_cost"),
            func.avg(ActionLog.duration_ms).label("avg_latency")
        ).where(*base_filters)
        
        overview = await db.execute(query)
        row = overview.fetchone()
        
        # 2. 按天统计 (用于图表)
        daily_query = select(
            func.date(ActionLog.created_at).label("day"),
            func.count(ActionLog.id).label("calls"),
            func.sum(ActionLog.total_tokens).label("tokens")
        ).where(*base_filters).group_by(func.date(ActionLog.created_at)).order_by(func.date(ActionLog.created_at))
        
        daily_res = await db.execute(daily_query)
        daily_data = [
            {"date": str(r.day), "calls": r.calls, "tokens": r.tokens or 0} 
            for r in daily_res.fetchall()
        ]
        
        # 3. 按智能体统计
        agent_query = select(
            ActionLog.agent_id,
            func.count(ActionLog.id).label("calls"),
            func.sum(ActionLog.total_tokens).label("tokens")
        ).where(*base_filters).group_by(ActionLog.agent_id)
        
        agent_res = await db.execute(agent_query)
        agent_data = [
            {"agent_id": r.agent_id or "System", "calls": r.calls, "tokens": r.tokens or 0}
            for r in agent_res.fetchall()
        ]
        
        # 4. 热门行动统计
        action_query = select(
            ActionLog.action_name,
            func.count(ActionLog.id).label("calls")
        ).where(*base_filters).group_by(ActionLog.action_name).order_by(desc("calls")).limit(10)
        
        action_res = await db.execute(action_query)
        action_data = [
            {"name": r.action_name or "Unknown", "calls": r.calls}
            for r in action_res.fetchall()
        ]
        
        return {
            "summary": {
                "total_calls": row.total_calls or 0,
                "total_tokens": row.total_tokens or 0,
                "total_cost": row.total_cost or 0.0,
                "avg_latency": row.avg_latency or 0.0
            },
            "daily": daily_data,
            "by_agent": agent_data,
            "top_actions": action_data
        }

    async def log_action(
        self,
        db: AsyncSession,
        user_id: str,
        action_name: str,
        status: str = "success",
        session_id: str = None,
        agent_id: str = None,
        input_params: Dict = None,
        output_result: str = None,
        duration_ms: float = 0,
        request_tokens: int = 0,
        response_tokens: int = 0,
        total_tokens: int = 0
    ) -> ActionLog:
        """记录一条审计日志"""
        # 极简版成本估算 (假定 0.01 USD / 1k tokens)
        cost = (total_tokens / 1000.0) * 0.01
        
        log = ActionLog(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            action_name=action_name,
            status=status,
            input_params=input_params,
            output_result=output_result[:500] if output_result else None, # 截断结果摘要
            duration_ms=duration_ms,
            request_tokens=request_tokens,
            response_tokens=response_tokens,
            total_tokens=total_tokens,
            cost=cost
        )
        db.add(log)
        await db.commit()
        return log

audit_service = AuditService()
