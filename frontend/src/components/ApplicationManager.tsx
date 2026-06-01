import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Drawer, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { AppstoreAddOutlined, EyeOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import axios from 'axios';
import type { Agent } from './ChatView';

const { Text, Title } = Typography;

export interface AgentApplication {
  id: string;
  name: string;
  description?: string;
  business_domain?: string;
  scenario_type: string;
  primary_agent_id?: string;
  runtime_provider_names: string[];
  tool_names: string[];
  ontology_space_id?: string;
  runtime_policy: Record<string, unknown>;
  acceptance_policy: Record<string, unknown>;
  status: string;
}

interface Props {
  applications: AgentApplication[];
  agents: Agent[];
  onRefresh: () => void;
  onSelectApplication: (application: AgentApplication) => void;
}

const scenarioOptions = [
  { label: '风控审核', value: 'risk_review' },
  { label: '合同审查', value: 'contract_review' },
  { label: '客户支持', value: 'customer_support' },
  { label: '研究流程', value: 'research_workflow' },
  { label: '自定义', value: 'custom' },
];

const statusOptions = [
  { label: '启用', value: 'active' },
  { label: '暂停', value: 'paused' },
  { label: '归档', value: 'archived' },
];

const ApplicationManager: React.FC<Props> = ({ applications, agents, onRefresh, onSelectApplication }) => {
  const [form] = Form.useForm();
  const [editing, setEditing] = useState<AgentApplication | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [actions, setActions] = useState<any[]>([]);
  const [providers, setProviders] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const loadAssets = async () => {
      try {
        const [actionsRes, capabilitiesRes] = await Promise.all([
          axios.get('/api/v1/registry/actions'),
          axios.get('/api/v1/graph/runtime/capabilities'),
        ]);
        setActions(actionsRes.data || []);
        setProviders(capabilitiesRes.data?.providers || []);
      } catch {
        setActions([]);
        setProviders([]);
      }
    };
    loadAssets();
  }, []);

  const agentOptions = useMemo(() => agents.map((agent) => ({ label: agent.name, value: agent.id })), [agents]);
  const toolOptions = useMemo(() => actions.map((item) => ({ label: item.label ? `${item.label} (${item.name})` : item.name, value: item.name })), [actions]);
  const providerOptions = useMemo(() => providers.map((item) => ({ label: `${item.name} · ${item.task_kinds?.join(', ') || 'runtime'}`, value: item.name })), [providers]);

  const openEditor = (application?: AgentApplication) => {
    setEditing(application || null);
    form.setFieldsValue(application || {
      scenario_type: 'custom',
      status: 'active',
      runtime_provider_names: [],
      tool_names: [],
      runtime_policy: '{}',
      acceptance_policy: '{}',
    });
    if (application) {
      form.setFieldsValue({
        ...application,
        runtime_policy: JSON.stringify(application.runtime_policy || {}, null, 2),
        acceptance_policy: JSON.stringify(application.acceptance_policy || {}, null, 2),
      });
    }
    setDrawerOpen(true);
  };

  const saveApplication = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const payload = {
        ...values,
        runtime_policy: values.runtime_policy ? JSON.parse(values.runtime_policy) : {},
        acceptance_policy: values.acceptance_policy ? JSON.parse(values.acceptance_policy) : {},
      };
      if (editing) {
        await axios.patch(`/api/v1/applications/${editing.id}`, payload);
      } else {
        await axios.post('/api/v1/applications/', payload);
      }
      message.success(editing ? '业务应用已更新' : '业务应用已创建');
      setDrawerOpen(false);
      onRefresh();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const showContract = async (application: AgentApplication) => {
    try {
      const res = await axios.get(`/api/v1/applications/${application.id}/runtime-contract`);
      Modal.info({
        title: `${application.name} · Runtime Contract`,
        width: 760,
        content: (
          <pre style={{ maxHeight: '60vh', overflow: 'auto', whiteSpace: 'pre-wrap', background: '#f8fafc', border: '1px solid #e5e7eb', padding: 12, borderRadius: 8 }}>
            {JSON.stringify(res.data, null, 2)}
          </pre>
        ),
      });
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '读取 runtime contract 失败');
    }
  };

  return (
    <div style={{ padding: 20, height: '100%', overflow: 'auto', background: '#f6f8fb' }}>
      <Card style={{ borderRadius: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 16 }}>
          <Space>
            <AppstoreAddOutlined style={{ color: '#1677ff' }} />
            <div>
              <Title level={4} style={{ margin: 0 }}>业务智能体应用</Title>
              <Text type="secondary">把业务场景、主控 Agent、工具、本体和运行时策略收拢成可运行入口。</Text>
            </div>
          </Space>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>新建应用</Button>
          </Space>
        </div>
        <Table
          rowKey="id"
          dataSource={applications}
          pagination={{ pageSize: 8 }}
          columns={[
            {
              title: '应用',
              dataIndex: 'name',
              render: (_: string, item: AgentApplication) => (
                <Space direction="vertical" size={2}>
                  <Text strong>{item.name}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>{item.description || item.business_domain || '-'}</Text>
                </Space>
              ),
            },
            { title: '场景', dataIndex: 'scenario_type', width: 140, render: (value: string) => <Tag color="blue">{value}</Tag> },
            { title: '主控', dataIndex: 'primary_agent_id', width: 180, render: (id: string) => agents.find((agent) => agent.id === id)?.name || id || '-' },
            { title: '工具', dataIndex: 'tool_names', width: 120, render: (items: string[]) => (items?.length ? <Tag color="purple">{items.length}</Tag> : <Tag>继承 Agent</Tag>) },
            { title: 'Provider', dataIndex: 'runtime_provider_names', width: 130, render: (items: string[]) => (items?.length ? <Tag color="geekblue">{items.length}</Tag> : <Tag>default</Tag>) },
            { title: '状态', dataIndex: 'status', width: 100, render: (status: string) => <Tag color={status === 'active' ? 'green' : 'default'}>{status}</Tag> },
            {
              title: '操作',
              width: 230,
              render: (_: unknown, item: AgentApplication) => (
                <Space>
                  <Button size="small" onClick={() => onSelectApplication(item)}>进入对话</Button>
                  <Button size="small" onClick={() => openEditor(item)}>编辑</Button>
                  <Button size="small" icon={<EyeOutlined />} onClick={() => showContract(item)}>Contract</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Drawer title={editing ? '编辑业务应用' : '新建业务应用'} open={drawerOpen} onClose={() => setDrawerOpen(false)} width={560}
        extra={<Button type="primary" loading={saving} onClick={saveApplication}>保存</Button>}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="应用名称" rules={[{ required: true, message: '请输入应用名称' }]}>
            <Input placeholder="例如：授信风控审核应用" />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={3} placeholder="说明这个应用处理的业务、输入和输出。" />
          </Form.Item>
          <Form.Item name="business_domain" label="业务域">
            <Input placeholder="risk / legal / support / research" />
          </Form.Item>
          <Form.Item name="scenario_type" label="场景类型" rules={[{ required: true }]}>
            <Select options={scenarioOptions} />
          </Form.Item>
          <Form.Item name="primary_agent_id" label="主控 Agent">
            <Select allowClear showSearch options={agentOptions} optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="runtime_provider_names" label="Runtime Provider">
            <Select mode="multiple" allowClear options={providerOptions} placeholder="留空使用 default_task_runtime" />
          </Form.Item>
          <Form.Item name="tool_names" label="应用工具白名单">
            <Select mode="multiple" allowClear options={toolOptions} optionFilterProp="label" placeholder="留空继承 Agent 工具配置" />
          </Form.Item>
          <Form.Item name="ontology_space_id" label="本体空间 ID">
            <Input placeholder="可选：绑定一个本体空间" />
          </Form.Item>
          <Form.Item name="runtime_policy" label="运行策略 JSON">
            <Input.TextArea rows={5} />
          </Form.Item>
          <Form.Item name="acceptance_policy" label="验收策略 JSON">
            <Input.TextArea rows={5} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={statusOptions} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default ApplicationManager;
