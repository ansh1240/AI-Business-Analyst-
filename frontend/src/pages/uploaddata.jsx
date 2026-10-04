import { useState } from "react";
import "./uploaddata.css";
import api from "../api/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";

const MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024;

const formatFileSizeMb = (sizeInBytes) => {
  if (!sizeInBytes && sizeInBytes !== 0) return "0.00 MB";
  return `${(sizeInBytes / (1024 * 1024)).toFixed(2)} MB`;
};

const recordRecentActivity = (activity) => {
  try {
    const storedActivities = JSON.parse(
      localStorage.getItem("recentActivities") || "[]"
    );
    const activities = Array.isArray(storedActivities) ? storedActivities : [];
    const entry = {
      ...activity,
      id: `${Date.now()}-${activity.title}`,
      timestamp: new Date().toISOString(),
    };

    localStorage.setItem(
      "recentActivities",
      JSON.stringify([entry, ...activities].slice(0, 8))
    );
  } catch {
    // Activity history is optional and should not interrupt an upload.
  }
};

function UploadData() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadResult, setUploadResult] = useState(null);
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dataQualityRecommendations, setDataQualityRecommendations] = useState([]);
  const [uploadError, setUploadError] = useState("");
  const [selectedColumn, setSelectedColumn] = useState("");
  const [previewSearch, setPreviewSearch] = useState("");
  const handleUpload = async () => {
    if (!selectedFile || uploading) return;

    // Frontend guard: reject oversized files before the request is sent.
    if (selectedFile.size > MAX_UPLOAD_SIZE_BYTES) {
      setUploadError(
        "File size exceeds the 100 MB limit. Please upload a smaller CSV or Excel file."
      );
      return;
    }

    setUploadError("");
    setUploadResult(null);
    setDataQualityRecommendations([]);
    setUploading(true);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await api.post("/upload", formData);
      const data = response.data;

      setUploadResult(data);
      recordRecentActivity({
        title: "Dataset uploaded",
        description: `${data.filename} - ${data.rows} rows and ${data.columns} columns.`,
        icon: "↑",
      });

      try {
        const kpiResponse = await api.post("/kpis", formData);
        localStorage.setItem(
          "businessKpis",
          JSON.stringify(kpiResponse.data)
        );
      } catch (error) {
        console.error("KPI generation error:", error);
        setUploadError(
          error.response?.data?.detail ||
          "Dataset uploaded, but KPI analysis could not be loaded."
        );
      }

      const requests = [
        ["insights", "insights"],
        ["recommendations", "recommendations"],
        ["metrics", "metrics"],
        ["summary", "summary"],
        ["data-quality-recommendations", "qualityRecommendations"],
      ].map(async ([endpoint, resultKey]) => {
        const enrichmentResponse = await api.post(`/${endpoint}`, data);
        return [resultKey, enrichmentResponse.data];
      });

      const results = await Promise.allSettled(requests);
      const failedRequests = results.filter(
        (result) => result.status === "rejected"
      );
      const enrichedResult = results.reduce(
        (result, enrichment) => {
          if (enrichment.status !== "fulfilled") return result;

          const [resultKey, enrichmentData] = enrichment.value;
          if (resultKey === "qualityRecommendations") {
            setDataQualityRecommendations(enrichmentData.recommendations || []);
          } else {
            result[resultKey] = enrichmentData[resultKey];
          }
          return result;
        },
        { ...data }
      );

      setUploadResult(enrichedResult);

      const insightsResult = results.find(
        (result) => result.status === "fulfilled" && result.value[0] === "insights"
      );
      if (insightsResult) {
        const insightCount = insightsResult.value[1]?.insights?.length ?? 0;
        recordRecentActivity({
          title: "Analysis completed",
          description: `${insightCount} insights generated for ${data.filename}.`,
          icon: "✦",
        });
      }

      if (failedRequests.length > 0) {
        setUploadError(
          "Dataset uploaded, but some automated analysis could not be loaded."
        );
      }
    } catch (error) {
      console.error("Upload error:", error);

      let message = "Unable to upload dataset. Please try again.";

      if (error.response?.status === 413) {
        message = "File size exceeds the 100 MB limit. Please upload a smaller CSV or Excel file.";
      } else if (error.response?.data?.detail) {
        message = error.response.data.detail;
      } else if (
        error.message !== "Network Error" &&
        error.message !== "Failed to fetch"
      ) {
        message = error.message;
      }

      setUploadError(message);
    } finally {
      setUploading(false);
    }
  };

  const handleAskAI = async () => {
    if (!aiQuestion.trim()) {
      return;
    }

    if (!uploadResult) {
      setAiAnswer("Please upload a dataset first.");
      return;
    }

    try {
      setAiLoading(true);
      setAiAnswer("");

      const response = await api.post("/ask-ai", {
        question: aiQuestion,
        rows: uploadResult.rows,
        columns: uploadResult.columns,
        data_quality_score: uploadResult.data_quality_score,
        numeric_statistics: uploadResult.numeric_statistics,
        missing_values: uploadResult.missing_values,
        strong_correlations: uploadResult.strong_correlations,
      });

      setAiAnswer(response.data.answer);
    } catch (error) {
      console.error("AI error:", error);
      setAiAnswer(
        error.response?.data?.detail ||
        (error.message !== "Network Error" && error.message !== "Failed to fetch"
          ? error.message
          : "AI analysis failed. Please try again.")
      );
    } finally {
      setAiLoading(false);
    }
  };
  const chartData = uploadResult?.numeric_statistics
  ? Object.entries(uploadResult.numeric_statistics)
      .slice(0, 10)
      .map(([column, stats]) => ({
        name: column,
        average: stats.average,
      }))
  : [];
  const missingChartData = uploadResult?.missing_values
  ? Object.entries(uploadResult.missing_values)
      .filter(([, value]) => value > 0)
      .slice(0, 10)
      .map(([column, value]) => ({
        name: column,
        missing: value,
      }))
  : [];
  const categoryChartData = uploadResult?.categorical_statistics
  ? Object.entries(uploadResult.categorical_statistics)
      .filter(
        ([, stats]) =>
          stats.top_values &&
          stats.top_values.length > 0
      )
      .slice(0, 5)
      .map(([column, stats]) => ({
        name: column,
        value: stats.top_values[0].count,
        category: stats.top_values[0].value,
      }))
  : [];
  const correlationChartData =
  uploadResult?.strong_correlations
    ? uploadResult.strong_correlations.map((item) => ({
        name: `${item.column_1} ↔ ${item.column_2}`,
        correlation: item.correlation,
      }))
    : [];
  const dataQualityChartData = uploadResult
  ? [
      {
        name: "Data Quality",
        score: uploadResult.data_quality_score,
      },
    ]
  : [];
  const handleFileChange = (event) => {
    const file = event.target.files[0];

    if (file) {
      const allowedTypes = [".csv", ".xlsx", ".xls"];
      const fileExtension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();

      if (!allowedTypes.includes(fileExtension)) {
        setSelectedFile(null);
        setUploadResult(null);
        setDataQualityRecommendations([]);
        setUploadError("Please choose a CSV, XLSX, or XLS file.");
        return;
      }

      // Frontend guard: keep the user experience simple and clear before upload.
      if (file.size > MAX_UPLOAD_SIZE_BYTES) {
        setSelectedFile(null);
        setUploadResult(null);
        setDataQualityRecommendations([]);
        setUploadError(
          "File size exceeds the 100 MB limit. Please upload a smaller CSV or Excel file."
        );
        event.target.value = "";
        return;
      }

      setUploadError("");
      setSelectedFile(file);
    }
  };
  const filteredPreview = uploadResult?.preview?.filter((row) =>
  Object.values(row).some((value) =>
    String(value)
      .toLowerCase()
      .includes(previewSearch.toLowerCase())
  )
) || [];

  return (
    <div className="upload-page">

      {/* Page Header */}
      <div className="upload-header">
        <div>
          <span className="upload-label">DATA WORKSPACE</span>

          <h1>Upload Dataset</h1>

          <p>
            Upload your CSV or Excel business data to start analyzing it.
          </p>
        </div>
      </div>

      {/* Upload Card */}
      <div className="upload-card">

        <div className="upload-icon">
          ↑
        </div>

        <h2>
          Upload your business dataset
        </h2>

        <p>
          Select a CSV or Excel file from your computer.
        </p>

        <label className="choose-file-btn">
          Choose File

          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={handleFileChange}
            hidden
          />
        </label>

        {/* Selected File */}
        {selectedFile && (
          <div className="selected-file">
            <div className="file-info">
              <strong>{selectedFile.name}</strong>
              <span className="file-size">
                {formatFileSizeMb(selectedFile.size)}
              </span>
            </div>
            <div className="file-size-meta">
              <span>Maximum allowed: 100 MB</span>
            </div>
          </div>
        )}

        <div className="upload-size-note">Maximum file size: 100 MB</div>

        {/* Step 3.2 - Upload Button */}
        <button
          className="upload-submit-btn"
          disabled={!selectedFile || uploading}
          onClick={handleUpload}
        >
          {uploading ? "Uploading..." : "Upload Dataset"}
        </button>

        <small className="supported-files">
          Supported formats: CSV, XLSX, XLS
        </small>

        {uploadResult && (
  <div className="upload-success">

    <div className="success-title">
      ✓ Dataset Uploaded Successfully
    </div>

    <div className="dataset-info">
      <strong>{uploadResult.filename}</strong>

      <div className="dataset-stats">
        <span>
          <b>{uploadResult.rows.toLocaleString()}</b>
          Rows
        </span>

        <span>
          <b>{uploadResult.columns}</b>
          Columns
        </span>
      </div>
    </div>

  </div>
)}
{uploadResult && (
  <div className="dataset-summary">

    <h3>Dataset Summary</h3>

    <div className="summary-grid">

      <div className="summary-item">
        <span>Total Rows</span>
        <strong>
          {uploadResult.rows.toLocaleString()}
        </strong>
      </div>

      <div className="summary-item">
        <span>Total Columns</span>
        <strong>
          {uploadResult.columns}
        </strong>
      </div>
      <div className="summary-item quality-item">
  <span>Data Quality</span>

  <strong>
    {uploadResult.data_quality_score}%
  </strong>

  <small className="quality-status">
    {uploadResult.data_quality_score >= 90
      ? "Good Quality"
      : uploadResult.data_quality_score >= 70
      ? "Needs Attention"
      : "Poor Quality"}
  </small>

  <div className="quality-bar">
    <div
      className="quality-fill"
      style={{
        width: `${uploadResult.data_quality_score}%`,
      }}
    ></div>
  </div>
</div>
      <div className="summary-item">
        <span>Numeric Columns</span>
        <strong>
          {uploadResult.numeric_columns?.length || 0}
        </strong>
      </div>

      <div className="summary-item">
        <span>Categorical Columns</span>
        <strong>
          {uploadResult.categorical_columns?.length || 0}
        </strong>
      </div>

    </div>

  </div>
)}
{uploadResult?.numeric_columns && (
  <div className="column-analysis">
    {uploadResult?.numeric_statistics && (
  <div className="numeric-statistics">

    <div className="statistics-header">
      <h3>Numeric Statistics</h3>
      <span>Basic statistical analysis</span>
    </div>

    <div className="statistics-table-wrapper">
      <table className="statistics-table">

        <thead>
          <tr>
            <th>Column</th>
            <th>Minimum</th>
            <th>Maximum</th>
            <th>Average</th>
            <th>Median</th>
          </tr>
        </thead>

        <tbody>
          {Object.entries(uploadResult.numeric_statistics).map(
            ([column, stats]) => (
              <tr key={column}>
                <td>{column}</td>
                <td>{stats.min}</td>
                <td>{stats.max}</td>
                <td>{stats.average}</td>
                <td>{stats.median}</td>
              </tr>
            )
          )}
        </tbody>

      </table>
    </div>

  </div>
)}
{uploadResult?.categorical_statistics && (
  <div className="categorical-statistics">

    <div className="statistics-header">
      <h3>Categorical Analysis</h3>
      <span>Top values by frequency</span>
    </div>

    <div className="categorical-list">
      {Object.entries(uploadResult.categorical_statistics).map(
        ([column, data]) => (
          <div className="categorical-card" key={column}>

            <div className="categorical-card-header">
              <strong>{column}</strong>
              <span>
                {data.unique_values} unique values
              </span>
            </div>

            <div className="category-values">
              {data.top_values.map((item) => (
                <div className="category-row" key={item.value}>

                  <span className="category-name">
                    {item.value}
                  </span>

                  <span className="category-count">
                    {item.count.toLocaleString()}
                  </span>

                </div>
              ))}
            </div>

          </div>
        )
      )}
    </div>

  </div>
)}
{uploadResult?.correlation_matrix &&
  Object.keys(uploadResult.correlation_matrix).length > 0 && (
    <div className="correlation-analysis">

      <div className="statistics-header">
        <h3>Correlation Analysis</h3>
        <span>Relationships between numeric columns</span>
      </div>

      <div className="correlation-list">
        {Object.entries(uploadResult.correlation_matrix).map(
          ([column, correlations]) => (
            <div className="correlation-card" key={column}>

              <strong>{column}</strong>

              <div className="correlation-values">
                {Object.entries(correlations).map(
                  ([otherColumn, value]) => (
                    <div
                      className="correlation-row"
                      key={otherColumn}
                    >
                      <span>{otherColumn}</span>

                      <b>{value}</b>
                    </div>
                  )
                )}
              </div>

            </div>
          )
        )}
      </div>

    </div>
  )}
{uploadResult?.strong_correlations &&
  uploadResult.strong_correlations.length > 0 && (
    <div className="strong-correlations">

      <div className="statistics-header">
        <h3>Strong Relationships</h3>
        <span>Correlation ≥ 0.7</span>
      </div>

      <div className="strong-correlation-list">
        {uploadResult.strong_correlations.map(
          (item, index) => (
            <div
              className="strong-correlation-item"
              key={index}
            >
              <div className="relationship-columns">
                <strong>{item.column_1}</strong>
                <span>↔</span>
                <strong>{item.column_2}</strong>
              </div>

              <div className="relationship-score">
                {item.correlation}
              </div>
            </div>
          )
        )}
      </div>

    </div>
  )}
{uploadResult?.summary?.length > 0 && (
  <div className="ai-summary">
    <div className="statistics-header">
      <h3>AI Executive Summary</h3>
      <span>Business overview</span>
    </div>

    <div className="summary-list">
      {uploadResult.summary.map((item, index) => (
        <div className="summary-item" key={index}>
          <span className="summary-number">
            {index + 1}
          </span>

          <p>{item}</p>
        </div>
      ))}
    </div>
  </div>
)}
{uploadResult && (
  <div className="ask-ai-section">
    <div className="statistics-header">
      <div>
        <h3>Ask AI</h3>
        <span>
          Ask questions about your uploaded dataset
        </span>
      </div>
    </div>

    <div className="ask-ai-input-area">
    <div className="ai-suggestions">
  <button
    type="button"
    onClick={() =>
      setAiQuestion("How many rows are in the dataset?")
    }
  >
    How many rows?
  </button>

  <button
    type="button"
    onClick={() =>
      setAiQuestion("How many columns are in the dataset?")
    }
  >
    How many columns?
  </button>

  <button
    type="button"
    onClick={() =>
      setAiQuestion("What is the data quality?")
    }
  >
    Data quality?
  </button>

  <button
    type="button"
    onClick={() =>
      setAiQuestion("What is the strongest correlation?")
    }
  >
    Strongest correlation?
  </button>
</div>
      <input
        type="text"
        value={aiQuestion}
        onChange={(e) =>
          setAiQuestion(e.target.value)
        }
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            handleAskAI();
          }
        }}
        placeholder="Ask something about your dataset..."
      />

      <button
        type="button"
        onClick={handleAskAI}
        disabled={aiLoading || !aiQuestion.trim()}
      >
        {aiLoading ? "Analyzing..." : "Ask AI"}
      </button>
    </div>

    {aiAnswer && (
      <div className="ai-answer">
        <span className="ai-answer-label">
          AI Answer
        </span>

        <p>{aiAnswer}</p>
      </div>
    )}
  </div>
)}
{uploadResult && (
  <div className="anomaly-section">
    <div className="statistics-header">
      <div>
        <h3>Anomaly Detection</h3>
        <span>
          Unusual values detected in numeric columns
        </span>
      </div>
    </div>

    {uploadResult.anomalies &&
    uploadResult.anomalies.length > 0 ? (
      <div className="anomaly-list">
        {uploadResult.anomalies.map((anomaly, index) => (
          <div className="anomaly-card" key={index}>
            <div className="anomaly-number">
              {index + 1}
            </div>

            <div className="anomaly-content">
              <h4>{anomaly.column}</h4>

              <p>
                <strong>{anomaly.count}</strong>{" "}
                unusual values detected.
              </p>

              <span>
                Expected range: {anomaly.lower_bound} –{" "}
                {anomaly.upper_bound}
              </span>
            </div>
          </div>
        ))}
      </div>
    ) : (
      <div className="no-anomaly">
        <h4>No anomalies detected</h4>
        <p>
          No unusual values were detected in the numeric
          columns of this dataset.
        </p>
      </div>
    )}
  </div>
)}
{uploadResult && chartData.length > 0 && (
  <div className="business-chart-section">
    <div className="statistics-header">
      <div>
        <h3>Average Metrics</h3>
        <span>
          Comparison of average values across numeric columns
        </span>
      </div>
    </div>

    <div className="business-chart">
      <ResponsiveContainer width="100%" height={350}>
        <BarChart
          data={chartData}
          margin={{
            top: 20,
            right: 20,
            left: 10,
            bottom: 60,
          }}
        >
          <CartesianGrid strokeDasharray="3 3" />

          <XAxis
            dataKey="name"
            angle={-35}
            textAnchor="end"
            interval={0}
          />

          <YAxis />

          <Tooltip />

          <Bar
            dataKey="average"
            name="Average"
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  </div>
)}
{uploadResult && missingChartData.length > 0 && (
  <div className="business-chart-section">
    <div className="statistics-header">
      <div>
        <h3>Missing Values Analysis</h3>
        <span>
          Columns containing missing values
        </span>
      </div>
    </div>

    <div className="business-chart">
      <ResponsiveContainer width="100%" height={350}>
        <BarChart
          data={missingChartData}
          margin={{
            top: 20,
            right: 20,
            left: 10,
            bottom: 60,
          }}
        >
          <CartesianGrid strokeDasharray="3 3" />

          <XAxis
            dataKey="name"
            angle={-35}
            textAnchor="end"
            interval={0}
          />

          <YAxis />

          <Tooltip />

          <Bar
            dataKey="missing"
            name="Missing Values"
          >
            {missingChartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill="#ef4444"
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  </div>
)}
{uploadResult && categoryChartData.length > 0 && (
  <div className="business-chart-section">
    <div className="statistics-header">
      <div>
        <h3>Category Distribution</h3>
        <span>
          Most common categories across categorical columns
        </span>
      </div>
    </div>

    <div className="business-chart">
      <ResponsiveContainer width="100%" height={350}>
        <BarChart
          data={categoryChartData}
          margin={{
            top: 20,
            right: 20,
            left: 10,
            bottom: 60,
          }}
        >
          <CartesianGrid strokeDasharray="3 3" />

          <XAxis
            dataKey="name"
            angle={-35}
            textAnchor="end"
            interval={0}
          />

          <YAxis />

          <Tooltip />

          <Bar
            dataKey="value"
            name="Count"
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  </div>
)}
{uploadResult && correlationChartData.length > 0 && (
  <div className="business-chart-section">
    <div className="statistics-header">
      <div>
        <h3>Strong Correlations</h3>
        <span>
          Strong relationships between numeric variables
        </span>
      </div>
    </div>

    <div className="business-chart">
      <ResponsiveContainer width="100%" height={350}>
        <BarChart
          data={correlationChartData}
          layout="vertical"
          margin={{
            top: 20,
            right: 30,
            left: 20,
            bottom: 20,
          }}
        >
          <CartesianGrid strokeDasharray="3 3" />

          <XAxis
            type="number"
            domain={[-1, 1]}
          />

          <YAxis
            type="category"
            dataKey="name"
            width={180}
          />

          <Tooltip />
          <ReferenceLine
  x={0}
  stroke="#666"
  strokeDasharray="4 4"
/>
          <Bar
            dataKey="correlation"
            name="Correlation"
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  </div>
)}
{uploadResult && dataQualityChartData.length > 0 && (
  <div className="business-chart-section">
    <div className="statistics-header">
      <div>
        <h3>Data Quality Overview</h3>
        <span>
          Overall quality score of the uploaded dataset
        </span>
      </div>
    </div>

    <div className="business-chart">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart
          data={dataQualityChartData}
          margin={{
            top: 20,
            right: 30,
            left: 20,
            bottom: 20,
          }}
        >
          <CartesianGrid strokeDasharray="3 3" />

          <XAxis dataKey="name" />

          <YAxis
            domain={[0, 100]}
          />

          <Tooltip />

          <Bar
            dataKey="score"
            name="Quality Score (%)"
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  </div>
)}
{uploadResult &&
  dataQualityRecommendations.length > 0 && (
    <div className="ai-insights">
      <div className="statistics-header">
        <div>
          <h3>AI Data Quality Recommendations</h3>
          <span>
            Suggestions to improve dataset quality
          </span>
        </div>
      </div>

      <div className="insights-list">
        {dataQualityRecommendations.map(
          (recommendation, index) => (
            <div
              className="insight-item"
              key={index}
            >
              <span className="insight-number">
                {index + 1}
              </span>

              <p>{recommendation}</p>
            </div>
          )
        )}
      </div>
    </div>
  )}
{uploadResult && uploadResult.column_names?.length > 0 && (
  <div className="column-explorer-section">
    <div className="statistics-header">
      <div>
        <h3>Column Explorer</h3>
        <span>
          Select a column to explore its statistics
        </span>
      </div>
    </div>

    <select
      value={selectedColumn}
      onChange={(e) => setSelectedColumn(e.target.value)}
    >
      <option value="">Select a column</option>

      {uploadResult.column_names.map((column) => (
        <option key={column} value={column}>
          {column}
        </option>
      ))}
    </select>

    {selectedColumn && uploadResult?.numeric_statistics?.[selectedColumn] && (
      <div className="column-explorer-details">
        <h4>{selectedColumn}</h4>

        <div className="metrics-grid">
          <div>
            <span>Minimum</span>
            <strong>
              {uploadResult.numeric_statistics[selectedColumn].min}
            </strong>
          </div>

          <div>
            <span>Maximum</span>
            <strong>
              {uploadResult.numeric_statistics[selectedColumn].max}
            </strong>
          </div>

          <div>
            <span>Average</span>
            <strong>
              {uploadResult.numeric_statistics[selectedColumn].average}
            </strong>
          </div>

          <div>
            <span>Median</span>
            <strong>
              {uploadResult.numeric_statistics[selectedColumn].median}
            </strong>
          </div>
        </div>
      </div>
    )}

    {selectedColumn &&
      uploadResult?.categorical_statistics?.[selectedColumn] && (
        <div className="column-explorer-details">
          <h4>{selectedColumn}</h4>

          <div className="metrics-grid">
            <div>
              <span>Unique Values</span>
              <strong>
                {
                  uploadResult.categorical_statistics[
                    selectedColumn
                  ].unique_values
                }
              </strong>
            </div>

            <div>
              <span>Top Category</span>
              <strong>
                {
                  uploadResult.categorical_statistics[
                    selectedColumn
                  ].top_values?.[0]?.value || "N/A"
                }
              </strong>
            </div>

            <div>
              <span>Top Category Count</span>
              <strong>
                {
                  uploadResult.categorical_statistics[
                    selectedColumn
                  ].top_values?.[0]?.count || 0
                }
              </strong>
            </div>
          </div>
        </div>
      )}
  </div>
)}
  {uploadResult?.metrics && (
    <div className="business-metrics">
      <div className="statistics-header">
        <h3>Key Business Metrics</h3>
        <span>Dataset performance overview</span>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <span>Data Quality</span>
          <strong>{uploadResult.metrics.data_quality}%</strong>
        </div>

        {uploadResult.metrics.highest_average && (
          <div className="metric-card">
            <span>Highest Average</span>
            <strong>
              {uploadResult.metrics.highest_average.column}
            </strong>
            <small>
              {uploadResult.metrics.highest_average.value}
            </small>
          </div>
        )}

        {uploadResult.metrics.lowest_average && (
          <div className="metric-card">
            <span>Lowest Average</span>
            <strong>
              {uploadResult.metrics.lowest_average.column}
            </strong>
            <small>
              {uploadResult.metrics.lowest_average.value}
            </small>
          </div>
        )}

        {uploadResult.metrics.strongest_relationship && (
          <div className="metric-card">
            <span>Strongest Relationship</span>
            <strong>
              {uploadResult.metrics.strongest_relationship.column_1}
              {" ↔ "}
              {uploadResult.metrics.strongest_relationship.column_2}
            </strong>
            <small>
              Correlation:{" "}
              {uploadResult.metrics.strongest_relationship.correlation}
            </small>
          </div>
        )}
      </div>
    </div>
  )}
{uploadResult?.insights?.length > 0 && (
  <div className="ai-insights">

    <div className="statistics-header">
      <h3>AI Business Insights</h3>
      <span>Automated dataset insights</span>
    </div>

    <div className="insights-list">
      {uploadResult.insights.map((insight, index) => (
        <div className="insight-item" key={index}>
          <span className="insight-number">{index + 1}</span>
          <p>{insight}</p>
        </div>
      ))}
    </div>

  </div>
)}
{uploadResult?.recommendations?.length > 0 && (
  <div className="ai-recommendations">
    <div className="statistics-header">
      <h3>AI Business Recommendations</h3>
      <span>Actionable suggestions</span>
    </div>

    <div className="recommendations-list">
      {uploadResult.recommendations.map(
        (recommendation, index) => (
          <div
            className="recommendation-item"
            key={index}
          >
            <span className="recommendation-number">
              {index + 1}
            </span>

            <p>{recommendation}</p>
          </div>
        )
      )}
    </div>
  </div>
)}
    {uploadResult?.missing_values && (
  <div className="missing-analysis">

    <h3>Missing Values</h3>

    <div className="missing-list">
      {Object.entries(uploadResult.missing_values)
        .filter(([, value]) => value > 0)
        .map(([column, value]) => (
          <div className="missing-item" key={column}>
            
            <span className="missing-column">
              {column}
            </span>

            <span className="missing-count">
              {value.toLocaleString()}
            </span>

          </div>
        ))}
    </div>

    {Object.values(uploadResult.missing_values)
      .every((value) => value === 0) && (
        <div className="no-missing">
          ✓ No missing values found
        </div>
      )}

  </div>
)}
    <h3>Column Analysis</h3>

    <div className="column-group">
      <strong>Numeric Columns</strong>

      <div className="column-list">
        {uploadResult.numeric_columns.map((column) => (
          <span key={column} className="column-tag numeric">
            {column}
          </span>
        ))}
      </div>
    </div>

    <div className="column-group">
      <strong>Categorical Columns</strong>

      <div className="column-list">
        {uploadResult.categorical_columns.map((column) => (
          <span key={column} className="column-tag categorical">
            {column}
          </span>
        ))}
      </div>
    </div>
  </div>
)}
{uploadResult?.preview && uploadResult?.column_names && (
  <div className="dataset-preview">

    <div className="preview-header">
      <h3>Dataset Preview</h3>
      <span>
  Showing {filteredPreview.length} of {uploadResult.preview.length} rows
</span>
      <span>First 5 rows</span>
    </div>

    <div className="preview-table-wrapper">
      <table className="preview-table">

        <thead>
          <tr>
            {uploadResult.column_names.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>

        <tbody>
        {filteredPreview.map((row, index) => (            <tr key={index}>
              {uploadResult.column_names.map((column) => (
                <td key={column}>
                  {String(row[column] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>

      </table>
    </div>

  </div>
)}
{uploadResult?.preview?.length > 0 && (
  <div className="preview-search">
    <input
      type="text"
      value={previewSearch}
      onChange={(e) =>
        setPreviewSearch(e.target.value)
      }
      placeholder="Search preview data..."
    />
  </div>
)}
{uploadError && (
  <div className="upload-error">
    <strong>{uploadResult ? "Analysis Notice" : "Upload Failed"}</strong>
    <span>{uploadError}</span>
  </div>
)}

  </div>

    </div>
  );
}

export default UploadData;