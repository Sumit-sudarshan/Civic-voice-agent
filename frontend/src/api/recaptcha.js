const SITE_KEY = import.meta.env.VITE_RECAPTCHA_SITE_KEY;

// Resolves to an empty string (rather than rejecting) when no site key is
// configured, so local dev without VITE_RECAPTCHA_SITE_KEY set still works —
// the backend's verify_recaptcha() treats an empty/missing token the same
// way whenever its own RECAPTCHA_API_KEY isn't configured either.
export function getRecaptchaToken(action) {
  if (!SITE_KEY) return Promise.resolve('');
  return new Promise((resolve, reject) => {
    const grecaptcha = window.grecaptcha?.enterprise;
    if (!grecaptcha) { reject(new Error('reCAPTCHA failed to load. Check your connection and try again.')); return; }
    grecaptcha.ready(() => {
      grecaptcha.execute(SITE_KEY, { action }).then(resolve).catch(reject);
    });
  });
}
