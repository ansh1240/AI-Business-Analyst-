import { useState } from "react";
import api from "../api/api";
import "./reports.css";

function Reports() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const generateReport = async () => {
    try {
      setLoading(true);
      setError("");

      const response = await api.get("/report");
      setReport(response.data);
    } catch (error) {
      console.error("Report error:", error);
      setError(
        error.response?.data?.detail ||
          "Unable to generate report. Please try again."
      );
    } finally {
      setLoading(false);
    }
  };

  const downloadReport = () => {
    if (!report) return;

    setError("");

    try {
    const content = `
AI BUSINESS ANALYST REPORT

DATASET SUMMARY
----------------
Total Rows: ${report.rows}
Total Columns: ${report.columns}

NUMERIC COLUMNS
----------------
${report.numeric_columns.join(", ")}

CATEGORICAL COLUMNS
----------------
${report.categorical_columns.join(", ")}

MISSING VALUES
----------------
${
  Object.keys(report.missing_values).length > 0
    ? Object.entries(report.missing_values)
        .map(
          ([column, value]) =>
            `${column}: ${value}`
        )
        .join("\n")
    : "No missing values detected."
}

NUMERIC STATISTICS
----------------
${Object.entries(report.numeric_statistics)
  .map(
    ([column, stats]) =>
      `${column}
Average: ${stats.average}
Median: ${stats.median}
Minimum: ${stats.minimum}
Maximum: ${stats.maximum}`
  )
  .join("\n\n")}

ANOMALY DETECTION
----------------
${
  report.anomalies.length > 0
    ? report.anomalies
        .map(
          (item) =>
            `${item.column}: ${item.count} unusual values`
        )
        .join("\n")
    : "No anomalies detected."
}
`;

    const blob = new Blob(
      [content],
      { type: "text/plain" }
    );

    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = "AI_Business_Analyst_Report.txt";
    link.click();

    URL.revokeObjectURL(url);
    } catch (error) {
      console.error("TXT report error:", error);
      setError(error.message || "Unable to download TXT report.");
    }
  };

  const downloadPDFReport = async () => {
    setError("");

    try {
      const response = await api.get("/report/pdf", {
        responseType: "blob",
      });

      const blob = response.data;

      const url = URL.createObjectURL(blob);

      const link = document.createElement("a");
      link.href = url;
      link.download = "AI_Business_Analyst_Report.pdf";

      document.body.appendChild(link);
      link.click();
      link.remove();

      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("PDF report error:", error);
      let message = "Unable to download PDF report.";
      if (error.response?.data instanceof Blob) {
        try {
          const errorData = JSON.parse(await error.response.data.text());
          message = errorData.detail || message;
        } catch {}
      } else {
        message = error.response?.data?.detail || message;
      }
      setError(message);
    }
  };

  return (
    <div className="reports-page">
      <div className="reports-header">
        <div>
          <h1>Business Report</h1>
          <p>
            Generate a summary report from your
            uploaded dataset.
          </p>
        </div>

        <button
          onClick={generateReport}
          disabled={loading}
        >
          {loading
            ? "Generating..."
            : "Generate Report"}
        </button>
      </div>

      {error && (
        <div className="error-message report-error" role="alert">
          {error}
        </div>
      )}

      {report && (
        <>
          <div className="report-actions">
            <button
              onClick={downloadReport}
            >
              Download TXT Report
            </button>

            <button
              onClick={downloadPDFReport}
            >
              Download PDF Report
            </button>
          </div>

          <div className="report-summary">
            <div className="report-card">
              <span>Total Rows</span>
              <strong>{report.rows}</strong>
            </div>

            <div className="report-card">
              <span>Total Columns</span>
              <strong>{report.columns}</strong>
            </div>

            <div className="report-card">
              <span>Numeric Columns</span>
              <strong>
                {report.numeric_columns.length}
              </strong>
            </div>

            <div className="report-card">
              <span>Anomaly Columns</span>
              <strong>
                {report.anomalies.length}
              </strong>
            </div>
          </div>

          <div className="report-section">
            <h2>Dataset Overview</h2>

            <p>
              The uploaded dataset contains{" "}
              <strong>{report.rows}</strong> rows
              and{" "}
              <strong>{report.columns}</strong>{" "}
              columns.
            </p>
          </div>

          <div className="report-section">
            <h2>Missing Values</h2>

            {Object.keys(
              report.missing_values
            ).length > 0 ? (
              <ul>
                {Object.entries(
                  report.missing_values
                ).map(
                  ([column, value]) => (
                    <li key={column}>
                      {column}: {value} missing
                      values
                    </li>
                  )
                )}
              </ul>
            ) : (
              <p>
                No missing values detected.
              </p>
            )}
          </div>

          <div className="report-section">
            <h2>Numeric Statistics</h2>

            <div className="statistics-table">
              {Object.entries(
                report.numeric_statistics
              ).map(
                ([column, stats]) => (
                  <div
                    className="statistics-row"
                    key={column}
                  >
                    <strong>{column}</strong>
                    <span>
                      Avg: {stats.average}
                    </span>
                    <span>
                      Median: {stats.median}
                    </span>
                    <span>
                      Min: {stats.minimum}
                    </span>
                    <span>
                      Max: {stats.maximum}
                    </span>
                  </div>
                )
              )}
            </div>
          </div>

          <div className="report-section">
            <h2>Anomaly Detection</h2>

            {report.anomalies.length > 0 ? (
              <ul>
                {report.anomalies.map(
                  (item) => (
                    <li key={item.column}>
                      <strong>
                        {item.column}
                      </strong>
                      : {item.count} unusual
                      values
                    </li>
                  )
                )}
              </ul>
            ) : (
              <p>
                No anomalies detected.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default Reports;