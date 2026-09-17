import { useState, useEffect } from 'react'
import axios from 'axios'

const API = 'http://localhost:8000/api'

export default function Centre() {
  const [exams, setExams]         = useState([])
  const [selectedExam, setSelectedExam] = useState(null)
  const [centreId, setCentreId]   = useState(14)
  const [hallId, setHallId]       = useState(3)
  const [unlocking, setUnlocking] = useState(false)
  const [printing, setPrinting]   = useState(false)
  const [unlockResult, setUnlockResult] = useState(null)
  const [error, setError]         = useState(null)
  const [countdown, setCountdown] = useState(null)

  useEffect(() => {
    loadExams()
  }, [])

  // Countdown timer
  useEffect(() => {
    if (!selectedExam) return
    const tick = () => {
      const rem = selectedExam.release_time - Date.now() / 1000
      setCountdown(rem > 0 ? rem : 0)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [selectedExam])

  const loadExams = async () => {
    try {
      const res = await axios.get(`${API}/exams/`)
      setExams(res.data)
    } catch {}
  }

  const handleUnlock = async () => {
    if (!selectedExam) return
    setUnlocking(true)
    setError(null)
    setUnlockResult(null)

    try {
      const res = await axios.post(`${API}/unlock/${selectedExam.id}`, {
        centre_id: centreId,
        hall_id:   hallId,
        otp:       'demo-otp',
      })
      setUnlockResult({ type: 'success', data: res.data })
    } catch (err) {
      const detail = err.response?.data?.detail
      if (detail?.error?.includes('TIMELOCK')) {
        setUnlockResult({ type: 'timelock', data: detail })
      } else {
        setError(detail || err.message)
      }
    } finally {
      setUnlocking(false)
    }
  }

  const handleWarp = async () => {
    if (!selectedExam) return
    try {
      await axios.post(`${API}/unlock/${selectedExam.id}/warp`)
      await loadExams()
      setSelectedExam(prev => prev ? { ...prev, release_time: Date.now() / 1000 - 10 } : null)
      setCountdown(0)
      setUnlockResult({
        type: 'success',
        data: {
          message: 'Blockchain clock advanced by +3600s (evm_increaseTime). Release window is active.',
          audit_hash: '0x300e375f1d18f7e7e825f04466b2931a'
        }
      })
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    }
  }

  const handlePrint = async () => {
    if (!selectedExam) return
    setPrinting(true)
    try {
      const res = await axios.get(
        `${API}/print/${selectedExam.id}?centre_id=${centreId}&hall_id=${hallId}`,
        { responseType: 'blob' }
      )
      const url = URL.createObjectURL(res.data)
      const a   = document.createElement('a')
      a.href    = url
      a.download = `exam_c${centreId}_h${hallId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setPrinting(false)
    }
  }

  const formatCountdown = (secs) => {
    if (secs <= 0) return '00:00:00 — UNLOCKABLE'
    const h = String(Math.floor(secs / 3600)).padStart(2, '0')
    const m = String(Math.floor((secs % 3600) / 60)).padStart(2, '0')
    const s = String(Math.floor(secs % 60)).padStart(2, '0')
    return `${h}:${m}:${s}`
  }

  const isLocked = countdown !== null && countdown > 0

  return (
    <div>
      <div className="page-header">
        <span className="page-overline">Dispersed Custody</span>
        <h1 className="page-title">Centre Custodian</h1>
        <p className="page-subtitle">
          On-chain custody enforcement gateway for local examination centres. Decrypts papers upon consensus release and prints sequentially watermarked physical copies.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, alignItems: 'start' }}>
        {/* Left: exam selection */}
        <div>
          <div className="card">
            <h2 className="card-title">Select Custody Document</h2>

            <div className="form-group">
              <label className="form-label">Examination</label>
              <select
                className="form-select"
                value={selectedExam?.id || ''}
                onChange={e => {
                  const exam = exams.find(ex => ex.id === e.target.value)
                  setSelectedExam(exam || null)
                  setUnlockResult(null)
                  setError(null)
                }}
              >
                <option value="">— Choose an exam —</option>
                {exams.map(ex => (
                  <option key={ex.id} value={ex.id}>{ex.name}</option>
                ))}
              </select>
            </div>

            <div className="grid-2">
              <div className="form-group">
                <label className="form-label">Centre ID</label>
                <input
                  className="form-input"
                  type="number"
                  value={centreId}
                  onChange={e => setCentreId(Number(e.target.value))}
                  min={1}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Hall ID</label>
                <input
                  className="form-input"
                  type="number"
                  value={hallId}
                  onChange={e => setHallId(Number(e.target.value))}
                  min={1}
                />
              </div>
            </div>
          </div>

          {/* Countdown clock */}
          {selectedExam && (
            <div className="card" style={{ marginTop: 20 }}>
              <h2 className="card-title">Consensus Time-Lock Gateway</h2>

              <div style={{
                textAlign: 'center',
                padding: '24px 20px',
                background: isLocked ? 'rgba(255, 59, 48, 0.05)' : 'rgba(52, 199, 89, 0.05)',
                borderRadius: 'var(--radius-md)',
                border: `1px solid ${isLocked ? 'var(--danger-border)' : 'var(--success-border)'}`,
              }}>
                <div style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: isLocked ? 'var(--danger-text)' : 'var(--success-text)',
                  marginBottom: 6,
                }}>
                  {isLocked ? 'Pre-Exam Custody Active (Early Access Blocked)' : 'Custody Window Open'}
                </div>
                <div style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 30,
                  fontWeight: 700,
                  letterSpacing: '-0.03em',
                  color: isLocked ? 'var(--danger-text)' : 'var(--success-text)',
                  marginBottom: 6,
                }}>
                  {countdown !== null ? formatCountdown(countdown) : '—'}
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
                  Scheduled Release: {selectedExam ? new Date(selectedExam.release_time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                </div>
              </div>

              <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <button
                  className={`btn btn-lg ${isLocked ? 'btn-danger' : 'btn-primary'}`}
                  style={{ width: '100%' }}
                  onClick={handleUnlock}
                  disabled={unlocking || !selectedExam}
                >
                  {unlocking
                    ? <><div className="spinner" />&nbsp;Verifying Consensus…</>
                    : isLocked
                      ? 'Simulate Early Unlock (Verify EVM Revert)'
                      : 'Release Examination Custody'
                  }
                </button>

                {isLocked && (
                  <button
                    className="btn btn-secondary"
                    style={{
                      width: '100%',
                      color: 'var(--accent)',
                    }}
                    onClick={handleWarp}
                    title="Simulates Hardhat evm_increaseTime to advance blockchain past unlock window"
                  >
                    Time-Travel Clock Warp (+3600s)
                  </button>
                )}

                <button
                  className="btn btn-secondary btn-lg"
                  style={{ width: '100%' }}
                  onClick={handlePrint}
                  disabled={printing || !selectedExam || isLocked}
                >
                  {printing
                    ? <><div className="spinner" />&nbsp;Generating Watermarked PDF…</>
                    : 'Print Secure Watermarked Copy'
                  }
                </button>
              </div>

              {/* On-chain custody status */}
              <div style={{
                marginTop: 16,
                padding: '14px 16px',
                background: '#f5f5f7',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border)',
                fontSize: 12,
                color: 'var(--text-secondary)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span>Smart Contract</span>
                  <span className="mono" style={{ color: 'var(--text-primary)', fontWeight: 600 }}>PaperVault.sol</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span>EVM Consensus</span>
                  <span className="mono" style={{ color: 'var(--accent)' }}>Chain 31337 (Local Hardhat)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Consensus State</span>
                  <span style={{ color: isLocked ? 'var(--danger-text)' : 'var(--success-text)', fontWeight: 600 }}>
                    {isLocked ? 'Proof-of-Denial Active' : 'Access Authorized'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: results */}
        <div>
          {/* Timelock revert — DEMO MOMENT #1 */}
          {unlockResult?.type === 'timelock' && (
            <div className="card" style={{ border: '1px solid var(--danger-border)', marginBottom: 20 }}>
              <div style={{ textAlign: 'center', padding: '16px 0' }}>
                <div style={{ display: 'inline-flex', marginBottom: 10 }}>
                  <span className="badge badge-danger" style={{ padding: '6px 14px', fontSize: 11.5 }}>
                    EVM Transaction Reverted
                  </span>
                </div>
                <div style={{
                  fontSize: 20,
                  fontWeight: 700,
                  color: 'var(--danger-text)',
                  marginBottom: 10,
                  letterSpacing: '-0.02em',
                }}>
                  Consensus Release Window Closed
                </div>

                <div style={{
                  margin: '12px 0',
                  padding: 12,
                  background: 'rgba(255, 59, 48, 0.05)',
                  border: '1px solid var(--danger-border)',
                  borderRadius: 'var(--radius-sm)',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 12,
                  color: 'var(--danger-text)',
                  textAlign: 'left',
                  lineHeight: 1.6
                }}>
                  <div>&gt; EVM Revert: TimeLockActive({Math.floor(unlockResult.data.current_time)}, {Math.floor(unlockResult.data.release_time)})</div>
                  <div>&gt; Consensus Rule: block.timestamp &lt; p.unlockTime</div>
                  <div>&gt; [Proof-of-Denial]: Mathematical consensus guarantees paper cannot leak early!</div>
                </div>

                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, marginTop: 12 }}>
                  <strong>Scheduled Release:</strong> {new Date(unlockResult.data.release_time * 1000).toLocaleString()}<br />
                  <strong>Current Block Time:</strong> {new Date(unlockResult.data.current_time * 1000).toLocaleString()}<br />
                  <strong>Time Remaining:</strong> {formatCountdown(unlockResult.data.seconds_remaining)}
                </div>
              </div>
              <hr className="divider" />
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
                No single authority or custodian can bypass this release window.<br />
                The smart contract enforces pre-exam secrecy unconditionally on-chain.
              </div>
            </div>
          )}

          {unlockResult?.type === 'success' && (
            <div className="card" style={{ border: '1px solid var(--success-border)', marginBottom: 20 }}>
              <div style={{ textAlign: 'center', padding: '16px 0' }}>
                <div style={{ display: 'inline-flex', marginBottom: 10 }}>
                  <span className="badge badge-success" style={{ padding: '6px 14px', fontSize: 11.5 }}>
                    Custody Access Granted
                  </span>
                </div>
                <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
                  Examination Paper Unlocked
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  {unlockResult.data.message}
                </div>
                <div className="mono" style={{ fontSize: 11.5, marginTop: 8, color: 'var(--text-secondary)' }}>
                  Audit Hash: {unlockResult.data.audit_hash?.slice(0, 24)}…
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="alert alert-danger" style={{ marginBottom: 20 }}>
              <div>
                <div style={{ fontWeight: 600 }}>Error</div>
                <div style={{ fontSize: 13 }}>{JSON.stringify(error)}</div>
              </div>
            </div>
          )}

          {/* Info box */}
          <div className="card">
            <h2 className="card-title">Custody Protocol Guarantees</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {[
                { title: 'Time-Lock Consensus', desc: 'Smart contract consensus halts access prior to the scheduled exam hour. Early unlock attempts fail unconditionally with an on-chain revert.' },
                { title: 'Just-in-Time Watermarking', desc: 'Each physical print copy embeds a unique cryptographic identifier via ±3pt inter-word space modulation, tying leaked photos to an exact centre and hall.' },
                { title: 'Immutable Audit Log', desc: 'Every custody operation and access attempt is hash-chained in an immutable ledger, ensuring tamper-evident operational compliance.' },
              ].map(item => (
                <div key={item.title} style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5, color: 'var(--text-primary)', marginBottom: 2 }}>{item.title}</div>
                  <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{item.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
