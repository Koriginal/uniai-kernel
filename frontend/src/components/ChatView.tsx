import React, { useRef, useEffect, useState } from 'react';
import { Typography, Avatar, Input, Empty, Space, Divider, Button, Tooltip, message, Tag, Drawer, Modal } from 'antd';
import { 
  AppstoreAddOutlined, CopyOutlined, SyncOutlined, PartitionOutlined, RobotOutlined, 
  UserOutlined, HistoryOutlined, PlusOutlined, EditOutlined, DeleteOutlined, LikeOutlined, 
  DislikeOutlined, BorderOutlined, ReloadOutlined, LikeFilled, DislikeFilled, SendOutlined,
  WarningOutlined, ScheduleOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Text } = Typography;
const MessageContent = React.lazy(() => import('./MarkdownMessage'));

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string | any[];
  timestamp: number;
  agentName?: string;
  images?: string[]; 
  feedback?: 'like' | 'dislike' | 'null';
  tool_calls?: { id: string; function: { name: string; arguments: string; }; }[];
  tool_runtime_events?: any[];
  ontology_runtime?: any;
  task_runtime?: any;
  task_evaluation?: any;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  tools?: string[];
  agent_type?: 'general' | 'tool' | 'ontology' | 'workflow';
  runtime_policy?: {
    allow_tools?: boolean;
    allow_web_search?: boolean;
    allow_swarm?: boolean;
    allow_canvas?: boolean;
    allow_ontology?: boolean;
    tool_call_mode?: string;
  };
  is_active: boolean;
  is_public: boolean;
  role: 'orchestrator' | 'expert';
  routing_keywords?: string[];
  handoff_strategy?: 'return' | 'end';
  ontology_config?: {
    enabled?: boolean;
    mode?: 'off' | 'auto' | 'required';
    space_id?: string | null;
    strict_rules?: boolean;
    explain_required?: boolean;
    fallback_when_unavailable?: string;
  };
  model_config_id: number;
  system_prompt?: string;
}

interface ChatViewProps {
  messages: Message[];
  currentSessionId?: string | null;
  loading: boolean;
  inputText: string;
  setInputText: (v: string) => void;
  currentAgent: Agent | null;
  enableMemory: boolean;
  setEnableMemory: (v: boolean) => void;
  enableSwarm: boolean;
  setEnableSwarm: (v: boolean) => void;
  onSend: () => void;
  onStop?: () => void;
  onDeleteMessage?: (id: string) => void;
  onEditMessage?: (id: string, content: string) => void;
  onFeedbackMessage?: (id: string, feedback: 'like' | 'dislike' | 'null') => void;
  onRegenerate?: () => void;
  pendingImages: string[];
  setPendingImages: (v: string[] | ((prev: string[]) => string[])) => void;
  onOpenCanvas?: (title: string, content: string, type: 'markdown' | 'code', language?: string, msgId?: string) => void;
  enableAutoCanvas?: boolean;
  setEnableAutoCanvas?: (v: boolean) => void;
  collaborationStatus?: { agentName?: string, content?: string, state: 'active' | 'completed' | null };
}

interface SessionRuntimeTrace {
  message_id: string;
  session_id?: string | null;
  agent_id?: string | null;
  created_at?: string;
  content_preview: string;
  summary: {
    has_ontology: boolean;
    ontology_status?: string | null;
    ontology_space_id?: string | null;
    ontology_space_name?: string | null;
    ontology_space_code?: string | null;
    risk_level?: string | null;
    tool_count: number;
    successful_tool_count: number;
    blocked_tool_count: number;
    failed_tool_count: number;
    task_status?: string | null;
    task_kind?: string | null;
    plan_status?: string | null;
    artifact_count?: number;
    repair_count?: number;
    pending_repair?: boolean;
    evaluation_check_count?: number;
    failed_check_count?: number;
    warning_check_count?: number;
    missing_requirement_count?: number;
  };
  ontology_runtime?: any;
  tool_runtime_events: any[];
  task_runtime?: any;
}

const buildLocalSessionRuntimeTraces = (messages: Message[]): SessionRuntimeTrace[] => {
  return messages
    .filter((item) => item.role === 'assistant' && (item.task_runtime || item.ontology_runtime || (item.tool_runtime_events || []).length > 0))
    .map((item) => {
      const ontology = item.ontology_runtime;
      const tools = item.tool_runtime_events || [];
      const taskRuntime = item.task_runtime || {};
      const taskFrame = taskRuntime.task_frame || {};
      const taskPlan = taskRuntime.execution_plan || {};
      const taskEvaluation = taskRuntime.task_evaluation || {};
      const evaluationChecks = Array.isArray(taskEvaluation.checks) ? taskEvaluation.checks : [];
      const missingRequirements = Array.isArray(taskEvaluation.missing_requirements) ? taskEvaluation.missing_requirements : [];
      const finalTools = tools.filter((event) => event && (!event.phase || event.phase === 'end'));
      return {
        message_id: item.id,
        created_at: item.timestamp ? new Date(item.timestamp).toISOString() : undefined,
        content_preview: typeof item.content === 'string' ? item.content.replace(/\s+/g, ' ').slice(0, 140) : '多模态消息',
        summary: {
          has_ontology: !!ontology,
          ontology_status: ontology?.status,
          ontology_space_id: ontology?.space_id,
          ontology_space_name: ontology?.space_name,
          ontology_space_code: ontology?.space_code,
          risk_level: ontology?.decision?.risk_level,
          tool_count: finalTools.length,
          successful_tool_count: finalTools.filter((event) => event.status === 'success').length,
          blocked_tool_count: finalTools.filter((event) => event.status === 'blocked').length,
          failed_tool_count: finalTools.filter((event) => event.status === 'error').length,
          task_status: taskEvaluation.status,
          task_kind: taskFrame.kind,
          plan_status: taskPlan.status,
          artifact_count: finalTools.filter((event) => event.artifact_id).length,
          repair_count: taskRuntime.task_repair_count || 0,
          pending_repair: !!taskRuntime.pending_repair,
          evaluation_check_count: evaluationChecks.length,
          failed_check_count: evaluationChecks.filter((check: any) => check.status === 'failed').length,
          warning_check_count: evaluationChecks.filter((check: any) => check.status === 'warning').length,
          missing_requirement_count: missingRequirements.length,
        },
        ontology_runtime: ontology,
        tool_runtime_events: tools,
        task_runtime: taskRuntime,
      };
    });
};

const buildSessionRuntimeReport = (traces: SessionRuntimeTrace[]): string => {
  const lines = [
    '# 会话运行轨迹报告',
    '',
    `生成时间：${new Date().toLocaleString()}`,
    `回答数量：${traces.length}`,
    '',
  ];
  traces.forEach((trace, index) => {
    const summary = trace.summary || {};
    const spaceLabel = summary.ontology_space_name || summary.ontology_space_code || summary.ontology_space_id || '未使用本体';
    lines.push(`## 回答 ${index + 1}`);
    if (trace.created_at) lines.push(`时间：${new Date(trace.created_at).toLocaleString()}`);
    lines.push(`本体空间：${spaceLabel}`);
    lines.push(`本体状态：${summary.ontology_status || (summary.has_ontology ? '已触发' : '未使用')}`);
    if (summary.task_kind || summary.task_status) {
      lines.push(`任务运行时：${summary.task_kind || '未知任务'} / ${summary.task_status || summary.plan_status || '未验收'}`);
    }
    if (summary.evaluation_check_count !== undefined) {
      lines.push(`验收检查：${summary.evaluation_check_count || 0} 项，失败 ${summary.failed_check_count || 0}，风险 ${summary.warning_check_count || 0}，缺口 ${summary.missing_requirement_count || 0}`);
    }
    if (trace.ontology_runtime?.trigger_reason) {
      lines.push(`触发判断：${trace.ontology_runtime.trigger_reason}`);
    }
    if (Array.isArray(trace.ontology_runtime?.trigger_signals) && trace.ontology_runtime.trigger_signals.length > 0) {
      lines.push(`触发信号：${trace.ontology_runtime.trigger_signals.join('，')}`);
    }
    lines.push(`风险等级：${summary.risk_level || '未执行'}`);
    lines.push(`工具：${summary.tool_count || 0} 次，成功 ${summary.successful_tool_count || 0}，拦截 ${summary.blocked_tool_count || 0}，失败 ${summary.failed_tool_count || 0}，产物 ${summary.artifact_count || 0}`);
    lines.push(`回答摘要：${trace.content_preview || '无'}`);
    lines.push('');
  });
  return lines.join('\n');
};

const statusLabelMap: Record<string, string> = {
  success: '已完成',
  mapped_only: '已映射',
  waiting_for_input: '等待输入',
  missing_mapping: '缺少映射',
  unavailable: '不可用',
  error: '执行异常',
};

const toolStatusMeta: Record<string, { color: string; label: string }> = {
  running: { color: 'processing', label: '运行中' },
  success: { color: 'success', label: '成功' },
  error: { color: 'error', label: '失败' },
  blocked: { color: 'warning', label: '已拦截' },
};

const taskStatusMeta: Record<string, { color: string; label: string }> = {
  passed: { color: 'success', label: '验收通过' },
  warning: { color: 'warning', label: '有风险' },
  failed: { color: 'error', label: '验收失败' },
  completed: { color: 'success', label: '已完成' },
  completed_with_warnings: { color: 'warning', label: '有警告' },
  repairing: { color: 'processing', label: '修复中' },
};

const openToolArtifact = async (artifactId: string) => {
  try {
    const token = localStorage.getItem('token');
    const res = await axios.get(`/api/v1/messages/artifacts/${artifactId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const artifact = res.data || {};
    const metadata = artifact.metadata || {};
    Modal.info({
      title: `${artifact.tool_name || '工具'} 产物`,
      width: 760,
      content: (
        <div style={{ display: 'grid', gap: 10 }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {artifact.content_type && <Tag>{artifact.content_type}</Tag>}
            {artifact.size_bytes !== undefined && <Tag>{artifact.size_bytes} bytes</Tag>}
            {artifact.tool_call_id && <Tag color="blue">{artifact.tool_call_id}</Tag>}
          </div>
          {Object.keys(metadata).length > 0 && (
            <pre style={{
              margin: 0,
              maxHeight: 120,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              background: '#f8fafc',
              border: '1px solid #e5e7eb',
              borderRadius: 8,
              padding: 10,
              fontSize: 12,
            }}>
              {JSON.stringify(metadata, null, 2)}
            </pre>
          )}
          <pre style={{
            margin: 0,
            maxHeight: '52vh',
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            background: '#f8fafc',
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            padding: 12,
            fontSize: 12,
          }}>
            {typeof artifact.content === 'string' ? artifact.content : JSON.stringify(artifact.content, null, 2)}
          </pre>
        </div>
      ),
    });
  } catch (err) {
    console.error('Failed to load tool artifact', err);
    message.error('工具产物读取失败');
  }
};

const TaskRuntimePanel: React.FC<{ runtime?: any }> = ({ runtime }) => {
  if (!runtime) return null;
  const frame = runtime.task_frame || {};
  const plan = runtime.execution_plan || {};
  const evaluation = runtime.task_evaluation || {};
  const artifacts = Array.isArray(runtime.execution_artifacts) ? runtime.execution_artifacts : [];
  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  const statusKey = evaluation.status || plan.evaluation_status || plan.status;
  const meta = taskStatusMeta[statusKey] || { color: 'default', label: statusKey || '未验收' };
  const failedChecks = (evaluation.checks || []).filter((check: any) => check.status === 'failed');
  const warningChecks = (evaluation.checks || []).filter((check: any) => check.status === 'warning');

  return (
    <div style={{
      border: '1px solid #d9e8ff',
      background: '#f8fbff',
      borderRadius: 12,
      padding: '12px 14px',
      marginBottom: 12,
      color: '#111827'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <Space size={8} wrap>
          <ScheduleOutlined style={{ color: '#1677ff' }} />
          <Text strong>Agent Runtime</Text>
          {frame.kind && <Tag color="blue">{frame.kind}</Tag>}
          {frame.application_id && <Tag color="purple">应用 {frame.application_id}</Tag>}
          {frame.scenario_type && <Tag>{frame.scenario_type}</Tag>}
          <Tag color={meta.color}>{meta.label}</Tag>
          {runtime.task_repair_count > 0 && <Tag color="purple">修复 {runtime.task_repair_count}</Tag>}
        </Space>
        {plan.current_step && <Text type="secondary" style={{ fontSize: 12 }}>当前步骤：{plan.current_step}</Text>}
      </div>

      {frame.user_goal && (
        <div style={{ marginTop: 8, color: '#475569', fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          目标：{frame.user_goal}
        </div>
      )}

      {steps.length > 0 && (
        <div style={{ display: 'grid', gap: 6, marginTop: 10 }}>
          {steps.map((step: any, index: number) => {
            const stepMeta = taskStatusMeta[step.status] || {
              color: step.status === 'in_progress' ? 'processing' : 'default',
              label: step.status || 'pending'
            };
            return (
              <div key={step.id || index} style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 1fr) auto',
                gap: 8,
                alignItems: 'center',
                background: '#fff',
                border: '1px solid #e5eefb',
                borderRadius: 10,
                padding: '7px 9px'
              }}>
                <div style={{ minWidth: 0 }}>
                  <Text strong style={{ fontSize: 13 }}>{index + 1}. {step.id}</Text>
                  <div style={{ color: '#64748b', fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{step.title}</div>
                </div>
                <Space size={4}>
                  <Tag>{step.owner}</Tag>
                  <Tag color={stepMeta.color}>{stepMeta.label}</Tag>
                </Space>
              </div>
            );
          })}
        </div>
      )}

      {(failedChecks.length > 0 || warningChecks.length > 0 || artifacts.length > 0) && (
        <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {failedChecks.length > 0 && <Tag color="error" icon={<WarningOutlined />}>失败检查 {failedChecks.length}</Tag>}
          {warningChecks.length > 0 && <Tag color="warning">风险检查 {warningChecks.length}</Tag>}
          {artifacts.length > 0 && <Tag color="cyan">产物 {artifacts.length}</Tag>}
        </div>
      )}
    </div>
  );
};

const RuntimeChecksPanel: React.FC<{ runtime?: any; tools?: any[] }> = ({ runtime, tools }) => {
  const plan = runtime?.execution_plan || {};
  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  const evaluation = runtime?.task_evaluation || {};
  const checks = Array.isArray(evaluation.checks) ? evaluation.checks : [];
  const missing = Array.isArray(evaluation.missing_requirements) ? evaluation.missing_requirements : [];
  const finalTools = (tools || []).filter((event) => event && (!event.phase || event.phase === 'end'));
  if (steps.length === 0 && checks.length === 0 && finalTools.length === 0) return null;

  return (
    <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
      {checks.length > 0 && (
        <div style={{ border: '1px solid #eef2f7', borderRadius: 10, padding: '8px 10px', background: '#fbfdff' }}>
          <Space size={6} wrap>
            <Text strong style={{ fontSize: 12 }}>验收检查</Text>
            <Tag color={taskStatusMeta[evaluation.status]?.color || 'default'}>{evaluation.status || 'unknown'}</Tag>
            {runtime?.task_repair_count > 0 && <Tag color="purple">修复 {runtime.task_repair_count}</Tag>}
            {missing.length > 0 && <Tag color="error">缺口 {missing.length}</Tag>}
          </Space>
          <div style={{ display: 'grid', gap: 5, marginTop: 7 }}>
            {checks.slice(0, 5).map((check: any, idx: number) => (
              <div key={check.id || idx} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                <Text style={{ fontSize: 12 }}>{check.id || `check_${idx + 1}`}</Text>
                <Tag color={taskStatusMeta[check.status]?.color || (check.status === 'warning' ? 'warning' : 'default')} style={{ marginInlineEnd: 0 }}>
                  {check.status || 'unknown'}
                </Tag>
              </div>
            ))}
          </div>
        </div>
      )}
      {steps.length > 0 && (
        <div style={{ border: '1px solid #eef2f7', borderRadius: 10, padding: '8px 10px', background: '#fff' }}>
          <Text strong style={{ fontSize: 12 }}>计划步骤</Text>
          <div style={{ display: 'grid', gap: 6, marginTop: 7 }}>
            {steps.slice(0, 4).map((step: any, idx: number) => {
              const stepTools = finalTools.filter((event) => event.plan_step_id === step.id);
              const artifacts = stepTools.filter((event) => event.artifact_id);
              return (
                <div key={step.id || idx} style={{ border: '1px solid #f1f5f9', borderRadius: 8, padding: '6px 7px', background: '#f8fafc' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <Text style={{ fontSize: 12 }}>{idx + 1}. {step.id || 'step'}</Text>
                    <Tag color={taskStatusMeta[step.status]?.color || 'default'} style={{ marginInlineEnd: 0 }}>{step.status || 'pending'}</Tag>
                  </div>
                  <Space size={[4, 4]} wrap style={{ marginTop: 4 }}>
                    {step.owner && <Tag>{step.owner}</Tag>}
                    {stepTools.length > 0 && <Tag color="purple">工具 {stepTools.length}</Tag>}
                    {artifacts.length > 0 && <Tag color="cyan">产物 {artifacts.length}</Tag>}
                  </Space>
                  {artifacts.length > 0 && (
                    <div style={{ display: 'grid', gap: 5, marginTop: 6 }}>
                      {artifacts.slice(0, 3).map((event: any, artifactIndex: number) => (
                        <div key={event.artifact_id || artifactIndex} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>{event.tool_label || event.tool_name || '工具产物'}</Text>
                          <Button size="small" onClick={() => openToolArtifact(event.artifact_id)}>
                            查看产物
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

const ExecutionTracePanel: React.FC<{ ontology?: any; tools?: any[]; taskRuntime?: any }> = ({ ontology, tools, taskRuntime }) => {
  const toolEvents = (tools || []).filter(Boolean);
  if (!taskRuntime && !ontology && toolEvents.length === 0) return null;

  const mapping = ontology?.mapping || {};
  const decision = ontology?.decision || {};
  const plan = ontology?.action_plan || {};
  const execution = ontology?.action_execution || {};
  const spaceLabel = ontology?.space_name || ontology?.space_code || ontology?.space_id || '未选择空间';
  const ontologyStatus = ontology ? (statusLabelMap[ontology.status] || ontology.status || '已触发') : '未介入';
  const ontologyRisk = decision.risk_level || '未执行';
  const triggerReason = ontology?.trigger_reason || (ontology ? '本体运行时已记录，但未提供触发原因' : '');
  const triggerSignals: string[] = Array.isArray(ontology?.trigger_signals) ? ontology.trigger_signals : [];
  const successfulTools = toolEvents.filter(event => event.status === 'success').length;
  const blockedTools = toolEvents.filter(event => event.status === 'blocked').length;
  const failedTools = toolEvents.filter(event => event.status === 'error').length;

  return (
    <div style={{
      border: '1px solid #dbe3ef',
      background: '#fbfdff',
      borderRadius: 12,
      padding: '12px 14px',
      marginBottom: 12,
      color: '#111827'
    }}>
      <TaskRuntimePanel runtime={taskRuntime} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Space size={8} wrap>
          <PartitionOutlined style={{ color: '#1677ff' }} />
          <Text strong>执行轨迹</Text>
          {ontology && <Tag color="blue">本体：{ontologyStatus}</Tag>}
          {toolEvents.length > 0 && <Tag>工具 {toolEvents.length}</Tag>}
          {blockedTools > 0 && <Tag color="warning">拦截 {blockedTools}</Tag>}
          {failedTools > 0 && <Tag color="error">失败 {failedTools}</Tag>}
        </Space>
        {ontology && <Text type="secondary" style={{ fontSize: 12 }}>空间：{spaceLabel}</Text>}
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(132px, 1fr))',
        gap: 8,
        marginTop: 10
      }}>
        {ontology && (
          <>
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '8px 10px' }}>
              <div style={{ color: '#64748b', fontSize: 12 }}>本体映射</div>
              <div style={{ fontWeight: 700, marginTop: 2 }}>{mapping.entity_count || 0} 对象 / {mapping.relation_count || 0} 关系</div>
            </div>
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '8px 10px' }}>
              <div style={{ color: '#64748b', fontSize: 12 }}>规则风险</div>
              <div style={{ fontWeight: 700, marginTop: 2 }}>{ontologyRisk}</div>
            </div>
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '8px 10px' }}>
              <div style={{ color: '#64748b', fontSize: 12 }}>补数计划</div>
              <div style={{ fontWeight: 700, marginTop: 2 }}>
                {typeof plan.missing_field_count === 'number' ? `缺失 ${plan.missing_field_count}` : '无缺失'}
                {execution.applied_patch_count ? ` · 已补 ${execution.applied_patch_count}` : ''}
              </div>
            </div>
          </>
        )}
        {toolEvents.length > 0 && (
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '8px 10px' }}>
            <div style={{ color: '#64748b', fontSize: 12 }}>工具执行</div>
            <div style={{ fontWeight: 700, marginTop: 2 }}>{successfulTools} 成功 / {blockedTools} 拦截 / {failedTools} 失败</div>
          </div>
        )}
      </div>

      {ontology && (
        <div style={{ marginTop: 8, color: '#475569', fontSize: 13 }}>
          {triggerReason}
          {triggerSignals.length > 0 && (
            <div style={{ marginTop: 6 }}>
              {triggerSignals.map((signal) => (
                <Tag key={signal} color="geekblue" style={{ marginBottom: 4 }}>{signal}</Tag>
              ))}
            </div>
          )}
        </div>
      )}

      {toolEvents.length > 0 && (
        <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
          {toolEvents.map((event, index) => {
            const meta = toolStatusMeta[event.status] || { color: 'default', label: event.status || '未知' };
            const result = event.result || {};
            return (
              <div key={event.tool_call_id || `${event.tool_name}-${index}`} style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 10,
                alignItems: 'start',
                border: '1px solid #eef2f7',
                background: '#fff',
                borderRadius: 10,
                padding: '8px 10px'
              }}>
                <div>
                  <Space size={6} wrap>
                    <Text strong>{event.tool_label || event.tool_name || '工具'}</Text>
                    <Tag color={meta.color}>{meta.label}</Tag>
                  </Space>
                  <div style={{ marginTop: 4 }}>
                    {event.category && <Tag>{event.category}</Tag>}
                    {event.plan_step_id && <Tag color="blue">步骤 {event.plan_step_id}</Tag>}
                    {event.policy_decision && (
                      <Tag color={event.policy_decision === 'deny' ? 'error' : event.policy_decision === 'warn' ? 'warning' : 'green'}>
                        策略 {event.policy_decision}
                      </Tag>
                    )}
                    {event.duration_ms !== undefined && <Text type="secondary" style={{ fontSize: 12 }}>{event.duration_ms} ms</Text>}
                  </div>
                  {event.policy_reason && (
                    <div style={{ marginTop: 4, color: '#64748b', fontSize: 12 }}>
                      {event.policy_reason}
                    </div>
                  )}
                  {event.artifact_id && (
                    <Button size="small" style={{ marginTop: 6 }} onClick={() => openToolArtifact(event.artifact_id)}>
                      查看产物
                    </Button>
                  )}
                </div>
                <div style={{ minWidth: 0 }}>
                  {event.error ? (
                    <div style={{ color: '#b42318', fontSize: 13 }}>{event.error}</div>
                  ) : (
                    <div style={{
                      color: '#475569',
                      fontSize: 12,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: 88,
                      overflow: 'auto'
                    }}>
                      {result.preview || '已完成，无结果摘要'}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

const ChatView: React.FC<ChatViewProps> = (props) => {
  const { messages, currentSessionId, loading, collaborationStatus, inputText, setInputText, currentAgent, enableMemory, setEnableMemory, enableSwarm, setEnableSwarm, onSend, onStop, onDeleteMessage, onEditMessage, onFeedbackMessage, onRegenerate, pendingImages, setPendingImages, onOpenCanvas, enableAutoCanvas, setEnableAutoCanvas } = props;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');
  const [hoveredMessageId, setHoveredMessageId] = useState<string | null>(null);
  const [isIME, setIsIME] = useState(false);
  const [runtimeDrawerOpen, setRuntimeDrawerOpen] = useState(false);
  const [runtimeTraceLoading, setRuntimeTraceLoading] = useState(false);
  const [sessionRuntimeTraces, setSessionRuntimeTraces] = useState<SessionRuntimeTrace[]>([]);
  

  const groupMessagesIntoTurns = (msgs: Message[]) => {
    const turns: { id: string, role: string, messages: Message[] }[] = [];
    msgs.forEach((m, idx) => {
      if (idx > 0 && m.role === msgs[idx-1].role && m.role === 'assistant') turns[turns.length - 1].messages.push(m);
      else turns.push({ id: m.id || `turn-${idx}`, role: m.role, messages: [m] });
    });
    return turns;
  };
  const messageTurns = groupMessagesIntoTurns(messages);
  const localRuntimeTraces = buildLocalSessionRuntimeTraces(messages);
  const runtimeTraceCount = localRuntimeTraces.length;

  const openSessionRuntimeTrace = async () => {
    setRuntimeDrawerOpen(true);
    setRuntimeTraceLoading(true);
    const fallbackTraces = buildLocalSessionRuntimeTraces(messages);
    try {
      if (!currentSessionId) {
        setSessionRuntimeTraces(fallbackTraces);
        return;
      }
      const token = localStorage.getItem('token');
      const res = await axios.get(`/api/v1/chat-sessions/${currentSessionId}/runtime-traces`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      setSessionRuntimeTraces(res.data?.items || fallbackTraces);
    } catch (err) {
      console.error('Failed to load session runtime traces', err);
      setSessionRuntimeTraces(fallbackTraces);
      message.warning('会话运行轨迹接口暂不可用，已显示当前页面缓存轨迹');
    } finally {
      setRuntimeTraceLoading(false);
    }
  };

  const copySessionRuntimeReport = async () => {
    const traces = sessionRuntimeTraces.length > 0 ? sessionRuntimeTraces : buildLocalSessionRuntimeTraces(messages);
    if (traces.length === 0) {
      message.info('当前会话还没有可复制的运行轨迹');
      return;
    }
    try {
      if (currentSessionId) {
        const token = localStorage.getItem('token');
        const res = await axios.get(`/api/v1/chat-sessions/${currentSessionId}/runtime-report?format=markdown`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          responseType: 'text',
        });
        await navigator.clipboard.writeText(res.data || buildSessionRuntimeReport(traces));
        message.success('会话运行轨迹报告已复制');
        return;
      }
    } catch (err) {
      console.warn('Failed to export server runtime report, fallback to local report', err);
    }
    await navigator.clipboard.writeText(buildSessionRuntimeReport(traces));
    message.success('会话运行轨迹报告已复制（本地快照）');
  };

  useEffect(() => {
    if (scrollRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
        if (scrollHeight - scrollTop - clientHeight < 200) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);


  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#fff', position: 'relative' }}>
      {runtimeTraceCount > 0 && (
        <div style={{ position: 'absolute', right: 18, top: 14, zIndex: 3 }}>
          <Button size="small" icon={<HistoryOutlined />} onClick={openSessionRuntimeTrace}>
            会话运行轨迹 {runtimeTraceCount}
          </Button>
        </div>
      )}
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '24px 0', scrollBehavior: 'smooth' }}>
        <div style={{ maxWidth: '900px', margin: '0 auto', padding: '0 24px' }}>
          {messages.length === 0 ? (
            <div style={{ height: '70vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Empty description="UniAI 协作引擎已就绪" /></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {messageTurns.map((turn, tIdx) => {
                const isUser = turn.role === 'user';
                const isAssistant = turn.role === 'assistant';
                const isSystem = turn.role === 'system';
                const isLastTurn = tIdx === messageTurns.length - 1;

                return (
                  <div key={turn.id} style={{ marginBottom: 32, width: '100%', position: 'relative' }}>
                    {isSystem ? (
                      <div style={{ width: '100%', textAlign: 'center', padding: '6px 16px', fontSize: '12px', color: 'rgba(0,0,0,0.45)', background: '#fafafa', borderRadius: '4px' }}>{turn.messages.map(m => (typeof m.content === 'string' ? m.content : '')).join('\n')}</div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', gap: '16px', maxWidth: '98%', position: 'relative' }}>
                        <div style={{ flexShrink: 0, width: 34 }}><Avatar size={34} icon={isUser ? <UserOutlined /> : <RobotOutlined />} style={{ background: isUser ? '#1890ff' : '#fff', color: isUser ? '#fff' : '#1890ff', border: '1px solid #eee' }} /></div>
                        
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', flex: 1, minWidth: 0 }}>
                          <div style={{ position: 'relative', width: isAssistant ? '100%' : 'auto' }}>
                            {turn.messages.map((m, mIdx) => {
                               const isLastInTurn = mIdx === turn.messages.length - 1;
                               const isMsgGenerating = loading && isLastTurn && isLastInTurn;
                               
                               return (
                                  <div key={m.id || m.timestamp} 
                                       onMouseEnter={() => setHoveredMessageId(m.id)} 
                                       onMouseLeave={() => setHoveredMessageId(null)} 
                                       style={{ marginBottom: isLastInTurn ? 0 : 20, display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', width: '100%' }}>
                                      
                                      {/* [BUBBLE] 仅包裹消息内容与图片 */}
                                      <div style={{
                                        padding: '12px 16px', 
                                        background: isUser ? '#1890ff' : '#fff', 
                                        color: isUser ? '#fff' : 'rgba(0,0,0,0.85)',
                                        borderRadius: '16px', 
                                        borderTopRightRadius: (isUser && isLastInTurn) ? '2px' : '16px', 
                                        borderTopLeftRadius: (isAssistant && isLastInTurn) ? '2px' : '16px',
                                        fontSize: '15px', 
                                        lineHeight: '1.7', 
                                        boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                                        border: isUser ? 'none' : '1px solid #f0f0f0', 
                                        position: 'relative', 
                                        width: isUser ? 'fit-content' : '100%', 
                                        maxWidth: '100%',
                                        wordBreak: 'break-word',
                                        overflowWrap: 'break-word',
                                        boxSizing: 'border-box'
                                      }}>
                                        {m.agentName && isAssistant && turn.messages.length > 1 && (
                                          <div style={{ fontSize: '11px', fontWeight: 600, color: isUser ? '#fff' : '#1890ff', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6, opacity: isUser ? 0.9 : 1 }}>
                                            <PartitionOutlined style={{ fontSize: 13 }} /><span>{m.agentName}</span>
                                          </div>
                                        )}
                                        {editingId === m.id ? (
                                          <div style={{ minWidth: '400px' }}><Input.TextArea autoSize={{ minRows: 2 }} value={editingText} onChange={e => setEditingText(e.target.value)} style={{ marginBottom: 12, borderRadius: 8 }} /><Space><Button size="small" type="primary" onClick={() => { onEditMessage?.(m.id, editingText); setEditingId(null); }}>保存</Button><Button size="small" onClick={() => setEditingId(null)}>取消</Button></Space></div>
                                        ) : (
                                          <>
                                            {isAssistant && (m.task_runtime || m.ontology_runtime || (m.tool_runtime_events && m.tool_runtime_events.length > 0)) && (
                                              <ExecutionTracePanel ontology={m.ontology_runtime} tools={m.tool_runtime_events} taskRuntime={m.task_runtime} />
                                            )}
                                            <React.Suspense fallback={<div style={{ color: '#64748b', fontSize: 13 }}>正在加载消息渲染器...</div>}>
                                              <MessageContent
                                                content={m.content}
                                                loading={isMsgGenerating}
                                                onOpenCanvas={onOpenCanvas}
                                                collaborationStatus={collaborationStatus}
                                              />
                                            </React.Suspense>
                                          </>
                                        )}
                                        {m.images && m.images.length > 0 && (
                                            <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                                                {m.images.map((img, idx) => (<img key={idx} src={img} alt="msg-img" style={{ maxWidth: '100%', borderRadius: 8, maxHeight: 400, border: '1px solid #f0f0f0' }} />))}
                                            </div>
                                        )}
                                      </div>

                                      {/* [ACTIONS] 彻底置于气泡之外 */}
                                      {hoveredMessageId === m.id && !editingId && !loading && (
                                          <div style={{ 
                                              marginTop: 6,
                                              display: 'flex',
                                              justifyContent: isUser ? 'flex-end' : 'flex-start',
                                              alignItems: 'center',
                                              width: '100%',
                                              animation: 'fadeIn 0.2s ease-in-out'
                                          }}>
                                              <div style={{ 
                                                  padding: '2px 8px', 
                                                  background: 'rgba(255, 255, 255, 0.8)', 
                                                  backdropFilter: 'blur(12px)',
                                                  borderRadius: '12px', 
                                                  border: '1px solid #f0f0f0', 
                                                  display: 'flex', 
                                                  gap: 6, 
                                                  alignItems: 'center',
                                                  boxShadow: '0 2px 10px rgba(0,0,0,0.05)'
                                              }} className="message-action-bar">
                                                  {isUser ? (
                                                    <>
                                                      <Tooltip title="复制内容"><CopyOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => { navigator.clipboard.writeText(typeof m.content === 'string' ? m.content : ""); message.success('已复制到剪贴板'); }} /></Tooltip>
                                                      <Tooltip title="编辑"><EditOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => { setEditingId(m.id); setEditingText(typeof m.content === 'string' ? m.content : ""); }} /></Tooltip>
                                                      <div style={{ width: 1, height: 10, background: '#eee', margin: '0 2px' }} />
                                                      <Tooltip title="撤回"><DeleteOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#ff4d4f' }} onClick={() => onDeleteMessage?.(m.id)} /></Tooltip>
                                                    </>
                                                  ) : (
                                                    <>
                                                      <Tooltip title="复制结果"><CopyOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => { navigator.clipboard.writeText(typeof m.content === 'string' ? m.content : ""); message.success('已复制到剪贴板'); }} /></Tooltip>
                                                      <Tooltip title="重新生成"><ReloadOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => onRegenerate?.()} /></Tooltip>
                                                      <Tooltip title="投至看板"><AppstoreAddOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#1890ff' }} onClick={() => { const text = typeof m.content === 'string' ? m.content : JSON.stringify(m.content); onOpenCanvas?.('快照', text, 'markdown'); }} /></Tooltip>
                                                      <div style={{ width: 1, height: 10, background: '#eee', margin: '0 2px' }} />
                                                      {m.feedback === 'like' ? <LikeFilled style={{ fontSize: 12, color: '#1890ff', cursor: 'pointer' }} onClick={() => onFeedbackMessage?.(m.id, 'null')} /> : <LikeOutlined style={{ fontSize: 12, color: '#999', cursor: 'pointer' }} onClick={() => onFeedbackMessage?.(m.id, 'like')} />}
                                                      {m.feedback === 'dislike' ? <DislikeFilled style={{ fontSize: 12, color: '#ff4d4f', cursor: 'pointer' }} onClick={() => onFeedbackMessage?.(m.id, 'null')} /> : <DislikeOutlined style={{ fontSize: 12, color: '#999', cursor: 'pointer' }} onClick={() => onFeedbackMessage?.(m.id, 'dislike')} />}
                                                      <div style={{ width: 1, height: 10, background: '#eee', margin: '0 2px' }} />
                                                      <Tooltip title="清除消息"><DeleteOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => onDeleteMessage?.(m.id)} /></Tooltip>
                                                    </>
                                                  )}
                                              </div>
                                          </div>
                                      )}
                                  </div>
                               );
                            })}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {loading && collaborationStatus?.state === 'active' && (
              <div style={{ padding: '0 54px', display: 'flex', gap: 12, alignItems: 'center', marginTop: -16, marginBottom: 24 }}>
                  <SyncOutlined spin style={{ color: '#52c41a' }} />
                  <Text style={{ fontSize: '14px', color: '#389e0d', fontWeight: 500 }}>
                    {collaborationStatus.agentName} {collaborationStatus.content || '正在深入协作中...'}
                  </Text>
              </div>
          )}
        </div>
      </div>

      <div style={{ padding: '24px', background: '#fff', borderTop: '1px solid #f0f0f0' }}>
        <div style={{ maxWidth: '900px', margin: '0 auto' }}>
          {pendingImages.length > 0 && (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
                {pendingImages.map((img, idx) => (
                    <div key={idx} style={{ position: 'relative' }}>
                        <img src={img} style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 8, border: '1px solid #eee' }} />
                        <div onClick={() => setPendingImages(prev => prev.filter((_, i) => i !== idx))} style={{ position: 'absolute', top: -8, right: -8, background: '#ff4d4f', color: '#fff', borderRadius: '50%', width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontSize: 10 }}>✕</div>
                    </div>
                ))}
            </div>
          )}
          
          <div style={{ display: 'flex', gap: '16px', marginBottom: '12px' }}>
            <Space size={0} split={<Divider type="vertical" />}>
                <Button type="text" icon={<HistoryOutlined />} size="small" onClick={() => setEnableMemory(!enableMemory)} style={{ color: enableMemory ? '#1890ff' : '#999' }}>长效记忆</Button>
                <Button type="text" icon={<PartitionOutlined />} size="small" onClick={() => setEnableSwarm(!enableSwarm)} style={{ color: enableSwarm ? '#52c41a' : '#999' }}>Swarm 协作</Button>
                <Button type="text" icon={<AppstoreAddOutlined />} size="small" onClick={() => setEnableAutoCanvas?.(!enableAutoCanvas)} style={{ color: enableAutoCanvas ? '#eb2f96' : '#999' }}>自动看板</Button>
            </Space>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#f9f9f9', border: '1px solid #e8e8e8', borderRadius: '24px', padding: '4px 12px' }}>
            <Button type="text" shape="circle" icon={<PlusOutlined style={{ fontSize: 20, color: '#999' }} />} onClick={() => document.getElementById('img-upload')?.click()} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, flexShrink: 0 }} />
            <input type="file" id="img-upload" style={{ display: 'none' }} accept="image/*" onChange={(e) => { const file = e.target.files?.[0]; if (file) { const reader = new FileReader(); reader.onload = (ev) => setPendingImages(prev => [...prev, ev.target?.result as string]); reader.readAsDataURL(file); } }} />
            <Input.TextArea placeholder={currentAgent ? `向 ${currentAgent.name} 发送指令...` : "请先选择一个专家"} autoSize={{ minRows: 1, maxRows: 12 }} variant="borderless" style={{ flex: 1, padding: '8px 0', fontSize: '15px', lineHeight: '20px' }} value={inputText} onChange={e => setInputText(e.target.value)} onCompositionStart={() => setIsIME(true)} onCompositionEnd={() => setIsIME(false)} onKeyDown={(e) => { if (e.key === 'Enter' && !isIME && !e.shiftKey) { e.preventDefault(); onSend(); } }} />
            <div style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                {loading ? <Button type="primary" shape="circle" danger icon={<BorderOutlined style={{ fontSize: 10 }} />} onClick={onStop} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32 }} /> : <Button type="primary" shape="circle" icon={<SendOutlined style={{ fontSize: 16 }} />} onClick={onSend} disabled={!currentAgent || (!inputText.trim() && pendingImages.length === 0)} style={{ width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }} />}
            </div>
          </div>
        </div>
      </div>

      <Drawer
        title="会话运行轨迹"
        placement="right"
        width={620}
        open={runtimeDrawerOpen}
        onClose={() => setRuntimeDrawerOpen(false)}
        extra={<Button size="small" onClick={copySessionRuntimeReport}>复制报告</Button>}
      >
        {runtimeTraceLoading ? (
          <div style={{ color: '#64748b' }}>正在读取会话轨迹...</div>
        ) : sessionRuntimeTraces.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前会话还没有任务、本体或工具运行轨迹" />
        ) : (
          <div style={{ display: 'grid', gap: 12 }}>
            {sessionRuntimeTraces.map((trace, index) => {
              const summary = trace.summary || {};
              const spaceLabel = summary.ontology_space_name || summary.ontology_space_code || summary.ontology_space_id || '未使用本体';
              const risk = summary.risk_level || '未执行';
              return (
                <div key={trace.message_id || index} style={{ border: '1px solid #e5e7eb', borderRadius: 12, padding: 12, background: '#fff' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                    <Space size={6} wrap>
                      <Tag color="blue">回答 {index + 1}</Tag>
                      {summary.has_ontology ? (
                        <Tag color={summary.ontology_status === 'success' ? 'green' : 'orange'}>
                          本体 {statusLabelMap[summary.ontology_status || ''] || summary.ontology_status || '已触发'}
                        </Tag>
                      ) : (
                        <Tag>未使用本体</Tag>
                      )}
                      {(summary.task_kind || summary.task_status || summary.plan_status) && (
                        <Tag color={summary.task_status === 'passed' ? 'green' : 'blue'}>
                          任务 {summary.task_kind || 'general'} / {summary.task_status || summary.plan_status || 'planned'}
                        </Tag>
                      )}
                      {(summary.tool_count || 0) > 0 && <Tag>工具 {summary.tool_count}</Tag>}
                    </Space>
                    {trace.created_at && <Text type="secondary" style={{ fontSize: 12 }}>{new Date(trace.created_at).toLocaleString()}</Text>}
                  </div>
                  <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8 }}>
                    <div style={{ background: '#f8fafc', border: '1px solid #edf2f7', borderRadius: 10, padding: '8px 10px' }}>
                      <div style={{ color: '#64748b', fontSize: 12 }}>任务类型</div>
                      <div style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{summary.task_kind || '未记录'}</div>
                    </div>
                    <div style={{ background: '#f8fafc', border: '1px solid #edf2f7', borderRadius: 10, padding: '8px 10px' }}>
                      <div style={{ color: '#64748b', fontSize: 12 }}>本体空间</div>
                      <div style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{spaceLabel}</div>
                    </div>
                    <div style={{ background: '#f8fafc', border: '1px solid #edf2f7', borderRadius: 10, padding: '8px 10px' }}>
                      <div style={{ color: '#64748b', fontSize: 12 }}>风险等级</div>
                      <div style={{ fontWeight: 700 }}>{risk}</div>
                    </div>
                    <div style={{ background: '#f8fafc', border: '1px solid #edf2f7', borderRadius: 10, padding: '8px 10px' }}>
                      <div style={{ color: '#64748b', fontSize: 12 }}>工具结果</div>
                      <div style={{ fontWeight: 700 }}>
                        {summary.successful_tool_count || 0} 成功 / {summary.blocked_tool_count || 0} 拦截 / {summary.failed_tool_count || 0} 失败
                      </div>
                    </div>
                    <div style={{ background: '#f8fafc', border: '1px solid #edf2f7', borderRadius: 10, padding: '8px 10px' }}>
                      <div style={{ color: '#64748b', fontSize: 12 }}>验收与产物</div>
                      <div style={{ fontWeight: 700 }}>
                        {summary.evaluation_check_count || 0} 检查 / {summary.missing_requirement_count || 0} 缺口 / {summary.artifact_count || 0} 产物
                      </div>
                    </div>
                  </div>
                  <RuntimeChecksPanel runtime={trace.task_runtime} tools={trace.tool_runtime_events} />
                  <div style={{ marginTop: 10, color: '#334155', lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {trace.ontology_runtime?.trigger_reason && (
                      <div style={{ marginBottom: 8, color: '#475569' }}>
                        触发判断：{trace.ontology_runtime.trigger_reason}
                      </div>
                    )}
                    {Array.isArray(trace.ontology_runtime?.trigger_signals) && trace.ontology_runtime.trigger_signals.length > 0 && (
                      <div style={{ marginBottom: 8 }}>
                        {trace.ontology_runtime.trigger_signals.map((signal: string) => (
                          <Tag key={signal} color="geekblue" style={{ marginBottom: 4 }}>{signal}</Tag>
                        ))}
                      </div>
                    )}
                    {trace.content_preview || '无回答摘要'}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default ChatView;
