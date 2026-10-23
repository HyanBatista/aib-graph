import { useRef } from 'react'
import { useApp } from '../lib/store'
import { useAction } from '../lib/hooks'
import type { ClassInfo } from '../lib/types'

export default function BookSetup({ info }: { info: ClassInfo }): JSX.Element {
  const api = useApp((s) => s.api)
  const job = useApp((s) => s.cls.job)
  const input = useRef<HTMLInputElement>(null)
  const upload = useAction()
  const isProfessor = info.role === 'professor'
  const working = info.status === 'indexing' || info.status === 'building'

  const send = async (file: File): Promise<void> => {
    const form = new FormData()
    form.append('file', file)
    await upload.run(() => api.post(`/classes/${info.id}/book`, form))
  }

  return (
    <div className="page narrow">
      <div className="card">
        {working ? (
          <>
            <div className="row">
              <span className="spinner" />
              <h3>{info.status === 'indexing' ? 'Reading the book…' : 'Building the graph…'}</h3>
            </div>
            <p className="muted">{job || info.status_detail || 'This can take a few minutes for a long book.'}</p>
          </>
        ) : isProfessor ? (
          <>
            <h3>Upload the course book</h3>
            <p className="muted">
              Upload a PDF. The AI extracts an index of topics and subtopics that you will review before the graph
              starts growing. Each topic becomes one node of the graph.
            </p>
            {info.status_detail && <div className="error">{info.status_detail}</div>}
            <div
              className="dropzone"
              onClick={() => input.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                const file = e.dataTransfer.files[0]
                if (file) void send(file)
              }}
            >
              {upload.busy ? 'Uploading…' : 'Drop a PDF here or click to choose'}
            </div>
            <input
              ref={input}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void send(file)
                e.target.value = ''
              }}
            />
            {upload.error && <div className="error">{upload.error}</div>}
          </>
        ) : (
          <>
            <h3>Waiting for the professor</h3>
            <p className="muted">The professor hasn't uploaded the course book yet.</p>
          </>
        )}
      </div>
    </div>
  )
}
