import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useSettings, useSetNasaApiKey, useSetN2yoApiKey } from "@/hooks/useSettings";

const LANGUAGES = [
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "de", label: "Deutsch", flag: "🇩🇪" },
  { code: "fr", label: "Français", flag: "🇫🇷" },
  { code: "ja", label: "日本語", flag: "🇯🇵" },
  { code: "ru", label: "Русский", flag: "🇷🇺" },
  { code: "es", label: "Español", flag: "🇪🇸" },
] as const;

const NASA_KEY_LS = "space-adventures-nasa-key";
const N2YO_KEY_LS = "space-adventures-n2yo-key";

export default function SettingsPage() {
  const { t, i18n } = useTranslation();
  const { data: status } = useSettings();
  const nasaMutation = useSetNasaApiKey();
  const n2yoMutation = useSetN2yoApiKey();

  const [nasaKey, setNasaKey] = useState(() => localStorage.getItem(NASA_KEY_LS) ?? "");
  const [n2yoKey, setN2yoKey] = useState(() => localStorage.getItem(N2YO_KEY_LS) ?? "");

  const handleLanguageChange = (code: string) => {
    i18n.changeLanguage(code);
  };

  const handleNasaSave = (e: FormEvent) => {
    e.preventDefault();
    localStorage.setItem(NASA_KEY_LS, nasaKey);
    nasaMutation.mutate({ api_key: nasaKey });
  };

  const handleN2yoSave = (e: FormEvent) => {
    e.preventDefault();
    localStorage.setItem(N2YO_KEY_LS, n2yoKey);
    n2yoMutation.mutate({ api_key: n2yoKey });
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

      {/* NASA API Key */}
      <section className="settings-section">
        <h2>{t("settings.apiKey")}</h2>
        <p
          className="settings-key-status"
          data-testid="nasa-key-status"
          aria-label="nasa-key-status"
        >
          {status?.nasa_key_set ? t("settings.keyConfigured") : t("settings.keyNotConfigured")}
        </p>
        <form className="settings-key-form" onSubmit={handleNasaSave}>
          <input
            type="password"
            className="settings-key-input"
            data-testid="nasa-key-input"
            aria-label={t("settings.apiKey")}
            value={nasaKey}
            onChange={(e) => setNasaKey(e.target.value)}
            autoComplete="off"
          />
          <button
            type="submit"
            className="settings-key-save"
            data-testid="nasa-key-save"
            disabled={nasaMutation.isPending}
          >
            {t("settings.save")}
          </button>
        </form>
        {nasaMutation.isSuccess && (
          <span className="settings-saved" data-testid="nasa-key-saved">
            {t("settings.saved")}
          </span>
        )}
        {nasaMutation.isError && (
          <span className="settings-error" data-testid="nasa-key-error">
            {t("settings.saveError")}
          </span>
        )}
      </section>

      {/* N2YO API Key */}
      <section className="settings-section">
        <h2>{t("settings.n2yoApiKey")}</h2>
        <p
          className="settings-key-status"
          data-testid="n2yo-key-status"
          aria-label="n2yo-key-status"
        >
          {status?.n2yo_key_set ? t("settings.keyConfigured") : t("settings.keyNotConfigured")}
        </p>
        <form className="settings-key-form" onSubmit={handleN2yoSave}>
          <input
            type="password"
            className="settings-key-input"
            data-testid="n2yo-key-input"
            aria-label={t("settings.n2yoApiKey")}
            value={n2yoKey}
            onChange={(e) => setN2yoKey(e.target.value)}
            autoComplete="off"
          />
          <button
            type="submit"
            className="settings-key-save"
            data-testid="n2yo-key-save"
            disabled={n2yoMutation.isPending}
          >
            {t("settings.save")}
          </button>
        </form>
        {n2yoMutation.isSuccess && (
          <span className="settings-saved" data-testid="n2yo-key-saved">
            {t("settings.saved")}
          </span>
        )}
        {n2yoMutation.isError && (
          <span className="settings-error" data-testid="n2yo-key-error">
            {t("settings.saveError")}
          </span>
        )}
      </section>
    </div>
  );
}
