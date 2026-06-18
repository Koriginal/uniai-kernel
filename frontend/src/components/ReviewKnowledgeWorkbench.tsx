import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Typography, Upload, message } from 'antd';
import { CheckCircleOutlined, EditOutlined, FileSearchOutlined, PlayCircleOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
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
}

interface PolicyDocument {
  id: string;
  title: string;
  document_type: string;
  business_domain?: string;
  version: string;
  status: string;
  created_at: string;
}

interface PolicyArticle {
  id: string;
  policy_document_id: string;
  locator: string;
  text: string;
  quote: string;
  chapter_path: string[];
}

interface NormClause {
  id: string;
  norm_code: string;
  norm_type: string;
  subject?: string;
  action?: string;
  object?: string;
  condition_text?: string;
  exception_text?: string;
  consequence_text?: string;
  evidence_required: string[];
  domain_tags: string[];
  scenario_tags: string[];
  confidence: string;
  status: string;
  review_note?: string;
}

interface ReviewCheck {
  id: string;
  check_code: string;
  name: string;
  scenario_type: string;
  description?: string;
  check_type: string;
  severity: string;
  norm_clause_ids: string[];
  input_schema: Record<string, unknown>;
  evidence_schema: Record<string, unknown>;
  fail_template?: string;
  pass_template?: string;
  status: string;
  review_note?: string;
}

interface ReviewPack {
  id: string;
  name: string;
  scenario_type: string;
  version: string;
  status: string;
  norm_clause_ids: string[];
  review_check_ids: string[];
}

const statusColors: Record<string, string> = {
  draft: 'default',
  segmented: 'blue',
  norms_extracted: 'purple',
  approved: 'green',
  released: 'cyan',
  rejected: 'red',
  archived: 'default',
};

const parseJsonObject = (value: string | undefined, fallback: Record<string, unknown>) => {
  if (!value || !value.trim()) return fallback;
  const parsed = JSON.parse(value);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('JSON 必须是对象');
  }
  return parsed;
};

const ReviewKnowledgeWorkbench: React.FC<Props> = ({ api }) => {
  const [uploadForm] = Form.useForm();
  const [packForm] = Form.useForm();
  const [runForm] = Form.useForm();
  const [normForm] = Form.useForm();
  const [checkForm] = Form.useForm();
  const [spaces, setSpaces] = useState<SpaceItem[]>([]);
  const [spaceId, setSpaceId] = useState('');
  const [documents, setDocuments] = useState<PolicyDocument[]>([]);
  const [articles, setArticles] = useState<PolicyArticle[]>([]);
  const [norms, setNorms] = useState<NormClause[]>([]);
  const [checks, setChecks] = useState<ReviewCheck[]>([]);
  const [packs, setPacks] = useState<ReviewPack[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [targetFile, setTargetFile] = useState<File | null>(null);
  const [editingNorm, setEditingNorm] = useState<NormClause | null>(null);
  const [editingCheck, setEditingCheck] = useState<ReviewCheck | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);

  const documentOptions = useMemo(() => documents.map((item) => ({ label: `${item.title} · ${item.version}`, value: item.id })), [documents]);
  const approvedNormOptions = useMemo(() => norms.filter((item) => item.status === 'approved').map((item) => ({ label: `${item.norm_code} · ${item.object || item.norm_type}`, value: item.id })), [norms]);
  const approvedCheckOptions = useMemo(() => checks.filter((item) => item.status === 'approved').map((item) => ({ label: `${item.check_code} · ${item.name}`, value: item.id })), [checks]);
  const releasedPackOptions = useMemo(() => packs.filter((item) => item.status === 'released').map((item) => ({ label: `${item.name} · ${item.version}`, value: item.id })), [packs]);
  const approvedNormCount = useMemo(() => norms.filter((item) => item.status === 'approved' || item.status === 'released').length, [norms]);
  const approvedCheckCount = useMemo(() => checks.filter((item) => item.status === 'approved' || item.status === 'released').length, [checks]);

  const loadSpaces = useCallback(async () => {
    const res = await api.get('/api/v1/ontology/spaces');
    const items = res.data || [];
    setSpaces(items);
    if (!spaceId && items[0]?.id) setSpaceId(items[0].id);
  }, [api, spaceId]);

  const loadAll = useCallback(async (targetSpaceId = spaceId) => {
    if (!targetSpaceId) return;
    setLoading(true);
    try {
      const [docsRes, articlesRes, normsRes, checksRes, packsRes] = await Promise.all([
        api.get('/api/v1/review/policy-documents', { params: { space_id: targetSpaceId } }),
        api.get('/api/v1/review/articles', { params: { space_id: targetSpaceId } }),
        api.get('/api/v1/review/norm-clauses', { params: { space_id: targetSpaceId } }),
        api.get('/api/v1/review/checks', { params: { space_id: targetSpaceId } }),
        api.get('/api/v1/review/packs', { params: { space_id: targetSpaceId } }),
      ]);
      setDocuments(docsRes.data || []);
      setArticles(articlesRes.data || []);
      setNorms(normsRes.data || []);
      setChecks(checksRes.data || []);
      setPacks(packsRes.data || []);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '读取评审知识库失败');
    } finally {
      setLoading(false);
    }
  }, [api, spaceId]);

  useEffect(() => {
    loadSpaces();
  }, [loadSpaces]);

  useEffect(() => {
    if (spaceId) loadAll(spaceId);
  }, [spaceId, loadAll]);

  const uploadPolicyDocument = async () => {
    const values = await uploadForm.validateFields();
    if (!file) {
      message.warning('请选择规则来源文件');
      return;
    }
    const formData = new FormData();
    formData.append('space_id', spaceId);
    formData.append('document_type', values.document_type);
    formData.append('version', values.version || '1');
    formData.append('business_domain', values.business_domain || 'legal');
    if (values.title) formData.append('title', values.title);
    formData.append('file', file);
    await api.post('/api/v1/review/policy-documents/upload', formData);
    setFile(null);
    uploadForm.resetFields();
    message.success('规则文档已上传');
    loadAll();
  };

  const segmentDocument = async (documentId: string) => {
    await api.post(`/api/v1/review/policy-documents/${documentId}/segment`);
    message.success('原文条款已生成');
    loadAll();
  };

  const extractNorms = async (documentId: string) => {
    const res = await api.post(`/api/v1/review/policy-documents/${documentId}/extract-norms`);
    message.success(`已生成 ${res.data?.norm_clauses?.length || 0} 条规范候选`);
    loadAll();
  };

  const patchNorm = async (id: string, status: string) => {
    await api.patch(`/api/v1/review/norm-clauses/${id}`, { status });
    message.success(status === 'approved' ? '规范已确认' : '规范已退回');
    loadAll();
  };

  const patchCheck = async (id: string, status: string) => {
    await api.patch(`/api/v1/review/checks/${id}`, { status });
    message.success(status === 'approved' ? '审查点已确认' : '审查点已退回');
    loadAll();
  };

  const openNormEditor = (item: NormClause) => {
    setEditingNorm(item);
    normForm.setFieldsValue({
      ...item,
      evidence_required: item.evidence_required?.join(', '),
      domain_tags: item.domain_tags?.join(', '),
      scenario_tags: item.scenario_tags?.join(', '),
    });
  };

  const saveNorm = async () => {
    const values = await normForm.validateFields();
    if (!editingNorm) return;
    await api.patch(`/api/v1/review/norm-clauses/${editingNorm.id}`, {
      ...values,
      evidence_required: String(values.evidence_required || '').split(',').map((item) => item.trim()).filter(Boolean),
      domain_tags: String(values.domain_tags || '').split(',').map((item) => item.trim()).filter(Boolean),
      scenario_tags: String(values.scenario_tags || '').split(',').map((item) => item.trim()).filter(Boolean),
    });
    setEditingNorm(null);
    message.success('规范条款已保存');
    loadAll();
  };

  const openCheckEditor = (item: ReviewCheck) => {
    setEditingCheck(item);
    checkForm.setFieldsValue({
      ...item,
      norm_clause_ids: item.norm_clause_ids,
      input_schema: JSON.stringify(item.input_schema || {}, null, 2),
      evidence_schema: JSON.stringify(item.evidence_schema || {}, null, 2),
    });
  };

  const saveCheck = async () => {
    const values = await checkForm.validateFields();
    if (!editingCheck) return;
    try {
      await api.patch(`/api/v1/review/checks/${editingCheck.id}`, {
        ...values,
        input_schema: parseJsonObject(values.input_schema, {}),
        evidence_schema: parseJsonObject(values.evidence_schema, {}),
      });
      setEditingCheck(null);
      message.success('审查点已保存');
      loadAll();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '保存审查点失败');
    }
  };

  const createPack = async () => {
    const values = await packForm.validateFields();
    await api.post('/api/v1/review/packs', { ...values, space_id: spaceId });
    packForm.resetFields();
    message.success('规则包草稿已创建');
    loadAll();
  };

  const releasePack = async (id: string) => {
    await api.post(`/api/v1/review/packs/${id}/release`);
    message.success('规则包已发布');
    loadAll();
  };

  const runReview = async () => {
    const values = await runForm.validateFields();
    setRunning(true);
    try {
      const res = await api.post('/api/v1/review/runs', values);
      Modal.info({
        title: '评审结果',
        width: 920,
        content: (
          <pre style={{ maxHeight: '64vh', overflow: 'auto', whiteSpace: 'pre-wrap', background: '#f8fafc', border: '1px solid #e5e7eb', padding: 12, borderRadius: 8 }}>
            {JSON.stringify(res.data, null, 2)}
          </pre>
        ),
      });
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '运行评审失败');
    } finally {
      setRunning(false);
    }
  };

  const extractTargetFile = async () => {
    if (!targetFile) {
      message.warning('请选择待审文件');
      return;
    }
    const title = runForm.getFieldValue('target_title');
    const formData = new FormData();
    if (title) formData.append('title', title);
    formData.append('file', targetFile);
    const res = await api.post('/api/v1/review/target-documents/extract', formData);
    runForm.setFieldsValue({
      target_title: res.data?.title,
      target_text: res.data?.text,
    });
    message.success(`已解析待审文件，正文 ${res.data?.text?.length || 0} 字`);
  };

  return (
    <div className="rule-workbench-page">
      <section className="rule-workbench-hero">
        <div className="rule-workbench-title">
          <span className="rule-workbench-title-icon"><FileSearchOutlined /></span>
          <div className="rule-workbench-title-copy">
            <Title level={4}>评审知识库</Title>
            <Text type="secondary">从制度、合同口径、招标口径中提取可引用规则，发布成固定评审包后进入运行时。</Text>
          </div>
        </div>
        <div className="rule-workbench-actions">
            <Select style={{ width: 260 }} value={spaceId || undefined} options={spaces.map((item) => ({ label: `${item.name} (${item.code})`, value: item.id }))} onChange={setSpaceId} />
            <Button icon={<ReloadOutlined />} onClick={() => loadAll()} loading={loading}>刷新</Button>
        </div>
      </section>

      <div className="rule-metric-strip">
        <div className="rule-metric"><div className="rule-metric-label">规则文档</div><div className="rule-metric-value">{documents.length}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">原文条款</div><div className="rule-metric-value">{articles.length}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">已确认规范</div><div className="rule-metric-value">{approvedNormCount}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">已确认审查点</div><div className="rule-metric-value">{approvedCheckCount}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">已发布规则包</div><div className="rule-metric-value">{packs.filter((item) => item.status === 'released').length}</div></div>
      </div>

      <div className="rule-workflow-shell">
      <Tabs
        tabPosition="left"
        className="rule-workflow-tabs"
        items={[
          {
            key: 'documents',
            label: '规则文档',
            children: (
              <>
                <div className="rule-stage-header">
                  <div className="rule-stage-title">
                    <strong>规则来源</strong>
                    <Text type="secondary">上传制度、合同审查口径、招标文件审查口径；后续所有规则都要追到这里。</Text>
                  </div>
                </div>
                <Form form={uploadForm} layout="inline" initialValues={{ document_type: 'contract_rule', business_domain: 'legal', version: '1' }} style={{ marginBottom: 16 }}>
                  <Form.Item name="title" label="标题">
                    <Input style={{ width: 200 }} placeholder="可选" />
                  </Form.Item>
                  <Form.Item name="document_type" label="类型" rules={[{ required: true }]}>
                    <Select style={{ width: 150 }} options={[
                      { label: '合同规则', value: 'contract_rule' },
                      { label: '招标规则', value: 'tender_rule' },
                      { label: '制度文件', value: 'policy_doc' },
                      { label: '审核手册', value: 'review_manual' },
                    ]} />
                  </Form.Item>
                  <Form.Item name="business_domain" label="业务域">
                    <Input style={{ width: 120 }} />
                  </Form.Item>
                  <Form.Item name="version" label="版本">
                    <Input style={{ width: 100 }} />
                  </Form.Item>
                  <Upload beforeUpload={(nextFile) => { setFile(nextFile); return false; }} maxCount={1} fileList={file ? [file as any] : []} onRemove={() => setFile(null)}>
                    <Button icon={<UploadOutlined />}>选择文件</Button>
                  </Upload>
                  <Button type="primary" onClick={uploadPolicyDocument}>上传</Button>
                </Form>
                <Table
                  className="rule-table-card"
                  rowKey="id"
                  dataSource={documents}
                  pagination={{ pageSize: 6 }}
                  columns={[
                    { title: '文档', dataIndex: 'title', render: (value, item) => <Space direction="vertical" size={1}><Text strong>{value}</Text><Text type="secondary" style={{ fontSize: 12 }}>{item.id}</Text></Space> },
                    { title: '类型', dataIndex: 'document_type', width: 120, render: (value) => <Tag>{value}</Tag> },
                    { title: '版本', dataIndex: 'version', width: 90 },
                    { title: '状态', dataIndex: 'status', width: 120, render: (value) => <Tag color={statusColors[value] || 'default'}>{value}</Tag> },
                    { title: '操作', width: 230, render: (_, item) => <Space><Button size="small" onClick={() => segmentDocument(item.id)}>分条</Button><Button size="small" onClick={() => extractNorms(item.id)}>抽规范</Button></Space> },
                  ]}
                />
              </>
            ),
          },
          {
            key: 'articles',
            label: '原文条款',
            children: (
              <Table
                className="rule-table-card"
                rowKey="id"
                dataSource={articles}
                pagination={{ pageSize: 8 }}
                columns={[
                  { title: '位置', dataIndex: 'locator', width: 120 },
                  { title: '章节', dataIndex: 'chapter_path', width: 180, render: (items: string[]) => items?.join(' / ') || '-' },
                  { title: '原文', dataIndex: 'text', render: (value) => <Text>{value}</Text> },
                ]}
              />
            ),
          },
          {
            key: 'norms',
            label: '规范条款',
            children: (
              <Table
                className="rule-table-card"
                rowKey="id"
                dataSource={norms}
                pagination={{ pageSize: 8 }}
                columns={[
                  { title: '编码', dataIndex: 'norm_code', width: 220 },
                  { title: '类型', dataIndex: 'norm_type', width: 140, render: (value) => <Tag color="blue">{value}</Tag> },
                  { title: '场景', dataIndex: 'scenario_tags', width: 150, render: (items: string[]) => items?.map((item) => <Tag key={item}>{item}</Tag>) },
                  { title: '内容', dataIndex: 'condition_text' },
                  { title: '状态', dataIndex: 'status', width: 110, render: (value) => <Tag color={statusColors[value] || 'default'}>{value}</Tag> },
                  {
                    title: '操作',
                    width: 230,
                    render: (_, item) => (
                      <Space>
                        <Button size="small" icon={<EditOutlined />} disabled={item.status === 'released'} onClick={() => openNormEditor(item)}>编辑</Button>
                        <Button size="small" icon={<CheckCircleOutlined />} onClick={() => patchNorm(item.id, 'approved')}>确认</Button>
                        <Button size="small" onClick={() => patchNorm(item.id, 'rejected')}>退回</Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: 'checks',
            label: '审查点',
            children: (
              <Table
                className="rule-table-card"
                rowKey="id"
                dataSource={checks}
                pagination={{ pageSize: 8 }}
                columns={[
                  { title: '编码', dataIndex: 'check_code', width: 220 },
                  { title: '名称', dataIndex: 'name' },
                  { title: '场景', dataIndex: 'scenario_type', width: 140, render: (value) => <Tag>{value}</Tag> },
                  { title: '级别', dataIndex: 'severity', width: 100, render: (value) => <Tag color={value === 'critical' ? 'red' : value === 'high' ? 'orange' : 'blue'}>{value}</Tag> },
                  { title: '状态', dataIndex: 'status', width: 110, render: (value) => <Tag color={statusColors[value] || 'default'}>{value}</Tag> },
                  {
                    title: '操作',
                    width: 230,
                    render: (_, item) => (
                      <Space>
                        <Button size="small" icon={<EditOutlined />} disabled={item.status === 'released'} onClick={() => openCheckEditor(item)}>编辑</Button>
                        <Button size="small" onClick={() => patchCheck(item.id, 'approved')}>确认</Button>
                        <Button size="small" onClick={() => patchCheck(item.id, 'rejected')}>退回</Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: 'packs',
            label: '规则包',
            children: (
              <>
                <div className="rule-stage-header">
                  <div className="rule-stage-title">
                    <strong>发布固定规则包</strong>
                    <Text type="secondary">只把已确认的规范和审查点放进包里，发布后运行时按版本执行。</Text>
                  </div>
                </div>
                <Alert type="info" showIcon style={{ marginBottom: 16 }} message="规则包只允许使用已确认的规范条款和审查点。发布后运行时按该版本执行，不再临时读取草稿规则。" />
                <Form form={packForm} layout="inline" initialValues={{ scenario_type: 'contract_review', business_domain: 'legal', version: '1.0.0' }} style={{ marginBottom: 16 }}>
                  <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                    <Input style={{ width: 180 }} placeholder="合同审查包" />
                  </Form.Item>
                  <Form.Item name="scenario_type" label="场景">
                    <Select style={{ width: 150 }} options={[{ label: '合同审查', value: 'contract_review' }, { label: '招标审查', value: 'tender_review' }]} />
                  </Form.Item>
                  <Form.Item name="version" label="版本">
                    <Input style={{ width: 100 }} />
                  </Form.Item>
                  <Form.Item name="policy_document_ids" label="文档">
                    <Select mode="multiple" style={{ minWidth: 220 }} options={documentOptions} />
                  </Form.Item>
                  <Form.Item name="norm_clause_ids" label="规范">
                    <Select mode="multiple" style={{ minWidth: 220 }} options={approvedNormOptions} />
                  </Form.Item>
                  <Form.Item name="review_check_ids" label="审查点">
                    <Select mode="multiple" style={{ minWidth: 220 }} options={approvedCheckOptions} />
                  </Form.Item>
                  <Button type="primary" onClick={createPack}>创建规则包</Button>
                </Form>
                <Table
                  className="rule-table-card"
                  rowKey="id"
                  dataSource={packs}
                  pagination={{ pageSize: 6 }}
                  columns={[
                    { title: '名称', dataIndex: 'name' },
                    { title: '场景', dataIndex: 'scenario_type', width: 140, render: (value) => <Tag>{value}</Tag> },
                    { title: '版本', dataIndex: 'version', width: 90 },
                    { title: '资产', width: 150, render: (_, item) => <Text type="secondary">{item.norm_clause_ids?.length || 0} 规范 / {item.review_check_ids?.length || 0} 审查点</Text> },
                    { title: '状态', dataIndex: 'status', width: 110, render: (value) => <Tag color={statusColors[value] || 'default'}>{value}</Tag> },
                    { title: '操作', width: 120, render: (_, item) => <Button size="small" disabled={item.status === 'released'} onClick={() => releasePack(item.id)}>发布</Button> },
                  ]}
                />
              </>
            ),
          },
          {
            key: 'run',
            label: '评审工作台',
            children: (
              <>
                <div className="rule-stage-header">
                  <div className="rule-stage-title">
                    <strong>试运行评审</strong>
                    <Text type="secondary">选择已发布规则包，上传或粘贴待审文件，检查输出是否稳定、是否能引用依据。</Text>
                  </div>
                </div>
                <Form form={runForm} layout="vertical">
                  <Form.Item name="review_pack_id" label="规则包" rules={[{ required: true }]}>
                    <Select options={releasedPackOptions} placeholder="选择已发布规则包" />
                  </Form.Item>
                  <Form.Item name="target_title" label="待审文件标题">
                    <Input placeholder="例如：XX 项目采购合同" />
                  </Form.Item>
                  <Form.Item label="待审文件上传">
                    <Space>
                      <Upload beforeUpload={(nextFile) => { setTargetFile(nextFile); return false; }} maxCount={1} fileList={targetFile ? [targetFile as any] : []} onRemove={() => setTargetFile(null)}>
                        <Button icon={<UploadOutlined />}>选择 DOCX/TXT/MD</Button>
                      </Upload>
                      <Button onClick={extractTargetFile}>解析到正文</Button>
                    </Space>
                  </Form.Item>
                  <Form.Item name="target_text" label="待审文件正文" rules={[{ required: true }]}>
                    <Input.TextArea rows={12} placeholder="上传文件解析后会自动填入，也可以直接粘贴合同或招标文件正文。" />
                  </Form.Item>
                  <Button type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={runReview}>运行评审</Button>
                </Form>
              </>
            ),
          },
        ]}
      />
      </div>

      <Modal title="编辑规范条款" open={!!editingNorm} onCancel={() => setEditingNorm(null)} onOk={saveNorm} width={760}>
        <Form form={normForm} layout="vertical">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="norm_type" label="规范类型" style={{ width: '50%' }} rules={[{ required: true }]}>
              <Select options={[
                { label: '义务', value: 'obligation' },
                { label: '禁止', value: 'prohibition' },
                { label: '允许', value: 'permission' },
                { label: '例外', value: 'exception' },
                { label: '审批要求', value: 'approval_required' },
                { label: '材料要求', value: 'evidence_required' },
                { label: '责任', value: 'liability' },
                { label: '标准', value: 'standard' },
                { label: '评分', value: 'scoring' },
              ]} />
            </Form.Item>
            <Form.Item name="confidence" label="置信度" style={{ width: '50%' }}>
              <Select options={[{ label: '高', value: 'high' }, { label: '中', value: 'medium' }, { label: '低', value: 'low' }]} />
            </Form.Item>
          </Space.Compact>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="subject" label="主体" style={{ width: '33%' }}><Input /></Form.Item>
            <Form.Item name="action" label="动作" style={{ width: '33%' }}><Input /></Form.Item>
            <Form.Item name="object" label="对象/字段" style={{ width: '34%' }}><Input /></Form.Item>
          </Space.Compact>
          <Form.Item name="condition_text" label="规则正文"><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="exception_text" label="例外条件"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="consequence_text" label="后果/责任"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="evidence_required" label="所需证据字段"><Input placeholder="逗号分隔，例如 payment_terms, amount" /></Form.Item>
          <Form.Item name="domain_tags" label="业务标签"><Input placeholder="逗号分隔" /></Form.Item>
          <Form.Item name="scenario_tags" label="场景标签"><Input placeholder="contract_review, tender_review" /></Form.Item>
          <Form.Item name="review_note" label="审核备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="编辑审查点" open={!!editingCheck} onCancel={() => setEditingCheck(null)} onOk={saveCheck} width={820}>
        <Form form={checkForm} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="scenario_type" label="场景" style={{ width: '34%' }} rules={[{ required: true }]}>
              <Select options={[{ label: '合同审查', value: 'contract_review' }, { label: '招标审查', value: 'tender_review' }, { label: '自定义', value: 'custom' }]} />
            </Form.Item>
            <Form.Item name="check_type" label="类型" style={{ width: '33%' }}>
              <Select options={[{ label: '语义', value: 'semantic' }, { label: '确定性', value: 'deterministic' }, { label: '人工', value: 'manual' }]} />
            </Form.Item>
            <Form.Item name="severity" label="严重度" style={{ width: '33%' }}>
              <Select options={[{ label: '低', value: 'low' }, { label: '中', value: 'medium' }, { label: '高', value: 'high' }, { label: '关键', value: 'critical' }]} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="norm_clause_ids" label="绑定规范"><Select mode="multiple" options={norms.map((item) => ({ label: `${item.norm_code} · ${item.object || item.norm_type}`, value: item.id }))} /></Form.Item>
          <Form.Item name="fail_template" label="未通过模板"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="pass_template" label="通过模板"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="input_schema" label="输入 Schema JSON"><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="evidence_schema" label="证据 Schema JSON"><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="review_note" label="审核备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ReviewKnowledgeWorkbench;
