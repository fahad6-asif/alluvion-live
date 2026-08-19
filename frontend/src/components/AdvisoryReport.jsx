import React from "react";

// The agentic AI advisory: threshold gate -> Gemini drafts report -> email dispatch.
export default function AdvisoryReport({
  occurrence, status, report, loading, onGenerate,
  recipient, setRecipient, onSend, sending, emailResult,
}) {
  if (occurrence == null || !status) return null;

  const threshold = status.occurrence_threshold ?? 0.5;
  const armed = occurrence >= threshold;         // AI report only fires above threshold
  const email = status.email || {};

  return (
    <div className="panel advisory-report">
      <h2>🤖 AI advisory <span className="exp-tag">AGENTIC</span></h2>

      <div className="workflow-steps">
        <span className={armed ? "wf on" : "wf"}>1 · Occurrence ≥ {Math.round(threshold * 100)}%</span>
        <span className="wf-arrow">→</span>
        <span className={report?.text ? "wf on" : "wf"}>2 · Gemini drafts report</span>
        <span className="wf-arrow">→</span>
        <span className={emailResult?.sent ? "wf on" : "wf"}>3 · Email dispatched</span>
      </div>

      {!armed ? (
        <div className="hint">
          Occurrence is <b>{Math.round(occurrence * 100)}%</b>, below the {Math.round(threshold * 100)}%
          reporting threshold. The workflow only drafts and sends an advisory when the mudslide
          chance is high enough to warrant one.
        </div>
      ) : (
        <>
          <p className="hint" style={{ marginTop: 0 }}>
            Occurrence is above threshold — the agent can draft a full advisory
            {status.gemini_available ? " with Gemini" : " (templated; add GEMINI_API_KEY for Gemini)"} and email it.
          </p>
          <button className="primary" onClick={onGenerate} disabled={loading}>
            {loading ? "Drafting advisory…" : report?.text ? "↻ Regenerate advisory" : "✍ Generate AI advisory"}
          </button>

          {report?.text && (
            <>
              <div className="report-box">
                <div className="report-head">
                  Severity: <b>{report.severity}</b> · source: {report.source}
                </div>
                <pre className="report-text">{report.text}</pre>
              </div>

              <div className="email-row">
                <input type="email" placeholder="recipient@gmail.com" value={recipient}
                  onChange={(e) => setRecipient(e.target.value)} />
                <button className="primary" onClick={onSend} disabled={sending || !email.available}>
                  {sending ? "Sending…" : "✉ Email this report"}
                </button>
              </div>
              {!email.available && (
                <div className="hint">{email.reason} {email.how_to_enable}</div>
              )}
              {emailResult && (
                <div className={emailResult.sent ? "email-ok" : "email-err"}>
                  {emailResult.sent
                    ? `✅ Sent to ${emailResult.recipient} from ${emailResult.sender}.`
                    : `⚠ ${emailResult.reason}`}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
