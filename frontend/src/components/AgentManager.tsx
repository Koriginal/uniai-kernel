import React, { useState, useEffect } from 'react';
import {
  Typography, Button, List, Card, Avatar, Switch, Modal,
  Input, Select, Checkbox, Tag, Space, Empty, Form, message, Tabs
} from 'antd';
import { 
  PlusOutlined, RobotOutlined, SettingOutlined, DeleteOutlined, 
  InfoCircleOutlined, NodeIndexOutlined, SyncOutlined 
} from '@ant-design/icons';
import axios from 'axios';
import type { Agent } from './ChatView';
import AgentTopologyGraph from './AgentTopologyGraph';

const { Title, Text } = Typography;

interface ActionMeta {
  name: string;
  label: string;
  description: string;
  category: string;
}

interface AgentManagerProps {
  agents: Agent[];
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
  modelConfigs: any[];
  msgApi: any;
  onRefresh: () => void;
}

// 子组件：Agent 卡片，包含实时统计数据
const AgentCard: React.FC<{ 
  agent: Agent, 
  onEdit: () => void, 
  onDelete: () => void, 
  onToggle: (c: boolean) => void 
}> = ({ agent, onEdit, onDelete, onToggle }) => {
  const [stats, setStats] = useState<any>(null);
  const [loadingStats, setLoadingStats] = useState(false);

  useEffect(() => {
    const fetchStats = async () => {
      setLoadingStats(true);
      try {
        const res = await axios.get(`/api/v1/agents/${agent.id}/stats`);
        setStats(res.data);
      } catch (err) {
        console.error("Failed to fetch stats for agent:", agent.id, err);
      } finally {
        setLoadingStats(false);
      }
    };
    if (agent.id) {
      fetchStats();
    }
  }, [agent.id]);

  return (
    <Card
      hoverable
      actions={[
        <SettingOutlined key="edit" onClick={onEdit} />,
        <DeleteOutlined key="delete" onClick={onDelete} style={{ color: '#ff4d4f' }} />,
        <Switch key="status" size="small" checked={agent.is_active} onChange={onToggle} />
      ]}
      style={{ opacity: agent.is_active ? 1 : 0.6, height: '100%', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{ flex: 1 }}
    >
      <Card.Meta
        avatar={<Avatar icon={<RobotOutlined />} style={{ backgroundColor: agent.is_active ? '#1890ff' : '#ccc' }} />}
        title={
          <Space>
            <Text strong>{agent.name}</Text>
            {agent.is_public && <Tag color="gold" style={{ fontSize: '10px' }}>🛡️ 全域</Tag>}
          </Space>
        }
        description={
          <div>
            <Text type="secondary" ellipsis={{ tooltip: true }} style={{ display: 'block', fontSize: '12px', marginBottom: 8 }}>
              {agent.description || '无描述'}
            </Text>
            
            {/* 实时评分统计 */}
            {stats && stats.total_calls > 0 ? (
                <div style={{ marginTop: 8, padding: '8px', background: '#fafafa', borderRadius: 4, display: 'flex', gap: 12, justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <Text type="secondary" style={{ fontSize: 10 }}>调用次数</Text>
                        <Text strong style={{ fontSize: 12 }}>{stats.total_calls}</Text>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <Text type="secondary" style={{ fontSize: 10 }}>成功率</Text>
                        <Text strong style={{ fontSize: 12, color: stats.success_rate > 0.8 ? '#52c41a' : '#faad14' }}>
                            {(stats.success_rate * 100).toFixed(1)}%
                        </Text>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                        <Text type="secondary" style={{ fontSize: 10 }}>Avg Latency</Text>
                        <Text strong style={{ fontSize: 12 }}>
                            {stats.avg_duration_ms < 1000 ? `${Math.round(stats.avg_duration_ms)}ms` : `${(stats.avg_duration_ms/1000).toFixed(1)}s`}
                        </Text>
                    </div>
                </div>
            ) : (
                loadingStats ? <SyncOutlined spin style={{ fontSize: 12, color: '#bfbfbf', marginTop: 8 }} /> : null
            )}

            <div style={{ marginTop: 12 }}>
              {(agent.tools || []).slice(0, 3).map(t => (
                <Tag key={t} style={{ fontSize: '10px', marginBottom: 2 }}>{t}</Tag>
              ))}
              {(agent.tools || []).length > 3 && <Text type="secondary" style={{ fontSize: 10 }}>...</Text>}
            </div>
          </div>
        }
      />
    </Card>
  );
};

// 主组件：Agent 管理器
const AgentManager: React.FC<AgentManagerProps> = ({ agents, setAgents, modelConfigs, msgApi, onRefresh }) => {
  const [form] = Form.useForm();
  
  const notify = {
    success: (content: string) => {
      if (msgApi?.success) msgApi.success(content);
      else message.success(content);
    },
    error: (content: string) => {
      if (msgApi?.error) msgApi.error(content);
      else message.error(content);
    }
  };

  const [modalVisible, setModalVisible] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [registeredTools, setRegisteredTools] = useState<ActionMeta[]>([]);

  useEffect(() => {
    const fetchTools = async () => {
      try {
        const res = await axios.get('/api/v1/registry/actions');
        setRegisteredTools(res.data);
      } catch (err) {
        console.warn("Tools registry is empty or unavailable");
      }
    };
    fetchTools();
  }, []);

  const openEditor = (agent?: Agent) => {
    if (agent) {
      setEditingAgent(agent);
      form.setFieldsValue({
        name: agent.name,
        description: agent.description,
        model_config_id: agent.model_config_id ? Number(agent.model_config_id) : undefined,
        system_prompt: agent.system_prompt,
        tools: agent.tools || [],
        is_public: agent.is_public
      });
    } else {
      setEditingAgent(null);
      form.resetFields();
      form.setFieldsValue({ is_public: false, tools: [] });
    }
    setModalVisible(true);
  };

  const handleSubmit = async (values: any) => {
    try {
      const payload = {
        ...values,
        model_config_id: Number(values.model_config_id)
      };

      if (editingAgent) {
        await axios.put(`/api/v1/agents/${editingAgent.id}`, payload);
        notify.success(`${values.name} 已更新`);
      } else {
        await axios.post('/api/v1/agents/', payload);
        notify.success(`${values.name} 已创建`);
      }
      setModalVisible(false);
      onRefresh();
    } catch (err: any) {
      const detail = err.response?.data?.detail || '操作失败';
      notify.error(detail);
    }
  };

  const handleDelete = async (agent: Agent) => {
    Modal.confirm({
      title: `确认删除 ${agent.name}？`,
      content: '此操作不可恢复。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await axios.delete(`/api/v1/agents/${agent.id}`);
          notify.success(`${agent.name} 已删除`);
          onRefresh();
        } catch {
          notify.error('删除失败');
        }
      }
    });
  };

  const toggleStatus = async (agent: Agent, checked: boolean) => {
    try {
      await axios.put(`/api/v1/agents/${agent.id}`, { is_active: checked });
      // 乐观更新
      setAgents(prev => prev.map(a => a.id === agent.id ? { ...a, is_active: checked } : a));
      notify.success(`${agent.name} 已${checked ? '上线' : '下线'}`);
    } catch {
      notify.error('状态更新失败');
    }
  };

  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%', background: '#fff' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '24px', alignItems: 'center' }}>
        <Space>
          <RobotOutlined style={{ fontSize: 24, color: '#1890ff' }} />
          <Title level={3} style={{ margin: 0 }}>专家集群管理</Title>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()} size="large">
          新增专家
        </Button>
      </div>

      <AgentTopologyGraph agents={agents} onClickNode={openEditor} />

      {agents.length === 0 ? (
        <Empty description="暂无专家，点击右上角按钮创建" style={{ marginTop: 40 }} />
      ) : (
        <List
          grid={{ gutter: 20, xs: 1, sm: 2, md: 3, lg: 3, xl: 4 }}
          dataSource={agents}
          renderItem={a => (
            <List.Item>
              <AgentCard 
                agent={a} 
                onEdit={() => openEditor(a)} 
                onDelete={() => handleDelete(a)} 
                onToggle={c => toggleStatus(a, c)} 
              />
            </List.Item>
          )}
          style={{ marginTop: 24 }}
        />
      )}

      {/* Agent Editor Modal */}
      <Modal
        title={editingAgent ? `编辑专家: ${editingAgent.name}` : '创建新专家'}
        open={modalVisible}
        onOk={() => form.submit()}
        onCancel={() => setModalVisible(false)}
        width={720}
        destroyOnClose
        bodyStyle={{ paddingTop: 16 }}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Tabs defaultActiveKey="1" items={[
            {
              key: '1',
              label: <span><SettingOutlined /> 基础配置</span>,
              children: (
                <div style={{ minHeight: 400 }}>
                  <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
                    <Input placeholder="e.g. 法律顾问" />
                  </Form.Item>

                  <Form.Item name="description" label="角色描述">
                    <Input.TextArea placeholder="简短描述该专家的职责..." rows={2} />
                  </Form.Item>

                  <Form.Item name="model_config_id" label="核心大脑 (LLM Base)" rules={[{ required: true, message: '请选择模型' }]}>
                    <Select 
                      placeholder="请选择专家的大脑..." 
                      showSearch 
                      optionLabelProp="label"
                    >
                        {(() => {
                            const typeMap: Record<string, string> = { 'chat': '💬 通用', 'vision': '👁️ 视觉', 'reasoning': '🧠 推理' };
                            const grouped: Record<string, any[]> = {};
                            modelConfigs.forEach(p => {
                                (p.models || []).forEach((m: any) => {
                                    let t = m.model_type === 'llm' ? 'chat' : m.model_type;
                                    const n = m.model_name.toLowerCase();
                                    if (n.includes('vl') || n.includes('vision')) t = 'vision';
                                    else if (n.includes('-r1') || n.includes('reasoner')) t = 'reasoning';
                                    if (!grouped[t]) grouped[t] = [];
                                    grouped[t].push({ ...m, provider: p.display_name });
                                });
                            });
                            return Object.entries(typeMap).map(([t, label]) => (
                                <Select.OptGroup key={t} label={label}>
                                    {(grouped[t] || []).map(m => (
                                        <Select.Option key={m.id} value={m.id} label={m.model_name}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                <span>{m.model_name} <small style={{ color: '#ccc' }}>({m.provider})</small></span>
                                            </div>
                                        </Select.Option>
                                    ))}
                                </Select.OptGroup>
                            ));
                        })()}
                    </Select>
                  </Form.Item>

                  <Form.Item name="is_public" label="全域公开" valuePropName="checked">
                    <Switch checkedChildren="公开" unCheckedChildren="私有" />
                  </Form.Item>

                  <Form.Item name="system_prompt" label="系统指令">
                    <Input.TextArea placeholder="定义专家的行为注入..." rows={6} />
                  </Form.Item>

                  <Form.Item name="tools" label="工具装备">
                    <Checkbox.Group style={{ width: '100%' }}>
                      <Space direction="vertical" style={{ width: '100%' }}>
                        {registeredTools.map(t => (
                          <Checkbox key={t.name} value={t.name}>
                            <Text strong>{t.label}</Text> <Text type="secondary" style={{ fontSize: 12 }}>- {t.description}</Text>
                          </Checkbox>
                        ))}
                      </Space>
                    </Checkbox.Group>
                  </Form.Item>
                </div>
              )
            },
            {
              key: '2',
              label: <span><NodeIndexOutlined /> 图路由配置</span>,
              children: (
                <div style={{ padding: '8px 0', minHeight: 400 }}>
                   <div style={{ padding: 16, background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 8, marginBottom: 24 }}>
                       基于 LangGraph 的自动路由。触发后专家将接管会话，执行完毕后自动归还控制权。
                   </div>
                   <Form.Item label="前置意图关键词 (Routing Keywords)" extra="多个关键词请用回车分隔">
                       <Select mode="tags" placeholder="输入关键词，如: 法律, 合同, 纠纷" />
                   </Form.Item>
                   <Form.Item label="接管策略">
                       <Select defaultValue="return">
                           <Select.Option value="return">执行完毕后主动归还控制权 (推荐)</Select.Option>
                           <Select.Option value="end">执行完毕后直接结束回合</Select.Option>
                       </Select>
                   </Form.Item>
                </div>
              )
            }
          ]} />
        </Form>
      </Modal>
    </div>
  );
};

export default AgentManager;
