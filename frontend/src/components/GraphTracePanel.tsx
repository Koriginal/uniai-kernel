import React, { useEffect, useState } from 'react';
import { Card, Typography, Steps, Tag, Space, Spin, Tooltip } from 'antd';
import { 
  ThunderboltOutlined, CheckCircleOutlined, SyncOutlined, 
  LeftCircleOutlined, RightCircleOutlined, NodeIndexOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;

interface GraphTracePanelProps {
  visible: boolean;
  onClose: () => void;
  currentAgentName?: string;
  isStreaming: boolean;
}

const GraphTracePanel: React.FC<GraphTracePanelProps> = ({ visible, onClose, currentAgentName, isStreaming }) => {
  const [nodes, setNodes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // 模拟节点执行状态的推进
  // 实际生产环境中，这应该通过后端的 SSE 事件增量更新
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    if (visible) {
      fetchNodes();
    }
  }, [visible]);

  useEffect(() => {
    if (visible && isStreaming) {
       // 模拟流式推进
       const timer = setInterval(() => {
          setActiveStep(prev => {
              if (prev < 4) return prev + 1;
              return prev;
          });
       }, 800);
       return () => clearInterval(timer);
    } else if (visible && !isStreaming) {
        setActiveStep(5); // 完成状态
    }
  }, [visible, isStreaming]);

  const fetchNodes = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/v1/graph/nodes');
      setNodes(res.data.nodes || []);
    } catch {
      // fallback
      setNodes([
          { id: 'context', label: '上下文构建', description: '加载记忆与 System Prompt', icon: '📥' },
          { id: 'agent', label: 'LLM 推理', description: '调用核心模型思考', icon: '🤖' },
          { id: 'tool_executor', label: '工具执行', description: '执行并行工具', icon: '🔧' },
          { id: 'handoff', label: '专家路由', description: '移交控制权', icon: '🤝' },
          { id: 'synthesize', label: '汇总归还', description: '收尾与回调', icon: '📝' }
      ]);
    } finally {
      setLoading(false);
    }
  };

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

        {loading ? (
           <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : (
           <Steps
             direction="vertical"
             size="small"
             current={activeStep}
             items={nodes.map((node, index) => {
               const isActive = index === activeStep && isStreaming;
               const isDone = index < activeStep || (!isStreaming && activeStep > 0);
               
               return {
                 title: (
                     <span style={{ fontWeight: isActive ? 600 : 400, color: isActive ? '#1890ff' : 'inherit' }}>
                         {node.icon} {node.label}
                     </span>
                 ),
                 description: (
                     <div style={{ fontSize: 12, marginTop: 4, opacity: (isActive || isDone) ? 1 : 0.5 }}>
                         {node.description}
                         {isActive && (
                             <div style={{ marginTop: 8, color: '#1890ff', display: 'flex', alignItems: 'center', gap: 6 }}>
                                 <SyncOutlined spin /> <Text style={{ fontSize: 11, color: '#1890ff' }}>Executing Node...</Text>
                             </div>
                         )}
                         {isDone && index === 1 && (
                             <div style={{ marginTop: 4 }}>
                                 <Tag color="blue" bordered={false} style={{ fontSize: 10 }}>Token ≈ 1.2k</Tag>
                                 <Tag color="green" bordered={false} style={{ fontSize: 10 }}>2.1s</Tag>
                             </div>
                         )}
                     </div>
                 ),
                 icon: isActive ? <SyncOutlined spin style={{ color: '#1890ff' }} /> : (isDone ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : undefined)
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
