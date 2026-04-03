import React, { useState, useEffect } from 'react';
import {
  Typography, Card, Tag, Empty, Row, Col, Descriptions,
  Collapse, Badge, Divider, Button, Spin, Alert
} from 'antd';
import {
  ToolOutlined, CodeOutlined, AppstoreOutlined,
  ThunderboltOutlined, ReloadOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text, Paragraph } = Typography;
const { Panel } = Collapse;

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
  integration: 'purple'
};

const ToolRegistry: React.FC<ToolRegistryProps> = ({ msgApi }) => {
  const [tools, setTools] = useState<ToolMeta[]>([]);
  const [toolDetails, setToolDetails] = useState<Record<string, ToolDetail>>({});
  const [kernelStatus, setKernelStatus] = useState<KernelStatus | null>(null);
  const [scaffold, setScaffold] = useState<Scaffold | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [toolsRes, statusRes, scaffoldRes] = await Promise.all([
        axios.get('/api/v1/registry/actions'),
        axios.get('/api/v1/registry/status'),
        axios.get('/api/v1/registry/scaffold')
      ]);
      setTools(toolsRes.data);
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

  if (loading) return <div style={{ padding: 60, textAlign: 'center' }}><Spin size="large" /></div>;

  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <ToolOutlined style={{ marginRight: 8 }} />
            工具注册表
          </Title>
          <Text type="secondary">管理内核中已注册的行动资产（Actions），查看参数 Schema 和开发指南</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={fetchAll}>刷新</Button>
      </div>

      {/* Kernel Status Bar */}
      {kernelStatus && (
        <Card size="small" style={{ marginBottom: 20, background: '#f6f8fa' }}>
          <Row gutter={24}>
            <Col>
              <Text type="secondary">已注册工具</Text>
              <div><Text strong style={{ fontSize: 20 }}>{kernelStatus.actions_count}</Text></div>
            </Col>
            <Col>
              <Text type="secondary">记忆系统</Text>
              <div>
                <Badge status={kernelStatus.has_memory_store ? 'success' : 'error'}
                  text={kernelStatus.has_memory_store ? '已激活' : '未连接'} />
              </div>
            </Col>
            <Col>
              <Text type="secondary">知识库</Text>
              <div>
                <Badge status={kernelStatus.has_knowledge_base ? 'success' : 'error'}
                  text={kernelStatus.has_knowledge_base ? '已激活' : '未连接'} />
              </div>
            </Col>
            {Object.entries(kernelStatus.actions_by_category).map(([cat, count]) => (
              <Col key={cat}>
                <Text type="secondary">{cat}</Text>
                <div><Tag color={CATEGORY_COLORS[cat] || 'default'}>{count} 个</Tag></div>
              </Col>
            ))}
          </Row>
        </Card>
      )}

      {/* Tool Cards */}
      {tools.length === 0 ? (
        <Empty description="内核暂无已注册工具" style={{ marginTop: 40 }} />
      ) : (
        <Row gutter={[16, 16]}>
          {tools.map(tool => (
            <Col key={tool.name} xs={24} md={12}>
              <Card
                hoverable
                size="small"
                style={{ height: '100%' }}
                title={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ThunderboltOutlined style={{ color: '#1890ff' }} />
                    <Text strong>{tool.label}</Text>
                    <Tag color={CATEGORY_COLORS[tool.category] || 'default'} style={{ fontSize: 10 }}>
                      {tool.category}
                    </Tag>
                    <Text type="secondary" style={{ fontSize: 10, marginLeft: 'auto' }}>v{tool.version}</Text>
                  </div>
                }
              >
                <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
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
                  <Panel header={<Text type="secondary" style={{ fontSize: 11 }}>参数 Schema & OpenAI Format</Text>} key="1">
                    {toolDetails[tool.name] ? (
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
                    )}
                  </Panel>
                </Collapse>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* Developer Guide */}
      {scaffold && (
        <>
          <Divider />
          <Card
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CodeOutlined style={{ color: '#722ed1' }} />
                <Text strong>{scaffold.guide.title}</Text>
              </div>
            }
            style={{ marginTop: 16 }}
          >
            <Alert
              type="info"
              showIcon
              icon={<AppstoreOutlined />}
              message={`注册方式: ${scaffold.registration_method}`}
              description={`扫描路径: ${scaffold.scan_path} | 基类: ${scaffold.base_class}`}
              style={{ marginBottom: 16 }}
            />

            <div style={{ marginBottom: 16 }}>
              {scaffold.guide.steps.map((step, i) => (
                <div key={i} style={{ padding: '4px 0', fontSize: 13 }}>
                  {step}
                </div>
              ))}
            </div>

            <Divider orientation="left" style={{ fontSize: 12 }}>代码模板</Divider>
            <pre style={{
              background: '#1e1e1e', color: '#d4d4d4',
              padding: '16px', borderRadius: '8px',
              fontSize: '12px', overflowX: 'auto',
              position: 'relative'
            }}>
              {scaffold.template}
            </pre>
          </Card>
        </>
      )}
    </div>
  );
};

export default ToolRegistry;
