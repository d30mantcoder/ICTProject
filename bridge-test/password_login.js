// This bridge explicitly starts a password login. Decline optional WebAuthn
// requests before Chromium opens an OS dialog that cannot be used from a phone.
// Microsoft still decides which alternative methods and MFA are available.
(() => {
  const origins = new Set([
    'https://login.microsoftonline.com',
    'https://login.microsoft.com',
    'https://login.live.com',
  ]);
  if (!origins.has(location.origin) || !navigator.credentials) return;

  for (const method of ['get', 'create']) {
    const original = navigator.credentials[method].bind(navigator.credentials);
    Object.defineProperty(navigator.credentials, method, {
      configurable: true,
      value(options) {
        if (options && options.publicKey) {
          return Promise.reject(new DOMException(
            'Passkey request declined for this password sign-in.', 'NotAllowedError'));
        }
        return original(options);
      },
    });
  }
})();
