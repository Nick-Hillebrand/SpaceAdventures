import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMe } from "@/hooks/useAuth";
import { setAccessToken, setRefreshToken } from "@/lib/api";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" },
  { code: "es", label: "Español" },
  { code: "ja", label: "日本語" },
  { code: "ru", label: "Русский" },
] as const;

function GlobeIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" width="14" height="14">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
    </svg>
  );
}

export default function Navbar() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { data: user } = useMe();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);

  const currentLang = (i18n.resolvedLanguage ?? "en").toUpperCase();

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
        <NavLink to="/solar-system">{t("nav.solarSystem")}</NavLink>
      </div>
      <div className="navbar-actions">
        <div
          className="lang-switcher"
          onBlur={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
              setLangOpen(false);
            }
          }}
        >
          <button
            type="button"
            className="lang-btn"
            aria-label="Change language"
            aria-expanded={langOpen}
            aria-haspopup="true"
            onClick={() => setLangOpen((v) => !v)}
          >
            <GlobeIcon />
            {currentLang}
          </button>
          {langOpen && (
            <div className="dropdown-menu lang-menu" role="menu">
              {LANGUAGES.map(({ code, label }) => (
                <button
                  key={code}
                  type="button"
                  role="menuitem"
                  className={`lang-option${i18n.resolvedLanguage === code ? " lang-option--active" : ""}`}
                  onClick={() => { void i18n.changeLanguage(code); setLangOpen(false); }}
                >
                  <span className="lang-code">{code.toUpperCase()}</span>
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

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
