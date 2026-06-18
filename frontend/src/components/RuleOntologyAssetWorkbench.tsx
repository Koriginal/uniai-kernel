import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Drawer, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Typography, Upload, message } from 'antd';
import { CheckCircleOutlined, FileTextOutlined, PlusOutlined, ReloadOutlined, ToolOutlined, UploadOutlined } from '@ant-design/icons';
import type { AxiosInstance } from 'axios';
import './ruleWorkbench.css';

const { Text, Title } = Typography;

interface Props {
  api: AxiosInstance;
}

interface SpaceItem {
  id: string;
  name: string;
  code: string;
  description?: string;
}

interface RuleSourceDocument {
  id: string;
  space_id: string;
  title: string;
  source_type: string;
  file_name?: string;
  content_hash: string;
  raw_text?: string;
  metadata: Record<string, unknown>;
  status: string;
  created_at: string;
}

interface RuleEntry {
  id: string;
  space_id: string;
  source_document_id?: string;
  rule_code: string;
  name: string;
  target_entity_type?: string;
  conditions: Record<string, unknown>[];
  severity: string;
  action: string;
  evidence_refs: Record<string, unknown>[];
  test_cases: Record<string, unknown>[];
  tags: string[];
  status: string;
  version: string;
  created_by: string;
  reviewed_by?: string;
  review_note?: string;
  created_at: string;
}

interface OntologyTerm {
  id: string;
  space_id: string;
  source_document_id?: string;
  term_code: string;
  name: string;
  kind: string;
  description?: string;
  entity_type?: string;
  data_type?: string;
  required: boolean;
  enum_values: string[];
  relation_target_type?: string;
  relation_cardinality?: string;
  aliases: string[];
  evidence_refs: Record<string, unknown>[];
  status: string;
  version: string;
  created_by: string;
}

const sourceTypes = [
  { label: '制度文件', value: 'policy_doc' },
  { label: '合同模板', value: 'contract_template' },
  { label: '审核手册', value: 'review_manual' },
  { label: '监管规则', value: 'regulation' },
  { label: '历史案例', value: 'historical_case' },
  { label: '数据库结构', value: 'database_schema' },
  { label: 'API 结构', value: 'api_schema' },
  { label: '手工说明', value: 'custom_note' },
];

const severityColors: Record<string, string> = {
  low: 'default',
  medium: 'blue',
  high: 'orange',
  critical: 'red',
};

const termKinds = [
  { label: '实体', value: 'entity' },
  { label: '字段', value: 'attribute' },
  { label: '关系', value: 'relation' },
  { label: '枚举', value: 'enum' },
  { label: '分类', value: 'taxonomy' },
  { label: '词表', value: 'vocabulary' },
];

const dataTypes = ['string', 'number', 'integer', 'boolean', 'array', 'object'].map((value) => ({ label: value, value }));

const statusColors: Record<string, string> = {
  uploaded: 'default',
  parsed: 'blue',
  reviewed: 'green',
  draft: 'default',
  reviewing: 'gold',
  approved: 'green',
  rejected: 'red',
  packaged: 'purple',
  released: 'cyan',
  deprecated: 'default',
};

const parseJsonField = (value: string | undefined, fallback: unknown) => {
  if (!value || !value.trim()) return fallback;
  return JSON.parse(value);
};

const RuleOntologyAssetWorkbench: React.FC<Props> = ({ api }) => {
  const [sourceForm] = Form.useForm();
  const [ruleForm] = Form.useForm();
  const [termForm] = Form.useForm();
  const [compileForm] = Form.useForm();
  const [schemaCompileForm] = Form.useForm();
  const [spaces, setSpaces] = useState<SpaceItem[]>([]);
  const [spaceId, setSpaceId] = useState<string>('');
  const [sources, setSources] = useState<RuleSourceDocument[]>([]);
  const [rules, setRules] = useState<RuleEntry[]>([]);
  const [terms, setTerms] = useState<OntologyTerm[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourceDrawerOpen, setSourceDrawerOpen] = useState(false);
  const [ruleDrawerOpen, setRuleDrawerOpen] = useState(false);
  const [termDrawerOpen, setTermDrawerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sourceFile, setSourceFile] = useState<File | null>(null);

  const sourceOptions = useMemo(
    () => sources.map((item) => ({ label: item.title, value: item.id })),
    [sources],
  );

  const approvedRuleOptions = useMemo(
    () => rules
      .filter((item) => item.status === 'approved')
      .map((item) => ({ label: `${item.rule_code} · ${item.name}`, value: item.id })),
    [rules],
  );

  const approvedTermOptions = useMemo(
    () => terms
      .filter((item) => item.status === 'approved')
      .map((item) => ({ label: `${item.term_code} · ${item.name}`, value: item.id })),
    [terms],
  );
  const approvedRuleCount = useMemo(() => rules.filter((item) => item.status === 'approved' || item.status === 'packaged' || item.status === 'released').length, [rules]);
  const approvedTermCount = useMemo(() => terms.filter((item) => item.status === 'approved' || item.status === 'packaged' || item.status === 'released').length, [terms]);

  const loadSpaces = useCallback(async () => {
    const res = await api.get('/api/v1/ontology/spaces');
    const items = res.data || [];
    setSpaces(items);
    setSpaceId((current) => current || items[0]?.id || '');
  }, [api]);

  const loadAssets = useCallback(async (targetSpaceId: string) => {
    if (!targetSpaceId) return;
    setLoading(true);
    try {
      const [sourceRes, ruleRes, termRes] = await Promise.allSettled([
        api.get(`/api/v1/ontology/asset-sources/${targetSpaceId}`),
        api.get(`/api/v1/ontology/rule-entries/${targetSpaceId}`),
        api.get(`/api/v1/ontology/terms/${targetSpaceId}`),
      ]);
      setSources(sourceRes.status === 'fulfilled' ? (sourceRes.value.data || []) : []);
      setRules(ruleRes.status === 'fulfilled' ? (ruleRes.value.data || []) : []);
      setTerms(termRes.status === 'fulfilled' ? (termRes.value.data || []) : []);
      const failed = [
        sourceRes.status === 'rejected' ? '来源文档' : '',
        ruleRes.status === 'rejected' ? '规则条目' : '',
        termRes.status === 'rejected' ? '本体条目' : '',
      ].filter(Boolean);
      if (failed.length) {
        message.warning(`${failed.join('、')}读取失败，请检查后端迁移和服务日志`);
      }
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    loadSpaces().catch(() => setSpaces([]));
  }, [loadSpaces]);

  useEffect(() => {
    if (spaceId) loadAssets(spaceId);
  }, [loadAssets, spaceId]);

  const openSourceDrawer = () => {
    sourceForm.resetFields();
    sourceForm.setFieldsValue({ source_type: 'custom_note' });
    setSourceFile(null);
    setSourceDrawerOpen(true);
  };

  const openRuleDrawer = () => {
    ruleForm.resetFields();
    ruleForm.setFieldsValue({
      severity: 'medium',
      action: 'flag',
      conditions: '[\n  {\n    "path": "entity.amount",\n    "operator": "gt",\n    "value": 1000000\n  }\n]',
      evidence_refs: '[\n  {\n    "locator": "第 1 条"\n  }\n]',
      test_cases: '[]',
      tags: '',
      version: '1',
    });
    setRuleDrawerOpen(true);
  };

  const openTermDrawer = () => {
    termForm.resetFields();
    termForm.setFieldsValue({
      kind: 'entity',
      data_type: 'string',
      relation_cardinality: 'many',
      required: false,
      enum_values: '',
      aliases: '',
      evidence_refs: '[\n  {\n    "locator": "术语表"\n  }\n]',
      metadata: '{}',
      version: '1',
    });
    setTermDrawerOpen(true);
  };

  const createSource = async () => {
    const values = await sourceForm.validateFields();
    setSaving(true);
    try {
      if (sourceFile) {
        const formData = new FormData();
        formData.append('space_id', spaceId);
        formData.append('source_type', values.source_type || 'custom_note');
        if (values.title) formData.append('title', values.title);
        formData.append('file', sourceFile);
        const res = await api.post('/api/v1/ontology/asset-sources/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        if (res.data?.warnings?.length) {
          Modal.warning({
            title: '文档已上传，但文本抽取有提示',
            content: (
              <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(res.data.warnings, null, 2)}</pre>
            ),
          });
        }
      } else {
        await api.post('/api/v1/ontology/asset-sources', {
          ...values,
          space_id: spaceId,
          metadata: parseJsonField(values.metadata, {}),
        });
      }
      message.success('来源文档已登记');
      setSourceDrawerOpen(false);
      setSourceFile(null);
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '保存来源失败');
    } finally {
      setSaving(false);
    }
  };

  const parseSource = async (source: RuleSourceDocument) => {
    try {
      const res = await api.post(`/api/v1/ontology/asset-sources/${source.id}/parse`, { max_rules: 50 });
      const count = res.data?.rule_entries?.length || 0;
      message.success(`已生成 ${count} 条候选规则`);
      if (res.data?.warnings?.length) {
        Modal.info({
          title: '解析提示',
          width: 720,
          content: (
            <pre style={{ maxHeight: '50vh', overflow: 'auto', whiteSpace: 'pre-wrap', background: '#f8fafc', border: '1px solid #e5e7eb', padding: 12, borderRadius: 8 }}>
              {JSON.stringify(res.data.warnings, null, 2)}
            </pre>
          ),
        });
      }
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '解析来源文档失败');
    }
  };

  const showSource = (source: RuleSourceDocument) => {
    Modal.info({
      title: source.title,
      width: 760,
      content: (
        <pre style={{ maxHeight: '58vh', overflow: 'auto', whiteSpace: 'pre-wrap', background: '#f8fafc', border: '1px solid #e5e7eb', padding: 12, borderRadius: 8 }}>
          {source.raw_text || JSON.stringify(source, null, 2)}
        </pre>
      ),
    });
  };

  const createRule = async () => {
    const values = await ruleForm.validateFields();
    setSaving(true);
    try {
      await api.post('/api/v1/ontology/rule-entries', {
        ...values,
        space_id: spaceId,
        conditions: parseJsonField(values.conditions, []),
        evidence_refs: parseJsonField(values.evidence_refs, []),
        test_cases: parseJsonField(values.test_cases, []),
        tags: String(values.tags || '').split(',').map((item) => item.trim()).filter(Boolean),
      });
      message.success('规则条目已创建');
      setRuleDrawerOpen(false);
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '保存规则失败');
    } finally {
      setSaving(false);
    }
  };

  const createTerm = async () => {
    const values = await termForm.validateFields();
    setSaving(true);
    try {
      await api.post('/api/v1/ontology/terms', {
        ...values,
        space_id: spaceId,
        enum_values: String(values.enum_values || '').split(',').map((item) => item.trim()).filter(Boolean),
        aliases: String(values.aliases || '').split(',').map((item) => item.trim()).filter(Boolean),
        evidence_refs: parseJsonField(values.evidence_refs, []),
        metadata: parseJsonField(values.metadata, {}),
      });
      message.success('本体条目已创建');
      setTermDrawerOpen(false);
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '保存本体条目失败');
    } finally {
      setSaving(false);
    }
  };

  const submitReview = async (rule: RuleEntry) => {
    try {
      await api.post(`/api/v1/ontology/rule-entries/${rule.id}/submit-review`);
      message.success('已提交审核');
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '提交审核失败');
    }
  };

  const reviewRule = async (rule: RuleEntry, approve: boolean) => {
    try {
      await api.post(`/api/v1/ontology/rule-entries/${rule.id}/review`, {
        approve,
        review_note: approve ? 'approved in asset workbench' : 'rejected in asset workbench',
      });
      message.success(approve ? '规则已批准' : '规则已退回');
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '审核失败');
    }
  };

  const submitTermReview = async (term: OntologyTerm) => {
    try {
      await api.post(`/api/v1/ontology/terms/${term.id}/submit-review`);
      message.success('已提交审核');
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '提交审核失败');
    }
  };

  const reviewTerm = async (term: OntologyTerm, approve: boolean) => {
    try {
      await api.post(`/api/v1/ontology/terms/${term.id}/review`, {
        approve,
        review_note: approve ? 'approved in asset workbench' : 'rejected in asset workbench',
      });
      message.success(approve ? '本体条目已批准' : '本体条目已退回');
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '审核失败');
    }
  };

  const compileRules = async () => {
    const values = await compileForm.validateFields();
    try {
      const res = await api.post('/api/v1/ontology/assets/compile-rules', {
        space_id: spaceId,
        version: values.version,
        description: values.description,
        rule_entry_ids: values.rule_entry_ids,
      });
      message.success(`规则包已生成：${values.version}`);
      Modal.info({
        title: '规则包编译结果',
        width: 760,
        content: (
          <pre style={{ maxHeight: '58vh', overflow: 'auto', background: '#f8fafc', border: '1px solid #e5e7eb', padding: 12, borderRadius: 8 }}>
            {JSON.stringify(res.data, null, 2)}
          </pre>
        ),
      });
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '编译失败');
    }
  };

  const compileSchema = async () => {
    const values = await schemaCompileForm.validateFields();
    try {
      const res = await api.post('/api/v1/ontology/assets/compile-schema', {
        space_id: spaceId,
        version: values.version,
        description: values.description,
        term_ids: values.term_ids,
      });
      message.success(`本体包已生成：${values.version}`);
      Modal.info({
        title: '本体包编译结果',
        width: 760,
        content: (
          <pre style={{ maxHeight: '58vh', overflow: 'auto', background: '#f8fafc', border: '1px solid #e5e7eb', padding: 12, borderRadius: 8 }}>
            {JSON.stringify(res.data, null, 2)}
          </pre>
        ),
      });
      await loadAssets(spaceId);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '编译失败');
    }
  };

  return (
    <div className="rule-workbench-page">
      <section className="rule-workbench-hero">
        <div className="rule-workbench-title">
          <span className="rule-workbench-title-icon"><ToolOutlined /></span>
          <div className="rule-workbench-title-copy">
            <Title level={4}>规则与本体资产</Title>
            <Text type="secondary">维护通用规则、本体字段和运行时 package；评审知识库会复用同一个业务空间里的来源材料。</Text>
          </div>
        </div>
        <div className="rule-workbench-actions">
            <Select
              style={{ width: 260 }}
              placeholder="选择本体空间"
              value={spaceId || undefined}
              onChange={setSpaceId}
              options={spaces.map((item) => ({ label: `${item.name} (${item.code})`, value: item.id }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadAssets(spaceId)} disabled={!spaceId}>刷新</Button>
        </div>
      </section>

      <div className="rule-metric-strip">
        <div className="rule-metric"><div className="rule-metric-label">来源文档</div><div className="rule-metric-value">{sources.length}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">规则条目</div><div className="rule-metric-value">{rules.length}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">已确认规则</div><div className="rule-metric-value">{approvedRuleCount}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">本体条目</div><div className="rule-metric-value">{terms.length}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">已确认本体</div><div className="rule-metric-value">{approvedTermCount}</div></div>
      </div>

      {!spaceId ? (
        <Alert type="info" showIcon message="请先在本体治理台创建本体空间，再维护规则资产。" />
      ) : (
        <div className="rule-workflow-shell">
        <Tabs
          tabPosition="left"
          className="rule-workflow-tabs"
          items={[
            {
              key: 'sources',
              label: '来源文档',
              children: (
                <>
                  <div className="rule-stage-header">
                    <div className="rule-stage-title">
                      <strong>来源材料</strong>
                      <Text type="secondary">登记制度、合同模板、审核手册和历史案例。规则条目必须能追到这里。</Text>
                    </div>
                    <div className="rule-stage-actions">
                      <Button type="primary" icon={<PlusOutlined />} onClick={openSourceDrawer}>登记来源</Button>
                    </div>
                  </div>
                  <Table
                    className="rule-table-card"
                    rowKey="id"
                    loading={loading}
                    dataSource={sources}
                    pagination={{ pageSize: 8 }}
                    columns={[
                      { title: '标题', dataIndex: 'title', render: (value: string) => <Text strong>{value}</Text> },
                      { title: '类型', dataIndex: 'source_type', width: 140, render: (value: string) => <Tag>{value}</Tag> },
                      { title: '文件', dataIndex: 'file_name', width: 180, render: (value: string) => value || '-' },
                      { title: '状态', dataIndex: 'status', width: 120, render: (value: string) => <Tag color={statusColors[value]}>{value}</Tag> },
                      { title: 'Hash', dataIndex: 'content_hash', width: 180, render: (value: string) => <Text code>{value.slice(0, 12)}</Text> },
                      {
                        title: '操作',
                        width: 160,
                        render: (_: unknown, item: RuleSourceDocument) => (
                          <Space>
                            <Button size="small" icon={<FileTextOutlined />} onClick={() => showSource(item)}>原文</Button>
                            <Button size="small" type="primary" onClick={() => parseSource(item)}>解析</Button>
                          </Space>
                        ),
                      },
                    ]}
                  />
                </>
              ),
            },
            {
              key: 'rules',
              label: '规则条目',
              children: (
                <>
                  <div className="rule-stage-header">
                    <div className="rule-stage-title">
                      <strong>通用规则条目</strong>
                      <Text type="secondary">规则条目是运行规则包的来源，只有 approved 条目能进入编译。</Text>
                    </div>
                    <div className="rule-stage-actions">
                      <Button type="primary" icon={<PlusOutlined />} onClick={openRuleDrawer}>新建规则</Button>
                    </div>
                  </div>
                  <Table
                    className="rule-table-card"
                    rowKey="id"
                    loading={loading}
                    dataSource={rules}
                    pagination={{ pageSize: 8 }}
                    columns={[
                      {
                        title: '规则',
                        dataIndex: 'rule_code',
                        render: (_: string, item: RuleEntry) => (
                          <Space direction="vertical" size={2}>
                            <Text strong>{item.rule_code}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>{item.name}</Text>
                          </Space>
                        ),
                      },
                      { title: '目标实体', dataIndex: 'target_entity_type', width: 130, render: (value: string) => value || '-' },
                      { title: '严重度', dataIndex: 'severity', width: 100, render: (value: string) => <Tag color={severityColors[value]}>{value}</Tag> },
                      { title: '动作', dataIndex: 'action', width: 100, render: (value: string) => <Tag>{value}</Tag> },
                      { title: '状态', dataIndex: 'status', width: 110, render: (value: string) => <Tag color={statusColors[value]}>{value}</Tag> },
                      { title: '证据', dataIndex: 'evidence_refs', width: 90, render: (items: unknown[]) => <Tag>{items?.length || 0}</Tag> },
                      {
                        title: '操作',
                        width: 230,
                        render: (_: unknown, item: RuleEntry) => (
                          <Space>
                            <Button size="small" icon={<FileTextOutlined />} onClick={() => Modal.info({
                              title: item.rule_code,
                              width: 720,
                              content: (
                                <pre style={{ maxHeight: '58vh', overflow: 'auto', whiteSpace: 'pre-wrap', background: '#f8fafc', border: '1px solid #e5e7eb', padding: 12, borderRadius: 8 }}>
                                  {JSON.stringify(item, null, 2)}
                                </pre>
                              ),
                            })}>详情</Button>
                            {(item.status === 'draft' || item.status === 'rejected') && (
                              <Button size="small" onClick={() => submitReview(item)}>提交</Button>
                            )}
                            {item.status === 'reviewing' && (
                              <>
                                <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => reviewRule(item, true)}>通过</Button>
                                <Button size="small" danger onClick={() => reviewRule(item, false)}>退回</Button>
                              </>
                            )}
                          </Space>
                        ),
                      },
                    ]}
                  />
                </>
              ),
            },
            {
              key: 'terms',
              label: '本体条目',
              children: (
                <>
                  <div className="rule-stage-header">
                    <div className="rule-stage-title">
                      <strong>本体条目</strong>
                      <Text type="secondary">实体、字段、关系和枚举必须先成为 approved 条目，再进入 schema package。</Text>
                    </div>
                    <div className="rule-stage-actions">
                      <Button type="primary" icon={<PlusOutlined />} onClick={openTermDrawer}>新建本体条目</Button>
                    </div>
                  </div>
                  <Table
                    className="rule-table-card"
                    rowKey="id"
                    loading={loading}
                    dataSource={terms}
                    pagination={{ pageSize: 8 }}
                    columns={[
                      {
                        title: '条目',
                        dataIndex: 'term_code',
                        render: (_: string, item: OntologyTerm) => (
                          <Space direction="vertical" size={2}>
                            <Text strong>{item.term_code}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>{item.name}</Text>
                          </Space>
                        ),
                      },
                      { title: '类型', dataIndex: 'kind', width: 100, render: (value: string) => <Tag color="blue">{value}</Tag> },
                      { title: '实体', dataIndex: 'entity_type', width: 130, render: (value: string) => value || '-' },
                      { title: '字段类型', dataIndex: 'data_type', width: 110, render: (value: string) => value || '-' },
                      { title: '状态', dataIndex: 'status', width: 110, render: (value: string) => <Tag color={statusColors[value]}>{value}</Tag> },
                      {
                        title: '操作',
                        width: 240,
                        render: (_: unknown, item: OntologyTerm) => (
                          <Space>
                            <Button size="small" icon={<FileTextOutlined />} onClick={() => Modal.info({
                              title: item.term_code,
                              width: 720,
                              content: (
                                <pre style={{ maxHeight: '58vh', overflow: 'auto', whiteSpace: 'pre-wrap', background: '#f8fafc', border: '1px solid #e5e7eb', padding: 12, borderRadius: 8 }}>
                                  {JSON.stringify(item, null, 2)}
                                </pre>
                              ),
                            })}>详情</Button>
                            {(item.status === 'draft' || item.status === 'rejected') && (
                              <Button size="small" onClick={() => submitTermReview(item)}>提交</Button>
                            )}
                            {item.status === 'reviewing' && (
                              <>
                                <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => reviewTerm(item, true)}>通过</Button>
                                <Button size="small" danger onClick={() => reviewTerm(item, false)}>退回</Button>
                              </>
                            )}
                          </Space>
                        ),
                      },
                    ]}
                  />
                </>
              ),
            },
            {
              key: 'compile',
              label: '编译规则包',
              children: (
                <Card style={{ borderRadius: 8 }}>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="这里只从 approved 规则条目生成 draft rule package。后续仍然要去本体治理台提交审批并发布到 staging/ga。"
                  />
                  <Form form={compileForm} layout="vertical" style={{ maxWidth: 720 }}>
                    <Form.Item name="version" label="规则包版本" rules={[{ required: true, message: '请输入 semver 版本，例如 1.0.0' }]}>
                      <Input placeholder="1.0.0" />
                    </Form.Item>
                    <Form.Item name="description" label="说明">
                      <Input.TextArea rows={3} placeholder="本次规则包包含的业务变更。" />
                    </Form.Item>
                    <Form.Item name="rule_entry_ids" label="规则条目">
                      <Select mode="multiple" allowClear options={approvedRuleOptions} placeholder="留空表示编译当前空间全部 approved 规则" />
                    </Form.Item>
                    <Button type="primary" onClick={compileRules}>编译规则包</Button>
                  </Form>
                </Card>
              ),
            },
            {
              key: 'compile-schema',
              label: '编译本体包',
              children: (
                <Card style={{ borderRadius: 8 }}>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="这里只从 approved 本体条目生成 draft schema package。后续仍然要去本体治理台提交审批并发布。"
                  />
                  <Form form={schemaCompileForm} layout="vertical" style={{ maxWidth: 720 }}>
                    <Form.Item name="version" label="本体包版本" rules={[{ required: true, message: '请输入 semver 版本，例如 1.0.0' }]}>
                      <Input placeholder="1.0.0" />
                    </Form.Item>
                    <Form.Item name="description" label="说明">
                      <Input.TextArea rows={3} placeholder="本次本体包包含的实体、字段和关系变更。" />
                    </Form.Item>
                    <Form.Item name="term_ids" label="本体条目">
                      <Select mode="multiple" allowClear options={approvedTermOptions} placeholder="留空表示编译当前空间全部 approved 本体条目" />
                    </Form.Item>
                    <Button type="primary" onClick={compileSchema}>编译本体包</Button>
                  </Form>
                </Card>
              ),
            },
          ]}
        />
        </div>
      )}

      <Drawer title="登记来源文档" width={560} open={sourceDrawerOpen} onClose={() => setSourceDrawerOpen(false)}
        extra={<Button type="primary" loading={saving} onClick={createSource}>保存</Button>}>
        <Form form={sourceForm} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入来源标题' }]}>
            <Input placeholder="合同审核手册 v2026.01" />
          </Form.Item>
          <Form.Item name="source_type" label="来源类型" rules={[{ required: true }]}>
            <Select options={sourceTypes} />
          </Form.Item>
          <Form.Item label="上传文件">
            <Upload
              maxCount={1}
              beforeUpload={(file) => {
                setSourceFile(file);
                if (!sourceForm.getFieldValue('title')) {
                  sourceForm.setFieldValue('title', file.name);
                }
                return false;
              }}
              onRemove={() => setSourceFile(null)}
              fileList={sourceFile ? [{ uid: 'source-file', name: sourceFile.name, status: 'done' }] : []}
            >
              <Button icon={<UploadOutlined />}>选择制度文档</Button>
            </Upload>
            <Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>
              当前支持 TXT/MD/JSON/CSV/DOCX 文本抽取；PDF 会先登记文件信息，后续接 PDF 解析器。
            </Text>
          </Form.Item>
          <Form.Item name="file_name" label="文件名">
            <Input placeholder="contract-review-2026.docx" />
          </Form.Item>
          <Form.Item name="content_type" label="内容类型">
            <Input placeholder="text/plain" />
          </Form.Item>
          <Form.Item name="raw_text" label="来源文本">
            <Input.TextArea rows={8} />
          </Form.Item>
          <Form.Item name="metadata" label="metadata JSON">
            <Input.TextArea rows={4} placeholder="{}" />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer title="新建规则条目" width={680} open={ruleDrawerOpen} onClose={() => setRuleDrawerOpen(false)}
        extra={<Button type="primary" loading={saving} onClick={createRule}>保存</Button>}>
        <Form form={ruleForm} layout="vertical">
          <Form.Item name="rule_code" label="规则编号" rules={[{ required: true, message: '请输入规则编号' }]}>
            <Input placeholder="CONTRACT_PAYMENT_TERM_GT_90D" />
          </Form.Item>
          <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input placeholder="付款周期超过 90 天" />
          </Form.Item>
          <Form.Item name="source_document_id" label="来源文档">
            <Select allowClear options={sourceOptions} />
          </Form.Item>
          <Form.Item name="target_entity_type" label="目标实体">
            <Input placeholder="Contract" />
          </Form.Item>
          <Space style={{ width: '100%' }} align="start">
            <Form.Item name="severity" label="严重度" rules={[{ required: true }]}>
              <Select style={{ width: 160 }} options={['low', 'medium', 'high', 'critical'].map((value) => ({ label: value, value }))} />
            </Form.Item>
            <Form.Item name="action" label="动作" rules={[{ required: true }]}>
              <Select style={{ width: 160 }} options={['flag', 'block', 'recommend'].map((value) => ({ label: value, value }))} />
            </Form.Item>
            <Form.Item name="version" label="条目版本">
              <Input style={{ width: 120 }} />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="conditions" label="conditions JSON" rules={[{ required: true, message: '请输入结构化条件' }]}>
            <Input.TextArea rows={7} />
          </Form.Item>
          <Form.Item name="evidence_refs" label="evidence_refs JSON" rules={[{ required: true, message: '请输入证据引用' }]}>
            <Input.TextArea rows={5} />
          </Form.Item>
          <Form.Item name="test_cases" label="test_cases JSON">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Input placeholder="contract,risk" />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer title="新建本体条目" width={680} open={termDrawerOpen} onClose={() => setTermDrawerOpen(false)}
        extra={<Button type="primary" loading={saving} onClick={createTerm}>保存</Button>}>
        <Form form={termForm} layout="vertical">
          <Form.Item name="term_code" label="条目编号" rules={[{ required: true, message: '请输入条目编号' }]}>
            <Input placeholder="ENTITY_CONTRACT / ATTR_CONTRACT_AMOUNT" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="Contract / amount / counterparty" />
          </Form.Item>
          <Form.Item name="kind" label="类型" rules={[{ required: true }]}>
            <Select options={termKinds} />
          </Form.Item>
          <Form.Item name="source_document_id" label="来源文档">
            <Select allowClear options={sourceOptions} />
          </Form.Item>
          <Form.Item name="description" label="定义说明" rules={[{ required: true, message: '请输入定义说明' }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Space style={{ width: '100%' }} align="start">
            <Form.Item name="entity_type" label="所属实体">
              <Input style={{ width: 180 }} placeholder="Contract" />
            </Form.Item>
            <Form.Item name="data_type" label="字段类型">
              <Select style={{ width: 150 }} options={dataTypes} />
            </Form.Item>
            <Form.Item name="required" label="必填">
              <Select style={{ width: 110 }} options={[{ label: '否', value: false }, { label: '是', value: true }]} />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} align="start">
            <Form.Item name="relation_target_type" label="关系目标实体">
              <Input style={{ width: 180 }} placeholder="Party" />
            </Form.Item>
            <Form.Item name="relation_cardinality" label="关系基数">
              <Select style={{ width: 150 }} options={[{ label: 'one', value: 'one' }, { label: 'many', value: 'many' }]} />
            </Form.Item>
            <Form.Item name="version" label="条目版本">
              <Input style={{ width: 120 }} />
            </Form.Item>
          </Space>
          <Form.Item name="enum_values" label="枚举/分类值">
            <Input placeholder="draft,active,archived" />
          </Form.Item>
          <Form.Item name="aliases" label="别名">
            <Input placeholder="合同,协议" />
          </Form.Item>
          <Form.Item name="evidence_refs" label="evidence_refs JSON" rules={[{ required: true, message: '请输入证据引用' }]}>
            <Input.TextArea rows={5} />
          </Form.Item>
          <Form.Item name="metadata" label="metadata JSON">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default RuleOntologyAssetWorkbench;
