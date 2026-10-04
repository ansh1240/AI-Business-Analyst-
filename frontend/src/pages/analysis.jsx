import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import api from "../api/api";
import "./analysis.css";

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return value;
}

function Analysis() {
  const location = useLocation();
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [question, setQuestion] = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [asking, setAsking] = useState(false);

  const loadAnalysis = async () => {
    setLoading(true);
    setError("");

    try {
      const response = await api.get("/ai-analysis");
      setAnalysis(response.data);
    } catch (err) {
      console.error("AI Analysis error:", err);
      setError(err.response?.data?.detail || "Unable to generate AI analysis.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isActive = true;

    api.get("/ai-analysis")
      .then((response) => {
        if (isActive) setAnalysis(response.data);
      })
      .catch((err) => {
        console.error("AI Analysis error:", err);
        if (isActive) {
          setError(err.response?.data?.detail || "Unable to generate AI analysis.");
        }
      })
      .finally(() => {
        if (isActive) setLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, []);

  const askAIQuestion = async (questionText) => {
    const trimmedQuestion = (questionText || "").trim();
    if (!trimmedQuestion || asking) return;

    try {
      setAsking(true);
      setAiAnswer("");
      const response = await api.post("/ask-ai", {
        question: trimmedQuestion,
      });
      setAiAnswer(response.data.answer);
    } catch (err) {
      console.error("Ask AI error:", err);
      setAiAnswer(err.response?.data?.detail || "Unable to answer your question.");
    } finally {
      setAsking(false);
    }
  };

  const askAI = async (event) => {
    event.preventDefault();
    await askAIQuestion(question);
  };

  useEffect(() => {
    const prefilledQuestion = location.state?.prefilledQuestion;
    if (prefilledQuestion) {
      setQuestion(prefilledQuestion);
      const timer = window.setTimeout(() => {
        askAIQuestion(prefilledQuestion);
      }, 150);
      return () => window.clearTimeout(timer);
    }
  }, [location.state]);

  if (loading) {
    return (
      <div className="analysis-page">
        <div className="analysis-state" aria-live="polite">
          <span className="analysis-spinner" aria-hidden="true" />
          <h2>Analyzing dataset</h2>
          <p>Preparing findings, risks, and recommendations.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="analysis-page">
        <div className="analysis-state" role="alert">
          <span className="analysis-error-mark" aria-hidden="true">!</span>
          <h2>Analysis unavailable</h2>
          <p>{error}</p>
          <button className="analysis-button" onClick={loadAnalysis}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!analysis) return null;

  const overview = analysis.overview || {};
  const findings = analysis.key_findings || [];
  const correlations = analysis.correlations || [];
  const statistics = Object.entries(analysis.numeric_statistics || {});

  return (
    <div className="analysis-page">
      <header className="analysis-header">
        <div>
          <span className="analysis-eyebrow">DATA INTELLIGENCE</span>
          <h1>AI Analysis</h1>
          <p>Key findings and practical actions based on your dataset.</p>
        </div>
        <button className="analysis-button" onClick={loadAnalysis} disabled={loading}>
          Refresh Analysis
        </button>
      </header>

      <section className="analysis-metrics" aria-label="Analysis overview">
        {[
          ["Data Quality", `${formatNumber(overview.data_quality_score)}%`],
          ["Key Findings", findings.length],
          ["Numeric Metrics", overview.numeric_columns],
          ["Relationships", correlations.length],
        ].map(([label, value]) => (
          <div className="analysis-metric" key={label}>
            <span>{label}</span>
            <strong>{formatNumber(value)}</strong>
          </div>
        ))}
      </section>

      <section className="analysis-section">
        <div className="analysis-section-heading">
          <span>EXECUTIVE SUMMARY</span>
          <h2>Dataset overview</h2>
        </div>
        <div className="analysis-summary">
          <span className="analysis-summary-mark" aria-hidden="true">AI</span>
          <p>{analysis.executive_summary}</p>
        </div>
      </section>

      <section className="analysis-section analysis-columns">
        <div>
          <div className="analysis-section-heading">
            <span>WHAT STANDS OUT</span>
            <h2>Key findings</h2>
          </div>
          <div className="analysis-list">
            {findings.map((finding, index) => (
              <article className={`analysis-list-item finding-${finding.type}`} key={`${finding.title}-${index}`}>
                <span className="analysis-list-mark" aria-hidden="true">
                  {finding.type === "positive" ? "✓" : finding.type === "warning" ? "!" : finding.type === "danger" ? "×" : "i"}
                </span>
                <div>
                  <h3>{finding.title}</h3>
                  <p>{finding.description}</p>
                </div>
              </article>
            ))}
          </div>
        </div>

        <div>
          <div className="analysis-section-heading">
            <span>WHERE TO LOOK NEXT</span>
            <h2>Opportunities</h2>
          </div>
          <ol className="analysis-opportunities">
            {(analysis.opportunities || []).map((item, index) => (
              <li key={`${item}-${index}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <p>{item}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="analysis-section">
        <div className="analysis-section-heading">
          <span>DATA HEALTH</span>
          <h2>Quality and coverage</h2>
        </div>
        <div className="analysis-quality">
          <div className="analysis-quality-main">
            <div className="analysis-quality-score">
              {formatNumber(overview.data_quality_score)}%
            </div>
            <div className="analysis-quality-track" role="progressbar" aria-label="Data quality" aria-valuemin={0} aria-valuemax={100} aria-valuenow={overview.data_quality_score || 0}>
              <span style={{ width: `${overview.data_quality_score || 0}%` }} />
            </div>
            <p>{overview.data_quality_score >= 90 ? "Strong condition for analysis." : overview.data_quality_score >= 70 ? "Usable, with some cleaning recommended." : "Review data quality before relying on results."}</p>
          </div>
          <div className="analysis-quality-stats">
            <div><span>Rows</span><strong>{formatNumber(overview.rows)}</strong></div>
            <div><span>Columns</span><strong>{formatNumber(overview.columns)}</strong></div>
            <div><span>Missing cells</span><strong>{formatNumber(overview.missing_cells)}</strong></div>
            <div><span>Duplicate rows</span><strong>{formatNumber(overview.duplicate_rows)}</strong></div>
          </div>
        </div>
        {(analysis.missing_analysis || []).length > 0 && (
          <div className="analysis-missing-list">
            <h3>Columns with missing values</h3>
            {analysis.missing_analysis.map((item) => (
              <div key={item.column}>
                <span>{item.column}</span>
                <strong>{formatNumber(item.count)} <small>({formatNumber(item.percentage)}%)</small></strong>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="analysis-section analysis-columns">
        <div>
          <div className="analysis-section-heading">
            <span>ATTENTION</span>
            <h2>Risks</h2>
          </div>
          <ul className="analysis-text-list risk-list">
            {(analysis.risks || []).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
          </ul>
        </div>
        <div>
          <div className="analysis-section-heading">
            <span>RECOMMENDED ACTIONS</span>
            <h2>Recommendations</h2>
          </div>
          <ol className="analysis-text-list">
            {(analysis.recommendations || []).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
          </ol>
        </div>
      </section>

      <section className="analysis-section analysis-columns">
        <div>
          <div className="analysis-section-heading">
            <span>RELATIONSHIPS</span>
            <h2>Numeric correlations</h2>
          </div>
          <div className="analysis-data-panel">
            {correlations.length ? correlations.map((item) => (
              <div className="analysis-correlation" key={`${item.column1}-${item.column2}`}>
                <span><strong>{item.column1}</strong> <i aria-hidden="true">↔</i> <strong>{item.column2}</strong></span>
                <div><span style={{ width: `${Math.min(Math.abs(item.correlation) * 100, 100)}%` }} /><strong>{formatNumber(item.correlation)}</strong></div>
              </div>
            )) : <p className="analysis-empty">Not enough numeric columns to calculate correlations.</p>}
          </div>
        </div>
        <div>
          <div className="analysis-section-heading">
            <span>SEGMENTS</span>
            <h2>Category patterns</h2>
          </div>
          <div className="analysis-data-panel">
            {(analysis.category_analysis || []).length ? analysis.category_analysis.map((category) => (
              <div className="analysis-category" key={category.column}>
                <h3>{category.column}</h3>
                {category.top_values.map((item) => (
                  <div key={item.value}><span>{item.value}</span><strong>{formatNumber(item.count)}</strong></div>
                ))}
              </div>
            )) : <p className="analysis-empty">No categorical values to compare.</p>}
          </div>
        </div>
      </section>

      <section className="analysis-section">
        <div className="analysis-section-heading">
          <span>METRICS</span>
          <h2>Numeric statistics</h2>
        </div>
        <div className="analysis-table-wrap">
          <table className="analysis-table">
            <thead><tr><th scope="col">Metric</th><th scope="col">Average</th><th scope="col">Minimum</th><th scope="col">Maximum</th><th scope="col">Median</th><th scope="col">Std. deviation</th></tr></thead>
            <tbody>
              {statistics.map(([column, values]) => (
                <tr key={column}><th scope="row">{column}</th><td>{formatNumber(values.average)}</td><td>{formatNumber(values.minimum)}</td><td>{formatNumber(values.maximum)}</td><td>{formatNumber(values.median)}</td><td>{formatNumber(values.std)}</td></tr>
              ))}
              {!statistics.length && <tr><td colSpan="6">No numeric statistics are available.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="analysis-section ask-ai-section">
        <div className="analysis-section-heading">
          <span>INTERACTIVE ANALYSIS</span>
          <h2>Ask about your data</h2>
          <p>Get a quick answer based on the current user’s uploaded dataset.</p>
        </div>
        <form className="analysis-question-form" onSubmit={askAI}>
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about rows, missing values, averages, or correlations"
            aria-label="Question about your dataset"
          />
          <button className="analysis-button" type="submit" disabled={asking || !question.trim()}>
            {asking ? "Analyzing..." : "Ask AI"}
          </button>
        </form>
        <div className="analysis-suggestions" aria-label="Suggested questions">
          {["Summarize this dataset", "Which metric has the highest average?", "How many missing values are there?"].map((suggestion) => (
            <button key={suggestion} type="button" onClick={() => setQuestion(suggestion)}>{suggestion}</button>
          ))}
        </div>
        {aiAnswer && <div className="analysis-answer" role="status"><strong>Answer</strong><p>{aiAnswer}</p></div>}
      </section>
    </div>
  );
}

export default Analysis;