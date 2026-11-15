import axios from 'axios'

export type User = { id: number; email: string; role: 'admin' | 'engineer' | 'viewer'; created_at: string }
export type TokenResponse = { access_token: string; token_type: 'bearer'; user: User }
export type Project = { id: number; owner_id: number; name: string; source_system: string; target_system: string; created_at: string }
export type NewProject = { name: string; source_system: string; target_system: string }
export type Dashboard = {
  project: Project; total_mappings: number; parsed: number; converted: number; verified: number; failing: number;
  converted_percent: number; verified_percent: number; failing_percent: number;
}
export type MappingSummary = {
  id: number; project_id: number; upload_id: number | null; name: string; description: string | null; status: string; created_at: string;
}
export type MappingPort = { id: number; name: string; datatype: string | null; direction: 'IN' | 'OUT' | 'INOUT' | 'VAR' | null; expression: string | null }
export type MappingTransformation = {
  id: number; name: string; type: string; logic_json: Record<string, unknown>; seq_order: number; ports: MappingPort[];
}
export type LineageEdge = {
  id: number; from_port_id: number; to_port_id: number; from_transformation: string; from_port: string; to_transformation: string; to_port: string;
}
export type MappingDetail = MappingSummary & { transformations: MappingTransformation[]; lineage_edges: LineageEdge[] }
export type ConversionRisk = { code: string; severity: 'low' | 'medium' | 'high'; message: string; transformation: string | null; port: string | null }
export type ConversionSummary = { id: number; mapping_id: number; version: number; confidence: number | null; model_used: string | null; created_at: string }
export type Conversion = ConversionSummary & {
  generated_sql: string; schema_yml: string | null; confidence_reasons: string[]; risk_flags: ConversionRisk[];
}
export type ShadowMismatchSample = {
  key?: unknown[]; kind?: string; column?: string; expected?: unknown; actual?: unknown; [key: string]: unknown;
}
export type ShadowRun = {
  id: number; project_id: number; mapping_id: number; conversion_id: number; fixture_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed'; comparison_result: 'PASS' | 'FAIL' | null;
  reference_row_count: number | null; migrated_row_count: number | null; matched_rows: number | null;
  missing_rows: number | null; unexpected_rows: number | null; duplicate_key_mismatches: number | null;
  column_mismatches: number | null; null_mismatches: number | null; numeric_precision_differences: number | null;
  mismatch_samples: ShadowMismatchSample[]; execution_time_ms: number | null; error: string | null;
  created_at: string; started_at: string | null; completed_at: string | null;
}

export type AutopsyStatus = 'queued' | 'running' | 'completed' | 'failed'
export type AutopsyDiagnosisCategory =
  | 'EXPRESSION_MISMATCH' | 'FILTER_MISMATCH' | 'NULL_SEMANTICS' | 'DATA_TYPE_CONVERSION'
  | 'DECIMAL_PRECISION' | 'JOIN_BEHAVIOR' | 'LOOKUP_BEHAVIOR' | 'DUPLICATE_KEYS'
  | 'MISSING_ROWS' | 'UNEXPECTED_ROWS' | 'SQL_EXECUTION' | 'UNSUPPORTED_TRANSFORMATION'
  | 'UNKNOWN' | 'NEEDS_MORE_EVIDENCE'
export type AutopsyEvidence = { reference: string; observation: string }
export type AutopsyDiagnosis = {
  summary: string
  diagnosis_category: AutopsyDiagnosisCategory
  suspected_root_cause: string
  observed_facts: string[]
  hypotheses: string[]
  affected_transformations: string[]
  affected_columns: string[]
  supporting_evidence: AutopsyEvidence[]
  confidence: number
  confidence_reasons: string[]
  suggested_corrective_actions: string[]
  suggested_sql: string | null
  risks_and_limitations: string[]
  recommended_verification_steps: string[]
  more_evidence_required: boolean
}
export type AutopsyRecord = {
  id: number; shadow_run_id: number; project_id: number; mapping_id: number; conversion_id: number
  status: AutopsyStatus; diagnosis_category: AutopsyDiagnosisCategory | null; diagnosis_json: AutopsyDiagnosis | null
  confidence: number | null; evidence: AutopsyEvidence[]; suggested_corrections: string[]; suggested_sql: string | null
  suggested_sql_verified: boolean; model_used: string | null; input_tokens: number; output_tokens: number
  provider_error: string | null; created_at: string; started_at: string | null; completed_at: string | null
}

export type KnowledgeStatus = 'draft' | 'verified' | 'published' | 'rejected' | 'archived'
export type KnowledgeEvent = {
  id: number; actor_id: number; event_type: string; from_status: KnowledgeStatus | null; to_status: KnowledgeStatus
  notes: string | null; evidence_snapshot: Record<string, unknown> | null; created_at: string
}
export type KnowledgeCandidate = {
  id: number; project_id: number; mapping_id: number; owner_id: number; source_autopsy_id: number
  original_shadow_run_id: number; original_conversion_id: number; corrected_conversion_id: number | null
  corrected_conversion_version: number | null; passing_shadow_run_id: number | null; diagnosis_category: string
  transformation_identifiers: string[]; affected_columns: string[]; signature_metadata: Record<string, unknown>
  root_cause_summary: string; suggested_corrective_actions: string[]; proposed_sql: string | null
  verified_remediation_summary: string | null; fixture_id: string; verification_outcome: string | null
  verification_scope: string | null; verification_evidence: Record<string, unknown> | null; status: KnowledgeStatus
  reviewer_id: number | null; review_notes: string | null; created_at: string; verified_at: string | null
  approved_at: string | null; published_at: string | null; archived_at: string | null; events: KnowledgeEvent[]
}
export type KnowledgeCandidateList = { items: KnowledgeCandidate[]; total: number; limit: number; offset: number }
export type KnowledgeSuggestion = {
  knowledge_id: number; diagnosis_category: string; relevance: 'HIGH' | 'MEDIUM' | 'LOW'; reasons: string[]
  root_cause_summary: string; suggested_corrective_actions: string[]; verified_remediation_summary: string
  fixture_id: string; corrected_conversion_version: number; published_at: string; advisory: string
}

export const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1', timeout: 20000 })
api.interceptors.request.use(config => {
  const token = sessionStorage.getItem('migrapilot_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map(item => item.msg ?? 'Invalid field').join('; ')
    return error.response ? `Request failed (${error.response.status})` : 'Cannot connect to API. Check that Docker services are running.'
  }
  return 'Something went wrong. Please try again.'
}

export async function startAutopsy(shadowRunId: number): Promise<AutopsyRecord> {
  return (await api.post<AutopsyRecord>(`/shadow-runs/${shadowRunId}/autopsies`)).data
}

export async function getAutopsy(autopsyId: number): Promise<AutopsyRecord> {
  return (await api.get<AutopsyRecord>(`/autopsies/${autopsyId}`)).data
}

export async function listAutopsies(shadowRunId: number): Promise<AutopsyRecord[]> {
  return (await api.get<AutopsyRecord[]>(`/shadow-runs/${shadowRunId}/autopsies`)).data
}

export async function listKnowledgeCandidates(projectId: number, options: { status?: KnowledgeStatus; limit?: number; offset?: number } = {}): Promise<KnowledgeCandidateList> {
  return (await api.get<KnowledgeCandidateList>(`/projects/${projectId}/knowledge-candidates`, { params: options })).data
}
export async function getKnowledgeCandidate(id: number): Promise<KnowledgeCandidate> {
  return (await api.get<KnowledgeCandidate>(`/knowledge-candidates/${id}`)).data
}
export async function createKnowledgeCandidate(autopsyId: number): Promise<KnowledgeCandidate> {
  return (await api.post<KnowledgeCandidate>(`/autopsies/${autopsyId}/knowledge-candidates`)).data
}
export async function verifyKnowledgeCandidate(id: number, passingShadowRunId: number): Promise<KnowledgeCandidate> {
  return (await api.post<KnowledgeCandidate>(`/knowledge-candidates/${id}/verification`, { passing_shadow_run_id: passingShadowRunId })).data
}
export async function reviewKnowledgeCandidate(id: number, decision: 'approve' | 'reject' | 'archive', notes: string): Promise<KnowledgeCandidate> {
  return (await api.post<KnowledgeCandidate>(`/knowledge-candidates/${id}/review`, { decision, notes })).data
}
export async function getKnowledgeSuggestions(mappingId: number, conversionId?: number): Promise<KnowledgeSuggestion[]> {
  return (await api.get<KnowledgeSuggestion[]>(`/mappings/${mappingId}/knowledge-suggestions`, { params: conversionId ? { conversion_id: conversionId } : undefined })).data
}
export async function findKnowledgeCandidateByAutopsy(projectId: number, autopsyId: number): Promise<KnowledgeCandidate | null> {
  const limit = 100
  for (let offset = 0; offset <= 100_000; offset += limit) {
    const page = await listKnowledgeCandidates(projectId, { limit, offset })
    const match = page.items.find(item => item.source_autopsy_id === autopsyId)
    if (match) return match
    if (offset + page.items.length >= page.total || page.items.length === 0) return null
  }
  return null
}
