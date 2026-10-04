import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./dashboard.css";

const formatKPI = (value, prefix = "") => {
  if (
    value === undefined ||
    value === null ||
    value === "" ||
    isNaN(value)
  ) {
    return "N/A";
  }

  return `${prefix}${Number(value).toLocaleString("en-IN", {
    maximumFractionDigits: 2,
  })}`;
};

const getRecentActivities = () => {
  try {
    const activities = JSON.parse(localStorage.getItem("recentActivities") || "[]");
    return Array.isArray(activities) ? activities.slice(0, 8) : [];
  } catch {
    return [];
  }
};

function Dashboard() {
  const navigate = useNavigate();
  const [activities] = useState(getRecentActivities);

  const [kpis] = useState(() => {
    const storedKpis = localStorage.getItem("businessKpis");

    if (!storedKpis) return null;

    try {
      const parsedKpis = JSON.parse(storedKpis);

      if (
        parsedKpis?.summary &&
        parsedKpis?.metrics &&
        parsedKpis?.detected_business_columns
      ) {
        return parsedKpis;
      }

      localStorage.removeItem("businessKpis");
      return null;
    } catch {
      localStorage.removeItem("businessKpis");
      return null;
    }
  });

  const hasDataset = Boolean(
    kpis?.summary &&
    kpis?.metrics &&
    kpis?.detected_business_columns
  );

  const revenueColumn =
    kpis?.detected_business_columns?.revenue;

  const salesColumn =
    kpis?.detected_business_columns?.sales;

  const profitColumn =
    kpis?.detected_business_columns?.profit;

  const quantityColumn =
    kpis?.detected_business_columns?.quantity;

  return (
    <div className="dashboard">

      {/* =========================
          HEADER
      ========================= */}

      <div className="dashboard-header">

        <div>
          <span className="dashboard-label">
            OVERVIEW
          </span>

          <h1>Business Dashboard</h1>

          <p>
            Monitor your business performance and discover
            actionable insights.
          </p>
        </div>

        <button
          className="upload-btn"
          onClick={() => navigate("/upload")}
        >
          + Upload Dataset
        </button>

      </div>


      {/* =========================
          PRIMARY KPI CARDS
      ========================= */}

      <div className="kpi-grid">

        {/* Total Rows */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Total Rows</span>
            <div className="kpi-icon">▤</div>
          </div>

          <h2>
            {kpis?.summary?.total_rows?.toLocaleString(
              "en-IN"
            ) || "0"}
          </h2>

          <p className="kpi-muted">
            {hasDataset
              ? "Records in dataset"
              : "No dataset uploaded"}
          </p>

        </div>


        {/* Total Columns */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Total Columns</span>
            <div className="kpi-icon">▥</div>
          </div>

          <h2>
            {kpis?.summary?.total_columns || "0"}
          </h2>

          <p className="kpi-muted">
            {hasDataset
              ? "Columns detected"
              : "No dataset available"}
          </p>

        </div>


        {/* Revenue */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Revenue</span>
            <div className="kpi-icon">₹</div>
          </div>

          <h2>
            {revenueColumn &&
            kpis?.metrics?.[revenueColumn]
              ? formatKPI(
                  kpis.metrics[revenueColumn].total,
                  "₹"
                )
              : "N/A"}
          </h2>

          <p className="kpi-muted">
            {revenueColumn
              ? "Total revenue detected"
              : "Revenue column not detected"}
          </p>

          {revenueColumn &&
            kpis?.metrics?.[revenueColumn] && (
              <small className="kpi-average">
                Avg:{" "}
                {formatKPI(
                  kpis.metrics[revenueColumn].average,
                  "₹"
                )}
              </small>
            )}

        </div>


        {/* Sales */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Sales</span>
            <div className="kpi-icon">↗</div>
          </div>

          <h2>
            {salesColumn &&
            kpis?.metrics?.[salesColumn]
              ? formatKPI(
                  kpis.metrics[salesColumn].total
                )
              : "N/A"}
          </h2>

          <p className="kpi-muted">
            {salesColumn
              ? "Total sales detected"
              : "Sales column not detected"}
          </p>

          {salesColumn &&
            kpis?.metrics?.[salesColumn] && (
              <small className="kpi-average">
                Avg:{" "}
                {formatKPI(
                  kpis.metrics[salesColumn].average
                )}
              </small>
            )}

        </div>


        {/* Profit */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Profit</span>
            <div className="kpi-icon">₹</div>
          </div>

          <h2>
            {profitColumn &&
            kpis?.metrics?.[profitColumn]
              ? formatKPI(
                  kpis.metrics[profitColumn].total,
                  "₹"
                )
              : "N/A"}
          </h2>

          <p className="kpi-muted">
            {profitColumn
              ? "Total profit detected"
              : "Profit column not detected"}
          </p>

          {profitColumn &&
            kpis?.metrics?.[profitColumn] && (
              <small className="kpi-average">
                Avg:{" "}
                {formatKPI(
                  kpis.metrics[profitColumn].average,
                  "₹"
                )}
              </small>
            )}

        </div>


        {/* Quantity */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Quantity</span>
            <div className="kpi-icon">#</div>
          </div>

          <h2>
            {quantityColumn &&
            kpis?.metrics?.[quantityColumn]
              ? formatKPI(
                  kpis.metrics[quantityColumn].total
                )
              : "N/A"}
          </h2>

          <p className="kpi-muted">
            {quantityColumn
              ? "Total quantity detected"
              : "Quantity column not detected"}
          </p>

          {quantityColumn &&
            kpis?.metrics?.[quantityColumn] && (
              <small className="kpi-average">
                Avg:{" "}
                {formatKPI(
                  kpis.metrics[quantityColumn].average
                )}
              </small>
            )}

        </div>


        {/* Numeric Metrics */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Numeric Metrics</span>
            <div className="kpi-icon">#</div>
          </div>

          <h2>
            {kpis?.summary?.numeric_columns || "0"}
          </h2>

          <p className="kpi-muted">
            {hasDataset
              ? "Numeric columns analyzed"
              : "Waiting for dataset"}
          </p>

        </div>


        {/* Dataset Status */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Dataset Status</span>
            <div className="kpi-icon">✓</div>
          </div>

          <h2>
            {hasDataset ? "Ready" : "—"}
          </h2>

          <p className="kpi-muted">
            {hasDataset
              ? "Analysis available"
              : "Not calculated yet"}
          </p>

        </div>

      </div>


      {/* =========================
          KEY BUSINESS METRICS
      ========================= */}

      <div className="section-heading">

        <div>
          <span className="dashboard-label">
            ANALYTICS
          </span>

          <h2>Key Business Metrics</h2>

          <p>
            Important metrics automatically detected from
            your dataset.
          </p>
        </div>

      </div>


      <div className="kpi-grid">

        {/* Data Quality */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Data Quality</span>
            <div className="kpi-icon">✓</div>
          </div>

          <h2>
            {kpis?.key_metrics?.data_quality_score ??
              "N/A"}
            {kpis?.key_metrics?.data_quality_score !==
              undefined &&
              "%"}
          </h2>

          <p className="kpi-muted">
            Dataset quality score
          </p>

        </div>


        {/* Highest Average */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Highest Average</span>
            <div className="kpi-icon">↑</div>
          </div>

          <h2>
            {kpis?.key_metrics?.highest_average
              ? formatKPI(
                  kpis.key_metrics.highest_average.value
                )
              : "N/A"}
          </h2>

          <p className="kpi-muted">
            {kpis?.key_metrics?.highest_average?.column ||
              "No numeric data"}
          </p>

        </div>


        {/* Lowest Average */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Lowest Average</span>
            <div className="kpi-icon">↓</div>
          </div>

          <h2>
            {kpis?.key_metrics?.lowest_average
              ? formatKPI(
                  kpis.key_metrics.lowest_average.value
                )
              : "N/A"}
          </h2>

          <p className="kpi-muted">
            {kpis?.key_metrics?.lowest_average?.column ||
              "No numeric data"}
          </p>

        </div>


        {/* Strongest Relationship */}
        <div className="kpi-card">

          <div className="kpi-top">
            <span>Strongest Relationship</span>
            <div className="kpi-icon">↔</div>
          </div>

          <h2>
            {kpis?.key_metrics?.strongest_relationship
              ? Number(
                  kpis.key_metrics
                    .strongest_relationship.correlation
                ).toFixed(2)
              : "N/A"}
          </h2>

          <p className="kpi-muted">
            {kpis?.key_metrics?.strongest_relationship
              ? kpis.key_metrics.strongest_relationship.columns.join(
                  " ↔ "
                )
              : "No relationship found"}
          </p>

        </div>

      </div>


      {/* =========================
          MAIN DASHBOARD GRID
      ========================= */}

      <div className="dashboard-grid">


        {/* Business Performance */}
        <div className="dashboard-card performance-card">

          <div className="card-header">

            <div>
              <h3>Business Performance</h3>

              <p>
                Revenue and sales performance overview
              </p>
            </div>

            <select>
              <option>Last 30 Days</option>
              <option>Last 90 Days</option>
              <option>This Year</option>
            </select>

          </div>


          {hasDataset ? (

            <>

              <div className="performance-summary">

                <span>
                  Dataset analyzed successfully
                </span>

                <strong>
                  {kpis.summary.total_rows?.toLocaleString(
                    "en-IN"
                  )}{" "}
                  records
                </strong>

              </div>


              <div className="performance-active">

                <div className="performance-stat">
                  <span>Total Records</span>

                  <strong>
                    {kpis.summary.total_rows?.toLocaleString(
                      "en-IN"
                    )}
                  </strong>
                </div>


                <div className="performance-stat">
                  <span>Total Columns</span>

                  <strong>
                    {kpis.summary.total_columns}
                  </strong>
                </div>


                <div className="performance-stat">
                  <span>Numeric Metrics</span>

                  <strong>
                    {kpis.summary.numeric_columns}
                  </strong>
                </div>


                <div className="performance-message">
                  Dataset analysis is available. Use AI
                  Analysis and Insights to explore detailed
                  business trends.
                </div>

              </div>

            </>

          ) : (

            <div className="empty-chart">

              <div className="chart-symbol">⌁</div>

              <h4>No data available</h4>

              <p>
                Upload a business dataset to generate
                performance charts.
              </p>

              <button
                className="upload-btn"
                onClick={() => navigate("/upload")}
              >
                Upload Dataset
              </button>

            </div>

          )}

        </div>


        {/* Quick Actions */}
        <div className="dashboard-card">

          <div className="card-header">

            <div>
              <h3>Quick Actions</h3>

              <p>
                Start analyzing your business data
              </p>
            </div>

          </div>


          <div className="quick-actions">

            <button
              className="action-item"
              onClick={() => navigate("/upload")}
            >
              <span className="action-icon">↑</span>

              <div>
                <strong>Upload Data</strong>
                <small>Import CSV or Excel</small>
              </div>

              <span>→</span>
            </button>


            <button
              className="action-item"
              onClick={() => navigate("/analysis")}
            >
              <span className="action-icon">✦</span>

              <div>
                <strong>AI Analysis</strong>
                <small>Ask questions about data</small>
              </div>

              <span>→</span>
            </button>


            <button
              className="action-item"
              onClick={() => navigate("/insights")}
            >
              <span className="action-icon">◈</span>

              <div>
                <strong>View Insights</strong>
                <small>Discover business trends</small>
              </div>

              <span>→</span>
            </button>


            <button
              className="action-item"
              onClick={() => navigate("/forecast")}
            >
              <span className="action-icon">↗</span>

              <div>
                <strong>Forecast Data</strong>
                <small>Predict future trends</small>
              </div>

              <span>→</span>
            </button>


            <button
              className="action-item"
              onClick={() => navigate("/reports")}
            >
              <span className="action-icon">▤</span>

              <div>
                <strong>View Reports</strong>
                <small>Generate business reports</small>
              </div>

              <span>→</span>
            </button>

          </div>

        </div>

      </div>


      {/* =========================
          BOTTOM SECTION
      ========================= */}

      <div className="dashboard-grid bottom-grid">


        {/* AI Insights */}
        <div className="dashboard-card">

          <div className="card-header">

            <div>
              <h3>AI Insights</h3>

              <p>
                Latest findings from your data
              </p>
            </div>

          </div>


          {hasDataset ? (

            <div className="insights-list">

              {kpis?.key_metrics?.highest_average && (
                <div className="insight-item">

                  <span className="insight-icon">↑</span>

                  <div>
                    <strong>Highest Average</strong>

                    <p>
                      {
                        kpis.key_metrics.highest_average
                          .column
                      }{" "}
                      has the highest average value of{" "}
                      {formatKPI(
                        kpis.key_metrics.highest_average
                          .value
                      )}
                      .
                    </p>
                  </div>

                </div>
              )}


              {kpis?.key_metrics?.lowest_average && (
                <div className="insight-item">

                  <span className="insight-icon">↓</span>

                  <div>
                    <strong>Lowest Average</strong>

                    <p>
                      {
                        kpis.key_metrics.lowest_average
                          .column
                      }{" "}
                      has the lowest average value of{" "}
                      {formatKPI(
                        kpis.key_metrics.lowest_average
                          .value
                      )}
                      .
                    </p>
                  </div>

                </div>
              )}


              {kpis?.key_metrics?.strongest_relationship && (
                <div className="insight-item">

                  <span className="insight-icon">↔</span>

                  <div>
                    <strong>
                      Strong Relationship
                    </strong>

                    <p>
                      {kpis.key_metrics
                        .strongest_relationship.columns.join(
                          " ↔ "
                        )}{" "}
                      have a correlation of{" "}
                      {Number(
                        kpis.key_metrics
                          .strongest_relationship
                          .correlation
                      ).toFixed(2)}
                      .
                    </p>
                  </div>

                </div>
              )}


              {!kpis?.key_metrics?.highest_average &&
                !kpis?.key_metrics?.lowest_average &&
                !kpis?.key_metrics
                  ?.strongest_relationship && (

                  <div className="empty-state">

                    <div className="empty-state-icon">
                      ◷
                    </div>

                    <h4>
                      No specific insights found
                    </h4>

                    <p>
                      The dataset does not contain enough
                      information for automatic insights.
                    </p>

                  </div>

                )}

            </div>

          ) : (

            <div className="empty-state">

              <div className="empty-state-icon">
                ◷
              </div>

              <h4>No insights available</h4>

              <p>
                Upload a dataset to see insights from
                your data.
              </p>

            </div>

          )}

        </div>


        {/* Recent Activity */}
        <div className="dashboard-card">

          <div className="card-header">

            <div>
              <h3>Recent Activity</h3>

              <p>
                Your latest analysis activity
              </p>
            </div>

          </div>


          {activities.length > 0 ? (
            <div className="activity-list">
              {activities.map((activity) => (
                <article className="activity-item" key={activity.id}>
                  <div className="activity-icon">{activity.icon || "◷"}</div>
                  <div className="activity-content">
                    <strong>{activity.title}</strong>
                    <p>{activity.description}</p>
                    <time dateTime={activity.timestamp}>
                      {new Date(activity.timestamp).toLocaleString()}
                    </time>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-state-icon">◷</div>
              <h4>No recent activity</h4>
              <p>Your dataset uploads and analysis history will appear here.</p>
            </div>
          )}

        </div>

      </div>

    </div>
  );
}

export default Dashboard;