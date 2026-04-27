import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Col, Form, Input, Modal, Row, Segmented, Select, Space, Switch, Table, Tabs, Tag, Typography, message } from 'antd';
import type { AxiosInstance } from 'axios';
import { Background, Controls, MarkerType, MiniMap, Panel, ReactFlow, type Connection, type Edge, type Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import * as dagre from 'dagre';
import { Boxes, CheckCircle2, Circle, Database, FlaskConical, GitBranch, Rocket, ShieldCheck } from 'lucide-react';

const { Text } = Typography;
const { TextArea } = Input;

type PackageKind = 'schema' | 'mapping' | 'rule';
type Stage = 'draft' | 'review' | 'staging' | 'ga' | 'deprecated';
type WorkbenchViewMode = 'guided' | 'graph' | 'pro';
type GuidedStep = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;
type GraphExplorerMode = 'focus' | 'search' | 'all';
type SourceInputKind = 'json' | 'table';
type DataSourceEntryMode = 'connector' | 'sample';
type DataSourceKind = 'database' | 'api' | 'protocol' | 'file' | 'stream';

interface VisualAttribute {
  id: string;
  name: string;
  data_type: 'string' | 'number' | 'integer' | 'boolean';
  required: boolean;
}

interface VisualRelation {
  id: string;
  name: string;
  target_entity_id?: string;
  target_type: string;
  cardinality: 'one' | 'many';
}

interface VisualEntity {
  id: string;
  name: string;
  attributes: VisualAttribute[];
  relations: VisualRelation[];
}

interface VisualMappingField {
  id: string;
  source_path: string;
  target_attr: string;
  transform: '' | 'trim' | 'lower' | 'upper' | 'to_int' | 'to_float' | 'to_bool';
  required: boolean;
}

interface VisualRuleCondition {
  id: string;
  path: string;
  operator: 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'contains' | 'in' | 'exists';
  value: string;
}

interface SourceField {
  path: string;
  name: string;
  data_type: VisualAttribute['data_type'];
  required: boolean;
  sample: string;
  ignored?: boolean;
  source?: string;
}

interface OntologyDataSource {
  id: string;
  space_id: string;
  name: string;
  kind: DataSourceKind;
  protocol: string;
  config: Record<string, unknown>;
  secret_ref?: string | null;
  status: 'draft' | 'active' | 'disabled';
  last_test_status?: string | null;
  last_test_message?: string | null;
  created_by: string;
  created_at: string;
}

interface DiscoveredColumn {
  name: string;
  data_type: VisualAttribute['data_type'];
  nullable: boolean;
  primary_key: boolean;
  description?: string;
  source_path?: string;
}

interface DiscoveredEntity {
  name: string;
  source: string;
  columns: DiscoveredColumn[];
  primary_keys: string[];
  description?: string;
}

interface DataSourceDiscoveryResult {
  ok: boolean;
  status: string;
  message: string;
  source_id: string;
  protocol: string;
  entities: DiscoveredEntity[];
  warnings: string[];
}

interface OntologySecretRecord {
  id: string;
  space_id: string;
  scope: string;
  name: string;
  ref: string;
  description?: string | null;
  created_by: string;
  created_at: string;
  updated_at?: string | null;
}

interface OrgItem {
  id: string;
  code: string;
  name: string;
  description?: string;
  owner_user_id: string;
  is_active: boolean;
  created_at: string;
}

interface SpaceItem {
  id: string;
  name: string;
  code: string;
  description?: string;
  owner_user_id: string;
  org_id?: string | null;
  created_at: string;
}

interface PackageItem {
  kind: PackageKind;
  space_id: string;
  version: string;
  stage: Stage;
  created_by: string;
  created_at: string;
  updated_at: string;
  notes?: string;
  payload: Record<string, unknown>;
}

interface ReleaseEvent {
  id: string;
  space_id: string;
  kind: PackageKind;
  version: string;
  from_stage: Stage;
  to_stage: Stage;
  actor_user_id: string;
  notes?: string;
  warnings: string[];
  created_at: string;
}

interface ApprovalItem {
  id: string;
  space_id: string;
  package_id: string;
  kind: PackageKind;
  version: string;
  requested_stage: Stage;
  status: 'pending' | 'approved' | 'rejected';
  requester_user_id: string;
  reviewer_user_id?: string;
  request_note?: string;
  review_note?: string;
  reviewed_at?: string;
  created_at: string;
}

interface DiffResponse {
  space_id: string;
  kind: PackageKind;
  from_version: string;
  to_version: string;
  summary: Record<string, unknown>;
  breaking_changes: string[];
}

interface Props {
  api: AxiosInstance;
}

const DEFAULT_PAYLOADS: Record<PackageKind, string> = {
  schema: JSON.stringify(
    {
      space_id: '',
      version: '1.0.0',
      description: 'schema package',
      entity_types: [{ name: 'Entity', attributes: { name: { data_type: 'string', required: true } }, relations: [] }],
      taxonomy: {},
      vocabulary: {},
    },
    null,
    2,
  ),
  mapping: JSON.stringify(
    {
      space_id: '',
      version: '1.0.0',
      description: 'mapping package',
      entity_mappings: [
        {
          entity_type: 'Entity',
          source_path: 'item',
          id_template: 'entity:{{row.id}}',
          field_mappings: [{ source_path: 'name', target_attr: 'name', required: true, transform: 'trim' }],
        },
      ],
      relation_mappings: [],
    },
    null,
    2,
  ),
  rule: JSON.stringify(
    {
      space_id: '',
      version: '1.0.0',
      description: 'rule package',
      rules: [
        {
          rule_id: 'RULE_EXISTS',
          name: 'Entity must have name',
          target_entity_type: 'Entity',
          severity: 'medium',
          action: 'flag',
          conditions: [{ path: 'entity.name', operator: 'exists' }],
          tags: [],
        },
      ],
    },
    null,
    2,
  ),
};

const pretty = (data: unknown) => JSON.stringify(data, null, 2);
const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
const createDefaultVisualEntities = (): VisualEntity[] => [
  {
    id: uid(),
    name: 'Entity',
    attributes: [
      { id: uid(), name: 'id', data_type: 'string', required: true },
      { id: uid(), name: 'name', data_type: 'string', required: false },
    ],
    relations: [],
  },
];
const NEXT_STAGE_MAP: Record<Stage, Stage | null> = {
  draft: 'review',
  review: 'staging',
  staging: 'ga',
  ga: 'deprecated',
  deprecated: null,
};
const STAGE_LABELS: Record<Stage, string> = {
  draft: '草稿',
  review: '评审',
  staging: '预发',
  ga: '正式',
  deprecated: '废弃',
};
const KIND_LABELS: Record<PackageKind, string> = {
  schema: '数据结构',
  mapping: '数据映射',
  rule: '业务规则',
};
const RISK_LABELS: Record<string, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  critical: '严重风险',
  none: '无风险',
  未执行: '未执行',
};

const pickRunnablePackage = (items: PackageItem[]) => {
  if (items.length === 0) return null;
  return (
    items.find((item) => item.stage === 'ga') ||
    items.find((item) => item.stage === 'staging') ||
    items.find((item) => item.stage === 'review') ||
    items[0]
  );
};

const getRequestErrorMessage = (error: unknown, fallback: string) => {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
  }
  return fallback;
};

const inferDataType = (value: unknown): VisualAttribute['data_type'] => {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number';
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (/^-?\d+$/.test(trimmed)) return 'integer';
    if (/^-?\d+\.\d+$/.test(trimmed)) return 'number';
  }
  return 'string';
};

const coerceVisualDataType = (value: unknown): VisualAttribute['data_type'] => {
  return ['string', 'number', 'integer', 'boolean'].includes(String(value))
    ? (String(value) as VisualAttribute['data_type'])
    : 'string';
};

const fieldNameFromPath = (path: string) => {
  const last = path.split('.').filter(Boolean).pop() || path;
  return last.replace(/\[\]/g, '').replace(/[^a-zA-Z0-9_\u4e00-\u9fa5]/g, '_') || 'field';
};

const collectSourceFields = (input: unknown, prefix = ''): SourceField[] => {
  if (Array.isArray(input)) {
    const sample = input[0];
    return sample === undefined ? [] : collectSourceFields(sample, prefix ? `${prefix}[]` : 'items[]');
  }
  if (input && typeof input === 'object') {
    return Object.entries(input as Record<string, unknown>).flatMap(([key, value]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      if (value && typeof value === 'object') return collectSourceFields(value, path);
      return [{
        path,
        name: fieldNameFromPath(path),
        data_type: inferDataType(value),
        required: value !== null && value !== undefined && value !== '',
        sample: value === null || value === undefined ? '' : String(value).slice(0, 80),
      }];
    });
  }
  return [];
};

const rootEntityNameFromSample = (input: unknown) => {
  if (input && typeof input === 'object' && !Array.isArray(input)) {
    const entries = Object.entries(input as Record<string, unknown>);
    if (entries.length === 1 && entries[0][1] && typeof entries[0][1] === 'object') {
      return fieldNameFromPath(entries[0][0]).replace(/^\w/, (char) => char.toUpperCase());
    }
  }
  return 'Entity';
};

const parseDelimitedLine = (line: string, delimiter: string) => {
  const cells: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === '"' && inQuotes && next === '"') {
      current += '"';
      index += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === delimiter && !inQuotes) {
      cells.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
};

const parseTableSample = (text: string) => {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.length < 2) throw new Error('至少需要表头和一行样本数据');
  const delimiter = lines[0].includes('\t') ? '\t' : ',';
  const headers = parseDelimitedLine(lines[0], delimiter).map((header, index) => fieldNameFromPath(header || `field_${index + 1}`));
  const rows = lines.slice(1, 26).map((line) => {
    const cells = parseDelimitedLine(line, delimiter);
    return Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? '']));
  });
  const fields: SourceField[] = headers.map((header) => {
    const values = rows.map((row) => row[header]).filter((value) => value !== '');
    const sample = values[0] ?? '';
    return {
      path: header,
      name: header,
      data_type: inferDataType(sample),
      required: rows.length > 0 && rows.every((row) => row[header] !== ''),
      sample,
    };
  });
  return { fields, rows };
};

const normalizeSourceFields = (fields: SourceField[]) =>
  fields.map((field) => ({ ...field, ignored: field.ignored ?? false }));

const updateSourceField = (
  setSourceFields: React.Dispatch<React.SetStateAction<SourceField[]>>,
  path: string,
  patch: Partial<SourceField>,
) => {
  setSourceFields((prev) => prev.map((field) => (field.path === path ? { ...field, ...patch } : field)));
};

const visualEntitiesFromSchemaPayload = (payload: Record<string, unknown>): VisualEntity[] => {
  const rawEntities = Array.isArray(payload.entity_types) ? payload.entity_types : [];
  const baseEntities = rawEntities
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    .map((item) => {
      const attributes = item.attributes && typeof item.attributes === 'object' && !Array.isArray(item.attributes)
        ? (item.attributes as Record<string, unknown>)
        : {};
      return {
        id: uid(),
        name: typeof item.name === 'string' && item.name.trim() ? item.name.trim() : 'Entity',
        attributes: Object.entries(attributes).map(([name, raw]) => {
          const def = raw && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
          const dataType = typeof def.data_type === 'string' ? def.data_type : 'string';
          return {
            id: uid(),
            name,
            data_type: ['string', 'number', 'integer', 'boolean'].includes(dataType)
              ? (dataType as VisualAttribute['data_type'])
              : 'string',
            required: Boolean(def.required),
          };
        }),
        relations: [] as VisualRelation[],
      };
    });

  const entities = baseEntities.length > 0
    ? baseEntities
    : createDefaultVisualEntities();
  const entityIdByName = new Map(entities.map((entity) => [entity.name, entity.id]));

  rawEntities.forEach((raw, index) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw) || !entities[index]) return;
    const rawRelations = Array.isArray((raw as Record<string, unknown>).relations)
      ? ((raw as Record<string, unknown>).relations as unknown[])
      : [];
    entities[index].relations = rawRelations
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
      .map((relation) => {
        const targetType = typeof relation.target_type === 'string' && relation.target_type.trim()
          ? relation.target_type.trim()
          : entities[index].name;
        const cardinality = relation.cardinality === 'one' ? 'one' : 'many';
        return {
          id: uid(),
          name: typeof relation.name === 'string' ? relation.name : '',
          target_entity_id: entityIdByName.get(targetType),
          target_type: targetType,
          cardinality,
        };
      });
  });

  return entities;
};

const pageStyle: React.CSSProperties = {
  padding: 24,
  overflow: 'auto',
  height: '100%',
  background: '#f5f7fb',
};

const shellStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 20,
  maxWidth: 1680,
  margin: '0 auto',
};

const surfaceStyle: React.CSSProperties = {
  borderRadius: 12,
  border: '1px solid #e5e7eb',
  boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
  background: '#ffffff',
};

const sectionCardStyle: React.CSSProperties = {
  ...surfaceStyle,
  borderRadius: 12,
  boxShadow: '0 6px 18px rgba(15, 23, 42, 0.035)',
};

const mutedTextStyle: React.CSSProperties = {
  color: '#64748b',
  fontSize: 13,
  lineHeight: 1.6,
};

const fieldLabelStyle: React.CSSProperties = {
  display: 'block',
  marginBottom: 8,
  color: '#334155',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.04em',
};

const toolbarStyle: React.CSSProperties = {
  ...surfaceStyle,
  minHeight: 64,
  padding: '12px 16px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 16,
};

const stepHeaderStyle: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 10,
  background: '#ffffff',
  padding: '14px 16px',
  marginBottom: 16,
};

const contentCardStyle: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 10,
  background: '#ffffff',
  boxShadow: 'none',
};

const getAllowedReleaseTargets = (stage: Stage): Stage[] => {
  const next = NEXT_STAGE_MAP[stage];
  if (!next) return [];
  if (next === 'deprecated') return ['deprecated'];
  return [next, 'deprecated'];
};

const OntologyWorkbench: React.FC<Props> = ({ api }) => {
  const [orgs, setOrgs] = useState<OrgItem[]>([]);
  const [newOrgCode, setNewOrgCode] = useState('');
  const [newOrgName, setNewOrgName] = useState('');
  const [selectedOrgFilter, setSelectedOrgFilter] = useState<string>('all');
  const [spaceOrgId, setSpaceOrgId] = useState<string | undefined>(undefined);

  const [spaces, setSpaces] = useState<SpaceItem[]>([]);
  const [selectedSpaceId, setSelectedSpaceId] = useState<string | null>(null);
  const [spacePackageSummary, setSpacePackageSummary] = useState<Record<PackageKind, PackageItem[]>>({
    schema: [],
    mapping: [],
    rule: [],
  });

  const [kind, setKind] = useState<PackageKind>('schema');
  const [version, setVersion] = useState<string>('1.0.0');
  const [payloadText, setPayloadText] = useState<string>(DEFAULT_PAYLOADS.schema);

  const [packages, setPackages] = useState<PackageItem[]>([]);
  const [events, setEvents] = useState<ReleaseEvent[]>([]);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [approvalTargetVersion, setApprovalTargetVersion] = useState<string>('');
  const [approvalTargetStage, setApprovalTargetStage] = useState<'staging' | 'ga'>('staging');
  const [diffFromVersion, setDiffFromVersion] = useState<string>('');
  const [diffToVersion, setDiffToVersion] = useState<string>('');
  const [diffResult, setDiffResult] = useState<string>('');
  const [diffObj, setDiffObj] = useState<DiffResponse | null>(null);

  const [mappingInput, setMappingInput] = useState<string>(pretty({ item: { id: 'demo-1', name: 'demo name' } }));
  const [mappingResult, setMappingResult] = useState<string>('');

  const [ruleGraphInput, setRuleGraphInput] = useState<string>(
    pretty({ entities: [{ id: 'entity:demo-1', entity_type: 'Entity', attributes: { name: 'demo name' } }], relations: [] }),
  );
  const [ruleResult, setRuleResult] = useState<string>('');
  const [latestDecisionId, setLatestDecisionId] = useState<string>('');
  const [explainResult, setExplainResult] = useState<string>('');

  const [loading, setLoading] = useState<boolean>(false);
  const [strictCompatibility, setStrictCompatibility] = useState<boolean>(false);
  const [viewMode, setViewMode] = useState<WorkbenchViewMode>('guided');
  const [activeTab, setActiveTab] = useState<string>('packages');
  const [guidedStep, setGuidedStep] = useState<GuidedStep>(0);
  const [guidedBuilderKind, setGuidedBuilderKind] = useState<PackageKind>('schema');
  const [schemaInspectorMode, setSchemaInspectorMode] = useState<'graph' | 'summary'>('graph');
  const [graphExplorerMode, setGraphExplorerMode] = useState<GraphExplorerMode>('focus');
  const [graphExplorerQuery, setGraphExplorerQuery] = useState<string>('');
  const [selectedGraphEdgeId, setSelectedGraphEdgeId] = useState<string | null>(null);
  const [sourceInputKind, setSourceInputKind] = useState<SourceInputKind>('json');
  const [sourceSampleText, setSourceSampleText] = useState<string>(pretty({ item: { id: 'demo-1', name: 'demo name', amount: 1000, active: true } }));
  const [sourceFields, setSourceFields] = useState<SourceField[]>([]);
  const [sourceEntityName, setSourceEntityName] = useState<string>('Entity');
  const [dataSourceEntryMode, setDataSourceEntryMode] = useState<DataSourceEntryMode>('connector');
  const [dataSources, setDataSources] = useState<OntologyDataSource[]>([]);
  const [secrets, setSecrets] = useState<OntologySecretRecord[]>([]);
  const [secretScope, setSecretScope] = useState<string>('prod');
  const [secretName, setSecretName] = useState<string>('db-password');
  const [secretValue, setSecretValue] = useState<string>('');
  const [secretDescription, setSecretDescription] = useState<string>('');
  const [dataSourceKind, setDataSourceKind] = useState<DataSourceKind>('database');
  const [dataSourceName, setDataSourceName] = useState<string>('业务数据库');
  const [dataSourceProtocol, setDataSourceProtocol] = useState<string>('postgresql');
  const [dataSourceConfigText, setDataSourceConfigText] = useState<string>(pretty({ host: '127.0.0.1', port: 5432, database: 'app', schema: 'public' }));
  const [dataSourceSecretRef, setDataSourceSecretRef] = useState<string>('');
  const [visualSchemaVersion, setVisualSchemaVersion] = useState<string>('1.0.0');
  const [visualEntities, setVisualEntities] = useState<VisualEntity[]>(createDefaultVisualEntities);
  const [activeVisualEntityId, setActiveVisualEntityId] = useState<string | null>(null);
  const [visualMappingVersion, setVisualMappingVersion] = useState<string>('1.0.0');
  const [visualMappingEntityType, setVisualMappingEntityType] = useState<string>('Entity');
  const [visualMappingSourcePath, setVisualMappingSourcePath] = useState<string>('item');
  const [visualMappingIdTemplate, setVisualMappingIdTemplate] = useState<string>('entity:{{row.id}}');
  const [visualMappingFields, setVisualMappingFields] = useState<VisualMappingField[]>([
    { id: uid(), source_path: 'id', target_attr: 'id', transform: 'trim', required: true },
    { id: uid(), source_path: 'name', target_attr: 'name', transform: 'trim', required: false },
  ]);
  const [visualRuleVersion, setVisualRuleVersion] = useState<string>('1.0.0');
  const [visualRuleId, setVisualRuleId] = useState<string>('RULE_EXISTS');
  const [visualRuleName, setVisualRuleName] = useState<string>('关键字段存在性检查');
  const [visualRuleSeverity, setVisualRuleSeverity] = useState<'low' | 'medium' | 'high' | 'critical'>('high');
  const [visualRuleAction, setVisualRuleAction] = useState<'flag' | 'block' | 'recommend'>('flag');
  const [visualRuleTargetEntityType, setVisualRuleTargetEntityType] = useState<string>('Entity');
  const [visualRuleConditions, setVisualRuleConditions] = useState<VisualRuleCondition[]>([
    { id: uid(), path: 'entity.id', operator: 'exists', value: '' },
  ]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const sourceFileInputRef = useRef<HTMLInputElement | null>(null);
  const schemaHydrationKeyRef = useRef<string>('');

  const selectedSpace = useMemo(() => spaces.find((item) => item.id === selectedSpaceId) || null, [spaces, selectedSpaceId]);
  const visibleSpaces = useMemo(
    () => (selectedOrgFilter === 'all' ? spaces : spaces.filter((s) => (s.org_id || '__none__') === selectedOrgFilter)),
    [spaces, selectedOrgFilter],
  );
  const hasSchema = useMemo(() => spacePackageSummary.schema.length > 0, [spacePackageSummary]);
  const hasMapping = useMemo(() => spacePackageSummary.mapping.length > 0, [spacePackageSummary]);
  const hasRule = useMemo(() => spacePackageSummary.rule.length > 0, [spacePackageSummary]);
  const hasGaAll = useMemo(() => {
    const kinds: PackageKind[] = ['schema', 'mapping', 'rule'];
    return kinds.every((k) => spacePackageSummary[k].some((p) => p.stage === 'ga'));
  }, [spacePackageSummary]);
  const hasDecision = !!latestDecisionId;
  const latestGuidedPackages = useMemo<Record<PackageKind, PackageItem | null>>(
    () => ({
      schema: pickRunnablePackage(spacePackageSummary.schema),
      mapping: pickRunnablePackage(spacePackageSummary.mapping),
      rule: pickRunnablePackage(spacePackageSummary.rule),
    }),
    [spacePackageSummary],
  );
  const runnableSchemaPackage = latestGuidedPackages.schema;
  const runnableMappingPackage = latestGuidedPackages.mapping;
  const runnableRulePackage = latestGuidedPackages.rule;
  const activeVisualEntity = useMemo(
    () => visualEntities.find((entity) => entity.id === activeVisualEntityId) || visualEntities[0] || null,
    [activeVisualEntityId, visualEntities],
  );
  const selectedGraphRelation = useMemo(() => {
    if (!selectedGraphEdgeId) return null;
    for (const entity of visualEntities) {
      const relation = (entity.relations || []).find((item) => item.id === selectedGraphEdgeId);
      if (relation) return { source: entity, relation };
    }
    return null;
  }, [selectedGraphEdgeId, visualEntities]);
  const mappingResultObj = useMemo<Record<string, unknown> | null>(() => {
    if (!mappingResult) return null;
    try {
      return JSON.parse(mappingResult) as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [mappingResult]);
  const ruleResultObj = useMemo<Record<string, unknown> | null>(() => {
    if (!ruleResult) return null;
    try {
      return JSON.parse(ruleResult) as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [ruleResult]);
  const explainResultObj = useMemo<Record<string, unknown> | null>(() => {
    if (!explainResult) return null;
    try {
      return JSON.parse(explainResult) as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [explainResult]);
  const mappedEntityCount = useMemo(() => {
    const graph = mappingResultObj?.graph as { entities?: unknown[] } | undefined;
    return Array.isArray(graph?.entities) ? graph.entities.length : 0;
  }, [mappingResultObj]);
  const ruleRiskLevel = String(ruleResultObj?.risk_level || ruleResultObj?.overall_risk || '未执行');
  const explainWhyCount = useMemo(() => {
    const why = explainResultObj?.why;
    return Array.isArray(why) ? why.length : 0;
  }, [explainResultObj]);
  const schemaGraph = useMemo(() => {
    const width = 360;
    const height = 300;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = visualEntities.length <= 2 ? 82 : 112;
    const nodes = visualEntities.map((entity, index) => {
      const angle = visualEntities.length === 1 ? -Math.PI / 2 : (Math.PI * 2 * index) / visualEntities.length - Math.PI / 2;
      return {
        id: entity.id,
        name: entity.name || `对象${index + 1}`,
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
      };
    });
    const edges = visualEntities.flatMap((entity) =>
      (entity.relations || [])
        .filter((relation) => relation.name.trim() && relation.target_type.trim())
        .map((relation) => {
          const source = nodes.find((node) => node.id === entity.id);
          const target = nodes.find((node) => node.id === relation.target_entity_id) || nodes.find((node) => node.name === relation.target_type.trim());
          return source && target ? { ...relation, source, target } : null;
        })
        .filter(
          (
            edge,
          ): edge is VisualRelation & {
            source: { id: string; name: string; x: number; y: number };
            target: { id: string; name: string; x: number; y: number };
          } => Boolean(edge),
        ),
    );
    return { width, height, nodes, edges };
  }, [visualEntities]);
  const graphExplorerData = useMemo(() => {
    const width = 1400;
    const height = 860;
    const maxNodes = graphExplorerMode === 'all' ? 300 : 160;
    const query = graphExplorerQuery.trim().toLowerCase();
    const entityById = new Map(visualEntities.map((entity) => [entity.id, entity]));
    const entityIdByName = new Map(visualEntities.map((entity) => [entity.name, entity.id]));
    const adjacency = new Map<string, Set<string>>();
    visualEntities.forEach((entity) => adjacency.set(entity.id, new Set()));
    visualEntities.forEach((entity) => {
      (entity.relations || []).forEach((relation) => {
        const targetId = relation.target_entity_id || entityIdByName.get(relation.target_type);
        if (!targetId || !entityById.has(targetId)) return;
        adjacency.get(entity.id)?.add(targetId);
        adjacency.get(targetId)?.add(entity.id);
      });
    });

    let selectedIds: string[] = [];
    if (graphExplorerMode === 'focus') {
      const startId = activeVisualEntity?.id || visualEntities[0]?.id;
      if (startId) {
        const visited = new Set<string>([startId]);
        const queue: Array<{ id: string; depth: number }> = [{ id: startId, depth: 0 }];
        while (queue.length && visited.size < maxNodes) {
          const current = queue.shift();
          if (!current || current.depth >= 2) continue;
          Array.from(adjacency.get(current.id) || []).forEach((nextId) => {
            if (visited.has(nextId) || visited.size >= maxNodes) return;
            visited.add(nextId);
            queue.push({ id: nextId, depth: current.depth + 1 });
          });
        }
        selectedIds = Array.from(visited);
      }
    } else if (graphExplorerMode === 'search' && query) {
      const matched = visualEntities.filter((entity) => {
        const haystack = [
          entity.name,
          ...entity.attributes.map((attr) => attr.name),
          ...(entity.relations || []).map((relation) => relation.name),
        ].join(' ').toLowerCase();
        return haystack.includes(query);
      });
      const selected = new Set<string>();
      matched.forEach((entity) => {
        if (selected.size >= maxNodes) return;
        selected.add(entity.id);
        Array.from(adjacency.get(entity.id) || []).forEach((neighborId) => {
          if (selected.size < maxNodes) selected.add(neighborId);
        });
      });
      selectedIds = Array.from(selected);
    } else {
      selectedIds = visualEntities.slice(0, maxNodes).map((entity) => entity.id);
    }

    const count = selectedIds.length || 1;
    const cols = Math.max(1, Math.ceil(Math.sqrt(count * 1.6)));
    const rows = Math.max(1, Math.ceil(count / cols));
    const cellW = width / (cols + 1);
    const cellH = height / (rows + 1);
    const nodes = selectedIds.map((id, index) => {
      const entity = entityById.get(id);
      const col = index % cols;
      const row = Math.floor(index / cols);
      return {
        id,
        name: entity?.name || '未命名对象',
        x: (col + 1) * cellW,
        y: (row + 1) * cellH,
        attrCount: entity?.attributes.length || 0,
        relationCount: entity?.relations.length || 0,
      };
    });
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const edges = visualEntities.flatMap((entity) =>
      (entity.relations || [])
        .map((relation) => {
          const targetId = relation.target_entity_id || entityIdByName.get(relation.target_type);
          const source = nodeById.get(entity.id);
          const target = targetId ? nodeById.get(targetId) : undefined;
          if (!source || !target) return null;
          return { id: relation.id, name: relation.name || '未命名关系', source, target };
        })
        .filter((edge): edge is { id: string; name: string; source: typeof nodes[number]; target: typeof nodes[number] } => Boolean(edge)),
    ).slice(0, 700);

    return {
      width,
      height,
      nodes,
      edges,
      totalNodes: visualEntities.length,
      totalEdges: visualEntities.reduce((sum, entity) => sum + (entity.relations || []).length, 0),
      truncated: selectedIds.length < visualEntities.length,
      maxNodes,
    };
  }, [activeVisualEntity?.id, graphExplorerMode, graphExplorerQuery, visualEntities]);
  const graphFlowElements = useMemo(() => {
    const nodeWidth = 220;
    const nodeHeight = 86;
    const graph = new dagre.graphlib.Graph();
    graph.setDefaultEdgeLabel(() => ({}));
    graph.setGraph({ rankdir: 'LR', nodesep: 58, ranksep: 120, marginx: 40, marginy: 40 });

    graphExplorerData.nodes.forEach((node) => {
      graph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
    });
    graphExplorerData.edges.forEach((edge) => {
      graph.setEdge(edge.source.id, edge.target.id);
    });
    dagre.layout(graph);

    const nodes: Node[] = graphExplorerData.nodes.map((item) => {
      const layout = graph.node(item.id) || { x: item.x, y: item.y };
      const active = activeVisualEntity?.id === item.id;
      return {
        id: item.id,
        position: { x: layout.x - nodeWidth / 2, y: layout.y - nodeHeight / 2 },
        data: {
          label: (
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 800, color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.name}
              </div>
              <Space size={6} wrap>
                <Tag color="blue">{item.attrCount} 字段</Tag>
                <Tag>{item.relationCount} 关系</Tag>
              </Space>
            </div>
          ),
        },
        style: {
          width: nodeWidth,
          minHeight: nodeHeight,
          padding: 14,
          borderRadius: 12,
          border: active ? '2px solid #2563eb' : '1px solid #dbe3ef',
          background: active ? '#eff6ff' : '#ffffff',
          boxShadow: active ? '0 10px 28px rgba(37, 99, 235, 0.14)' : '0 8px 20px rgba(15, 23, 42, 0.06)',
        },
      };
    });

    const edges: Edge[] = graphExplorerData.edges.map((edge) => {
      const selected = selectedGraphEdgeId === edge.id;
      return {
        id: edge.id,
        source: edge.source.id,
        target: edge.target.id,
        label: edge.name,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, color: selected ? '#2563eb' : '#94a3b8' },
        style: { stroke: selected ? '#2563eb' : '#94a3b8', strokeWidth: selected ? 2.6 : 1.8 },
        labelStyle: { fill: selected ? '#1d4ed8' : '#475569', fontSize: 12, fontWeight: 600 },
        labelBgStyle: { fill: '#ffffff', fillOpacity: 0.94 },
        labelBgPadding: [6, 3],
        labelBgBorderRadius: 6,
      };
    });

    return { nodes, edges };
  }, [activeVisualEntity?.id, graphExplorerData, selectedGraphEdgeId]);
  const schemaValidationIssues = useMemo(() => {
    const issues: string[] = [];
    const names = visualEntities.map((entity) => entity.name.trim()).filter(Boolean);
    const duplicatedNames = names.filter((name, index) => names.indexOf(name) !== index);
    if (visualEntities.some((entity) => !entity.name.trim())) issues.push('存在未命名对象');
    if (duplicatedNames.length > 0) issues.push(`对象名称重复：${Array.from(new Set(duplicatedNames)).join('、')}`);
    visualEntities.forEach((entity) => {
      const attrNames = entity.attributes.map((attr) => attr.name.trim()).filter(Boolean);
      const duplicatedAttrs = attrNames.filter((name, index) => attrNames.indexOf(name) !== index);
      if (entity.attributes.some((attr) => !attr.name.trim())) issues.push(`${entity.name || '未命名对象'} 存在未命名字段`);
      if (duplicatedAttrs.length > 0) issues.push(`${entity.name || '未命名对象'} 字段重复：${Array.from(new Set(duplicatedAttrs)).join('、')}`);
      (entity.relations || []).forEach((relation) => {
        if (!relation.name.trim()) issues.push(`${entity.name || '未命名对象'} 存在未命名关系`);
        const targetExists = visualEntities.some((target) => target.id === relation.target_entity_id || target.name === relation.target_type);
        if (relation.name.trim() && !targetExists) issues.push(`${entity.name || '未命名对象'} 的关系 ${relation.name} 缺少有效目标对象`);
      });
    });
    return issues;
  }, [visualEntities]);
  const stepIndex = useMemo<GuidedStep>(() => {
    if (!selectedSpaceId) return 0;
    if (dataSources.length === 0 && sourceFields.length === 0) return 1;
    if (sourceFields.length > 0 && !hasSchema) return 2;
    if (!hasSchema) return 3;
    if (!hasMapping) return 4;
    if (!hasRule) return 5;
    if (!mappingResult || !hasDecision || !explainResult) return 6;
    if (!hasGaAll) return 7;
    return 7;
  }, [selectedSpaceId, dataSources.length, sourceFields.length, hasSchema, hasMapping, hasRule, hasGaAll, mappingResult, hasDecision, explainResult]);

  useEffect(() => {
    setGuidedStep(stepIndex);
  }, [stepIndex]);

  useEffect(() => {
    if (guidedStep === 3) setGuidedBuilderKind('schema');
    if (guidedStep === 4) setGuidedBuilderKind('mapping');
    if (guidedStep === 5) setGuidedBuilderKind('rule');
  }, [guidedStep]);

  useEffect(() => {
    if (!activeVisualEntityId && visualEntities.length > 0) {
      setActiveVisualEntityId(visualEntities[0].id);
      return;
    }
    if (activeVisualEntityId && !visualEntities.some((entity) => entity.id === activeVisualEntityId)) {
      setActiveVisualEntityId(visualEntities[0]?.id || null);
    }
  }, [activeVisualEntityId, visualEntities]);

  useEffect(() => {
    if (selectedGraphEdgeId && !visualEntities.some((entity) => (entity.relations || []).some((relation) => relation.id === selectedGraphEdgeId))) {
      setSelectedGraphEdgeId(null);
    }
  }, [selectedGraphEdgeId, visualEntities]);

  useEffect(() => {
    const entityNames = visualEntities.map((entity) => entity.name.trim()).filter(Boolean);
    if (entityNames.length === 0) return;
    if (!entityNames.includes(visualMappingEntityType.trim())) {
      setVisualMappingEntityType(entityNames[0]);
    }
    if (!entityNames.includes(visualRuleTargetEntityType.trim())) {
      setVisualRuleTargetEntityType(entityNames[0]);
    }
  }, [visualEntities, visualMappingEntityType, visualRuleTargetEntityType]);

  const fetchOrgs = useCallback(async () => {
    try {
      const res = await api.get<OrgItem[]>('/api/v1/ontology/orgs');
      setOrgs(res.data || []);
    } catch {
      setOrgs([]);
    }
  }, [api]);

  const fetchSpaces = useCallback(async () => {
    const res = await api.get<SpaceItem[]>('/api/v1/ontology/spaces');
    setSpaces(res.data || []);
    if (!selectedSpaceId && res.data.length > 0) setSelectedSpaceId(res.data[0].id);
  }, [api, selectedSpaceId]);

  const fetchPackages = useCallback(async () => {
    if (!selectedSpaceId) return;
    const res = await api.get<PackageItem[]>(`/api/v1/ontology/packages/${selectedSpaceId}/${kind}`);
    setPackages(res.data || []);
  }, [api, kind, selectedSpaceId]);

  const fetchSpacePackageSummary = useCallback(async () => {
    if (!selectedSpaceId) {
      setSpacePackageSummary({ schema: [], mapping: [], rule: [] });
      return;
    }
    const kinds: PackageKind[] = ['schema', 'mapping', 'rule'];
    const results = await Promise.all(
      kinds.map(async (targetKind) => {
        const res = await api.get<PackageItem[]>(`/api/v1/ontology/packages/${selectedSpaceId}/${targetKind}`);
        return [targetKind, res.data || []] as const;
      }),
    );
    setSpacePackageSummary({
      schema: results.find(([targetKind]) => targetKind === 'schema')?.[1] || [],
      mapping: results.find(([targetKind]) => targetKind === 'mapping')?.[1] || [],
      rule: results.find(([targetKind]) => targetKind === 'rule')?.[1] || [],
    });
  }, [api, selectedSpaceId]);

  const fetchEvents = useCallback(async () => {
    if (!selectedSpaceId) return;
    const res = await api.get<ReleaseEvent[]>(`/api/v1/ontology/governance/releases/${selectedSpaceId}`);
    setEvents(res.data || []);
  }, [api, selectedSpaceId]);

  const fetchApprovals = useCallback(async () => {
    if (!selectedSpaceId) return;
    const res = await api.get<ApprovalItem[]>(`/api/v1/ontology/governance/approvals/${selectedSpaceId}`);
    setApprovals(res.data || []);
  }, [api, selectedSpaceId]);

  const fetchDataSources = useCallback(async () => {
    if (!selectedSpaceId) {
      setDataSources([]);
      return;
    }
    const res = await api.get<OntologyDataSource[]>(`/api/v1/ontology/data-sources/${selectedSpaceId}`);
    setDataSources(res.data || []);
  }, [api, selectedSpaceId]);

  const fetchSecrets = useCallback(async () => {
    if (!selectedSpaceId) {
      setSecrets([]);
      return;
    }
    const res = await api.get<OntologySecretRecord[]>(`/api/v1/ontology/secrets/${selectedSpaceId}`);
    setSecrets(res.data || []);
  }, [api, selectedSpaceId]);

  useEffect(() => {
    void fetchOrgs();
    void fetchSpaces();
  }, [fetchOrgs, fetchSpaces]);

  useEffect(() => {
    void fetchPackages();
    void fetchEvents();
    void fetchApprovals();
    void fetchSpacePackageSummary();
    void fetchDataSources();
    void fetchSecrets();
  }, [fetchPackages, fetchEvents, fetchApprovals, fetchSpacePackageSummary, fetchDataSources, fetchSecrets]);

  useEffect(() => {
    const schemaPkg = pickRunnablePackage(spacePackageSummary.schema);
    if (!schemaPkg) {
      schemaHydrationKeyRef.current = '';
      const defaults = createDefaultVisualEntities();
      setVisualSchemaVersion('1.0.0');
      setVisualEntities(defaults);
      setActiveVisualEntityId(defaults[0]?.id || null);
      return;
    }
    const hydrationKey = `${schemaPkg.space_id}:${schemaPkg.version}:${schemaPkg.updated_at}`;
    if (schemaHydrationKeyRef.current === hydrationKey) return;
    schemaHydrationKeyRef.current = hydrationKey;
    setVisualSchemaVersion(schemaPkg.version);
    const nextEntities = visualEntitiesFromSchemaPayload(schemaPkg.payload || {});
    setVisualEntities(nextEntities);
    setActiveVisualEntityId(nextEntities[0]?.id || null);
  }, [spacePackageSummary.schema]);

  useEffect(() => {
    const parsed = JSON.parse(DEFAULT_PAYLOADS[kind]) as { version: string };
    setVersion(parsed.version);
    setPayloadText(DEFAULT_PAYLOADS[kind]);
  }, [kind]);

  const onCreateOrg = async () => {
    const code = newOrgCode.trim();
    const name = newOrgName.trim();
    if (!code || !name) {
      message.warning('请输入组织编码与名称');
      return;
    }
    setLoading(true);
    try {
      await api.post('/api/v1/ontology/orgs', { code, name });
      message.success('组织创建成功');
      setNewOrgCode('');
      setNewOrgName('');
      await fetchOrgs();
    } catch (error) {
      message.error(getRequestErrorMessage(error, '组织创建失败'));
    } finally {
      setLoading(false);
    }
  };

  const onCreateSpace = async (values: { name: string; code?: string; description?: string }) => {
    setLoading(true);
    try {
      const res = await api.post<SpaceItem>('/api/v1/ontology/spaces', { ...values, org_id: spaceOrgId || undefined });
      message.success('本体空间创建成功');
      await fetchSpaces();
      setSelectedSpaceId(res.data.id);
      setSpaceOrgId(undefined);
    } catch (error) {
      message.error(getRequestErrorMessage(error, '创建空间失败'));
    } finally {
      setLoading(false);
    }
  };

  const onSavePackage = async () => {
    if (!selectedSpaceId) return message.warning('请先选择本体空间');
    let obj: Record<string, unknown>;
    try {
      obj = JSON.parse(payloadText) as Record<string, unknown>;
    } catch {
      return message.error('JSON 格式错误，请检查 payload');
    }
    obj.space_id = selectedSpaceId;
    obj.version = version;
    setLoading(true);
    try {
      const endpoint = kind === 'rule' ? '/api/v1/ontology/rules' : `/api/v1/ontology/${kind}`;
      await api.post(endpoint, obj);
      message.success(`${kind} 包保存成功`);
      await fetchPackages();
      await fetchSpacePackageSummary();
    } catch (error) {
      message.error(getRequestErrorMessage(error, '保存失败'));
    } finally {
      setLoading(false);
    }
  };

  const savePackageObject = async (targetKind: PackageKind, targetVersion: string, obj: Record<string, unknown>) => {
    if (!selectedSpaceId) return message.warning('请先选择本体空间');
    const payload = { ...obj, space_id: selectedSpaceId, version: targetVersion };
    setLoading(true);
    try {
      const endpoint = targetKind === 'rule' ? '/api/v1/ontology/rules' : `/api/v1/ontology/${targetKind}`;
      await api.post(endpoint, payload);
      await fetchPackages();
      await fetchSpacePackageSummary();
      setKind(targetKind);
      setVersion(targetVersion);
      setPayloadText(pretty(payload));
      if (targetKind === 'schema') {
        setMappingResult('');
        setRuleGraphInput(pretty({ entities: [], relations: [], metadata: { reason: 'schema changed' } }));
        setRuleResult('');
        setExplainResult('');
        setLatestDecisionId('');
      } else if (targetKind === 'mapping') {
        setMappingResult('');
        setRuleGraphInput(pretty({ entities: [], relations: [], metadata: { reason: 'mapping changed' } }));
        setRuleResult('');
        setExplainResult('');
        setLatestDecisionId('');
      } else if (targetKind === 'rule') {
        setRuleResult('');
        setExplainResult('');
        setLatestDecisionId('');
      }
      message.success(`${targetKind} 可视化配置已保存`);
    } catch (error) {
      message.error(getRequestErrorMessage(error, `${targetKind} 保存失败`));
    } finally {
      setLoading(false);
    }
  };

  const saveVisualSchema = async () => {
    if (schemaValidationIssues.length > 0) {
      message.warning(schemaValidationIssues[0]);
      return;
    }
    const entity_types = visualEntities
      .filter((entity) => entity.name.trim())
      .map((entity) => ({
        name: entity.name.trim(),
        attributes: Object.fromEntries(
          entity.attributes
            .filter((attr) => attr.name.trim())
            .map((attr) => [attr.name.trim(), { data_type: attr.data_type, required: attr.required }]),
        ),
        relations: entity.relations
          .filter((relation) => relation.name.trim() && relation.target_type.trim())
          .map((relation) => {
            const target = visualEntities.find((item) => item.id === relation.target_entity_id) || visualEntities.find((item) => item.name === relation.target_type);
            return {
              name: relation.name.trim(),
              target_type: (target?.name || relation.target_type).trim(),
              cardinality: relation.cardinality,
            };
          }),
      }));
    if (entity_types.length === 0) {
      message.warning('至少配置一个实体');
      return;
    }
    await savePackageObject('schema', visualSchemaVersion, {
      description: 'visual schema',
      entity_types,
      taxonomy: {},
      vocabulary: {},
    });
  };

  const saveVisualMapping = async () => {
    if (!visualMappingEntityType.trim() || !visualMappingIdTemplate.trim()) {
      message.warning('请填写实体类型与ID模板');
      return;
    }
    const field_mappings = visualMappingFields
      .filter((field) => field.source_path.trim() && field.target_attr.trim())
      .map((field) => ({
        source_path: field.source_path.trim(),
        target_attr: field.target_attr.trim(),
        required: field.required,
        transform: field.transform || undefined,
      }));
    await savePackageObject('mapping', visualMappingVersion, {
      description: 'visual mapping',
      entity_mappings: [
        {
          entity_type: visualMappingEntityType.trim(),
          source_path: visualMappingSourcePath.trim() || undefined,
          id_template: visualMappingIdTemplate.trim(),
          field_mappings,
        },
      ],
      relation_mappings: [],
    });
  };

  const saveVisualRule = async () => {
    if (!visualRuleId.trim() || !visualRuleName.trim()) {
      message.warning('请填写规则ID与规则名称');
      return;
    }
    const conditions = visualRuleConditions
      .filter((condition) => condition.path.trim())
      .map((condition) => ({
        path: condition.path.trim(),
        operator: condition.operator,
        value: condition.operator === 'exists' ? undefined : condition.value,
      }));
    await savePackageObject('rule', visualRuleVersion, {
      description: 'visual rule',
      rules: [
        {
          rule_id: visualRuleId.trim(),
          name: visualRuleName.trim(),
          target_entity_type: visualRuleTargetEntityType.trim() || undefined,
          severity: visualRuleSeverity,
          action: visualRuleAction,
          conditions,
          tags: [],
        },
      ],
    });
  };

  const analyzeSourceSample = useCallback(() => {
    let fields: SourceField[] = [];
    let entityName = 'Entity';
    try {
      if (sourceInputKind === 'json') {
        const parsed = JSON.parse(sourceSampleText) as unknown;
        fields = collectSourceFields(parsed);
        entityName = rootEntityNameFromSample(parsed);
      } else {
        const parsed = parseTableSample(sourceSampleText);
        fields = parsed.fields;
        entityName = 'Record';
      }
    } catch (error) {
      message.error(sourceInputKind === 'json' ? '样本 JSON 格式不正确，先检查逗号、引号和括号' : getRequestErrorMessage(error, '表格样本解析失败，请检查表头和分隔符'));
      return;
    }
    if (fields.length === 0) {
      message.warning(sourceInputKind === 'json' ? '没有识别到可用字段，请提供对象或对象数组样本' : '没有识别到可用列，请提供表头和至少一行数据');
      return;
    }
    setSourceFields(normalizeSourceFields(fields));
    setSourceEntityName(entityName);
    message.success(`已识别 ${fields.length} 个字段，可一键生成结构和映射`);
  }, [sourceInputKind, sourceSampleText]);

  const applySourceSuggestion = useCallback(() => {
    const selectedFields = sourceFields.filter((field) => !field.ignored);
    if (selectedFields.length === 0) {
      analyzeSourceSample();
      return;
    }
    const entityId = uid();
    const attributes: VisualAttribute[] = selectedFields.map((field) => ({
      id: uid(),
      name: field.name,
      data_type: field.data_type,
      required: field.required,
    }));
    const normalizedEntityName = sourceEntityName.trim() || 'Entity';
    setVisualEntities([{ id: entityId, name: normalizedEntityName, attributes, relations: [] }]);
    setActiveVisualEntityId(entityId);
    setVisualMappingEntityType(normalizedEntityName);
    setVisualMappingSourcePath('');
    const idField = selectedFields.find((field) => ['id', 'code', 'no', 'number'].some((hint) => field.name.toLowerCase().includes(hint)));
    setVisualMappingIdTemplate(`${normalizedEntityName.toLowerCase()}:{{row.${idField?.path || selectedFields[0].path}}}`);
    setVisualMappingFields(
      selectedFields.map((field) => ({
        id: uid(),
        source_path: field.path,
        target_attr: field.name,
        transform: field.data_type === 'string' ? 'trim' : '',
        required: field.required,
      })),
    );
    if (sourceInputKind === 'table') {
      try {
        const { rows } = parseTableSample(sourceSampleText);
        setMappingInput(pretty(rows[0] || {}));
      } catch {
        setMappingInput('{}');
      }
    } else {
      setMappingInput(sourceSampleText);
    }
    setGuidedBuilderKind('schema');
    setGuidedStep(3);
    message.success('已生成本体结构和默认映射，请检查后保存');
  }, [analyzeSourceSample, sourceEntityName, sourceFields, sourceInputKind, sourceSampleText]);

  const onImportSourceSample = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (/\.xlsx?$/i.test(file.name)) {
      message.warning('暂不直接读取 Excel，请先另存为 CSV 后导入；后续会接正式 Excel 解析器');
      return;
    }
    const text = await file.text();
    setSourceSampleText(text);
    setSourceInputKind(/\.csv$|\.tsv$|\.txt$/i.test(file.name) ? 'table' : 'json');
    setSourceFields([]);
    message.success('样本已导入，请点击解析样本');
  }, []);

  const onDataSourceKindChange = (nextKind: DataSourceKind) => {
    setDataSourceKind(nextKind);
    if (nextKind === 'database') {
      setDataSourceName('业务数据库');
      setDataSourceProtocol('postgresql');
      setDataSourceConfigText(pretty({ host: '127.0.0.1', port: 5432, database: 'app', schema: 'public' }));
    } else if (nextKind === 'api') {
      setDataSourceName('业务 API');
      setDataSourceProtocol('rest');
      setDataSourceConfigText(pretty({ base_url: 'https://api.example.com', auth: 'secret_ref', sample_path: '/contracts/{id}' }));
    } else {
      setDataSourceName('协议连接器');
      setDataSourceProtocol('mcp');
      setDataSourceConfigText(pretty({ endpoint: 'connector-name', capability: 'query' }));
    }
  };

  const onSaveDataSource = async () => {
    if (!selectedSpaceId) return message.warning('请先选择本体空间');
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(dataSourceConfigText) as Record<string, unknown>;
    } catch {
      return message.error('连接配置必须是合法 JSON');
    }
    setLoading(true);
    try {
      await api.post('/api/v1/ontology/data-sources', {
        space_id: selectedSpaceId,
        name: dataSourceName.trim(),
        kind: dataSourceKind,
        protocol: dataSourceProtocol.trim(),
        config,
        secret_ref: dataSourceSecretRef.trim() || undefined,
        status: 'draft',
      });
      message.success('数据源已保存');
      await fetchDataSources();
    } catch (error) {
      message.error(getRequestErrorMessage(error, '数据源保存失败'));
    } finally {
      setLoading(false);
    }
  };

  const onTestDataSource = async (source: OntologyDataSource) => {
    setLoading(true);
    try {
      const res = await api.post(`/api/v1/ontology/data-sources/${source.id}/test`);
      message.success(res.data?.message || '数据源配置检查通过');
      await fetchDataSources();
    } catch (error) {
      message.error(getRequestErrorMessage(error, '数据源测试失败'));
    } finally {
      setLoading(false);
    }
  };

  const onSaveSecret = async () => {
    if (!selectedSpaceId) return message.warning('请先选择本体空间');
    if (!secretScope.trim() || !secretName.trim() || !secretValue) return message.warning('请填写 scope、name 和密钥值');
    setLoading(true);
    try {
      const res = await api.post<OntologySecretRecord>('/api/v1/ontology/secrets', {
        space_id: selectedSpaceId,
        scope: secretScope.trim(),
        name: secretName.trim(),
        value: secretValue,
        description: secretDescription.trim() || undefined,
      });
      setDataSourceSecretRef(res.data.ref);
      setSecretValue('');
      message.success(`密钥已保存：${res.data.ref}`);
      await fetchSecrets();
    } catch (error) {
      message.error(getRequestErrorMessage(error, '密钥保存失败'));
    } finally {
      setLoading(false);
    }
  };

  const onDiscoverDataSource = async (source: OntologyDataSource) => {
    setLoading(true);
    try {
      const res = await api.post<DataSourceDiscoveryResult>(`/api/v1/ontology/data-sources/${source.id}/discover`);
      const discovered = res.data;
      if (!discovered.entities?.length) {
        message.warning(discovered.message || '没有发现可用结构');
        return;
      }
      const first = discovered.entities[0];
      const fields = normalizeSourceFields(
        (first.columns || []).map((column) => ({
          path: column.source_path || `${first.source}.${column.name}`,
          name: column.name,
          data_type: coerceVisualDataType(column.data_type),
          required: Boolean(column.primary_key || !column.nullable),
          sample: column.description || '',
          source: first.source,
          ignored: false,
        })),
      );
      setSourceFields(fields);
      setSourceEntityName(first.name || 'Entity');
      setDataSourceEntryMode('sample');
      setGuidedStep(2);
      const extra = discovered.entities.length > 1 ? `，已先载入 ${first.name}，其余 ${discovered.entities.length - 1} 个对象后续可继续导入` : '';
      message.success(`${discovered.message}${extra}`);
      if (discovered.warnings?.length) {
        Modal.warning({
          title: '结构发现提示',
          content: (
            <ul style={{ marginBottom: 0 }}>
              {discovered.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ),
        });
      }
    } catch (error) {
      message.error(getRequestErrorMessage(error, '结构发现失败'));
    } finally {
      setLoading(false);
    }
  };

  const createVisualEntity = useCallback(() => {
    const nextEntity: VisualEntity = {
      id: uid(),
      name: `Entity${visualEntities.length + 1}`,
      attributes: [{ id: uid(), name: 'id', data_type: 'string', required: true }],
      relations: [],
    };
    setVisualEntities((prev) => [...prev, nextEntity]);
    setActiveVisualEntityId(nextEntity.id);
    setSelectedGraphEdgeId(null);
    setGraphExplorerMode('focus');
  }, [visualEntities.length]);

  const onGraphConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target) return;
    if (connection.source === connection.target) {
      message.warning('同一个对象不需要通过连线表达自身关系');
      return;
    }
    const relationId = uid();
    setVisualEntities((prev) => {
      const target = prev.find((entity) => entity.id === connection.target);
      const source = prev.find((entity) => entity.id === connection.source);
      if (!target || !source) return prev;
      const relationName = `relates_to_${target.name || 'target'}`.replace(/\s+/g, '_');
      return prev.map((entity) =>
        entity.id !== source.id
          ? entity
          : {
              ...entity,
              relations: [
                ...(entity.relations || []),
                {
                  id: relationId,
                  name: relationName,
                  target_entity_id: target.id,
                  target_type: target.name || 'Entity',
                  cardinality: 'many',
                },
              ],
            },
      );
    });
    setActiveVisualEntityId(connection.source);
    setSelectedGraphEdgeId(relationId);
    setGraphExplorerMode('focus');
    message.success('关系已创建，可在右侧面板调整名称和数量');
  }, []);

  const getGaCompatibilityReport = async (pkg: PackageItem): Promise<DiffResponse | null> => {
    const active = packages.find((p) => p.kind === pkg.kind && p.stage === 'ga' && p.version !== pkg.version);
    if (!active) return null;
    const res = await api.get<DiffResponse>('/api/v1/ontology/governance/diff', {
      params: {
        space_id: pkg.space_id,
        kind: pkg.kind,
        from_version: active.version,
        to_version: pkg.version,
      },
    });
    return res.data;
  };

  const onRelease = async (pkg: PackageItem, targetStage: Stage) => {
    let report: DiffResponse | null = null;
    if (targetStage === 'ga') {
      try {
        report = await getGaCompatibilityReport(pkg);
      } catch {
        report = null;
      }
    }
    Modal.confirm({
      title: `确认将 ${pkg.kind}:${pkg.version} 变更到 ${targetStage} 吗？`,
      content: (
        <Space direction="vertical" style={{ width: '100%' }} size={8}>
          <Text>
            {strictCompatibility
              ? '当前启用严格兼容模式：出现兼容性告警会直接阻断发布。'
              : '当前为告警模式：兼容性问题会提示但允许继续发布。'}
          </Text>
          {report && (
            <>
              <Alert
                showIcon
                type={(report.breaking_changes || []).length > 0 ? 'warning' : 'info'}
                message={(report.breaking_changes || []).length > 0 ? '检测到潜在破坏性变更' : '未检测到破坏性变更'}
                description={`比较版本: ${report.from_version} -> ${report.to_version}`}
              />
              <TextArea
                readOnly
                value={pretty({ breaking_changes: report.breaking_changes, summary: report.summary })}
                autoSize={{ minRows: 4, maxRows: 8 }}
                style={{ fontFamily: 'monospace' }}
              />
            </>
          )}
        </Space>
      ),
      okText: '确认执行',
      cancelText: '取消',
      onOk: async () => {
        if (strictCompatibility && report && (report.breaking_changes || []).length > 0) {
          message.error('严格模式下检测到破坏性变更，已阻断发布');
          return;
        }
        setLoading(true);
        try {
          const res = await api.post('/api/v1/ontology/governance/release', {
            space_id: pkg.space_id,
            kind: pkg.kind,
            version: pkg.version,
            target_stage: targetStage,
            strict_compatibility: strictCompatibility,
          });
          const warnings = (res.data?.warnings || []) as string[];
          if (warnings.length > 0) {
            Modal.warning({
              title: '兼容性告警',
              content: (
                <ul style={{ marginBottom: 0 }}>
                  {warnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ),
            });
          }
          message.success('发布状态更新成功');
          await fetchPackages();
          await fetchSpacePackageSummary();
          await fetchEvents();
          await fetchApprovals();
        } catch (error: unknown) {
          const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
          if (detail && typeof detail === 'object' && 'warnings' in detail) {
            const warnings = (detail as { warnings?: string[] }).warnings || [];
            Modal.error({
              title: '发布被阻断',
              content: (
                <ul style={{ marginBottom: 0 }}>
                  {warnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ),
            });
          } else {
            message.error('发布失败');
          }
        } finally {
          setLoading(false);
        }
      },
    });
  };

  const onRollback = async (pkg: PackageItem) => {
    Modal.confirm({
      title: `确认回滚 ${pkg.kind} 到版本 ${pkg.version} 吗？`,
      content: '回滚会把该版本重新设为 GA，并将当前 GA 标记为 deprecated。',
      okText: '确认回滚',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setLoading(true);
        try {
          await api.post('/api/v1/ontology/governance/rollback', {
            space_id: pkg.space_id,
            kind: pkg.kind,
            target_version: pkg.version,
            notes: 'rollback from console',
          });
          message.success('回滚成功');
          await fetchPackages();
          await fetchSpacePackageSummary();
          await fetchEvents();
          await fetchApprovals();
        } catch (error) {
          message.error(getRequestErrorMessage(error, '回滚失败'));
        } finally {
          setLoading(false);
        }
      },
    });
  };

  const onSubmitApproval = async () => {
    if (!selectedSpaceId || !approvalTargetVersion) return message.warning('请先选择版本并填写审批目标');
    const targetPkg = packages.find((item) => item.version === approvalTargetVersion && item.kind === kind);
    if (!targetPkg) return message.warning('未找到对应版本，请先刷新版本列表');
    const allowedTargets = getAllowedReleaseTargets(targetPkg.stage);
    if (!allowedTargets.includes(approvalTargetStage)) {
      message.warning(`当前版本处于 ${targetPkg.stage}，仅可申请 ${allowedTargets.join(' / ') || '无可用审批目标'}`);
      return;
    }
    setLoading(true);
    try {
      await api.post('/api/v1/ontology/governance/approvals/submit', {
        space_id: selectedSpaceId,
        kind,
        version: approvalTargetVersion,
        target_stage: approvalTargetStage,
      });
      message.success('审批申请已提交');
      await fetchApprovals();
    } catch (error) {
      message.error(getRequestErrorMessage(error, '审批申请提交失败'));
    } finally {
      setLoading(false);
    }
  };

  const onReviewApproval = async (approvalId: string, approve: boolean) => {
    Modal.confirm({
      title: approve ? '确认批准该审批申请？' : '确认拒绝该审批申请？',
      onOk: async () => {
        setLoading(true);
        try {
          await api.post('/api/v1/ontology/governance/approvals/review', { approval_id: approvalId, approve });
          message.success(approve ? '已批准' : '已拒绝');
          await fetchApprovals();
        } catch (error) {
          message.error(getRequestErrorMessage(error, '审批处理失败'));
        } finally {
          setLoading(false);
        }
      },
    });
  };

  const onDiffPackages = async () => {
    if (!selectedSpaceId || !diffFromVersion || !diffToVersion) return message.warning('请填写对比版本');
    setLoading(true);
    try {
      const res = await api.get<DiffResponse>('/api/v1/ontology/governance/diff', {
        params: {
          space_id: selectedSpaceId,
          kind,
          from_version: diffFromVersion,
          to_version: diffToVersion,
        },
      });
      setDiffObj(res.data);
      setDiffResult(pretty(res.data));
      message.success('版本对比完成');
    } catch (error) {
      message.error(getRequestErrorMessage(error, '版本对比失败'));
    } finally {
      setLoading(false);
    }
  };

  const onExportPayload = () => {
    const blob = new Blob([payloadText], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ontology-${kind}-${version}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const onTriggerImport = () => fileInputRef.current?.click();

  const onImportPayload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    try {
      JSON.parse(text);
      setPayloadText(text);
      message.success('JSON 导入成功');
    } catch {
      message.error('导入失败：文件不是合法 JSON');
    } finally {
      event.target.value = '';
    }
  };

  const onGenerateSampleInput = () => {
    const row: Record<string, unknown> = {};
    visualMappingFields.forEach((field) => {
      const sourceKey = field.source_path.trim().split('.').filter(Boolean).pop();
      if (!sourceKey) return;
      if (field.transform === 'to_int') row[sourceKey] = 100;
      else if (field.transform === 'to_float') row[sourceKey] = 100.5;
      else if (field.transform === 'to_bool') row[sourceKey] = true;
      else row[sourceKey] = field.required ? `${sourceKey}-sample` : `sample ${sourceKey}`;
    });
    const sourceRoot = visualMappingSourcePath.trim() || 'item';
    setMappingInput(pretty({ [sourceRoot]: row }));
    setMappingResult('');
    setRuleResult('');
    setExplainResult('');
    setLatestDecisionId('');
    message.success('已根据映射配置生成样本');
  };

  const onRunMapping = async () => {
    if (!selectedSpaceId) return;
    const mappingPkg = runnableMappingPackage;
    if (!mappingPkg) {
      message.warning('请先保存数据映射，再执行映射测试');
      return;
    }
    const schemaPkg = runnableSchemaPackage;
    let inputPayload: Record<string, unknown>;
    try {
      inputPayload = JSON.parse(mappingInput) as Record<string, unknown>;
    } catch {
      return message.error('映射输入 JSON 无效');
    }
    setLoading(true);
    try {
      const res = await api.post('/api/v1/ontology/mapping/execute', {
        space_id: selectedSpaceId,
        input_payload: inputPayload,
        mapping_version: mappingPkg.version,
        schema_version: schemaPkg?.version,
      });
      setMappingResult(pretty(res.data));
      if (res.data?.graph) {
        setRuleGraphInput(pretty(res.data.graph));
      }
      message.success('映射执行成功');
    } catch (error) {
      message.error(getRequestErrorMessage(error, '映射执行失败'));
    } finally {
      setLoading(false);
    }
  };

  const onRunRules = async () => {
    if (!selectedSpaceId) return;
    const rulePkg = runnableRulePackage;
    if (!rulePkg) {
      message.warning('请先保存业务规则，再执行规则测试');
      return;
    }
    let graph: Record<string, unknown>;
    try {
      graph = JSON.parse(ruleGraphInput) as Record<string, unknown>;
    } catch {
      return message.error('图输入 JSON 无效');
    }
    setLoading(true);
    try {
      const res = await api.post('/api/v1/ontology/rules/evaluate', {
        space_id: selectedSpaceId,
        graph,
        rule_version: rulePkg.version,
      });
      setRuleResult(pretty(res.data));
      if (res.data?.decision_id) setLatestDecisionId(String(res.data.decision_id));
      message.success('规则执行成功');
    } catch (error) {
      message.error(getRequestErrorMessage(error, '规则执行失败'));
    } finally {
      setLoading(false);
    }
  };

  const onExplain = async () => {
    if (!latestDecisionId) return message.warning('请先执行规则生成 decision_id');
    setLoading(true);
    try {
      const res = await api.get(`/api/v1/ontology/explain/${latestDecisionId}`);
      setExplainResult(pretty(res.data));
      message.success('解释查询成功');
    } catch (error) {
      message.error(getRequestErrorMessage(error, '解释查询失败'));
    } finally {
      setLoading(false);
    }
  };

  const workflowItems = [
    { title: '空间', description: selectedSpaceId ? '已连接' : '创建或选择空间', ready: !!selectedSpaceId, icon: Boxes },
    {
      title: '数据来源',
      description: dataSources.length > 0 ? `${dataSources.length} 个连接器` : sourceFields.length > 0 ? `${sourceFields.length} 个样本字段` : '接入数据库/API/协议',
      ready: dataSources.length > 0 || sourceFields.length > 0,
      icon: Database,
    },
    { title: '自动建模', description: sourceFields.length > 0 ? `${sourceFields.length} 个字段待确认` : '从样本生成草稿', ready: sourceFields.length > 0 || hasSchema, icon: GitBranch },
    { title: '数据结构', description: hasSchema ? '已保存' : '定义对象和字段', ready: hasSchema, icon: Database },
    { title: '数据映射', description: hasMapping ? '已保存' : '连接输入和字段', ready: hasMapping, icon: GitBranch },
    { title: '业务规则', description: hasRule ? '已保存' : '配置命中条件', ready: hasRule, icon: ShieldCheck },
    { title: '测试验证', description: mappingResult && hasDecision && explainResult ? '已跑通' : '跑样本看结果', ready: !!(mappingResult && hasDecision && explainResult), icon: FlaskConical },
    { title: '发布上线', description: hasGaAll ? '已上线' : '推进到 GA', ready: hasGaAll, icon: Rocket },
  ];
  const activeWorkflowItem = workflowItems[guidedStep];
  const getPreviousGuidedStep = useCallback(
    (current: GuidedStep): GuidedStep => {
      if (current === 0) return 0;
      if (current === 3 && sourceFields.length === 0) return 1;
      return Math.max(0, current - 1) as GuidedStep;
    },
    [sourceFields.length],
  );
  const getNextGuidedStep = useCallback(
    (current: GuidedStep): GuidedStep => {
      const lastStep = workflowItems.length - 1;
      if (current >= lastStep) return lastStep as GuidedStep;
      if (current === 1 && sourceFields.length === 0) return 3;
      if (current === 2 && sourceFields.length === 0) return 3;
      return Math.min(lastStep, current + 1) as GuidedStep;
    },
    [sourceFields.length, workflowItems.length],
  );

  return (
    <div style={pageStyle}>
      <div style={shellStyle}>
        <div style={toolbarStyle}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#111827', lineHeight: 1.2 }}>本体控制台</div>
              <Tag color="blue" style={{ margin: 0 }}>Ontology</Tag>
              <Tag color={selectedSpace ? 'cyan' : 'default'} style={{ margin: 0 }}>
                {selectedSpace ? selectedSpace.name : '未选择空间'}
              </Tag>
            </div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {viewMode === 'guided' ? '按数据来源、结构、映射、规则、验证、发布完成配置' : viewMode === 'graph' ? '满屏查看和操作本体图' : '版本治理、审批和审计'}
            </Text>
          </div>
          <Space wrap size={8}>
            <Segmented
              value={viewMode}
              onChange={(v) => setViewMode(v as WorkbenchViewMode)}
              options={[
                { label: '引导模式', value: 'guided' },
                { label: '图谱视图', value: 'graph' },
                { label: '专业模式', value: 'pro' },
              ]}
            />
          </Space>
        </div>

        {viewMode === 'guided' && (
          <div style={{ ...surfaceStyle, display: 'grid', gridTemplateColumns: '260px minmax(0, 1fr)', overflow: 'hidden' }}>
            <div style={{ borderRight: '1px solid #e5e7eb', background: '#ffffff', padding: 18 }}>
              <div style={{ padding: '4px 6px 14px' }}>
                <div style={{ color: '#111827', fontWeight: 800 }}>配置流程</div>
                <div style={{ marginTop: 4, ...mutedTextStyle, fontSize: 12 }}>保存后可回到任一步调整。</div>
              </div>
              <Space direction="vertical" style={{ width: '100%' }} size={8}>
                {workflowItems.map((item, index) => {
                  const Icon = item.icon;
                  const active = guidedStep === index;
                  return (
                    <button
                      key={item.title}
                      type="button"
                      onClick={() => {
                        if (index > 0 && !selectedSpaceId) {
                          message.warning('请先创建或选择一个本体空间');
                          setGuidedStep(0);
                          return;
                        }
                        setGuidedStep(index as GuidedStep);
                      }}
                      style={{
                        width: '100%',
                        border: active ? '1px solid #93c5fd' : '1px solid #f1f5f9',
                        background: active ? '#eff6ff' : '#ffffff',
                        borderRadius: 10,
                        padding: '11px 12px',
                        cursor: 'pointer',
                        textAlign: 'left',
                        boxShadow: active ? '0 6px 14px rgba(37, 99, 235, 0.08)' : 'none',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <Icon size={18} color={active ? '#2563eb' : '#64748b'} />
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                            <span style={{ color: '#0f172a', fontWeight: 700 }}>{item.title}</span>
                            {item.ready ? <CheckCircle2 size={16} color="#16a34a" /> : <Circle size={14} color="#cbd5e1" />}
                          </div>
                          <div style={{ ...mutedTextStyle, fontSize: 12 }}>{item.description}</div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </Space>
            </div>

            <div style={{ minWidth: 0, padding: 20, background: '#f8fafc' }}>
              <div style={stepHeaderStyle}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                  <div>
                    <Space size={8} wrap>
                      <Tag color="blue" style={{ margin: 0 }}>{`步骤 ${guidedStep + 1} / ${workflowItems.length}`}</Tag>
                      <Text style={{ ...mutedTextStyle, fontSize: 12 }}>{activeWorkflowItem.description}</Text>
                    </Space>
                    <div style={{ marginTop: 6, fontSize: 24, fontWeight: 800, color: '#111827', lineHeight: 1.25 }}>{activeWorkflowItem.title}</div>
                  </div>
                  <Space wrap>
                    <Button disabled={guidedStep === 0} onClick={() => setGuidedStep((prev) => getPreviousGuidedStep(prev))}>
                      上一步
                    </Button>
                    <Button
                      type="primary"
                      disabled={guidedStep >= workflowItems.length - 1 || (guidedStep === 0 && !selectedSpaceId)}
                      onClick={() => setGuidedStep((prev) => getNextGuidedStep(prev))}
                    >
                      下一步
                    </Button>
                  </Space>
                </div>
              </div>

              {guidedStep === 0 && (
                <Space direction="vertical" style={{ width: '100%' }} size={18}>
                  <Row gutter={[16, 16]} align="bottom">
                    <Col xs={24} lg={12}>
                      <label style={fieldLabelStyle}>选择已有空间</label>
                      <Select
                        style={{ width: '100%' }}
                        value={selectedSpaceId ?? undefined}
                        placeholder="请选择本体空间"
                        onChange={(v) => setSelectedSpaceId(v)}
                        options={visibleSpaces.map((s) => ({ label: `${s.name} (${s.code})`, value: s.id }))}
                        size="large"
                      />
                    </Col>
                    <Col xs={24} md={12} lg={6}>
                      <label style={fieldLabelStyle}>所有者</label>
                      <Input readOnly size="large" value={selectedSpace ? selectedSpace.owner_user_id : '未选择'} />
                    </Col>
                    <Col xs={24} md={12} lg={6}>
                      <label style={fieldLabelStyle}>组织范围</label>
                      <Select
                        style={{ width: '100%' }}
                        value={selectedOrgFilter}
                        onChange={setSelectedOrgFilter}
                        options={[
                          { value: 'all', label: '全部组织' },
                          { value: '__none__', label: '仅个人空间' },
                          ...orgs.map((o) => ({ value: o.id, label: `${o.name} (${o.code})` })),
                        ]}
                        size="large"
                      />
                    </Col>
                  </Row>
                  <Form layout="vertical" onFinish={onCreateSpace}>
                    <Row gutter={[12, 4]}>
                      <Col xs={24} md={10}>
                        <Form.Item label="新空间名称" name="name" rules={[{ required: true, message: '请输入空间名称' }]}>
                          <Input placeholder="例如 风险治理空间" size="large" />
                        </Form.Item>
                      </Col>
                      <Col xs={24} md={6}>
                        <Form.Item label="空间代码" name="code">
                          <Input placeholder="可选，例如 risk-prod" size="large" />
                        </Form.Item>
                      </Col>
                      <Col xs={24} md={8}>
                        <Form.Item label="描述" name="description">
                          <Input placeholder="可选，用来区分用途" size="large" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Button htmlType="submit" type="primary" loading={loading} size="large">
                          创建空间
                        </Button>
                        {selectedSpaceId && (
                          <Button style={{ marginLeft: 8 }} size="large" onClick={() => setGuidedStep(1)}>
                            继续接入数据
                          </Button>
                        )}
                      </Col>
                    </Row>
                  </Form>
                </Space>
              )}

              {selectedSpaceId && guidedStep === 1 && (
                <Card
                  size="small"
                  style={contentCardStyle}
                  title={<span style={{ fontSize: 18, fontWeight: 700 }}>数据来源</span>}
                  extra={<Text style={mutedTextStyle}>先注册真实数据入口，再生成本体结构。</Text>}
                >
                  <Space direction="vertical" style={{ width: '100%' }} size={16}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                      <Space wrap>
                        <Tag color={dataSources.length > 0 ? 'green' : 'default'}>{dataSources.length} 个连接器</Tag>
                        <Tag color={sourceFields.length > 0 ? 'blue' : 'default'}>{sourceFields.length} 个样本字段</Tag>
                      </Space>
                      <Segmented
                        value={dataSourceEntryMode}
                        onChange={(value) => setDataSourceEntryMode(value as DataSourceEntryMode)}
                        options={[
                          { label: '连接器', value: 'connector' },
                          { label: '样本导入', value: 'sample' },
                        ]}
                      />
                    </div>

                    {dataSourceEntryMode === 'connector' && (
                      <>
                        <Alert
                          type="info"
                          showIcon
                          message="注册数据库、API 或协议入口"
                          description="这里保存连接器元数据和安全 dry-run 配置检查，不要求把真实密码写进配置；敏感信息请使用密钥引用。"
                        />
                        <Row gutter={[12, 12]}>
                          <Col xs={24} xl={5}>
                            <label style={fieldLabelStyle}>类型</label>
                            <Select
                              value={dataSourceKind}
                              style={{ width: '100%' }}
                              onChange={onDataSourceKindChange}
                              options={[
                                { value: 'database', label: '数据库' },
                                { value: 'api', label: 'API' },
                                { value: 'protocol', label: '协议连接器' },
                              ]}
                            />
                          </Col>
                          <Col xs={24} xl={5}>
                            <label style={fieldLabelStyle}>名称</label>
                            <Input value={dataSourceName} onChange={(e) => setDataSourceName(e.target.value)} />
                          </Col>
                          <Col xs={24} xl={4}>
                            <label style={fieldLabelStyle}>协议</label>
                            <Select
                              value={dataSourceProtocol}
                              style={{ width: '100%' }}
                              onChange={setDataSourceProtocol}
                              options={(dataSourceKind === 'database'
                                ? ['postgresql', 'mysql', 'sqlite', 'mssql', 'oracle']
                                : dataSourceKind === 'api'
                                  ? ['rest', 'graphql', 'openapi', 'webhook']
                                  : ['mcp', 's3', 'oss', 'kafka', 'mqtt', 'amqp', 'ftp', 'sftp']
                              ).map((item) => ({ value: item, label: item }))}
                            />
                          </Col>
                          <Col xs={24} xl={5}>
                            <label style={fieldLabelStyle}>密钥引用</label>
                            <Input value={dataSourceSecretRef} onChange={(e) => setDataSourceSecretRef(e.target.value)} placeholder="例如 secret://prod/db-password" />
                            <div style={{ marginTop: 6, ...mutedTextStyle, fontSize: 12 }}>
                              支持 secret://scope/name 或 env:环境变量名。数据库密码/API Token 不要写进配置 JSON。
                            </div>
                          </Col>
                          <Col xs={24} xl={5}>
                            <label style={fieldLabelStyle}>操作</label>
                            <Button type="primary" onClick={onSaveDataSource} loading={loading} block>保存连接器</Button>
                          </Col>
                          <Col xs={24} xl={12}>
                            <label style={fieldLabelStyle}>连接配置 JSON</label>
                            <TextArea value={dataSourceConfigText} onChange={(e) => setDataSourceConfigText(e.target.value)} autoSize={{ minRows: 8, maxRows: 12 }} style={{ fontFamily: 'monospace', fontSize: 12 }} />
                          </Col>
                          <Col xs={24} xl={12}>
                            <label style={fieldLabelStyle}>已注册连接器</label>
                            <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, minHeight: 240, maxHeight: 360, overflowY: 'auto' }}>
                              {dataSources.length === 0 ? (
                                <div style={{ padding: 18, color: '#64748b' }}>还没有连接器。保存一个数据库、API 或协议连接器后，它会出现在这里。</div>
                              ) : (
                                <Table<OntologyDataSource>
                                  rowKey="id"
                                  size="small"
                                  pagination={false}
                                  dataSource={dataSources}
                                  columns={[
                                    { title: '名称', dataIndex: 'name' },
                                    { title: '协议', dataIndex: 'protocol', width: 120, render: (value, row) => <Tag>{row.kind}:{String(value)}</Tag> },
                                    { title: '检查', dataIndex: 'last_test_status', width: 100, render: (value) => <Tag color={value === 'ready' ? 'green' : value === 'invalid' ? 'red' : 'default'}>{String(value || '未测试')}</Tag> },
                                    {
                                      title: '操作',
                                      key: 'actions',
                                      width: 150,
                                      render: (_, row) => (
                                        <Space size={6}>
                                          <Button size="small" onClick={() => onTestDataSource(row)} loading={loading}>检查</Button>
                                          <Button size="small" type="primary" onClick={() => onDiscoverDataSource(row)} loading={loading}>发现结构</Button>
                                        </Space>
                                      ),
                                    },
                                  ]}
                                />
                              )}
                            </div>
                          </Col>
                        </Row>
                      </>
                    )}

                    {dataSourceEntryMode === 'sample' && (
                      <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, background: '#fff', padding: 14 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                        <div>
                          <Text strong style={{ fontSize: 16 }}>样本数据</Text>
                          <div style={{ marginTop: 4, ...mutedTextStyle }}>
                            没有现成连接器时，也可以先粘贴 JSON 或 CSV/TSV 样本。样本只负责识别字段，下一步再确认是否生成结构和映射。
                          </div>
                        </div>
                        <Space wrap>
                          <Segmented
                            value={sourceInputKind}
                            onChange={(value) => {
                              const next = value as SourceInputKind;
                              setSourceInputKind(next);
                              setSourceFields([]);
                              setSourceSampleText(next === 'json'
                                ? pretty({ item: { id: 'demo-1', name: 'demo name', amount: 1000, active: true } })
                                : 'id,name,amount,active\n demo-1,demo name,1000,true');
                            }}
                            options={[
                              { label: 'JSON', value: 'json' },
                              { label: 'CSV/TSV', value: 'table' },
                            ]}
                          />
                          <Button onClick={() => sourceFileInputRef.current?.click()}>导入文件</Button>
                          <Button type="primary" onClick={analyzeSourceSample}>解析样本</Button>
                        </Space>
                      </div>
                      <input ref={sourceFileInputRef} type="file" accept=".json,.csv,.tsv,.txt,.xlsx,.xls" style={{ display: 'none' }} onChange={onImportSourceSample} />
                      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 360px', gap: 14, marginTop: 14 }}>
                        <div>
                          <label style={fieldLabelStyle}>{sourceInputKind === 'json' ? '数据样本 JSON' : '表格样本 CSV / TSV'}</label>
                          <TextArea
                            value={sourceSampleText}
                            onChange={(e) => setSourceSampleText(e.target.value)}
                            autoSize={{ minRows: 8, maxRows: 14 }}
                            style={{ fontFamily: 'monospace', fontSize: 13 }}
                            placeholder={sourceInputKind === 'json'
                              ? '例如：\n{\n  "item": {\n    "id": "demo-1",\n    "name": "demo name"\n  }\n}'
                              : '例如：\nid,name,amount\n demo-1,demo name,1000'}
                          />
                        </div>
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                            <label style={{ ...fieldLabelStyle, marginBottom: 0 }}>识别结果</label>
                            <Tag color={sourceFields.length > 0 ? 'blue' : 'default'}>{sourceFields.length} 字段</Tag>
                          </div>
                          <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#f8fafc', minHeight: 220, maxHeight: 320, overflowY: 'auto' }}>
                            {sourceFields.length === 0 ? (
                              <div style={{ padding: 18, color: '#64748b' }}>
                                点击“解析样本”后，这里会列出字段路径、推断类型和样例值。
                              </div>
                            ) : (
                              <Table<SourceField>
                                rowKey="path"
                                size="small"
                                pagination={false}
                                dataSource={sourceFields}
                                columns={[
                                  { title: '路径', dataIndex: 'path', ellipsis: true },
                                  { title: '字段', dataIndex: 'name', width: 110 },
                                  { title: '类型', dataIndex: 'data_type', width: 76, render: (value) => <Tag>{String(value)}</Tag> },
                                ]}
                              />
                            )}
                          </div>
                        </div>
                      </div>
                      </div>
                    )}
                    <Space>
                      <Button type="primary" disabled={sourceFields.length === 0} onClick={() => setGuidedStep(2)}>
                        进入自动建模
                      </Button>
                      <Button onClick={() => setGuidedStep(3)}>手动建模</Button>
                      <Text style={mutedTextStyle}>数据库/API/协议连接器与样本数据二选一即可继续，后续可以互相补齐。</Text>
                    </Space>
                  </Space>
                </Card>
              )}

              {selectedSpaceId && guidedStep === 2 && (
                <Card
                  size="small"
                  style={contentCardStyle}
                  title={<span style={{ fontSize: 18, fontWeight: 700 }}>自动建模建议</span>}
                  extra={<Text style={mutedTextStyle}>确认字段后生成结构与默认映射。</Text>}
                >
                  {sourceFields.length === 0 ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="还没有可用样本字段"
                      description="请回到“数据来源”步骤导入或粘贴样本并点击解析。也可以跳到“数据结构”手动建模。"
                      action={<Button size="small" onClick={() => setGuidedStep(1)}>返回数据来源</Button>}
                    />
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 360px', gap: 16, alignItems: 'start' }}>
                      <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 12 }}>
                        <Table<SourceField>
                          rowKey="path"
                          size="small"
                          pagination={false}
                          dataSource={sourceFields}
                          columns={[
                            {
                              title: '使用',
                              dataIndex: 'ignored',
                              width: 72,
                              render: (_, row) => (
                                <Switch
                                  size="small"
                                  checked={!row.ignored}
                                  onChange={(checked) => updateSourceField(setSourceFields, row.path, { ignored: !checked })}
                                />
                              ),
                            },
                            { title: '来源路径', dataIndex: 'path', ellipsis: true },
                            {
                              title: '字段名',
                              dataIndex: 'name',
                              width: 160,
                              render: (_, row) => (
                                <Input
                                  value={row.name}
                                  disabled={row.ignored}
                                  onChange={(event) => updateSourceField(setSourceFields, row.path, { name: event.target.value })}
                                />
                              ),
                            },
                            {
                              title: '类型',
                              dataIndex: 'data_type',
                              width: 130,
                              render: (_, row) => (
                                <Select
                                  value={row.data_type}
                                  disabled={row.ignored}
                                  style={{ width: '100%' }}
                                  onChange={(value) => updateSourceField(setSourceFields, row.path, { data_type: value })}
                                  options={[
                                    { value: 'string', label: '文本' },
                                    { value: 'number', label: '小数' },
                                    { value: 'integer', label: '整数' },
                                    { value: 'boolean', label: '布尔' },
                                  ]}
                                />
                              ),
                            },
                            {
                              title: '必填',
                              dataIndex: 'required',
                              width: 80,
                              render: (_, row) => (
                                <Switch
                                  size="small"
                                  disabled={row.ignored}
                                  checked={row.required}
                                  onChange={(checked) => updateSourceField(setSourceFields, row.path, { required: checked })}
                                />
                              ),
                            },
                            { title: '样例/说明', dataIndex: 'sample', ellipsis: true },
                          ]}
                        />
                      </div>
                      <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 16 }}>
                        <Space direction="vertical" style={{ width: '100%' }} size={14}>
                          <div>
                            <label style={fieldLabelStyle}>对象名称</label>
                            <Input value={sourceEntityName} onChange={(e) => setSourceEntityName(e.target.value)} placeholder="例如 Customer、Order、Asset" />
                          </div>
                          <div>
                            <Text strong>将生成</Text>
                            <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                              <Tag color="blue">1 个对象：{sourceEntityName || 'Entity'}</Tag>
                              <Tag color="cyan">{sourceFields.filter((field) => !field.ignored).length} 个字段</Tag>
                              <Tag color="purple">{sourceFields.filter((field) => !field.ignored).length} 条默认映射</Tag>
                            </div>
                          </div>
                          <Alert
                            type="info"
                            showIcon
                            message="自动建模不会直接发布"
                            description="生成后会进入“数据结构”步骤，你仍然可以增删字段、补关系、再保存版本。"
                          />
                          <Space wrap>
                            <Button onClick={() => setGuidedStep(1)}>返回数据来源</Button>
                            <Button onClick={() => setGuidedStep(3)}>手动建模</Button>
                            <Button type="primary" onClick={applySourceSuggestion}>生成结构和映射</Button>
                          </Space>
                        </Space>
                      </div>
                    </div>
                  )}
                </Card>
              )}

            {selectedSpaceId && guidedStep >= 3 && guidedStep <= 5 && (
              <Card
                size="small"
                style={contentCardStyle}
                title={<span style={{ fontSize: 18, fontWeight: 700 }}>{activeWorkflowItem.title}</span>}
                extra={<Text style={mutedTextStyle}>保存后会自动生成底层包。</Text>}
              >
                <Space direction="vertical" style={{ width: '100%' }} size={16}>

                  {guidedBuilderKind === 'schema' && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(380px, 440px)', gap: 16, alignItems: 'start' }}>
                      <div style={{ gridColumn: '1 / -1', border: '1px solid #e2e8f0', borderRadius: 8, background: '#f8fafc', padding: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                          <Space size={8}>
                            <Text strong>对象</Text>
                            <Tag color="blue">{visualEntities.length}</Tag>
                          </Space>
                          <Button
                            size="small"
                            onClick={() => {
                              const nextEntity = { id: uid(), name: '', attributes: [], relations: [] };
                              setVisualEntities((prev) => [...prev, nextEntity]);
                              setActiveVisualEntityId(nextEntity.id);
                            }}
                          >
                            新增对象
                          </Button>
                        </div>
                        <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 2 }}>
                          {visualEntities.map((entity, entityIdx) => {
                            const active = activeVisualEntity?.id === entity.id;
                            return (
                              <button
                                key={entity.id}
                                type="button"
                                onClick={() => setActiveVisualEntityId(entity.id)}
                                style={{
                                  minWidth: 190,
                                  maxWidth: 260,
                                  textAlign: 'left',
                                  padding: '10px 12px',
                                  borderRadius: 8,
                                  border: active ? '1px solid #2563eb' : '1px solid #e2e8f0',
                                  background: active ? '#eff6ff' : '#fff',
                                  cursor: 'pointer',
                                  boxShadow: active ? '0 8px 18px rgba(37, 99, 235, 0.08)' : 'none',
                                }}
                              >
                                <div style={{ fontWeight: 700, color: '#0f172a' }}>{entity.name || `未命名对象 ${entityIdx + 1}`}</div>
                                <div style={{ marginTop: 4, color: '#64748b', fontSize: 12 }}>{entity.attributes.length} 个字段</div>
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 16 }}>
                        {activeVisualEntity ? (
                          <Space direction="vertical" style={{ width: '100%' }} size={14}>
                            <Row gutter={[12, 12]} align="bottom">
                              <Col xs={24} lg={8}>
                                <label style={fieldLabelStyle}>版本</label>
                                <Input value={visualSchemaVersion} onChange={(e) => setVisualSchemaVersion(e.target.value)} />
                              </Col>
                              <Col xs={24} lg={16}>
                                <label style={fieldLabelStyle}>对象名称</label>
                                <Input
                                  placeholder="例如 Customer、Invoice、Project"
                                  value={activeVisualEntity.name}
                                  onChange={(e) =>
                                    setVisualEntities((prev) =>
                                      prev.map((item) => (item.id === activeVisualEntity.id ? { ...item, name: e.target.value } : item)),
                                    )
                                  }
                                />
                              </Col>
                            </Row>
                            <Tabs
                              size="small"
                              items={[
                                {
                                  key: 'attributes',
                                  label: `字段 ${activeVisualEntity.attributes.length}`,
                                  children: (
                                    <Table<VisualAttribute>
                                      rowKey="id"
                                      size="small"
                                      pagination={false}
                                      dataSource={activeVisualEntity.attributes}
                                      locale={{ emptyText: '还没有字段，点击下方添加字段。' }}
                                      columns={[
                                        {
                                          title: '字段名',
                                          dataIndex: 'name',
                                          render: (_, row) => (
                                            <Input
                                              placeholder="字段名"
                                              value={row.name}
                                              onChange={(e) =>
                                                setVisualEntities((prev) =>
                                                  prev.map((item) =>
                                                    item.id !== activeVisualEntity.id
                                                      ? item
                                                      : {
                                                          ...item,
                                                          attributes: item.attributes.map((attr) => (attr.id === row.id ? { ...attr, name: e.target.value } : attr)),
                                                        },
                                                  ),
                                                )
                                              }
                                            />
                                          ),
                                        },
                                        {
                                          title: '类型',
                                          dataIndex: 'data_type',
                                          width: 150,
                                          render: (_, row) => (
                                            <Select
                                              value={row.data_type}
                                              style={{ width: '100%' }}
                                              onChange={(v) =>
                                                setVisualEntities((prev) =>
                                                  prev.map((item) =>
                                                    item.id !== activeVisualEntity.id
                                                      ? item
                                                      : {
                                                          ...item,
                                                          attributes: item.attributes.map((attr) => (attr.id === row.id ? { ...attr, data_type: v } : attr)),
                                                        },
                                                  ),
                                                )
                                              }
                                              options={[
                                                { value: 'string', label: '文本' },
                                                { value: 'number', label: '数字' },
                                                { value: 'integer', label: '整数' },
                                                { value: 'boolean', label: '布尔' },
                                              ]}
                                            />
                                          ),
                                        },
                                        {
                                          title: '必填',
                                          dataIndex: 'required',
                                          width: 90,
                                          render: (_, row) => (
                                            <Switch
                                              checked={row.required}
                                              onChange={(checked) =>
                                                setVisualEntities((prev) =>
                                                  prev.map((item) =>
                                                    item.id !== activeVisualEntity.id
                                                      ? item
                                                      : {
                                                          ...item,
                                                          attributes: item.attributes.map((attr) => (attr.id === row.id ? { ...attr, required: checked } : attr)),
                                                        },
                                                  ),
                                                )
                                              }
                                            />
                                          ),
                                        },
                                        {
                                          title: '',
                                          key: 'actions',
                                          width: 76,
                                          render: (_, row) => (
                                            <Button
                                              danger
                                              size="small"
                                              onClick={() =>
                                                setVisualEntities((prev) =>
                                                  prev.map((item) =>
                                                    item.id !== activeVisualEntity.id
                                                      ? item
                                                      : { ...item, attributes: item.attributes.filter((attr) => attr.id !== row.id) },
                                                  ),
                                                )
                                              }
                                            >
                                              删除
                                            </Button>
                                          ),
                                        },
                                      ]}
                                    />
                                  ),
                                },
                                {
                                  key: 'relations',
                                  label: `关系 ${(activeVisualEntity.relations || []).length}`,
                                  children: (
                                    <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12, background: '#f8fafc' }}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                                        <Text strong>对象关系</Text>
                                        <Button
                                          size="small"
                                          onClick={() =>
                                            setVisualEntities((prev) =>
                                              prev.map((item) =>
                                                item.id !== activeVisualEntity.id
                                                  ? item
                                                  : (() => {
                                                      const target = visualEntities.find((entity) => entity.id !== item.id) || item;
                                                      return {
                                                        ...item,
                                                        relations: [
                                                          ...(item.relations || []),
                                                          {
                                                            id: uid(),
                                                            name: '',
                                                            target_entity_id: target.id,
                                                            target_type: target.name || 'Entity',
                                                            cardinality: 'many',
                                                          },
                                                        ],
                                                      };
                                                    })(),
                                              ),
                                            )
                                          }
                                        >
                                          添加关系
                                        </Button>
                                      </div>
                                      <Table<VisualRelation>
                                        rowKey="id"
                                        size="small"
                                        pagination={false}
                                        dataSource={activeVisualEntity.relations || []}
                                        locale={{ emptyText: '暂无关系。对象之间有关联时再添加即可。' }}
                                        columns={[
                                          {
                                            title: '关系名',
                                            dataIndex: 'name',
                                            render: (_, row) => (
                                              <Input
                                                placeholder="例如 owns、contains、belongs_to"
                                                value={row.name}
                                                onChange={(e) =>
                                                  setVisualEntities((prev) =>
                                                    prev.map((item) =>
                                                      item.id !== activeVisualEntity.id
                                                        ? item
                                                        : {
                                                            ...item,
                                                            relations: (item.relations || []).map((relation) =>
                                                              relation.id === row.id ? { ...relation, name: e.target.value } : relation,
                                                            ),
                                                          },
                                                    ),
                                                  )
                                                }
                                              />
                                            ),
                                          },
                                          {
                                            title: '目标对象',
                                            dataIndex: 'target_type',
                                            width: 160,
                                            render: (_, row) => (
                                              <Select
                                                value={row.target_entity_id || visualEntities.find((entity) => entity.name === row.target_type)?.id}
                                                style={{ width: '100%' }}
                                                onChange={(v) =>
                                                  setVisualEntities((prev) =>
                                                    prev.map((item) =>
                                                      item.id !== activeVisualEntity.id
                                                        ? item
                                                        : {
                                                            ...item,
                                                            relations: (item.relations || []).map((relation) =>
                                                              relation.id === row.id
                                                                ? {
                                                                    ...relation,
                                                                    target_entity_id: v,
                                                                    target_type: visualEntities.find((entity) => entity.id === v)?.name || relation.target_type,
                                                                  }
                                                                : relation,
                                                            ),
                                                          },
                                                    ),
                                                  )
                                                }
                                                options={visualEntities.map((entity) => ({ value: entity.id, label: entity.name || '未命名对象' }))}
                                              />
                                            ),
                                          },
                                          {
                                            title: '数量',
                                            dataIndex: 'cardinality',
                                            width: 110,
                                            render: (_, row) => (
                                              <Select
                                                value={row.cardinality}
                                                style={{ width: '100%' }}
                                                onChange={(v) =>
                                                  setVisualEntities((prev) =>
                                                    prev.map((item) =>
                                                      item.id !== activeVisualEntity.id
                                                        ? item
                                                        : {
                                                            ...item,
                                                            relations: (item.relations || []).map((relation) =>
                                                              relation.id === row.id ? { ...relation, cardinality: v } : relation,
                                                            ),
                                                          },
                                                    ),
                                                  )
                                                }
                                                options={[
                                                  { value: 'one', label: '一对一' },
                                                  { value: 'many', label: '一对多' },
                                                ]}
                                              />
                                            ),
                                          },
                                          {
                                            title: '',
                                            key: 'actions',
                                            width: 70,
                                            render: (_, row) => (
                                              <Button
                                                danger
                                                size="small"
                                                onClick={() =>
                                                  setVisualEntities((prev) =>
                                                    prev.map((item) =>
                                                      item.id !== activeVisualEntity.id
                                                        ? item
                                                        : { ...item, relations: (item.relations || []).filter((relation) => relation.id !== row.id) },
                                                    ),
                                                  )
                                                }
                                              >
                                                删除
                                              </Button>
                                            ),
                                          },
                                        ]}
                                      />
                                    </div>
                                  ),
                                },
                              ]}
                            />
                            <Space wrap>
                              <Button
                                onClick={() =>
                                  setVisualEntities((prev) =>
                                    prev.map((item) =>
                                      item.id !== activeVisualEntity.id
                                        ? item
                                        : {
                                            ...item,
                                            attributes: [...item.attributes, { id: uid(), name: '', data_type: 'string', required: false }],
                                          },
                                    ),
                                  )
                                }
                              >
                                添加字段
                              </Button>
                              <Button
                                danger
                                disabled={visualEntities.length <= 1}
                                onClick={() => setVisualEntities((prev) => prev.filter((item) => item.id !== activeVisualEntity.id))}
                              >
                                删除对象
                              </Button>
                              <Button type="primary" onClick={saveVisualSchema} loading={loading}>
                                保存结构
                              </Button>
                              {schemaValidationIssues.length > 0 && <Text type="warning">还有 {schemaValidationIssues.length} 个结构问题</Text>}
                            </Space>
                          </Space>
                        ) : (
                          <Alert message="请先创建一个对象。" type="info" showIcon />
                        )}
                      </div>

                      <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#f8fafc', padding: 14 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                          <Space size={8} wrap>
                            <Text strong>{schemaInspectorMode === 'graph' ? '本体图视角' : '结构摘要'}</Text>
                            <Button size="small" onClick={() => setViewMode('graph')}>
                              打开图谱视图
                            </Button>
                            <Tag color="blue">实时</Tag>
                            <Tag color={schemaValidationIssues.length > 0 ? 'orange' : 'green'}>
                              {schemaValidationIssues.length > 0 ? `${schemaValidationIssues.length} 个问题` : '可保存'}
                            </Tag>
                          </Space>
                          <Segmented
                            size="small"
                            value={schemaInspectorMode}
                            onChange={(value) => setSchemaInspectorMode(value as 'graph' | 'summary')}
                            options={[
                              { label: '图视角', value: 'graph' },
                              { label: '摘要', value: 'summary' },
                            ]}
                          />
                        </div>
                        {schemaValidationIssues.length > 0 && (
                          <Alert
                            type="warning"
                            showIcon
                            style={{ marginTop: 10 }}
                            message="保存前需要处理"
                            description={
                              <ul style={{ margin: 0, paddingLeft: 18 }}>
                                {schemaValidationIssues.slice(0, 4).map((issue) => (
                                  <li key={issue}>{issue}</li>
                                ))}
                              </ul>
                            }
                          />
                        )}
                        {schemaInspectorMode === 'graph' ? (
                          <>
                            <div style={{ display: 'flex', gap: 10, marginTop: 10, color: '#64748b', fontSize: 12 }}>
                              <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 999, background: '#dbeafe', border: '1px solid #2563eb', marginRight: 4 }} />当前对象</span>
                              <span><span style={{ display: 'inline-block', width: 16, height: 2, background: '#94a3b8', marginRight: 4, verticalAlign: 'middle' }} />关系</span>
                            </div>
                            <div style={{ marginTop: 12, border: '1px solid #dbeafe', borderRadius: 8, background: '#fff', overflow: 'hidden' }}>
                              <svg viewBox={`0 0 ${schemaGraph.width} ${schemaGraph.height}`} width="100%" height="360" role="img" aria-label="本体结构图">
                                <defs>
                                  <marker id="ontology-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
                                    <path d="M0,0 L8,4 L0,8 Z" fill="#94a3b8" />
                                  </marker>
                                </defs>
                                <rect x="0" y="0" width={schemaGraph.width} height={schemaGraph.height} fill="#f8fafc" />
                                {schemaGraph.nodes.length === 0 && (
                                  <text x={schemaGraph.width / 2} y={schemaGraph.height / 2} textAnchor="middle" fontSize="13" fill="#64748b">
                                    新增对象后会在这里生成本体图
                                  </text>
                                )}
                                {schemaGraph.edges.map((edge) => (
                                  <g key={edge.id}>
                                    <line
                                      x1={edge.source.x}
                                      y1={edge.source.y}
                                      x2={edge.target.x}
                                      y2={edge.target.y}
                                      stroke="#94a3b8"
                                      strokeWidth="1.8"
                                      markerEnd="url(#ontology-arrow)"
                                    />
                                    <text
                                      x={(edge.source.x + edge.target.x) / 2}
                                      y={(edge.source.y + edge.target.y) / 2 - 6}
                                      textAnchor="middle"
                                      fontSize="10"
                                      fill="#475569"
                                    >
                                      {edge.name}
                                    </text>
                                  </g>
                                ))}
                                {schemaGraph.edges.length === 0 && schemaGraph.nodes.length > 1 && (
                                  <text x={schemaGraph.width / 2} y={schemaGraph.height - 24} textAnchor="middle" fontSize="11" fill="#94a3b8">
                                    可在左侧对象关系中添加连线
                                  </text>
                                )}
                                {schemaGraph.nodes.map((node) => {
                                  const active = activeVisualEntity?.id === node.id;
                                  return (
                                    <g key={node.id} onClick={() => setActiveVisualEntityId(node.id)} style={{ cursor: 'pointer' }}>
                                      <circle cx={node.x} cy={node.y} r={active ? 34 : 30} fill={active ? '#dbeafe' : '#ffffff'} stroke={active ? '#2563eb' : '#cbd5e1'} strokeWidth="2" />
                                      <text x={node.x} y={node.y - 2} textAnchor="middle" fontSize="11" fontWeight="700" fill="#0f172a">
                                        {node.name.length > 14 ? `${node.name.slice(0, 12)}…` : node.name}
                                      </text>
                                      <text x={node.x} y={node.y + 13} textAnchor="middle" fontSize="9" fill="#64748b">
                                        {(visualEntities.find((entity) => entity.id === node.id)?.attributes.length || 0)} 字段
                                      </text>
                                    </g>
                                  );
                                })}
                              </svg>
                            </div>
                            <Text style={{ ...mutedTextStyle, display: 'block', marginTop: 8 }}>
                              点击节点可切换正在编辑的对象。
                            </Text>
                          </>
                        ) : (
                          <Space direction="vertical" style={{ width: '100%', marginTop: 12, maxHeight: 420, overflowY: 'auto' }} size={10}>
                            {visualEntities.map((entity) => (
                              <div key={entity.id} style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 12 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                                  <Text strong>{entity.name || '未命名对象'}</Text>
                                  <Tag>{entity.attributes.length} 字段 · {(entity.relations || []).length} 关系</Tag>
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
                                  {entity.attributes.length === 0 && <Text style={mutedTextStyle}>暂无字段</Text>}
                                  {entity.attributes.map((attr) => (
                                    <Tag key={attr.id} color={attr.required ? 'blue' : 'default'}>
                                      {attr.name || '未命名'} · {attr.data_type}
                                    </Tag>
                                  ))}
                                  {(entity.relations || []).map((relation) => (
                                    <Tag key={relation.id} color="purple">
                                      {relation.name || '未命名关系'} → {relation.target_type || '目标对象'}
                                    </Tag>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </Space>
                        )}
                      </div>
                    </div>
                  )}

                  {guidedBuilderKind === 'mapping' && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 280px', gap: 14 }}>
                      <Space direction="vertical" style={{ width: '100%', border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 16 }} size={14}>
                        <Row gutter={[12, 12]}>
                          <Col xs={24} md={6}>
                            <label style={fieldLabelStyle}>版本</label>
                            <Input value={visualMappingVersion} onChange={(e) => setVisualMappingVersion(e.target.value)} />
                          </Col>
                          <Col xs={24} md={6}>
                            <label style={fieldLabelStyle}>目标对象</label>
                            <Select
                              value={visualMappingEntityType}
                              style={{ width: '100%' }}
                              onChange={(v) => setVisualMappingEntityType(v)}
                              options={visualEntities.map((entity) => ({ value: entity.name || 'Entity', label: entity.name || '未命名对象' }))}
                            />
                          </Col>
                          <Col xs={24} md={6}>
                            <label style={fieldLabelStyle}>来源节点</label>
                            <Input value={visualMappingSourcePath} onChange={(e) => setVisualMappingSourcePath(e.target.value)} />
                          </Col>
                          <Col xs={24} md={6}>
                            <label style={fieldLabelStyle}>ID 模板</label>
                            <Input value={visualMappingIdTemplate} onChange={(e) => setVisualMappingIdTemplate(e.target.value)} />
                          </Col>
                        </Row>
                        <Table<VisualMappingField>
                          rowKey="id"
                          size="small"
                          pagination={false}
                          dataSource={visualMappingFields}
                          columns={[
                            { title: '输入字段路径', dataIndex: 'source_path', render: (_, row) => <Input value={row.source_path} onChange={(e) => setVisualMappingFields((prev) => prev.map((f) => (f.id === row.id ? { ...f, source_path: e.target.value } : f)))} /> },
                            { title: '写入对象字段', dataIndex: 'target_attr', render: (_, row) => <Input value={row.target_attr} onChange={(e) => setVisualMappingFields((prev) => prev.map((f) => (f.id === row.id ? { ...f, target_attr: e.target.value } : f)))} /> },
                            {
                              title: '转换',
                              dataIndex: 'transform',
                              width: 140,
                              render: (_, row) => (
                                <Select
                                  value={row.transform}
                                  style={{ width: '100%' }}
                                  onChange={(v) => setVisualMappingFields((prev) => prev.map((f) => (f.id === row.id ? { ...f, transform: v } : f)))}
                                  options={[
                                    { value: '', label: '无' },
                                    { value: 'trim', label: '去空格' },
                                    { value: 'lower', label: '小写' },
                                    { value: 'upper', label: '大写' },
                                    { value: 'to_int', label: '转整数' },
                                    { value: 'to_float', label: '转小数' },
                                    { value: 'to_bool', label: '转布尔' },
                                  ]}
                                />
                              ),
                            },
                            { title: '必填', dataIndex: 'required', width: 90, render: (_, row) => <Switch checked={row.required} onChange={(checked) => setVisualMappingFields((prev) => prev.map((f) => (f.id === row.id ? { ...f, required: checked } : f)))} /> },
                            { title: '', key: 'actions', width: 76, render: (_, row) => <Button danger size="small" onClick={() => setVisualMappingFields((prev) => prev.filter((f) => f.id !== row.id))}>删除</Button> },
                          ]}
                        />
                        <Space wrap>
                          <Button onClick={() => setVisualMappingFields((prev) => [...prev, { id: uid(), source_path: '', target_attr: '', transform: '', required: false }])}>新增映射字段</Button>
                          <Button type="primary" onClick={saveVisualMapping} loading={loading}>保存映射</Button>
                        </Space>
                      </Space>
                      <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#f8fafc', padding: 14 }}>
                        <Text strong>映射预览</Text>
                        <div style={{ marginTop: 12, display: 'grid', gap: 10 }}>
                          <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 12 }}>
                            <Text type="secondary">输入</Text>
                            <div style={{ marginTop: 4, fontWeight: 700 }}>{visualMappingSourcePath || '根节点'}</div>
                          </div>
                          <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 12 }}>
                            <Text type="secondary">输出对象</Text>
                            <div style={{ marginTop: 4, fontWeight: 700 }}>{visualMappingEntityType || '未指定'}</div>
                          </div>
                          <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 12 }}>
                            <Text type="secondary">字段绑定</Text>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                              {visualMappingFields.filter((field) => field.source_path && field.target_attr).map((field) => (
                                <Tag key={field.id} color={field.required ? 'blue' : 'default'}>
                                  {field.source_path} → {field.target_attr}
                                </Tag>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {guidedBuilderKind === 'rule' && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 280px', gap: 14 }}>
                      <Space direction="vertical" style={{ width: '100%', border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 16 }} size={14}>
                        <Row gutter={[12, 12]}>
                          <Col xs={24} md={4}>
                            <label style={fieldLabelStyle}>版本</label>
                            <Input value={visualRuleVersion} onChange={(e) => setVisualRuleVersion(e.target.value)} />
                          </Col>
                          <Col xs={24} md={5}>
                            <label style={fieldLabelStyle}>规则 ID</label>
                            <Input value={visualRuleId} onChange={(e) => setVisualRuleId(e.target.value)} />
                          </Col>
                          <Col xs={24} md={7}>
                            <label style={fieldLabelStyle}>规则名称</label>
                            <Input value={visualRuleName} onChange={(e) => setVisualRuleName(e.target.value)} />
                          </Col>
                          <Col xs={24} md={4}>
                            <label style={fieldLabelStyle}>目标对象</label>
                            <Select
                              value={visualRuleTargetEntityType}
                              style={{ width: '100%' }}
                              onChange={(v) => setVisualRuleTargetEntityType(v)}
                              options={visualEntities.map((entity) => ({ value: entity.name || 'Entity', label: entity.name || '未命名对象' }))}
                            />
                          </Col>
                          <Col xs={12} md={2}>
                            <label style={fieldLabelStyle}>级别</label>
                            <Select value={visualRuleSeverity} style={{ width: '100%' }} onChange={(v) => setVisualRuleSeverity(v)} options={[{ value: 'low', label: '低' }, { value: 'medium', label: '中' }, { value: 'high', label: '高' }, { value: 'critical', label: '严重' }]} />
                          </Col>
                          <Col xs={12} md={2}>
                            <label style={fieldLabelStyle}>动作</label>
                            <Select value={visualRuleAction} style={{ width: '100%' }} onChange={(v) => setVisualRuleAction(v)} options={[{ value: 'flag', label: '标记' }, { value: 'block', label: '阻断' }, { value: 'recommend', label: '建议' }]} />
                          </Col>
                        </Row>
                        <Table<VisualRuleCondition>
                          rowKey="id"
                          size="small"
                          pagination={false}
                          dataSource={visualRuleConditions}
                          columns={[
                            { title: '检查路径', dataIndex: 'path', render: (_, row) => <Input value={row.path} onChange={(e) => setVisualRuleConditions((prev) => prev.map((c) => (c.id === row.id ? { ...c, path: e.target.value } : c)))} /> },
                            {
                              title: '判断方式',
                              dataIndex: 'operator',
                              width: 140,
                              render: (_, row) => (
                                <Select
                                  value={row.operator}
                                  style={{ width: '100%' }}
                                  onChange={(v) => setVisualRuleConditions((prev) => prev.map((c) => (c.id === row.id ? { ...c, operator: v } : c)))}
                                  options={[
                                    { value: 'eq', label: '等于' },
                                    { value: 'neq', label: '不等于' },
                                    { value: 'gt', label: '大于' },
                                    { value: 'gte', label: '大于等于' },
                                    { value: 'lt', label: '小于' },
                                    { value: 'lte', label: '小于等于' },
                                    { value: 'contains', label: '包含' },
                                    { value: 'in', label: '属于' },
                                    { value: 'exists', label: '存在' },
                                  ]}
                                />
                              ),
                            },
                            { title: '比较值', dataIndex: 'value', render: (_, row) => <Input disabled={row.operator === 'exists'} value={row.value} onChange={(e) => setVisualRuleConditions((prev) => prev.map((c) => (c.id === row.id ? { ...c, value: e.target.value } : c)))} /> },
                            { title: '', key: 'actions', width: 76, render: (_, row) => <Button danger size="small" onClick={() => setVisualRuleConditions((prev) => prev.filter((c) => c.id !== row.id))}>删除</Button> },
                          ]}
                        />
                        <Space wrap>
                          <Button onClick={() => setVisualRuleConditions((prev) => [...prev, { id: uid(), path: '', operator: 'exists', value: '' }])}>新增条件</Button>
                          <Button type="primary" onClick={saveVisualRule} loading={loading}>保存规则</Button>
                        </Space>
                      </Space>
                      <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#f8fafc', padding: 14 }}>
                        <Text strong>规则摘要</Text>
                        <div style={{ marginTop: 12, display: 'grid', gap: 10 }}>
                          <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 12 }}>
                            <Text type="secondary">命中对象</Text>
                            <div style={{ marginTop: 4, fontWeight: 700 }}>{visualRuleTargetEntityType || '未指定'}</div>
                          </div>
                          <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 12 }}>
                            <Text type="secondary">处置策略</Text>
                            <div style={{ marginTop: 8 }}>
                              <Tag color={visualRuleSeverity === 'critical' || visualRuleSeverity === 'high' ? 'red' : 'blue'}>{visualRuleSeverity}</Tag>
                              <Tag>{visualRuleAction}</Tag>
                            </div>
                          </div>
                          <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 12 }}>
                            <Text type="secondary">条件</Text>
                            <Space direction="vertical" style={{ width: '100%', marginTop: 8 }} size={6}>
                              {visualRuleConditions.map((condition) => (
                                <Tag key={condition.id}>
                                  {condition.path || '未设置路径'} {condition.operator} {condition.operator === 'exists' ? '' : condition.value}
                                </Tag>
                              ))}
                            </Space>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </Space>
              </Card>
            )}

              {selectedSpaceId && guidedStep === 6 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 420px) minmax(0, 1fr)', gap: 16 }}>
                  <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                      <Text strong>样本数据</Text>
                      <Tag color="blue">JSON</Tag>
                    </div>
                    <TextArea
                      value={mappingInput}
                      onChange={(e) => setMappingInput(e.target.value)}
                      autoSize={{ minRows: 16, maxRows: 22 }}
                      style={{ fontFamily: 'monospace', fontSize: 13 }}
                    />
                    <Space style={{ marginTop: 12 }} wrap>
                      <Button onClick={onGenerateSampleInput}>生成样本</Button>
                      <Button type="primary" onClick={onRunMapping} disabled={!runnableMappingPackage} loading={loading}>1. 映射成图</Button>
                      <Button onClick={onRunRules} disabled={!mappingResult || !runnableRulePackage} loading={loading}>2. 执行规则</Button>
                      <Button onClick={onExplain} disabled={!latestDecisionId} loading={loading}>3. 查看解释</Button>
                    </Space>
                    <Space direction="vertical" size={4} style={{ marginTop: 12, width: '100%' }}>
                      {!runnableMappingPackage && <Alert type="warning" showIcon message="还没有可用于调试的数据映射，请先在“数据映射”步骤保存。" />}
                      {!runnableRulePackage && <Alert type="warning" showIcon message="还没有可用于调试的业务规则，请先在“业务规则”步骤保存。" />}
                    </Space>
                  </div>

                  <Space direction="vertical" style={{ width: '100%' }} size={14}>
                    <div style={{ border: '1px solid #dbeafe', borderRadius: 8, background: '#eff6ff', padding: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                        <Text strong>本次调试使用版本</Text>
                        <Text style={mutedTextStyle}>页面调试会使用已保存版本，不强制要求 GA。</Text>
                      </div>
                      <Space wrap style={{ marginTop: 10 }}>
                        <Tag color={runnableSchemaPackage ? 'blue' : 'default'}>结构 {runnableSchemaPackage ? `${runnableSchemaPackage.version} / ${STAGE_LABELS[runnableSchemaPackage.stage]}` : '未保存'}</Tag>
                        <Tag color={runnableMappingPackage ? 'blue' : 'default'}>映射 {runnableMappingPackage ? `${runnableMappingPackage.version} / ${STAGE_LABELS[runnableMappingPackage.stage]}` : '未保存'}</Tag>
                        <Tag color={runnableRulePackage ? 'blue' : 'default'}>规则 {runnableRulePackage ? `${runnableRulePackage.version} / ${STAGE_LABELS[runnableRulePackage.stage]}` : '未保存'}</Tag>
                      </Space>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
                      {[
                        { title: '映射', status: mappingResult ? '完成' : '待执行', value: `${mappedEntityCount} 个对象`, color: mappingResult ? '#16a34a' : '#94a3b8' },
                        { title: '规则', status: ruleResult ? '完成' : '待执行', value: RISK_LABELS[ruleRiskLevel] || ruleRiskLevel, color: ruleResult ? '#2563eb' : '#94a3b8' },
                        { title: '解释', status: explainResult ? '完成' : '待执行', value: `${explainWhyCount} 条原因`, color: explainResult ? '#7c3aed' : '#94a3b8' },
                      ].map((item) => (
                        <div key={item.title} style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 14 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <Text type="secondary">{item.title}</Text>
                            <span style={{ width: 8, height: 8, borderRadius: 999, background: item.color, marginTop: 6 }} />
                          </div>
                          <div style={{ marginTop: 10, fontSize: 22, fontWeight: 800, color: '#0f172a' }}>{item.value}</div>
                          <div style={{ marginTop: 4, ...mutedTextStyle }}>{item.status}</div>
                        </div>
                      ))}
                    </div>

                    <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 16 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                        <Text strong>执行检查清单</Text>
                        <Text style={mutedTextStyle}>确认每一步的输入和产物是否可继续使用。</Text>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10, marginTop: 12 }}>
                        {[
                          {
                            title: '输入映射',
                            state: mappingResult ? '已生成' : '等待',
                            desc: mappingResult ? `本体图包含 ${mappedEntityCount} 个对象` : '先把样本数据转换成本体图',
                            ok: !!mappingResult,
                          },
                          {
                            title: '规则判断',
                            state: ruleResult ? '已判断' : '等待',
                            desc: ruleResult ? `当前风险：${RISK_LABELS[ruleRiskLevel] || ruleRiskLevel}` : '使用业务规则检查本体图',
                            ok: !!ruleResult,
                          },
                          {
                            title: '原因解释',
                            state: explainResult ? '已生成' : '等待',
                            desc: explainResult ? `已沉淀 ${explainWhyCount} 条解释依据` : '复盘 why / why-not / evidence',
                            ok: !!explainResult,
                          },
                        ].map((item, idx) => (
                          <div key={item.title} style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: item.ok ? '#f0fdf4' : '#f8fafc', padding: 12 }}>
                            <Tag color={item.ok ? 'green' : 'default'}>{idx + 1} · {item.state}</Tag>
                            <div style={{ marginTop: 8, fontWeight: 700 }}>{item.title}</div>
                            <div style={{ marginTop: 4, ...mutedTextStyle }}>{item.desc}</div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <Tabs
                      size="small"
                      items={[
                        {
                          key: 'mapping',
                          label: '映射详情',
                          children: <TextArea value={mappingResult || '暂无映射结果'} readOnly autoSize={{ minRows: 7, maxRows: 12 }} style={{ fontFamily: 'monospace', fontSize: 12 }} />,
                        },
                        {
                          key: 'rules',
                          label: '规则详情',
                          children: <TextArea value={ruleResult || '暂无规则结果'} readOnly autoSize={{ minRows: 7, maxRows: 12 }} style={{ fontFamily: 'monospace', fontSize: 12 }} />,
                        },
                        {
                          key: 'explain',
                          label: '解释详情',
                          children: <TextArea value={explainResult || '暂无解释结果'} readOnly autoSize={{ minRows: 7, maxRows: 12 }} style={{ fontFamily: 'monospace', fontSize: 12 }} />,
                        },
                      ]}
                    />
                  </Space>
                </div>
              )}

              {selectedSpaceId && guidedStep === 7 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 14 }}>
                  {(['schema', 'mapping', 'rule'] as PackageKind[]).map((targetKind) => {
                    const pkg = latestGuidedPackages[targetKind];
                    const allowedTargets = pkg ? getAllowedReleaseTargets(pkg.stage) : [];
                    const nextTarget = pkg ? NEXT_STAGE_MAP[pkg.stage] : null;
                    const stages: Stage[] = ['draft', 'review', 'staging', 'ga'];
                    const currentIndex = pkg ? stages.indexOf(pkg.stage) : -1;
                    return (
                      <div key={targetKind} style={{ border: '1px solid #e2e8f0', borderRadius: 8, background: '#fff', padding: 16 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 10 }}>
                          <div>
                            <div style={{ fontSize: 18, fontWeight: 800, color: '#0f172a' }}>{KIND_LABELS[targetKind]}</div>
                            <div style={{ marginTop: 4, ...mutedTextStyle }}>{pkg ? `版本 ${pkg.version}` : '暂无版本'}</div>
                          </div>
                          {pkg?.stage === 'ga' ? <Tag color="green">已上线</Tag> : <Tag>{pkg ? STAGE_LABELS[pkg.stage] : '未保存'}</Tag>}
                        </div>

                        <div style={{ display: 'grid', gap: 8, marginTop: 16 }}>
                          {stages.map((stage, idx) => {
                            const done = currentIndex >= idx;
                            const active = pkg?.stage === stage;
                            return (
                              <div key={stage} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <span
                                  style={{
                                    width: 18,
                                    height: 18,
                                    borderRadius: 999,
                                    background: done ? '#2563eb' : '#e2e8f0',
                                    border: active ? '2px solid #93c5fd' : '2px solid transparent',
                                  }}
                                />
                                <Text style={{ color: done ? '#0f172a' : '#94a3b8', fontWeight: active ? 700 : 500 }}>{STAGE_LABELS[stage]}</Text>
                              </div>
                            );
                          })}
                        </div>

                        <div style={{ marginTop: 18, minHeight: 42 }}>
                          {pkg?.stage === 'ga' ? (
                            <Alert type="success" showIcon message="已发布到 GA" />
                          ) : pkg && nextTarget ? (
                            <Button
                              block
                              type={nextTarget === 'ga' ? 'primary' : 'default'}
                              onClick={() => void onRelease(pkg, nextTarget)}
                              loading={loading}
                              disabled={!allowedTargets.includes(nextTarget)}
                            >
                              推进到 {STAGE_LABELS[nextTarget]}
                            </Button>
                          ) : (
                            <Button block disabled>先保存版本</Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {viewMode === 'graph' && (
          <div style={{ ...surfaceStyle, overflow: 'hidden' }}>
            <div style={{ padding: '12px 14px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <Space wrap>
                <Text strong>本体图工作区</Text>
                <Tag color="blue">{graphExplorerData.nodes.length} / {graphExplorerData.totalNodes} 对象</Tag>
                <Tag>{graphExplorerData.edges.length} / {graphExplorerData.totalEdges} 关系</Tag>
                {graphExplorerData.truncated && <Tag color="orange">已启用渲染上限 {graphExplorerData.maxNodes}</Tag>}
              </Space>
              <Space wrap>
                <Button onClick={() => setViewMode('guided')}>返回配置</Button>
                <Button type="primary" onClick={saveVisualSchema} loading={loading}>保存结构</Button>
              </Space>
            </div>
          <div style={{ height: 'calc(100vh - 210px)', minHeight: 680, display: 'grid', gridTemplateColumns: '280px minmax(0, 1fr) 360px', background: '#f8fafc' }}>
            <div style={{ borderRight: '1px solid #e5e7eb', background: '#fff', padding: 14, overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <Input
                placeholder="搜索对象、字段、关系"
                value={graphExplorerQuery}
                onChange={(e) => {
                  setGraphExplorerQuery(e.target.value);
                  if (e.target.value.trim()) setGraphExplorerMode('search');
                }}
                allowClear
              />
              <Segmented
                value={graphExplorerMode}
                onChange={(value) => setGraphExplorerMode(value as GraphExplorerMode)}
                options={[
                  { label: '聚焦', value: 'focus' },
                  { label: '搜索', value: 'search' },
                  { label: '全图', value: 'all' },
                ]}
              />
              <Alert
                type="info"
                showIcon
                message="操作方式"
                description="拖动画布、滚轮缩放；点击对象编辑属性，从一个对象拖线到另一个对象可创建关系。"
              />
              <Button type="primary" onClick={createVisualEntity}>新增对象</Button>
              <div style={{ overflowY: 'auto', minHeight: 0 }}>
                <Space direction="vertical" style={{ width: '100%' }} size={8}>
                  {visualEntities.map((entity) => {
                    const active = activeVisualEntity?.id === entity.id;
                    return (
                      <button
                        key={entity.id}
                        type="button"
                        onClick={() => {
                          setActiveVisualEntityId(entity.id);
                          setGraphExplorerMode('focus');
                        }}
                        style={{
                          width: '100%',
                          textAlign: 'left',
                          border: active ? '1px solid #2563eb' : '1px solid #e5e7eb',
                          background: active ? '#eff6ff' : '#fff',
                          borderRadius: 8,
                          padding: 10,
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ fontWeight: 800, color: '#111827' }}>{entity.name || '未命名对象'}</div>
                        <div style={{ marginTop: 4, color: '#64748b', fontSize: 12 }}>
                          {entity.attributes.length} 字段 · {(entity.relations || []).length} 关系
                        </div>
                      </button>
                    );
                  })}
                </Space>
              </div>
            </div>
            <div style={{ minWidth: 0, padding: 14, overflow: 'hidden' }}>
              <div style={{ height: '100%', border: '1px solid #e5e7eb', borderRadius: 12, background: '#fff', overflow: 'hidden' }}>
                <ReactFlow
                  nodes={graphFlowElements.nodes}
                  edges={graphFlowElements.edges}
                  onNodeClick={(_, node) => {
                    setActiveVisualEntityId(node.id);
                    setSelectedGraphEdgeId(null);
                    setGraphExplorerMode('focus');
                  }}
                  onEdgeClick={(_, edge) => {
                    setSelectedGraphEdgeId(edge.id);
                    const relation = visualEntities.find((entity) => (entity.relations || []).some((item) => item.id === edge.id));
                    if (relation) setActiveVisualEntityId(relation.id);
                  }}
                  onPaneClick={() => setSelectedGraphEdgeId(null)}
                  onConnect={onGraphConnect}
                  fitView
                  minZoom={0.2}
                  maxZoom={1.8}
                  onlyRenderVisibleElements
                  nodesDraggable
                  nodesConnectable
                  elementsSelectable
                  proOptions={{ hideAttribution: true }}
                  style={{ background: '#f8fafc' }}
                >
                  <Background color="#e2e8f0" gap={28} size={1} />
                  <Controls position="bottom-right" style={{ borderRadius: 8, overflow: 'hidden', boxShadow: '0 8px 24px rgba(15, 23, 42, 0.12)' }} />
                  <MiniMap
                    position="bottom-left"
                    pannable
                    zoomable
                    style={{ width: 180, height: 120, borderRadius: 10, border: '1px solid #dbe3ef', background: '#fff' }}
                    nodeColor={(node) => (node.id === activeVisualEntity?.id ? '#2563eb' : '#94a3b8')}
                  />
                  <Panel position="top-left">
                    <div style={{ padding: '8px 10px', background: 'rgba(255, 255, 255, 0.94)', border: '1px solid #e5e7eb', borderRadius: 10, boxShadow: '0 8px 22px rgba(15, 23, 42, 0.08)' }}>
                      <Space size={8} wrap>
                        <Tag color="blue">React Flow</Tag>
                        <Text style={{ fontSize: 12, color: '#64748b' }}>图上建模：点对象编辑，拖线建立关系</Text>
                      </Space>
                    </div>
                  </Panel>
                  {graphExplorerData.nodes.length === 0 && (
                    <Panel position="top-center">
                      <Alert type="info" showIcon message="没有匹配的对象" description="调整搜索条件，或切换到全图模式查看当前本体。" />
                    </Panel>
                  )}
                </ReactFlow>
              </div>
            </div>
            <div style={{ borderLeft: '1px solid #e5e7eb', background: '#fff', padding: 14, overflowY: 'auto' }}>
              <Space direction="vertical" style={{ width: '100%' }} size={14}>
                <div>
                  <Text strong>属性面板</Text>
                  <div style={{ marginTop: 4, ...mutedTextStyle }}>
                    {selectedGraphRelation ? '正在编辑关系' : '正在编辑对象'}
                  </div>
                </div>

                {selectedGraphRelation ? (
                  <Space direction="vertical" style={{ width: '100%' }} size={12}>
                    <div>
                      <label style={fieldLabelStyle}>来源对象</label>
                      <Input value={selectedGraphRelation.source.name || '未命名对象'} disabled />
                    </div>
                    <div>
                      <label style={fieldLabelStyle}>关系名称</label>
                      <Input
                        value={selectedGraphRelation.relation.name}
                        placeholder="例如 belongs_to、contains、depends_on"
                        onChange={(e) =>
                          setVisualEntities((prev) =>
                            prev.map((entity) =>
                              entity.id !== selectedGraphRelation.source.id
                                ? entity
                                : {
                                    ...entity,
                                    relations: (entity.relations || []).map((relation) =>
                                      relation.id === selectedGraphRelation.relation.id ? { ...relation, name: e.target.value } : relation,
                                    ),
                                  },
                            ),
                          )
                        }
                      />
                    </div>
                    <div>
                      <label style={fieldLabelStyle}>目标对象</label>
                      <Select
                        value={selectedGraphRelation.relation.target_entity_id}
                        style={{ width: '100%' }}
                        options={visualEntities.map((entity) => ({ value: entity.id, label: entity.name || '未命名对象' }))}
                        onChange={(value) =>
                          setVisualEntities((prev) =>
                            prev.map((entity) =>
                              entity.id !== selectedGraphRelation.source.id
                                ? entity
                                : {
                                    ...entity,
                                    relations: (entity.relations || []).map((relation) =>
                                      relation.id === selectedGraphRelation.relation.id
                                        ? {
                                            ...relation,
                                            target_entity_id: value,
                                            target_type: visualEntities.find((item) => item.id === value)?.name || relation.target_type,
                                          }
                                        : relation,
                                    ),
                                  },
                            ),
                          )
                        }
                      />
                    </div>
                    <div>
                      <label style={fieldLabelStyle}>数量关系</label>
                      <Select
                        value={selectedGraphRelation.relation.cardinality}
                        style={{ width: '100%' }}
                        options={[
                          { value: 'one', label: '一对一' },
                          { value: 'many', label: '一对多' },
                        ]}
                        onChange={(value) =>
                          setVisualEntities((prev) =>
                            prev.map((entity) =>
                              entity.id !== selectedGraphRelation.source.id
                                ? entity
                                : {
                                    ...entity,
                                    relations: (entity.relations || []).map((relation) =>
                                      relation.id === selectedGraphRelation.relation.id ? { ...relation, cardinality: value } : relation,
                                    ),
                                  },
                            ),
                          )
                        }
                      />
                    </div>
                    <Button
                      danger
                      onClick={() => {
                        setVisualEntities((prev) =>
                          prev.map((entity) =>
                            entity.id !== selectedGraphRelation.source.id
                              ? entity
                              : { ...entity, relations: (entity.relations || []).filter((relation) => relation.id !== selectedGraphRelation.relation.id) },
                          ),
                        );
                        setSelectedGraphEdgeId(null);
                      }}
                    >
                      删除关系
                    </Button>
                  </Space>
                ) : activeVisualEntity ? (
                  <Space direction="vertical" style={{ width: '100%' }} size={12}>
                    <div>
                      <label style={fieldLabelStyle}>对象名称</label>
                      <Input
                        value={activeVisualEntity.name}
                        placeholder="例如 Customer、Order、RiskEvent"
                        onChange={(e) =>
                          setVisualEntities((prev) =>
                            prev.map((entity) => (entity.id === activeVisualEntity.id ? { ...entity, name: e.target.value } : entity)),
                          )
                        }
                      />
                    </div>
                    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
                      <div style={{ padding: '10px 12px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text strong>字段</Text>
                        <Button
                          size="small"
                          onClick={() =>
                            setVisualEntities((prev) =>
                              prev.map((entity) =>
                                entity.id !== activeVisualEntity.id
                                  ? entity
                                  : { ...entity, attributes: [...entity.attributes, { id: uid(), name: '', data_type: 'string', required: false }] },
                              ),
                            )
                          }
                        >
                          添加字段
                        </Button>
                      </div>
                      <Space direction="vertical" style={{ width: '100%', padding: 12 }} size={10}>
                        {activeVisualEntity.attributes.length === 0 && <Text style={mutedTextStyle}>暂无字段，建议至少保留一个 id 字段。</Text>}
                        {activeVisualEntity.attributes.map((attr) => (
                          <div key={attr.id} style={{ display: 'grid', gridTemplateColumns: '1fr 96px 52px 42px', gap: 8, alignItems: 'center' }}>
                            <Input
                              value={attr.name}
                              placeholder="字段名"
                              onChange={(e) =>
                                setVisualEntities((prev) =>
                                  prev.map((entity) =>
                                    entity.id !== activeVisualEntity.id
                                      ? entity
                                      : {
                                          ...entity,
                                          attributes: entity.attributes.map((item) => (item.id === attr.id ? { ...item, name: e.target.value } : item)),
                                        },
                                  ),
                                )
                              }
                            />
                            <Select
                              value={attr.data_type}
                              options={[
                                { value: 'string', label: '文本' },
                                { value: 'number', label: '小数' },
                                { value: 'integer', label: '整数' },
                                { value: 'boolean', label: '布尔' },
                              ]}
                              onChange={(value) =>
                                setVisualEntities((prev) =>
                                  prev.map((entity) =>
                                    entity.id !== activeVisualEntity.id
                                      ? entity
                                      : {
                                          ...entity,
                                          attributes: entity.attributes.map((item) => (item.id === attr.id ? { ...item, data_type: value } : item)),
                                        },
                                  ),
                                )
                              }
                            />
                            <Switch
                              checked={attr.required}
                              onChange={(checked) =>
                                setVisualEntities((prev) =>
                                  prev.map((entity) =>
                                    entity.id !== activeVisualEntity.id
                                      ? entity
                                      : {
                                          ...entity,
                                          attributes: entity.attributes.map((item) => (item.id === attr.id ? { ...item, required: checked } : item)),
                                        },
                                  ),
                                )
                              }
                            />
                            <Button
                              danger
                              size="small"
                              onClick={() =>
                                setVisualEntities((prev) =>
                                  prev.map((entity) =>
                                    entity.id !== activeVisualEntity.id
                                      ? entity
                                      : { ...entity, attributes: entity.attributes.filter((item) => item.id !== attr.id) },
                                  ),
                                )
                              }
                            >
                              删
                            </Button>
                          </div>
                        ))}
                      </Space>
                    </div>
                    <Space wrap>
                      <Button
                        danger
                        disabled={visualEntities.length <= 1}
                        onClick={() => {
                          const deletingId = activeVisualEntity.id;
                          setVisualEntities((prev) =>
                            prev
                              .filter((entity) => entity.id !== deletingId)
                              .map((entity) => ({
                                ...entity,
                                relations: (entity.relations || []).filter((relation) => relation.target_entity_id !== deletingId),
                              })),
                          );
                          setSelectedGraphEdgeId(null);
                        }}
                      >
                        删除对象
                      </Button>
                      <Button type="primary" onClick={saveVisualSchema} loading={loading}>
                        保存结构
                      </Button>
                    </Space>
                    {schemaValidationIssues.length > 0 && (
                      <Alert type="warning" showIcon message="结构需要处理" description={schemaValidationIssues.slice(0, 3).join('；')} />
                    )}
                  </Space>
                ) : (
                  <Alert type="info" showIcon message="请选择或新建对象" />
                )}
              </Space>
            </div>
          </div>
          </div>
        )}

        {viewMode === 'pro' && (
          <Space direction="vertical" style={{ width: '100%' }} size={18}>
            <Card size="small" style={sectionCardStyle} title={<span style={{ fontSize: 18, fontWeight: 700 }}>治理上下文</span>}>
              <Row gutter={[16, 16]} align="bottom">
                <Col xs={24} xl={12}>
                  <label style={fieldLabelStyle}>当前空间</label>
                  <Select
                    style={{ width: '100%' }}
                    value={selectedSpaceId ?? undefined}
                    placeholder="请选择本体空间"
                    onChange={(v) => setSelectedSpaceId(v)}
                    options={visibleSpaces.map((s) => ({ label: `${s.name} (${s.code})`, value: s.id }))}
                    size="large"
                  />
                </Col>
                <Col xs={24} md={12} xl={6}>
                  <label style={fieldLabelStyle}>所有者</label>
                  <div
                    style={{
                      height: 40,
                      display: 'flex',
                      alignItems: 'center',
                      padding: '0 14px',
                      borderRadius: 12,
                      background: '#eff6ff',
                      border: '1px solid #bfdbfe',
                      color: '#1d4ed8',
                      fontWeight: 600,
                    }}
                  >
                    {selectedSpace ? selectedSpace.owner_user_id : '未选择'}
                  </div>
                </Col>
                <Col xs={24} md={12} xl={6}>
                  <label style={fieldLabelStyle}>组织范围</label>
                  <Select
                    style={{ width: '100%' }}
                    value={selectedOrgFilter}
                    onChange={setSelectedOrgFilter}
                    options={[
                      { value: 'all', label: '全部组织' },
                      { value: '__none__', label: '仅个人空间' },
                      ...orgs.map((o) => ({ value: o.id, label: `${o.name} (${o.code})` })),
                    ]}
                    size="large"
                  />
                </Col>
              </Row>
            </Card>

            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              tabPosition="left"
              style={{ ...sectionCardStyle, padding: 18 }}
              items={[
                {
                  key: 'workspace',
                  label: '空间与组织',
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }} size={18}>
                      {!selectedSpaceId && (
                        <Alert
                          type="warning"
                          showIcon
                          message="先在这里创建或选择空间，再继续版本管理、映射调试和规则验证。"
                          style={{ borderRadius: 12 }}
                        />
                      )}
                      <Row gutter={[18, 18]}>
                        <Col xs={24} xl={9}>
                          <Card size="small" style={sectionCardStyle} title={<span style={{ fontSize: 18, fontWeight: 700 }}>组织</span>}>
                            <Space direction="vertical" style={{ width: '100%' }} size={14}>
                              <div>
                                <label style={fieldLabelStyle}>组织编码</label>
                                <Input placeholder="例如 finance-cn" value={newOrgCode} onChange={(e) => setNewOrgCode(e.target.value)} size="large" />
                              </div>
                              <div>
                                <label style={fieldLabelStyle}>组织名称</label>
                                <Input placeholder="例如 财务中台" value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)} size="large" />
                              </div>
                              <div style={mutedTextStyle}>如果没有组织权限，也可以直接使用个人空间。</div>
                              <Button onClick={onCreateOrg} loading={loading} size="large">创建组织</Button>
                            </Space>
                          </Card>
                        </Col>
                        <Col xs={24} xl={15}>
                          <Card size="small" style={sectionCardStyle} title={<span style={{ fontSize: 18, fontWeight: 700 }}>新建空间</span>}>
                            <Form layout="vertical" onFinish={onCreateSpace}>
                              <Row gutter={[12, 4]}>
                                <Col xs={24} md={12}>
                                  <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入空间名' }]}>
                                    <Input placeholder="例如 风险治理生产空间" size="large" />
                                  </Form.Item>
                                </Col>
                                <Col xs={24} md={12}>
                                  <Form.Item label="代码" name="code">
                                    <Input placeholder="例如 risk-prod" size="large" />
                                  </Form.Item>
                                </Col>
                                <Col xs={24} md={12}>
                                  <Form.Item label="描述" name="description">
                                    <Input placeholder="可选，用于记录用途" size="large" />
                                  </Form.Item>
                                </Col>
                                <Col xs={24} md={12}>
                                  <Form.Item label="绑定组织">
                                    <Select
                                      allowClear
                                      placeholder="可选"
                                      value={spaceOrgId}
                                      onChange={(v) => setSpaceOrgId(v)}
                                      options={orgs.map((o) => ({ value: o.id, label: `${o.name} (${o.code})` }))}
                                      size="large"
                                    />
                                  </Form.Item>
                                </Col>
                                <Col span={24}>
                                  <Button htmlType="submit" type="primary" loading={loading} size="large">创建空间</Button>
                                </Col>
                              </Row>
                            </Form>
                          </Card>
                        </Col>
                      </Row>
                    </Space>
                  ),
                },
                {
                  key: 'secrets',
                  label: '密钥管理',
                  disabled: !selectedSpaceId,
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }} size={14}>
                      <Alert
                        type="info"
                        showIcon
                        message="密钥以密文落库，连接器通过 secret://scope/name 引用"
                        description="保存后可直接复制 ref 到数据源的“密钥引用”。也兼容 env:环境变量名。"
                      />
                      <Card size="small" title="新建或更新密钥" style={sectionCardStyle}>
                        <Row gutter={[12, 12]} align="bottom">
                          <Col xs={24} md={5}>
                            <label style={fieldLabelStyle}>Scope</label>
                            <Input value={secretScope} onChange={(e) => setSecretScope(e.target.value)} placeholder="prod" />
                          </Col>
                          <Col xs={24} md={6}>
                            <label style={fieldLabelStyle}>Name</label>
                            <Input value={secretName} onChange={(e) => setSecretName(e.target.value)} placeholder="db-password" />
                          </Col>
                          <Col xs={24} md={7}>
                            <label style={fieldLabelStyle}>密钥值</label>
                            <Input.Password value={secretValue} onChange={(e) => setSecretValue(e.target.value)} placeholder="不会明文返回" />
                          </Col>
                          <Col xs={24} md={6}>
                            <label style={fieldLabelStyle}>说明</label>
                            <Input value={secretDescription} onChange={(e) => setSecretDescription(e.target.value)} placeholder="可选" />
                          </Col>
                          <Col span={24}>
                            <Button type="primary" onClick={onSaveSecret} loading={loading}>保存密钥</Button>
                          </Col>
                        </Row>
                      </Card>
                      <Card size="small" title="已保存密钥" style={sectionCardStyle}>
                        <Table<OntologySecretRecord>
                          rowKey="id"
                          dataSource={secrets}
                          pagination={{ pageSize: 8 }}
                          columns={[
                            { title: '引用', dataIndex: 'ref', render: (value) => <Tag color="blue">{value}</Tag> },
                            { title: '说明', dataIndex: 'description' },
                            { title: '创建人', dataIndex: 'created_by', width: 130 },
                            { title: '更新时间', dataIndex: 'updated_at', width: 180 },
                            {
                              title: '操作',
                              width: 120,
                              render: (_, row) => <Button size="small" onClick={() => setDataSourceSecretRef(row.ref)}>填入数据源</Button>,
                            },
                          ]}
                        />
                      </Card>
                    </Space>
                  ),
                },
                {
                  key: 'datasources',
                  label: '数据源发现',
                  disabled: !selectedSpaceId,
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }} size={14}>
                      <Card size="small" title="连接器配置" style={sectionCardStyle}>
                        <Row gutter={[12, 12]}>
                          <Col xs={24} xl={4}>
                            <label style={fieldLabelStyle}>类型</label>
                            <Select
                              value={dataSourceKind}
                              style={{ width: '100%' }}
                              onChange={onDataSourceKindChange}
                              options={[
                                { value: 'database', label: '数据库' },
                                { value: 'api', label: 'API' },
                                { value: 'protocol', label: '协议' },
                              ]}
                            />
                          </Col>
                          <Col xs={24} xl={5}>
                            <label style={fieldLabelStyle}>名称</label>
                            <Input value={dataSourceName} onChange={(e) => setDataSourceName(e.target.value)} />
                          </Col>
                          <Col xs={24} xl={4}>
                            <label style={fieldLabelStyle}>协议</label>
                            <Select
                              value={dataSourceProtocol}
                              style={{ width: '100%' }}
                              onChange={setDataSourceProtocol}
                              options={(dataSourceKind === 'database'
                                ? ['postgresql', 'mysql', 'sqlite', 'mssql', 'oracle']
                                : dataSourceKind === 'api'
                                  ? ['rest', 'graphql', 'openapi', 'webhook']
                                  : ['mcp', 's3', 'oss', 'kafka', 'mqtt', 'amqp', 'ftp', 'sftp']
                              ).map((item) => ({ value: item, label: item }))}
                            />
                          </Col>
                          <Col xs={24} xl={7}>
                            <label style={fieldLabelStyle}>密钥引用</label>
                            <Input value={dataSourceSecretRef} onChange={(e) => setDataSourceSecretRef(e.target.value)} placeholder="secret://prod/db-password" />
                          </Col>
                          <Col xs={24} xl={4}>
                            <label style={fieldLabelStyle}>操作</label>
                            <Button type="primary" block onClick={onSaveDataSource} loading={loading}>保存连接器</Button>
                          </Col>
                          <Col span={24}>
                            <label style={fieldLabelStyle}>配置 JSON</label>
                            <TextArea value={dataSourceConfigText} onChange={(e) => setDataSourceConfigText(e.target.value)} autoSize={{ minRows: 8, maxRows: 14 }} style={{ fontFamily: 'monospace' }} />
                          </Col>
                        </Row>
                      </Card>
                      <Card size="small" title="发现与导入" style={sectionCardStyle}>
                        <Table<OntologyDataSource>
                          rowKey="id"
                          dataSource={dataSources}
                          pagination={{ pageSize: 8 }}
                          columns={[
                            { title: '名称', dataIndex: 'name' },
                            { title: '协议', dataIndex: 'protocol', render: (value, row) => <Tag>{row.kind}:{String(value)}</Tag> },
                            { title: '密钥', dataIndex: 'secret_ref', render: (value) => value ? <Tag color="blue">{String(value)}</Tag> : <Text type="secondary">未配置</Text> },
                            { title: '检查', dataIndex: 'last_test_status', render: (value) => <Tag color={value === 'ready' ? 'green' : value === 'invalid' ? 'red' : 'default'}>{String(value || '未测试')}</Tag> },
                            {
                              title: '操作',
                              width: 220,
                              render: (_, row) => (
                                <Space>
                                  <Button size="small" onClick={() => onTestDataSource(row)} loading={loading}>检查</Button>
                                  <Button size="small" type="primary" onClick={() => onDiscoverDataSource(row)} loading={loading}>发现结构</Button>
                                </Space>
                              ),
                            },
                          ]}
                        />
                      </Card>
                    </Space>
                  ),
                },
                {
                  key: 'packages',
                  label: '版本管理',
                  disabled: !selectedSpaceId,
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }} size={14}>
                      <Card size="small" title="包编辑" style={sectionCardStyle}>
                        <Row gutter={[12, 12]} align="middle">
                          <Col xs={24} md={5}>
                            <Select
                              value={kind}
                              onChange={(v) => setKind(v)}
                              style={{ width: '100%' }}
                              size="large"
                              options={[
                                { value: 'schema', label: 'Schema' },
                                { value: 'mapping', label: 'Mapping' },
                                { value: 'rule', label: 'Rule' },
                              ]}
                            />
                          </Col>
                          <Col xs={24} md={7}>
                            <Input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="版本号，如 1.0.0" size="large" />
                          </Col>
                          <Col xs={24} md={12}>
                            <Space wrap>
                              <Button type="primary" onClick={onSavePackage} loading={loading} size="large">保存当前包</Button>
                              <Button onClick={onTriggerImport} size="large">导入 JSON</Button>
                              <Button onClick={onExportPayload} size="large">导出 JSON</Button>
                            </Space>
                          </Col>
                        </Row>
                        <input ref={fileInputRef} type="file" accept="application/json" style={{ display: 'none' }} onChange={onImportPayload} />
                        <TextArea value={payloadText} onChange={(e) => setPayloadText(e.target.value)} autoSize={{ minRows: 16, maxRows: 24 }} style={{ marginTop: 14, fontFamily: 'monospace' }} />
                      </Card>

                      <Card size="small" title="版本与发布" style={sectionCardStyle}>
                        <div style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                          <Text type="secondary">严格兼容发布</Text>
                          <Switch checked={strictCompatibility} onChange={setStrictCompatibility} />
                          <Text type="secondary">{strictCompatibility ? '发现破坏性变更时阻断' : '发现风险时只提示，不阻断'}</Text>
                        </div>
                        <Table<PackageItem>
                          rowKey={(r) => `${r.space_id}:${r.kind}:${r.version}`}
                          dataSource={packages}
                          pagination={{ pageSize: 8 }}
                          columns={[
                            { title: '类型', dataIndex: 'kind', width: 100 },
                            { title: '版本', dataIndex: 'version', width: 120 },
                            { title: '阶段', dataIndex: 'stage', width: 120, render: (stage: Stage) => <Tag color={stage === 'ga' ? 'green' : 'default'}>{stage}</Tag> },
                            { title: '提交人', dataIndex: 'created_by', width: 140 },
                            { title: '更新时间', dataIndex: 'updated_at', width: 180 },
                            {
                              title: '操作',
                              key: 'actions',
                              render: (_, row) => {
                                const allowedTargets = getAllowedReleaseTargets(row.stage);
                                return (
                                  <Space wrap>
                                    <Button size="small" disabled={!allowedTargets.includes('review')} onClick={() => void onRelease(row, 'review')}>评审</Button>
                                    <Button size="small" disabled={!allowedTargets.includes('staging')} onClick={() => void onRelease(row, 'staging')}>预发</Button>
                                    <Button size="small" type="primary" disabled={!allowedTargets.includes('ga')} onClick={() => void onRelease(row, 'ga')}>发布</Button>
                                    <Button size="small" onClick={() => void onRollback(row)}>回滚</Button>
                                    <Button size="small" danger disabled={!allowedTargets.includes('deprecated')} onClick={() => void onRelease(row, 'deprecated')}>废弃</Button>
                                  </Space>
                                );
                              },
                            },
                          ]}
                        />
                      </Card>
                    </Space>
                  ),
                },
                {
                  key: 'mapping',
                  label: '映射调试',
                  disabled: !selectedSpaceId,
                  children: (
                    <Card size="small" title="执行映射" style={sectionCardStyle}>
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <TextArea value={mappingInput} onChange={(e) => setMappingInput(e.target.value)} autoSize={{ minRows: 10, maxRows: 16 }} style={{ fontFamily: 'monospace' }} />
                        <Button type="primary" onClick={onRunMapping} loading={loading}>执行映射</Button>
                        <TextArea value={mappingResult} readOnly autoSize={{ minRows: 12, maxRows: 20 }} style={{ fontFamily: 'monospace' }} />
                      </Space>
                    </Card>
                  ),
                },
                {
                  key: 'rules',
                  label: '规则执行',
                  disabled: !selectedSpaceId,
                  children: (
                    <Card size="small" title="执行规则与解释" style={sectionCardStyle}>
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <TextArea value={ruleGraphInput} onChange={(e) => setRuleGraphInput(e.target.value)} autoSize={{ minRows: 10, maxRows: 16 }} style={{ fontFamily: 'monospace' }} />
                        <Space wrap>
                          <Button type="primary" onClick={onRunRules} loading={loading}>执行规则</Button>
                          <Button onClick={onExplain} disabled={!latestDecisionId} loading={loading}>查询解释</Button>
                          {latestDecisionId && <Tag color="blue">{latestDecisionId}</Tag>}
                        </Space>
                        <TextArea value={ruleResult} readOnly autoSize={{ minRows: 8, maxRows: 16 }} style={{ fontFamily: 'monospace' }} />
                        <TextArea value={explainResult} readOnly autoSize={{ minRows: 8, maxRows: 16 }} style={{ fontFamily: 'monospace' }} />
                      </Space>
                    </Card>
                  ),
                },
                {
                  key: 'governance',
                  label: '发布审计',
                  disabled: !selectedSpaceId,
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Card size="small" title="版本差异对比" style={sectionCardStyle}>
                        <Space style={{ marginBottom: 12 }} wrap>
                          <Input placeholder="from version" value={diffFromVersion} onChange={(e) => setDiffFromVersion(e.target.value)} style={{ width: 180 }} />
                          <Input placeholder="to version" value={diffToVersion} onChange={(e) => setDiffToVersion(e.target.value)} style={{ width: 180 }} />
                          <Button onClick={onDiffPackages} loading={loading}>对比版本</Button>
                        </Space>
                        <TextArea value={diffResult} readOnly autoSize={{ minRows: 6, maxRows: 12 }} style={{ fontFamily: 'monospace' }} />
                        {diffObj && (
                          <Alert
                            style={{ marginTop: 12, borderRadius: 12 }}
                            showIcon
                            type={(diffObj.breaking_changes || []).length > 0 ? 'warning' : 'success'}
                            message={(diffObj.breaking_changes || []).length > 0 ? '阻断告警：存在破坏性变更' : '兼容性通过：未发现阻断项'}
                          />
                        )}
                      </Card>

                      <Card size="small" title="审批流" style={sectionCardStyle}>
                        <Space style={{ marginBottom: 12 }} wrap>
                          <Input placeholder="目标版本，例如 1.0.0" value={approvalTargetVersion} onChange={(e) => setApprovalTargetVersion(e.target.value)} style={{ width: 180 }} />
                          <Select
                            value={approvalTargetStage}
                            onChange={(v) => setApprovalTargetStage(v)}
                            style={{ width: 140 }}
                            options={[
                              { value: 'staging', label: '预发审批' },
                              { value: 'ga', label: '正式审批' },
                            ]}
                          />
                          <Button type="primary" onClick={onSubmitApproval} loading={loading}>提交审批</Button>
                        </Space>
                        <Table<ApprovalItem>
                          rowKey={(r) => r.id}
                          dataSource={approvals}
                          pagination={{ pageSize: 8 }}
                          columns={[
                            { title: '时间', dataIndex: 'created_at', width: 180 },
                            { title: '类型', dataIndex: 'kind', width: 90 },
                            { title: '版本', dataIndex: 'version', width: 100 },
                            { title: '目标', dataIndex: 'requested_stage', width: 110 },
                            { title: '状态', dataIndex: 'status', width: 110, render: (status: ApprovalItem['status']) => <Tag color={status === 'approved' ? 'green' : status === 'rejected' ? 'red' : 'gold'}>{status}</Tag> },
                            { title: '申请人', dataIndex: 'requester_user_id', width: 140 },
                            { title: '审批人', dataIndex: 'reviewer_user_id', width: 140 },
                            {
                              title: '操作',
                              key: 'actions',
                              render: (_, row) =>
                                row.status === 'pending' ? (
                                  <Space>
                                    <Button size="small" type="primary" onClick={() => void onReviewApproval(row.id, true)}>批准</Button>
                                    <Button size="small" danger onClick={() => void onReviewApproval(row.id, false)}>拒绝</Button>
                                  </Space>
                                ) : (
                                  <Text type="secondary">已处理</Text>
                                ),
                            },
                          ]}
                        />
                      </Card>

                      <Card size="small" title="发布事件" style={sectionCardStyle}>
                        <Table<ReleaseEvent>
                          rowKey={(r) => r.id}
                          dataSource={events}
                          pagination={{ pageSize: 10 }}
                          columns={[
                            { title: '时间', dataIndex: 'created_at', width: 200 },
                            { title: '类型', dataIndex: 'kind', width: 90 },
                            { title: '版本', dataIndex: 'version', width: 110 },
                            { title: '流转', key: 'flow', width: 180, render: (_, r) => `${r.from_stage} -> ${r.to_stage}` },
                            { title: '操作人', dataIndex: 'actor_user_id', width: 130 },
                            {
                              title: '告警',
                              key: 'warnings',
                              render: (_, r) =>
                                r.warnings.length > 0 ? (
                                  <Space wrap>
                                    {r.warnings.map((w) => (
                                      <Tag key={w} color={w.includes('removes') ? 'red' : 'orange'}>
                                        {w}
                                      </Tag>
                                    ))}
                                  </Space>
                                ) : (
                                  <Text type="secondary">-</Text>
                                ),
                            },
                          ]}
                        />
                      </Card>
                    </Space>
                  ),
                },
              ]}
            />
          </Space>
        )}
      </div>
    </div>
  );
};

export default OntologyWorkbench;
