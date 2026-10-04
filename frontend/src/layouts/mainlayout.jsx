import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import api from "../api/api";
import "./mainlayout.css";

function MainLayout() {
  const navigate = useNavigate();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState("");
  const [datasetMissing, setDatasetMissing] = useState(false);
  const [readNotificationIds, setReadNotificationIds] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("read_notification_ids") || "[]");
    } catch {
      return [];
    }
  });

  const unreadNotificationCount = notifications.filter(
    (notification) => !notification.read
  ).length;

  const toggleNotificationRead = (id) => {
    const isRead = readNotificationIds.includes(id);
    const updatedReadIds = isRead
      ? readNotificationIds.filter((notificationId) => notificationId !== id)
      : [...readNotificationIds, id];

    localStorage.setItem("read_notification_ids", JSON.stringify(updatedReadIds));
    setReadNotificationIds(updatedReadIds);
    setNotifications((currentNotifications) =>
      currentNotifications.map((notification) =>
        notification.id === id ? { ...notification, read: !isRead } : notification
      )
    );
  };

  const toggleNotifications = async () => {
    const shouldOpen = !notificationsOpen;
    setNotificationsOpen(shouldOpen);

    if (!shouldOpen) return;

    setNotificationsLoading(true);
    setNotificationsError("");
    setDatasetMissing(false);

    try {
      const response = await api.get("/insights");
      const insights = response.data;
      const overview = insights.overview || {};
      const items = [];

      if (Number(overview.critical_issues) > 0) {
        items.push({
          title: "Critical issues detected",
          message: `${overview.critical_issues} data issue${overview.critical_issues === 1 ? "" : "s"} need review.`,
          to: "/insights",
        });
      }

      const qualityIssues = Array.isArray(insights.data_quality_insights)
        ? insights.data_quality_insights
        : [];
      qualityIssues.slice(0, 3).forEach((issue) => {
        items.push({
          title: `Data quality: ${issue.column}`,
          message: `${issue.count} missing value${Number(issue.count) === 1 ? "" : "s"} (${issue.percentage}%).`,
          to: "/profile",
        });
      });

      const relationships = Array.isArray(insights.correlation_insights)
        ? insights.correlation_insights.length
        : 0;
      if (relationships > 0) {
        items.push({
          title: "Strong relationships found",
          message: `${relationships} metric relationship${relationships === 1 ? "" : "s"} identified in your data.`,
          to: "/insights",
        });
      }

      const recommendations = Array.isArray(insights.recommendations)
        ? insights.recommendations.length
        : 0;
      if (recommendations > 0) {
        items.push({
          title: "Recommendations ready",
          message: `${recommendations} actions are available for your dataset.`,
          to: "/insights",
        });
      }

      if (items.length === 0) {
        items.push({
          title: "Analysis is up to date",
          message: "No critical data issues were found.",
          to: "/insights",
        });
      }

      setNotifications(items.map((item) => {
        const id = `${item.title}|${item.message}`;
        return { ...item, id, read: readNotificationIds.includes(id) };
      }));
    } catch (error) {
      if (error.response?.status === 400) {
        setDatasetMissing(true);
      } else {
        setNotificationsError("Notifications could not be loaded. Please try again.");
      }
      setNotifications([]);
    } finally {
      setNotificationsLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");

    navigate("/login", { replace: true });
  };
  const user = JSON.parse(
  localStorage.getItem("user") || "{}"
);

const userName = user.name || "Analyst";
const userEmail = user.email || "Business User";
  const menuItems = [
    { name: "Dashboard", path: "/dashboard", icon: "▦" },
    { name: "Upload Data", path: "/upload", icon: "↑" },
    { name: "Data Profile", path: "/profile", icon: "◫" },
    { name: "AI Data Cleaning", path: "/data-cleaning", icon: "✎" },
    { name: "AI Analysis", path: "/analysis", icon: "✦" },
    { name: "Insights", path: "/insights", icon: "◈" },
    { name: "AI Auto Dashboard", path: "/auto-dashboard", icon: "✦" },
    { name: "Forecast", path: "/forecast", icon: "↗" },
    { name: "What-If Analysis", path: "/what-if", icon: "?" },
    { name: "Reports", path: "/reports", icon: "▤" },
  ];

  return (
    <div className="app-layout">

      {/* Sidebar */}
      <aside className="sidebar">

        <div className="brand">
          <div className="brand-logo">AI</div>

          <div>
            <h2>Business Analyst</h2>
            <span>AI Analytics Platform</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <p className="menu-title">WORKSPACE</p>

          {menuItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                isActive ? "nav-item active" : "nav-item"
              }
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.name}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="status-dot"></div>
          <div>
            <strong>System Online</strong>
            <span>All services running</span>
          </div>
        </div>

      </aside>

      {/* Main Area */}
      <div className="main-area">

        {/* Navbar */}
        <header className="top-navbar">

          <div>
            <span className="breadcrumb">Workspace</span>
            <h3>AI Business Analyst</h3>
          </div>

          <div className="navbar-right">
            <div className="notification-wrap">
              <button
                className="icon-button"
                type="button"
                title="Notifications"
                aria-label="Notifications"
                aria-expanded={notificationsOpen}
                aria-controls="notification-panel"
                onClick={toggleNotifications}
              >
                🔔
                {unreadNotificationCount > 0 && (
                  <span className="notification-count" aria-hidden="true">
                    {unreadNotificationCount}
                  </span>
                )}
              </button>

              {notificationsOpen && (
                <section className="notification-panel" id="notification-panel" aria-label="Notifications">
                  <div className="notification-panel-header">
                    <h2>Notifications</h2>
                    <button
                      className="notification-close"
                      type="button"
                      aria-label="Close notifications"
                      onClick={() => setNotificationsOpen(false)}
                    >
                      ×
                    </button>
                  </div>

                  {notificationsLoading ? (
                    <p className="notification-state" role="status">Loading notifications...</p>
                  ) : notificationsError ? (
                    <p className="notification-state" role="alert">{notificationsError}</p>
                  ) : datasetMissing ? (
                    <div className="notification-state">
                      <p>Upload a dataset to receive analysis notifications.</p>
                      <NavLink to="/upload" onClick={() => setNotificationsOpen(false)}>
                        Upload data
                      </NavLink>
                    </div>
                  ) : (
                    <div className="notification-list">
                      {notifications.map((notification, index) => (
                        <div
                          className={`notification-item${notification.read ? " is-read" : ""}`}
                          key={`${notification.id}-${index}`}
                        >
                          <NavLink
                            className="notification-link"
                            to={notification.to}
                            onClick={() => {
                              if (!notification.read) toggleNotificationRead(notification.id);
                              setNotificationsOpen(false);
                            }}
                          >
                            <strong>{notification.title}</strong>
                            <span>{notification.message}</span>
                          </NavLink>
                          <input
                            className="notification-read-checkbox"
                            type="checkbox"
                            checked={notification.read}
                            aria-label={`${notification.read ? "Mark as unread" : "Mark as read"}: ${notification.title}`}
                            onChange={() => toggleNotificationRead(notification.id)}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}
            </div>

            <div className="profile">
  <div className="profile-avatar">A</div>

  <div className="profile-info">
  <strong>{userName}</strong>
  <span>{userEmail}</span>
  </div>

  <button
    className="logout-button"
    onClick={handleLogout}
  >
    Logout
  </button>
</div>

          </div>

        </header>

        {/* Page Content */}
        <main className="page-content">
          <Outlet />
        </main>

      </div>

    </div>
  );
}

export default MainLayout;