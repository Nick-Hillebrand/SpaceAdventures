import { useTranslation } from "react-i18next";
import { useSettings } from "@/hooks/useSettings";

const LANGUAGES = [
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "de", label: "Deutsch", flag: "🇩🇪" },
  { code: "fr", label: "Français", flag: "🇫🇷" },
  { code: "ja", label: "日本語", flag: "🇯🇵" },
  { code: "ru", label: "Русский", flag: "🇷🇺" },
  { code: "es", label: "Español", flag: "🇪🇸" },
] as const;

export default function SettingsPage() {
  const { t, i18n } = useTranslation();
  const { data: status } = useSettings();

  const handleLanguageChange = (code: string) => {
    i18n.changeLanguage(code);
  };

  return (
    <div className="settings-page" data-testid="settings-page">
      <h1>{t("settings.title")}</h1>

      {/* Language */}
      <section className="settings-section">
        <h2>{t("settings.language")}</h2>
        <div className="settings-lang-grid">
          {LANGUAGES.map(({ code, label, flag }) => (
            <button
              key={code}
              type="button"
              className="settings-lang-btn"
              data-testid={`lang-button-${code}`}
              aria-pressed={i18n.language === code}
              onClick={() => handleLanguageChange(code)}
            >
              {flag} {label}
            </button>
          ))}
        </div>
      </section>

      {/* API key status — keys are server configuration (env vars) and are
          intentionally not editable from the browser. */}
      <section className="settings-section">
        <h2>{t("settings.apiKey")}</h2>
        <p
          className="settings-key-status"
          data-testid="nasa-key-status"
          aria-label="nasa-key-status"
        >
          {status?.nasa_key_set ? t("settings.keyConfigured") : t("settings.keyNotConfigured")}
        </p>
      </section>

      <section className="settings-section">
        <h2>{t("settings.n2yoApiKey")}</h2>
        <p
          className="settings-key-status"
          data-testid="n2yo-key-status"
          aria-label="n2yo-key-status"
        >
          {status?.n2yo_key_set ? t("settings.keyConfigured") : t("settings.keyNotConfigured")}
        </p>
      </section>

      <p className="settings-key-hint" data-testid="settings-key-hint">
        {t("settings.serverManaged")}
      </p>
    </div>
  );
}
