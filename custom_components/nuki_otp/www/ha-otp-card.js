/**
 * HA OTP Card
 * A custom Lovelace card that displays a one-time password (OTP/TOTP) with a
 * live countdown ring, grouped digits, tap-to-copy and reveal/hide controls.
 *
 * Two sources are supported:
 *   1. `entity`  — read the current code from an existing Home Assistant entity.
 *   2. `secret`  — generate RFC-6238 TOTP codes in the browser via Web Crypto.
 *
 * Zero dependencies, no build step. Drop the file in `config/www/` and add it
 * as a dashboard resource of type "module".
 */

const VERSION = "1.0.0";

/* ------------------------------------------------------------------ *
 *  Base32 + TOTP (RFC 4648 / RFC 6238) — runs entirely client-side.  *
 * ------------------------------------------------------------------ */

const B32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

/** Decode a base32 string (the format authenticator secrets use) to bytes. */
function base32Decode(input) {
  const clean = String(input)
    .toUpperCase()
    .replace(/=+$/, "")
    .replace(/\s+/g, "");
  let bits = 0;
  let value = 0;
  const out = [];
  for (const char of clean) {
    const idx = B32_ALPHABET.indexOf(char);
    if (idx === -1) throw new Error(`Invalid base32 character: "${char}"`);
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      bits -= 8;
      out.push((value >>> bits) & 0xff);
    }
  }
  return new Uint8Array(out);
}

/**
 * Generate an RFC-6238 TOTP code.
 * @returns {Promise<string>} zero-padded code of `digits` length.
 */
async function generateTotp(secret, { digits = 6, period = 30, algorithm = "SHA-1" } = {}) {
  const key = base32Decode(secret);
  const counter = Math.floor(Date.now() / 1000 / period);

  // 8-byte big-endian counter.
  const counterBytes = new Uint8Array(8);
  let temp = counter;
  for (let i = 7; i >= 0; i--) {
    counterBytes[i] = temp & 0xff;
    temp = Math.floor(temp / 256);
  }

  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    key,
    { name: "HMAC", hash: { name: algorithm } },
    false,
    ["sign"]
  );
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", cryptoKey, counterBytes));

  // Dynamic truncation.
  const offset = sig[sig.length - 1] & 0x0f;
  const binary =
    ((sig[offset] & 0x7f) << 24) |
    ((sig[offset + 1] & 0xff) << 16) |
    ((sig[offset + 2] & 0xff) << 8) |
    (sig[offset + 3] & 0xff);

  const code = (binary % 10 ** digits).toString().padStart(digits, "0");
  return code;
}

/* ------------------------------------------------------------------ *
 *  The card element.                                                  *
 * ------------------------------------------------------------------ */

class HaOtpCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._code = "";
    this._error = "";
    this._revealed = true;
    this._copied = false;
    this._timer = null;
    this._rendered = false;
    this._totpCounter = null;
  }

  /* ---- Lovelace lifecycle ---- */

  setConfig(config) {
    if (!config.entity && !config.secret) {
      throw new Error("You must define either `entity` or `secret`.");
    }
    this._config = {
      name: "One-Time Password",
      digits: 6,
      period: 30,
      algorithm: "SHA-1",
      icon: "mdi:shield-key",
      reveal_by_default: true,
      ...config,
    };
    this._revealed = this._config.reveal_by_default !== false;
    this._rendered = false; // force a fresh DOM build
    this._totpCounter = null; // invalidate the cached code (secret may have changed)
    this._startTimer();
    this._refresh();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._config && this._config.entity) this._refresh();
  }

  connectedCallback() {
    this._startTimer();
  }

  disconnectedCallback() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  getCardSize() {
    return 3;
  }

  static getConfigElement() {
    return document.createElement("ha-otp-card-editor");
  }

  static getStubConfig() {
    return { secret: "JBSWY3DPEHPK3PXP", name: "Demo OTP" };
  }

  /* ---- internals ---- */

  _startTimer() {
    if (this._timer) clearInterval(this._timer);
    // Tick every 250ms so the ring animates smoothly and code rotation is prompt.
    this._timer = setInterval(() => this._refresh(), 250);
  }

  get _period() {
    return Number(this._config.period) || 30;
  }

  _secondsRemaining() {
    const period = this._period;
    return period - (Math.floor(Date.now() / 1000) % period);
  }

  async _computeCode() {
    const cfg = this._config;
    if (cfg.entity) {
      const stateObj = this._hass && this._hass.states[cfg.entity];
      if (!stateObj) {
        this._error = `Entity "${cfg.entity}" not found.`;
        this._code = "";
        return;
      }
      this._error = "";
      this._code = String(stateObj.state || "").trim();
      return;
    }
    try {
      this._error = "";
      // The code only changes once per time-step, so skip the HMAC when the
      // counter hasn't advanced (the timer ticks every 250ms for the ring).
      const counter = Math.floor(Date.now() / 1000 / this._period);
      if (this._code && this._totpCounter === counter) return;
      this._totpCounter = counter;
      this._code = await generateTotp(cfg.secret, {
        digits: Number(cfg.digits) || 6,
        period: this._period,
        algorithm: cfg.algorithm || "SHA-1",
      });
    } catch (err) {
      this._error = err.message || String(err);
      this._code = "";
    }
  }

  async _refresh() {
    const prevCode = this._code;
    await this._computeCode();
    if (!this._rendered) {
      this._render();
    } else {
      // Only re-render the dynamic parts on a tick.
      this._update(prevCode !== this._code);
    }
  }

  _formatCode(code) {
    if (!code) return "------";
    if (!this._revealed) return code.replace(/./g, "•");
    // Group into two halves for readability (e.g. 123 456).
    if (code.length === 6) return `${code.slice(0, 3)} ${code.slice(3)}`;
    if (code.length === 8) return `${code.slice(0, 4)} ${code.slice(4)}`;
    return code;
  }

  async _copy() {
    if (!this._code) return;
    try {
      await navigator.clipboard.writeText(this._code);
    } catch (e) {
      // Fallback for non-secure contexts.
      const ta = document.createElement("textarea");
      ta.value = this._code;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      this.shadowRoot.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
      } catch (_) {
        /* ignore */
      }
      ta.remove();
    }
    this._copied = true;
    this._update(false);
    clearTimeout(this._copyTimer);
    this._copyTimer = setTimeout(() => {
      this._copied = false;
      this._update(false);
    }, 1400);
  }

  _toggleReveal() {
    this._revealed = !this._revealed;
    this._update(false);
  }

  /* ---- rendering ---- */

  _render() {
    const root = this.shadowRoot;
    root.innerHTML = `
      <style>${HaOtpCard.styles}</style>
      <ha-card>
        <div class="container">
          <div class="header">
            <div class="icon-wrap">
              <ha-icon icon="${this._config.icon}"></ha-icon>
            </div>
            <div class="title">${this._escape(this._config.name)}</div>
          </div>

          <div class="code-row" role="button" tabindex="0" title="Tap to copy">
            <span class="code" part="code"></span>
          </div>

          <div class="error" hidden></div>

          <div class="footer">
            <div class="countdown">
              <svg viewBox="0 0 36 36" class="ring" aria-hidden="true">
                <circle class="ring-bg" cx="18" cy="18" r="15.915"></circle>
                <circle class="ring-fg" cx="18" cy="18" r="15.915"></circle>
              </svg>
              <span class="secs"></span>
            </div>
            <div class="spacer"></div>
            <button class="btn reveal" title="Show / hide code" aria-label="Show or hide code">
              <ha-icon icon="mdi:eye"></ha-icon>
            </button>
            <button class="btn copy" title="Copy code" aria-label="Copy code">
              <ha-icon icon="mdi:content-copy"></ha-icon>
            </button>
          </div>
        </div>
      </ha-card>
    `;

    root.querySelector(".code-row").addEventListener("click", () => this._copy());
    root.querySelector(".code-row").addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this._copy();
      }
    });
    root.querySelector(".copy").addEventListener("click", (e) => {
      e.stopPropagation();
      this._copy();
    });
    root.querySelector(".reveal").addEventListener("click", (e) => {
      e.stopPropagation();
      this._toggleReveal();
    });

    this._rendered = true;
    this._update(true);
  }

  _update(codeChanged) {
    const root = this.shadowRoot;
    if (!root || !this._rendered) return;

    const codeEl = root.querySelector(".code");
    const errEl = root.querySelector(".error");
    const secsEl = root.querySelector(".secs");
    const ringFg = root.querySelector(".ring-fg");
    const revealIcon = root.querySelector(".reveal ha-icon");
    const copyBtn = root.querySelector(".copy");
    const copyIcon = root.querySelector(".copy ha-icon");

    // Error state.
    if (this._error) {
      errEl.hidden = false;
      errEl.textContent = this._error;
      codeEl.textContent = "------";
    } else {
      errEl.hidden = true;
      codeEl.textContent = this._formatCode(this._code);
    }

    if (codeChanged) {
      codeEl.classList.remove("flip");
      // Force reflow to restart the animation.
      void codeEl.offsetWidth;
      codeEl.classList.add("flip");
    }

    // Countdown.
    const remaining = this._secondsRemaining();
    const fraction = remaining / this._period;
    secsEl.textContent = remaining;
    const circumference = 2 * Math.PI * 15.915;
    ringFg.style.strokeDasharray = `${circumference}`;
    ringFg.style.strokeDashoffset = `${circumference * (1 - fraction)}`;
    ringFg.classList.toggle("urgent", remaining <= 5);
    secsEl.classList.toggle("urgent", remaining <= 5);

    // Reveal toggle icon.
    revealIcon.setAttribute("icon", this._revealed ? "mdi:eye" : "mdi:eye-off");

    // Copy feedback.
    if (this._copied) {
      copyBtn.classList.add("copied");
      copyIcon.setAttribute("icon", "mdi:check");
    } else {
      copyBtn.classList.remove("copied");
      copyIcon.setAttribute("icon", "mdi:content-copy");
    }
  }

  _escape(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[c]));
  }
}

HaOtpCard.styles = `
  :host { --otp-accent: var(--primary-color, #03a9f4); }
  ha-card {
    overflow: hidden;
  }
  .container {
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .header {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .icon-wrap {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: color-mix(in srgb, var(--otp-accent) 16%, transparent);
    color: var(--otp-accent);
    flex: 0 0 auto;
  }
  .icon-wrap ha-icon { --mdc-icon-size: 22px; }
  .title {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--primary-text-color);
    letter-spacing: 0.2px;
  }
  .code-row {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 10px 12px;
    border-radius: 14px;
    background: var(--secondary-background-color, rgba(127,127,127,0.12));
    cursor: pointer;
    user-select: none;
    transition: background 0.15s ease, transform 0.08s ease;
    outline: none;
  }
  .code-row:hover { background: color-mix(in srgb, var(--otp-accent) 10%, var(--secondary-background-color, rgba(127,127,127,0.12))); }
  .code-row:active { transform: scale(0.99); }
  .code-row:focus-visible { box-shadow: 0 0 0 2px var(--otp-accent); }
  .code {
    font-family: "Roboto Mono", "SF Mono", ui-monospace, monospace;
    font-size: clamp(2rem, 9vw, 2.9rem);
    font-weight: 700;
    letter-spacing: 0.12em;
    color: var(--primary-text-color);
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
  }
  .code.flip { animation: flip 0.4s ease; }
  @keyframes flip {
    0% { opacity: 0.2; transform: translateY(-6px); }
    100% { opacity: 1; transform: translateY(0); }
  }
  .error {
    color: var(--error-color, #db4437);
    font-size: 0.85rem;
    text-align: center;
  }
  .footer {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .countdown {
    position: relative;
    width: 40px;
    height: 40px;
    flex: 0 0 auto;
  }
  .ring { width: 100%; height: 100%; transform: rotate(-90deg); }
  .ring-bg {
    fill: none;
    stroke: var(--divider-color, rgba(127,127,127,0.25));
    stroke-width: 3;
  }
  .ring-fg {
    fill: none;
    stroke: var(--otp-accent);
    stroke-width: 3;
    stroke-linecap: round;
    transition: stroke-dashoffset 0.25s linear, stroke 0.3s ease;
  }
  .ring-fg.urgent { stroke: var(--error-color, #db4437); }
  .secs {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--secondary-text-color);
    font-variant-numeric: tabular-nums;
  }
  .secs.urgent { color: var(--error-color, #db4437); }
  .spacer { flex: 1 1 auto; }
  .btn {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    border: none;
    background: var(--secondary-background-color, rgba(127,127,127,0.12));
    color: var(--secondary-text-color);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s ease, color 0.15s ease, transform 0.08s ease;
  }
  .btn:hover { background: color-mix(in srgb, var(--otp-accent) 18%, transparent); color: var(--otp-accent); }
  .btn:active { transform: scale(0.92); }
  .btn ha-icon { --mdc-icon-size: 20px; }
  .btn.copied { background: var(--success-color, #43a047); color: #fff; }
`;

customElements.define("ha-otp-card", HaOtpCard);

/* ------------------------------------------------------------------ *
 *  Minimal GUI config editor.                                         *
 * ------------------------------------------------------------------ */

class HaOtpCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  _emit() {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    if (!this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const c = this._config;
    this.shadowRoot.innerHTML = `
      <style>
        .form { display: flex; flex-direction: column; gap: 12px; padding: 8px 0; }
        label { display: flex; flex-direction: column; gap: 4px; font-size: 0.85rem; color: var(--secondary-text-color); }
        input, select { padding: 8px 10px; border-radius: 8px; border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color, #fff); color: var(--primary-text-color); font-size: 0.95rem; }
        .hint { font-size: 0.75rem; color: var(--secondary-text-color); opacity: 0.8; }
        .row { display: flex; gap: 12px; }
        .row > label { flex: 1; }
      </style>
      <div class="form">
        <label>Name
          <input id="name" type="text" value="${this._v(c.name)}" placeholder="One-Time Password">
        </label>
        <label>Entity (optional)
          <input id="entity" type="text" value="${this._v(c.entity)}" placeholder="sensor.totp_code">
          <span class="hint">Read the code from an existing HA entity. Leave empty to use a secret.</span>
        </label>
        <label>TOTP secret (optional)
          <input id="secret" type="text" value="${this._v(c.secret)}" placeholder="JBSWY3DPEHPK3PXP">
          <span class="hint">Base32 authenticator secret. Used only when no entity is set.</span>
        </label>
        <div class="row">
          <label>Digits
            <select id="digits">
              <option value="6" ${Number(c.digits) !== 8 ? "selected" : ""}>6</option>
              <option value="8" ${Number(c.digits) === 8 ? "selected" : ""}>8</option>
            </select>
          </label>
          <label>Period (s)
            <input id="period" type="number" min="10" max="120" value="${this._v(c.period) || 30}">
          </label>
          <label>Algorithm
            <select id="algorithm">
              ${["SHA-1", "SHA-256", "SHA-512"]
                .map((a) => `<option value="${a}" ${(c.algorithm || "SHA-1") === a ? "selected" : ""}>${a}</option>`)
                .join("")}
            </select>
          </label>
        </div>
        <label>Icon
          <input id="icon" type="text" value="${this._v(c.icon) || "mdi:shield-key"}" placeholder="mdi:shield-key">
        </label>
      </div>
    `;

    const bind = (id, key, transform) => {
      const el = this.shadowRoot.getElementById(id);
      el.addEventListener("input", () => {
        const val = transform ? transform(el.value) : el.value;
        if (val === "" || val == null) delete this._config[key];
        else this._config[key] = val;
        this._emit();
      });
    };
    bind("name", "name");
    bind("entity", "entity");
    bind("secret", "secret");
    bind("digits", "digits", (v) => Number(v));
    bind("period", "period", (v) => Number(v));
    bind("algorithm", "algorithm");
    bind("icon", "icon");
  }

  _v(val) {
    return val == null ? "" : String(val).replace(/"/g, "&quot;");
  }
}

customElements.define("ha-otp-card-editor", HaOtpCardEditor);

/* ------------------------------------------------------------------ *
 *  Register with the card picker.                                     *
 * ------------------------------------------------------------------ */

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ha-otp-card",
  name: "OTP Card",
  description: "Displays a one-time password (TOTP) with a live countdown, copy and reveal controls.",
  preview: true,
  documentationURL: "https://github.com/paperclip/ha-otp-card",
});

console.info(
  `%c HA-OTP-CARD %c v${VERSION} `,
  "color:#fff;background:#03a9f4;font-weight:700;border-radius:4px 0 0 4px;padding:2px 6px;",
  "color:#03a9f4;background:#222;border-radius:0 4px 4px 0;padding:2px 6px;"
);
