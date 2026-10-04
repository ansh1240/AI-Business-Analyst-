import { useEffect, useState } from "react";
import api from "../api/api";

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  if (typeof value === "number") {
    return value.toLocaleString(undefined, {
      maximumFractionDigits: 2,
    });
  }

  return value;
}

function getProfileError(error) {
  return error.response?.data?.detail || "Unable to load data profile.";
}

function DataProfile() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadProfile = async () => {
    try {
      setLoading(true);
      setError("");
      const response = await api.get("/data-profile");
      setProfile(response.data);
    } catch (err) {
      console.error("Data profile error:", err);
      setError(getProfileError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isActive = true;

    api.get("/data-profile")
      .then((response) => {
        if (isActive) {
          setProfile(response.data);
        }
      })
      .catch((err) => {
        console.error("Data profile error:", err);
        if (isActive) {
          setError(getProfileError(err));
        }
      })
      .finally(() => {
        if (isActive) {
          setLoading(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="page-container data-profile-page">
        <div className="profile-state" aria-live="polite">
          <div className="loading-spinner" aria-hidden="true" />
          <h2>Analyzing Dataset</h2>
          <p>Generating column statistics and data quality details.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container data-profile-page">
        <div className="profile-state" role="alert">
          <span className="profile-error-icon" aria-hidden="true">!</span>
          <h2>Data Profile Unavailable</h2>
          <p>{error}</p>
          <button className="profile-refresh-button" onClick={loadProfile}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!profile) {
    return null;
  }

  const overview = profile.overview || {};
  const columnProfile = profile.column_profile || [];
  const categoricalProfiles = columnProfile.filter(
    (column) => column.top_values?.length
  );

  return (
    <div className="page-container data-profile-page">
      <header className="profile-header">
        <div>
          <span className="profile-eyebrow">DATA ANALYSIS</span>
          <h1>Data Profile</h1>
          <p>Dataset structure, quality, and column-level statistics.</p>
        </div>
        <button
          className="profile-refresh-button"
          onClick={loadProfile}
          disabled={loading}
        >
          Refresh Profile
        </button>
      </header>

      <section className="profile-section" aria-labelledby="overview-heading">
        <div className="profile-section-heading">
          <h2 id="overview-heading">Dataset Overview</h2>
          <p>At-a-glance size, structure, and quality.</p>
        </div>
        <div className="profile-overview-grid">
          {[
            ["Total Rows", overview.rows],
            ["Total Columns", overview.columns],
            ["Numeric Columns", overview.numeric_columns],
            ["Categorical Columns", overview.categorical_columns],
            ["Duplicate Rows", overview.duplicate_rows],
            ["Data Quality", `${formatNumber(overview.data_quality_score)}%`],
          ].map(([label, value]) => (
            <div className="profile-stat" key={label}>
              <span>{label}</span>
              <strong>{formatNumber(value)}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="profile-section" aria-labelledby="quality-heading">
        <div className="profile-section-heading">
          <h2 id="quality-heading">Data Quality</h2>
          <p>Missing values by column and overall completeness.</p>
        </div>
        <div className="profile-quality-layout">
          <div className="profile-quality-score">
            <span>Completeness</span>
            <strong>{formatNumber(overview.data_quality_score)}%</strong>
            <div
              className="profile-quality-track"
              role="progressbar"
              aria-label="Dataset completeness"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={overview.data_quality_score || 0}
            >
              <span style={{ width: `${overview.data_quality_score || 0}%` }} />
            </div>
          </div>
          <div className="profile-missing-values">
            <h3>Missing Values</h3>
            <div className="profile-missing-list">
              {Object.entries(profile.missing_values || {}).map(([column, count]) => (
                <div className="profile-missing-row" key={column}>
                  <span>{column}</span>
                  <strong className={count > 0 ? "has-missing" : "no-missing"}>
                    {formatNumber(count)}
                  </strong>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="profile-section" aria-labelledby="columns-heading">
        <div className="profile-section-heading">
          <h2 id="columns-heading">Column Profile</h2>
          <p>Type, missing and distinct values, and numeric statistics.</p>
        </div>
        <div className="profile-table-wrapper">
          <table className="profile-table">
            <thead>
              <tr>
                <th scope="col">Column</th>
                <th scope="col">Data Type</th>
                <th scope="col">Missing</th>
                <th scope="col">Unique</th>
                <th scope="col">Min</th>
                <th scope="col">Max</th>
                <th scope="col">Average</th>
                <th scope="col">Median</th>
              </tr>
            </thead>
            <tbody>
              {columnProfile.map((column) => (
                <tr key={column.name}>
                  <th scope="row">{column.name}</th>
                  <td><span className="profile-type-badge">{column.data_type}</span></td>
                  <td className={column.missing > 0 ? "has-missing" : "no-missing"}>
                    {formatNumber(column.missing)}
                  </td>
                  <td>{formatNumber(column.unique)}</td>
                  <td>{formatNumber(column.min)}</td>
                  <td>{formatNumber(column.max)}</td>
                  <td>{formatNumber(column.average)}</td>
                  <td>{formatNumber(column.median)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {categoricalProfiles.length > 0 && (
        <section className="profile-section" aria-labelledby="categories-heading">
          <div className="profile-section-heading">
            <h2 id="categories-heading">Categorical Analysis</h2>
            <p>Most frequent values for each categorical column.</p>
          </div>
          <div className="profile-category-grid">
            {categoricalProfiles.map((column) => (
              <section className="profile-category" key={column.name}>
                <h3>{column.name}</h3>
                {column.top_values.map((item) => (
                  <div className="profile-category-row" key={item.value}>
                    <span>{item.value}</span>
                    <strong>{formatNumber(item.count)}</strong>
                  </div>
                ))}
              </section>
            ))}
          </div>
        </section>
      )}

      <section className="profile-section" aria-labelledby="correlations-heading">
        <div className="profile-section-heading">
          <h2 id="correlations-heading">Correlation Analysis</h2>
          <p>Pairwise relationships between numeric columns.</p>
        </div>
        <div className="profile-correlation-list">
          {profile.correlations?.length ? profile.correlations.map((item) => (
            <div
              className="profile-correlation-row"
              key={`${item.column1}-${item.column2}`}
            >
              <span><strong>{item.column1}</strong> <span aria-hidden="true">↔</span> <strong>{item.column2}</strong></span>
              <strong className={Math.abs(item.correlation) >= 0.7 ? "strong-correlation" : ""}>
                {formatNumber(item.correlation)}
              </strong>
            </div>
          )) : (
            <p className="profile-empty">Not enough numeric columns for correlation analysis.</p>
          )}
        </div>
      </section>

      <section className="profile-section" aria-labelledby="insights-heading">
        <div className="profile-section-heading">
          <h2 id="insights-heading">Profile Insights</h2>
          <p>Automated observations about this dataset.</p>
        </div>
        <ul className="profile-insights">
          {profile.insights?.map((insight) => <li key={insight}>{insight}</li>)}
        </ul>
      </section>
    </div>
  );
}

export default DataProfile;