import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import api from "../api/api";
import "./autodashboard.css";

const CHART_COLORS = [
  "#3b82f6",
  "#14b8a6",
  "#f59e0b",
  "#8b5cf6",
  "#ef4444",
  "#22c55e",
  "#ec4899",
  "#0ea5e9",
];

const formatNumber = (value) => {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "N/A";
  }

  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "N/A";
  }

  if (Math.abs(numericValue) >= 1_000_000_000) {
    return `${(numericValue / 1_000_000_000).toFixed(2)}B`;
  }

  if (Math.abs(numericValue) >= 1_000_000) {
    return `${(numericValue / 1_000_000).toFixed(2)}M`;
  }

  if (Math.abs(numericValue) >= 1_000) {
    return `${(numericValue / 1_000).toFixed(2)}K`;
  }

  if (Math.abs(numericValue) >= 1) {
    return numericValue.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  return numericValue.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  });
};

const readableError = (error) => {
  if (error?.response?.data?.detail) {
    return error.response.data.detail;
  }

  if (error?.message === "Network Error" || error?.message === "Failed to fetch") {
    return "Network connection issue. Please check your connection and try again.";
  }

  return "Unable to generate the dashboard right now. Please try again.";
};

function AutoDashboard() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadDashboard = async () => {
    try {
      setLoading(true);
      setError("");
      const response = await api.get("/auto-dashboard");
      setDashboard(response.data || null);
    } catch (err) {
      console.error("Auto dashboard error:", err);
      setDashboard(null);
      setError(readableError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  const renderChart = (chart) => {
    if (!chart || !Array.isArray(chart.data) || chart.data.length === 0) {
      return <div className="auto-dashboard-empty-chart">No chart data available.</div>;
    }

    const chartData = chart.data;
    const valueKey = chart.y_axis || "value";

    switch (chart.chart_type) {
      case "line":
        return (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{ top: 12, right: 16, left: 0, bottom: 12 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} minTickGap={12} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value) => formatNumber(value)} />
              <Line type="monotone" dataKey={valueKey} stroke="#3b82f6" strokeWidth={3} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        );
      case "area":
        return (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chartData} margin={{ top: 12, right: 16, left: 0, bottom: 12 }}>
              <defs>
                <linearGradient id={`fill-${chart.id}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.45} />
                  <stop offset="95%" stopColor="#14b8a6" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} minTickGap={12} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value) => formatNumber(value)} />
              <Area type="monotone" dataKey={valueKey} stroke="#14b8a6" fill={`url(#fill-${chart.id})`} strokeWidth={3} />
            </AreaChart>
          </ResponsiveContainer>
        );
      case "pie":
        return (
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={chartData}
                dataKey={valueKey}
                nameKey="name"
                innerRadius={52}
                outerRadius={82}
                paddingAngle={4}
              >
                {chartData.map((entry, index) => (
                  <Cell key={`${entry.name}-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatNumber(value)} />
            </PieChart>
          </ResponsiveContainer>
        );
      case "scatter":
        return (
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ top: 20, right: 12, bottom: 12, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis type="number" dataKey={chart.x_axis} name={chart.x_axis} tick={{ fontSize: 11 }} />
              <YAxis type="number" dataKey={chart.y_axis} name={chart.y_axis} tick={{ fontSize: 11 }} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(value) => formatNumber(value)} />
              <Scatter data={chartData} fill="#8b5cf6" />
            </ScatterChart>
          </ResponsiveContainer>
        );
      default:
        return (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} margin={{ top: 12, right: 16, left: 0, bottom: 12 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} minTickGap={12} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value) => formatNumber(value)} />
              <Bar dataKey={valueKey} radius={[8, 8, 0, 0]}>
                {chartData.map((entry, index) => (
                  <Cell key={`${entry.name}-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        );
    }
  };

  if (loading) {
    return (
      <div className="auto-dashboard-page auto-dashboard-loading-state" aria-live="polite">
        <div className="auto-dashboard-loading-card">
          <div className="auto-dashboard-spinner" aria-hidden="true" />
          <h2>Analyzing dataset...</h2>
          <p>Generating your personalized dashboard.</p>
        </div>
      </div>
    );
  }

  if (!dashboard && error && error.toLowerCase().includes("dataset")) {
    return (
      <div className="auto-dashboard-page">
        <div className="auto-dashboard-empty-state">
          <div className="auto-dashboard-empty-icon">✦</div>
          <h2>No dataset available</h2>
          <p>Upload a CSV or Excel file to generate your AI dashboard.</p>
          <button className="auto-dashboard-primary-btn" type="button" onClick={() => navigate("/upload")}>
            Upload Dataset
          </button>
        </div>
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="auto-dashboard-page">
        <div className="auto-dashboard-empty-state">
          <div className="auto-dashboard-empty-icon">!</div>
          <h2>Dashboard unavailable</h2>
          <p>{error}</p>
          <button className="auto-dashboard-primary-btn" type="button" onClick={loadDashboard}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  const dataset = dashboard.dataset || {};
  const kpis = Array.isArray(dashboard.kpis) ? dashboard.kpis : [];
  const charts = Array.isArray(dashboard.charts) ? dashboard.charts : [];
  const insights = Array.isArray(dashboard.insights) ? dashboard.insights : [];
  const alerts = Array.isArray(dashboard.alerts) ? dashboard.alerts : [];
  const recommendedQuestions = Array.isArray(dashboard.recommended_questions) ? dashboard.recommended_questions : [];
  const dataQuality = dashboard.data_quality || {};

  return (
    <div className="auto-dashboard-page">
      <header className="auto-dashboard-header">
        <div>
          <span className="auto-dashboard-eyebrow">AI BUSINESS INTELLIGENCE</span>
          <h1>AI Auto Dashboard</h1>
          <p>Automatically generated insights and visualizations from your dataset.</p>
        </div>

        <button className="auto-dashboard-refresh-btn" type="button" onClick={loadDashboard}>
          Refresh Dashboard
        </button>
      </header>

      <section className="auto-dashboard-overview-grid">
        {[
          ["Rows", dataset.rows ?? 0],
          ["Columns", dataset.columns ?? 0],
          ["Numeric Fields", Array.isArray(dataset.numeric_columns) ? dataset.numeric_columns.length : 0],
          ["Categorical Fields", Array.isArray(dataset.categorical_columns) ? dataset.categorical_columns.length : 0],
          ["Data Quality", `${Math.round(Number(dataQuality.score || 0))}%`],
        ].map(([label, value]) => (
          <div className="auto-dashboard-stat-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      <section className="auto-dashboard-section">
        <div className="auto-dashboard-section-heading">
          <span>AI KPI CARDS</span>
          <h2>Performance indicators</h2>
        </div>

        {kpis.length > 0 ? (
          <div className="auto-dashboard-kpi-grid">
            {kpis.map((kpi, index) => (
              <div className="auto-dashboard-kpi-card" key={`${kpi.title}-${index}`}>
                <div className="auto-dashboard-kpi-meta">
                  <span>{kpi.title}</span>
                  <div className="auto-dashboard-kpi-tag">{kpi.calculation}</div>
                </div>
                <h3>{kpi.formatted_value || formatNumber(kpi.value)}</h3>
                <p>{kpi.description}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="auto-dashboard-empty-box">No KPI metrics were detected for the current dataset.</div>
        )}
      </section>

      <section className="auto-dashboard-section">
        <div className="auto-dashboard-summary-card">
          <div className="auto-dashboard-summary-label">AI Business Summary</div>
          <p>{dashboard.summary || "The current dataset is ready for analysis."}</p>
        </div>
      </section>

      <section className="auto-dashboard-section">
        <div className="auto-dashboard-section-heading">
          <span>AUTO-GENERATED CHARTS</span>
          <h2>Dynamic visual analysis</h2>
        </div>

        {charts.length > 0 ? (
          <div className="auto-dashboard-chart-grid">
            {charts.map((chart) => (
              <article className="auto-dashboard-chart-card" key={chart.id}>
                <div className="auto-dashboard-chart-header">
                  <div>
                    <h3>{chart.title}</h3>
                    <p>{chart.description}</p>
                  </div>
                  <span className="auto-dashboard-chart-type">{chart.chart_type}</span>
                </div>
                {renderChart(chart)}
              </article>
            ))}
          </div>
        ) : (
          <div className="auto-dashboard-empty-box">No useful charts could be generated from this dataset.</div>
        )}
      </section>

      <section className="auto-dashboard-section">
        <div className="auto-dashboard-section-heading">
          <span>KEY INSIGHTS</span>
          <h2>Highlights from your dataset</h2>
        </div>

        {insights.length > 0 ? (
          <div className="auto-dashboard-insight-grid">
            {insights.map((insight, index) => (
              <div className="auto-dashboard-insight-card" key={`${insight.title}-${index}`}>
                <div className="auto-dashboard-insight-header">
                  <span className={`auto-dashboard-pill auto-dashboard-pill-${String(insight.type || "info").toLowerCase()}`}>
                    {String(insight.type || "info").toUpperCase()}
                  </span>
                  <strong>{insight.value || insight.title}</strong>
                </div>
                <p>{insight.description}</p>
                {insight.metric && <div className="auto-dashboard-insight-metric">{insight.metric}</div>}
              </div>
            ))}
          </div>
        ) : (
          <div className="auto-dashboard-empty-box">No key insights were produced for this dataset.</div>
        )}
      </section>

      <section className="auto-dashboard-section">
        <div className="auto-dashboard-section-heading">
          <span>ALERTS</span>
          <h2>Monitoring and risks</h2>
        </div>

        {alerts.length > 0 ? (
          <div className="auto-dashboard-alert-list">
            {alerts.map((alert, index) => (
              <div className="auto-dashboard-alert-card" key={`${alert.title}-${index}`}>
                <div className="auto-dashboard-alert-top">
                  <h3>{alert.title}</h3>
                  <span className={`auto-dashboard-severity auto-dashboard-severity-${String(alert.severity || "low").toLowerCase()}`}>
                    {String(alert.severity || "LOW").toUpperCase()}
                  </span>
                </div>
                <p>{alert.message}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="auto-dashboard-empty-box">No alerts were generated for the current dataset.</div>
        )}
      </section>

      <section className="auto-dashboard-section">
        <div className="auto-dashboard-section-heading">
          <span>RECOMMENDED QUESTIONS</span>
          <h2>Explore the data further</h2>
        </div>

        {recommendedQuestions.length > 0 ? (
          <div className="auto-dashboard-question-grid">
            {recommendedQuestions.map((question, index) => (
              <button
                key={`${question}-${index}`}
                type="button"
                className="auto-dashboard-question-card"
                onClick={() => navigate("/analysis", { state: { prefilledQuestion: question } })}
              >
                {question}
              </button>
            ))}
          </div>
        ) : (
          <div className="auto-dashboard-empty-box">No recommended questions were created for this dataset.</div>
        )}
      </section>
    </div>
  );
}

export default AutoDashboard;
