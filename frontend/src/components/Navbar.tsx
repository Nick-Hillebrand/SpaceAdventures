import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMe } from "@/hooks/useAuth";
import { setAccessToken, setRefreshToken } from "@/lib/api";

export default function Navbar() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data: user } = useMe();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  function handleLogout() {
    setAccessToken(null);
    setRefreshToken(null);
    setDropdownOpen(false);
    navigate("/");
  }

  const initials = user
    ? `${user.first_name[0] ?? ""}${user.last_name[0] ?? ""}`.toUpperCase()
    : null;

  return (
    <nav className="navbar">
      <Link to="/" className="navbar-brand">
        Space Adventures
      </Link>
      <div className="navbar-nav">
        <NavLink to="/apod">{t("nav.apod")}</NavLink>
        <NavLink to="/launches">{t("nav.launches")}</NavLink>
        <NavLink to="/iss">{t("nav.iss")}</NavLink>
        <NavLink to="/mars">{t("nav.mars")}</NavLink>
        <NavLink to="/neo">{t("nav.neo")}</NavLink>
        <NavLink to="/space-weather">{t("nav.spaceWeather")}</NavLink>
      </div>
      <div className="navbar-actions">
        {user ? (
          <div className="navbar-user">
            <button
              type="button"
              className="avatar-button"
              aria-label="User menu"
              onClick={() => setDropdownOpen((open) => !open)}
            >
              {initials}
            </button>
            {dropdownOpen && (
              <div className="dropdown-menu" role="menu">
                <Link
                  to="/account"
                  role="menuitem"
                  onClick={() => setDropdownOpen(false)}
                >
                  {t("nav.myAccount")}
                </Link>
                <button type="button" role="menuitem" onClick={handleLogout}>
                  {t("nav.logout")}
                </button>
              </div>
            )}
          </div>
        ) : (
          <Link to="/login" className="login-link">
            {t("nav.login")}
          </Link>
        )}
      </div>
    </nav>
  );
}
