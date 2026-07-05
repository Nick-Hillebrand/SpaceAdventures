import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMe } from "@/hooks/useAuth";
import { setAccessToken, setRefreshToken } from "@/lib/api";

export default function Navbar() {
  const navigate = useNavigate();
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
                  My Account
                </Link>
                <button type="button" role="menuitem" onClick={handleLogout}>
                  Log Out
                </button>
              </div>
            )}
          </div>
        ) : (
          <Link to="/login" className="login-link">
            Log In
          </Link>
        )}
      </div>
    </nav>
  );
}
