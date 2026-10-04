import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import api from "../api/api";
import "./whatif.css";

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
  return error.response?.data?.detail || "Unable to run the scenario analysis.";
}

const chartColors = ["#111827", "#2563eb"];

function WhatIf() {
  const [columns, setColumns] = useState([]);
  const [selectedMetric, setSelectedMetric] = useState("");
  const [scenarioType, setScenarioType] = useState("increase_by_percent");
  const [changePercent, setChangePercent] = useState(10);
  const [changeValue, setChangeValue] = useState(1000);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState(() => {
    try {
      const saved = sessionStorage.getItem("whatif-history");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadColumns = async () => {
    setLoading(true);
    setError("");

    try {
      const response = await api.get("/what-if/columns");
      const availableColumns = response.data.columns || [];
      setColumns(availableColumns);
      setSelectedMetric((current) => current || availableColumns[0] || "");
    } catch (err) {
      console.error("What-if columns error:", err);
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadColumns();
  }, []);

  useEffect(() => {
    sessionStorage.setItem("whatif-history", JSON.stringify(history.slice(0, 5)));
  }, [history]);

  const chartData = useMemo(() => {
    if (!result) return [];
    return [
      { name: "Original", value: Number(result.results.original_value) },
      { name: "Scenario", value: Number(result.results.scenario_value) },
    ];
  }, [result]);

  const runScenario = async (event) => {
    event.preventDefault();

    if (!selectedMetric) {
      setError("Select a metric to simulate.");
      return;
    }

    try {
      setError("");
      const payload = {
        column: selectedMetric,
        scenario_type: scenarioType,
      };

      if (scenarioType === "increase_by_percent" || scenarioType === "decrease_by_percent") {
        payload.change_percent = Number(changePercent);
      } else {
        payload.change_value = Number(changeValue);
      }

      const response = await api.post("/what-if", payload);
      setResult(response.data);

      const scenarioLabel =
        scenarioType === "increase_by_percent"
          ? `Increase by ${changePercent}%`
          : scenarioType === "decrease_by_percent"
            ? `Decrease by ${changePercent}%`
            : `Change by ${changeValue}`;

      const entry = {
        id: `${selectedMetric}-${Date.now()}`,
        scenario: `${selectedMetric} • ${scenarioLabel}`,
        original: Number(response.data.results.original_value),
        scenarioValue: Number(response.data.results.scenario_value),
        change: Number(response.data.results.absolute_change),
        date: new Date().toLocaleString(),
      };

      setHistory((current) => [entry, ...current].slice(0, 5));
    } catch (err) {
      console.error("What-if analysis error:", err);
      setError(getErrorMessage(err));
    }
  };

  const clearHistory = () => {
    setHistory([]);
  };

  if (loading) {
    return (
      <div className="whatif-page">
        <div className="whatif-state" aria-live="polite">
          <div className="whatif-spinner" aria-hidden="true" />
          <h2>Preparing scenario builder</h2>
          <p>Loading numeric variables for what-if simulation.</p>
        </div>
      </div>
    );
  }

  if (error && !columns.length) {
    return (
      <div className="whatif-page">
        <div className="whatif-state" role="alert">
          <div className="whatif-error-mark" aria-hidden="true">!</div>
          <h2>What-If Analysis Unavailable</h2>
          <p>{error}</p>
          <button className="whatif-primary-btn" type="button" onClick={loadColumns}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="whatif-page">
      <header className="whatif-header">
        <div>
          <span className="whatif-eyebrow">SCENARIO MODELING</span>
          <h1>What-If Analysis</h1>
          <p>Simulate business scenarios and understand their potential impact on key metrics.</p>
        </div>
      </header>

      <section className="whatif-section">
        <div className="whatif-section-heading">
          <h2>Scenario Builder</h2>
        </div>

        <form className="whatif-form" onSubmit={runScenario}>
          <div className="whatif-field">
            <label htmlFor="metric-select">Select metric</label>
            <select id="metric-select" value={selectedMetric} onChange={(event) => setSelectedMetric(event.target.value)}>
              <option value="">Choose a metric</option>
              {columns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </div>

          <div className="whatif-field">
            <label htmlFor="scenario-type">Scenario type</label>
            <select id="scenario-type" value={scenarioType} onChange={(event) => setScenarioType(event.target.value)}>
              <option value="increase_by_percent">Increase by %</option>
              <option value="decrease_by_percent">Decrease by %</option>
              <option value="change_by_value">Change by value</option>
            </select>
          </div>

          {scenarioType === "change_by_value" ? (
            <div className="whatif-field">
              <label htmlFor="change-value">Change value</label>
              <input
                id="change-value"
                type="number"
                value={changeValue}
                onChange={(event) => setChangeValue(event.target.value)}
              />
            </div>
          ) : (
            <div className="whatif-field">
              <label htmlFor="change-percent">Change %</label>
              <input
                id="change-percent"
                type="number"
                value={changePercent}
                min={-100}
                max={1000}
                onChange={(event) => setChangePercent(event.target.value)}
              />
            </div>
          )}

          <div className="whatif-form-actions">
            <button className="whatif-primary-btn" type="submit">
              Run Scenario
            </button>
          </div>
        </form>

        {error && <p className="whatif-error-text">{error}</p>}
      </section>

      {result && (
        <>
          <section className="whatif-section">
            <div className="whatif-section-heading">
              <h2>Scenario Result</h2>
            </div>

            <div className="whatif-result-grid">
              <div className="whatif-result-card">
                <span>Original Value</span>
                <strong>{formatNumber(result.results.original_value)}</strong>
              </div>
              <div className="whatif-result-card">
                <span>Scenario Value</span>
                <strong>{formatNumber(result.results.scenario_value)}</strong>
              </div>
              <div className="whatif-result-card">
                <span>Absolute Change</span>
                <strong>{formatNumber(result.results.absolute_change)}</strong>
              </div>
              <div className="whatif-result-card">
                <span>Percentage Change</span>
                <strong>{formatNumber(result.results.percentage_change)}%</strong>
              </div>
            </div>
          </section>

          <section className="whatif-section">
            <div className="whatif-section-heading">
              <h2>Impact Visualization</h2>
            </div>

            <div className="whatif-chart-wrap">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(value) => formatNumber(value)} />
                  <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                    {chartData.map((entry, index) => (
                      <Cell key={`${entry.name}-${index}`} fill={chartColors[index % chartColors.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {result.kpi_impact?.length > 0 && (
              <div className="whatif-kpi-impact">
                <h3>Related KPI impacts</h3>
                <div className="whatif-impact-list">
                  {result.kpi_impact.map((item) => (
                    <div key={item.name} className="whatif-impact-item">
                      <strong>{item.name}</strong>
                      <p>Original: {formatNumber(item.original_value)}</p>
                      <p>Scenario: {formatNumber(item.scenario_value)}</p>
                      <p>Delta: {formatNumber(item.absolute_change)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="whatif-section">
            <div className="whatif-section-heading">
              <h2>AI Scenario Insight</h2>
            </div>
            <div className="whatif-insight-box">
              <p>{result.insight}</p>
            </div>
          </section>
        </>
      )}

      <section className="whatif-section">
        <div className="whatif-section-heading whatif-history-heading">
          <h2>Scenario History</h2>
          <button className="whatif-secondary-btn" type="button" onClick={clearHistory}>
            Clear History
          </button>
        </div>

        {history.length > 0 ? (
          <div className="whatif-history-list">
            {history.map((entry) => (
              <div key={entry.id} className="whatif-history-item">
                <div>
                  <strong>{entry.scenario}</strong>
                  <span>{entry.date}</span>
                </div>
                <div className="whatif-history-values">
                  <p>Original: {formatNumber(entry.original)}</p>
                  <p>Scenario: {formatNumber(entry.scenarioValue)}</p>
                  <p>Change: {formatNumber(entry.change)}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="whatif-empty-state">No recent scenarios yet. Run one to review the history.</p>
        )}
      </section>
    </div>
  );
}

export default WhatIf;
