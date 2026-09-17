import { useState, useEffect } from 'react'
import axios from 'axios'

const API = 'http://localhost:8000/api'

export default function Setter() {
  const [file, setFile]     = useState(null)
  const [name, setName]     = useState('')
  const [releaseDate, setReleaseDate] = useState('')
  const [releaseTime, setReleaseTime] = useState('10:00')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState(null)
  const [error, setError]     = useState(null)
  const [exams, setExams]     = useState([])
  const [loadingExams, setLoadingExams] = useState(false)

  const handleDrop = (e) => {
    e.preventDefault()
    const f = e.dataTransfer?.files?.[0] || e.target.files?.[0]
    if (f?.type === 'application/pdf') setFile(f)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file || !name || !releaseDate) return
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const dt = new Date(`${releaseDate}T${releaseTime}:00`)
      const releaseEpoch = dt.getTime() / 1000

      const form = new FormData()
      form.append('file', file)
      form.append('name', name)
      form.append('release_time', releaseEpoch)

      const res = await axios.post(`${API}/exams/`, form)
      setResult(res.data)

      // Reload exam list
      loadExams()
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  const loadExams = async () => {
    setLoadingExams(true)
    try {
      const res = await axios.get(`${API}/exams/`)
      setExams(res.data)
    } catch {}
    setLoadingExams(false)
  }

  useEffect(() => { loadExams() }, [])

  const statusColor = {
    SEALED: 'badge-accent', AUTHORIZED: 'badge-success',
    PRINTING: 'badge-warning', DRAFT: 'badge-neutral',
  }

  return (
    <div>
      <div className="page-header">
        <span className="page-overline">Master Custody</span>
        <h1 className="page-title">Paper Vault</h1>
        <p className="page-subtitle">
          Encrypt and seal master exam question papers with AES-256-GCM and Shamir Secret Sharing under on-chain time-lock custody.
        </p>
      </div>

      {/* Upload form */}
      <div className="card" style={{ marginBottom: 28 }}>
        <h2 className="card-title">Register Master Question Paper</h2>
        <form onSubmit={handleSubmit}>
          {/* Drop zone */}
          <div
            className={`upload-zone ${file ? 'drag-over' : ''}`}
            style={{ marginBottom: 24 }}
            onDrop={handleDrop}
            onDragOver={e => e.preventDefault()}
            onClick={() => document.getElementById('pdf-input').click()}
          >
            <input
              id="pdf-input"
              type="file"
              accept="application/pdf"
              style={{ display: 'none' }}
              onChange={handleDrop}
            />
            <div className="upload-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="12" y1="18" x2="12" y2="12"></line>
                <line x1="9" y1="15" x2="12" y2="12"></line>
                <line x1="15" y1="15" x2="12" y2="12"></line>
              </svg>
            </div>
            {file ? (
              <div>
                <div style={{ fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>
                  {file.name}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  {(file.size / 1024).toFixed(1)} KB · Ready for cryptographic sealing
                </div>
              </div>
            ) : (
              <div>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                  Choose PDF or drag and drop here
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  Master document is encrypted with AES-256-GCM and split across 3-of-5 Shamir key shards
                </div>
              </div>
            )}
          </div>

          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Examination Name</label>
              <input
                className="form-input"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. National Entrance Physics 2026"
                required
              />
            </div>
            <div className="grid-2">
              <div className="form-group">
                <label className="form-label">Release Date</label>
                <input
                  className="form-input"
                  type="date"
                  value={releaseDate}
                  onChange={e => setReleaseDate(e.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Release Time</label>
                <input
                  className="form-input"
                  type="time"
                  value={releaseTime}
                  onChange={e => setReleaseTime(e.target.value)}
                  required
                />
              </div>
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-lg"
            style={{ width: '100%' }}
            disabled={loading || !file || !name || !releaseDate}
          >
            {loading ? <><div className="spinner" />&nbsp;Sealing & Registering On-Chain…</> : 'Seal & Commit to Custody'}
          </button>
        </form>

        {/* Result */}
        {result && (
          <div className="alert alert-success" style={{ marginTop: 20 }}>
            <div>
              <div style={{ fontWeight: 600 }}>Master Question Paper Sealed & Committed</div>
              <div className="mono" style={{ marginTop: 6, fontSize: 12, lineHeight: 1.6 }}>
                <div><strong>Exam ID:</strong> {result.exam_id}</div>
                <div><strong>IPFS CID:</strong> {result.ipfs_cid}</div>
                <div><strong>SHA-256:</strong> {result.sha256_plain?.slice(0, 24)}…</div>
                <div><strong>Audit Hash:</strong> {result.audit_hash?.slice(0, 24)}…</div>
              </div>
            </div>
          </div>
        )}
        {error && (
          <div className="alert alert-danger" style={{ marginTop: 20 }}>
            <div>
              <div style={{ fontWeight: 600 }}>Registration Error</div>
              <div style={{ fontSize: 13 }}>{JSON.stringify(error)}</div>
            </div>
          </div>
        )}
      </div>

      {/* Registered exams list */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <h2 className="card-title" style={{ margin: 0 }}>Registered Custody Papers</h2>
          <button className="btn btn-secondary" onClick={loadExams} disabled={loadingExams} style={{ padding: '6px 14px', fontSize: 12 }}>
            {loadingExams ? <div className="spinner" /> : 'Refresh'}
          </button>
        </div>
        {exams.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '36px 0', fontSize: 13 }}>
            No exams registered in current custody ledger. Upload a master question paper above.
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Examination Paper</th>
                  <th>Paper Identifier</th>
                  <th>Scheduled Unlock</th>
                  <th>Custody Status</th>
                </tr>
              </thead>
              <tbody>
                {exams.map(exam => (
                  <tr key={exam.id}>
                    <td style={{ fontWeight: 600 }}>{exam.name}</td>
                    <td className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      {exam.id}
                    </td>
                    <td style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
                      {new Date(exam.release_time * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                    </td>
                    <td>
                      <span className={`badge ${statusColor[exam.status] || 'badge-neutral'}`}>
                        {exam.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
