import { useQuery } from '@tanstack/react-query'
import { BookOpen, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getErrorMessage, getKnowledgeSuggestions } from '../../lib/api'

export default function RelatedKnowledge({ projectId, mappingId, conversionId }: { projectId: number; mappingId: number; conversionId: number }) {
  const query = useQuery({
    queryKey: ['knowledge-suggestions', projectId, mappingId, conversionId],
    queryFn: () => getKnowledgeSuggestions(mappingId, conversionId), retry: false,
  })
  return <section className="related-knowledge" aria-label="Related Verified Knowledge">
    <header><span><BookOpen size={13} /> Related Verified Knowledge</span><small>Advisory only</small></header>
    {query.isLoading ? <p>Finding relevant verified knowledge…</p>
    : query.isError ? <p role="alert">{getErrorMessage(query.error)}</p>
    : !query.data?.length ? <p>No related published knowledge was found for this mapping.</p>
    : <>{query.data.map(item => <article key={item.knowledge_id}>
      <div><strong>Knowledge #{item.knowledge_id} · {item.diagnosis_category.replaceAll('_', ' ')}</strong><span className={`knowledge-relevance relevance-${item.relevance.toLowerCase()}`}>{item.relevance}</span></div>
      <p>{item.root_cause_summary}</p><ul>{item.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
      <p><b>Verified remediation:</b> {item.verified_remediation_summary}</p><p><b>Actions:</b> {item.suggested_corrective_actions.join('; ')}</p>
      <p><b>Verification scope:</b> {item.fixture_id}</p>
      <Link to={`/app/projects/${projectId}/knowledge?candidate=${item.knowledge_id}`}>Open knowledge record</Link>
    </article>)}<div className="knowledge-advisory"><ShieldCheck size={13} /> {query.data[0].advisory}</div></>}
  </section>
}
