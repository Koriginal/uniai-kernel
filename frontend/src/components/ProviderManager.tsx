import React, { useState } from 'react';
import {
  Typography, Button, Card, Tag, Modal, Form, Input, Select,
  Empty, Row, Col, Segmented, Table, Space, Drawer, Divider, Alert, message
} from 'antd';
import {
  PlusOutlined, SettingOutlined, DeleteOutlined, SyncOutlined,
  GlobalOutlined, CheckCircleOutlined, DatabaseOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;

interface ProviderManagerProps {
  modelConfigs: any[];
  msgApi: any;
  onRefresh: () => void;
}

const ProviderManager: React.FC<ProviderManagerProps> = ({ modelConfigs, msgApi, onRefresh }) => {
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
    },
    info: (content: string) => {
      if (msgApi?.info) msgApi.info(content);
      else message.info(content);
    }
  };

  const [modalVisible, setModalVisible] = useState(false);
  const [customMode, setCustomMode] = useState<string | number>('template');
  const [templates, setTemplates] = useState<any[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null);

  // 模型管理子面板状态
  const [manageModalVisible, setManageModalVisible] = useState(false);
  const [currentProvider, setCurrentProvider] = useState<any>(null);
  const [addModelVisible, setAddModelVisible] = useState(false);
  const [modelForm] = Form.useForm();

  // 默认模型全局设置状态
  const [defaultModelsVisible, setDefaultModelsVisible] = useState(false);
  const [defaultsForm] = Form.useForm();
  const [savingDefaults, setSavingDefaults] = useState(false);

  const fetchTemplates = async () => {
    try {
      const res = await axios.get('/api/v1/providers/templates');
      setTemplates(res.data);
    } catch { notify.error('获取模板失败'); }
  };

  const openAddModal = () => {
    fetchTemplates();
    form.resetFields();
    setSelectedTemplate(null);
    setModalVisible(true);
  };

  const openManageModels = (provider: any) => {
    setCurrentProvider(provider);
    setManageModalVisible(true);
  };

  const handleAddModel = async (values: any) => {
    try {
      await axios.post(`/api/v1/providers/my/providers/${currentProvider.id}/models`, values);
      notify.success('模型已添加');
      setAddModelVisible(false);
      modelForm.resetFields();
      onRefresh();
      const res = await axios.get(`/api/v1/providers/my/providers/${currentProvider.id}/models`);
      setCurrentProvider({ ...currentProvider, models: res.data });
    } catch { notify.error('添加失败'); }
  };

  const handleDeleteModel = async (modelId: number) => {
    try {
      await axios.delete(`/api/v1/providers/my/providers/${currentProvider.id}/models/${modelId}`);
      notify.success('已删除');
      const res = await axios.get(`/api/v1/providers/my/providers/${currentProvider.id}/models`);
      setCurrentProvider({ ...currentProvider, models: res.data });
      onRefresh();
    } catch { notify.error('删除失败'); }
  };

  const handleSubmit = async (values: any) => {
    try {
      const payload = {
        template_name: customMode === 'template' ? values.template_name : null,
        display_name: values.display_name,
        api_base: values.api_base,
        api_key: values.api_key,
        custom_config: {}
      };
      await axios.post('/api/v1/providers/my/providers', payload);
      notify.success('供应商接入成功');
      setModalVisible(false);
      onRefresh();
    } catch { notify.error('接入失败'); }
  };

  const handleSyncProvider = async (id: number) => {
    try {
      const res = await axios.post(`/api/v1/providers/my/providers/${id}/sync`);
      if (res.data.status === 'synced') {
        notify.success(`同步成功：新增 ${res.data.added} 个，更新 ${res.data.updated} 个模型`);
      } else {
        notify.info(res.data.message || '已是最新版本');
      }
      onRefresh();
    } catch { notify.error('同步失败'); }
  };

  const handleDeleteProvider = (id: number, name: string) => {
    Modal.confirm({
      title: `确认移除供应商 ${name}？`,
      content: '该供应商下的所有模型配置也将被同步移除。',
      okText: '确认移除',
      okType: 'danger',
      onOk: async () => {
        try {
          await axios.delete(`/api/v1/providers/my/providers/${id}`);
          notify.success('已移除');
          onRefresh();
        } catch { notify.error('移除失败'); }
      }
    });
  };

  const openDefaultModels = async () => {
    try {
      const res = await axios.get('/api/v1/providers/my/default-models');
      const initialValues: any = {};
      res.data.forEach((item: any) => {
        initialValues[item.model_type] = `${item.provider_id}:${item.model_name}`;
      });
      defaultsForm.setFieldsValue(initialValues);
      setDefaultModelsVisible(true);
    } catch { notify.error('获取配置失败'); }
  };

  const saveDefaults = async (values: any) => {
    console.log('Saving default models:', values);
    setSavingDefaults(true);
    try {
      for (const [type, val] of Object.entries(values)) {
        if (!val) continue;
        const [pid, name] = (val as string).split(':');
        await axios.put('/api/v1/providers/my/default-models', {
          model_type: type,
          model_name: name,
          provider_id: parseInt(pid)
        });
      }
      notify.success('全局默认模型已保存');
      setDefaultModelsVisible(false);
      onRefresh();
    } catch (err: any) {
      console.error('Save defaults error:', err);
      notify.error(err.response?.data?.detail || '保存失败');
    }
    finally { setSavingDefaults(false); }
  };

  const typeColors: Record<string, string> = {
    'chat': 'blue',
    'llm': 'blue',
    'embedding': 'green',
    'rerank': 'purple',
    'vision': 'cyan',
    'reasoning': 'magenta',
    'tts': 'orange',
    'stt': 'gold'
  };

  const getTypeName = (type: string) => {
    const names: Record<string, string> = {
      'chat': '对话 (Chat)',
      'llm': '对话 (Chat)',
      'embedding': '向量 (Embed)',
      'rerank': '重排 (Rank)',
      'vision': '视觉 (Vision)',
      'reasoning': '推理 (Think)',
      'tts': '语音 (TTS)',
      'stt': '语音 (STT)'
    };
    return names[type] || type;
  };

  const renderModelOptions = (type: string) => {
    return modelConfigs.map(p => {
      const filtered = (p.models || []).filter((m: any) => {
          let mtype = m.model_type === 'llm' ? 'chat' : m.model_type;
          const lowerName = m.model_name.toLowerCase();
          // 前端语义识别：识别 vl/vision/r1/o1 等模型
          if (lowerName.includes('vl') || lowerName.includes('vision')) mtype = 'vision';
          else if (lowerName.includes('-r1') || lowerName.includes('reasoner') || lowerName.startsWith('o1') || lowerName.startsWith('o3')) mtype = 'reasoning';
          
          return mtype === type;
      });
      if (filtered.length === 0) return null;

      return (
        <Select.OptGroup key={p.id} label={p.display_name}>
            {filtered.map((m: any) => (
            <Select.Option key={`${p.id}:${m.model_name}`} value={`${p.id}:${m.model_name}`} label={m.model_name}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '13px' }}>{m.model_name}</span>
                    <Tag bordered={false} style={{ fontSize: '10px', scale: '0.9', margin: 0 }}>
                        {m.context_length >= 1024 ? `${Math.round(m.context_length / 1024)}K` : m.context_length}
                    </Tag>
                </div>
            </Select.Option>
            ))}
        </Select.OptGroup>
      );
    });
  };

  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%', background: '#fafafa' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>模型供应商</Title>
          <Text type="secondary">管理 API 接入、配置模型参数以及设置系统默认模型</Text>
        </div>
        <Space>
          <Button icon={<GlobalOutlined />} onClick={openDefaultModels}>默认模型设置</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal}>接入供应商</Button>
        </Space>
      </div>

      {modelConfigs.length === 0 ? (
        <Empty description="尚未配置任何模型供应商" />
      ) : (
        <Row gutter={[16, 16]}>
          {modelConfigs.map((p) => (
            <Col key={p.id} xs={24} sm={12} lg={8}>
              <Card
                hoverable
                className="provider-card"
                style={{ height: '100%', borderRadius: '12px', border: '1px solid #f0f0f0', overflow: 'hidden' }}
                actions={[
                  <Space key="sync" onClick={() => handleSyncProvider(p.id)} style={{ width: '100%', justifyContent: 'center' }}>
                    <SyncOutlined /> <Text style={{ fontSize: '12px' }}>同步模型</Text>
                  </Space>,
                  <Space key="manage" onClick={() => openManageModels(p)} style={{ width: '100%', justifyContent: 'center' }}>
                    <SettingOutlined /> <Text style={{ fontSize: '12px' }}>管理模型</Text>
                  </Space>,
                  <Text key="del" type="danger" onClick={() => handleDeleteProvider(p.id, p.display_name)} style={{ cursor: 'pointer', display: 'inline-block' }}>
                    <DeleteOutlined /> 移除
                  </Text>
                ]}
              >
                <Card.Meta
                  title={
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong style={{ fontSize: '16px' }}>{p.display_name}</Text>
                      <Tag color="geekblue" style={{ borderRadius: '4px' }}>{p.provider_type.toUpperCase()}</Tag>
                    </div>
                  }
                  description={
                    <div style={{ marginTop: 12 }}>
                      <Text type="secondary" style={{ fontSize: '12px', marginBottom: 12, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {p.api_base}
                      </Text>
                      <div style={{ minHeight: '60px' }}>
                        {p.models && p.models.length > 0 ? (
                          <Space wrap size={[4, 8]}>
                            {p.models.map((m: any) => (
                              <Tag 
                                key={m.id} 
                                color={typeColors[m.model_type] || 'default'} 
                                bordered={false} 
                                style={{ fontSize: '11px', borderRadius: '4px' }}
                              >
                                {m.model_name}
                              </Tag>
                            ))}
                          </Space>
                        ) : (
                          <Text type="secondary" style={{ fontSize: '12px', fontStyle: 'italic' }}>暂未配置模型</Text>
                        )}
                      </div>
                    </div>
                  }
                />
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* 接入供应商 Modal */}
      <Modal
        title="接入模型供应商"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={600}
        destroyOnClose
      >
        <div style={{ marginBottom: 24 }}>
          <Segmented
            block
            value={customMode}
            onChange={setCustomMode}
            options={[
              { label: '从模板接入 (推荐)', value: 'template' },
              { label: '自定义接入', value: 'custom' },
            ]}
          />
        </div>

        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          {customMode === 'template' ? (
            <>
              <Form.Item name="template_name" label="供应商模板" rules={[{ required: true }]}>
                <Select
                  size="large"
                  placeholder="搜索并选择供应商..."
                  onChange={(val) => setSelectedTemplate(templates.find(t => t.name === val))}
                  showSearch
                >
                  {templates.map(t => (
                    <Select.Option key={t.name} value={t.name}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>{t.name}</span>
                        <Space>
                          {t.is_free && <Tag color="green">Free</Tag>}
                          <Tag bordered={false} style={{ fontSize: '10px' }}>{t.provider_type}</Tag>
                        </Space>
                      </div>
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>
              {selectedTemplate && (
                <div style={{ background: '#f5f7fa', padding: '16px', borderRadius: '8px', marginBottom: '24px', border: '1px solid #eef1f6' }}>
                  <Text type="secondary" style={{ fontSize: '13px', display: 'block', marginBottom: '12px' }}>{selectedTemplate.description}</Text>
                  <div>
                    <Text strong style={{ fontSize: '12px', display: 'block', marginBottom: '8px' }}>包含能力：</Text>
                    <Space wrap>
                      {(selectedTemplate.supported_models || []).map((m: any) => (
                        <Tag key={m.name} color={typeColors[m.type] || 'default'} style={{ fontSize: '11px', borderRadius: '4px' }}>
                          {m.name}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                </div>
              )}
            </>
          ) : (
            <Form.Item name="display_name" label="供应商名称" rules={[{ required: true }]}>
              <Input size="large" placeholder="e.g. 我的私有中转" />
            </Form.Item>
          )}

          {customMode === 'custom' && (
            <Form.Item
              name="api_base"
              label="API Base URL"
              rules={[{ required: true, message: '请输入 API Base' }]}
            >
              <Input size="large" placeholder="https://api.example.com/v1" />
            </Form.Item>
          )}

          <Form.Item name="api_key" label="API Key" rules={[{ required: true }]}>
            <Input.Password size="large" placeholder="输入 API 密钥 (将加密存储)" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 模型详情管理 Modal */}
      <Modal
        title={
          <Space>
            <DatabaseOutlined />
            <span>{currentProvider?.display_name} — 模型能力管理</span>
          </Space>
        }
        open={manageModalVisible}
        onCancel={() => setManageModalVisible(false)}
        footer={null}
        width={800}
      >
        <div style={{ background: '#f0f2f5', padding: '12px 16px', borderRadius: '6px', marginBottom: 24 }}>
          <Row gutter={24}>
            <Col span={16}>
              <Text type="secondary" style={{ fontSize: '12px' }}>API Base: </Text>
              <Text code style={{ fontSize: '12px' }}>{currentProvider?.api_base}</Text>
            </Col>
            <Col span={8} style={{ textAlign: 'right' }}>
              <Tag color="blue">{currentProvider?.provider_type}</Tag>
            </Col>
          </Row>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={5} style={{ margin: 0 }}>已配置模型 ({currentProvider?.models?.length || 0})</Title>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModelVisible(true)}>添加模型</Button>
        </div>

        <Table
          dataSource={currentProvider?.models || []}
          rowKey="id"
          pagination={false}
          size="middle"
          columns={[
            { 
              title: '模型名称', 
              dataIndex: 'model_name', 
              key: 'name', 
              render: (t: any, r: any) => (
                <Space>
                  <Text strong>{t}</Text>
                  {r.is_default && <Tag color="success" icon={<CheckCircleOutlined />}>默认</Tag>}
                </Space>
              ) 
            },
            { 
              title: '能力类型', 
              dataIndex: 'model_type', 
              key: 'type', 
              render: (t: any) => (
                <Tag color={typeColors[t] || 'default'}>{getTypeName(t)}</Tag>
              ) 
            },
            { 
              title: '上下文', 
              dataIndex: 'context_length', 
              key: 'ctx', 
              render: v => <Text type="secondary">{v >= 1024 ? `${Math.round(v / 1024)}K` : v}</Text> 
            },
            {
              title: '操作', 
              key: 'op', 
              width: 80,
              render: (_: any, r: any) => (
                <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleDeleteModel(r.id)} />
              )
            }
          ]}
        />

        <Modal
          title="添加模型配置"
          open={addModelVisible}
          onCancel={() => setAddModelVisible(false)}
          onOk={() => modelForm.submit()}
          destroyOnClose
        >
          <Form form={modelForm} layout="vertical" onFinish={handleAddModel} initialValues={{ model_type: 'llm', context_length: 4096 }}>
            <Form.Item name="model_name" label="模型名称" rules={[{ required: true }]}>
              <Input placeholder="e.g. gpt-4o" />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="model_type" label="类型">
                  <Select options={[
                    { label: '聊天 (LLM)', value: 'llm' },
                    { label: '向量 (Embedding)', value: 'embedding' },
                    { label: '重排 (Rerank)', value: 'rerank' },
                    { label: '语音 (TTS/STT)', value: 'tts' },
                  ]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="context_length" label="上下文长度 (Tokens)">
                  <Input type="number" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="max_output_tokens" label="最大输出 (可选)">
              <Input placeholder="默认模型限制" />
            </Form.Item>
          </Form>
        </Modal>
      </Modal>

      {/* 默认模型全局设置 Drawer */}
      <Drawer
        title="系统全局默认模型"
        placement="right"
        width={400}
        onClose={() => setDefaultModelsVisible(false)}
        open={defaultModelsVisible}
        extra={
          <Space>
            <Button onClick={() => setDefaultModelsVisible(false)}>取消</Button>
            <Button type="primary" loading={savingDefaults} onClick={() => defaultsForm.submit()}>保存配置</Button>
          </Space>
        }
      >
        <Alert
          message="配置建议"
          description="在此设置系统核心任务的默认选型。若智能体未指定模型，将自动回退到此处配置。"
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
        />
        <Form form={defaultsForm} layout="vertical" onFinish={saveDefaults}>
          <Divider orientation="left" style={{ marginTop: 0 }}>核心基础</Divider>
          <Form.Item name="llm" label="默认语言模型 (LLM)">
            <Select placeholder="选择默认 LLM..." allowClear showSearch optionLabelProp="label">
              {renderModelOptions('chat')}
            </Select>
          </Form.Item>

          <Form.Item name="embedding" label="默认向量模型 (Embedding)">
            <Select placeholder="选择默认 Embedding..." allowClear showSearch optionLabelProp="label">
              {renderModelOptions('embedding')}
            </Select>
          </Form.Item>

          <Form.Item name="vision" label="默认视觉模型 (Vision)">
            <Select placeholder="选择默认 Vision 模型..." allowClear showSearch optionLabelProp="label">
              {renderModelOptions('vision')}
            </Select>
          </Form.Item>

          <Divider orientation="left">增强能力</Divider>
          <Form.Item name="rerank" label="默认重排序模型 (Rerank)">
            <Select placeholder="选择默认 Rerank..." allowClear showSearch optionLabelProp="label">
              {renderModelOptions('rerank')}
            </Select>
          </Form.Item>

          <Form.Item name="tts" label="默认语音模型 (TTS)">
            <Select placeholder="选择默认 TTS..." allowClear showSearch optionLabelProp="label">
              {renderModelOptions('tts')}
            </Select>
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default ProviderManager;
