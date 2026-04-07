import React, { useState, useEffect } from 'react';
import {
  Typography, Card, Tag, Empty, Row, Col, Descriptions,
  Collapse, Badge, Button, Spin, Alert, Tabs, Modal, Form, Input, Select, Space, Tooltip
} from 'antd';
import {
  ToolOutlined, CodeOutlined, AppstoreOutlined,
  ThunderboltOutlined, ReloadOutlined, PlusOutlined,
  ApiOutlined, ConsoleSqlOutlined, GlobalOutlined,
  DeleteOutlined, PoweroffOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text, Paragraph } = Typography;
const { Panel } = Collapse;
const { Option } = Select;

interface ToolMeta {
  name: string;
  label: string;
  description: string;
  category: string;
  icon: string | null;
  version: string;
}

interface ToolDetail {
  name: string;
  label: string;
  description: string;
  category: string;
  version: string;
  parameters_schema: any;
  openai_format: any;
}

interface DynamicTool extends ToolMeta {
    id: string;
    tool_type: 'api' | 'mcp' | 'cli';
    config: any;
    parameters_schema: any;
    is_active: boolean;
}

interface KernelStatus {
  actions_count: number;
  actions_by_category: Record<string, number>;
  has_memory_store: boolean;
  has_knowledge_base: boolean;
  registered_actions: string[];
}

interface Scaffold {
  guide: { title: string; steps: string[] };
  template: string;
  base_class: string;
  scan_path: string;
  auto_discovery: boolean;
  registration_method: string;
}

interface ToolRegistryProps {
  msgApi: any;
}

const CATEGORY_COLORS: Record<string, string> = {
  knowledge: 'blue',
  utility: 'green',
  system: 'orange',
  integration: 'purple',
  custom: 'cyan',
  api: 'geekblue',
  mcp: 'magenta',
  cli: 'volcano'
};

const ToolRegistry: React.FC<ToolRegistryProps> = ({ msgApi }) => {
  const [tools, setTools] = useState<ToolMeta[]>([]);
  const [dynamicTools, setDynamicTools] = useState<DynamicTool[]>([]);
  const [toolDetails, setToolDetails] = useState<Record<string, ToolDetail>>({});
  const [kernelStatus, setKernelStatus] = useState<KernelStatus | null>(null);
  const [scaffold, setScaffold] = useState<Scaffold | null>(null);
  const [loading, setLoading] = useState(true);
  
  // Registration State
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [toolType, setToolType] = useState<'api' | 'mcp' | 'cli'>('api');
  const [form] = Form.useForm();

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [toolsRes, dynamicRes, statusRes, scaffoldRes] = await Promise.all([
        axios.get('/api/v1/registry/actions'),
        axios.get('/api/v1/dynamic-tools/'),
        axios.get('/api/v1/registry/status'),
        axios.get('/api/v1/registry/scaffold')
      ]);
      setTools(toolsRes.data);
      setDynamicTools(dynamicRes.data);
      setKernelStatus(statusRes.data);
      setScaffold(scaffoldRes.data);
    } catch {
      msgApi.error('获取工具注册表失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchToolDetail = async (name: string) => {
    if (toolDetails[name]) return;
    try {
      const res = await axios.get(`/api/v1/registry/actions/${name}`);
      setToolDetails(prev => ({ ...prev, [name]: res.data }));
    } catch {
      msgApi.error(`获取 ${name} 详情失败`);
    }
  };

  const handleCreateTool = async (values: any) => {
      try {
          // 构造复杂的 Config 对象
          let config = {};
          if (toolType === 'api') {
              config = { url: values.url, method: values.method || 'POST', headers: JSON.parse(values.headers || '{}') };
          } else if (toolType === 'mcp') {
              config = { command: values.command, args: (values.args || '').split(' ').filter((a: string) => a) };
          } else if (toolType === 'cli') {
              config = { script: values.script };
          }

          const payload = {
              name: values.name,
              label: values.label,
              description: values.description,
              tool_type: toolType,
              category: values.category || 'custom',
              config: config,
              parameters_schema: JSON.parse(values.parameters_schema || '{"type": "object", "properties": {}}')
          };

          await axios.post('/api/v1/dynamic-tools/', payload);
          msgApi.success('工具注册成功');
          setIsModalVisible(false);
          form.resetFields();
          fetchAll();
      } catch (err: any) {
          msgApi.error('注册失败: ' + (err.response?.data?.detail || err.message));
      }
  };

  const handleDeleteDynamic = async (id: string) => {
      try {
          await axios.delete(`/api/v1/dynamic-tools/${id}`);
          msgApi.success('工具已删除');
          fetchAll();
      } catch {
          msgApi.error('删除失败');
      }
  };

  const handleToggleDynamic = async (id: string) => {
      try {
          await axios.post(`/api/v1/dynamic-tools/${id}/toggle`);
          fetchAll();
      } catch {
          msgApi.error('状态切换失败');
      }
  };

  const renderToolCard = (tool: ToolMeta | DynamicTool, isDynamic = false) => {
      const dTool = isDynamic ? (tool as DynamicTool) : null;
      return (
          <Col key={tool.name} xs={24} md={12}>
              <Card
                  hoverable
                  size="small"
                  style={{ height: '100%', opacity: dTool && !dTool.is_active ? 0.6 : 1 }}
                  title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {isDynamic ? (
                          dTool?.tool_type === 'api' ? <GlobalOutlined style={{ color: '#722ed1' }} /> :
                          dTool?.tool_type === 'mcp' ? <AppstoreOutlined style={{ color: '#eb2f96' }} /> :
                          <ConsoleSqlOutlined style={{ color: '#fa8c16' }} />
                      ) : <ThunderboltOutlined style={{ color: '#1890ff' }} />}
                      <Text strong>{tool.label}</Text>
                      <Tag color={CATEGORY_COLORS[tool.category] || (isDynamic ? 'cyan' : 'default')} style={{ fontSize: 10 }}>
                        {tool.category}
                      </Tag>
                      {isDynamic && <Tag color="blue" style={{ fontSize: 10 }}>{dTool?.tool_type.toUpperCase()}</Tag>}
                      <Text type="secondary" style={{ fontSize: 10, marginLeft: 'auto' }}>v{tool.version || '1.0.0'}</Text>
                    </div>
                  }
                  extra={isDynamic && (
                      <Space>
                          <Tooltip title={dTool?.is_active ? "停用" : "启用"}>
                              <Button 
                                type="text" 
                                size="small" 
                                icon={<PoweroffOutlined style={{ color: dTool?.is_active ? '#52c41a' : '#ff4d4f' }} />} 
                                onClick={() => handleToggleDynamic(dTool!.id)} 
                              />
                          </Tooltip>
                          <Button 
                            type="text" 
                            size="small" 
                            danger 
                            icon={<DeleteOutlined />} 
                            onClick={() => Modal.confirm({
                                title: '确定删除此工具吗？',
                                onOk: () => handleDeleteDynamic(dTool!.id)
                            })} 
                          />
                      </Space>
                  )}
              >
                  <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8, height: 40, overflow: 'hidden' }}>
                    {tool.description}
                  </Paragraph>
  
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="函数名">
                      <Text code copyable style={{ fontSize: 11 }}>{tool.name}</Text>
                    </Descriptions.Item>
                  </Descriptions>
  
                  <Collapse ghost size="small" onChange={(keys) => {
                    if (keys.length > 0) fetchToolDetail(tool.name);
                  }}>
                    <Panel header={<Text type="secondary" style={{ fontSize: 11 }}>参数内容与配置</Text>} key="1">
                      {isDynamic ? (
                          <div style={{ fontSize: 11 }}>
                              <Text strong>配置 (Config):</Text>
                              <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                                  {JSON.stringify(dTool?.config, null, 2)}
                              </pre>
                              <Text strong>参数 (Schema):</Text>
                              <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                                  {JSON.stringify(dTool?.parameters_schema, null, 2)}
                              </pre>
                          </div>
                      ) : (
                          toolDetails[tool.name] ? (
                            <pre style={{
                              background: '#1e1e1e', color: '#d4d4d4',
                              padding: '12px', borderRadius: '6px',
                              fontSize: '11px', overflowX: 'auto',
                              maxHeight: 200
                            }}>
                              {JSON.stringify(toolDetails[tool.name].parameters_schema, null, 2)}
                            </pre>
                          ) : (
                            <Spin size="small" />
                          )
                      )}
                    </Panel>
                  </Collapse>
              </Card>
          </Col>
      );
  };

  if (loading) return <div style={{ padding: 60, textAlign: 'center' }}><Spin size="large" /></div>;

  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%', background: '#f5f7fa' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <ToolOutlined style={{ marginRight: 8 }} />
            工具注册表
          </Title>
          <Text type="secondary">管理内核中已注册的行动资产（Actions），查看参数 Schema 和开发指南</Text>
        </div>
        <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalVisible(true)}>注册外部工具</Button>
            <Button icon={<ReloadOutlined />} onClick={fetchAll}>刷新</Button>
        </Space>
      </div>

      {/* Kernel Status Bar */}
      {kernelStatus && (
        <Card size="small" style={{ marginBottom: 20, background: '#fff', borderRadius: 8 }}>
          <Row gutter={24}>
            <Col>
              <Text type="secondary">基础工具</Text>
              <div><Text strong style={{ fontSize: 20 }}>{tools.length}</Text></div>
            </Col>
            <Col>
              <Text type="secondary">动态工具</Text>
              <div><Text strong style={{ fontSize: 20, color: '#722ed1' }}>{dynamicTools.length}</Text></div>
            </Col>
            <Col>
              <Text type="secondary">知识库/记忆</Text>
              <div>
                <Space>
                    <Badge status={kernelStatus.has_memory_store ? 'success' : 'error'} text="Memory" />
                    <Badge status={kernelStatus.has_knowledge_base ? 'success' : 'error'} text="Knowledge" />
                </Space>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      <Tabs defaultActiveKey="1" className="custom-tabs">
          <Tabs.TabPane tab={<span><AppstoreOutlined /> 内置工具</span>} key="1">
              <Row gutter={[16, 16]}>
                  {tools.map(t => renderToolCard(t))}
              </Row>
          </Tabs.TabPane>
          <Tabs.TabPane tab={<span><PlusOutlined /> 自定义工具</span>} key="2">
              {dynamicTools.length === 0 ? (
                  <Empty description="暂无自定义工具，点击上方按钮注册" />
              ) : (
                  <Row gutter={[16, 16]}>
                      {dynamicTools.map(t => renderToolCard(t, true))}
                  </Row>
              )}
          </Tabs.TabPane>
          <Tabs.TabPane tab={<span><CodeOutlined /> 开发者指南</span>} key="3">
              {scaffold && (
                <Card bordered={false}>
                    <Alert
                        type="info"
                        showIcon
                        icon={<ApiOutlined />}
                        message={`内核加载机制: ${scaffold.registration_method}`}
                        description={`扫描路径: ${scaffold.scan_path} | 基类: ${scaffold.base_class}`}
                        style={{ marginBottom: 16 }}
                    />
                    <Title level={5}>开发步骤</Title>
                    <div style={{ marginBottom: 16 }}>
                        {scaffold.guide.steps.map((step, i) => (
                            <div key={i} style={{ padding: '4px 0', fontSize: 13 }}>
                                {step}
                            </div>
                        ))}
                    </div>
                    <Title level={5}>Python 模板</Title>
                    <pre style={{
                        background: '#1e1e1e', color: '#d4d4d4',
                        padding: '16px', borderRadius: '8px',
                        fontSize: '12px', overflowX: 'auto'
                    }}>
                        {scaffold.template}
                    </pre>
                </Card>
              )}
          </Tabs.TabPane>
      </Tabs>

      {/* 注册工具弹窗 */}
      <Modal
          title="注册外部能力"
          visible={isModalVisible}
          onCancel={() => setIsModalVisible(false)}
          onOk={() => form.submit()}
          width={700}
          destroyOnClose
      >
          <Form form={form} layout="vertical" onFinish={handleCreateTool}>
              <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="tool_type" label="工具类型" initialValue="api">
                        <Select onChange={(v) => setToolType(v)}>
                            <Option value="api">Web API (HTTP)</Option>
                            <Option value="mcp">MCP (Model Context Protocol)</Option>
                            <Option value="cli">CLI (Command Line)</Option>
                        </Select>
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="category" label="分类" initialValue="custom">
                        <Select>
                            <Option value="api">外部接口</Option>
                            <Option value="utility">实用工具</Option>
                            <Option value="erp">业务系统</Option>
                            <Option value="custom">自定义</Option>
                        </Select>
                    </Form.Item>
                  </Col>
              </Row>
              
              <Row gutter={16}>
                  <Col span={12}>
                      <Form.Item name="name" label="函数名 (ID)" rules={[{ required: true, message: '唯一标识' }]}>
                          <Input placeholder="如 get_weather" />
                      </Form.Item>
                  </Col>
                  <Col span={12}>
                      <Form.Item name="label" label="显示名称" rules={[{ required: true }]}>
                          <Input placeholder="如 获取天气状况" />
                      </Form.Item>
                  </Col>
              </Row>

              <Form.Item name="description" label="功能描述 (供 LLM 阅读)" rules={[{ required: true }]}>
                  <Input.TextArea placeholder="详细描述工具的作用、入参含义等，这将直接影响 LLM 的调用准确性。" rows={2} />
              </Form.Item>

              {toolType === 'api' && (
                  <Card size="small" title="API 配置" style={{ marginBottom: 16 }}>
                      <Form.Item name="url" label="API Endpoint" rules={[{ required: true }]}>
                          <Input placeholder="https://api.example.com/v1/action" />
                      </Form.Item>
                      <Form.Item name="method" label="HTTP Method" initialValue="POST">
                          <Select><Option value="GET">GET</Option><Option value="POST">POST</Option></Select>
                      </Form.Item>
                      <Form.Item name="headers" label="HTTP Headers (JSON)">
                          <Input.TextArea placeholder='{"Authorization": "Bearer xxx"}' rows={2} />
                      </Form.Item>
                  </Card>
              )}

              {toolType === 'mcp' && (
                  <Card size="small" title="MCP 配置" style={{ marginBottom: 16 }}>
                      <Form.Item name="command" label="Executable Command" rules={[{ required: true }]}>
                          <Input placeholder="npx" />
                      </Form.Item>
                      <Form.Item name="args" label="Arguments (Space separated)">
                          <Input placeholder="-y @modelcontextprotocol/server-everything" />
                      </Form.Item>
                  </Card>
              )}

              {toolType === 'cli' && (
                  <Card size="small" title="CLI 配置" style={{ marginBottom: 16 }}>
                      <Form.Item name="script" label="Shell Script" rules={[{ required: true }]}>
                          <Input.TextArea placeholder='python3 /path/to/my_script.py --data $input' rows={3} />
                      </Form.Item>
                  </Card>
              )}

              <Form.Item name="parameters_schema" label="参数 Schema (JSON Schema)" initialValue='{"type": "object", "properties": {}}'>
                  <Input.TextArea rows={4} placeholder='{"type": "object", "properties": {"loc": {"type": "string"}}}' />
              </Form.Item>
          </Form>
      </Modal>
    </div>
  );
};

export default ToolRegistry;
