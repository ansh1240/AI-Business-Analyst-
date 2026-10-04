import { useState } from "react";
import api from "../api/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import "./forecast.css";

const forecastNumberFormat = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
});

function Forecast() {
  const [column, setColumn] = useState("");
  const [periods, setPeriods] = useState(5);
  const [columns, setColumns] = useState([]);
  const [forecastData, setForecastData] = useState([]);
  const [forecastRows, setForecastRows] = useState([]);
  const [trend, setTrend] = useState(null);
  const [insight, setInsight] = useState("");
  const [excludedValues, setExcludedValues] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 25;
  const pageCount = Math.max(1, Math.ceil(forecastRows.length / rowsPerPage));
  const visibleForecastRows = forecastRows.slice(
    (currentPage - 1) * rowsPerPage,
    currentPage * rowsPerPage
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadColumns = async () => {
    setError("");

    try {
      const response = await api.get("/forecast-columns");

      setColumns(response.data.columns);

      if (response.data.columns.length > 0) {
        setColumn(response.data.columns[0]);
      } else {
        setError("No numeric columns are available for forecasting.");
      }
    } catch (error) {
      console.error("Forecast error:", error);
      const detail = error.response?.data?.detail;
      setError(
        (Array.isArray(detail) ? detail.map((item) => item.msg).join(" ") : detail) ||
          "Unable to load forecast columns. Please try again."
      );
    }
  };

  const handleForecast = async () => {
    setError("");

    if (!column) {
      setError("Please select a numeric column.");
      return;
    }

    const periodCount = Number(periods);
    if (!Number.isInteger(periodCount) || periodCount < 1 || periodCount > 120) {
      setError("Choose between 1 and 120 forecast periods.");
      return;
    }

    try {
      setLoading(true);

      const response = await api.post("/forecast", {
        column,
        periods: periodCount,
      });
      const data = response.data;

      const historical = data.historical.map(
        (item) => ({
          period: item.period,
          historical: item.value,
        })
      );

      const future = data.forecast.map(
        (item) => ({
          period: item.period,
          forecast: item.value,
        })
      );

      setForecastData([
        ...historical,
        ...future,
      ]);
      setForecastRows([
        ...data.historical.map((item) => ({
          period: item.period,
          type: "Historical",
          value: item.value,
        })),
        ...data.forecast.map((item) => ({
          period: item.period,
          type: "Forecast",
          value: item.value,
        })),
      ]);
      setCurrentPage(1);

      setTrend(data.trend);
      setInsight(data.insight);
      setExcludedValues(data.excluded_values || 0);
    } catch (error) {
      console.error("Forecast error:", error);
      const detail = error.response?.data?.detail;
      setError(
        (Array.isArray(detail) ? detail.map((item) => item.msg).join(" ") : detail) ||
          "Forecast could not be generated. Please try again."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="forecast-page">
      <div className="forecast-header">
        <h1>Sales Forecasting</h1>

        <p>
          Analyze historical trends and estimate
          future values.
        </p>
      </div>

      <div className="forecast-card">
        <div className="forecast-controls">
          <div>
            <label htmlFor="forecast-column">Numeric Column</label>

            <select
              id="forecast-column"
              value={column}
              onChange={(e) => {
                setColumn(e.target.value);
                setForecastData([]);
                setForecastRows([]);
                setInsight("");
                setCurrentPage(1);
              }}
            >
              <option value="">
                Select a column
              </option>

              {columns.map((item) => (
                <option
                  key={item}
                  value={item}
                >
                  {item}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="forecast-periods">Forecast Periods</label>

            <input
              id="forecast-periods"
              type="number"
              min="1"
              max="120"
              value={periods}
              onChange={(e) => {
                setPeriods(e.target.value);
                setForecastData([]);
                setForecastRows([]);
                setInsight("");
                setCurrentPage(1);
              }}
            />
          </div>

          <button
            type="button"
            onClick={
              columns.length === 0
                ? loadColumns
                : handleForecast
            }
            disabled={loading || (columns.length > 0 && !column)}
          >
            {loading
              ? "Forecasting..."
              : columns.length === 0
              ? "Load Dataset"
              : "Generate Forecast"}
          </button>
        </div>

        {error && (
          <div className="error-message forecast-error" role="alert">
            {error}
          </div>
        )}
      </div>

      {forecastData.length > 0 && (
        <>
          <div className="forecast-summary">
            <div>
              <span>Selected Column</span>
              <strong>{column}</strong>
            </div>

            <div>
              <span>Forecast Periods</span>
              <strong>{periods}</strong>
            </div>

            <div>
              <span>Trend</span>
              <strong>
                {trend > 0
                  ? "Increasing"
                  : trend < 0
                  ? "Decreasing"
                  : "Stable"}
              </strong>
            </div>
          </div>

          <div className="forecast-chart-card">
            <div className="forecast-section-heading">
              <div>
                <h2>Forecast Trend</h2>
                <p>Historical values and estimated future values</p>
              </div>
              <span className="forecast-model-label">Damped trend model</span>
            </div>

            <ResponsiveContainer
              width="100%"
              height={360}
            >
              <LineChart
                data={forecastData}
              >
                <CartesianGrid strokeDasharray="3 3" />

                <XAxis dataKey="period" />

                <YAxis />

                <Tooltip />

                <Legend />

                <Line
                  type="monotone"
                  dataKey="historical"
                  name="Historical"
                  stroke="#16a34a"
                  strokeWidth={2}
                  dot={false}
                />

                <Line
                  type="monotone"
                  dataKey="forecast"
                  name="Forecast"
                  stroke="#d97706"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <section className="forecast-insight" aria-live="polite">
            <div className="forecast-insight-mark" aria-hidden="true">i</div>
            <div>
              <h2>Forecast Insight</h2>
              <p>{insight}</p>
              {excludedValues > 0 && (
                <small>{excludedValues} missing or non-finite values were excluded.</small>
              )}
            </div>
          </section>

          <section className="forecast-table-card">
            <div className="forecast-section-heading">
              <div>
                <h2>Forecast Values</h2>
                <p>{forecastRows.length.toLocaleString()} periods in this result</p>
              </div>
            </div>
            <div className="forecast-table-scroll">
              <table className="forecast-table">
                <thead>
                  <tr>
                    <th scope="col">Period</th>
                    <th scope="col">Type</th>
                    <th scope="col">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleForecastRows.map((row) => (
                    <tr key={`${row.type}-${row.period}`}>
                      <td>{row.period}</td>
                      <td>
                        <span className={`forecast-type forecast-type-${row.type.toLowerCase()}`}>
                          {row.type}
                        </span>
                      </td>
                      <td>{forecastNumberFormat.format(row.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="forecast-table-footer">
              <span>
                {forecastRows.length === 0
                  ? "No rows"
                  : `Rows ${(currentPage - 1) * rowsPerPage + 1}-${Math.min(currentPage * rowsPerPage, forecastRows.length)} of ${forecastRows.length.toLocaleString()}`}
              </span>
              <div>
                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                  disabled={currentPage === 1}
                >
                  Previous
                </button>
                <span>Page {currentPage} of {pageCount}</span>
                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.min(pageCount, page + 1))}
                  disabled={currentPage === pageCount}
                >
                  Next
                </button>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

export default Forecast;