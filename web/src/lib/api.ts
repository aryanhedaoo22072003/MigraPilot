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
