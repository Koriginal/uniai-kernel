import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Checkbox, Divider, Drawer, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Typography, Upload, message } from 'antd';
import { CheckCircleOutlined, DeleteOutlined, FileTextOutlined, PlusOutlined, ReloadOutlined, SafetyOutlined, UploadOutlined } from '@ant-design/icons';
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

interface RuleSourceDocument {
  id: string;
  title: string;
  source_type: string;
  file_name?: string;
  content_hash: string;
  raw_text?: string;
  status: string;
}

interface RuleEntry {
  id: string;
  source_document_id?: string;
  rule_code: string;
  name: string;
  description?: string;
  target_entity_type?: string;
  conditions: Record<string, unknown>[];
  severity: string;
  action: string;
  evidence_refs: Record<string, unknown>[];
  test_cases: Record<string, unknown>[];
  tags: string[];
  status: string;
  version: string;
}

interface EvidenceReference {
  source_document_id?: string;
  locator?: string;
  quote?: string;
  line_start?: number;
  line_end?: number;
}

interface RulePackage {
  kind: string;
  space_id: string;
  version: string;
  stage: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  notes?: string;
  payload: {
    description?: string;
    rules?: Record<string, unknown>[];
    metadata?: Record<string, unknown>;
  };
}

interface RuleQualityIssue {
  code: string;
  field: string;
  message: string;
}

interface RuleQualityReport {
  rule_entry_id: string;
  status: string;
  blockers: RuleQualityIssue[];
  warnings: RuleQualityIssue[];
  can_submit_review: boolean;
  can_approve: boolean;
  can_package: boolean;
}

const sourceTypes = [
  { label: '制度文件', value: 'policy_doc' },
  { label: '合同规则', value: 'contract_template' },
  { label: '审核手册', value: 'review_manual' },
  { label: '监管规则', value: 'regulation' },
  { label: '招标规则', value: 'custom_note' },
];

const statusColors: Record<string, string> = {
  uploaded: 'default',
  parsed: 'blue',
  parse_failed: 'red',
  draft: 'default',
  reviewing: 'gold',
  approved: 'green',
  rejected: 'red',
  packaged: 'purple',
  released: 'cyan',
};

const severityColors: Record<string, string> = {
  low: 'default',
  medium: 'blue',
  high: 'orange',
  critical: 'red',
};

const statusLabels: Record<string, string> = {
  uploaded: '待提取',
  parsed: '已提取',
  parse_failed: '提取失败',
  draft: '草稿',
  reviewing: '待审核',
  approved: '已批准',
  rejected: '已退回',
  packaged: '已入包',
  released: '已发布',
  deprecated: '已停用',
};

const packageStageLabels: Record<string, string> = {
  draft: '草稿',
  review: '评审中',
  staging: '测试中',
  ga: '已发布',
  deprecated: '已停用',
};

const qualityIssueLabels: Record<string, string> = {
  missing_conditions: '缺少结构化条件',
  missing_evidence_refs: '缺少原文依据',
  missing_evidence_locator: '原文依据缺少位置',
  missing_high_risk_test_cases: '高危规则缺少测试用例',
  missing_test_cases: '尚未配置测试用例',
  missing_target_entity_type: '尚未指定目标对象',
};

const parseScalarValue = (value: unknown) => {
  if (typeof value !== 'string') return value;
  const normalized = value.trim();
  if (!normalized) return '';
  if (normalized === 'true') return true;
  if (normalized === 'false') return false;
  if (normalized === 'null') return null;
  if (/^-?\d+(\.\d+)?$/.test(normalized)) return Number(normalized);
  if ((normalized.startsWith('[') && normalized.endsWith(']')) || (normalized.startsWith('{') && normalized.endsWith('}'))) {
    try {
      return JSON.parse(normalized);
    } catch {
      return normalized;
    }
  }
  return normalized;
};

const displayScalarValue = (value: unknown) => {
  if (value === undefined || value === null) return '';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
};

const getPrimaryEvidence = (rule?: RuleEntry | null): EvidenceReference | null => {
  const reference = rule?.evidence_refs?.[0];
  return reference ? reference as EvidenceReference : null;
};

const renderHighlightedSource = (sourceText: string, quote?: string) => {
  const normalizedQuote = quote?.trim();
  if (!normalizedQuote) return <>{sourceText}</>;
  const index = sourceText.indexOf(normalizedQuote);
  if (index < 0) return <>{sourceText}</>;
  return (
    <>
      {sourceText.slice(0, index)}
      <mark id="rule-source-active-quote" className="rule-source-highlight">{sourceText.slice(index, index + normalizedQuote.length)}</mark>
      {sourceText.slice(index + normalizedQuote.length)}
    </>
  );
};

const validateJsonObject = (_: unknown, value: string | undefined) => {
  if (!value?.trim()) return Promise.resolve();
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? Promise.resolve()
      : Promise.reject(new Error('请输入 JSON 对象'));
  } catch {
    return Promise.reject(new Error('JSON 格式不正确'));
  }
};

const RuleLibraryWorkbench: React.FC<Props> = ({ api }) => {
  const [sourceForm] = Form.useForm();
  const [ruleForm] = Form.useForm();
  const [compileForm] = Form.useForm();
  const [spaces, setSpaces] = useState<SpaceItem[]>([]);
  const [spaceId, setSpaceId] = useState('');
  const [sources, setSources] = useState<RuleSourceDocument[]>([]);
  const [rules, setRules] = useState<RuleEntry[]>([]);
  const [qualityReports, setQualityReports] = useState<Record<string, RuleQualityReport>>({});
  const [packages, setPackages] = useState<RulePackage[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourceDrawerOpen, setSourceDrawerOpen] = useState(false);
  const [ruleDrawerOpen, setRuleDrawerOpen] = useState(false);
  const [reviewDrawerOpen, setReviewDrawerOpen] = useState(false);
  const [reviewSource, setReviewSource] = useState<RuleSourceDocument | null>(null);
  const [selectedReviewRuleId, setSelectedReviewRuleId] = useState('');
  const [editingRule, setEditingRule] = useState<RuleEntry | null>(null);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [activeAction, setActiveAction] = useState('');
  const [ruleSearch, setRuleSearch] = useState('');
  const [ruleStatusFilter, setRuleStatusFilter] = useState('all');
  const [ruleQualityFilter, setRuleQualityFilter] = useState('all');
  const [selectedRuleIds, setSelectedRuleIds] = useState<React.Key[]>([]);

  const sourceOptions = useMemo(() => sources.map((item) => ({ label: item.title, value: item.id })), [sources]);
  const approvedRuleOptions = useMemo(
    () => rules.filter((item) => item.status === 'approved').map((item) => ({
      label: `${item.rule_code} · ${item.name}`,
      value: item.id,
    })),
    [rules],
  );
  const approvedRuleCount = useMemo(() => rules.filter((item) => ['approved', 'packaged', 'released'].includes(item.status)).length, [rules]);
  const filteredRules = useMemo(() => {
    const keyword = ruleSearch.trim().toLowerCase();
    return rules.filter((rule) => {
      const report = qualityReports[rule.id];
      const matchesSearch = !keyword || `${rule.rule_code} ${rule.name} ${rule.target_entity_type || ''}`.toLowerCase().includes(keyword);
      const matchesStatus = ruleStatusFilter === 'all' || rule.status === ruleStatusFilter;
      const matchesQuality = ruleQualityFilter === 'all'
        || (ruleQualityFilter === 'ready' && report?.blockers.length === 0)
        || (ruleQualityFilter === 'blocked' && (report?.blockers.length || 0) > 0)
        || (ruleQualityFilter === 'warning' && report?.blockers.length === 0 && (report?.warnings.length || 0) > 0);
      return matchesSearch && matchesStatus && matchesQuality;
    });
  }, [qualityReports, ruleQualityFilter, ruleSearch, ruleStatusFilter, rules]);
  const reviewSourceRules = useMemo(
    () => reviewSource ? rules.filter((item) => item.source_document_id === reviewSource.id) : [],
    [reviewSource, rules],
  );
  const selectedReviewRule = useMemo(
    () => reviewSourceRules.find((item) => item.id === selectedReviewRuleId) || reviewSourceRules[0] || null,
    [reviewSourceRules, selectedReviewRuleId],
  );

  const getRuleQualityBlockers = (rule: RuleEntry) => {
    const report = qualityReports[rule.id];
    if (report) return report.blockers.map((issue) => qualityIssueLabels[issue.code] || issue.message);
    const blockers: string[] = [];
    if (!rule.conditions?.length) blockers.push('缺少结构化条件');
    if (!rule.evidence_refs?.length) blockers.push('缺少原文依据');
    if (['high', 'critical'].includes(rule.severity) && !rule.test_cases?.length) blockers.push('高危规则缺少测试用例');
    return blockers;
  };

  const getRuleReleaseBlockers = (rule: RuleEntry) => {
    const blockers = getRuleQualityBlockers(rule);
    if (rule.status !== 'approved') blockers.push(`状态是 ${rule.status}`);
    return blockers;
  };

  const loadSpaces = useCallback(async () => {
    const res = await api.get('/api/v1/ontology/spaces');
    const items = res.data || [];
    setSpaces(items);
    setSpaceId((current) => current || items[0]?.id || '');
  }, [api]);

  const loadRules = useCallback(async (targetSpaceId = spaceId) => {
    if (!targetSpaceId) return;
    setLoading(true);
    try {
      const [sourceRes, ruleRes, packageRes, qualityRes] = await Promise.all([
        api.get(`/api/v1/ontology/asset-sources/${targetSpaceId}`),
        api.get(`/api/v1/ontology/rule-entries/${targetSpaceId}`),
        api.get(`/api/v1/ontology/packages/${targetSpaceId}/rule`),
        api.get(`/api/v1/ontology/rule-quality/${targetSpaceId}`),
      ]);
      setSources(sourceRes.data || []);
      setRules(ruleRes.data || []);
      setPackages(packageRes.data || []);
      setQualityReports(Object.fromEntries((qualityRes.data || []).map((item: RuleQualityReport) => [item.rule_entry_id, item])));
      setSelectedRuleIds([]);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '读取规则库失败');
    } finally {
      setLoading(false);
    }
  }, [api, spaceId]);

  useEffect(() => {
    loadSpaces().catch(() => setSpaces([]));
  }, [loadSpaces]);

  useEffect(() => {
    if (spaceId) loadRules(spaceId);
  }, [spaceId, loadRules]);

  useEffect(() => {
    if (!reviewDrawerOpen || !selectedReviewRule) return;
    window.requestAnimationFrame(() => {
      document.getElementById('rule-source-active-quote')?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
  }, [reviewDrawerOpen, selectedReviewRule]);

  const openSourceDrawer = () => {
    sourceForm.resetFields();
    sourceForm.setFieldsValue({ source_type: 'policy_doc' });
    setSourceFile(null);
    setSourceDrawerOpen(true);
  };

  const openReviewDrawer = (source: RuleSourceDocument) => {
    const sourceRules = rules.filter((item) => item.source_document_id === source.id);
    setReviewSource(source);
    setSelectedReviewRuleId(sourceRules[0]?.id || '');
    setReviewDrawerOpen(true);
  };

  const openRuleDrawer = (rule?: RuleEntry) => {
    ruleForm.resetFields();
    setEditingRule(rule || null);
    if (rule) {
      ruleForm.setFieldsValue({
        rule_code: rule.rule_code,
        name: rule.name,
        source_document_id: rule.source_document_id,
        target_entity_type: rule.target_entity_type,
        severity: rule.severity,
        action: rule.action,
        version: rule.version,
        description: rule.description || '',
        conditions: (rule.conditions || []).map((item) => ({
          ...item,
          value: displayScalarValue(item.value),
        })),
        evidence_refs: rule.evidence_refs || [],
        test_cases: (rule.test_cases || []).map((item) => ({
          ...item,
          graph: JSON.stringify(item.graph || {}, null, 2),
        })),
        tags: (rule.tags || []).join(','),
      });
      setRuleDrawerOpen(true);
      return;
    }
    ruleForm.setFieldsValue({
      severity: 'medium',
      action: 'flag',
      conditions: [{ path: '', operator: 'exists', value: '' }],
      evidence_refs: [{ source_document_id: undefined, locator: '', quote: '' }],
      test_cases: [],
      tags: '',
      version: '1',
    });
    setRuleDrawerOpen(true);
  };

  const createSource = async () => {
    const values = await sourceForm.validateFields();
    if (!sourceFile && !String(values.raw_text || '').trim()) {
      message.error('请上传 DOCX/TXT/MD 文件，或直接输入来源文本');
      return;
    }
    setSaving(true);
    try {
      if (sourceFile) {
        const formData = new FormData();
        formData.append('space_id', spaceId);
        formData.append('source_type', values.source_type || 'policy_doc');
        if (values.title) formData.append('title', values.title);
        formData.append('file', sourceFile);
        await api.post('/api/v1/ontology/asset-sources/upload', formData);
      } else {
        await api.post('/api/v1/ontology/asset-sources', {
          ...values,
          space_id: spaceId,
          metadata: {},
        });
      }
      message.success('规则来源已保存');
      setSourceDrawerOpen(false);
      await loadRules();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '保存来源失败');
    } finally {
      setSaving(false);
    }
  };

  const extractRules = async (source: RuleSourceDocument) => {
    setActiveAction(`extract:${source.id}`);
    try {
      const res = await api.post(`/api/v1/ontology/asset-sources/${source.id}/parse`, { max_rules: 100 });
      message.success(`已提取 ${res.data?.rule_entries?.length || 0} 条规则候选`);
      if (res.data?.warnings?.length) {
        Modal.info({
          title: '规则提取提示',
          width: 760,
          content: <pre style={{ maxHeight: '50vh', overflow: 'auto', whiteSpace: 'pre-wrap' }}>{JSON.stringify(res.data.warnings, null, 2)}</pre>,
        });
      }
      await loadRules();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '提取规则失败');
    } finally {
      setActiveAction('');
    }
  };

  const saveRule = async () => {
    const values = await ruleForm.validateFields();
    setSaving(true);
    try {
      const payload = {
        name: values.name,
        source_document_id: values.source_document_id,
        description: values.description,
        target_entity_type: values.target_entity_type,
        severity: values.severity,
        action: values.action,
        version: values.version,
        conditions: (values.conditions || []).map((item: Record<string, unknown>) => ({
          path: String(item.path || '').trim(),
          operator: item.operator,
          ...((item.operator === 'exists') ? {} : { value: parseScalarValue(item.value) }),
        })),
        evidence_refs: (values.evidence_refs || []).map((item: Record<string, unknown>) => ({
          source_document_id: item.source_document_id || undefined,
          locator: String(item.locator || '').trim(),
          quote: String(item.quote || '').trim() || undefined,
        })),
        test_cases: (values.test_cases || []).map((item: Record<string, unknown>) => ({
          name: String(item.name || '').trim(),
          expected_hit: item.expected_hit !== false,
          graph: item.graph ? JSON.parse(String(item.graph)) : {},
        })),
        tags: String(values.tags || '').split(',').map((item) => item.trim()).filter(Boolean),
      };
      if (editingRule) {
        await api.patch(`/api/v1/ontology/rule-entries/${editingRule.id}`, payload);
      } else {
        await api.post('/api/v1/ontology/rule-entries', {
          ...payload,
          space_id: spaceId,
          rule_code: values.rule_code,
        });
      }
      message.success(editingRule ? '规则条目已更新' : '规则条目已保存');
      setRuleDrawerOpen(false);
      setEditingRule(null);
      await loadRules();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '保存规则失败');
    } finally {
      setSaving(false);
    }
  };

  const submitReview = async (rule: RuleEntry) => {
    setActiveAction(`submit:${rule.id}`);
    try {
      await api.post(`/api/v1/ontology/rule-entries/${rule.id}/submit-review`);
      message.success('已提交审核');
      await loadRules();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '提交审核失败');
    } finally {
      setActiveAction('');
    }
  };

  const reviewRule = async (rule: RuleEntry, approve: boolean) => {
    setActiveAction(`${approve ? 'approve' : 'reject'}:${rule.id}`);
    try {
      await api.post(`/api/v1/ontology/rule-entries/${rule.id}/review`, {
        approve,
        review_note: approve ? 'approved in rule library' : 'rejected in rule library',
      });
      message.success(approve ? '规则已批准' : '规则已退回');
      await loadRules();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '审核失败');
    } finally {
      setActiveAction('');
    }
  };

  const batchSubmitReview = async () => {
    const eligibleIds = selectedRuleIds
      .map(String)
      .filter((id) => qualityReports[id]?.can_submit_review);
    if (!eligibleIds.length) {
      message.warning('请选择草稿或已退回的规则');
      return;
    }
    setActiveAction('batch-submit');
    try {
      const res = await api.post('/api/v1/ontology/rule-entries/batch-submit-review', {
        rule_entry_ids: eligibleIds,
      });
      const submittedCount = res.data?.submitted_ids?.length || 0;
      const skippedCount = Object.keys(res.data?.skipped || {}).length;
      message.success(`已提交 ${submittedCount} 条规则${skippedCount ? `，跳过 ${skippedCount} 条` : ''}`);
      await loadRules();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '批量提交审核失败');
    } finally {
      setActiveAction('');
    }
  };

  const compileRules = async () => {
    setActiveAction('compile');
    try {
      const values = await compileForm.validateFields();
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
        content: <pre style={{ maxHeight: '58vh', overflow: 'auto', whiteSpace: 'pre-wrap' }}>{JSON.stringify(res.data, null, 2)}</pre>,
      });
      await loadRules();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err.message || '编译规则包失败');
    } finally {
      setActiveAction('');
    }
  };

  return (
    <div className="rule-workbench-page">
      <section className="rule-workbench-hero">
        <div className="rule-workbench-title">
          <span className="rule-workbench-title-icon"><SafetyOutlined /></span>
          <div className="rule-workbench-title-copy">
            <Title level={4}>规则库</Title>
            <Text type="secondary">从非结构化制度、合同口径、招标口径中提取规则条目，审核后发布成可复用规则包。</Text>
          </div>
        </div>
        <div className="rule-workbench-actions">
          <Select
            style={{ width: 280 }}
            placeholder="选择规则空间"
            value={spaceId || undefined}
            onChange={setSpaceId}
            options={spaces.map((item) => ({ label: `${item.name} (${item.code})`, value: item.id }))}
          />
          <Button icon={<ReloadOutlined />} onClick={() => loadRules()} disabled={!spaceId}>刷新</Button>
        </div>
      </section>

      <div className="rule-metric-strip">
        <div className="rule-metric"><div className="rule-metric-label">来源文档</div><div className="rule-metric-value">{sources.length}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">规则条目</div><div className="rule-metric-value">{rules.length}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">已确认规则</div><div className="rule-metric-value">{approvedRuleCount}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">待审核</div><div className="rule-metric-value">{rules.filter((item) => item.status === 'reviewing').length}</div></div>
        <div className="rule-metric"><div className="rule-metric-label">已编译</div><div className="rule-metric-value">{rules.filter((item) => item.status === 'packaged' || item.status === 'released').length}</div></div>
      </div>

      {!spaceId ? (
        <Alert type="info" showIcon message="请先创建规则空间，再维护规则库。" />
      ) : (
        <div className="rule-workflow-shell">
          <Tabs
            tabPosition="left"
            className="rule-workflow-tabs"
            items={[
              {
                key: 'sources',
                label: '规则来源',
                children: (
                  <>
                    <div className="rule-stage-header">
                      <div className="rule-stage-title">
                        <strong>非结构化来源</strong>
                        <Text type="secondary">上传制度、合同审查口径、招标审查口径。规则只从这里提取，不和本体、评审应用混在一起。</Text>
                      </div>
                      <div className="rule-stage-actions">
                        <Button type="primary" icon={<PlusOutlined />} onClick={openSourceDrawer}>新增来源</Button>
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
                        { title: '文件', dataIndex: 'file_name', width: 220, render: (value: string) => value || '-' },
                        { title: '状态', dataIndex: 'status', width: 120, render: (value: string) => <Tag color={statusColors[value]}>{statusLabels[value] || value}</Tag> },
                        {
                          title: '操作',
                          width: 260,
                          render: (_: unknown, item: RuleSourceDocument) => (
                            <Space>
                              <Button size="small" icon={<FileTextOutlined />} onClick={() => Modal.info({
                                title: item.title,
                                width: 760,
                                content: <pre style={{ maxHeight: '58vh', overflow: 'auto', whiteSpace: 'pre-wrap' }}>{item.raw_text || JSON.stringify(item, null, 2)}</pre>,
                              })}>原文</Button>
                              <Button
                                size="small"
                                type="primary"
                                loading={activeAction === `extract:${item.id}`}
                                onClick={() => extractRules(item)}
                              >
                                提取规则
                              </Button>
                              <Button size="small" disabled={!rules.some((rule) => rule.source_document_id === item.id)} onClick={() => openReviewDrawer(item)}>
                                校对
                              </Button>
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
                        <strong>结构化规则</strong>
                        <Text type="secondary">每条规则必须有结构化条件和原文依据。这里只处理规则，不处理本体。</Text>
                      </div>
                      <div className="rule-stage-actions">
                        <Input.Search
                          allowClear
                          placeholder="搜索编号、名称、目标对象"
                          value={ruleSearch}
                          onChange={(event) => setRuleSearch(event.target.value)}
                          style={{ width: 240 }}
                        />
                        <Select
                          value={ruleStatusFilter}
                          onChange={setRuleStatusFilter}
                          style={{ width: 120 }}
                          options={[
                            { label: '全部状态', value: 'all' },
                            ...['draft', 'reviewing', 'approved', 'rejected', 'packaged', 'released'].map((value) => ({
                              label: statusLabels[value],
                              value,
                            })),
                          ]}
                        />
                        <Select
                          value={ruleQualityFilter}
                          onChange={setRuleQualityFilter}
                          style={{ width: 130 }}
                          options={[
                            { label: '全部质量', value: 'all' },
                            { label: '质量完整', value: 'ready' },
                            { label: '存在阻断', value: 'blocked' },
                            { label: '仅有提醒', value: 'warning' },
                          ]}
                        />
                        <Button
                          disabled={!selectedRuleIds.some((id) => qualityReports[String(id)]?.can_submit_review)}
                          loading={activeAction === 'batch-submit'}
                          onClick={batchSubmitReview}
                        >
                          批量提交审核
                        </Button>
                        <Button type="primary" icon={<PlusOutlined />} onClick={() => openRuleDrawer()}>手工新增规则</Button>
                      </div>
                    </div>
                    <Table
                      className="rule-table-card"
                      rowKey="id"
                      loading={loading}
                      dataSource={filteredRules}
                      rowSelection={{
                        selectedRowKeys: selectedRuleIds,
                        onChange: setSelectedRuleIds,
                        getCheckboxProps: (item: RuleEntry) => ({
                          disabled: !qualityReports[item.id]?.can_submit_review,
                        }),
                      }}
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
                        { title: '目标对象', dataIndex: 'target_entity_type', width: 130, render: (value: string) => value || '-' },
                        { title: '条件', dataIndex: 'conditions', width: 90, render: (items: unknown[]) => <Tag>{items?.length || 0}</Tag> },
                        { title: '级别', dataIndex: 'severity', width: 100, render: (value: string) => <Tag color={severityColors[value]}>{value}</Tag> },
                        { title: '动作', dataIndex: 'action', width: 100, render: (value: string) => <Tag>{value}</Tag> },
                        {
                          title: '质量检查',
                          width: 180,
                          render: (_: unknown, item: RuleEntry) => {
                            const blockers = getRuleQualityBlockers(item);
                            const warnings = qualityReports[item.id]?.warnings || [];
                            if (blockers.length) return <Text type="warning">{blockers.join('；')}</Text>;
                            if (warnings.length) {
                              return <Text type="secondary">{warnings.map((issue) => qualityIssueLabels[issue.code] || issue.message).join('；')}</Text>;
                            }
                            return <Tag color="green">质量完整</Tag>;
                          },
                        },
                        { title: '状态', dataIndex: 'status', width: 110, render: (value: string) => <Tag color={statusColors[value]}>{statusLabels[value] || value}</Tag> },
                        {
                          title: '操作',
                          width: 300,
                          render: (_: unknown, item: RuleEntry) => (
                            <Space>
                              <Button size="small" onClick={() => Modal.info({
                                title: item.rule_code,
                                width: 760,
                                content: <pre style={{ maxHeight: '58vh', overflow: 'auto', whiteSpace: 'pre-wrap' }}>{JSON.stringify(item, null, 2)}</pre>,
                              })}>详情</Button>
                              {!['packaged', 'released', 'deprecated'].includes(item.status) && (
                                <Button size="small" onClick={() => openRuleDrawer(item)}>编辑</Button>
                              )}
                              {(item.status === 'draft' || item.status === 'rejected') && (
                                <Button size="small" loading={activeAction === `submit:${item.id}`} onClick={() => submitReview(item)}>提交审核</Button>
                              )}
                              {item.status === 'reviewing' && (
                                <>
                                  <Button
                                    size="small"
                                    type="primary"
                                    icon={<CheckCircleOutlined />}
                                    disabled={!qualityReports[item.id]?.can_approve}
                                    loading={activeAction === `approve:${item.id}`}
                                    onClick={() => reviewRule(item, true)}
                                  >
                                    通过
                                  </Button>
                                  <Button size="small" danger loading={activeAction === `reject:${item.id}`} onClick={() => reviewRule(item, false)}>退回</Button>
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
                key: 'packages',
                label: '规则包',
                children: (
                  <>
                    <div className="rule-stage-header">
                      <div className="rule-stage-title">
                        <strong>发布前编译</strong>
                        <Text type="secondary">只从 approved 规则条目编译规则包。业务应用、评审应用、其他工程都应该消费这里的规则包。</Text>
                      </div>
                    </div>
                    <Form form={compileForm} layout="vertical" style={{ maxWidth: 760 }}>
                      <Form.Item name="version" label="规则包版本" rules={[{ required: true, message: '请输入版本，例如 1.0.0' }]}>
                        <Input placeholder="1.0.0" />
                      </Form.Item>
                      <Form.Item name="description" label="说明">
                        <Input.TextArea rows={3} />
                      </Form.Item>
                      <Form.Item name="rule_entry_ids" label="规则条目">
                        <Select mode="multiple" allowClear options={approvedRuleOptions} placeholder="留空表示编译全部 approved 规则" />
                      </Form.Item>
                      {rules.filter((item) => item.status === 'approved').length === 0 && (
                        <Alert
                          type="warning"
                          showIcon
                          message="当前没有可入包规则"
                          description="规则包只接收 approved 规则。先在规则条目里提交审核，通过质量门禁后才能出现在这里。"
                          style={{ marginBottom: 16 }}
                        />
                      )}
                      <Table
                        className="rule-table-card"
                        rowKey="id"
                        size="small"
                        dataSource={rules}
                        pagination={false}
                        columns={[
                          { title: '规则', dataIndex: 'rule_code', render: (value: string, item: RuleEntry) => <Text>{value} · {item.name}</Text> },
                          { title: '状态', dataIndex: 'status', width: 110, render: (value: string) => <Tag color={statusColors[value]}>{statusLabels[value] || value}</Tag> },
                          {
                            title: '入包检查',
                            render: (_: unknown, item: RuleEntry) => {
                              const blockers = getRuleReleaseBlockers(item);
                              if (!blockers.length) return <Tag color="green">可入包</Tag>;
                              return <Text type="secondary">{blockers.join('；')}</Text>;
                            },
                          },
                          {
                            title: '操作',
                            width: 120,
                            render: (_: unknown, item: RuleEntry) => ['packaged', 'released', 'deprecated'].includes(item.status)
                              ? <Text type="secondary">版本已固化</Text>
                              : <Button size="small" onClick={() => openRuleDrawer(item)}>编辑</Button>,
                          },
                        ]}
                      />
                      <Button
                        type="primary"
                        loading={activeAction === 'compile'}
                        disabled={approvedRuleOptions.length === 0}
                        onClick={compileRules}
                        style={{ marginTop: 16 }}
                      >
                        编译规则包
                      </Button>
                    </Form>
                    <Divider />
                    <div className="rule-stage-header">
                      <div className="rule-stage-title">
                        <strong>已生成规则包</strong>
                        <Text type="secondary">规则包生成后保留独立版本，业务应用按版本绑定，不直接读取草稿规则。</Text>
                      </div>
                    </div>
                    <Table
                      className="rule-table-card"
                      rowKey={(item) => `${item.kind}:${item.version}`}
                      dataSource={packages}
                      pagination={{ pageSize: 6 }}
                      columns={[
                        { title: '版本', dataIndex: 'version', width: 140, render: (value: string) => <Text strong>{value}</Text> },
                        {
                          title: '阶段',
                          dataIndex: 'stage',
                          width: 120,
                          render: (value: string) => <Tag color={value === 'ga' ? 'green' : value === 'staging' ? 'blue' : 'default'}>{packageStageLabels[value] || value}</Tag>,
                        },
                        { title: '规则数', width: 100, render: (_: unknown, item: RulePackage) => item.payload?.rules?.length || 0 },
                        { title: '说明', render: (_: unknown, item: RulePackage) => item.payload?.description || item.notes || '-' },
                        { title: '更新时间', dataIndex: 'updated_at', width: 190, render: (value: string) => value ? new Date(value).toLocaleString() : '-' },
                        {
                          title: '操作',
                          width: 100,
                          render: (_: unknown, item: RulePackage) => (
                            <Button size="small" onClick={() => Modal.info({
                              title: `规则包 ${item.version}`,
                              width: 780,
                              content: <pre style={{ maxHeight: '58vh', overflow: 'auto', whiteSpace: 'pre-wrap' }}>{JSON.stringify(item.payload, null, 2)}</pre>,
                            })}>查看</Button>
                          ),
                        },
                      ]}
                    />
                  </>
                ),
              },
            ]}
          />
        </div>
      )}

      <Drawer
        title={reviewSource ? `规则校对 · ${reviewSource.title}` : '规则校对'}
        width="92vw"
        open={reviewDrawerOpen}
        onClose={() => {
          setReviewDrawerOpen(false);
          setReviewSource(null);
          setSelectedReviewRuleId('');
        }}
      >
        {reviewSource && (
          <div className="rule-review-layout">
            <section className="rule-review-source">
              <div className="rule-review-pane-header">
                <div>
                  <Text strong>来源原文</Text>
                  <div><Text type="secondary">{reviewSource.file_name || reviewSource.title}</Text></div>
                </div>
                {getPrimaryEvidence(selectedReviewRule)?.locator && (
                  <Tag color="blue">{getPrimaryEvidence(selectedReviewRule)?.locator}</Tag>
                )}
              </div>
              <pre className="rule-source-document">
                {renderHighlightedSource(reviewSource.raw_text || '当前来源没有可显示的原文。', getPrimaryEvidence(selectedReviewRule)?.quote)}
              </pre>
            </section>

            <section className="rule-review-rules">
              <div className="rule-review-pane-header">
                <div>
                  <Text strong>提取规则</Text>
                  <div><Text type="secondary">共 {reviewSourceRules.length} 条，逐条核对条件与引用。</Text></div>
                </div>
              </div>
              <div className="rule-review-body">
                <div className="rule-review-list">
                  {reviewSourceRules.map((rule) => {
                    const blockers = getRuleQualityBlockers(rule);
                    return (
                      <button
                        type="button"
                        className={`rule-review-list-item${selectedReviewRule?.id === rule.id ? ' is-active' : ''}`}
                        key={rule.id}
                        onClick={() => setSelectedReviewRuleId(rule.id)}
                      >
                        <span className="rule-review-list-title">{rule.name}</span>
                        <span className="rule-review-list-meta">
                          <Tag color={statusColors[rule.status]}>{statusLabels[rule.status] || rule.status}</Tag>
                          {blockers.length ? <Text type="warning">{blockers.length} 项待补</Text> : <Text type="success">质量完整</Text>}
                        </span>
                      </button>
                    );
                  })}
                </div>

                <div className="rule-review-detail">
                  {selectedReviewRule ? (
                    <>
                      <div className="rule-review-detail-header">
                        <div>
                          <Text code>{selectedReviewRule.rule_code}</Text>
                          <Title level={5}>{selectedReviewRule.name}</Title>
                        </div>
                        <Space wrap>
                          {!['packaged', 'released', 'deprecated'].includes(selectedReviewRule.status) && (
                            <Button onClick={() => openRuleDrawer(selectedReviewRule)}>编辑规则</Button>
                          )}
                          {(selectedReviewRule.status === 'draft' || selectedReviewRule.status === 'rejected') && (
                            <Button
                              type="primary"
                              loading={activeAction === `submit:${selectedReviewRule.id}`}
                              onClick={() => submitReview(selectedReviewRule)}
                            >
                              提交审核
                            </Button>
                          )}
                          {selectedReviewRule.status === 'reviewing' && (
                            <>
                              <Button
                                type="primary"
                                disabled={!qualityReports[selectedReviewRule.id]?.can_approve}
                                loading={activeAction === `approve:${selectedReviewRule.id}`}
                                onClick={() => reviewRule(selectedReviewRule, true)}
                              >
                                通过
                              </Button>
                              <Button
                                danger
                                loading={activeAction === `reject:${selectedReviewRule.id}`}
                                onClick={() => reviewRule(selectedReviewRule, false)}
                              >
                                退回
                              </Button>
                            </>
                          )}
                        </Space>
                      </div>

                      {getRuleQualityBlockers(selectedReviewRule).length > 0 ? (
                        <Alert
                          type="warning"
                          showIcon
                          message="批准前需要补充"
                          description={getRuleQualityBlockers(selectedReviewRule).join('；')}
                        />
                      ) : (
                        <Alert
                          type={qualityReports[selectedReviewRule.id]?.warnings.length ? 'info' : 'success'}
                          showIcon
                          message="规则结构完整，可以进入批准流程"
                          description={qualityReports[selectedReviewRule.id]?.warnings
                            .map((issue) => qualityIssueLabels[issue.code] || issue.message)
                            .join('；') || undefined}
                        />
                      )}

                      <div className="rule-review-summary">
                        <div><Text type="secondary">目标对象</Text><strong>{selectedReviewRule.target_entity_type || '-'}</strong></div>
                        <div><Text type="secondary">风险级别</Text><Tag color={severityColors[selectedReviewRule.severity]}>{selectedReviewRule.severity}</Tag></div>
                        <div><Text type="secondary">处理动作</Text><Tag>{selectedReviewRule.action}</Tag></div>
                        <div><Text type="secondary">版本</Text><strong>{selectedReviewRule.version}</strong></div>
                      </div>

                      <Divider orientation="left">触发条件</Divider>
                      <Table
                        size="small"
                        rowKey={(_, index) => String(index)}
                        dataSource={selectedReviewRule.conditions || []}
                        pagination={false}
                        columns={[
                          { title: '字段路径', dataIndex: 'path' },
                          { title: '运算符', dataIndex: 'operator', width: 100 },
                          { title: '比较值', dataIndex: 'value', render: (value: unknown) => displayScalarValue(value) || '-' },
                        ]}
                      />

                      <Divider orientation="left">原文依据</Divider>
                      {(selectedReviewRule.evidence_refs || []).map((item, index) => {
                        const evidence = item as EvidenceReference;
                        return (
                          <div className="rule-review-evidence" key={`${evidence.locator || 'evidence'}:${index}`}>
                            <Tag color="blue">{evidence.locator || '未标注位置'}</Tag>
                            <Text>{evidence.quote || '未保存引用原文'}</Text>
                          </div>
                        );
                      })}

                      <Divider orientation="left">测试用例</Divider>
                      {selectedReviewRule.test_cases?.length ? (
                        <Table
                          size="small"
                          rowKey={(_, index) => String(index)}
                          dataSource={selectedReviewRule.test_cases}
                          pagination={false}
                          columns={[
                            { title: '名称', dataIndex: 'name' },
                            { title: '预期', dataIndex: 'expected_hit', width: 100, render: (value: boolean) => value ? '命中' : '不命中' },
                          ]}
                        />
                      ) : (
                        <Text type="secondary">暂无测试用例</Text>
                      )}
                    </>
                  ) : (
                    <Alert type="info" showIcon message="当前来源还没有规则候选，请先执行提取。" />
                  )}
                </div>
              </div>
            </section>
          </div>
        )}
      </Drawer>

      <Drawer title="新增规则来源" width={560} open={sourceDrawerOpen} onClose={() => setSourceDrawerOpen(false)}
        extra={<Button type="primary" loading={saving} onClick={createSource}>保存</Button>}>
        <Form form={sourceForm} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入来源标题' }]}>
            <Input placeholder="某类合同审查规则 / 招标文件审查口径" />
          </Form.Item>
          <Form.Item name="source_type" label="来源类型" rules={[{ required: true }]}>
            <Select options={sourceTypes} />
          </Form.Item>
          <Form.Item label="上传文件">
            <Upload
              accept=".docx,.txt,.md"
              maxCount={1}
              beforeUpload={(nextFile) => {
                const extension = nextFile.name.toLowerCase().split('.').pop();
                if (!extension || !['docx', 'txt', 'md'].includes(extension)) {
                  message.error('只支持 DOCX、TXT、MD 文件');
                  return Upload.LIST_IGNORE;
                }
                if (nextFile.size > 20 * 1024 * 1024) {
                  message.error('文件不能超过 20 MB');
                  return Upload.LIST_IGNORE;
                }
                setSourceFile(nextFile);
                if (!sourceForm.getFieldValue('title')) sourceForm.setFieldValue('title', nextFile.name);
                return false;
              }}
              onRemove={() => setSourceFile(null)}
              fileList={sourceFile ? [{ uid: 'source-file', name: sourceFile.name, status: 'done' }] : []}
            >
              <Button icon={<UploadOutlined />}>选择 DOCX/TXT/MD</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="raw_text" label="直接输入来源文本">
            <Input.TextArea rows={8} />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer title={editingRule ? '编辑规则条目' : '手工新增规则'} width={860} open={ruleDrawerOpen} onClose={() => {
        setRuleDrawerOpen(false);
        setEditingRule(null);
      }}
        extra={<Button type="primary" loading={saving} onClick={saveRule}>保存</Button>}>
        <Form form={ruleForm} layout="vertical">
          <Form.Item name="rule_code" label="规则编号" rules={[{ required: true }]}>
            <Input placeholder="CONTRACT_PAYMENT_TERM_GT_90D" disabled={!!editingRule} />
          </Form.Item>
          <Form.Item name="name" label="规则名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="source_document_id" label="来源文档">
            <Select allowClear options={sourceOptions} />
          </Form.Item>
          <Space align="start">
            <Form.Item name="target_entity_type" label="目标对象"><Input style={{ width: 180 }} /></Form.Item>
            <Form.Item name="severity" label="级别"><Select style={{ width: 130 }} options={['low', 'medium', 'high', 'critical'].map((value) => ({ label: value, value }))} /></Form.Item>
            <Form.Item name="action" label="动作"><Select style={{ width: 130 }} options={['flag', 'block', 'recommend'].map((value) => ({ label: value, value }))} /></Form.Item>
            <Form.Item name="version" label="版本"><Input style={{ width: 100 }} /></Form.Item>
          </Space>
          <Form.Item name="description" label="说明"><Input.TextArea rows={3} /></Form.Item>
          <Divider orientation="left">触发条件</Divider>
          <Text type="secondary">字段路径使用运行时对象路径，例如 entity.payment_term_days。多个条件按 AND 执行。</Text>
          <Form.List name="conditions">
            {(fields, { add, remove }) => (
              <div className="rule-form-list">
                {fields.map((field) => (
                  <div className="rule-form-row" key={field.key}>
                    <Form.Item {...field} name={[field.name, 'path']} rules={[{ required: true, message: '请输入字段路径' }]}>
                      <Input placeholder="entity.payment_term_days" />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'operator']} rules={[{ required: true, message: '请选择运算符' }]}>
                      <Select
                        placeholder="运算符"
                        options={['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'contains', 'in', 'exists'].map((value) => ({ label: value, value }))}
                      />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'value']}>
                      <Input placeholder="比较值；exists 可留空" />
                    </Form.Item>
                    <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除条件" onClick={() => remove(field.name)} />
                  </div>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ path: '', operator: 'exists', value: '' })}>增加条件</Button>
              </div>
            )}
          </Form.List>

          <Divider orientation="left">原文依据</Divider>
          <Text type="secondary">每条规则至少保留一个可回溯位置。引用内容用于审核和最终报告展示。</Text>
          <Form.List name="evidence_refs">
            {(fields, { add, remove }) => (
              <div className="rule-form-list">
                {fields.map((field) => (
                  <div className="rule-evidence-row" key={field.key}>
                    <div className="rule-form-row">
                      <Form.Item {...field} name={[field.name, 'source_document_id']}>
                        <Select allowClear placeholder="来源文档" options={sourceOptions} />
                      </Form.Item>
                      <Form.Item {...field} name={[field.name, 'locator']} rules={[{ required: true, message: '请输入条款位置' }]}>
                        <Input placeholder="第三章 / 第二十一条 / 段落 18" />
                      </Form.Item>
                      <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除依据" onClick={() => remove(field.name)} />
                    </div>
                    <Form.Item {...field} name={[field.name, 'quote']}>
                      <Input.TextArea rows={2} placeholder="粘贴与本规则直接相关的原文片段" />
                    </Form.Item>
                  </div>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ locator: '', quote: '' })}>增加原文依据</Button>
              </div>
            )}
          </Form.List>

          <Divider orientation="left">测试用例</Divider>
          <Text type="secondary">高危和关键规则必须有测试用例。样例数据是规则执行时接收的业务对象。</Text>
          <Form.List name="test_cases">
            {(fields, { add, remove }) => (
              <div className="rule-form-list">
                {fields.map((field) => (
                  <div className="rule-test-row" key={field.key}>
                    <div className="rule-form-row">
                      <Form.Item {...field} name={[field.name, 'name']} rules={[{ required: true, message: '请输入用例名称' }]}>
                        <Input placeholder="付款周期超过 90 天应命中" />
                      </Form.Item>
                      <Form.Item {...field} name={[field.name, 'expected_hit']} valuePropName="checked">
                        <Checkbox>预期命中</Checkbox>
                      </Form.Item>
                      <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除测试用例" onClick={() => remove(field.name)} />
                    </div>
                    <Form.Item
                      {...field}
                      name={[field.name, 'graph']}
                      label="样例数据"
                      rules={[{ validator: validateJsonObject }]}
                    >
                      <Input.TextArea rows={4} placeholder={'{\n  "entity": {\n    "payment_term_days": 120\n  }\n}'} />
                    </Form.Item>
                  </div>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ name: '', expected_hit: true, graph: '{\n  \"entity\": {}\n}' })}>增加测试用例</Button>
              </div>
            )}
          </Form.List>
          <Form.Item name="tags" label="标签"><Input placeholder="contract,risk" /></Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default RuleLibraryWorkbench;
