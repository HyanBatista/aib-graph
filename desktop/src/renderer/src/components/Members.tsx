import { useApp } from '../lib/store'
import { useAction, useResource } from '../lib/hooks'
import type { ClassInfo, Member } from '../lib/types'

export default function Members({ info }: { info: ClassInfo }): JSX.Element {
  const api = useApp((s) => s.api)
  const me = useApp((s) => s.user)
  const version = useApp((s) => s.cls.versions.members)
  const members = useResource(() => api.get<Member[]>(`/classes/${info.id}/members`), [api, info.id, version])
  const action = useAction()
  const isProfessor = info.role === 'professor'

  const setRole = async (m: Member, role: string): Promise<void> => {
    if (await action.run(() => api.patch(`/classes/${info.id}/members/${m.user_id}`, { role }))) void members.reload()
  }
  const remove = async (m: Member): Promise<void> => {
    if (!window.confirm(`Remove ${m.full_name || m.email} from the class?`)) return
    const ok = await action.run(async () => {
      await api.del(`/classes/${info.id}/members/${m.user_id}`)
      return true
    })
    if (ok) void members.reload()
  }

  return (
    <div className="page narrow">
      <div className="card invite">
        <div>
          <div className="muted small">Invite code</div>
          <div className="code" data-testid="invite-code">
            {info.invite_code}
          </div>
        </div>
        <p className="muted small">
          Students join with this code from their class list. To add an assistant, let them join and change their role
          here.
        </p>
        <button onClick={() => void navigator.clipboard.writeText(info.invite_code ?? '')}>Copy</button>
      </div>
      {(members.error || action.error) && <div className="error">{members.error || action.error}</div>}
      <div className="card">
        <h4>Members ({members.data?.length ?? 0})</h4>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {members.data?.map((m) => (
              <tr key={m.user_id}>
                <td>{m.full_name || '—'}</td>
                <td className="muted">{m.email}</td>
                <td>
                  {isProfessor && m.role !== 'professor' ? (
                    <select value={m.role} onChange={(e) => void setRole(m, e.target.value)} disabled={action.busy}>
                      <option value="student">student</option>
                      <option value="assistant">assistant</option>
                    </select>
                  ) : (
                    <span className="badge role">{m.role}</span>
                  )}
                </td>
                <td>
                  {isProfessor && m.role !== 'professor' && m.user_id !== me?.id && (
                    <button className="icon danger" title="Remove" onClick={() => void remove(m)}>
                      ✕
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
