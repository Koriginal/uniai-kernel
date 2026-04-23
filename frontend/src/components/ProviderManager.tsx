import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
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
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  GlobalOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  SyncOutlined,
  UnorderedListOutlined,
  AppstoreOutlined,
  ApiOutlined,
  LinkOutlined,
  RadarChartOutlined,
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text, Paragraph } = Typography;

interface ProviderManagerProps {
  modelConfigs: any[];
  msgApi: any;
  onRefresh: () => void;
}

interface ProviderModelItem {
  id: number;
  model_name: string;
  model_type: string;
  context_length: number;
  max_output_tokens?: number | null;
  is_default?: boolean;
}

interface ProviderItem {
  id: number;
  display_name: string;
  provider_type: string;
  api_base: string;
  description?: string | null;
  is_active?: boolean;
  created_at?: string | null;
  models: ProviderModelItem[];
}

interface ProviderHealth {
  provider_id: number;
  status: 'healthy' | 'degraded' | 'error';
  model?: string;
  latency_ms?: number | null;
  error?: string;
  reason?: string;
}

const MODEL_TYPE_COLOR: Record<string, string> = {
  chat: 'blue',
  llm: 'blue',
  embedding: 'green',
  rerank: 'purple',
  vision: 'cyan',
  reasoning: 'magenta',
  tts: 'orange',
  stt: 'gold',
};

const MODEL_TYPE_NAME: Record<string, string> = {
  chat: '对话',
  llm: '对话',
  embedding: '向量',
  rerank: '重排',
  vision: '视觉',
  reasoning: '推理',
  tts: '语音TTS',
  stt: '语音STT',
};

const PROVIDER_ACCENT: Record<string, { bg: string; border: string; iconBg: string; iconText: string }> = {
  openai: { bg: 'linear-gradient(135deg, #eff6ff 0%, #ffffff 100%)', border: '#bfdbfe', iconBg: '#ffffff', iconText: '#2563eb' },
  azure_openai: { bg: 'linear-gradient(135deg, #eff6ff 0%, #ffffff 100%)', border: '#bfdbfe', iconBg: '#ffffff', iconText: '#2563eb' },
  anthropic: { bg: 'linear-gradient(135deg, #fff7ed 0%, #ffffff 100%)', border: '#fed7aa', iconBg: '#ffffff', iconText: '#c2410c' },
  gemini: { bg: 'linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%)', border: '#bbf7d0', iconBg: '#ffffff', iconText: '#15803d' },
};

const ProviderManager: React.FC<ProviderManagerProps> = ({ modelConfigs, msgApi, onRefresh }) => {
  const [form] = Form.useForm();
  const [modelForm] = Form.useForm();
  const [defaultsForm] = Form.useForm();

  const notify = {
    success: (content: string) => (msgApi?.success ? msgApi.success(content) : message.success(content)),
    error: (content: string) => (msgApi?.error ? msgApi.error(content) : message.error(content)),
    info: (content: string) => (msgApi?.info ? msgApi.info(content) : message.info(content)),
  };

  const [modalVisible, setModalVisible] = useState(false);
  const [customMode, setCustomMode] = useState<'template' | 'custom'>('template');
  const [templates, setTemplates] = useState<any[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null);

  const [manageModalVisible, setManageModalVisible] = useState(false);
  const [currentProvider, setCurrentProvider] = useState<ProviderItem | null>(null);
  const [addModelVisible, setAddModelVisible] = useState(false);

  const [defaultModelsVisible, setDefaultModelsVisible] = useState(false);
  const [savingDefaults, setSavingDefaults] = useState(false);
  const [defaultModelsSnapshot, setDefaultModelsSnapshot] = useState<any[]>([]);

  const [search, setSearch] = useState('');
  const [providerTypeFilter, setProviderTypeFilter] = useState<string>('all');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('table');
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [providerHealthMap, setProviderHealthMap] = useState<Record<number, ProviderHealth>>({});
  const [healthCheckingIds, setHealthCheckingIds] = useState<number[]>([]);

  const providers = modelConfigs as ProviderItem[];

  const providerTypeOptions = useMemo(() => {
    const values = Array.from(new Set(providers.map((item) => item.provider_type).filter(Boolean)));
    return ['all', ...values];
  }, [providers]);

  const filteredProviders = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return providers.filter((provider) => {
      if (providerTypeFilter !== 'all' && provider.provider_type !== providerTypeFilter) return false;
      if (!keyword) return true;
      const modelNames = (provider.models || []).map((m) => m.model_name);
      return [provider.display_name, provider.api_base, provider.description, provider.provider_type, ...modelNames]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [providers, search, providerTypeFilter]);

  useEffect(() => {
    const keySet = new Set(filteredProviders.map((item) => item.id));
    setSelectedRowKeys((prev) => prev.filter((key) => keySet.has(Number(key))));
  }, [filteredProviders]);

  const selectedProviders = useMemo(
    () => filteredProviders.filter((item) => selectedRowKeys.includes(item.id)),
    [filteredProviders, selectedRowKeys],
  );

  const providerStats = useMemo(() => {
    const totalProviders = providers.length;
    const totalModels = providers.reduce((sum, p) => sum + (p.models?.length || 0), 0);
    const typeCount = providerTypeOptions.filter((item) => item !== 'all').length;
    const coveredModelTypes = new Set<string>();
    providers.forEach((p) => (p.models || []).forEach((m) => coveredModelTypes.add(m.model_type === 'llm' ? 'chat' : m.model_type)));
    return {
      totalProviders,
      totalModels,
      typeCount,
      coveredModelTypes: coveredModelTypes.size,
    };
  }, [providers, providerTypeOptions]);

  const modelTypeDistribution = useMemo(() => {
    const counter = new Map<string, number>();
    providers.forEach((p) => {
      (p.models || []).forEach((m) => {
        const type = m.model_type === 'llm' ? 'chat' : m.model_type;
        counter.set(type, (counter.get(type) || 0) + 1);
      });
    });
    return Array.from(counter.entries()).sort((a, b) => b[1] - a[1]);
  }, [providers]);

  const fetchTemplates = async () => {
    try {
      const res = await axios.get('/api/v1/providers/templates');
      setTemplates(res.data || []);
    } catch {
      notify.error('获取模板失败');
    }
  };

  const fetchDefaultModelsSnapshot = async () => {
    try {
      const res = await axios.get('/api/v1/providers/my/default-models');
      setDefaultModelsSnapshot(res.data || []);
    } catch {
      setDefaultModelsSnapshot([]);
    }
  };

  useEffect(() => {
    fetchDefaultModelsSnapshot();
  }, []);

  const refreshProviders = () => {
    onRefresh();
    fetchDefaultModelsSnapshot();
  };

  const openAddModal = () => {
    fetchTemplates();
    form.resetFields();
    setSelectedTemplate(null);
    setCustomMode('template');
    setModalVisible(true);
  };

  const handleSubmit = async (values: any) => {
    try {
      const payload = {
        template_name: customMode === 'template' ? values.template_name : null,
        display_name: values.display_name,
        api_base: customMode === 'custom' ? values.api_base : null,
        api_key: values.api_key,
        custom_config: {},
      };
      await axios.post('/api/v1/providers/my/providers', payload);
      notify.success('供应商接入成功');
      setModalVisible(false);
      refreshProviders();
    } catch (err: any) {
      notify.error(err.response?.data?.detail || '接入失败');
    }
  };

  const openManageModels = (provider: ProviderItem) => {
    setCurrentProvider(provider);
    setManageModalVisible(true);
  };

  const handleSyncProvider = async (id: number) => {
    try {
      const res = await axios.post(`/api/v1/providers/my/providers/${id}/sync`);
      if (res.data.status === 'synced') {
        notify.success(`同步成功：新增 ${res.data.added} 个，更新 ${res.data.updated} 个模型`);
      } else {
        notify.info(res.data.message || '已是最新版本');
      }
      refreshProviders();
    } catch (err: any) {
      notify.error(err.response?.data?.detail || '同步失败');
    }
  };

  const handleBatchSync = async () => {
    if (selectedProviders.length === 0) {
      notify.info('请先选择至少一个供应商');
      return;
    }
    try {
      await Promise.all(selectedProviders.map((item) => axios.post(`/api/v1/providers/my/providers/${item.id}/sync`)));
      notify.success(`已批量同步 ${selectedProviders.length} 个供应商`);
      setSelectedRowKeys([]);
      refreshProviders();
    } catch {
      notify.error('批量同步失败');
    }
  };

  const handleDeleteProvider = (provider: ProviderItem) => {
    Modal.confirm({
      title: `确认移除供应商 ${provider.display_name}？`,
      content: '该供应商下的模型配置将被同步移除。',
      okText: '确认移除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await axios.delete(`/api/v1/providers/my/providers/${provider.id}`);
          notify.success('已移除');
          if (currentProvider?.id === provider.id) {
            setManageModalVisible(false);
            setCurrentProvider(null);
          }
          refreshProviders();
        } catch (err: any) {
          notify.error(err.response?.data?.detail || '移除失败');
        }
      },
    });
  };

  const handleBatchDelete = async () => {
    if (selectedProviders.length === 0) {
      notify.info('请先选择至少一个供应商');
      return;
    }
    Modal.confirm({
      title: `确认删除 ${selectedProviders.length} 个供应商？`,
      content: '删除后会同时移除其下属模型配置。',
      okText: '确认删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await Promise.all(selectedProviders.map((item) => axios.delete(`/api/v1/providers/my/providers/${item.id}`)));
          notify.success('已批量移除所选供应商');
          setSelectedRowKeys([]);
          refreshProviders();
        } catch {
          notify.error('批量删除失败');
        }
      },
    });
  };

  const checkProviderHealth = async (providerId: number) => {
    setHealthCheckingIds((prev) => Array.from(new Set([...prev, providerId])));
    try {
      const res = await axios.get(`/api/v1/providers/my/providers/${providerId}/health`);
      setProviderHealthMap((prev) => ({ ...prev, [providerId]: res.data }));
      if (res.data?.status === 'healthy') notify.success('健康检查通过');
      else if (res.data?.status === 'degraded') notify.info(res.data?.reason || '健康检查完成（降级）');
      else notify.error(res.data?.error || '健康检查失败');
    } catch (err: any) {
      notify.error(err.response?.data?.detail || '健康检查失败');
    } finally {
      setHealthCheckingIds((prev) => prev.filter((id) => id !== providerId));
    }
  };

  const handleBatchHealthCheck = async () => {
    const targets = selectedProviders.length > 0 ? selectedProviders : filteredProviders;
    if (!targets.length) {
      notify.info('没有可检测的供应商');
      return;
    }
    await Promise.all(targets.map((item) => checkProviderHealth(item.id)));
  };

  const renderHealthTag = (providerId: number) => {
    const health = providerHealthMap[providerId];
    if (!health) return <Tag style={{ margin: 0 }}>未检测</Tag>;
    if (health.status === 'healthy') {
      return <Tag color="success" style={{ margin: 0 }}>健康 {health.latency_ms ? `${health.latency_ms}ms` : ''}</Tag>;
    }
    if (health.status === 'degraded') {
      return <Tag color="warning" style={{ margin: 0 }}>降级</Tag>;
    }
    return <Tag color="error" style={{ margin: 0 }}>异常</Tag>;
  };

  const handleAddModel = async (values: any) => {
    if (!currentProvider) return;
    try {
      await axios.post(`/api/v1/providers/my/providers/${currentProvider.id}/models`, values);
      notify.success('模型已添加');
      setAddModelVisible(false);
      modelForm.resetFields();
      refreshProviders();
      const res = await axios.get(`/api/v1/providers/my/providers/${currentProvider.id}/models`);
      setCurrentProvider({ ...currentProvider, models: res.data || [] });
    } catch (err: any) {
      notify.error(err.response?.data?.detail || '添加失败');
    }
  };

  const handleDeleteModel = async (modelId: number) => {
    if (!currentProvider) return;
    try {
      await axios.delete(`/api/v1/providers/my/providers/${currentProvider.id}/models/${modelId}`);
      notify.success('模型已删除');
      const res = await axios.get(`/api/v1/providers/my/providers/${currentProvider.id}/models`);
      setCurrentProvider({ ...currentProvider, models: res.data || [] });
      refreshProviders();
    } catch {
      notify.error('删除失败');
    }
  };

  const openDefaultModels = async () => {
    try {
      const res = await axios.get('/api/v1/providers/my/default-models');
      const initialValues: any = {};
      (res.data || []).forEach((item: any) => {
        initialValues[item.model_type] = `${item.provider_id}:${item.model_name}`;
      });
      defaultsForm.setFieldsValue(initialValues);
      setDefaultModelsVisible(true);
    } catch {
      notify.error('获取默认模型配置失败');
    }
  };

  const saveDefaults = async (values: any) => {
    setSavingDefaults(true);
    try {
      for (const [type, val] of Object.entries(values)) {
        if (!val) continue;
        const [pid, name] = (val as string).split(':');
        await axios.put('/api/v1/providers/my/default-models', {
          model_type: type,
          model_name: name,
          provider_id: Number(pid),
        });
      }
      notify.success('全局默认模型已保存');
      setDefaultModelsVisible(false);
      refreshProviders();
    } catch (err: any) {
      notify.error(err.response?.data?.detail || '保存失败');
    } finally {
      setSavingDefaults(false);
    }
  };

  const renderModelOptions = (type: string) =>
    providers.map((provider) => {
      const filtered = (provider.models || []).filter((model) => {
        let modelType = model.model_type === 'llm' ? 'chat' : model.model_type;
        const name = String(model.model_name || '').toLowerCase();
        if (name.includes('vl') || name.includes('vision')) modelType = 'vision';
        else if (name.includes('-r1') || name.includes('reasoner') || name.startsWith('o1') || name.startsWith('o3')) modelType = 'reasoning';
        return modelType === type;
      });
      if (!filtered.length) return null;
      return (
        <Select.OptGroup key={provider.id} label={provider.display_name}>
          {filtered.map((model) => (
            <Select.Option key={`${provider.id}:${model.model_name}`} value={`${provider.id}:${model.model_name}`} label={model.model_name}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 13 }}>{model.model_name}</span>
                <Tag bordered={false} style={{ margin: 0, fontSize: 10 }}>
                  {model.context_length >= 1024 ? `${Math.round(model.context_length / 1024)}K` : model.context_length}
                </Tag>
              </div>
            </Select.Option>
          ))}
        </Select.OptGroup>
      );
    });

  return (
    <div style={{ padding: 16, background: '#edf2f7', minHeight: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1480, margin: '0 auto' }}>
        <Card bordered={false} style={{ marginBottom: 12, borderRadius: 14, border: '1px solid #dbeafe', background: '#f8fbff', boxShadow: '0 8px 20px rgba(29,78,216,0.06)' }} bodyStyle={{ padding: '10px 14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
            <Space direction="vertical" size={4}>
              <Space wrap size={6}>
                <Tag color="blue" style={{ borderRadius: 999, margin: 0 }}>Model Hub</Tag>
                <Text type="secondary" style={{ fontSize: 12 }}>统一管理供应商接入、模型目录与默认选型</Text>
              </Space>
              <Title level={4} style={{ margin: 0, lineHeight: 1.2 }}>模型供应商控制台</Title>
              <Space size={6} wrap>
                <Tag style={{ padding: '3px 8px', borderRadius: 999, margin: 0, fontSize: 13 }}>
                  <ApiOutlined /> 供应商 {providerStats.totalProviders}
                </Tag>
                <Tag style={{ padding: '3px 8px', borderRadius: 999, margin: 0, fontSize: 13 }}>
                  <DatabaseOutlined /> 模型 {providerStats.totalModels}
                </Tag>
                <Tag style={{ padding: '3px 8px', borderRadius: 999, margin: 0, fontSize: 13 }}>
                  <RadarChartOutlined /> 覆盖 {providerStats.coveredModelTypes}
                </Tag>
              </Space>
            </Space>
            <Space wrap size={8}>
              <Button icon={<GlobalOutlined />} onClick={openDefaultModels}>默认模型设置</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal}>接入供应商</Button>
              <Tooltip title="刷新供应商与默认模型快照">
                <Button icon={<ReloadOutlined />} onClick={refreshProviders}>刷新</Button>
              </Tooltip>
            </Space>
          </div>
        </Card>

        <Card bordered={false} style={{ borderRadius: 14, marginBottom: 12 }} bodyStyle={{ padding: 10 }}>
          <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
            <Input allowClear prefix={<SearchOutlined />} placeholder="搜索供应商、模型名、API 地址" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 560, maxWidth: '100%' }} />
            <Space wrap>
              <Select value={providerTypeFilter} onChange={setProviderTypeFilter} style={{ width: 180 }}>
                {providerTypeOptions.map((item) => (
                  <Select.Option key={item} value={item}>{item === 'all' ? '全部类型' : item.toUpperCase()}</Select.Option>
                ))}
              </Select>
              <Segmented value={viewMode} onChange={(value) => setViewMode(value as 'cards' | 'table')} options={[{ label: '卡片', value: 'cards', icon: <AppstoreOutlined /> }, { label: '表格', value: 'table', icon: <UnorderedListOutlined /> }]} />
              <Button icon={<RadarChartOutlined />} onClick={handleBatchHealthCheck} disabled={filteredProviders.length === 0}>
                健康检测
              </Button>
            </Space>
          </Space>
        </Card>

        {filteredProviders.length === 0 ? (
          <Card bordered={false} style={{ borderRadius: 16 }}><Empty description="没有匹配到模型供应商" /></Card>
        ) : viewMode === 'cards' ? (
          <div
            style={{
              display: 'grid',
              gap: 12,
              justifyContent: 'start',
              gridTemplateColumns:
                filteredProviders.length === 1
                  ? 'minmax(0, 1fr)'
                  : 'repeat(auto-fit, minmax(460px, 1fr))',
            }}
          >
            {filteredProviders.map((provider) => (
              <div
                key={provider.id}
                style={
                  filteredProviders.length === 1
                    ? { width: '100%', maxWidth: 'calc((100% - 12px) / 2)' }
                    : undefined
                }
              >
                <Card
                  hoverable
                  bordered={false}
                  style={{
                    borderRadius: 16,
                    border: `1px solid ${(PROVIDER_ACCENT[provider.provider_type] || PROVIDER_ACCENT.openai).border}`,
                    background: (PROVIDER_ACCENT[provider.provider_type] || PROVIDER_ACCENT.openai).bg,
                    boxShadow: '0 8px 20px rgba(15,23,42,0.05)',
                    height: '100%',
                  }}
                  bodyStyle={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}
                >
                  <Space align="start" size={10}>
                    <div
                      style={{
                        width: 38,
                        height: 38,
                        borderRadius: 12,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: (PROVIDER_ACCENT[provider.provider_type] || PROVIDER_ACCENT.openai).iconBg,
                        border: `1px solid ${(PROVIDER_ACCENT[provider.provider_type] || PROVIDER_ACCENT.openai).border}`,
                        color: (PROVIDER_ACCENT[provider.provider_type] || PROVIDER_ACCENT.openai).iconText,
                        boxShadow: '0 6px 16px rgba(0,0,0,0.06)',
                      }}
                    >
                      <LinkOutlined />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <Space wrap size={6}>
                        <Text strong style={{ fontSize: 17, color: '#0f172a' }}>{provider.display_name}</Text>
                        <Tag color="geekblue" style={{ margin: 0 }}>{provider.provider_type.toUpperCase()}</Tag>
                        {renderHealthTag(provider.id)}
                      </Space>
                      <Text type="secondary" style={{ fontSize: 13 }}>
                        {provider.description || '通用模型接入通道，可承载多类能力模型。'}
                      </Text>
                    </div>
                  </Space>
                  <Paragraph
                    ellipsis={{ rows: 1, tooltip: provider.api_base }}
                    style={{ margin: 0, fontFamily: 'SFMono-Regular, Menlo, Monaco, Consolas, monospace', color: '#475569' }}
                  >
                    {provider.api_base}
                  </Paragraph>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 8 }}>
                    <div style={{ background: 'rgba(255,255,255,0.78)', borderRadius: 12, padding: 10 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>模型</Text>
                      <div><Text strong>{provider.models?.length || 0}</Text></div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.78)', borderRadius: 12, padding: 10 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>创建</Text>
                      <div><Text strong>{provider.created_at ? provider.created_at.slice(0, 10) : '未知'}</Text></div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.78)', borderRadius: 12, padding: 10 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>类型覆盖</Text>
                      <div>
                        <Text strong>{new Set((provider.models || []).map((item) => item.model_type)).size}</Text>
                      </div>
                    </div>
                  </div>
                  <Space wrap size={[6, 6]}>
                    {(provider.models || []).slice(0, 7).map((model) => (
                      <Tag key={model.id} color={MODEL_TYPE_COLOR[model.model_type] || 'default'} style={{ margin: 0 }}>{model.model_name}</Tag>
                    ))}
                    {(provider.models || []).length > 7 && <Tag style={{ margin: 0 }}>+{provider.models.length - 7}</Tag>}
                  </Space>
                  <Divider style={{ margin: '2px 0' }} />
                  <Space wrap style={{ marginTop: 'auto' }} size={6}>
                    <Button size="small" icon={<RadarChartOutlined />} loading={healthCheckingIds.includes(provider.id)} onClick={() => checkProviderHealth(provider.id)}>检测</Button>
                    <Button size="small" icon={<SyncOutlined />} onClick={() => handleSyncProvider(provider.id)}>同步</Button>
                    <Button size="small" icon={<SettingOutlined />} onClick={() => openManageModels(provider)}>模型</Button>
                    <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDeleteProvider(provider)}>移除</Button>
                  </Space>
                </Card>
              </div>
            ))}
          </div>
        ) : (
          <Card bordered={false} style={{ borderRadius: 14 }} bodyStyle={{ padding: 0 }}>
            <div style={{ padding: '8px 12px', borderBottom: '1px solid #eef2f7', background: '#f8fafc', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <Space size={10} wrap>
                <Tag color="blue" style={{ margin: 0 }}>已选 {selectedRowKeys.length}</Tag>
                <Text type="secondary" style={{ fontSize: 12 }}>支持批量同步 / 健康检测 / 删除</Text>
              </Space>
              <Space wrap>
                <Button size="small" icon={<RadarChartOutlined />} disabled={selectedProviders.length === 0} onClick={handleBatchHealthCheck}>批量检测</Button>
                <Button size="small" icon={<SyncOutlined />} disabled={selectedProviders.length === 0} onClick={handleBatchSync}>批量同步</Button>
                <Button size="small" danger icon={<DeleteOutlined />} disabled={selectedProviders.length === 0} onClick={handleBatchDelete}>批量删除</Button>
              </Space>
            </div>
            <Table<ProviderItem>
              rowKey="id"
              size="middle"
              rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys), preserveSelectedRowKeys: true }}
              pagination={{ pageSize: 8, showSizeChanger: false }}
              dataSource={filteredProviders}
              scroll={{ x: 1080 }}
              columns={[
                {
                  title: '供应商',
                  key: 'provider',
                  width: 420,
                  render: (_, provider) => (
                    <Space align="start" size={10}>
                      <div style={{ width: 28, height: 28, borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fff', border: '1px solid #dbeafe', color: '#2563eb', marginTop: 2 }}><LinkOutlined /></div>
                      <Space direction="vertical" size={1}>
                        <Space size={6} wrap>
                          <Text strong>{provider.display_name}</Text>
                          <Tag color="geekblue" style={{ margin: 0 }}>{provider.provider_type.toUpperCase()}</Tag>
                        </Space>
                        <Paragraph
                          ellipsis={{ rows: 1, tooltip: provider.api_base }}
                          style={{ margin: 0, maxWidth: 420 }}
                        >
                          <Text code>{provider.api_base}</Text>
                        </Paragraph>
                      </Space>
                    </Space>
                  ),
                },
                {
                  title: '健康',
                  key: 'health',
                  width: 110,
                  render: (_, provider) => renderHealthTag(provider.id),
                },
                { title: '模型数', key: 'models', width: 80, align: 'center', render: (_, provider) => provider.models?.length || 0 },
                {
                  title: '模型类型覆盖',
                  key: 'coverage',
                  width: 320,
                  render: (_, provider) => (
                    <Space wrap size={[6, 6]}>
                      {Array.from(new Set((provider.models || []).map((item) => item.model_type))).slice(0, 5).map((type) => (
                        <Tag key={`${provider.id}-${type}`} color={MODEL_TYPE_COLOR[type] || 'default'} style={{ margin: 0 }}>{MODEL_TYPE_NAME[type] || type}</Tag>
                      ))}
                    </Space>
                  ),
                },
                { title: '创建时间', key: 'created_at', width: 120, render: (_, provider) => (provider.created_at ? provider.created_at.slice(0, 10) : '-') },
                {
                  title: '操作',
                  key: 'actions',
                  width: 300,
                  render: (_, provider) => (
                    <Space wrap>
                      <Button size="small" icon={<RadarChartOutlined />} loading={healthCheckingIds.includes(provider.id)} onClick={() => checkProviderHealth(provider.id)}>检测</Button>
                      <Button size="small" icon={<SyncOutlined />} onClick={() => handleSyncProvider(provider.id)}>同步</Button>
                      <Button size="small" icon={<SettingOutlined />} onClick={() => openManageModels(provider)}>模型</Button>
                      <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDeleteProvider(provider)}>移除</Button>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        )}

        <div
          style={{
            marginTop: 10,
            display: 'grid',
            gap: 10,
            gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
          }}
        >
          <Card bordered={false} style={{ borderRadius: 14 }} bodyStyle={{ padding: 12 }}>
              <Title level={5} style={{ marginTop: 0, marginBottom: 10 }}>默认模型映射</Title>
              <div style={{ maxHeight: 290, overflow: 'auto', paddingRight: 2 }}>
                {defaultModelsSnapshot.length ? (
                  <List
                    size="small"
                    dataSource={defaultModelsSnapshot}
                    renderItem={(item: any) => (
                      <List.Item style={{ paddingInline: 0 }}>
                        <Space direction="vertical" size={0}>
                          <Tag color={MODEL_TYPE_COLOR[item.model_type] || 'default'} style={{ margin: 0 }}>{MODEL_TYPE_NAME[item.model_type] || item.model_type}</Tag>
                          <Text>{item.model_name}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description="尚未配置默认模型" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </div>
            </Card>
            <Card bordered={false} style={{ borderRadius: 14 }} bodyStyle={{ padding: 12 }}>
              <Title level={5} style={{ marginTop: 0, marginBottom: 10 }}>能力覆盖分布</Title>
              <div style={{ maxHeight: 220, overflow: 'auto', paddingRight: 2 }}>
                <List
                  size="small"
                  dataSource={modelTypeDistribution}
                  locale={{ emptyText: '暂无模型数据' }}
                  renderItem={([type, count]) => (
                    <List.Item style={{ paddingInline: 0 }}>
                      <Space>
                        <Tag color={MODEL_TYPE_COLOR[type] || 'default'}>{MODEL_TYPE_NAME[type] || type}</Tag>
                        <Text>{count}</Text>
                      </Space>
                    </List.Item>
                  )}
                />
              </div>
              <Divider style={{ margin: '8px 0' }} />
              <Alert type="info" showIcon message="运营建议" description="优先保证 chat、embedding、vision 三类默认模型可用，再按业务扩展 rerank/reasoning/tts/stt。" />
            </Card>
        </div>
      </div>

      <Modal
        title="接入模型供应商"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        okText="确定"
        cancelText="取消"
        width={680}
        destroyOnClose
      >
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <Segmented block value={customMode} onChange={(value) => setCustomMode(value as 'template' | 'custom')} options={[{ label: '从模板接入 (推荐)', value: 'template' }, { label: '自定义接入', value: 'custom' }]} />
          <Form form={form} layout="vertical" onFinish={handleSubmit} autoComplete="off">
            {customMode === 'template' ? (
              <>
                <Form.Item name="template_name" label="供应商模板" rules={[{ required: true, message: '请选择模板' }]}>
                  <Select
                    showSearch
                    placeholder="搜索并选择供应商模板"
                    onChange={(value) => setSelectedTemplate(templates.find((t) => t.name === value))}
                    optionFilterProp="children"
                  >
                    {templates.map((template) => (
                      <Select.Option key={template.name} value={template.name}>{template.name}</Select.Option>
                    ))}
                  </Select>
                </Form.Item>
                <Form.Item name="display_name" label="显示名称（可选）">
                  <Input placeholder="默认使用模板名" autoComplete="off" />
                </Form.Item>
                {selectedTemplate && (
                  <Alert
                    type="info"
                    showIcon
                    message={selectedTemplate.description || '模板描述'}
                    description={
                      <Space wrap size={[6, 6]}>
                        {(selectedTemplate.supported_models || []).map((item: any, idx: number) => {
                          const type = item?.type || 'llm';
                          const name = item?.name || String(item);
                          return <Tag key={`${name}-${idx}`} color={MODEL_TYPE_COLOR[type] || 'default'}>{name}</Tag>;
                        })}
                      </Space>
                    }
                  />
                )}
              </>
            ) : (
              <>
                <Form.Item name="display_name" label="供应商名称" rules={[{ required: true, message: '请输入供应商名称' }]}>
                  <Input placeholder="例如：我的私有网关" autoComplete="off" />
                </Form.Item>
                <Form.Item name="api_base" label="API Base URL" rules={[{ required: true, message: '请输入 API Base URL' }]}>
                  <Input placeholder="https://api.example.com/v1" autoComplete="off" />
                </Form.Item>
              </>
            )}
            <Form.Item name="api_key" label="API Key" rules={[{ required: true, message: '请输入 API Key' }]}>
              <Input.Password placeholder="将加密存储" autoComplete="new-password" visibilityToggle={false} />
            </Form.Item>
          </Form>
        </Space>
      </Modal>

      <Modal
        title={<Space><DatabaseOutlined /><span>{currentProvider?.display_name || '供应商'} · 模型能力管理</span></Space>}
        open={manageModalVisible}
        onCancel={() => setManageModalVisible(false)}
        footer={null}
        width={900}
      >
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <Card size="small" style={{ borderRadius: 14, background: '#f8fafc' }}>
            <Space direction="vertical" size={4}>
              <Text type="secondary">API Base</Text>
              <Text code>{currentProvider?.api_base}</Text>
            </Space>
          </Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Title level={5} style={{ margin: 0 }}>已配置模型 ({currentProvider?.models?.length || 0})</Title>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModelVisible(true)}>添加模型</Button>
          </div>
          <Table<ProviderModelItem>
            dataSource={currentProvider?.models || []}
            rowKey="id"
            pagination={false}
            size="middle"
            columns={[
              { title: '模型名称', dataIndex: 'model_name', key: 'model_name', render: (name: string, row) => <Space><Text strong>{name}</Text>{row.is_default && <Tag color="success" icon={<CheckCircleOutlined />}>默认</Tag>}</Space> },
              { title: '能力类型', dataIndex: 'model_type', key: 'model_type', width: 140, render: (type: string) => <Tag color={MODEL_TYPE_COLOR[type] || 'default'}>{MODEL_TYPE_NAME[type] || type}</Tag> },
              { title: '上下文', dataIndex: 'context_length', key: 'context_length', width: 120, render: (value: number) => (value >= 1024 ? `${Math.round(value / 1024)}K` : value) },
              { title: '最大输出', dataIndex: 'max_output_tokens', key: 'max_output_tokens', width: 120, render: (value: number | null | undefined) => value || '-' },
              { title: '操作', key: 'op', width: 80, render: (_, row) => <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleDeleteModel(row.id)} /> },
            ]}
          />
        </Space>

        <Modal
          title="添加模型配置"
          open={addModelVisible}
          onCancel={() => setAddModelVisible(false)}
          onOk={() => modelForm.submit()}
          okText="确定"
          cancelText="取消"
          destroyOnClose
        >
          <Form form={modelForm} layout="vertical" onFinish={handleAddModel} initialValues={{ model_type: 'llm', context_length: 4096 }}>
            <Form.Item name="model_name" label="模型名称" rules={[{ required: true, message: '请输入模型名称' }]}>
              <Input placeholder="例如：gpt-4o / qwen-plus" />
            </Form.Item>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="model_type" label="类型">
                  <Select options={[{ label: '聊天 (LLM)', value: 'llm' }, { label: '向量 (Embedding)', value: 'embedding' }, { label: '重排 (Rerank)', value: 'rerank' }, { label: '视觉 (Vision)', value: 'vision' }, { label: '推理 (Reasoning)', value: 'reasoning' }, { label: '语音 (TTS)', value: 'tts' }, { label: '语音 (STT)', value: 'stt' }]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="context_length" label="上下文长度">
                  <Input type="number" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="max_output_tokens" label="最大输出（可选）">
              <Input type="number" />
            </Form.Item>
          </Form>
        </Modal>
      </Modal>

      <Drawer
        title="系统全局默认模型"
        placement="right"
        width={420}
        onClose={() => setDefaultModelsVisible(false)}
        open={defaultModelsVisible}
        extra={
          <Space>
            <Button onClick={() => setDefaultModelsVisible(false)}>取消</Button>
            <Button type="primary" loading={savingDefaults} onClick={() => defaultsForm.submit()}>保存配置</Button>
          </Space>
        }
      >
        <Alert type="info" showIcon message="配置建议" description="若专家未显式指定模型，将回退到这里的默认选型。建议优先配置 chat、embedding、vision。" style={{ marginBottom: 18 }} />
        <Form form={defaultsForm} layout="vertical" onFinish={saveDefaults}>
          <Divider orientation="left" style={{ marginTop: 0 }}>核心基础</Divider>
          <Form.Item name="llm" label="默认语言模型 (LLM)"><Select allowClear showSearch optionLabelProp="label">{renderModelOptions('chat')}</Select></Form.Item>
          <Form.Item name="embedding" label="默认向量模型 (Embedding)"><Select allowClear showSearch optionLabelProp="label">{renderModelOptions('embedding')}</Select></Form.Item>
          <Form.Item name="vision" label="默认视觉模型 (Vision)"><Select allowClear showSearch optionLabelProp="label">{renderModelOptions('vision')}</Select></Form.Item>
          <Divider orientation="left">增强能力</Divider>
          <Form.Item name="reasoning" label="默认推理模型 (Reasoning)"><Select allowClear showSearch optionLabelProp="label">{renderModelOptions('reasoning')}</Select></Form.Item>
          <Form.Item name="rerank" label="默认重排序模型 (Rerank)"><Select allowClear showSearch optionLabelProp="label">{renderModelOptions('rerank')}</Select></Form.Item>
          <Form.Item name="tts" label="默认语音模型 (TTS)"><Select allowClear showSearch optionLabelProp="label">{renderModelOptions('tts')}</Select></Form.Item>
          <Form.Item name="stt" label="默认识别模型 (STT)"><Select allowClear showSearch optionLabelProp="label">{renderModelOptions('stt')}</Select></Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default ProviderManager;
