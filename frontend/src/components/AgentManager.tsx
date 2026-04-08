import React, { useState, useEffect } from 'react';
import {
  Typography, Button, List, Card, Avatar, Switch, Modal,
  Input, Select, Checkbox, Tag, Space, Empty, Form, message, Tabs
} from 'antd';
import { PlusOutlined, RobotOutlined, SettingOutlined, DeleteOutlined, InfoCircleOutlined, NodeIndexOutlined } from '@ant-design/icons';
import axios from 'axios';
import type { Agent } from './ChatView';
import AgentTopologyGraph from './AgentTopologyGraph';

const { Title, Text, Paragraph } = Typography;

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

const AgentManager: React.FC<AgentManagerProps> = ({ agents, setAgents, modelConfigs, msgApi, onRefresh }) => {
  const [form] = Form.useForm();
  
  // 核心修复：定义一个可靠的通知函数
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
    fetchTools();
  }, []);

  const fetchTools = async () => {
    try {
      const res = await axios.get('/api/v1/registry/actions');
      setRegisteredTools(res.data);
    } catch {
      // 工具注册表可能为空
    }
  };

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
      form.setFieldsValue({ is_public: false });
    }
    setModalVisible(true);
  };

  const handleSubmit = async (values: any) => {
    console.log('AgentManager submitting values:', values);
    try {
      // 预处理 values，确保模型 ID 是数字
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
      console.error('Agent save error:', err);
      // 如果后端报错，notify 将显示详细的 500 错误信息（已在后端捕获）
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
      setAgents(prev => prev.map(a => a.id === agent.id ? { ...a, is_active: checked } : a));
      notify.success(`${agent.name} 已${checked ? '上线' : '下线'}`);
    } catch {
      notify.error('状态更新失败');
    }
  };

  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '24px' }}>
        <Title level={3} style={{ margin: 0 }}>专家集群管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>
          新增专家
        </Button>
      </div>

      <AgentTopologyGraph agents={agents} onClickNode={openEditor} />

      {agents.length === 0 ? (
        <Empty description="暂无专家，点击上方按钮创建" />
      ) : (
        <List
          grid={{ gutter: 16, xs: 1, sm: 2, md: 3, lg: 3, xl: 4 }}
          dataSource={agents}
          renderItem={a => (
            <List.Item>
              <Card
                hoverable
                actions={[
                  <SettingOutlined key="edit" onClick={() => openEditor(a)} />,
                  <DeleteOutlined key="delete" onClick={() => handleDelete(a)} style={{ color: '#ff4d4f' }} />,
                  <Switch key="status" size="small" checked={a.is_active} onChange={c => toggleStatus(a, c)} />
                ]}
                style={{ opacity: a.is_active ? 1 : 0.6 }}
              >
                <Card.Meta
                  avatar={<Avatar icon={<RobotOutlined />} style={{ backgroundColor: a.is_active ? '#1890ff' : '#ccc' }} />}
                  title={
                    <Space>
                      <Text strong>{a.name}</Text>
                      {a.is_public && <Tag color="gold" style={{ fontSize: '10px' }}>🛡️ 全域专家</Tag>}
                    </Space>
                  }
                  description={
                    <div>
                      <Text type="secondary" ellipsis={{ tooltip: true }} style={{ display: 'block', fontSize: '12px' }}>
                        {a.description || '无描述'}
                      </Text>
                      <div style={{ marginTop: 8 }}>
                        {(a.tools || []).map(t => (
                          <Tag key={t} style={{ fontSize: '10px', marginBottom: 2 }}>{t}</Tag>
                        ))}
                        {(!a.tools || a.tools.length === 0) && (
                          <Text type="secondary" style={{ fontSize: '11px' }}>无工具</Text>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
                        <div style={{
                          width: 8, height: 8, borderRadius: '50%',
                          background: a.is_active ? '#52c41a' : '#bfbfbf',
                          boxShadow: a.is_active ? '0 0 6px rgba(82,196,26,0.4)' : 'none'
                        }} />
                        <Text type="secondary" style={{ fontSize: '11px' }}>
                          {a.is_active ? '在线' : '离线'}
                        </Text>
                      </div>
                    </div>
                  }
                />
              </Card>
            </List.Item>
          )}
        />
      )}

      {/* Agent Editor Modal */}
      <Modal
        title={editingAgent ? `编辑专家: ${editingAgent.name}` : '创建新专家'}
        open={modalVisible}
        onOk={() => form.submit()}
        onCancel={() => setModalVisible(false)}
        okText={editingAgent ? '保存' : '创建'}
        cancelText="取消"
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ tools: [] }}>
          <Tabs defaultActiveKey="1" items={[
            {
              key: '1',
              label: <span><SettingOutlined /> 基础配置</span>,
              children: (
                <div style={{ paddingTop: 8 }}>
                  <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
                    <Input placeholder="e.g. 法律顾问" />
                  </Form.Item>

                  <Form.Item name="description" label="角色描述">
                    <Input.TextArea placeholder="简短描述该专家的职责..." rows={2} />
                  </Form.Item>

                  <Form.Item name="model_config_id" label="核心大脑 (LLM Base)" rules={[{ required: true, message: '请选择模型' }]}>
                    <Select 
                      placeholder="请通过搜索或分类选择专家的大脑..." 
                      showSearch 
                      optionLabelProp="label"
                      defaultValue={undefined}
                      listHeight={400}
                      dropdownStyle={{ borderRadius: 8, padding: 8 }}
                      filterOption={(input, option: any) =>
                        String(option?.search ?? '').toLowerCase().includes(input.toLowerCase())
                      }
                    >
                      {(() => {
                        // 定义核心大脑白名单分组 (仅保留具备生成能力的模型)
                        const typeMap: Record<string, { icon: string, label: string, color: string }> = {
                           'chat': { icon: '💬', label: '通用对话', color: '#1890ff' },
                           'vision': { icon: '👁️', label: '视觉理解', color: '#722ed1' },
                           'reasoning': { icon: '🧠', label: '逻辑推理', color: '#eb2f96' }
                        };

                        // 增强后的前端语义识别与分组
                        const grouped: Record<string, any[]> = {};
                        modelConfigs.forEach(p => {
                            (p.models || []).forEach((m: any) => {
                                let t = m.model_type === 'llm' ? 'chat' : m.model_type;
                                const lowerName = m.model_name.toLowerCase();
                                
                                // 智能降级/语义辨识：即使 DB 数据陈旧，前端也能正确分类
                                if (lowerName.includes('vl') || lowerName.includes('vision')) t = 'vision';
                                else if (lowerName.includes('-r1') || lowerName.includes('reasoner') || lowerName.startsWith('o1') || lowerName.startsWith('o3')) t = 'reasoning';
                                
                                if (!grouped[t]) grouped[t] = [];
                                grouped[t].push({ ...m, provider_name: p.display_name });
                            });
                        });

                        return Object.entries(typeMap).map(([type, meta]) => {
                            const models = grouped[type] || [];
                            if (models.length === 0) return null;
                            return (
                                <Select.OptGroup key={type} label={<span>{meta.icon} {meta.label}</span>}>
                                    {models.map(m => (
                                        <Select.Option 
                                            key={m.id} 
                                            value={m.id}
                                            label={`${meta.icon} ${m.model_name}`}
                                            search={`${m.model_name} ${m.provider_name}`}
                                        >
                                            <div style={{ display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
                                                <Space size={4}>
                                                    <span style={{ fontSize: '13px' }}>{m.model_name}</span>
                                                    <span style={{ fontSize: '11px', color: '#bfbfbf' }}>({m.provider_name})</span>
                                                </Space>
                                                <Text type="secondary" style={{ fontSize: '10px' }}>
                                                    {m.context_length >= 1024 ? `${Math.round(m.context_length/1024)}K` : m.context_length}
                                                </Text>
                                            </div>
                                        </Select.Option>
                                    ))}
                                </Select.OptGroup>
                            );
                        });
                      })()}
                    </Select>
                  </Form.Item>

                  <Form.Item name="is_public" label="全域专家权限" valuePropName="checked">
                    <Switch checkedChildren="全域公开" unCheckedChildren="私有" />
                  </Form.Item>

                  <Form.Item name="system_prompt" label="系统指令 (System Prompt)">
                    <Input.TextArea placeholder="定义专家的行为准则、专业背景与回复风格..." rows={4} />
                  </Form.Item>

                  <Form.Item name="tools" label="工具装备">
                    {registeredTools.length > 0 ? (
                      <Checkbox.Group style={{ width: '100%' }}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                          {registeredTools.map(t => (
                            <Checkbox key={t.name} value={t.name}>
                              <Text strong>{t.label}</Text>
                              <Text type="secondary" style={{ marginLeft: 8, fontSize: '12px' }}>{t.description}</Text>
                            </Checkbox>
                          ))}
                        </Space>
                      </Checkbox.Group>
                    ) : (
                      <Paragraph type="secondary">
                        内核暂无已注册工具。请在 backend/app/tools/ 中添加工具实现。
                      </Paragraph>
                    )}
                  </Form.Item>
                </div>
              )
            },
            {
              key: '2',
              label: <span><NodeIndexOutlined /> 图路由配置</span>,
              children: (
                <div style={{ padding: '24px 0', minHeight: 300, display: 'flex', flexDirection: 'column', gap: 16 }}>
                   <div style={{ padding: 16, background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 8 }}>
                       <Space align="start">
                           <InfoCircleOutlined style={{ color: '#52c41a', marginTop: 4 }} />
                           <div>
                               <Text strong style={{ display: 'block' }}>基于 LangGraph 的意图路由</Text>
                               <Text type="secondary" style={{ fontSize: 13 }}>由于该专家受信任度较高，主控节点(Orchestrator) 将在检测到特定意图时，沿图中 <b>Handoff 条件边</b> 自动放弃控制权并唤醒此专家。</Text>
                           </div>
                       </Space>
                   </div>
                   
                   <Form.Item label="前置路由意图 (Routing Intent)" extra="主控节点检测到以下意图时，将自动移交通信信道。">
                       <Select 
                           mode="tags" 
                           placeholder="输入意图关键词，如: '搜索', '股票', '查询数据库' 回车确认"
                           defaultValue={[]} 
                       />
                   </Form.Item>

                   <Form.Item label="图节点衔接策略 (Edge Action)">
                       <Select defaultValue="return">
                           <Select.Option value="return">执行完毕后主动归还控制权 (推荐)</Select.Option>
                           <Select.Option value="end">执行完毕后直接结束当前回合 (END Node)</Select.Option>
                           <Select.Option value="pass">将上下文顺延给下一个关联专家 (暂不开放)</Select.Option>
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
