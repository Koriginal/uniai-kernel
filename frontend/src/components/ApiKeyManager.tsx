import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Form,
  Input,
  List,
  Modal,
  Row,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ApiOutlined,
  CopyOutlined,
  DeleteOutlined,
  GlobalOutlined,
  KeyOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import type { AxiosInstance } from 'axios';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);

const { Text, Paragraph } = Typography;

interface ApiKeyManagerProps {
  api: AxiosInstance;
  user: any;
}

interface ApiKeyItem {
  id: string;
  name: string;
  key: string;
  is_active: boolean;
  created_at: string;
  last_used_at?: string | null;
}

const CodeBlock = ({ code, onCopy }: { code: string; onCopy: (value: string) => void }) => (
  <div style={{ position: 'relative' }}>
    <Button
      size="small"
      icon={<CopyOutlined />}
      style={{ position: 'absolute', right: 12, top: 12, zIndex: 1 }}
      onClick={() => onCopy(code)}
    >
      复制
    </Button>
    <pre
      style={{
        margin: 0,
        padding: '16px',
        borderRadius: 12,
        background: '#0b1220',
        color: '#d6e4ff',
        overflow: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        fontSize: 13,
        lineHeight: 1.6,
      }}
    >
      {code}
    </pre>
  </div>
);

const ApiKeyManager: React.FC<ApiKeyManagerProps> = ({ api, user }) => {
  const [loading, setLoading] = useState(true);
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [newKeyDetails, setNewKeyDetails] = useState<ApiKeyItem | null>(null);
  const [form] = Form.useForm();

  const origin = window.location.origin;
  const openAIBaseUrl = `${origin}/api/v1`;

  const curlExample = useMemo(
    () => `curl ${openAIBaseUrl}/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: <YOUR_API_KEY>" \\
  -d '{
    "model": "default",
    "stream": false,
    "messages": [
      { "role": "user", "content": "你好，请介绍一下你自己" }
    ]
  }'`,
    [openAIBaseUrl]
  );

  const pythonExample = useMemo(
    () => `from openai import OpenAI

client = OpenAI(
    api_key="<YOUR_API_KEY>",
    base_url="${openAIBaseUrl}"
)

resp = client.chat.completions.create(
    model="default",
    messages=[
        {"role": "user", "content": "帮我总结今天的任务重点"}
    ]
)

print(resp.choices[0].message.content)`,
    [openAIBaseUrl]
  );

  const jsExample = useMemo(
    () => `import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "<YOUR_API_KEY>",
  baseURL: "${openAIBaseUrl}",
});

const resp = await client.chat.completions.create({
  model: "default",
  messages: [
    { role: "user", content: "给我一份 3 条的接入建议" },
  ],
});

console.log(resp.choices[0].message.content);`,
    [openAIBaseUrl]
  );

  const fetchKeys = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/v1/user/api-keys/');
      setKeys(res.data || []);
    } catch {
      message.error('加载 API 秘钥失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success('已复制到剪贴板');
  };

  const handleCreate = async (values: { name: string }) => {
    try {
      const res = await api.post('/api/v1/user/api-keys/', values);
      setNewKeyDetails(res.data);
      setIsModalVisible(false);
      form.resetFields();
      message.success('API 秘钥创建成功');
      fetchKeys();
    } catch {
      message.error('创建失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/api/v1/user/api-keys/${id}`);
      message.success('秘钥已吊销');
      fetchKeys();
    } catch {
      message.error('操作失败');
    }
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (value: string) => <Text strong>{value}</Text>,
    },
    {
      title: '秘钥预览',
      dataIndex: 'key',
      key: 'key',
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (value: boolean) => <Tag color={value ? 'green' : 'red'}>{value ? '有效' : '禁用'}</Tag>,
    },
    {
      title: '最后使用',
      dataIndex: 'last_used_at',
      key: 'last_used_at',
      render: (value: string) => (value ? dayjs(value).fromNow() : '从未使用'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 92,
      render: (_: unknown, record: ApiKeyItem) => (
        <Button
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() =>
            Modal.confirm({
              title: '确定要吊销此 API 秘钥吗？',
              content: '删除后，所有使用此秘钥的应用将无法继续访问当前内核。',
              onOk: () => handleDelete(record.id),
            })
          }
        >
          吊销
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 24, background: '#f5f7fb', minHeight: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1480, margin: '0 auto' }}>
        <Row gutter={[16, 16]} align="top">
          <Col xs={24} xxl={10}>
          <Card
            bordered={false}
            style={{ borderRadius: 20, overflow: 'hidden' }}
            title={
              <Space>
                <KeyOutlined />
                <span>API 秘钥管理</span>
              </Space>
            }
            extra={
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalVisible(true)}>
                创建新秘钥
              </Button>
            }
          >
            <Space direction="vertical" size={12} style={{ width: '100%', marginBottom: 16 }}>
              <Text type="secondary">
                当前登录用户 {user?.username || user?.email || '当前用户'} 的开发者秘钥。适合接入外部客户端、工作流平台和自定义应用。
              </Text>
              <Alert
                type="info"
                showIcon
                message="安全提示"
                description="完整 API Key 只会在创建成功时展示一次。列表页仅显示脱敏预览。"
              />
            </Space>

            <Card
              size="small"
              style={{ marginBottom: 16, borderRadius: 14, background: '#fafcff' }}
              bodyStyle={{ padding: 14 }}
            >
              <Row gutter={[12, 12]}>
                <Col xs={24} sm={12}>
                  <Text type="secondary">OpenAI 兼容基地址</Text>
                  <div style={{ marginTop: 6 }}>
                    <Text code>{openAIBaseUrl}</Text>
                  </div>
                </Col>
                <Col xs={24} sm={12}>
                  <Text type="secondary">鉴权头</Text>
                  <div style={{ marginTop: 6 }}>
                    <Text code>X-API-Key: &lt;YOUR_API_KEY&gt;</Text>
                  </div>
                </Col>
              </Row>
            </Card>

            <Table
              columns={columns}
              dataSource={keys}
              rowKey="id"
              loading={loading}
              pagination={false}
              scroll={{ x: 'max-content' }}
            />
          </Card>
        </Col>

          <Col xs={24} xxl={14}>
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Card
                bordered={false}
                style={{ borderRadius: 20 }}
                title={
                  <Space>
                    <ApiOutlined />
                    <span>开发者接入指南</span>
                  </Space>
                }
              >
                <List
                  size="small"
                  dataSource={[
                    `Base URL: ${openAIBaseUrl}`,
                    '鉴权方式: 推荐使用 `X-API-Key: <YOUR_API_KEY>`',
                    '兼容接口: `POST /chat/completions`',
                    '请求格式: OpenAI Chat Completions 风格',
                  ]}
                  renderItem={(item) => <List.Item>{item}</List.Item>}
                />
              </Card>

              <Card
                bordered={false}
                style={{ borderRadius: 20 }}
                title={
                  <Space>
                    <GlobalOutlined />
                    <span>快速示例</span>
                  </Space>
                }
              >
                <Collapse
                  defaultActiveKey={['curl']}
                  items={[
                    {
                      key: 'curl',
                      label: 'cURL 示例',
                      children: <CodeBlock code={curlExample} onCopy={copyToClipboard} />,
                    },
                    {
                      key: 'python',
                      label: 'Python 示例',
                      children: <CodeBlock code={pythonExample} onCopy={copyToClipboard} />,
                    },
                    {
                      key: 'javascript',
                      label: 'JavaScript 示例',
                      children: <CodeBlock code={jsExample} onCopy={copyToClipboard} />,
                    },
                  ]}
                />
              </Card>

              <Card size="small" style={{ borderRadius: 16, background: '#fafafa' }}>
                <Space direction="vertical" size={6}>
                  <Text strong>接入建议</Text>
                  <Text type="secondary">优先把 API Key 放在服务端环境变量中，不要直接写死在前端代码里。</Text>
                  <Text type="secondary">如果你在对接 Dify、LobeChat 或自建 Agent UI，可直接将 Base URL 指向上面的地址。</Text>
                  <Text type="secondary">如果需要多环境隔离，建议按用途分别创建不同名称的 key，便于吊销和排查。</Text>
                </Space>
              </Card>
            </Space>
          </Col>
        </Row>
      </div>

      <Modal
        title="创建 API 秘钥"
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        onOk={() => form.submit()}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ name: 'Default Key' }}>
          <Form.Item name="name" label="秘钥名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：Dify 生产环境 / 团队机器人 / 本地测试" maxLength={48} />
          </Form.Item>
          <Text type="secondary">创建后将立即显示完整 key，请当场保存。</Text>
        </Form>
      </Modal>

      <Modal
        title={
          <Space>
            <SafetyCertificateOutlined style={{ color: '#52c41a' }} />
            <span>秘钥创建成功</span>
          </Space>
        }
        open={!!newKeyDetails}
        onCancel={() => setNewKeyDetails(null)}
        footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={() => newKeyDetails && copyToClipboard(newKeyDetails.key)}>
            复制秘钥
          </Button>,
          <Button key="close" type="primary" onClick={() => setNewKeyDetails(null)}>
            我已保存
          </Button>,
        ]}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message="这是你唯一一次看到完整秘钥"
            description="关闭后列表中只会展示脱敏预览，请先复制到密码管理器或环境变量。"
          />
          <Card size="small" style={{ background: '#f6f8fa', border: '1px solid #d0d7de' }}>
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Text strong style={{ fontFamily: 'monospace', fontSize: 15 }}>
                {newKeyDetails?.key}
              </Text>
              <Button type="link" icon={<CopyOutlined />} onClick={() => newKeyDetails && copyToClipboard(newKeyDetails.key)} />
            </Space>
          </Card>
          <Paragraph style={{ marginBottom: 0 }}>
            这个 key 可直接用于上面的 `curl`、Python 和 JavaScript 示例，把 {'<YOUR_API_KEY>'} 替换掉即可。
          </Paragraph>
        </Space>
      </Modal>
    </div>
  );
};

export default ApiKeyManager;
