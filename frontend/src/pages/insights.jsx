import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

import api from "../api/api";
import "./insights.css";

function Insights() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadInsights = async () => {
    try {
      setLoading(true);
      setError("");
      const response = await api.get("/insights");
      setData(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to load insights.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInsights();
  }, []);

  if (loading) {
    return (
      <div className="insights-page">
        <div className="insights-loading">
          <div className="loading-spinner"></div>
          <h3>Analyzing your dataset...</h3>
          <p>Generating business insights from the uploaded data.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="insights-page">
        <div className="insights-empty">
          <div className="empty-icon">✦</div>
          <h2>Insights unavailable</h2>
          <p>{error}</p>
          <button className="primary-insight-btn" onClick={loadInsights}>Try Again</button>
        </div>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const overview = data.overview || {};
  const keyInsights = Array.isArray(data.key_insights) ? data.key_insights : [];
  const performanceInsights = Array.isArray(data.performance_insights) ? data.performance_insights : [];
  const categoryInsights = Array.isArray(data.category_insights) ? data.category_insights : [];
  const trendInsights = Array.isArray(data.trend_insights) ? data.trend_insights : [];
  const correlationInsights = Array.isArray(data.correlation_insights) ? data.correlation_insights : [];
  const anomalyInsights = Array.isArray(data.anomaly_insights) ? data.anomaly_insights : [];
  const qualityItems = Array.isArray(data.data_quality_insights) ? data.data_quality_insights : [];
  const riskItems = Array.isArray(data.risks) ? data.risks : [];
  const opportunityItems = Array.isArray(data.opportunities) ? data.opportunities : [];
  const recommendations = Array.isArray(data.recommendations) ? data.recommendations : [];

  const chartData = performanceInsights.slice(0, 8).map((item) => ({
    name: item.column || "Metric",
    avg: Number(item.average) || 0,
  }));

  return (
    <div className="insights-page">
      <div className="insights-header">
        <div>
          <span className="eyebrow">AI BUSINESS INTELLIGENCE</span>
          <h1>Insights</h1>
          <p>Transform your uploaded dataset into clear, actionable business intelligence.</p>
        </div>

        <button className="refresh-insights" onClick={loadInsights}>↻ Refresh Analysis</button>
      </div>

      <section className="insights-overview">
        <div className="insight-stat-card">
          <div className="stat-icon">✓</div>
          <div>
            <span>Data Quality</span>
            <strong>{overview.data_quality_score ?? 0}%</strong>
            <small>Dataset health</small>
          </div>
        </div>

        <div className="insight-stat-card">
          <div className="stat-icon">✦</div>
          <div>
            <span>Total Insights</span>
            <strong>{overview.total_insights ?? 0}</strong>
            <small>Generated from your data</small>
          </div>
        </div>

        <div className="insight-stat-card">
          <div className="stat-icon">!</div>
          <div>
            <span>Critical Issues</span>
            <strong>{overview.critical_issues ?? 0}</strong>
            <small>Need attention</small>
          </div>
        </div>

        <div className="insight-stat-card">
          <div className="stat-icon">↗</div>
          <div>
            <span>Opportunities</span>
            <strong>{overview.opportunities ?? 0}</strong>
            <small>Potential growth areas</small>
          </div>
        </div>
      </section>

      <section className="insight-section">
        <div className="section-title">
          <div>
            <span>EXECUTIVE INTELLIGENCE</span>
            <h2>AI Executive Summary</h2>
          </div>
        </div>

        <div className="executive-card">
          <div className="executive-icon">✦</div>
          <div>
            <h3>Business Overview</h3>
            <p>{data.executive_summary}</p>
          </div>
        </div>
      </section>

      <section className="insight-section">
        <div className="section-title">
          <div>
            <span>DISCOVERIES</span>
            <h2>Key Insights</h2>
          </div>
        </div>

        <div className="key-insights-grid">
          {keyInsights.map((item, index) => (
            <div className="key-insight-card" key={`${item.title}-${index}`}>
              <div className="insight-card-top">
                <span className={`priority-badge ${String(item.priority || "low").toLowerCase()}`}>
                  {item.priority || "Low"}
                </span>
                <span className="insight-number">0{index + 1}</span>
              </div>

              <h3>{item.title}</h3>
              <p>{item.description}</p>

              {item.metric && <div className="insight-metric">{item.metric}</div>}
            </div>
          ))}
        </div>
      </section>

      <section className="insight-section">
        <div className="section-title">
          <div>
            <span>METRIC ANALYSIS</span>
            <h2>Performance Insights</h2>
          </div>
        </div>

        <div className="chart-card">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={330}>
              <BarChart data={chartData} margin={{ top: 20, right: 20, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                <XAxis dataKey="name" angle={-35} textAnchor="end" interval={0} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="avg" name="Average" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="no-data-box">No numeric performance metrics available.</div>
          )}
        </div>
      </section>

      <div className="two-column-layout">
        <section className="insight-panel">
          <div className="panel-heading">
            <span>CATEGORY ANALYSIS</span>
            <h2>Top Categories</h2>
          </div>

          {categoryInsights.length ? (
            categoryInsights.map((item, index) => (
              <div className="category-block" key={`${item.column}-${index}`}>
                <div className="category-heading">
                  <strong>{item.column}</strong>
                  <span>Top: {item.top_category}</span>
                </div>

                {(item.categories || []).map((cat, catIndex) => (
                  <div className="category-row" key={`${item.column}-${catIndex}`}>
                    <span>{cat.name}</span>
                    <div className="category-bar">
                      <div
                        className="category-bar-fill"
                        style={{
                          width: `${Math.min(100, ((Number(cat.count) || 0) / Math.max(Number(item.count) || 1, 1)) * 100)}%`,
                        }}
                      />
                    </div>
                    <strong>{cat.count}</strong>
                  </div>
                ))}
              </div>
            ))
          ) : (
            <div className="no-data-box">No categorical insights available.</div>
          )}
        </section>

        <section className="insight-panel">
          <div className="panel-heading">
            <span>RELATIONSHIP ANALYSIS</span>
            <h2>Strong Relationships</h2>
          </div>

          {correlationInsights.length ? (
            correlationInsights.map((item, index) => (
              <div className="correlation-card" key={`${item.column_a}-${item.column_b}-${index}`}>
                <div className="correlation-main">
                  <div>
                    <strong>{item.column_a}</strong>
                    <span>↔</span>
                    <strong>{item.column_b}</strong>
                  </div>
                  <div className={`relationship-value ${Number(item.correlation) >= 0 ? "positive" : "negative"}`}>
                    {item.correlation}
                  </div>
                </div>
                <p>
                  {item.strength} {String(item.relationship || "Positive").toLowerCase()} relationship detected.
                </p>
              </div>
            ))
          ) : (
            <div className="no-data-box">No strong relationships detected.</div>
          )}
        </section>
      </div>

      <section className="insight-section">
        <div className="section-title">
          <div>
            <span>TIME-BASED ANALYSIS</span>
            <h2>Trend Insights</h2>
          </div>
        </div>

        <div className="trend-grid">
          {trendInsights.length ? (
            trendInsights.map((item, index) => (
              <div className="trend-card" key={`${item.column || "trend"}-${index}`}>
                <div className="trend-top">
                  <span>{item.column || "Trend"}</span>
                  <strong
                    className={
                      item.direction === "Increasing"
                        ? "trend-up"
                        : item.direction === "Decreasing"
                        ? "trend-down"
                        : "trend-neutral"
                    }
                  >
                    {item.direction || "Stable"}
                  </strong>
                </div>

                <div className="trend-value">
                  {item.change_percent != null ? `${item.change_percent > 0 ? "+" : ""}${item.change_percent}%` : "—"}
                </div>

                <p>
                  {item.start_period && item.end_period
                    ? `Change from ${item.start_period} to ${item.end_period}.`
                    : item.message || "Trend data available."}
                </p>
              </div>
            ))
          ) : (
            <div className="no-data-box">No trend data available.</div>
          )}
        </div>
      </section>

      <section className="insight-section">
        <div className="section-title">
          <div>
            <span>DATA HEALTH</span>
            <h2>Data Quality Insights</h2>
          </div>
        </div>

        <div className="quality-list">
          {qualityItems.map((item, index) => (
            <div className="quality-item" key={`${item.column || "quality"}-${index}`}>
              <div className="quality-status">{item.priority === "High" ? "!" : "✓"}</div>
              <div className="quality-content">
                <div>
                  <strong>{item.column || "Dataset"}</strong>
                  <span className={`priority-badge ${String(item.priority || "low").toLowerCase()}`}>
                    {item.priority || "Low"}
                  </span>
                </div>
                <p>{item.message}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="insight-section">
        <div className="section-title">
          <div>
            <span>EXCEPTION DETECTION</span>
            <h2>Anomaly Insights</h2>
          </div>
        </div>

        <div className="anomaly-card">
          {anomalyInsights.map((item, index) => (
            <div className="anomaly-content" key={`${item.title}-${index}`}>
              <div className="anomaly-icon">!</div>
              <div>
                <h3>{item.title}</h3>
                <p>{item.message}</p>
              </div>
              {item.count !== undefined && <strong>{item.count}</strong>}
            </div>
          ))}
        </div>
      </section>

      <div className="two-column-layout">
        <section className="insight-panel">
          <div className="panel-heading">
            <span>RISK MONITORING</span>
            <h2>Business Risks</h2>
          </div>

          <div className="risk-list">
            {riskItems.map((item, index) => (
              <div className="risk-item" key={`${item.title}-${index}`}>
                <div className="risk-icon">!</div>
                <div>
                  <div className="risk-title">
                    <strong>{item.title}</strong>
                    <span className={`priority-badge ${String(item.priority || "low").toLowerCase()}`}>
                      {item.priority || "Low"}
                    </span>
                  </div>
                  <p>{item.description}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="insight-panel">
          <div className="panel-heading">
            <span>GROWTH AREAS</span>
            <h2>Opportunities</h2>
          </div>

          <div className="opportunity-list">
            {opportunityItems.map((item, index) => (
              <div className="opportunity-item" key={`${item.title}-${index}`}>
                <div className="opportunity-icon">↗</div>
                <div>
                  <div className="risk-title">
                    <strong>{item.title}</strong>
                    <span className={`priority-badge ${String(item.priority || "medium").toLowerCase()}`}>
                      {item.priority || "Medium"}
                    </span>
                  </div>
                  <p>{item.description}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="insight-section">
        <div className="section-title">
          <div>
            <span>NEXT BEST ACTIONS</span>
            <h2>Recommendations</h2>
          </div>
        </div>

        <div className="recommendations-grid">
          {recommendations.map((recommendation, index) => (
            <div className="recommendation-card" key={`${recommendation}-${index}`}>
              <div className="recommendation-number">{String(index + 1).padStart(2, "0")}</div>
              <p>{recommendation}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="insights-footer">
        <span>AI Business Analyst</span>
        <span>Insights generated from the currently uploaded dataset</span>
      </div>
    </div>
  );
}

export default Insights;
