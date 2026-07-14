// Simulated signed-in citizen identity — the Signup page (Phase 5) has no
// backend, so this is the data it "would have" written. Login ID stays the
// demo value CitizenLogin.jsx already accepts ("CivicAgent"); the display
// name and contact fields are what the chat auto-fills instead of asking.
export const DEMO_IDENTITY = {
  loginId: 'CivicAgent',
  firstName: 'Linkin',
  lastName: 'Park',
  phone: '9820011223',
  email: 'linkin.park@example.com',
};

export function getIdentity() {
  return DEMO_IDENTITY;
}
