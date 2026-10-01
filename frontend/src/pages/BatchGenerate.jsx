import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

const API = 'http://localhost:8000/api'

export default function BatchGenerate() {
  const [exams, setExams] = useState([])
  const [selectedExam, setSelectedExam] = useState('')
  const [centreInput, setCentreInput] = useState('')
  const [answerKey, setAnswerKey] = useState('')
  const [jobId, setJobId] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)
  const [polling, setPolling] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  useEffect(() => {
    axios.get(`${API}/exams/`).then(r => setExams(r.data)).catch(() => {})
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const handleGenerate = async () => {
    if (!selectedExam || !centreInput.trim()) return
    setGenerating(true)
    setError(null)
    setJobStatus(null)

    try {
      const res = await axios.post(`${API}/batch/generate`, {
        exam_id: selectedExam,
        centre_ids_raw: centreInput.trim(),
        answer_key_text: answerKey.trim() || null,
      })
      setJobId(res.data.job_id)
      setPolling(true)
      startPolling(res.data.job_id)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setGenerating(false)
    }
  }

  const startPolling = (jid) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`${API}/batch/status/${jid}`)
        setJobStatus(res.data)
        if (res.data.status === 'COMPLETED' || res.data.status === 'FAILED') {
          clearInterval(pollRef.current)
          pollRef.current = null
          setPolling(false)
        }
      } catch {
        clearInterval(pollRef.current)
        pollRef.current = null
        setPolling(false)
      }
    }, 1500)
  }

  const downloadZip = () => {
    if (!jobId) return
    window.open(`${API}/batch/download/${jobId}`, '_blank')
  }

  const downloadSingle = (centreId, fmt) => {
    if (!jobId) return
    window.open(`${API}/batch/download/${jobId}/${centreId}?fmt=${fmt}`, '_blank')
  }

  const progress = jobStatus?.progress || 0
  const centres = jobStatus?.centres || {}
  const centreKeys = Object.keys(centres).sort((a, b) => Number(a) - Number(b))
  const verifiedCount = jobStatus?.verified_count || 0
  const totalCount = jobStatus?.total_count || 0

  return (
    <div>
      <div className="page-header">
        <span className="page-overline">Batch Operations</span>
        <h1 className="page-title">Centre Paper Generation</h1>
        <p className="page-subtitle">
          Generate watermarked examination papers for multiple centres simultaneously.
          Each paper receives a unique forensic engraving and optional semantic variant.
          Every output is self-verified before inclusion in the distribution package.
        </p>
      </div>

      {/* Configuration card */}
      <div className="card" style={{ marginBottom: 28 }}>
        <h2 className="card-title">Batch Configuration</h2>

        <div className="form-group" style={{ marginBottom: 18 }}>
          <label className="form-label">Examination Paper</label>
          <select
            className="form-input"
            value={selectedExam}
            onChange={e => setSelectedExam(e.target.value)}
          >
            <option value="">Select a registered exam</option>
            {exams.map(ex => (
              <option key={ex.id} value={ex.id}>{ex.name} ({ex.id.slice(0, 8)}…)</option>
            ))}
          </select>
          {(() => {
            const exObj = exams.find(e => e.id === selectedExam)
            if (!exObj) return null
            return (
              <div style={{ marginTop: 10, padding: 12, background: 'rgba(0,0,0,0.2)', borderRadius: 6, border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span className="badge badge-accent" style={{ fontSize: 11 }}>{exObj.question_count ?? (exObj.questions_json ? JSON.parse(exObj.questions_json).length : 0)} Questions Parsed</span>
                  {exObj.engine && <span className="badge badge-neutral" style={{ fontSize: 11 }}>Engine: {exObj.engine}</span>}
                </div>
                {exObj.preview && (
                  <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', fontFamily: 'JetBrains Mono, monospace', whiteSpace: 'pre-wrap', maxHeight: 80, overflowY: 'auto' }}>
                    {exObj.preview}
                  </div>
                )}
              </div>
            )
          })()}
        </div>

        <div className="form-group" style={{ marginBottom: 18 }}>
          <label className="form-label">Centre Identifiers</label>
          <input
            className="form-input"
            value={centreInput}
            onChange={e => setCentreInput(e.target.value)}
            placeholder="e.g. 14, 28, 42  or  1..500  or  1..5, 14, 28"
          />
          <div style={{ fontSize: 11.5, color: 'var(--text-tertiary)', marginTop: 4 }}>
            Comma-separated IDs, range notation (1..500), or a combination of both.
          </div>
        </div>

        <div className="form-group" style={{ marginBottom: 22 }}>
          <label className="form-label">Answer Key (optional — enables numeric perturbation)</label>
          <textarea
            className="form-input"
            rows={4}
            value={answerKey}
            onChange={e => setAnswerKey(e.target.value)}
            placeholder="Paste the answer key text here to enable per-centre numeric variants. If left blank, only wording variants are applied."
            style={{ resize: 'vertical', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}
          />
        </div>

        <button
          className="btn btn-primary btn-lg"
          style={{ width: '100%' }}
          disabled={generating || polling || !selectedExam || !centreInput.trim()}
          onClick={handleGenerate}
        >
          {generating ? <><div className="spinner" />&nbsp;Submitting…</> :
           polling ? <><div className="spinner" />&nbsp;Generating…</> :
           'Generate Centre Papers'}
        </button>

        {error && (
          <div className="alert alert-danger" style={{ marginTop: 16 }}>
            <div style={{ fontWeight: 600 }}>Generation Error</div>
            <div style={{ fontSize: 13 }}>{JSON.stringify(error)}</div>
          </div>
        )}
      </div>

      {/* Progress and status */}
      {jobStatus && (
        <div className="card" style={{ marginBottom: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <h2 className="card-title" style={{ margin: 0 }}>
              Generation Progress
            </h2>
            <span className={`badge ${
              jobStatus.status === 'COMPLETED' ? 'badge-success' :
              jobStatus.status === 'RUNNING' ? 'badge-warning' :
              jobStatus.status === 'FAILED' ? 'badge-danger' : 'badge-neutral'
            }`}>
              {jobStatus.status}
            </span>
          </div>

          {/* Progress bar */}
          <div style={{
            background: 'var(--bg-inset)',
            borderRadius: 'var(--radius-pill)',
            height: 8,
            marginBottom: 16,
            overflow: 'hidden'
          }}>
            <div style={{
              width: `${Math.round(progress * 100)}%`,
              height: '100%',
              background: verifiedCount === totalCount && jobStatus.status === 'COMPLETED'
                ? 'var(--success)' : 'var(--accent)',
              borderRadius: 'var(--radius-pill)',
              transition: 'width 0.4s ease'
            }} />
          </div>

          <div style={{ display: 'flex', gap: 24, marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
            <span>Progress: {Math.round(progress * 100)}%</span>
            <span>Verified: {verifiedCount}/{totalCount}</span>
          </div>

          {/* Warnings */}
          {jobStatus.warnings?.length > 0 && (
            <div className="alert alert-warning" style={{ marginBottom: 16 }}>
              {jobStatus.warnings.map((w, i) => (
                <div key={i} style={{ fontSize: 13 }}>{w}</div>
              ))}
            </div>
          )}

          {/* Download all button */}
          {jobStatus.status === 'COMPLETED' && (
            <button
              className="btn btn-primary"
              onClick={downloadZip}
              style={{ marginBottom: 20 }}
            >
              Download All ({verifiedCount} verified papers) — ZIP
            </button>
          )}

          {/* Per-centre table */}
          {centreKeys.length > 0 && (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th>Centre ID</th>
                    <th>Watermark</th>
                    <th>Text Variant</th>
                    <th>PDF</th>
                    <th>DOCX</th>
                    <th>Self-Check</th>
                  </tr>
                </thead>
                <tbody>
                  {centreKeys.map(cid => {
                    const c = centres[cid]
                    const cidNum = Number(cid)
                    return (
                      <tr key={cid}>
                        <td style={{ fontWeight: 600, fontFamily: 'JetBrains Mono, monospace', fontSize: 13 }}>
                          {String(cidNum).padStart(4, '0')}
                        </td>
                        <td>
                          <span className={`badge ${c.self_check === 'VERIFIED' ? 'badge-success' : 'badge-danger'}`}>
                            {c.self_check === 'VERIFIED' ? 'Engraved' : 'Failed'}
                          </span>
                        </td>
                        <td>
                          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            {c.variant_slots || 0} slots
                            {c.difficulty_index !== undefined && (
                              <> · DI {c.difficulty_index?.toFixed(2)}</>
                            )}
                          </span>
                        </td>
                        <td>
                          {c.pdf_status === 'VERIFIED' ? (
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '3px 10px', fontSize: 11 }}
                              onClick={() => downloadSingle(cidNum, 'pdf')}
                            >
                              PDF
                            </button>
                          ) : (
                            <span className="badge badge-danger" style={{ fontSize: 10 }}>
                              {c.pdf_status}
                            </span>
                          )}
                        </td>
                        <td>
                          {c.docx_status === 'VERIFIED' ? (
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '3px 10px', fontSize: 11 }}
                              onClick={() => downloadSingle(cidNum, 'docx')}
                            >
                              DOCX
                            </button>
                          ) : c.docx_status === 'WORKING_COPY' ? (
                            <div>
                              <button
                                className="btn btn-secondary"
                                style={{ padding: '3px 10px', fontSize: 11, opacity: 0.7 }}
                                onClick={() => downloadSingle(cidNum, 'docx')}
                              >
                                DOCX*
                              </button>
                              <div style={{ fontSize: 10, color: 'var(--warning-text)', marginTop: 2 }}>
                                {c.docx_warning || 'Editable master — the PDF is the watermarked official copy.'}
                              </div>
                            </div>
                          ) : (
                            <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                              {c.docx_status || '—'}
                            </span>
                          )}
                        </td>
                        <td>
                          <span className={`badge ${
                            c.self_check === 'VERIFIED' ? 'badge-success' :
                            c.self_check === 'PENDING' ? 'badge-neutral' : 'badge-danger'
                          }`}>
                            {c.self_check}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
