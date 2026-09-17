import { useState, useEffect } from 'react'
import axios from 'axios'

const API = 'http://localhost:8000/api'

export default function Audit() {
  const [exams, setExams]       = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [log, setLog]           = useState(null)
  const [loading, setLoading]   = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [verifyResult, setVerifyResult] = useState(null)

  useEffect(() => {
    axios.get(`${API}/exams/`).then(r => setExams(r.data)).catch(() => {})
  }, [])

  const loadLog = async (id) => {
    setLoading(true)
    setLog(null)
    setVerifyResult(null)
    try {
      const res = await axios.get(`${API}/audit/${id}`)
      setLog(res.data)
    } catch {}
    setLoading(false)
  }

  const verifyChain = async () => {
    if (!selectedId) return
    setVerifying(true)
    try {
      const res = await axios.get(`${API}/audit/${selectedId}/verify`)
      setVerifyResult(res.data)
    } catch {}
    setVerifying(false)
  }

  const EVENT_COLORS = {
    PAPER_SEALED:       'badge-accent',
    PAPER_SCHEDULED:    'badge-accent',
    PAPER_UNLOCKED:     'badge-success',
    PRINT_GENERATED:    'badge-warning',
    EARLY_UNLOCK_ATTEMPT: 'badge-danger',
    PAPER_SEALED_DB:    'badge-accent',
  }

  return (
    <div>
      <div className="page-header">
        <span className="page-overline">Immutability Proof</span>
        <h1 className="page-title">Ledger Audit Trail</h1>
        <p className="page-subtitle">
          Cryptographically verified, hash-chained custody events. Any mutation or state manipulation immediately invalidates subsequent SHA-256 block hashes.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end' }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label className="form-label">Examination Paper</label>
            <select
              className="form-select"
              value={selectedId}
              onChange={e => {
                setSelectedId(e.target.value)
                if (e.target.value) loadLog(e.target.value)
              }}
            >
              <option value="">— Select an examination —</option>
              {exams.map(ex => (
                <option key={ex.id} value={ex.id}>{ex.name}</option>
              ))}
            </select>
          </div>
          <button
            className="btn btn-secondary"
            onClick={verifyChain}
            disabled={!selectedId || verifying}
            style={{ padding: '11px 20px' }}
          >
            {verifying ? <><div className="spinner" />&nbsp;Auditing Block Hashes…</> : 'Verify Ledger Integrity'}
          </button>
        </div>

        {verifyResult && (
          <div
            className={`alert ${verifyResult.chain_valid ? 'alert-success' : 'alert-danger'}`}
            style={{ marginTop: 16 }}
          >
            <div>
              <div style={{ fontWeight: 600 }}>
                {verifyResult.chain_valid ? 'Cryptographic Chain Validated' : 'Ledger Integrity Compromised'}
              </div>
              <div style={{ fontSize: 12.5, marginTop: 3, fontFamily: 'JetBrains Mono, monospace' }}>
                {verifyResult.message}
              </div>
            </div>
          </div>
        )}
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>
          <div className="spinner" style={{ margin: '0 auto 14px', width: 26, height: 26 }} />
          Loading immutable audit sequence…
        </div>
      )}

      {log && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
            <div>
              <h2 className="card-title" style={{ margin: 0 }}>Custody Sequence</h2>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                {log.event_count} chronological events logged
              </div>
            </div>
            <span className={`badge ${log.chain_valid ? 'badge-success' : 'badge-danger'}`}>
              {log.chain_valid ? 'Chain Intact' : 'Tamper Detected'}
            </span>
          </div>

          <div className="audit-chain">
            {log.events.map((ev) => (
              <div key={ev.seq} className="audit-event">
                <div className="audit-event-dot" />
                <div className="audit-event-time">
                  {new Date(ev.timestamp * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' })}
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span className={`badge ${EVENT_COLORS[ev.event_type] || 'badge-neutral'}`} style={{ fontSize: 11 }}>
                      {ev.event_type}
                    </span>
                    {ev.actor && (
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>by {ev.actor}</span>
                    )}
                  </div>
                  {ev.metadata_json && ev.metadata_json !== '{}' && (
                    <div className="mono" style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginBottom: 4 }}>
                      {Object.entries(JSON.parse(ev.metadata_json)).map(([k, v]) => (
                        <span key={k} style={{ marginRight: 14 }}>{k}: <strong style={{ color: 'var(--text-primary)' }}>{String(v).slice(0, 24)}{String(v).length > 24 ? '…' : ''}</strong></span>
                      ))}
                    </div>
                  )}
                  <div className="audit-event-hash">
                    H({ev.seq}): {ev.event_hash}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!log && !loading && (
        <div className="card" style={{ textAlign: 'center', padding: '56px 20px', color: 'var(--text-secondary)' }}>
          <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: 'var(--text-primary)' }}>Awaiting Examination Selection</div>
          <div style={{ fontSize: 13 }}>Choose an examination above to inspect its cryptographic sequence of custody events.</div>
        </div>
      )}
    </div>
  )
}
