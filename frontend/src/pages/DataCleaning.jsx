import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/api";
import "./datacleaning.css";

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  if (typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  return value;
}

function getErrorMessage(error) {
  return error.response?.data?.detail || "Unable to load the data cleaning assistant.";
}

function severityClass(level) {
  if (!level) return "severity-low";
  return `severity-${String(level).toLowerCase()}`;
}

function DataCleaning() {
  const navigate = useNavigate();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedActions, setSelectedActions] = useState([]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [result, setResult] = useState(null);
  const [applying, setApplying] = useState(false);

  const loadPlan = async () => {
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await api.get("/data-cleaning");
      const cleaningActions = response.data.cleaning_actions || [];
      setPlan(response.data);
      setSelectedActions(
        cleaningActions
          .filter((action) => [
            "remove_duplicates",
            "trim_text",
            "fill_numeric_missing",
            "fill_categorical_missing",
            "replace_infinite",
            "normalize_categories",
          ].includes(action.name))
          .map((action) => action.name)
      );
    } catch (err) {
      console.error("Data cleaning error:", err);
      setPlan(null);
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPlan();
  }, []);

  const toggleAction = (actionName) => {
    setSelectedActions((current) =>
      current.includes(actionName)
        ? current.filter((name) => name !== actionName)
        : [...current, actionName]
    );
  };

  const applySelectedFixes = async () => {
    if (!selectedActions.length) {
      setError("Please select at least one cleaning action before applying fixes.");
      return;
    }

    setApplying(true);
    setError("");

    try {
      const response = await api.post("/data-cleaning/apply", {
        actions: selectedActions,
      });
      setResult(response.data);
      const refreshed = await api.get("/data-cleaning");
      setPlan(refreshed.data);
      setSelectedActions(
        (refreshed.data.cleaning_actions || []).map((action) => action.name)
      );
    } catch (err) {
      console.error("Apply cleaning error:", err);
      setError(getErrorMessage(err));
    } finally {
      setApplying(false);
    }
  };

  if (loading) {
    return (
      <div className="data-cleaning-page">
        <div className="data-cleaning-state" aria-live="polite">
          <div className="data-cleaning-spinner" aria-hidden="true" />
          <h2>Reviewing dataset quality</h2>
          <p>Analyzing missing values, duplicates, and invalid entries.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="data-cleaning-page">
        <div className="data-cleaning-state" role="alert">
          <div className="data-cleaning-error-mark" aria-hidden="true">!</div>
          <h2>Data Cleaning Assistant Unavailable</h2>
          <p>{error}</p>
          <div className="data-cleaning-state-actions">
            <button className="data-cleaning-primary-btn" type="button" onClick={() => navigate("/upload")}>
              Go to Upload Data
            </button>
            <button className="data-cleaning-secondary-btn" type="button" onClick={loadPlan}>
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!plan) return null;

  const summary = plan.summary || {};
  const issues = plan.issues || [];
  const recommendations = plan.recommendations || [];
  const cleaningActions = plan.cleaning_actions || [];
  const missingValues = issues
    .filter((issue) => issue.type === "missing_values")
    .reduce((total, issue) => total + Number(issue.count || 0), 0);
  const duplicateRows = issues.find((issue) => issue.type === "duplicate_rows")?.count || 0;

  return (
    <div className="data-cleaning-page">
      <header className="data-cleaning-header">
        <div>
          <span className="data-cleaning-eyebrow">AI DATA QUALITY</span>
          <h1>AI Data Cleaning Assistant</h1>
          <p>Automatically detect data quality issues and review recommended cleaning actions.</p>
        </div>
        <button className="data-cleaning-primary-btn" type="button" onClick={loadPlan} disabled={loading}>
          Refresh Review
        </button>
      </header>

      <section className="data-cleaning-section" aria-label="Overview">
        <div className="data-cleaning-overview-grid">
          <div className="data-cleaning-stat-card">
            <span>Data Quality Score</span>
            <strong>{formatNumber(summary.data_quality_score)}%</strong>
          </div>
          <div className="data-cleaning-stat-card">
            <span>Issues Found</span>
            <strong>{formatNumber(summary.issues_found)}</strong>
          </div>
          <div className="data-cleaning-stat-card">
            <span>Missing Values</span>
            <strong>{formatNumber(missingValues)}</strong>
          </div>
          <div className="data-cleaning-stat-card">
            <span>Duplicate Rows</span>
            <strong>{formatNumber(duplicateRows)}</strong>
          </div>
        </div>
      </section>

      <section className="data-cleaning-section">
        <div className="data-cleaning-section-heading">
          <h2>Detected Issues</h2>
        </div>

        <div className="data-cleaning-table-wrap">
          <table className="data-cleaning-table">
            <thead>
              <tr>
                <th>Issue</th>
                <th>Column</th>
                <th>Count</th>
                <th>Percentage</th>
                <th>Severity</th>
                <th>Description</th>
                <th>Recommended Action</th>
              </tr>
            </thead>
            <tbody>
              {issues.length > 0 ? (
                issues.map((issue, index) => (
                  <tr key={`${issue.type}-${issue.column || "dataset"}-${index}`}>
                    <td>{issue.type}</td>
                    <td>{issue.column || "Dataset"}</td>
                    <td>{formatNumber(issue.count)}</td>
                    <td>{formatNumber(issue.percentage)}%</td>
                    <td>
                      <span className={`data-cleaning-severity ${severityClass(issue.severity)}`}>
                        {issue.severity || "low"}
                      </span>
                    </td>
                    <td>{issue.description}</td>
                    <td>{issue.suggested_action}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="7" className="data-cleaning-empty-cell">
                    No quality issues were detected in the current dataset.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="data-cleaning-section">
        <div className="data-cleaning-section-heading">
          <h2>Cleaning Recommendations</h2>
        </div>

        <div className="data-cleaning-options">
          {cleaningActions.map((action) => (
            <label key={action.name} className="data-cleaning-option">
              <input
                type="checkbox"
                checked={selectedActions.includes(action.name)}
                onChange={() => toggleAction(action.name)}
              />
              <div>
                <strong>{action.label}</strong>
                <span>{action.description}</span>
              </div>
            </label>
          ))}
        </div>

        <div className="data-cleaning-action-bar">
          <button className="data-cleaning-secondary-btn" type="button" onClick={() => setPreviewOpen((current) => !current)}>
            Preview Changes
          </button>
          <button className="data-cleaning-primary-btn" type="button" onClick={applySelectedFixes} disabled={applying || !selectedActions.length}>
            {applying ? "Applying..." : "Apply Selected Fixes"}
          </button>
        </div>

        {previewOpen && (
          <div className="data-cleaning-preview-panel">
            <h3>Selected cleanup plan</h3>
            {selectedActions.length > 0 ? (
              <ul>
                {selectedActions.map((actionName) => (
                  <li key={actionName}>
                    {cleaningActions.find((action) => action.name === actionName)?.label || actionName}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No actions selected yet. Select one or more fixes to preview the impact.</p>
            )}
            {recommendations.length > 0 && (
              <div className="data-cleaning-preview-suggestions">
                <strong>Recommended review items</strong>
                <ul>
                  {recommendations.map((recommendation, index) => (
                    <li key={`${recommendation}-${index}`}>{recommendation}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {result && (
        <section className="data-cleaning-section">
          <div className="data-cleaning-section-heading">
            <h2>Cleaning Results</h2>
          </div>

          <div className="data-cleaning-result-grid">
            <div className="data-cleaning-result-card">
              <span>Before</span>
              <div className="data-cleaning-result-content">
                <p>Rows: {formatNumber(result.before?.rows)}</p>
                <p>Missing Values: {formatNumber(result.before?.missing_values)}</p>
                <p>Duplicates: {formatNumber(result.before?.duplicates)}</p>
                <p>Data Quality: {formatNumber(result.before?.data_quality_score)}%</p>
              </div>
            </div>
            <div className="data-cleaning-result-card">
              <span>After</span>
              <div className="data-cleaning-result-content">
                <p>Rows: {formatNumber(result.after?.rows)}</p>
                <p>Missing Values: {formatNumber(result.after?.missing_values)}</p>
                <p>Duplicates: {formatNumber(result.after?.duplicates)}</p>
                <p>Data Quality: {formatNumber(result.after?.data_quality_score)}%</p>
              </div>
            </div>
          </div>

          <div className="data-cleaning-result-metrics">
            <div className="data-cleaning-mini-stat">
              <span>Rows affected</span>
              <strong>{formatNumber(result.rows_affected)}</strong>
            </div>
            <div className="data-cleaning-mini-stat">
              <span>Values changed</span>
              <strong>{formatNumber(result.values_changed)}</strong>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

export default DataCleaning;
