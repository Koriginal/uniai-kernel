import React, { useEffect, useState } from 'react';
import { Card, Typography, Steps, Tag, Space, Spin, Tooltip, Divider, Button } from 'antd';
import { 
  ThunderboltOutlined, CheckCircleOutlined, SyncOutlined, 
  LeftCircleOutlined, NodeIndexOutlined, ClockCircleOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;

interface GraphTracePanelProps {
  visible: boolean;
  onClose: () => void;
  currentAgentName?: string;
  isStreaming: boolean;
  nodeEvents: any[];
  runtimeEvents?: any[];
}

const eventLabelMap: Record<string, string> = {
  task_runtime: '任务规划',
  task_runtime_update: '任务更新',
  task_evaluation: '任务验收',
  tool_runtime: '工具执行',
  ontology_runtime: '本体运行',
  node_event: '节点事件',
};

const statusColor = (status?: string) => {
  if (!status) return 'default';
  if (['success', 'passed', 'completed'].includes(status)) return 'green';
  if (['running', 'repairing', 'in_progress'].includes(status)) return 'processing';
  if (['blocked', 'warning', 'warn'].includes(status)) return 'warning';
  if (['error', 'failed', 'deny'].includes(status)) return 'error';
  return 'default';
};

const compactTime = (value?: number) => {
  if (!value) return '';
  return new Date(value).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const summarizeRuntimeEvent = (event: any) => {
  const payload = event?.payload || {};
  if (event.type === 'tool_runtime') {
    return {
      title: payload.tool_label || payload.tool_name || '工具',
      status: payload.status,
      detail: [
        payload.plan_step_id ? `步骤 ${payload.plan_step_id}` : '',
        payload.policy_decision ? `策略 ${payload.policy_decision}` : '',
        payload.artifact_id ? `产物 ${payload.artifact_id}` : '',
      ].filter(Boolean).join(' · ') || payload.policy_reason || '',
    };
  }
  if (event.type === 'task_evaluation') {
    const evaluation = payload.task_evaluation || payload.evaluation || payload;
    return {
      title: '任务验收',
      status: evaluation.status,
      detail: Array.isArray(evaluation.missing_requirements) && evaluation.missing_requirements.length > 0
        ? `缺口 ${evaluation.missing_requirements.join(', ')}`
        : `检查 ${Array.isArray(evaluation.checks) ? evaluation.checks.length : 0} 项`,
    };
  }
  if (event.type === 'task_runtime' || event.type === 'task_runtime_update') {
    const runtime = payload.task_runtime || payload.runtime || payload;
    const frame = runtime.task_frame || {};
    const plan = runtime.execution_plan || {};
    const steps = Array.isArray(plan.steps) ? plan.steps : [];
    return {
      title: frame.kind || '任务运行时',
      status: plan.status,
      detail: [
        steps.length ? `${steps.length} 步` : '',
        plan.current_step ? `当前 ${plan.current_step}` : '',
      ].filter(Boolean).join(' · '),
    };
  }
  if (event.type === 'ontology_runtime') {
    return {
      title: payload.space_name || payload.space_code || '本体运行',
      status: payload.status,
      detail: payload.trigger_reason || '',
    };
  }
  return {
    title: event.type || '事件',
    status: payload.status,
    detail: payload.message || '',
  };
};

const GraphTracePanel: React.FC<GraphTracePanelProps> = ({ visible, onClose, currentAgentName, isStreaming, nodeEvents, runtimeEvents = [] }) => {
  const [nodes, setNodes] = useState<any[]>([]);
  const [capabilities, setCapabilities] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // 根据实时事件计算当前活跃步骤和节点状态
  const getActiveStep = () => {
    if (nodeEvents.length === 0) return 0;
    
    // 找到最后一个 start 事件
    const lastStart = [...nodeEvents].reverse().find(e => e.event === 'start');
    if (!lastStart) return 0;
    
    // 映射节点 ID 到步骤索引
    const nodeOrder = ['context', 'task_planner', 'agent', 'tool_executor', 'handoff', 'orchestrator_invoke', 'synthesize', 'task_evaluator'];
    const idx = nodeOrder.indexOf(lastStart.node);
    return idx === -1 ? 0 : idx;
  };

  const activeStep = getActiveStep();
  const completedNodes = nodeEvents.filter(e => e.event === 'end').map(e => e.node);
  const errorNodes = nodeEvents.filter(e => e.event === 'end' && e.payload?.status === 'error').map(e => e.node);

  useEffect(() => {
    if (visible) {
      fetchNodes();
    }
  }, [visible]);

  useEffect(() => {
    // 自动重置/同步逻辑 (如果需要)
  }, [visible, isStreaming, nodeEvents]);

  const fetchNodes = async () => {
    setLoading(true);
    try {
      const [nodesRes, capabilityRes] = await Promise.all([
        axios.get('/api/v1/graph/nodes'),
        axios.get('/api/v1/graph/runtime/capabilities'),
      ]);
      setNodes(nodesRes.data.nodes || []);
      setCapabilities(capabilityRes.data || null);
    } catch {
      // fallback
      setNodes([
          { id: 'context', label: '上下文构建', description: '加载记忆、语义帧与本体预处理', icon: '📥' },
          { id: 'task_planner', label: '任务规划', description: '生成 task_frame 与 execution_plan', icon: '🧭' },
          { id: 'agent', label: 'LLM 推理', description: '读取运行时契约并生成动作', icon: '🤖' },
          { id: 'tool_executor', label: '工具执行', description: '执行工具并写入执行产物', icon: '🔧' },
          { id: 'handoff', label: '专家路由', description: '移交控制权', icon: '🤝' },
          { id: 'orchestrator_invoke', label: '子主控调用', description: '调用下级编排器处理子任务', icon: '🪄' },
          { id: 'synthesize', label: '汇总归还', description: '收尾与回调', icon: '📝' },
          { id: 'task_evaluator', label: '任务验收', description: '检查完成条件并决定是否修复', icon: '✅' }
      ]);
      setCapabilities(null);
    } finally {
      setLoading(false);
    }
  };

  const taskKinds: string[] = capabilities?.task_kinds
    || capabilities?.runtime_capabilities?.task_kinds
    || (Array.isArray(capabilities?.capabilities) ? capabilities.capabilities.map((item: any) => item.name).filter(Boolean) : []);
  const eventTypes: string[] = capabilities?.events || capabilities?.runtime_events || [];
  const latestTaskRuntimeEvent = [...runtimeEvents].reverse().find((event) => event.type === 'task_runtime' || event.type === 'task_runtime_update');
  const latestTaskRuntime = latestTaskRuntimeEvent?.payload?.task_runtime || latestTaskRuntimeEvent?.payload?.runtime || latestTaskRuntimeEvent?.payload || {};
  const latestTaskFrame = latestTaskRuntime.task_frame || {};
  const latestPlan = latestTaskRuntime.execution_plan || {};
  const latestEvaluationEvent = [...runtimeEvents].reverse().find((event) => event.type === 'task_evaluation');
  const latestEvaluation = latestEvaluationEvent?.payload?.task_evaluation || latestEvaluationEvent?.payload?.evaluation || latestEvaluationEvent?.payload || {};
  const finalToolEvents = runtimeEvents
    .filter((event) => event.type === 'tool_runtime')
    .map((event) => event.payload || {})
    .filter((payload) => !payload.phase || payload.phase === 'end');
  const artifactCount = finalToolEvents.filter((event) => event.artifact_id).length;
  const blockedToolCount = finalToolEvents.filter((event) => event.status === 'blocked').length;
  const timelineEvents = [
    ...nodeEvents.map((event) => ({ type: 'node_event', timestamp: event.timestamp, payload: event })),
    ...runtimeEvents,
  ].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));

  if (!visible) return null;

  return (
    <Card
      style={{
        width: 320,
        height: '100%',
        borderLeft: '1px solid #f0f0f0',
        borderRadius: 0,
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '-4px 0 16px rgba(0,0,0,0.03)',
        animation: 'slideInRight 0.3s ease'
      }}
      bodyStyle={{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }}
    >
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: '#fafafa'
      }}>
        <Space>
          <NodeIndexOutlined style={{ color: '#1890ff', fontSize: 16 }} />
          <Title level={5} style={{ margin: 0 }}>图执行轨迹</Title>
        </Space>
        <LeftCircleOutlined 
          onClick={onClose} 
          style={{ fontSize: 18, color: '#bfbfbf', cursor: 'pointer' }}
          className="hover-blue"
        />
      </div>

      {/* Content */}
      <div style={{ flex: 1, padding: '24px 24px', overflowY: 'auto' }}>
        <div style={{ marginBottom: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
           <Text type="secondary">当前编排器</Text>
           <Tag color="cyan">{currentAgentName || 'Orchestrator'}</Tag>
        </div>

        <div style={{
          marginBottom: 18,
          border: '1px solid #e5e7eb',
          background: '#fff',
          borderRadius: 8,
          padding: '10px 12px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <Text strong style={{ fontSize: 13 }}>本轮运行</Text>
            {isStreaming ? <Tag color="processing">执行中</Tag> : <Tag color="green">已停止</Tag>}
          </div>
          <Space size={[4, 6]} wrap>
            {latestTaskFrame.kind && <Tag color="blue">{latestTaskFrame.kind}</Tag>}
            {latestPlan.status && <Tag color={statusColor(latestPlan.status)}>计划 {latestPlan.status}</Tag>}
            {latestEvaluation.status && <Tag color={statusColor(latestEvaluation.status)}>验收 {latestEvaluation.status}</Tag>}
            {finalToolEvents.length > 0 && <Tag>工具 {finalToolEvents.length}</Tag>}
            {blockedToolCount > 0 && <Tag color="warning">拦截 {blockedToolCount}</Tag>}
            {artifactCount > 0 && <Tag color="cyan">产物 {artifactCount}</Tag>}
          </Space>
          {latestPlan.current_step && (
            <div style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>
              当前步骤：{latestPlan.current_step}
            </div>
          )}
        </div>

        <div style={{
          marginBottom: 18,
          border: '1px solid #eef2f7',
          background: '#fbfdff',
          borderRadius: 8,
          padding: '10px 12px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <Text strong style={{ fontSize: 13 }}>运行时能力</Text>
            {capabilities ? <Tag color="green">已同步</Tag> : <Tag>本地兜底</Tag>}
          </div>
          <Space size={[4, 6]} wrap>
            {taskKinds.slice(0, 6).map((kind) => <Tag key={kind} color="blue">{kind}</Tag>)}
            {eventTypes.slice(0, 4).map((event) => <Tag key={event}>{event}</Tag>)}
            {taskKinds.length === 0 && eventTypes.length === 0 && (
              <>
                <Tag color="blue">task_frame</Tag>
                <Tag color="blue">execution_plan</Tag>
                <Tag>task_runtime</Tag>
                <Tag>task_evaluation</Tag>
              </>
            )}
          </Space>
        </div>

        {loading ? (
           <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : (
           <Steps
             direction="vertical"
             size="small"
             current={activeStep}
              items={nodes.map((node, index) => {
                const nodeName = node.id;
                const isCompleted = completedNodes.includes(nodeName);
                const isError = errorNodes.includes(nodeName);
                const isActive = index === activeStep && isStreaming;
                
                // 获取具体的错误信息
                const errorEvent = nodeEvents.find(e => e.node === nodeName && e.event === 'end' && e.payload?.status === 'error');
                const errorMessage = errorEvent?.payload?.message;
                
                return {
                  title: (
                      <span style={{ 
                        fontWeight: isActive ? 600 : 400, 
                        color: isError ? '#ff4d4f' : (isActive ? '#1890ff' : 'inherit') 
                      }}>
                          {node.icon} {node.label}
                      </span>
                  ),
                  description: (
                      <div style={{ fontSize: 12, marginTop: 4, opacity: (isActive || isCompleted || isError) ? 1 : 0.5 }}>
                          {node.description}
                          {isActive && (
                              <div style={{ marginTop: 8, color: '#1890ff', display: 'flex', alignItems: 'center', gap: 6 }}>
                                  <SyncOutlined spin /> <Text style={{ fontSize: 11, color: '#1890ff' }}>Executing Node...</Text>
                              </div>
                          )}
                          {isError && (
                              <div style={{ marginTop: 8, color: '#ff4d4f', fontSize: 11 }}>
                                  <Tooltip title={errorMessage}>
                                      <span>⚠️ 执行异常: {errorMessage?.substring(0, 20)}...</span>
                                  </Tooltip>
                              </div>
                          )}
                          {isCompleted && !isError && index === activeStep && !isStreaming && (
                              <div style={{ marginTop: 4 }}>
                                  <Tag color="green" bordered={false} style={{ fontSize: 10 }}>Completed</Tag>
                              </div>
                          )}
                      </div>
                  ),
                  icon: isActive ? <SyncOutlined spin style={{ color: '#1890ff' }} /> : 
                        (isError ? <CheckCircleOutlined style={{ color: '#ff4d4f' }} /> : 
                        (isCompleted ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : undefined))
                };
              })}
           />
        )}

        <Divider style={{ margin: '18px 0 12px' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <Space size={6}>
            <ClockCircleOutlined style={{ color: '#1677ff' }} />
            <Text strong style={{ fontSize: 13 }}>运行时间线</Text>
          </Space>
          <Tag>{timelineEvents.length}</Tag>
        </div>
        {timelineEvents.length === 0 ? (
          <div style={{ border: '1px dashed #d9d9d9', borderRadius: 8, padding: 12, color: '#8c8c8c', fontSize: 12 }}>
            本轮还没有运行事件。
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 8 }}>
            {timelineEvents.slice(-18).map((event, index) => {
              const summary = summarizeRuntimeEvent(event);
              const isNode = event.type === 'node_event';
              const nodePayload = event.payload || {};
              const nodeTitle = isNode ? `${nodePayload.node || 'node'} ${nodePayload.event || ''}` : summary.title;
              const nodeStatus = isNode ? nodePayload.payload?.status || nodePayload.event : summary.status;
              const nodeDetail = isNode ? nodePayload.payload?.message || '' : summary.detail;
              return (
                <div key={`${event.type}-${event.timestamp}-${index}`} style={{
                  border: '1px solid #eef2f7',
                  borderRadius: 8,
                  padding: '8px 9px',
                  background: '#fff',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <Text strong style={{ fontSize: 12 }}>{nodeTitle}</Text>
                    <Text type="secondary" style={{ fontSize: 11 }}>{compactTime(event.timestamp)}</Text>
                  </div>
                  <Space size={[4, 4]} wrap style={{ marginTop: 5 }}>
                    <Tag color={isNode ? 'geekblue' : 'blue'}>{eventLabelMap[event.type] || event.type}</Tag>
                    {nodeStatus && <Tag color={statusColor(nodeStatus)}>{nodeStatus}</Tag>}
                  </Space>
                  {nodeDetail && (
                    <div style={{ marginTop: 5, color: '#64748b', fontSize: 12, lineHeight: 1.5, wordBreak: 'break-word' }}>
                      {nodeDetail}
                    </div>
                  )}
                </div>
              );
            })}
            {timelineEvents.length > 18 && (
              <Button size="small" disabled>
                仅显示最近 18 条
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Status Bar */}
      <div style={{
          padding: '12px 20px',
          background: isStreaming ? '#e6f7ff' : '#f6ffed',
          borderTop: `1px solid ${isStreaming ? '#91d5ff' : '#b7eb8f'}`,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
      }}>
          <Text style={{ fontSize: 12, color: isStreaming ? '#1890ff' : '#52c41a' }}>
             {isStreaming ? '图流式执行中...' : '图执行完毕'}
          </Text>
          <ThunderboltOutlined style={{ color: isStreaming ? '#1890ff' : '#52c41a' }} />
      </div>

      <style>{`
          @keyframes slideInRight {
              from { transform: translateX(100%); opacity: 0; }
              to { transform: translateX(0); opacity: 1; }
          }
          .hover-blue:hover { color: #1890ff !important; }
      `}</style>
    </Card>
  );
};

export default GraphTracePanel;
