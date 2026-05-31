import React, { useEffect, useState } from 'react';
import { Card, Typography, Steps, Tag, Space, Spin, Tooltip } from 'antd';
import { 
  ThunderboltOutlined, CheckCircleOutlined, SyncOutlined, 
  LeftCircleOutlined, NodeIndexOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;

interface GraphTracePanelProps {
  visible: boolean;
  onClose: () => void;
  currentAgentName?: string;
  isStreaming: boolean;
  nodeEvents: any[];
}

const GraphTracePanel: React.FC<GraphTracePanelProps> = ({ visible, onClose, currentAgentName, isStreaming, nodeEvents }) => {
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
