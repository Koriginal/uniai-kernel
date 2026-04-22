import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  ConsoleSqlOutlined,
  CopyOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
  GlobalOutlined,
  LinkOutlined,
  PlusOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  RocketOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text, Paragraph } = Typography;

interface ToolMeta {
  name: string;
  label: string;
  description: string;
  category: string;
  icon: string | null;
  version: string;
}

interface ToolDetail extends ToolMeta {
  parameters_schema: any;
  openai_format: any;
}

interface DynamicTool extends ToolMeta {
  id: string;
  tool_type: 'api' | 'mcp' | 'cli';
  category: string;
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
  dynamic_diagnostics?: Record<string, { status: string; tool_type?: string; tool_id?: string; error?: string | null }>;
  version?: string;
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

interface CatalogItem {
  key: string;
  source: 'builtin' | 'dynamic';
  runtime_active: boolean;
  name: string;
  label: string;
  description: string;
  category: string;
  version: string;
  tool_type?: 'api' | 'mcp' | 'cli';
  id?: string;
  config?: any;
  parameters_schema?: any;
  is_active?: boolean;
}

interface ValidationResult {
  ok: boolean;
  normalized_config: any;
  normalized_schema: any;
  warnings: string[];
}

interface TestResult extends ValidationResult {
  result_preview: string;
}

const CATEGORY_COLORS: Record<string, string> = {
  knowledge: 'blue',
  utility: 'green',
  system: 'orange',
  integration: 'purple',
  custom: 'cyan',
  api: 'geekblue',
  mcp: 'magenta',
  cli: 'volcano',
};

const typeAccent: Record<string, { bg: string; border: string; text: string }> = {
  builtin: { bg: 'linear-gradient(135deg, #eff6ff 0%, #ffffff 100%)', border: '#bfdbfe', text: '#1d4ed8' },
  api: { bg: 'linear-gradient(135deg, #f5f3ff 0%, #ffffff 100%)', border: '#d8b4fe', text: '#6d28d9' },
  mcp: { bg: 'linear-gradient(135deg, #fff1f2 0%, #ffffff 100%)', border: '#fda4af', text: '#be123c' },
  cli: { bg: 'linear-gradient(135deg, #fff7ed 0%, #ffffff 100%)', border: '#fdba74', text: '#c2410c' },
};

const getTypeIcon = (source: 'builtin' | 'dynamic', toolType?: 'api' | 'mcp' | 'cli') => {
  if (source === 'builtin') return <ThunderboltOutlined />;
  if (toolType === 'api') return <GlobalOutlined />;
  if (toolType === 'mcp') return <CloudServerOutlined />;
  return <ConsoleSqlOutlined />;
};

const toolTemplates = {
  api: {
    title: 'HTTP API 工具',
    description: '把任意 REST 接口包装成模型可调用的函数。',
    defaults: {
      category: 'api',
      description: '调用外部 HTTP API 并返回结果',
      method: 'POST',
      timeout_seconds: 20,
      headers: '{\n  "Authorization": "Bearer <token>"\n}',
      sample_args: '{\n  "query": "OpenAI"\n}',
      parameters_schema: '{\n  "type": "object",\n  "properties": {\n    "query": {\n      "type": "string",\n      "description": "查询内容"\n    }\n  },\n  "required": ["query"]\n}',
    },
  },
  mcp: {
    title: 'MCP 工具',
    description: '接入 Model Context Protocol 服务器，可选 stdio 或 SSE 模式。',
    defaults: {
      category: 'mcp',
      transport: 'stdio',
      description: '通过 MCP 协议接入外部能力',
      timeout_seconds: 30,
      command: 'npx',
      args: '@modelcontextprotocol/server-memory',
      sse_url: 'http://localhost:3000/sse',
      sample_args: '{\n  "query": "hello"\n}',
      parameters_schema: '{\n  "type": "object",\n  "properties": {\n    "query": {\n      "type": "string",\n      "description": "输入内容"\n    }\n  },\n  "required": ["query"]\n}',
    },
  },
  cli: {
    title: 'CLI 工具',
    description: '在服务器本地执行可信脚本，适合内部自动化。',
    defaults: {
      category: 'cli',
      description: '执行本地命令行脚本并返回输出',
      timeout_seconds: 30,
      script: 'python3 scripts/my_tool.py',
      sample_args: '{\n  "path": "."\n}',
      parameters_schema: '{\n  "type": "object",\n  "properties": {\n    "path": {\n      "type": "string",\n      "description": "目标路径"\n    }\n  },\n  "required": ["path"]\n}',
    },
  },
};

const ToolRegistry: React.FC<ToolRegistryProps> = ({ msgApi }) => {
  const [tools, setTools] = useState<ToolMeta[]>([]);
  const [dynamicTools, setDynamicTools] = useState<DynamicTool[]>([]);
  const [toolDetails, setToolDetails] = useState<Record<string, ToolDetail>>({});
  const [kernelStatus, setKernelStatus] = useState<KernelStatus | null>(null);
  const [scaffold, setScaffold] = useState<Scaffold | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'builtin' | 'dynamic'>('all');
  const [category, setCategory] = useState<string>('all');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [selected, setSelected] = useState<CatalogItem | null>(null);
  const [selectedTableRowKeys, setSelectedTableRowKeys] = useState<React.Key[]>([]);

  const [isModalVisible, setIsModalVisible] = useState(false);
  const [toolType, setToolType] = useState<'api' | 'mcp' | 'cli'>('api');
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [testing, setTesting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();

  const formValues = Form.useWatch([], form) || {};
  const mcpTransport = Form.useWatch('transport', form) || 'stdio';

  useEffect(() => {
    fetchAll();
  }, []);

  useEffect(() => {
    applyTemplate(toolType);
  }, [toolType]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [toolsRes, dynamicRes, statusRes, scaffoldRes] = await Promise.all([
        axios.get('/api/v1/registry/actions'),
        axios.get('/api/v1/dynamic-tools/'),
        axios.get('/api/v1/registry/status'),
        axios.get('/api/v1/registry/scaffold'),
      ]);
      setTools(toolsRes.data || []);
      setDynamicTools(dynamicRes.data || []);
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
      setToolDetails((prev) => ({ ...prev, [name]: res.data }));
    } catch {
      msgApi.error(`获取 ${name} 详情失败`);
    }
  };

  const applyTemplate = (nextType: 'api' | 'mcp' | 'cli') => {
    const template = toolTemplates[nextType];
    form.setFieldsValue(template.defaults);
    setValidation(null);
    setTestResult(null);
  };

  const normalizePayload = (values: any) => {
    const parametersSchema = JSON.parse(values.parameters_schema || '{"type":"object","properties":{}}');
    let config: any = {};

    if (toolType === 'api') {
      config = {
        url: values.url,
        method: values.method || 'POST',
        headers: JSON.parse(values.headers || '{}'),
        timeout_seconds: Number(values.timeout_seconds || 20),
      };
    } else if (toolType === 'mcp') {
      config =
        values.transport === 'sse'
          ? {
              transport: 'sse',
              url: values.sse_url,
              timeout_seconds: Number(values.timeout_seconds || 30),
            }
          : {
              transport: 'stdio',
              command: values.command,
              args: (values.args || '').split(' ').filter((item: string) => item),
              timeout_seconds: Number(values.timeout_seconds || 30),
            };
    } else {
      config = {
        script: values.script,
        timeout_seconds: Number(values.timeout_seconds || 30),
      };
    }

    return {
      name: values.name,
      label: values.label,
      description: values.description,
      tool_type: toolType,
      category: values.category || 'custom',
      config,
      parameters_schema: parametersSchema,
    };
  };

  const validateBeforeCreate = async () => {
    try {
      const values = await form.validateFields();
      const payload = normalizePayload(values);
      setValidating(true);
      const res = await axios.post('/api/v1/dynamic-tools/validate', payload);
      setValidation(res.data);
      msgApi.success('配置校验通过');
      return res.data as ValidationResult;
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        msgApi.error(err.response.data.detail);
      } else if (err?.errorFields) {
        msgApi.error('请先补全表单中的必填项');
      } else if (err instanceof SyntaxError) {
        msgApi.error('JSON 字段格式不合法，请检查请求头或参数 Schema');
      } else {
        msgApi.error('配置校验失败');
      }
      return null;
    } finally {
      setValidating(false);
    }
  };

  const handleCreateTool = async () => {
    try {
      const values = await form.validateFields();
      setCreating(true);
      const checked = await validateBeforeCreate();
      if (!checked) return;
      const payload = normalizePayload(values);
      await axios.post('/api/v1/dynamic-tools/', payload);
      msgApi.success('外部工具注册成功');
      setIsModalVisible(false);
      form.resetFields();
      setValidation(null);
      setTestResult(null);
      fetchAll();
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        msgApi.error(err.response.data.detail);
      } else if (!err?.errorFields) {
        msgApi.error('注册失败');
      }
    } finally {
      setCreating(false);
    }
  };

  const handleTestTool = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        ...normalizePayload(values),
        sample_args: JSON.parse(values.sample_args || '{}'),
      };
      setTesting(true);
      const res = await axios.post('/api/v1/dynamic-tools/test', payload);
      setValidation(res.data);
      setTestResult(res.data);
      msgApi.success('测试调用成功');
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        msgApi.error(err.response.data.detail);
      } else if (err?.errorFields) {
        msgApi.error('请先补全表单中的必填项');
      } else if (err instanceof SyntaxError) {
        msgApi.error('JSON 字段格式不合法，请检查测试参数或 Schema');
      } else {
        msgApi.error('测试调用失败');
      }
    } finally {
      setTesting(false);
    }
  };

  const handleDeleteDynamic = async (id: string) => {
    try {
      await axios.delete(`/api/v1/dynamic-tools/${id}`);
      msgApi.success('工具已删除');
      if (selected?.id === id) setSelected(null);
      fetchAll();
    } catch {
      msgApi.error('删除失败');
    }
  };

  const handleToggleDynamic = async (id: string) => {
    try {
      await axios.post(`/api/v1/dynamic-tools/${id}/toggle`);
      msgApi.success('工具状态已更新');
      fetchAll();
    } catch {
      msgApi.error('状态切换失败');
    }
  };

  const categories = useMemo(() => {
    const values = new Set<string>();
    tools.forEach((item) => values.add(item.category));
    dynamicTools.forEach((item) => values.add(item.category));
    return ['all', ...Array.from(values)];
  }, [tools, dynamicTools]);

  const catalog = useMemo<CatalogItem[]>(() => {
    const activeNames = new Set(kernelStatus?.registered_actions || []);
    const builtinItems: CatalogItem[] = tools.map((tool) => ({
      key: `builtin:${tool.name}`,
      source: 'builtin',
      runtime_active: activeNames.has(tool.name),
      ...tool,
    }));
    const dynamicItems: CatalogItem[] = dynamicTools.map((tool) => ({
      key: `dynamic:${tool.id}`,
      source: 'dynamic',
      runtime_active: activeNames.has(tool.name),
      ...tool,
    }));
    return [...builtinItems, ...dynamicItems];
  }, [tools, dynamicTools, kernelStatus]);

  const filteredCatalog = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return catalog.filter((item) => {
      if (filter !== 'all' && item.source !== filter) return false;
      if (category !== 'all' && item.category !== category) return false;
      if (!keyword) return true;
      return [item.name, item.label, item.description, item.category, item.tool_type]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [catalog, search, filter, category]);

  useEffect(() => {
    const keySet = new Set(filteredCatalog.map((item) => item.key));
    setSelectedTableRowKeys((prev) => prev.filter((key) => keySet.has(String(key))));
  }, [filteredCatalog]);

  const previewPayload = useMemo(() => {
    try {
      return normalizePayload(formValues);
    } catch {
      return null;
    }
  }, [formValues, toolType]);

  const openDetail = (item: CatalogItem) => {
    setSelected(item);
    if (item.source === 'builtin') fetchToolDetail(item.name);
  };

  const selectedDynamicRows = useMemo(
    () =>
      filteredCatalog.filter(
        (item) => selectedTableRowKeys.includes(item.key) && item.source === 'dynamic' && item.id,
      ),
    [filteredCatalog, selectedTableRowKeys],
  );

  const handleBatchToggle = async (nextActive: boolean) => {
    if (selectedDynamicRows.length === 0) {
      msgApi.warning('请先选择至少一个动态工具');
      return;
    }
    try {
      await Promise.all(
        selectedDynamicRows.map(async (item) => {
          const currentlyActive = !!item.is_active;
          if (currentlyActive !== nextActive && item.id) {
            await axios.post(`/api/v1/dynamic-tools/${item.id}/toggle`);
          }
        }),
      );
      msgApi.success(nextActive ? '已批量启用所选动态工具' : '已批量停用所选动态工具');
      setSelectedTableRowKeys([]);
      fetchAll();
    } catch {
      msgApi.error('批量更新状态失败');
    }
  };

  const handleBatchDelete = async () => {
    if (selectedDynamicRows.length === 0) {
      msgApi.warning('请先选择至少一个动态工具');
      return;
    }
    Modal.confirm({
      title: `确认删除 ${selectedDynamicRows.length} 个动态工具？`,
      content: '删除后会从数据库和运行时注册表中移除，无法恢复。',
      okText: '确认删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await Promise.all(
            selectedDynamicRows.map((item) => axios.delete(`/api/v1/dynamic-tools/${item.id}`)),
          );
          msgApi.success('已批量删除所选动态工具');
          setSelectedTableRowKeys([]);
          fetchAll();
        } catch {
          msgApi.error('批量删除失败');
        }
      },
    });
  };

  const renderToolActions = (item: CatalogItem) => (
    <Space wrap>
      <Button size="small" onClick={() => openDetail(item)}>查看详情</Button>
      {item.source === 'dynamic' && item.id && (
        <>
          <Button size="small" icon={<PoweroffOutlined />} onClick={() => handleToggleDynamic(item.id!)}>
            {item.is_active ? '停用' : '启用'}
          </Button>
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() =>
              Modal.confirm({
                title: '确定删除此工具吗？',
                content: '删除后会同时从数据库和运行时注册表中移除。',
                onOk: () => handleDeleteDynamic(item.id!),
              })
            }
          >
            删除
          </Button>
        </>
      )}
    </Space>
  );

  const handleCopyTemplate = async () => {
    const content = scaffold?.template || '';
    if (!content) {
      msgApi.warning('当前没有可复制的模板内容');
      return;
    }
    try {
      await navigator.clipboard.writeText(content);
      msgApi.success('Python 模板已复制到剪贴板');
    } catch {
      msgApi.error('复制失败，请检查浏览器剪贴板权限');
    }
  };

  if (loading) {
    return <div style={{ padding: 80, textAlign: 'center' }}><Spin size="large" /></div>;
  }

  return (
    <div style={{ padding: 18, background: '#edf2f7', minHeight: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1560, margin: '0 auto' }}>
        <Card
          bordered={false}
          style={{
            marginBottom: 12,
            borderRadius: 14,
            border: '1px solid #dbeafe',
            background: '#f8fbff',
            boxShadow: '0 8px 20px rgba(29,78,216,0.06)',
          }}
          bodyStyle={{ padding: '10px 14px' }}
        >
          <Row gutter={[10, 10]} align="middle">
            <Col xs={24} xl={10}>
              <Space direction="vertical" size={2}>
                <Space wrap size={6}>
                  <Tag color="blue" style={{ borderRadius: 999, margin: 0 }}>Tool Hub</Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>内置能力 + 外部注册能力</Text>
                </Space>
                <Title level={4} style={{ margin: 0, lineHeight: 1.2 }}>工具注册中心</Title>
              </Space>
            </Col>
            <Col xs={24} xl={9}>
              <Space wrap size={14}>
                <Space size={6}>
                  <Tooltip title="当前运行时已可调用的能力数量">
                    <RocketOutlined style={{ color: '#1d4ed8' }} />
                  </Tooltip>
                  <Text type="secondary">运行中能力</Text>
                  <Text strong style={{ fontSize: 18 }}>{kernelStatus?.actions_count || 0}</Text>
                </Space>
                <Divider type="vertical" />
                <Space size={6}>
                  <Tooltip title="通过注册中心新增的外部工具数量">
                    <LinkOutlined style={{ color: '#0f172a' }} />
                  </Tooltip>
                  <Text type="secondary">动态工具</Text>
                  <Text strong style={{ fontSize: 18 }}>{dynamicTools.length}</Text>
                </Space>
              </Space>
            </Col>
            <Col xs={24} xl={5} style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Space wrap>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalVisible(true)} size="middle">
                  注册外部工具
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchAll} size="middle">
                  刷新
                </Button>
              </Space>
            </Col>
          </Row>
        </Card>

        <Row gutter={[18, 18]} align="top">
          <Col xs={24} xl={17}>
            <Card bordered={false} style={{ borderRadius: 16, marginBottom: 12 }} bodyStyle={{ padding: 14 }}>
              <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                <Input
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索工具名、场景、分类"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{ width: 360, maxWidth: '100%' }}
                />
                <Space wrap>
                  <Segmented
                    value={filter}
                    onChange={(value) => setFilter(value as 'all' | 'builtin' | 'dynamic')}
                    options={[
                      { label: '全部', value: 'all' },
                      { label: '内置', value: 'builtin' },
                      { label: '动态', value: 'dynamic' },
                    ]}
                  />
                  <Select value={category} onChange={setCategory} style={{ width: 160 }}>
                    {categories.map((item) => (
                      <Select.Option key={item} value={item}>
                        {item === 'all' ? '全部分类' : item}
                      </Select.Option>
                    ))}
                  </Select>
                  <Segmented
                    value={viewMode}
                    onChange={(value) => setViewMode(value as 'cards' | 'table')}
                    options={[
                      { label: '卡片', value: 'cards', icon: <AppstoreOutlined /> },
                      { label: '表格', value: 'table', icon: <UnorderedListOutlined /> },
                    ]}
                  />
                </Space>
              </Space>
            </Card>

            {filteredCatalog.length === 0 ? (
              <Card bordered={false} style={{ borderRadius: 16 }}>
                <Empty description="没有匹配到工具" />
              </Card>
            ) : viewMode === 'cards' ? (
              <Row gutter={[12, 12]}>
                {filteredCatalog.map((item) => {
                  const accent = typeAccent[item.source === 'builtin' ? 'builtin' : item.tool_type || 'api'];
                  return (
                    <Col key={item.key} xs={24} md={12} xxl={8}>
                      <Card
                        bordered={false}
                        hoverable
                        style={{
                          borderRadius: 16,
                          height: '100%',
                          overflow: 'hidden',
                          background: accent.bg,
                          border: `1px solid ${accent.border}`,
                          boxShadow: '0 8px 20px rgba(15,23,42,0.05)',
                        }}
                        bodyStyle={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                          <Space align="start" size={12}>
                            <Tooltip title={item.source === 'builtin' ? '内置工具' : `动态工具 · ${(item.tool_type || 'api').toUpperCase()}`}>
                              <div style={{
                                width: 36,
                                height: 36,
                                borderRadius: 12,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                background: '#fff',
                                color: accent.text,
                                boxShadow: '0 6px 16px rgba(0,0,0,0.06)',
                                fontSize: 16,
                              }}>
                                {getTypeIcon(item.source, item.tool_type)}
                              </div>
                            </Tooltip>
                            <div>
                              <Space wrap size={8}>
                                <Text strong style={{ fontSize: 17, color: '#0f172a' }}>{item.label}</Text>
                                <Tag color={item.source === 'builtin' ? 'blue' : 'purple'}>{item.source === 'builtin' ? '内置' : '动态'}</Tag>
                                <Tag color={CATEGORY_COLORS[item.category] || 'default'}>{item.category}</Tag>
                                {item.tool_type && <Tag>{item.tool_type.toUpperCase()}</Tag>}
                              </Space>
                              <div style={{ marginTop: 6 }}>
                                <Text code>{item.name}</Text>
                              </div>
                            </div>
                          </Space>
                          <Badge
                            status={
                              item.runtime_active
                                ? 'success'
                                : kernelStatus?.dynamic_diagnostics?.[item.name]?.status === 'error'
                                  ? 'error'
                                  : 'default'
                            }
                            text={
                              item.runtime_active
                                ? '已加载'
                                : kernelStatus?.dynamic_diagnostics?.[item.name]?.status === 'error'
                                  ? '加载失败'
                                  : '未加载'
                            }
                          />
                        </div>

                        <Paragraph ellipsis={{ rows: 3 }} style={{ margin: 0, color: '#334155' }}>
                          {item.description}
                        </Paragraph>

                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 8 }}>
                          <div style={{ padding: 10, borderRadius: 12, background: 'rgba(255,255,255,0.75)' }}>
                            <Text type="secondary" style={{ fontSize: 11 }}>版本</Text>
                            <div><Text strong>{item.version || '1.0.0'}</Text></div>
                          </div>
                          <div style={{ padding: 10, borderRadius: 12, background: 'rgba(255,255,255,0.75)' }}>
                            <Text type="secondary" style={{ fontSize: 11 }}>来源</Text>
                            <div><Text strong>{item.source === 'builtin' ? '内置' : '外部'}</Text></div>
                          </div>
                          <div style={{ padding: 10, borderRadius: 12, background: 'rgba(255,255,255,0.75)' }}>
                            <Text type="secondary" style={{ fontSize: 11 }}>超时</Text>
                            <div><Text strong>{item.config?.timeout_seconds ? `${item.config.timeout_seconds}s` : '默认'}</Text></div>
                          </div>
                        </div>

                        {kernelStatus?.dynamic_diagnostics?.[item.name]?.error && (
                          <Alert
                            type="error"
                            showIcon
                            message="运行时加载失败"
                            description={kernelStatus.dynamic_diagnostics[item.name].error}
                          />
                        )}

                        {renderToolActions(item)}
                      </Card>
                    </Col>
                  );
                })}
              </Row>
            ) : (
              <Card bordered={false} style={{ borderRadius: 16 }} bodyStyle={{ padding: 0 }}>
                <div
                  style={{
                    padding: '10px 12px',
                    borderBottom: '1px solid #eef2f7',
                    background: 'linear-gradient(180deg, #f8fbff 0%, #ffffff 100%)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 10,
                    flexWrap: 'wrap',
                  }}
                >
                  <Space size={10} wrap>
                    <Tag color="blue" style={{ margin: 0 }}>
                      已选 {selectedTableRowKeys.length}
                    </Tag>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      仅动态工具支持批量启停和删除
                    </Text>
                  </Space>
                  <Space wrap>
                    <Button
                      size="small"
                      icon={<PoweroffOutlined />}
                      disabled={selectedDynamicRows.length === 0}
                      onClick={() => handleBatchToggle(true)}
                    >
                      批量启用
                    </Button>
                    <Button
                      size="small"
                      icon={<PoweroffOutlined />}
                      disabled={selectedDynamicRows.length === 0}
                      onClick={() => handleBatchToggle(false)}
                    >
                      批量停用
                    </Button>
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      disabled={selectedDynamicRows.length === 0}
                      onClick={handleBatchDelete}
                    >
                      批量删除
                    </Button>
                  </Space>
                </div>
                <Table<CatalogItem>
                  rowKey="key"
                  size="middle"
                  rowSelection={{
                    selectedRowKeys: selectedTableRowKeys,
                    onChange: (keys) => setSelectedTableRowKeys(keys),
                    preserveSelectedRowKeys: true,
                  }}
                  pagination={{ pageSize: 10, showSizeChanger: false }}
                  dataSource={filteredCatalog}
                  rowClassName={(_, index) => (index % 2 === 0 ? 'tool-row-even' : 'tool-row-odd')}
                  onRow={(record) => ({
                    onDoubleClick: () => openDetail(record),
                  })}
                  columns={[
                    {
                      title: '工具',
                      key: 'tool',
                      width: 320,
                      render: (_, item) => (
                        <Space align="start" size={10}>
                          <Tooltip title={item.source === 'builtin' ? '内置工具' : `动态工具 · ${(item.tool_type || 'api').toUpperCase()}`}>
                            <div
                              style={{
                                width: 28,
                                height: 28,
                                borderRadius: 9,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                background: '#fff',
                                border: '1px solid #dbeafe',
                                color: '#2563eb',
                                marginTop: 2,
                              }}
                            >
                              {getTypeIcon(item.source, item.tool_type)}
                            </div>
                          </Tooltip>
                          <Space direction="vertical" size={1}>
                            <Space size={6} wrap>
                              <Text strong>{item.label}</Text>
                              <Tag color={item.source === 'builtin' ? 'blue' : 'purple'} style={{ margin: 0 }}>
                                {item.source === 'builtin' ? '内置' : '动态'}
                              </Tag>
                              {item.tool_type && <Tag style={{ margin: 0 }}>{item.tool_type.toUpperCase()}</Tag>}
                            </Space>
                            <Text code>{item.name}</Text>
                          </Space>
                        </Space>
                      ),
                    },
                    {
                      title: '分类',
                      dataIndex: 'category',
                      key: 'category',
                      width: 120,
                      render: (value: string) => <Tag color={CATEGORY_COLORS[value] || 'default'}>{value}</Tag>,
                    },
                    {
                      title: '状态',
                      key: 'status',
                      width: 130,
                      render: (_, item) => {
                        const isError = kernelStatus?.dynamic_diagnostics?.[item.name]?.status === 'error';
                        const loaded = item.runtime_active;
                        return (
                          <Tag
                            color={loaded ? 'success' : isError ? 'error' : 'default'}
                            style={{ borderRadius: 999, paddingInline: 10, margin: 0 }}
                          >
                            {loaded ? '已加载' : isError ? '加载失败' : '未加载'}
                          </Tag>
                        );
                      },
                    },
                    {
                      title: '版本',
                      dataIndex: 'version',
                      key: 'version',
                      width: 100,
                      render: (value: string) => <Text code>{value || '1.0.0'}</Text>,
                    },
                    {
                      title: '描述',
                      dataIndex: 'description',
                      key: 'description',
                      ellipsis: true,
                      render: (value: string) => (
                        <Text type="secondary" ellipsis style={{ maxWidth: 360 }}>
                          {value}
                        </Text>
                      ),
                    },
                    {
                      title: '操作',
                      key: 'actions',
                      width: 220,
                      render: (_, item) => renderToolActions(item),
                    },
                  ]}
                />
              </Card>
            )}
          </Col>

          <Col xs={24} xl={7}>
            <Space direction="vertical" size={12} style={{ width: '100%', position: 'sticky', top: 16 }}>
              <Card bordered={false} style={{ borderRadius: 16 }}>
                <Title level={5} style={{ marginTop: 0, marginBottom: 10 }}>接入建议</Title>
                <List
                  dataSource={[
                    '外部 API 适合封装 SaaS 接口、内部服务和 webhook 能力。',
                    'MCP 更适合结构化能力服务，推荐优先使用标准协议接入。',
                    'CLI 适合可信内网自动化，不建议直接暴露高风险系统命令。',
                  ]}
                  renderItem={(item) => (
                    <List.Item style={{ paddingInline: 0 }}>
                      <Space align="start">
                        <CheckCircleOutlined style={{ color: '#1677ff', marginTop: 4 }} />
                        <Text>{item}</Text>
                      </Space>
                    </List.Item>
                  )}
                />
              </Card>

              <Card bordered={false} style={{ borderRadius: 16 }}>
                <Title level={5} style={{ marginTop: 0, marginBottom: 10 }}>系统状态</Title>
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Alert
                    type="info"
                    showIcon
                    icon={<AppstoreOutlined />}
                    message={`注册表版本 ${kernelStatus?.version || '1.0.0'}`}
                    description={`当前运行时已加载 ${kernelStatus?.registered_actions?.length || 0} 个可执行能力`}
                  />
                  <Space>
                    <Badge status={kernelStatus?.has_memory_store ? 'success' : 'error'} text="Memory" />
                    <Badge status={kernelStatus?.has_knowledge_base ? 'success' : 'error'} text="Knowledge" />
                  </Space>
                  <Divider style={{ margin: '8px 0' }} />
                  <List
                    size="small"
                    dataSource={Object.entries(kernelStatus?.actions_by_category || {})}
                    renderItem={([key, count]) => (
                      <List.Item style={{ paddingInline: 0 }}>
                        <Space>
                          <Tag color={CATEGORY_COLORS[key] || 'default'}>{key}</Tag>
                          <Text>{count}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                  {Object.values(kernelStatus?.dynamic_diagnostics || {}).some((item) => item.status === 'error') && (
                    <>
                      <Divider style={{ margin: '8px 0' }} />
                      <Alert
                        type="warning"
                        showIcon
                        message="存在动态工具加载失败"
                        description="可以进入工具详情查看错误原因，或在注册向导中重新校验并测试。"
                      />
                    </>
                  )}
                </Space>
              </Card>

              <Card bordered={false} style={{ borderRadius: 16 }}>
                <Title level={5} style={{ marginTop: 0, marginBottom: 10 }}>开发者指南</Title>
                {scaffold ? (
                  <Space direction="vertical" size={14} style={{ width: '100%' }}>
                    <Alert
                      type="success"
                      showIcon
                      icon={<ToolOutlined />}
                      message={scaffold.registration_method}
                      description={`扫描路径: ${scaffold.scan_path}`}
                    />
                    <List
                      size="small"
                      dataSource={scaffold.guide.steps}
                      renderItem={(item) => <List.Item style={{ paddingInline: 0 }}>{item}</List.Item>}
                    />
                    <Collapse
                      items={[
                        {
                          key: 'python-template',
                          label: '查看 Python 模板',
                          children: (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                                <Button size="small" icon={<CopyOutlined />} onClick={handleCopyTemplate}>
                                  复制模板
                                </Button>
                              </div>
                              <pre
                                style={{
                                  margin: 0,
                                  maxHeight: 340,
                                  overflow: 'auto',
                                  whiteSpace: 'pre',
                                  wordBreak: 'normal',
                                  fontFamily: 'SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
                                  fontSize: 12,
                                  lineHeight: 1.6,
                                  background: '#0b1220',
                                  color: '#dbeafe',
                                  borderRadius: 12,
                                  border: '1px solid #1e293b',
                                  padding: 12,
                                }}
                              >
                                {scaffold.template}
                              </pre>
                            </div>
                          ),
                        },
                      ]}
                    />
                  </Space>
                ) : (
                  <Empty description="暂无开发指南" />
                )}
              </Card>
            </Space>
          </Col>
        </Row>
      </div>

      <style>{`
        .tool-row-even td {
          background: #fcfdff !important;
        }
        .tool-row-odd td {
          background: #f8fbff !important;
        }
        .ant-table-thead > tr > th {
          background: #f1f5f9 !important;
          color: #0f172a !important;
          font-weight: 700 !important;
          border-bottom: 1px solid #e2e8f0 !important;
        }
        .ant-table-tbody > tr:hover > td {
          background: #eaf2ff !important;
        }
      `}</style>

      <Drawer
        title={<span style={{ fontSize: 24, fontWeight: 700 }}>注册外部工具</span>}
        placement="right"
        width={720}
        open={isModalVisible}
        onClose={() => {
          setIsModalVisible(false);
          setValidation(null);
          setTestResult(null);
        }}
        extra={
          <Space>
            <Button onClick={validateBeforeCreate} loading={validating}>
              先校验配置
            </Button>
            <Button onClick={handleTestTool} loading={testing}>
              测试调用
            </Button>
            <Button type="primary" onClick={handleCreateTool} loading={creating}>
              注册工具
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size={18} style={{ width: '100%' }}>
          <Card
            bordered={false}
            style={{
              borderRadius: 22,
              background: 'linear-gradient(135deg, #eff6ff 0%, #ffffff 100%)',
              border: '1px solid #bfdbfe',
            }}
          >
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Text strong style={{ fontSize: 18 }}>选择接入类型</Text>
              <Segmented
                block
                value={toolType}
                onChange={(value) => setToolType(value as 'api' | 'mcp' | 'cli')}
                options={[
                  { label: 'API', value: 'api' },
                  { label: 'MCP', value: 'mcp' },
                  { label: 'CLI', value: 'cli' },
                ]}
              />
              <Text type="secondary">{toolTemplates[toolType].description}</Text>
            </Space>
          </Card>

          <Form form={form} layout="vertical">
            <Row gutter={14}>
              <Col span={12}>
                <Form.Item name="name" label="函数名" rules={[{ required: true, message: '请输入函数名' }]}>
                  <Input placeholder="例如 web_lookup" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="label" label="展示名称" rules={[{ required: true, message: '请输入展示名称' }]}>
                  <Input placeholder="例如 网络查询" />
                </Form.Item>
              </Col>
            </Row>

            <Form.Item name="description" label="工具描述" rules={[{ required: true, message: '请输入工具描述' }]}>
              <Input.TextArea rows={3} placeholder="描述它能做什么、适合什么场景，方便模型正确选择。" />
            </Form.Item>

            <Form.Item name="category" label="分类">
              <Select>
                {['custom', 'utility', 'integration', 'knowledge', 'system', 'api', 'mcp', 'cli'].map((item) => (
                  <Select.Option key={item} value={item}>{item}</Select.Option>
                ))}
              </Select>
            </Form.Item>

            {toolType === 'api' && (
              <>
                <Row gutter={14}>
                  <Col span={16}>
                    <Form.Item name="url" label="接口地址" rules={[{ required: true, message: '请输入 URL' }]}>
                      <Input placeholder="https://example.com/tool" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name="method" label="HTTP 方法">
                      <Select>
                        {['POST', 'GET', 'PUT', 'PATCH', 'DELETE'].map((item) => (
                          <Select.Option key={item} value={item}>{item}</Select.Option>
                        ))}
                      </Select>
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item name="timeout_seconds" label="超时（秒）">
                  <Input type="number" min={1} max={120} />
                </Form.Item>
                <Form.Item name="headers" label="请求头 JSON">
                  <Input.TextArea rows={5} placeholder='{"Authorization":"Bearer xxx"}' />
                </Form.Item>
              </>
            )}

            {toolType === 'mcp' && (
              <>
                <Form.Item name="transport" label="传输方式">
                  <Segmented
                    block
                    options={[
                      { label: 'stdio', value: 'stdio' },
                      { label: 'SSE', value: 'sse' },
                    ]}
                  />
                </Form.Item>
                {mcpTransport === 'sse' ? (
                  <>
                    <Form.Item name="sse_url" label="SSE 地址" rules={[{ required: true, message: '请输入 SSE 地址' }]}>
                      <Input placeholder="http://localhost:3000/sse" />
                    </Form.Item>
                    <Form.Item name="timeout_seconds" label="超时（秒）">
                      <Input type="number" min={1} max={120} />
                    </Form.Item>
                  </>
                ) : (
                  <>
                    <Form.Item name="command" label="命令" rules={[{ required: true, message: '请输入命令' }]}>
                      <Input placeholder="npx" />
                    </Form.Item>
                    <Form.Item name="args" label="参数">
                      <Input placeholder="@modelcontextprotocol/server-memory" />
                    </Form.Item>
                    <Form.Item name="timeout_seconds" label="超时（秒）">
                      <Input type="number" min={1} max={120} />
                    </Form.Item>
                  </>
                )}
              </>
            )}

            {toolType === 'cli' && (
              <>
                <Form.Item name="script" label="执行脚本" rules={[{ required: true, message: '请输入脚本内容' }]}>
                  <Input.TextArea rows={5} placeholder="python3 scripts/my_tool.py" />
                </Form.Item>
                <Form.Item name="timeout_seconds" label="超时（秒）">
                  <Input type="number" min={1} max={120} />
                </Form.Item>
              </>
            )}

            <Form.Item name="parameters_schema" label="参数 Schema JSON">
              <Input.TextArea rows={10} placeholder='{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}' />
            </Form.Item>
            <Form.Item name="sample_args" label="测试参数 JSON">
              <Input.TextArea rows={6} placeholder='{"query":"hello"}' />
            </Form.Item>
          </Form>

          {validation && validation.warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              icon={<ExclamationCircleOutlined />}
              message="校验通过，但有运行提醒"
              description={
                <ul style={{ marginBottom: 0, paddingLeft: 18 }}>
                  {validation.warnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              }
            />
          )}

          <Row gutter={[14, 14]}>
            <Col span={12}>
              <Card title="配置预览" size="small" style={{ borderRadius: 18 }}>
                <pre style={{ margin: 0, maxHeight: 300, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {JSON.stringify(previewPayload?.config || {}, null, 2)}
                </pre>
              </Card>
            </Col>
            <Col span={12}>
              <Card title="OpenAI 参数 Schema" size="small" style={{ borderRadius: 18 }}>
                <pre style={{ margin: 0, maxHeight: 300, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {JSON.stringify(previewPayload?.parameters_schema || {}, null, 2)}
                </pre>
              </Card>
            </Col>
          </Row>

          {testResult && (
            <Card title="测试结果预览" size="small" style={{ borderRadius: 18 }}>
              <pre style={{ margin: 0, maxHeight: 260, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {testResult.result_preview}
              </pre>
            </Card>
          )}
        </Space>
      </Drawer>

      <Drawer
        title={selected?.label || '工具详情'}
        placement="right"
        width={620}
        open={!!selected}
        onClose={() => setSelected(null)}
      >
        {selected && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card bordered={false} style={{ borderRadius: 20 }}>
              <Space wrap size={8}>
                <Tag color={selected.source === 'builtin' ? 'blue' : 'purple'}>
                  {selected.source === 'builtin' ? '内置' : '动态'}
                </Tag>
                <Tag color={CATEGORY_COLORS[selected.category] || 'default'}>{selected.category}</Tag>
                {selected.tool_type && <Tag>{selected.tool_type.toUpperCase()}</Tag>}
                <Badge status={selected.runtime_active ? 'success' : 'default'} text={selected.runtime_active ? '已加载到运行时' : '当前未加载'} />
              </Space>
              <Paragraph style={{ marginTop: 12 }}>{selected.description}</Paragraph>
              <Text code>{selected.name}</Text>
            </Card>

            {selected.source === 'dynamic' && kernelStatus?.dynamic_diagnostics?.[selected.name]?.error && (
              <Alert
                type="error"
                showIcon
                message="运行时加载错误"
                description={kernelStatus.dynamic_diagnostics[selected.name].error}
              />
            )}

            <Card title="参数 Schema" size="small" style={{ borderRadius: 18 }}>
              <pre style={{ margin: 0, maxHeight: 260, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {JSON.stringify(
                  selected.source === 'dynamic'
                    ? selected.parameters_schema || {}
                    : toolDetails[selected.name]?.parameters_schema || {},
                  null,
                  2
                )}
              </pre>
            </Card>

            <Card title={selected.source === 'dynamic' ? '运行配置' : 'OpenAI Function 定义'} size="small" style={{ borderRadius: 18 }}>
              <pre style={{ margin: 0, maxHeight: 320, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {JSON.stringify(
                  selected.source === 'dynamic'
                    ? selected.config || {}
                    : toolDetails[selected.name]?.openai_format || {},
                  null,
                  2
                )}
              </pre>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default ToolRegistry;
