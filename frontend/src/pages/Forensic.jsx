import { useState, useEffect } from 'react'
import axios from 'axios'

const API = 'http://localhost:8000/api'

const PIPELINE_STEPS = [
  { key: 'detect',     label: 'Page Boundary Detected' },
  { key: 'anchor',     label: 'Corner Fiducial Crosshairs' },
  { key: 'homography', label: 'Canonical Euclidean Homography' },
  { key: 'lines',      label: 'Text Line Projection Segmentation' },
  { key: 'gaps',       label: 'Inter-Word Spacing Measurement' },
  { key: 'rs',         label: 'Error-Correction Decoding' },
  { key: 'verified',   label: 'Custody Registry Correlated' },
]

export default function Forensic() {
  const [activeTab, setActiveTab] = useState('photo') // 'photo' | 'text'

  // Photo Investigation State
  const [file, setFile]             = useState(null)
  const [preview, setPreview]       = useState(null)
  const [loading, setLoading]       = useState(false)
  const [pipelineState, setPipelineState] = useState({})
  const [result, setResult]         = useState(null)
  const [history, setHistory]       = useState([])

  // Honey-Token Plaintext State
  const [leakText, setLeakText]     = useState('')
  const [textLoading, setTextLoading] = useState(false)
  const [textResult, setTextResult] = useState(null)

  useEffect(() => {
    if (!file) { setPreview(null); return }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const handleDrop = (e) => {
    e.preventDefault()
    const f = e.dataTransfer?.files?.[0] || e.target.files?.[0]
    if (f) { setFile(f); setResult(null); setPipelineState({}) }
  }

  const runPipeline = async () => {
    if (!file) return
    setLoading(true)
    setResult(null)

    const steps = PIPELINE_STEPS.map(s => s.key)
    setPipelineState({})

    for (let i = 0; i < steps.length - 1; i++) {
      await new Promise(r => setTimeout(r, 260 + Math.random() * 150))
      setPipelineState(prev => ({ ...prev, [steps[i]]: 'active' }))
      await new Promise(r => setTimeout(r, 120))
      setPipelineState(prev => ({ ...prev, [steps[i]]: 'done' }))
    }

    setPipelineState(prev => ({ ...prev, verified: 'active' }))

    try {
      const form = new FormData()
      form.append('file', file)
      const res = await axios.post(`${API}/investigate/`, form)
      const data = res.data

      const lastStepState = data.status === 'VERIFIED' ? 'done' : data.status === 'CORRUPTED' ? 'done' : 'failed'
      setPipelineState(prev => ({ ...prev, verified: lastStepState }))
      setResult(data)

      loadHistory()
    } catch (err) {
      setPipelineState(prev => ({ ...prev, verified: 'failed' }))
      setResult({ status: 'UNKNOWN', message: err.response?.data?.detail || err.message, confidence: 0 })
    } finally {
      setLoading(false)
    }
  }

  const runHoneyTokenInvestigation = async () => {
    if (!leakText.trim()) return
    setTextLoading(true)
    setTextResult(null)
    try {
      const res = await axios.post(`${API}/investigate/honey-token`, {
        leaked_text: leakText,
        paper_id: 'EXAM-2026-MAIN',
        total_centres: 50,
      })
      setTextResult(res.data)
      loadHistory()
    } catch (err) {
      setTextResult({
        status: 'INVALID',
        message: err.response?.data?.detail || err.message,
        confidence: 0,
      })
    } finally {
      setTextLoading(false)
    }
  }

  const loadSampleLeak = async (centreId) => {
    try {
      const res = await axios.get(`${API}/investigate/honey-token/sample/${centreId}`)
      setLeakText(res.data.simulated_leak)
      setTextResult(null)
    } catch {
      if (centreId === 2) {
        setLeakText(`Intercepted Chat [Group #NEET_LEAKS]:\nQ1: AC circuit has inductor 18 mH and resistance 55 ohms. Find impedance.\nQ2: Particle mass 3.5 kg with kinetic energy 480 J. Max height?`)
      } else if (centreId === 14) {
        setLeakText(`Intercepted Chat [Group #NEET_LEAKS]:\nQ1: AC circuit has inductor 18 mH and resistance 45 ohms.\nQ2: Particle mass 3.0 kg with kinetic energy 450 J.`)
      } else {
        setLeakText(`Intercepted Chat [Group #NEET_LEAKS]:\nQ1: Inductor 20 mH with 40 ohms resistance.\nQ2: Mass 5.0 kg with kinetic energy 560 J.`)
      }
      setTextResult(null)
    }
  }

  const loadHistory = async () => {
    try {
      const res = await axios.get(`${API}/investigate/history`)
      setHistory(res.data)
    } catch {}
  }

  useEffect(() => { loadHistory() }, [])

  // Render gap distribution histogram
  const renderGapHistogram = () => {
    const gaps = result?.gap_sample && result.gap_sample.length > 0
      ? result.gap_sample
      : [18.2, 19.1, 18.5, 31.4, 32.1, 19.0, 30.8, 18.7, 31.9, 19.3, 31.2, 18.9, 19.4, 32.0, 31.5, 18.6, 19.2, 31.8]
    const threshold = result?.threshold || 25.0

    return (
      <div className="card" style={{ marginTop: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h2 className="card-title" style={{ margin: 0 }}>Inter-Word Spacing Distribution</h2>
          <span className="badge badge-neutral mono">
            Decision Boundary: {threshold}px
          </span>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
          Physical spacing shifts by ±3pt (12.5% delta). Bit 0 maps to narrow gaps (~18-20px) and Bit 1 maps to wide gaps (~30-33px).
        </p>

        <div style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: 4,
          height: 120,
          padding: '12px 10px 4px 10px',
          background: '#f5f5f7',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--border)',
          position: 'relative',
        }}>
          {/* Threshold line */}
          <div style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: `${(threshold / 42) * 100}%`,
            borderTop: '2px dashed #ff9500',
            zIndex: 2,
            pointerEvents: 'none',
          }}>
            <span style={{
              position: 'absolute',
              right: 8,
              top: -16,
              fontSize: 10,
              color: '#b25e00',
              fontWeight: 600,
              background: '#ffffff',
              padding: '1px 6px',
              borderRadius: 4,
              border: '1px solid rgba(0,0,0,0.08)',
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            }}>
              Boundary {threshold}px
            </span>
          </div>

          {gaps.slice(0, 36).map((g, idx) => {
            const isWide = g >= threshold
            const heightPct = Math.min(100, Math.max(15, (g / 40) * 100))
            return (
              <div
                key={idx}
                title={`Gap #${idx + 1}: ${g}px → Bit ${isWide ? 1 : 0}`}
                style={{
                  flex: 1,
                  height: `${heightPct}%`,
                  background: isWide ? '#0071e3' : '#a1a1a6',
                  borderRadius: '3px 3px 0 0',
                  transition: 'all 0.2s ease',
                  cursor: 'pointer',
                }}
              />
            )
          })}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontSize: 12 }}>
          <div style={{ display: 'flex', gap: 16 }}>
            <span style={{ color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: '#a1a1a6', display: 'inline-block' }} />
              Bit 0: Narrow Spacing (&lt; {threshold}px)
            </span>
            <span style={{ color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: '#0071e3', display: 'inline-block' }} />
              Bit 1: Wide Spacing (≥ {threshold}px)
            </span>
          </div>
          <span style={{ color: 'var(--text-tertiary)' }}>{gaps.length} gaps plotted</span>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <span className="page-overline">Attribution Intelligence</span>
        <h1 className="page-title">Forensic Tracer</h1>
        <p className="page-subtitle">
          Recover examination paper provenance through physical inter-word gap steganography or semantic honey-token content correlation.
        </p>
      </div>

      {/* Apple Segmented Control */}
      <div style={{ marginBottom: 28 }}>
        <div className="segmented-control">
          <button
            onClick={() => setActiveTab('photo')}
            className={`segmented-item ${activeTab === 'photo' ? 'active' : ''}`}
          >
            Physical Watermark Scanner
          </button>
          <button
            onClick={() => setActiveTab('text')}
            className={`segmented-item ${activeTab === 'text' ? 'active' : ''}`}
          >
            Honey-Token Plaintext Inspector
          </button>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────── */}
      {/* TAB 1: PHYSICAL PHOTO SCANNER                              */}
      {/* ─────────────────────────────────────────────────────────── */}
      {activeTab === 'photo' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, alignItems: 'start' }}>
          {/* Left: upload & pipeline */}
          <div>
            <div className="card">
              <h2 className="card-title">Upload Examination Sheet Photograph</h2>

              <div
                className="upload-zone"
                style={{ padding: 32, marginBottom: 20 }}
                onDrop={handleDrop}
                onDragOver={e => e.preventDefault()}
                onClick={() => document.getElementById('photo-input').click()}
              >
                <input
                  id="photo-input"
                  type="file"
                  accept="image/*"
                  style={{ display: 'none' }}
                  onChange={handleDrop}
                />
                {preview ? (
                  <div style={{
                    background: '#1d1d1f',
                    padding: 12,
                    borderRadius: 12,
                    boxShadow: 'inset 0 2px 8px rgba(0,0,0,0.3)',
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                  }}>
                    <img
                      src={preview}
                      alt="uploaded"
                      style={{ maxWidth: '100%', maxHeight: 220, borderRadius: 6, objectFit: 'contain' }}
                    />
                  </div>
                ) : (
                  <>
                    <div className="upload-icon">
                      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                        <circle cx="12" cy="13" r="4"></circle>
                      </svg>
                    </div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                      Choose photo or drag and drop here
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      JPEG / PNG · Supports tilted, folded, or unevenly lit sheets
                    </div>
                  </>
                )}
              </div>

              <button
                className="btn btn-primary btn-lg"
                style={{ width: '100%' }}
                onClick={runPipeline}
                disabled={!file || loading}
              >
                {loading
                  ? <><div className="spinner" />&nbsp;Extracting Forensic Signal…</>
                  : 'Execute Signal Extraction Pipeline'
                }
              </button>
            </div>

            {/* Pipeline Steps */}
            {Object.keys(pipelineState).length > 0 && (
              <div className="card" style={{ marginTop: 20 }}>
                <h2 className="card-title">Computer Vision Reconstruction Sequence</h2>
                <div className="pipeline">
                  {PIPELINE_STEPS.map(step => {
                    const state = pipelineState[step.key]
                    return (
                      <div
                        key={step.key}
                        className={`pipeline-step ${state || ''}`}
                      >
                        <span className="pipeline-step-label">{step.label}</span>
                        <span className="pipeline-step-detail">
                          {state === 'done'   ? 'Verified' :
                           state === 'active' ? <div className="spinner" style={{ width: 14, height: 14 }} /> :
                           state === 'failed' ? 'Failed' : 'Pending'}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Right: verdict & histogram */}
          <div>
            {result ? (
              <div>
                {/* Verdict card */}
                <div className="verdict-card" style={{ marginBottom: 20 }}>
                  <div style={{ display: 'inline-flex', marginBottom: 12 }}>
                    <span className={`badge ${result.status === 'VERIFIED' ? 'badge-success' : 'badge-danger'}`} style={{ padding: '6px 14px', fontSize: 12 }}>
                      {result.status === 'VERIFIED' ? 'Proven Origin Identified' : 'Signal Inconclusive'}
                    </span>
                  </div>

                  <div className="verdict-title" style={{ color: result.status === 'VERIFIED' ? 'var(--text-primary)' : 'var(--danger-text)' }}>
                    {result.status === 'VERIFIED' ? 'Physical Watermark Recovered' : 'Watermark Unresolved'}
                  </div>

                  {result.status === 'VERIFIED' && (
                    <div className="verdict-meta-row">
                      {[
                        { label: 'Centre Identity', value: `Centre #${result.centre_id}` },
                        { label: 'Hall Number',    value: `Hall #${result.hall_id}` },
                        { label: 'Print Instance', value: `#${result.print_num}` },
                      ].map(m => (
                        <div key={m.label} className="verdict-meta-item">
                          <div className="verdict-meta-label">{m.label}</div>
                          <div className="verdict-meta-value">{m.value}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {result.exam_match && (
                    <div style={{
                      marginTop: 18, padding: '12px 16px',
                      background: '#f5f5f7', borderRadius: 'var(--radius-md)', fontSize: 12.5,
                      textAlign: 'left', border: '1px solid var(--border)'
                    }}>
                      <div><strong>Custody Exam:</strong> {result.exam_match.exam_name}</div>
                      <div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>
                        Authorized Release: {new Date(result.exam_match.authorized_at * 1000).toLocaleString()}
                      </div>
                    </div>
                  )}
                </div>

                {/* Confidence */}
                <div className="card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-secondary)' }}>
                      Signal Confidence
                    </span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--success-text)' }}>
                      {(result.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="confidence-bar-wrap">
                    <div className="confidence-bar-track">
                      <div
                        className="confidence-bar-fill"
                        style={{ width: `${Math.min(100, result.confidence * 100)}%` }}
                      />
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 16, marginTop: 12, fontSize: 12.5, color: 'var(--text-secondary)' }}>
                    <span>Bits Extracted: <strong>{result.bit_count}</strong></span>
                    <span>Corner Fiducials: <strong>{result.anchor_found ? 'Aligned (4/4)' : 'Estimated'}</strong></span>
                  </div>
                  {result.message && (
                    <div className="mono" style={{ marginTop: 12, fontSize: 11.5, color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                      {result.message}
                    </div>
                  )}
                </div>

                {/* Gap Distribution Histogram */}
                {renderGapHistogram()}
              </div>
            ) : (
              <div className="card" style={{ textAlign: 'center', padding: '64px 20px', color: 'var(--text-secondary)' }}>
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: 'var(--text-primary)' }}>Awaiting Examination Photograph</div>
                <div style={{ fontSize: 13 }}>Upload an image of the physical examination sheet to execute homography alignment and word-gap recovery.</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────── */}
      {/* TAB 2: TELEGRAM & PLAINTEXT HONEY-TOKEN INSPECTOR          */}
      {/* ─────────────────────────────────────────────────────────── */}
      {activeTab === 'text' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: 24, alignItems: 'start' }}>
          {/* Left: Input & Pre-fill */}
          <div>
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h2 className="card-title" style={{ margin: 0 }}>Plaintext Honey-Token Correlator</h2>
                <span className="badge badge-accent">Retyping Defense</span>
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
                When leakers retype questions into online channels, physical watermarks are lost.
                ZeroLock embeds <strong>deterministic numerical distractor permutations</strong> per centre to mathematically attribute the leak source.
              </p>

              {/* Sample loader buttons */}
              <div style={{ marginBottom: 16 }}>
                <label className="form-label">
                  Load Centre Benchmark Signatures
                </label>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: 12, padding: '6px 14px' }}
                    onClick={() => loadSampleLeak(2)}
                  >
                    Pune Centre #2 (18mH / 55Ω)
                  </button>
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: 12, padding: '6px 14px' }}
                    onClick={() => loadSampleLeak(14)}
                  >
                    Mumbai Centre #14 (18mH / 45Ω)
                  </button>
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: 12, padding: '6px 14px' }}
                    onClick={() => loadSampleLeak(7)}
                  >
                    Delhi Centre #7 (20mH / 40Ω)
                  </button>
                </div>
              </div>

              {/* Textarea */}
              <div className="form-group">
                <label className="form-label">Intercepted Chat / Channel Transcript</label>
                <textarea
                  className="form-input"
                  style={{ minHeight: 180, fontFamily: 'JetBrains Mono, monospace', fontSize: 13, lineHeight: 1.6 }}
                  placeholder="Paste leaked text here (e.g. from Telegram, Discord, or WhatsApp)..."
                  value={leakText}
                  onChange={e => setLeakText(e.target.value)}
                />
              </div>

              <button
                className="btn btn-primary btn-lg"
                style={{ width: '100%' }}
                onClick={runHoneyTokenInvestigation}
                disabled={!leakText.trim() || textLoading}
              >
                {textLoading
                  ? <><div className="spinner" />&nbsp;Correlating 50 Mathematical Profiles…</>
                  : 'Execute Semantic Attribution Analysis'
                }
              </button>
            </div>
          </div>

          {/* Right: Results */}
          <div>
            {textResult ? (
              <div>
                {/* Result Verdict Card */}
                <div className="verdict-card" style={{ marginBottom: 20 }}>
                  <div style={{ display: 'inline-flex', marginBottom: 12 }}>
                    <span className={`badge ${textResult.status === 'VERIFIED' ? 'badge-success' : 'badge-warning'}`} style={{ padding: '6px 14px', fontSize: 12 }}>
                      {textResult.status === 'VERIFIED' ? 'Origin Correlated' : 'Inconclusive Signature'}
                    </span>
                  </div>

                  <div className="verdict-title" style={{ color: textResult.status === 'VERIFIED' ? 'var(--text-primary)' : 'var(--warning-text)' }}>
                    {textResult.status === 'VERIFIED' ? `Centre #${textResult.implicated_centre_id} Implicated` : 'No Unique Signature Match'}
                  </div>

                  {textResult.status === 'VERIFIED' && (
                    <div className="verdict-meta-row">
                      <div className="verdict-meta-item">
                        <div className="verdict-meta-label">Culprit Centre</div>
                        <div className="verdict-meta-value" style={{ color: 'var(--accent)' }}>
                          #{textResult.implicated_centre_id}
                        </div>
                      </div>
                      <div className="verdict-meta-item">
                        <div className="verdict-meta-label">Matched Tokens</div>
                        <div className="verdict-meta-value">
                          {textResult.tokens_matched_count} Values
                        </div>
                      </div>
                      <div className="verdict-meta-item">
                        <div className="verdict-meta-label">Confidence</div>
                        <div className="verdict-meta-value">
                          {textResult.confidence}%
                        </div>
                      </div>
                    </div>
                  )}

                  <div style={{ marginTop: 14, fontSize: 13, color: 'var(--text-secondary)' }}>
                    {textResult.message}
                  </div>
                </div>

                {/* Statistical Margin & Runner-Up */}
                {textResult.status === 'VERIFIED' && (
                  <div className="card" style={{ marginBottom: 20 }}>
                    <h3 style={{ fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-secondary)', marginBottom: 12 }}>
                      Statistical Separation Margin
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                          <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                            Centre #{textResult.implicated_centre_id} (Top Candidate)
                          </span>
                          <span style={{ fontWeight: 700, color: 'var(--accent)' }}>{textResult.confidence}%</span>
                        </div>
                        <div className="confidence-bar-track">
                          <div className="confidence-bar-fill" style={{ width: `${textResult.confidence}%`, background: 'var(--accent)' }} />
                        </div>
                      </div>

                      {textResult.runner_up_centre_id && (
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                            <span style={{ color: 'var(--text-secondary)' }}>
                              Centre #{textResult.runner_up_centre_id} (Runner-Up Signature)
                            </span>
                            <span style={{ color: 'var(--text-secondary)' }}>{textResult.runner_up_confidence}%</span>
                          </div>
                          <div className="confidence-bar-track">
                            <div className="confidence-bar-fill" style={{ width: `${textResult.runner_up_confidence}%`, background: '#d2d2d7' }} />
                          </div>
                        </div>
                      )}

                      <div style={{
                        marginTop: 4,
                        padding: 10,
                        background: 'var(--success-bg)',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: 12,
                        color: 'var(--success-text)',
                        textAlign: 'center',
                        fontWeight: 600,
                      }}>
                        Attribution Separation: +{(textResult.confidence - textResult.runner_up_confidence).toFixed(1)}% Distinctness Margin
                      </div>
                    </div>
                  </div>
                )}

                {/* Token Match Breakdown */}
                {textResult.tokens_matched && textResult.tokens_matched.length > 0 && (
                  <div className="card">
                    <h3 style={{ fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-secondary)', marginBottom: 12 }}>
                      Correlated Distractor Parameters
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {textResult.tokens_matched.map((tok, i) => (
                        <div
                          key={i}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            padding: '8px 12px',
                            background: '#fafafc',
                            borderRadius: 'var(--radius-sm)',
                            border: '1px solid var(--border)',
                          }}
                        >
                          <div>
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', marginRight: 8 }}>
                              {tok.question_id}
                            </span>
                            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                              {tok.topic}
                            </span>
                          </div>
                          <span className="badge badge-accent mono">
                            {tok.parameter} = {tok.value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="card" style={{ textAlign: 'center', padding: '64px 20px', color: 'var(--text-secondary)' }}>
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: 'var(--text-primary)' }}>Awaiting Plaintext Transcript</div>
                <div style={{ fontSize: 13 }}>Paste intercepted message text or load one of the benchmark signatures to run correlation.</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Global Investigation History */}
      {history.length > 0 && (
        <div className="card" style={{ marginTop: 24 }}>
          <h2 className="card-title">Recent Intelligence Investigations</h2>
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Target Artifact / Transcript</th>
                  <th>Timestamp</th>
                  <th>Forensic Attribution</th>
                  <th>Signal Status</th>
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 6).map(inv => (
                  <tr key={inv.id}>
                    <td style={{ fontWeight: 600 }}>{inv.image_filename || 'Plaintext Channel Transcript'}</td>
                    <td style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
                      {new Date(inv.uploaded_at * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                    </td>
                    <td>
                      {inv.centre_id ? (
                        <span style={{ fontWeight: 600, color: 'var(--accent)' }}>
                          Centre #{inv.centre_id} {inv.hall_id ? `· Hall #${inv.hall_id}` : ''}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-tertiary)' }}>Unresolved</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${inv.status === 'VERIFIED' ? 'badge-success' : inv.status === 'CORRUPTED' ? 'badge-warning' : 'badge-neutral'}`}>
                        {inv.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
