import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, Outlet, RouteObject, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Shell from '../components/Shell'
import { api, type Project } from '../lib/api'
import { useAuth } from '../lib/auth'
import KnowledgeProjectSelector from './KnowledgeProjectSelector'

const projects: Project[] = [
  { id: 6, owner_id: 1, name: 'Orders Migration', source_system: 'PowerCenter', target_system: 'dbt', created_at: '' },
  { id: 7, owner_id: 1, name: 'Discount Migration', source_system: 'PowerCenter', target_system: 'PostgreSQL', created_at: '' },
]

function DashboardStub() { return <div>Main dashboard</div> }
function ProjectStub() { return <div>Project workspace</div> }
function KnowledgeStub() { return <div>Project Knowledge Base</div> }
function BareLayout() { return <Outlet /> }

function setup(initialEntries: string[], shell = true) {
  const children: RouteObject[] = [
    { index: true, element: <DashboardStub /> },
    { path: 'knowledge', element: <KnowledgeProjectSelector /> },
    { path: 'projects/:id', element: <ProjectStub /> },
    { path: 'projects/:id/knowledge', element: <KnowledgeStub /> },
  ]
  const router = createMemoryRouter([{ path: '/app', element: shell ? <Shell /> : <BareLayout />, children }], { initialEntries })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>)
  return router
}

beforeEach(() => {
  vi.restoreAllMocks()
  useAuth.setState({ token: 'test-token', user: { id: 1, email: 'owner@example.com', role: 'engineer', created_at: '' } })
  vi.spyOn(api, 'get').mockImplementation(async url => {
    if (url === '/projects') return { data: projects } as never
    throw new Error(`Unexpected GET ${url}`)
  })
})

describe('Knowledge Base navigation', () => {
  it('routes Dashboard sidebar clicks to the project chooser', async () => {
    const router = setup(['/app'])
    expect(screen.getByText('Main dashboard')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('link', { name: 'Knowledge Base' }))
    expect(await screen.findByRole('heading', { name: 'Choose a project' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app/knowledge')
    expect(screen.getAllByRole('link', { name: 'Knowledge Base' })[0]).toHaveClass('text-violet-200')
  })

  it('opens the selected authorized project Knowledge Base', async () => {
    const router = setup(['/app/knowledge'])
    expect(await screen.findByText('Orders Migration')).toBeInTheDocument()
    const actions = screen.getAllByRole('link', { name: /Open Knowledge Base/ })
    expect(actions[0]).toHaveAttribute('href', '/app/projects/6/knowledge')
    await userEvent.click(actions[1])
    expect(await screen.findByText('Project Knowledge Base')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app/projects/7/knowledge')
  })

  it('keeps a project-scoped sidebar click inside that project', async () => {
    const router = setup(['/app/projects/6'])
    await userEvent.click(screen.getByRole('link', { name: 'Knowledge Base' }))
    expect(await screen.findByText('Project Knowledge Base')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app/projects/6/knowledge')
  })

  it('supports direct refresh and browser back/forward history', async () => {
    const router = setup(['/app', '/app/knowledge'], true)
    expect(await screen.findByRole('heading', { name: 'Choose a project' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app/knowledge')
    await router.navigate(-1)
    await waitFor(() => expect(router.state.location.pathname).toBe('/app'))
    expect(screen.getByText('Main dashboard')).toBeInTheDocument()
    await router.navigate(1)
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/knowledge'))
    expect(screen.getByRole('heading', { name: 'Choose a project' })).toBeInTheDocument()
  })
})
